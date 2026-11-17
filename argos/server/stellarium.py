"""The Stellarium bridge (API 2, row A19): Stellarium's Telescope Control over TCP.

Qt-free port of ``argos/workers/stellarium_worker.py:24-130`` (the QThread
that owned an asyncio loop running :class:`argos.core.stellarium.server.
StellariumServer`) and of ``DeviceSession.start_stellarium /
stop_stellarium`` (``argos/core/session/device_session.py:783-816``). The
protocol server itself is the core module, unchanged.

The bridge runs on its own thread with its own asyncio loop, as the Qt
worker did, so a Stellarium client can never hold the server's HTTP loop.
Every crossing into that loop goes through ``call_soon_threadsafe``.

Fixed on the way (02 H14): a bind error is part of the state (the Qt card
never showed it), the host is reported, the port is written to the config
when the bridge starts (the hub does that), and the last GoTo carries its
outcome and time instead of a label that never reverted.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

from argos.core.stellarium.server import StellariumServer

logger = logging.getLogger(__name__)

#: How long ``start`` waits for the listening socket (or the bind error).
START_WAIT_S = 3.0
#: How long ``stop`` waits for the loop thread (the Qt card waited 3 s).
STOP_WAIT_S = 3.0


class StellariumBridge:
    """One Stellarium server at a time, restartable (stop, change port, start).

    *on_goto(ra_hours, dec_deg)* is called on the bridge's loop thread for
    every valid GoTo; it must not block (the hub hands it to a thread).
    *on_change()* is called whenever :meth:`snapshot` changes (start, stop,
    a client connects or leaves, an error).
    """

    def __init__(
        self,
        on_goto: Callable[[float, float], None],
        on_change: Callable[[], None],
    ) -> None:
        self._on_goto = on_goto
        self._on_change = on_change
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: StellariumServer | None = None
        self._stop_event: asyncio.Event | None = None
        self._running = False
        self._host: str | None = None
        self._port: int | None = None
        self._clients = 0
        self._error: str | None = None

    # -- state -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "host": self._host,
                "port": self._port,
                "clients": self._clients,
                "error": self._error,
            }

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def _changed(self) -> None:
        try:
            self._on_change()
        except Exception:  # a listener must never break the bridge
            logger.exception("Stellarium state listener failed")

    # -- lifecycle ---------------------------------------------------------

    def start(self, host: str, port: int) -> str | None:
        """Start listening on *host*:*port*; returns the bind error, or None.

        A running bridge is stopped first (``device_session.py:784-785``).
        Blocks until the socket is open or refused (≤ :data:`START_WAIT_S`).
        """
        self.stop(announce=False)
        opened = threading.Event()
        outcome: dict[str, str | None] = {"error": None}
        with self._lock:
            self._host, self._port = host, int(port)
            self._clients = 0
            self._error = None
        thread = threading.Thread(
            target=self._run,
            args=(host, int(port), opened, outcome),
            name="argos-stellarium",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        thread.start()
        if not opened.wait(START_WAIT_S):
            outcome["error"] = f"bind {host}:{port} timed out"
        error = outcome["error"]
        with self._lock:
            self._error = error
            self._running = error is None
        if error is not None:
            self.stop(announce=False)
            with self._lock:
                self._error = error  # stop() keeps it: the card shows why
        self._changed()
        return error

    def stop(self, announce: bool = True) -> bool:
        """Close the server and its clients; returns True if one was running."""
        with self._lock:
            thread, loop, event = self._thread, self._loop, self._stop_event
            was = self._running
            self._thread = None
            self._running = False
            self._clients = 0
            if was:
                self._error = None
        if loop is not None and event is not None:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass  # loop already closed
        if thread is not None and thread is not threading.current_thread():
            thread.join(STOP_WAIT_S)
        if announce and was:
            self._changed()
        return was

    def set_position(self, ra_hours: float, dec_deg: float, slewing: bool) -> None:
        """The mount's pointing, pushed to Stellarium's reticle (any thread, cheap)."""
        with self._lock:
            loop, server = self._loop, self._server
        if loop is None or server is None:
            return
        try:
            loop.call_soon_threadsafe(server.set_position, ra_hours, dec_deg, slewing)
        except RuntimeError:
            pass

    # -- loop thread (stellarium_worker.py:88-130) ---------------------------

    def _run(
        self, host: str, port: int, opened: threading.Event, outcome: dict[str, str | None]
    ) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._serve(loop, host, port, opened, outcome))
        except Exception as exc:  # stellarium_worker.py:94-96
            logger.exception("Stellarium bridge loop crashed: %s", exc)
            outcome["error"] = outcome["error"] or str(exc)
            opened.set()
            with self._lock:
                crashed = self._running
                self._running = False
                self._error = str(exc)
            if crashed:
                self._changed()
        finally:
            with self._lock:
                self._loop = self._server = self._stop_event = None
            try:
                loop.close()
            except Exception:
                pass

    async def _serve(
        self,
        loop: asyncio.AbstractEventLoop,
        host: str,
        port: int,
        opened: threading.Event,
        outcome: dict[str, str | None],
    ) -> None:
        stop_event = asyncio.Event()
        server = StellariumServer(
            host=host,
            port=port,
            on_goto=self._on_goto,
            on_client_count=self._count,
        )
        try:
            await server.start()
        except OSError as exc:  # stellarium_worker.py:119-123
            outcome["error"] = f"bind {host}:{port} failed — {exc.strerror or exc}"
            opened.set()
            return
        with self._lock:
            self._loop, self._server, self._stop_event = loop, server, stop_event
            self._running = True
        opened.set()
        try:
            await stop_event.wait()
        finally:
            await server.stop()

    def _count(self, n: int) -> None:
        with self._lock:
            changed = n != self._clients
            self._clients = n
        if changed:
            self._changed()
