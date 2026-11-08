"""Stellarium bridge (API 2, row A19), on 127.0.0.1 only.

A test plays Stellarium's Telescope Control plugin: it connects over TCP,
sends a GoTo in the Stellarium Telescope Protocol and reads the position
packets the bridge streams back. The simulator mount answers the GoTo.
"""

from __future__ import annotations

import socket
import struct
import time

import pytest

from argos.core.stellarium.protocol import _radec_to_int, find_next_message
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until, wait_for


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _goto_packet(ra_hours: float, dec_deg: float) -> bytes:
    """MessageGoto of the Stellarium Telescope Protocol v1.0 (20 bytes)."""
    ra_int, dec_int = _radec_to_int(ra_hours, dec_deg)
    return struct.pack("<HHQIi", 20, 0, int(time.time() * 1e6), ra_int, dec_int)


def _state(client) -> dict:
    return client.get("/api/stellarium", headers=AUTH).json()


@pytest.fixture
def bridge(client):
    port = _free_port()
    response = client.post("/api/stellarium", json={"port": port}, headers=AUTH)
    assert response.status_code == 200, response.text
    yield client, port
    client.delete("/api/stellarium", headers=AUTH)


def test_start_reports_the_listening_bridge_and_saves_the_port(bridge):
    client, port = bridge
    state = _state(client)
    assert state == {
        "running": True,
        "host": "127.0.0.1",
        "port": port,
        "clients": 0,
        "error": None,
        "last_goto": None,
        "suggestions": None,  # wave 3 (A20): no GoTo yet, so no target-name suggestion
    }
    values = client.get("/api/config", headers=AUTH).json()["values"]
    assert values["stellarium.port"] == port
    messages = [e["message"] for e in client.get("/api/logs", headers=AUTH).json()["entries"]]
    assert f"Stellarium bridge listening on 127.0.0.1:{port}" in messages


def test_a_client_is_counted_and_a_goto_slews_the_mount(bridge):
    client, port = bridge
    client.post("/api/devices/mount/connect", json={"mode": "simulator"}, headers=AUTH)
    client.post("/api/mount/unpark", headers=AUTH)
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as stellarium:
            counted = receive_until(
                events, lambda m: m["type"] == "stellarium" and m["clients"] == 1
            )
            assert counted["running"] is True
            stellarium.sendall(_goto_packet(5.5, 22.0))
            done = receive_until(
                events, lambda m: m["type"] == "stellarium" and m["last_goto"] is not None
            )
            # The reticle follows the mount: position packets come back (1 Hz).
            stellarium.settimeout(3)
            data = stellarium.recv(64)
            assert find_next_message(data) == 24
        receive_until(events, lambda m: m["type"] == "stellarium" and m["clients"] == 0)
    goto = done["last_goto"]
    assert goto["outcome"] == "slewing" and goto["t"].endswith("Z")
    assert goto["ra_hours"] == pytest.approx(5.5, abs=1e-6)
    assert goto["dec_deg"] == pytest.approx(22.0, abs=1e-6)
    target = client.get("/api/status", headers=AUTH).json()["mount"]["target"]
    assert target["ra_hours"] == pytest.approx(5.5, abs=1e-6)


def test_a_goto_without_a_mount_says_so(bridge):
    client, port = bridge
    with socket.create_connection(("127.0.0.1", port), timeout=5) as stellarium:
        wait_for(lambda: _state(client)["clients"] == 1)
        stellarium.sendall(_goto_packet(1.0, 10.0))
        state = wait_for(lambda: (s := _state(client))["last_goto"] and s)
    assert state["last_goto"]["outcome"] == "mount not connected"
    warnings = client.get("/api/logs?level=warning", headers=AUTH).json()["entries"]
    assert [e["message"] for e in warnings] == ["Stellarium GoTo not sent: mount not connected"]
    assert {e["topic"] for e in warnings} == {"planetarium"}
    # A new bridge session starts without the previous session's GoTo.
    restarted = client.post("/api/stellarium", json={"port": port}, headers=AUTH).json()
    assert restarted["running"] is True and restarted["last_goto"] is None


def test_a_port_in_use_is_reported_in_the_state(client):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        port = taken.getsockname()[1]
        response = client.post("/api/stellarium", json={"port": port}, headers=AUTH)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "bind_failed"
    state = _state(client)
    assert state["running"] is False
    assert state["error"].startswith(f"bind 127.0.0.1:{port} failed")
    errors = client.get("/api/logs?level=error", headers=AUTH).json()["entries"]
    assert errors[-1]["message"].startswith("Stellarium: bind")


def test_stop_closes_clients_and_is_idempotent(bridge):
    client, port = bridge
    with socket.create_connection(("127.0.0.1", port), timeout=5) as stellarium:
        wait_for(lambda: _state(client)["clients"] == 1)
        state = client.delete("/api/stellarium", headers=AUTH).json()
        assert state["running"] is False and state["clients"] == 0
        stellarium.settimeout(3)
        assert stellarium.recv(64) == b""  # the bridge closed the connection
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    assert client.delete("/api/stellarium", headers=AUTH).status_code == 200


def test_body_is_validated(client):
    for body in ({"port": 80}, {"port": "10001"}, {"host": ""}, {"other": 1}):
        response = client.post("/api/stellarium", json=body, headers=AUTH)
        assert response.status_code == 400, body
    assert _state(client)["running"] is False


def test_server_shutdown_stops_the_bridge(make_client):
    client = make_client()
    port = _free_port()
    client.post("/api/stellarium", json={"port": port}, headers=AUTH)
    client.__exit__(None, None, None)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
