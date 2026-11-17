"""Telescope profiles (row A17) and network reachability (row A18)."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from argos.core.hardware import active, catalog
from argos.server.network import NetworkMonitor
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until, wait_for

# -- profiles ------------------------------------------------------------------


def test_profiles_list_with_derived_values(client):
    body = client.get("/api/profiles", headers=AUTH).json()
    assert body["active"] == "s30pro" and body["locked"] is False and body["locked_reason"] is None
    assert [p["key"] for p in body["profiles"]] == ["s30pro", "s30", "s50"]
    for record in body["profiles"]:
        profile = catalog.get(record["key"])
        assert record["validated"] is profile.validated
        assert record["caveats"] == list(profile.caveats)
        assert record["focal_ratio"] == pytest.approx(profile.focal_ratio)
        assert record["arcsec_per_px"] == pytest.approx(profile.arcsec_per_full_px)
        assert record["fov_deg"] == pytest.approx(list(profile.fov_deg))
        assert record["sensor_px"] == [profile.sensor_width_px, profile.sensor_height_px]
        assert record["filter_names"] == list(profile.filter_names)
    s30pro = body["profiles"][0]
    # catalog.py:40-56: 30 mm, 160 mm, 2.9 µm → f/5.33, 3.74″/px (connection_page specs line).
    assert s30pro["focal_ratio"] == pytest.approx(160 / 30)
    assert round(s30pro["arcsec_per_px"], 2) == 3.74
    assert body["profiles"][1]["validated"] is False and body["profiles"][1]["caveats"]


def test_change_profile_when_idle(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        response = client.put("/api/profile", json={"key": "s50"}, headers=AUTH)
        seen: list[dict] = []
        receive_until(
            events, lambda m: m["type"] == "status" and m["profile"]["key"] == "s50", seen=seen
        )
    assert response.status_code == 200
    assert response.json()["active"] == "s50"
    assert active.profile().key == "s50"
    config = [m for m in seen if m["type"] == "config"]
    assert config and config[0]["changed"] == {"hardware.profile": "s50"}
    path = Path(client.get("/api/config", headers=AUTH).json()["path"])
    assert json.loads(path.read_text())["hardware"]["profile"] == "s50"
    logs = [m["message"] for m in client.get("/api/logs", headers=AUTH).json()["entries"]]
    assert any(m.startswith("Telescope profile: ZWO Seestar S50") for m in logs)


def test_profile_change_refused_while_a_device_is_connected(client):
    client.post("/api/devices/focuser/connect", json={"mode": "simulator"}, headers=AUTH)
    state = client.get("/api/profiles", headers=AUTH).json()
    assert state["locked"] is True and "Disconnect the equipment" in state["locked_reason"]
    response = client.put("/api/profile", json={"key": "s30"}, headers=AUTH)
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "busy",
        "message": "Disconnect the equipment before changing the telescope: it sets plate "
        "scale, sensor geometry and FITS metadata.",
    }
    assert active.profile().key == "s30pro"
    # Choosing the active one again is always accepted.
    assert client.put("/api/profile", json={"key": "s30pro"}, headers=AUTH).status_code == 200
    client.delete("/api/devices", headers=AUTH)
    assert client.put("/api/profile", json={"key": "s30"}, headers=AUTH).status_code == 200


def test_unknown_profile_is_invalid(client):
    response = client.put("/api/profile", json={"key": "s50pro"}, headers=AUTH)
    assert response.status_code == 400
    assert "s30pro, s30, s50" in response.json()["error"]["message"]
    assert client.put("/api/profile", json={}, headers=AUTH).status_code == 400


def test_the_configured_profile_is_active_at_start_up(make_client, tmp_path):
    folder = tmp_path / "configured"
    folder.mkdir()
    (folder / "config.json").write_text(
        json.dumps({"hardware": {"profile": "s30", "overrides": {"full_well_adu": 50000}}})
    )
    client = make_client(config_dir=folder)
    body = client.get("/api/profiles", headers=AUTH).json()
    assert body["active"] == "s30"
    s30 = body["profiles"][1]
    assert s30["full_well_adu"] == 50000 and s30["overrides"] == {"full_well_adu": 50000}
    status = client.get("/api/status", headers=AUTH).json()
    assert status["profile"] == {"key": "s30", "name": "ZWO Seestar S30", "validated": False}


# -- network -------------------------------------------------------------------


@pytest.fixture
def listener():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    yield sock.getsockname()[1]
    sock.close()


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_monitor_states_without_a_seestar_address():
    published: list[dict] = []
    probes: list = []
    monitor = NetworkMonitor(
        lambda: ("", 32323), published.append, probe=lambda *a: probes.append(a) or True
    )
    state = monitor.check()
    assert state["seestar"] is None and state["internet"] is None  # "not configured"
    assert state["host"] is None and state["t"].endswith("Z") and state["internet_t"] is None
    assert probes == [] and published == [state]  # nothing contacted


def test_internet_is_only_checked_on_demand():
    probes: list = []
    monitor = NetworkMonitor(
        lambda: ("192.168.1.42", 32323),
        probe=lambda host, port, timeout: probes.append((host, port, timeout)) or host != "1.1.1.1",
    )
    state = monitor.check()
    assert probes == [("192.168.1.42", 32323, 1.5)]  # Seestar only (Q-G13)
    assert state["seestar"] is True and state["internet"] is None
    state = monitor.check(internet=True)
    # network_monitor.py:37: Cloudflare first, then Google.
    assert [p[0] for p in probes[1:]] == ["192.168.1.42", "1.1.1.1", "8.8.8.8"]
    assert state["internet"] is True and state["internet_t"] is not None


def test_monitor_probes_periodically_and_wakes_on_change():
    address = ["192.168.1.42"]
    seen: list[str] = []
    monitor = NetworkMonitor(
        lambda: (address[0], 32323),
        interval_s=60,
        probe=lambda host, port, timeout: seen.append(host) or False,
    )
    monitor.start()
    try:
        wait_for(lambda: seen == ["192.168.1.42"])
        address[0] = "192.168.1.43"
        monitor.wake()  # long before the 60 s period
        wait_for(lambda: seen[-1:] == ["192.168.1.43"])
    finally:
        monitor.stop()


def test_network_routes_and_events_against_a_local_listener(make_client, listener):
    client = make_client(network_interval_s=60)
    initial = client.get("/api/network", headers=AUTH).json()
    assert initial["seestar"] is None and initial["internet"] is None
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)  # status
        assert receive_json(events)["type"] == "network"  # the current snapshot, at once
        client.patch(
            "/api/config", json={"alpaca.host": "127.0.0.1", "alpaca.port": listener}, headers=AUTH
        )
        up = receive_until(events, lambda m: m["type"] == "network" and m["seestar"] is True)
    assert (up["host"], up["port"]) == ("127.0.0.1", listener)
    client.patch("/api/config", json={"alpaca.port": _closed_port()}, headers=AUTH)
    wait_for(lambda: client.get("/api/network", headers=AUTH).json()["seestar"] is False)


def test_network_check_route_probes_the_internet_only_when_asked(client, listener):
    hub = client.app.state.hub
    hub.network._internet_targets = (("127.0.0.1", listener),)  # never the real resolvers
    state = client.post("/api/network/check", headers=AUTH).json()
    assert state["internet"] is None
    state = client.post("/api/network/check", json={"internet": True}, headers=AUTH).json()
    assert state["internet"] is True
    assert client.post("/api/network/check", json={"internet": 1}, headers=AUTH).status_code == 400


def test_a_slow_probe_never_blocks_the_routes(make_client):
    gate = threading.Event()
    client = make_client(network_interval_s=60)
    hub = client.app.state.hub
    hub.network._probe = lambda host, port, timeout: gate.wait(2)
    client.patch("/api/config", json={"alpaca.host": "192.0.2.1"}, headers=AUTH)
    try:
        for _ in range(5):
            assert client.get("/api/status", headers=AUTH).status_code == 200
    finally:
        gate.set()
