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
  - UDP scan_iscope on port 4720 must be sent before TCP connect (guest mode unlock)
  - ``"verify": true`` is required in params for firmware 2582–2705 only;
    firmware ≥ 2706 is SSL-authenticated and rejects verify in dict params.

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
import time

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

NATIVE_PORT    = 4700
UDP_INTRO_PORT = 4720  # Port for the UDP scan_iscope handshake (guest mode unlock)

# Firmware version thresholds for verify injection (from seestar_alp source).
_VERIFY_MIN = 2582  # First firmware that requires verify in params
_VERIFY_MAX = 2706  # First firmware where verify in dict params is rejected (SSL auth)


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
        self._firmware_ver_int: int = 0  # 0 = unknown until connect

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the TCP connection to the Seestar native API.

        Sends a UDP scan_iscope handshake on port 4720 first — the Seestar
        requires this to release guest-mode lock before accepting TCP control.
        Then queries the firmware version to calibrate verify injection.

        Raises:
            SeestarNativeError: If the connection cannot be established.
        """
        self._send_udp_intro()
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

        # Read firmware version so we know whether to inject "verify" in params.
        self._detect_firmware()

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
            self._firmware_ver_int = 0
            logger.info("Seestar native client disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def firmware_ver_int(self) -> int:
        """Firmware version integer read at connect time (0 if unknown)."""
        return self._firmware_ver_int

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
        params: dict = {
            "speed": speed,
            "angle": angle,
            "dur_sec": dur_sec,
        }
        if self._needs_verify():
            params["verify"] = True
        self._send("scope_speed_move", params)
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
    # Internal — firmware detection
    # ------------------------------------------------------------------

    def _needs_verify(self) -> bool:
        """Return True if this firmware version requires ``"verify": true`` in params.

        - Unknown firmware (0): inject as a safe default.
        - Firmware 2582–2705: inject required.
        - Firmware < 2582: not required.
        - Firmware ≥ 2706: SSL-authenticated; verify in dict params is **rejected**.
        """
        v = self._firmware_ver_int
        return v == 0 or (_VERIFY_MIN < v < _VERIFY_MAX)

    def _detect_firmware(self) -> None:
        """Query get_device_state to read firmware version integer.

        Sets ``self._firmware_ver_int``. Non-fatal: on any error the version
        stays at 0 (unknown), which causes verify to be injected by default.
        """
        if not self._socket:
            return
        try:
            payload = json.dumps({
                "method": "get_device_state",
                "params": {},
                "id": self._cmdid,
            }) + "\r\n"
            self._cmdid += 1
            self._socket.sendall(payload.encode("utf-8"))

            # Read the response (CRLF-delimited) with a short timeout.
            self._socket.settimeout(3.0)
            try:
                buf = b""
                while b"\r\n" not in buf:
                    chunk = self._socket.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                if b"\r\n" in buf:
                    line = buf.split(b"\r\n")[0]
                    data = json.loads(line)
                    result = data.get("result", {})
                    device = result.get("device", {}) if isinstance(result, dict) else {}
                    self._firmware_ver_int = int(device.get("firmware_ver_int", 0))
                    logger.info(
                        "Native: firmware ver_int=%d  verify_needed=%s",
                        self._firmware_ver_int, self._needs_verify(),
                    )
            except (socket.timeout, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                logger.warning("Native: could not parse firmware response: %s", exc)
                self._firmware_ver_int = 0
            finally:
                self._socket.settimeout(None)

        except OSError as exc:
            logger.warning("Native: firmware query failed: %s", exc)
            self._firmware_ver_int = 0

    # ------------------------------------------------------------------
    # Internal — UDP intro
    # ------------------------------------------------------------------

    def _send_udp_intro(self) -> None:
        """Send a UDP scan_iscope handshake to unlock Seestar guest mode.

        The Seestar will refuse TCP control from a new client unless it has
        first seen this UDP message on port 4720 (documented by seestar_alp).
        """
        message = json.dumps({"id": 1, "method": "scan_iscope", "params": ""}).encode()
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            sock.sendto(message, (self._host, UDP_INTRO_PORT))
            try:
                sock.recv(1024)  # drain response (non-critical)
            except socket.timeout:
                pass
            logger.debug("Native: UDP intro sent to %s:%d", self._host, UDP_INTRO_PORT)
        except OSError as exc:
            logger.warning("Native: UDP intro failed (non-fatal) — %s: %s", type(exc).__name__, exc)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        time.sleep(0.2)  # brief pause to let the Seestar process the intro

    # ------------------------------------------------------------------
    # Internal — reconnect + send
    # ------------------------------------------------------------------

    def _reconnect(self) -> None:
        """Re-open TCP socket (called when socket is None or broken). Not thread-safe — caller holds lock."""
        logger.warning("Native: reconnecting to %s:%d…", self._host, self._port)
        self._send_udp_intro()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((self._host, self._port))
            s.settimeout(None)
            self._socket = s
            self._connected = True
            logger.info("Native: reconnected to %s:%d", self._host, self._port)
        except OSError as exc:
            self._socket = None
            self._connected = False
            logger.error("Native: reconnect failed — %s: %s", type(exc).__name__, exc)
            raise SeestarNativeError(f"Reconnect failed: {exc}") from exc

    def _send(self, method: str, params: dict | list) -> None:
        with self._lock:
            if not self._socket:
                # Seestar closes idle TCP connections — reconnect transparently
                self._reconnect()

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
                # Socket broke mid-send — reconnect and retry once
                logger.warning(
                    "Native: sendall failed (%s: %s) — reconnecting and retrying %s",
                    type(exc).__name__, exc, method,
                )
                self._connected = False
                self._socket = None
                self._reconnect()
                # Retry with a new command ID
                payload = json.dumps({
                    "method": method,
                    "params": params,
                    "id": self._cmdid,
                }) + "\r\n"
                self._cmdid += 1
                try:
                    self._socket.sendall(payload.encode("utf-8"))
                    logger.info("Native: retry succeeded for %s", method)
                except OSError as exc2:
                    self._connected = False
                    self._socket = None
                    logger.error("Native: retry also failed — %s: %s", type(exc2).__name__, exc2)
                    raise SeestarNativeError(f"Send failed after reconnect: {exc2}") from exc2
