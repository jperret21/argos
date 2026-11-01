"""Mount routes against the simulator (fast slews), plus 4 Hz telemetry."""

from __future__ import annotations

import time

import pytest

from argos.server.settings import SimOptions
from tests.server.conftest import AUTH, TOKEN, receive_json, wait_for


def _mount(client) -> dict:
    return client.get("/api/status", headers=AUTH).json()["mount"]


def _post(client, route: str, body: dict | None = None):
    return client.post(f"/api/mount/{route}", json=body, headers=AUTH)


def test_mount_requires_connection(client):
    response = _post(client, "goto", {"ra_hours": 1.0, "dec_deg": 2.0})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_connected"


def test_starts_parked_and_refuses_goto_and_tracking(connected):
    mount = _mount(connected)
    assert mount["state"] == "parked" and mount["tracking"] is False
    assert mount["dec_deg"] == pytest.approx(90.0)
    assert mount["target"] is None and mount["pier_side"] is None
    for route, body in (
        ("goto", {"ra_hours": 5.0, "dec_deg": 20.0}),
        ("tracking", {"enabled": True}),
    ):
        response = _post(connected, route, body)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "parked"


def test_unpark_then_tracking_toggles(connected):
    assert _post(connected, "unpark").json()["state"] == "idle"
    on = _post(connected, "tracking", {"enabled": True}).json()
    assert on["state"] == "tracking" and on["tracking"] is True
    off = _post(connected, "tracking", {"enabled": False}).json()
    assert off["state"] == "idle" and off["tracking"] is False


def test_goto_slews_then_tracks_on_target(connected):
    _post(connected, "unpark")
    started = _post(connected, "goto", {"ra_hours": 5.5, "dec_deg": 22.0}).json()
    assert started["state"] == "slewing"
    assert started["tracking"] is True
    assert started["target"] == {"ra_hours": 5.5, "dec_deg": 22.0}

    mount = wait_for(lambda: (m := _mount(connected))["state"] == "tracking" and m)
    assert mount["ra_hours"] == pytest.approx(5.5, abs=1e-9)
    assert mount["dec_deg"] == pytest.approx(22.0, abs=1e-9)
    assert -90 <= mount["alt_deg"] <= 90 and 0 <= mount["az_deg"] < 360
    assert mount["pier_side"] in ("east", "west")
    assert mount["target"] == {"ra_hours": 5.5, "dec_deg": 22.0}


def test_ra_24_is_folded_to_zero(connected):
    _post(connected, "unpark")
    assert _post(connected, "goto", {"ra_hours": 24.0, "dec_deg": 0.0}).json()["target"] == {
        "ra_hours": 0.0,
        "dec_deg": 0.0,
    }


def test_stop_aborts_a_slew_and_keeps_tracking(make_client):
    client = make_client(sim=SimOptions(width=64, height=48, slew_rate_deg_s=2.0))
    client.post("/api/connection", json={"mode": "simulator"}, headers=AUTH)
    _post(client, "unpark")
    _post(client, "goto", {"ra_hours": 0.0, "dec_deg": -30.0})  # 120° of Dec at 2°/s
    time.sleep(0.2)
    stopped = _post(client, "stop").json()
    assert stopped["state"] == "tracking"  # AbortSlew leaves tracking on
    assert stopped["dec_deg"] > 80.0  # stopped well short of the target
    assert stopped["target"] == {"ra_hours": 0.0, "dec_deg": -30.0}  # intent survives a stop
    time.sleep(0.3)
    assert _mount(client)["dec_deg"] == pytest.approx(stopped["dec_deg"], abs=1e-9)


def test_park_slews_home_and_clears_target(connected):
    _post(connected, "unpark")
    _post(connected, "goto", {"ra_hours": 3.0, "dec_deg": 10.0})
    wait_for(lambda: _mount(connected)["state"] == "tracking")
    parking = _post(connected, "park").json()
    assert parking["state"] == "slewing"
    assert parking["tracking"] is False and parking["target"] is None
    mount = wait_for(lambda: (m := _mount(connected))["state"] == "parked" and m)
    assert mount["dec_deg"] == pytest.approx(90.0)
    assert mount["tracking"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"ra_hours": 24.01, "dec_deg": 0},
        {"ra_hours": -0.1, "dec_deg": 0},
        {"ra_hours": 1, "dec_deg": 90.5},
        {"ra_hours": "1", "dec_deg": 0},
        {"ra_hours": 1},
    ],
)
def test_goto_validation(connected, body):
    response = _post(connected, "goto", body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize("body", [{"enabled": "true"}, {"enabled": 1}, {}])
def test_tracking_validation(connected, body):
    response = _post(connected, "tracking", body)
    assert response.status_code == 400


def test_telemetry_is_at_most_4_hz(connected):
    with connected.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)  # status
        t0 = time.monotonic()
        stamps = []
        while time.monotonic() - t0 < 1.3:
            message = receive_json(events, timeout=2.0)
            if message["type"] == "mount":
                stamps.append(time.monotonic())
    assert 3 <= len(stamps) <= 6
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    # The receiver may batch two messages; the producer's period is 0.25 s.
    assert sum(gaps) / len(gaps) >= 0.2


def test_slew_end_is_announced_by_status(connected):
    _post(connected, "unpark")
    with connected.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        _post(connected, "goto", {"ra_hours": 12.0, "dec_deg": 0.0})
        states = []
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "tracking" not in states:
            message = receive_json(events)
            if message["type"] == "status":
                states.append(message["mount"]["state"])
    assert "slewing" in states and states[-1] == "tracking"


def test_command_in_flight_at_disconnect_writes_nothing(connected, monkeypatch):
    """An Alpaca GoTo blocks; a disconnect meanwhile must win, target included."""
    import threading

    from argos.server.devices.sim_mount import SimMount

    _post(connected, "unpark")
    hub = connected.app.state.hub
    original = SimMount.goto
    entered = threading.Event()

    def slow_goto(self, ra, dec):
        entered.set()
        time.sleep(0.5)
        original(self, ra, dec)

    monkeypatch.setattr(SimMount, "goto", slow_goto)
    answers: list[int] = []
    worker = threading.Thread(
        target=lambda: answers.append(
            _post(connected, "goto", {"ra_hours": 5.5, "dec_deg": -5.0}).status_code
        )
    )
    worker.start()
    assert entered.wait(2)
    connected.delete("/api/connection", headers=AUTH)
    worker.join(5)
    assert answers == [409]
    status = connected.get("/api/status", headers=AUTH).json()
    assert status["connection"]["state"] == "disconnected"
    assert status["mount"]["state"] == "idle" and status["mount"]["target"] is None
    # Nothing carries over into the next session either.
    connected.post("/api/connection", json={"mode": "simulator"}, headers=AUTH)
    assert _mount(connected)["target"] is None
    assert hub._mount_state.target is None
