"""asyncio TCP server speaking the Stellarium Telescope Protocol v1.0.

Listens on a TCP port (10001 by default). Stellarium's Telescope Control
plugin connects, sends MessageType 0 to request a slew, and expects the
telescope to keep streaming its current position so the on-screen reticle
follows the mount in real time.

This module is pure asyncio — it has no Qt dependency. The QThread bridge
in ``argos.workers.stellarium_worker`` wraps it so it can run inside
the Argos event loop and exchange data with the UI via Qt signals.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Callable, Optional

from argos.core.stellarium.protocol import (
    decode_goto,
    encode_position,
    find_next_message,
)

logger = logging.getLogger(__name__)

# Callback invoked when a Stellarium client sends a goto. (ra_hours, dec_deg)
GotoCallback = Callable[[float, float], None]
# Optional sync (non-awaitable) callback on client connect/disconnect.
ClientCountCallback = Callable[[int], None]


class StellariumServer:
    """Asynchronous Stellarium Telescope Protocol server.

    Typical lifecycle::

        srv = StellariumServer(port=10001, on_goto=lambda r, d: ...)
        await srv.start()
        srv.set_position(5.59, -5.39, slewing=False)   # push to clients
        # ... later ...
        await srv.stop()

    Args:
        host:               Interface to bind. ``127.0.0.1`` for loopback only
                            (default — safer), ``0.0.0.0`` to expose on LAN.
        port:               TCP port (10001 is Stellarium's convention).
        on_goto:            Called from the event loop on every valid goto.
                            Keep it cheap; offload long work to a queue.
        push_interval_s:    How often to broadcast current position to clients.
        on_client_count:    Optional callback that fires when a client connects
                            or disconnects. Receives the new total count.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 10001,
        on_goto: Optional[GotoCallback] = None,
        push_interval_s: float = 1.0,
        on_client_count: Optional[ClientCountCallback] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._on_goto = on_goto
        self._on_client_count = on_client_count
        self._push_interval = push_interval_s

        self._server: Optional[asyncio.AbstractServer] = None
        self._push_task: Optional[asyncio.Task] = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._latest: Optional[tuple[float, float, bool]] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Open the TCP socket and start the position-broadcast loop."""
        self._server = await asyncio.start_server(
            self._handle_client, host=self._host, port=self._port
        )
        self._push_task = asyncio.create_task(self._push_loop())
        sockets = ", ".join(str(s.getsockname()) for s in (self._server.sockets or ()))
        logger.info("Stellarium server listening on %s", sockets)

    async def stop(self) -> None:
        """Close the listening socket and disconnect all clients."""
        if self._push_task:
            self._push_task.cancel()
            # We are the canceller — await the task to let it finish unwinding.
            with contextlib.suppress(asyncio.CancelledError):
                await self._push_task
            self._push_task = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        for w in self._writers:
            try:
                w.close()
            except Exception:
                pass
        self._writers.clear()
        self._emit_client_count()
        logger.info("Stellarium server stopped")

    # ------------------------------------------------------------------ #
    # Thread-safe setters (called via loop.call_soon_threadsafe)           #
    # ------------------------------------------------------------------ #

    def set_position(self, ra_hours: float, dec_degrees: float, slewing: bool = False) -> None:
        """Latest mount position; broadcast at the next push tick."""
        self._latest = (ra_hours, dec_degrees, slewing)

    @property
    def client_count(self) -> int:
        return len(self._writers)

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.info("Stellarium client connected: %s", peer)
        self._writers.add(writer)
        self._emit_client_count()
        try:
            await self._read_loop(reader)
        except (ConnectionResetError, BrokenPipeError) as exc:
            logger.debug("Client dropped: %s (%s)", peer, exc)
        finally:
            self._writers.discard(writer)
            try:
                writer.close()
            except Exception:
                pass
            self._emit_client_count()
            logger.info("Stellarium client gone: %s", peer)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        buf = b""
        while True:
            chunk = await reader.read(1024)
            if not chunk:
                return
            buf += chunk
            while True:
                size = find_next_message(buf)
                if size == 0:
                    break
                frame, buf = buf[:size], buf[size:]
                msg = decode_goto(frame)
                if msg is None or self._on_goto is None:
                    continue
                logger.info("Goto from Stellarium: ra=%.4fh dec=%+.4f°",
                            msg.ra_hours, msg.dec_degrees)
                try:
                    self._on_goto(msg.ra_hours, msg.dec_degrees)
                except Exception as exc:
                    logger.exception("on_goto callback raised: %s", exc)

    async def _push_loop(self) -> None:
        # Cancellation propagates naturally; ``stop()`` cancels and awaits us.
        while True:
            await asyncio.sleep(self._push_interval)
            if not self._writers or self._latest is None:
                continue
            ra, dec, _slewing = self._latest
            pkt = encode_position(ra, dec, status=0)
            await self._broadcast(pkt)

    async def _broadcast(self, pkt: bytes) -> None:
        dead: list[asyncio.StreamWriter] = []
        # Snapshot the writer set — ``await drain()`` may yield to a coroutine
        # that mutates ``self._writers`` (e.g. a client disconnects).
        for w in tuple(self._writers):
            try:
                w.write(pkt)
                await w.drain()
            except OSError:
                # ConnectionResetError / BrokenPipeError both inherit from OSError
                dead.append(w)
        for w in dead:
            self._writers.discard(w)
            try:
                w.close()
            except Exception:
                pass
        if dead:
            self._emit_client_count()

    def _emit_client_count(self) -> None:
        if self._on_client_count is None:
            return
        try:
            self._on_client_count(len(self._writers))
        except Exception as exc:
            logger.exception("on_client_count callback raised: %s", exc)
