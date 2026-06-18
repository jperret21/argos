"""Tests for SeestarNativeClient using the seestar_alp simulator.

Run with:
    uv run python -m pytest tests/core/test_native_client.py -v

The seestar_alp simulator must be present at:
    ../seestar_alp-main/simulator/src/

These tests are automatically skipped if the simulator is not found.
"""

from __future__ import annotations

import json
import socket

import pytest

from argos.core.seestar.native_client import (
    ANGLE_EAST,
    ANGLE_NORTH,
    ANGLE_SOUTH,
    ANGLE_WEST,
    SPEED_NORMAL,
    SPEED_SLOW,
    SeestarNativeClient,
    SeestarNativeError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw_send(host: str, port: int, method: str, params: dict | list, cmd_id: int = 1) -> dict:
    """Send one JSON-RPC message and read the response. For assertion checks."""
    payload = json.dumps({"id": cmd_id, "method": method, "params": params}) + "\r\n"
    with socket.create_connection((host, port), timeout=5) as s:
        s.sendall(payload.encode("utf-8"))
        buf = b""
        s.settimeout(3.0)
        while b"\r\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    line = buf.split(b"\r\n")[0]
    return json.loads(line)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(seestar_simulator):
    """Connected SeestarNativeClient pointed at the simulator."""
    c = SeestarNativeClient(
        host=seestar_simulator["host"],
        port=seestar_simulator["tcp_port"],
    )
    c.connect()
    yield c
    c.disconnect()


# ---------------------------------------------------------------------------
# Tests — connection
# ---------------------------------------------------------------------------

class TestConnect:
    def test_connect_sets_connected(self, seestar_simulator):
        c = SeestarNativeClient(
            host=seestar_simulator["host"],
            port=seestar_simulator["tcp_port"],
        )
        assert not c.is_connected
        c.connect()
        assert c.is_connected
        c.disconnect()

    def test_disconnect_clears_connected(self, seestar_simulator):
        c = SeestarNativeClient(
            host=seestar_simulator["host"],
            port=seestar_simulator["tcp_port"],
        )
        c.connect()
        c.disconnect()
        assert not c.is_connected

    def test_connect_reads_firmware_version(self, client):
        # Simulator firmware_ver_int is 2470 — should be read correctly.
        assert client.firmware_ver_int == 2470

    def test_connect_bad_host_raises(self):
        c = SeestarNativeClient(host="192.0.2.1", port=14700)  # TEST-NET, unreachable
        c._socket = None  # ensure no socket
        with pytest.raises(SeestarNativeError):
            c.connect()


# ---------------------------------------------------------------------------
# Tests — scope_speed_move
# ---------------------------------------------------------------------------

class TestMove:
    def test_move_north(self, client):
        """move() with ANGLE_NORTH should not raise."""
        client.move(ANGLE_NORTH, SPEED_NORMAL, dur_sec=1)

    def test_move_south(self, client):
        client.move(ANGLE_SOUTH, SPEED_NORMAL, dur_sec=1)

    def test_move_east(self, client):
        client.move(ANGLE_EAST, SPEED_NORMAL, dur_sec=1)

    def test_move_west(self, client):
        client.move(ANGLE_WEST, SPEED_NORMAL, dur_sec=1)

    def test_move_slow_speed(self, client):
        client.move(ANGLE_NORTH, SPEED_SLOW, dur_sec=1)

    def test_move_simulator_responds_result_zero(self, seestar_simulator):
        """The simulator must return result=0 for scope_speed_move."""
        resp = _raw_send(
            seestar_simulator["host"],
            seestar_simulator["tcp_port"],
            "scope_speed_move",
            {"speed": 4000, "angle": 0, "dur_sec": 2},
        )
        assert resp.get("result") == 0 or resp.get("code") == 0

    @pytest.mark.parametrize("angle", [ANGLE_NORTH, ANGLE_EAST, ANGLE_SOUTH, ANGLE_WEST])
    def test_all_directions(self, client, angle):
        client.move(angle, SPEED_NORMAL, dur_sec=1)

    def test_move_extends_with_repeated_calls(self, client):
        """Calling move twice in succession should not raise (extend semantics)."""
        client.move(ANGLE_NORTH, SPEED_NORMAL, dur_sec=2)
        client.move(ANGLE_NORTH, SPEED_NORMAL, dur_sec=2)


# ---------------------------------------------------------------------------
# Tests — iscope_stop_view
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_after_move(self, client):
        client.move(ANGLE_NORTH, SPEED_NORMAL, dur_sec=5)
        client.stop()  # must not raise

    def test_stop_without_prior_move(self, client):
        client.stop()  # must not raise

    def test_stop_simulator_responds(self, seestar_simulator):
        resp = _raw_send(
            seestar_simulator["host"],
            seestar_simulator["tcp_port"],
            "iscope_stop_view",
            {},
        )
        assert resp.get("result") == 0 or resp.get("code") == 0


# ---------------------------------------------------------------------------
# Tests — reconnect on broken socket
# ---------------------------------------------------------------------------

class TestReconnect:
    def test_move_after_socket_closed(self, seestar_simulator):
        """Simulate a dropped connection: closing the socket should trigger
        auto-reconnect on the next move() call."""
        c = SeestarNativeClient(
            host=seestar_simulator["host"],
            port=seestar_simulator["tcp_port"],
        )
        c.connect()
        # Force-close the underlying socket to simulate an idle timeout drop.
        c._socket.close()
        c._socket = None
        # The next move should reconnect transparently.
        c.move(ANGLE_NORTH, SPEED_SLOW, dur_sec=1)
        assert c.is_connected
        c.disconnect()


# ---------------------------------------------------------------------------
# Tests — verify injection
# ---------------------------------------------------------------------------

class TestVerifyInjection:
    def test_firmware_2470_no_verify(self, client):
        """Simulator firmware 2470 < 2582 — verify should NOT be injected."""
        assert client.firmware_ver_int == 2470
        assert not client._needs_verify()

    def test_unknown_firmware_no_verify(self):
        """Unknown firmware (0) → assume modern S30 Pro (≥ 2706): do NOT inject verify."""
        c = SeestarNativeClient("127.0.0.1")
        assert c.firmware_ver_int == 0
        assert not c._needs_verify()

    @pytest.mark.parametrize("ver,expected", [
        (0,    False),  # unknown → assume modern, don't inject
        (2470, False),  # < 2582 → no inject
        (2600, True),   # 2582 < ver < 2706 → inject
        (2705, True),   # boundary − 1 → inject
        (2706, False),  # SSL-auth → don't inject (would be rejected)
        (2800, False),  # newer SSL-auth → don't inject
    ])
    def test_needs_verify_logic(self, ver, expected):
        c = SeestarNativeClient("127.0.0.1")
        c._firmware_ver_int = ver
        assert c._needs_verify() == expected
