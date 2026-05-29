"""QThread bridge between the asyncio Stellarium server and the Qt UI.

Owns its own asyncio event loop running inside ``QThread.run()``. The UI
thread interacts with the worker only through Qt signals/slots; all calls
that cross into the asyncio world are routed through ``call_soon_threadsafe``
so the loop never sees a foreign-thread access.

The worker is restartable: stop it, change host/port, start it again.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

from seercontrol.core.stellarium.server import StellariumServer

logger = logging.getLogger(__name__)


class StellariumWorker(QThread):
    """Runs the Stellarium TCP server on a background QThread.

    Signals:
        target_received(ra_hours, dec_degrees):
            Stellarium asked the telescope to slew to these J2000 coords.
        client_count_changed(n):
            Number of Stellarium clients currently connected.
        server_started():
            Listening socket is open.
        server_stopped():
            Listening socket is closed.
        error_occurred(message):
            The asyncio server raised — typically port-in-use on bind.
    """

    target_received      = pyqtSignal(float, float)
    client_count_changed = pyqtSignal(int)
    server_started       = pyqtSignal()
    server_stopped       = pyqtSignal()
    error_occurred       = pyqtSignal(str)

    def __init__(self, host: str = "127.0.0.1", port: int = 10001) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Optional[StellariumServer] = None
        self._stop_event: Optional[asyncio.Event] = None

    # ------------------------------------------------------------------ #
    # Public, thread-safe API (callable from UI thread)                    #
    # ------------------------------------------------------------------ #

    def configure(self, host: str, port: int) -> None:
        """Change bind address. Takes effect on the next start; restart if running."""
        self._host = host
        self._port = port

    @pyqtSlot(float, float, bool)
    def update_mount_position(
        self, ra_hours: float, dec_degrees: float, slewing: bool = False
    ) -> None:
        """Forward the latest mount pointing to the asyncio server.

        Safe to call from any thread. If the server isn't running, this is a
        no-op so callers don't have to gate the signal connection.
        """
        loop, server = self._loop, self._server
        if loop is None or server is None:
            return
        loop.call_soon_threadsafe(server.set_position, ra_hours, dec_degrees, slewing)

    def stop(self) -> None:
        """Request a clean shutdown. Returns immediately."""
        loop, evt = self._loop, self._stop_event
        if loop is None or evt is None:
            return
        loop.call_soon_threadsafe(evt.set)

    # ------------------------------------------------------------------ #
    # QThread.run — owns the asyncio loop                                  #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as exc:
            logger.exception("Stellarium worker loop crashed: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None
            self._stop_event = None
            self._server = None

    async def _serve(self) -> None:
        def on_goto(ra: float, dec: float) -> None:
            self.target_received.emit(ra, dec)

        def on_count(n: int) -> None:
            self.client_count_changed.emit(n)

        self._server = StellariumServer(
            host=self._host,
            port=self._port,
            on_goto=on_goto,
            on_client_count=on_count,
        )
        try:
            await self._server.start()
        except OSError as exc:
            self.error_occurred.emit(f"bind {self._host}:{self._port} failed — {exc}")
            return

        self.server_started.emit()
        try:
            await self._stop_event.wait()  # type: ignore[union-attr]
        finally:
            await self._server.stop()
            self.server_stopped.emit()
