"""Native JSON-RPC 2.0 TCP client for the Seestar S30 Pro.

The Seestar exposes two separate APIs:
  - ASCOM Alpaca HTTP  → standard telescope control (GoTo, tracking, position…)
  - Native JSON-RPC TCP (port 4700) → features not in Alpaca, notably
    ``scope_speed_move`` for continuous manual jogging.

Protocol details (from seestar_alp / smart-underworld):
  - Raw TCP socket, port 4700
  - JSON-RPC 2.0, messages delimited by CRLF (\\r\\n)
  - Direction angles use compass convention: 0=North, 90=East, 180=South, 270=West
  - ``scope_speed_move`` starts movement for ``dur_sec`` seconds then auto-stops
  - ``iscope_stop_view`` stops any ongoing movement immediately

Usage::

    client = SeestarNativeClient("192.168.1.42")
    client.connect()
    client.move(angle=0, speed=3000, dur_sec=2)   # move North for 2s
    client.stop()
    client.disconnect()
"""

from __future__ import annotations

import json
import logging
import socket
import threading

logger = logging.getLogger(__name__)

# Compass angles for the four cardinal directions.
ANGLE_NORTH = 0
ANGLE_EAST  = 90
ANGLE_SOUTH = 180
ANGLE_WEST  = 270

# Speed presets based on seestar_alp documentation (speed=4000 = default normal move).
# Do not exceed 10000 until motor limits are confirmed.
SPEED_SLOW   = 1000
SPEED_NORMAL = 4000
SPEED_FAST   = 8000

NATIVE_PORT = 4700


class SeestarNativeError(Exception):
    """Raised when a native client operation fails."""


class SeestarNativeClient:
    """Direct TCP JSON-RPC client to the Seestar native API.

    Thread-safe: ``move()`` and ``stop()`` can be called from any thread.

    Args:
        host: IP address of the Seestar device.
        port: TCP port (default 4700).
    """

    def __init__(self, host: str, port: int = NATIVE_PORT) -> None:
        self._host = host
        self._port = port
        self._socket: socket.socket | None = None
        self._cmdid = 10000
        self._lock = threading.Lock()
        self._connected = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the TCP connection to the Seestar native API.

        Raises:
            SeestarNativeError: If the connection cannot be established.
        """
        logger.debug("Native: opening TCP socket to %s:%d…", self._host, self._port)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((self._host, self._port))
            s.settimeout(None)
            self._socket = s
            self._connected = True
            logger.info("Native: connected to %s:%d", self._host, self._port)
        except OSError as exc:
            logger.error("Native: connection failed to %s:%d — %s: %s",
                         self._host, self._port, type(exc).__name__, exc)
            raise SeestarNativeError(f"Cannot connect to {self._host}:{self._port}: {exc}") from exc

    def disconnect(self) -> None:
        """Close the TCP connection."""
        with self._lock:
            if self._socket:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None
            self._connected = False
            logger.info("Seestar native client disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def move(self, angle: int, speed: int, dur_sec: int = 2) -> None:
        """Move the mount continuously in the given direction.

        The mount moves for ``dur_sec`` seconds then stops automatically.
        Call again before the duration expires to extend the movement, or
        call ``stop()`` to abort immediately.

        Args:
            angle: Compass direction in degrees.
                   0=North, 90=East, 180=South, 270=West.
            speed: Movement speed. Typical range 500–8000.
            dur_sec: Duration the mount will move (seconds, default 2).

        Raises:
            SeestarNativeError: If the command cannot be sent.
        """
        logger.debug("Native move: angle=%d speed=%d dur=%ds  socket=%s connected=%s",
                     angle, speed, dur_sec,
                     "ok" if self._socket else "NONE", self._connected)
        self._send("scope_speed_move", {
            "speed": speed,
            "angle": angle,
            "dur_sec": dur_sec,
        })
        logger.debug("scope_speed_move sent OK")

    def stop(self) -> None:
        """Stop any ongoing movement immediately.

        Raises:
            SeestarNativeError: If the command cannot be sent.
        """
        logger.debug("Native stop: socket=%s connected=%s",
                     "ok" if self._socket else "NONE", self._connected)
        self._send("iscope_stop_view", {})
        logger.debug("iscope_stop_view sent OK")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _send(self, method: str, params: dict | list) -> None:
        with self._lock:
            if not self._socket:
                # Socket is gone — try once to reconnect (Seestar may close idle connections)
                logger.warning(
                    "Native: socket is None (was connected=%s) — attempting reconnect for %s",
                    self._connected, method,
                )
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(5)
                    s.connect((self._host, self._port))
                    s.settimeout(None)
                    self._socket = s
                    self._connected = True
                    logger.info("Native: reconnected to %s:%d", self._host, self._port)
                except OSError as exc:
                    logger.error("Native: reconnect failed — %s: %s", type(exc).__name__, exc)
                    raise SeestarNativeError(f"Not connected and reconnect failed: {exc}") from exc

            payload = json.dumps({
                "method": method,
                "params": params,
                "id": self._cmdid,
            }) + "\r\n"
            self._cmdid += 1
            logger.debug("Native send [%d]: %s %s", self._cmdid - 1, method, params)
            try:
                self._socket.sendall(payload.encode("utf-8"))
            except OSError as exc:
                logger.error(
                    "Native: sendall failed — %s: %s  (socket reset)",
                    type(exc).__name__, exc,
                )
                self._connected = False
                self._socket = None
                raise SeestarNativeError(f"Send failed: {exc}") from exc
