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

Architecture — three background threads:
  - ``seestar-reader``    : continuously drains socket into response_dict
  - ``seestar-heartbeat`` : sends scope_get_equ_coord every 10s (keeps TCP alive)
  - Caller thread         : sends commands and polls response_dict (up to 3s)

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
SPEED_SLOW   = 1000
SPEED_NORMAL = 4000
SPEED_FAST   = 8000

NATIVE_PORT    = 4700
UDP_INTRO_PORT = 4720  # Port for the UDP scan_iscope handshake (guest mode unlock)

# Firmware version thresholds for verify injection (from seestar_alp source).
_VERIFY_MIN = 2582  # First firmware that requires verify in params
_VERIFY_MAX = 2706  # First firmware where verify in dict params is rejected (SSL auth)

_HEARTBEAT_INTERVAL = 10.0   # seconds between scope_get_equ_coord pings
_RESPONSE_TIMEOUT   = 3.0    # seconds to wait for a command response
_RESPONSE_POLL      = 0.05   # polling interval when waiting for response


class SeestarNativeError(Exception):
    """Raised when a native client operation fails."""


class SeestarNativeClient:
    """Direct TCP JSON-RPC client to the Seestar native API.

    Thread-safe: ``move()`` and ``stop()`` can be called from any thread.

    Internally maintains:
    - A reader thread that continuously drains socket responses into a dict.
    - A heartbeat thread that pings the device every 10s to keep TCP alive.

    Args:
        host: IP address of the Seestar device.
        port: TCP port (default 4700).
    """

    def __init__(self, host: str, port: int = NATIVE_PORT) -> None:
        self._host = host
        self._port = port
        self._socket: socket.socket | None = None
        self._cmdid = 10000
        self._lock = threading.Lock()          # protects socket + cmdid
        self._connected = False
        self._firmware_ver_int: int = 0

        # Response dict — filled by the reader thread, consumed by _send().
        self._response_dict: dict[int, dict] = {}
        self._response_lock = threading.Lock()

        # Background thread lifecycle.
        self._stop_event = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the TCP connection and start background threads.

        Sends a UDP scan_iscope handshake on port 4720 first — the Seestar
        requires this to release guest-mode lock before accepting TCP control.

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

        # Start background threads.
        self._stop_event.clear()
        self._response_dict.clear()

        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="seestar-reader", daemon=True,
        )
        self._reader_thread.start()

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="seestar-heartbeat", daemon=True,
        )
        self._heartbeat_thread.start()

        # Read firmware version (reader thread handles responses now).
        self._detect_firmware()

        # Claim master-CLI control — without this the Seestar is in observer mode:
        # it sends events but ignores all control commands (scope_speed_move etc.).
        self._claim_master_cli()

    def disconnect(self) -> None:
        """Close the TCP connection and stop background threads."""
        self._stop_event.set()

        with self._lock:
            if self._socket:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None
            self._connected = False
            self._firmware_ver_int = 0

        # Join background threads.
        for t in (self._reader_thread, self._heartbeat_thread):
            if t and t.is_alive():
                t.join(timeout=2.0)
        self._reader_thread = None
        self._heartbeat_thread = None

        logger.info("Native: disconnected from %s:%d", self._host, self._port)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def firmware_ver_int(self) -> int:
        return self._firmware_ver_int

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def move(self, angle: int, speed: int, dur_sec: int = 2) -> None:
        """Move the mount continuously in the given direction.

        Args:
            angle: Compass direction — 0=North, 90=East, 180=South, 270=West.
            speed: Movement speed. Typical range 500–8000.
            dur_sec: Duration the mount will move (seconds, default 2).

        Raises:
            SeestarNativeError: If the command cannot be sent.
        """
        params: dict = {"speed": speed, "angle": angle, "dur_sec": dur_sec}
        if self._needs_verify():
            params["verify"] = True
        self._send("scope_speed_move", params)

    def stop(self) -> None:
        """Stop any ongoing movement immediately.

        Raises:
            SeestarNativeError: If the command cannot be sent.
        """
        self._send("iscope_stop_view", {})

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _reader_loop(self) -> None:
        """Continuously read CRLF-delimited JSON messages from the socket.

        Stores responses keyed by their ``id`` field in ``_response_dict``.
        Unsolicited events (no id) are logged at INFO level.
        """
        buf = b""
        logger.info("Native reader thread started")
        while not self._stop_event.is_set():
            sock = self._socket
            if sock is None:
                time.sleep(0.1)
                continue
            try:
                # Use select to wait for data without modifying socket timeout
                # (avoids race with sendall in _send).
                import select
                ready, _, _ = select.select([sock], [], [], 1.0)
                if not ready:
                    continue
                chunk = sock.recv(65536)
                if not chunk:
                    logger.warning("Native: reader — server closed connection")
                    self._connected = False
                    break
                logger.info("Native: reader received %d bytes: %r", len(chunk), chunk[:200])
                buf += chunk
            except OSError as exc:
                if not self._stop_event.is_set():
                    logger.warning("Native: reader OSError: %s", exc)
                break

            # Parse all complete messages in the buffer.
            # Try both \r\n and \n as delimiters (some firmware variants).
            while True:
                # Find the earliest line ending.
                idx_crlf = buf.find(b"\r\n")
                idx_lf   = buf.find(b"\n")
                if idx_crlf == -1 and idx_lf == -1:
                    break
                if idx_crlf == -1:
                    idx = idx_lf
                    end = idx + 1
                elif idx_lf == -1 or idx_crlf <= idx_lf:
                    idx = idx_crlf
                    end = idx + 2
                else:
                    idx = idx_lf
                    end = idx + 1

                line = buf[:idx]
                buf  = buf[end:]
                if not line:
                    continue

                logger.info("Native: reader parsed line: %r", line[:300])
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("Native: reader malformed JSON (%s): %r", exc, line[:200])
                    continue

                msg_id = msg.get("id")
                if msg_id is None:
                    logger.info("Native: unsolicited event: method=%s  full=%s",
                                msg.get("method", "?"), msg)
                    continue

                code = msg.get("code", 0)
                method = msg.get("method", "?")
                if code != 0:
                    logger.warning("Native: device error id=%d method=%s code=%d full=%s",
                                   msg_id, method, code, msg)
                else:
                    logger.info("Native: response id=%d method=%s OK", msg_id, method)

                with self._response_lock:
                    self._response_dict[msg_id] = msg

        logger.info("Native reader thread exited")

    def _heartbeat_loop(self) -> None:
        """Send scope_get_equ_coord every _HEARTBEAT_INTERVAL seconds.

        Keeps the TCP connection alive — without this the Seestar closes
        idle connections after ~20 seconds.
        """
        logger.debug("Native heartbeat thread started (interval=%.0fs)", _HEARTBEAT_INTERVAL)
        while not self._stop_event.wait(_HEARTBEAT_INTERVAL):
            if self._connected and self._socket:
                try:
                    self._send_raw("scope_get_equ_coord", {})
                    logger.debug("Native: heartbeat sent")
                except OSError as exc:
                    logger.debug("Native: heartbeat failed: %s", exc)
        logger.debug("Native heartbeat thread exited")

    # ------------------------------------------------------------------
    # Internal — guest mode / master CLI
    # ------------------------------------------------------------------

    def _claim_master_cli(self) -> None:
        """Claim master CLI control so the Seestar accepts control commands.

        Without this the device stays in observer mode: it sends periodic
        events (PiStatus, EqModePA …) but silently ignores all commands like
        scope_speed_move.  seestar_alp calls this its "guest_mode_init".

        Only firmware > 2300 requires the claim.  Since our firmware detection
        often times out (device takes > 5s to respond to get_device_state),
        we always attempt the claim — it is a no-op on older firmware.
        """
        logger.info("Native: claiming master CLI control (guest_mode_init)…")
        try:
            self._send("set_setting", {"master_cli": True})
            logger.info("Native: master CLI claimed — device should now accept commands")
        except SeestarNativeError as exc:
            logger.warning("Native: master CLI claim failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Internal — firmware detection
    # ------------------------------------------------------------------

    def _needs_verify(self) -> bool:
        """Return True if firmware requires ``"verify": true`` in params."""
        v = self._firmware_ver_int
        if v == 0:
            return False  # unknown → assume modern device (≥ 2706), don't inject
        return _VERIFY_MIN < v < _VERIFY_MAX

    def _detect_firmware(self) -> None:
        """Query get_device_state to read firmware version integer.

        The reader thread handles the response asynchronously. We poll
        _response_dict for up to 5s. Non-fatal on timeout — stays at 0
        (unknown) → verify NOT injected (safe default for modern S30 Pro).
        """
        if not self._socket:
            return
        try:
            # seestar_alp sends get_device_state without a params key — omit it.
            # _send_raw returns the cmd_id atomically (read + increment under
            # _lock) so the heartbeat thread cannot steal our id.
            target_id = self._send_raw("get_device_state", None)
        except OSError as exc:
            logger.warning("Native: firmware query failed: %s", exc)
            return
        if target_id is None:
            logger.warning("Native: firmware query skipped — socket already closed")
            return

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self._response_lock:
                resp = self._response_dict.pop(target_id, None)
            if resp is not None:
                result = resp.get("result", {})
                device = result.get("device", {}) if isinstance(result, dict) else {}
                self._firmware_ver_int = int(device.get("firmware_ver_int", 0))
                logger.info(
                    "Native: firmware ver_int=%d  verify_needed=%s",
                    self._firmware_ver_int, self._needs_verify(),
                )
                return
            time.sleep(0.1)

        logger.warning(
            "Native: firmware detection timed out — assuming modern firmware, verify=False"
        )
        self._firmware_ver_int = 0

    # ------------------------------------------------------------------
    # Internal — UDP intro
    # ------------------------------------------------------------------

    def _send_udp_intro(self) -> None:
        """Send a UDP scan_iscope handshake to unlock Seestar guest mode."""
        message = json.dumps({"id": 1, "method": "scan_iscope", "params": ""}).encode()
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            sock.sendto(message, (self._host, UDP_INTRO_PORT))
            try:
                sock.recv(1024)
            except socket.timeout:
                pass
            logger.debug("Native: UDP intro sent to %s:%d", self._host, UDP_INTRO_PORT)
        except OSError as exc:
            logger.warning("Native: UDP intro failed (non-fatal): %s: %s",
                           type(exc).__name__, exc)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        time.sleep(0.2)

    # ------------------------------------------------------------------
    # Internal — reconnect + send
    # ------------------------------------------------------------------

    def _reconnect(self) -> None:
        """Re-open TCP socket. Not thread-safe — caller must hold _lock."""
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

    def _send_raw(self, method: str, params: dict | list | None) -> int | None:
        """Send without waiting for response (used by heartbeat + detect_firmware).

        Pass params=None to omit the params key entirely (required by some methods
        such as get_device_state — seestar_alp omits it and the firmware rejects
        an explicit empty dict for those methods).

        Returns:
            The command id that was actually sent on the wire, or ``None`` if
            the socket was not connected. Callers that need to correlate the
            response (e.g. _detect_firmware) must use this returned id rather
            than reading ``self._cmdid`` separately, which would race with the
            heartbeat thread.
        """
        with self._lock:
            if not self._socket:
                return None
            cmd_id = self._cmdid
            self._cmdid += 1
            msg: dict = {"method": method, "id": cmd_id}
            if params is not None:
                msg["params"] = params
            payload = json.dumps(msg) + "\r\n"
            self._socket.sendall(payload.encode("utf-8"))
            return cmd_id

    def _send(self, method: str, params: dict | list) -> None:
        """Send a command and wait up to _RESPONSE_TIMEOUT for a response.

        Handles BrokenPipe by reconnecting and retrying once.
        Response is read by the reader thread from _response_dict.
        """
        with self._lock:
            if not self._socket:
                self._reconnect()

            cmd_id = self._cmdid
            self._cmdid += 1
            payload = json.dumps({"method": method, "params": params, "id": cmd_id}) + "\r\n"
            logger.info("Native → [%d] %s  params=%s  firmware=%d",
                        cmd_id, method, params, self._firmware_ver_int)
            try:
                self._socket.sendall(payload.encode("utf-8"))
            except OSError as exc:
                logger.warning(
                    "Native: sendall failed (%s: %s) — reconnecting and retrying %s",
                    type(exc).__name__, exc, method,
                )
                self._connected = False
                self._socket = None
                self._reconnect()
                cmd_id = self._cmdid
                self._cmdid += 1
                payload = json.dumps({
                    "method": method, "params": params, "id": cmd_id,
                }) + "\r\n"
                try:
                    self._socket.sendall(payload.encode("utf-8"))
                    logger.info("Native: retry [%d] sent for %s", cmd_id, method)
                except OSError as exc2:
                    self._connected = False
                    self._socket = None
                    logger.error("Native: retry also failed: %s: %s",
                                 type(exc2).__name__, exc2)
                    raise SeestarNativeError(f"Send failed after reconnect: {exc2}") from exc2

        # Wait for response outside the lock (reader thread needs socket access).
        deadline = time.monotonic() + _RESPONSE_TIMEOUT
        while time.monotonic() < deadline:
            with self._response_lock:
                resp = self._response_dict.pop(cmd_id, None)
            if resp is not None:
                return  # success/error already logged by reader thread
            time.sleep(_RESPONSE_POLL)

        logger.warning("Native: %s [%d] — no response within %.1fs",
                       method, cmd_id, _RESPONSE_TIMEOUT)
