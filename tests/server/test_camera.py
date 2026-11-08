"""Camera routes over HTTP + the two WebSockets, against the simulator."""

from __future__ import annotations

import time

import pytest

from argos.server.settings import SimOptions
from tests.server.conftest import (
    AUTH,
    TOKEN,
    decode_frame,
    receive_bytes,
    receive_json,
    receive_until,
    reference_stats,
    wait_for,
)

SHORT = {"exposure_s": 0.02, "gain": 80}


def _camera(client) -> dict:
    return client.get("/api/status", headers=AUTH).json()["camera"]


def test_capture_requires_connection(client):
    response = client.post("/api/camera/capture", json=SHORT, headers=AUTH)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_connected"


def test_connect_reports_sensor(connected):
    camera = _camera(connected)
    assert camera["state"] == "idle"
    assert camera["sensor"] == {"width": 160, "height": 120, "bitpix": 16, "bayer": None}
    assert camera["last_frame_seq"] is None


def test_capture_delivers_one_full_size_frame(make_client):
    client = make_client(sim=SimOptions())  # real S50 geometry
    client.post("/api/connection", json={"mode": "simulator"}, headers=AUTH)
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        response = client.post(
            "/api/camera/capture", json={"exposure_s": 0.05, "gain": 80}, headers=AUTH
        )
        assert response.status_code == 200
        state = response.json()
        assert state["state"] == "exposing"
        assert state["exposure_s"] == 0.05 and state["gain"] == 80
        header, pixels = decode_frame(receive_bytes(frames))

    assert pixels.shape == (1920, 1080)  # rows = height: portrait, as the Seestar delivers
    assert header["width"] == 1080 and header["height"] == 1920
    assert header["channels"] == 1 and header["dtype"] == "uint16"
    assert header["pixel_offset"] % 8 == 0
    assert header["source"] == "simulator" and header["exposure_s"] == 0.05
    assert header["timestamp"].endswith("Z")
    assert header["stats"] == pytest.approx(reference_stats(pixels), abs=1e-9)
    # A short exposure sits on the pedestal: 1600 + 200 ADU/s × 0.05 s.
    assert 1550 < header["stats"]["median"] < 1700

    camera = wait_for(lambda: (c := _camera(client))["state"] == "idle" and c)
    assert camera["last_frame_seq"] == header["seq"]


def test_capture_state_transitions_on_events(connected):
    with connected.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        assert receive_json(events)["type"] == "status"
        connected.post("/api/camera/capture", json=SHORT, headers=AUTH)
        seen: list[dict] = []
        receive_until(
            events,
            lambda m: m["type"] == "camera" and m["camera"]["last_frame_seq"] is not None,
            seen=seen,
        )
    states = [m["camera"]["state"] for m in seen if m["type"] == "camera"]
    assert states == ["exposing", "downloading", "idle"]  # FIFO: no transition lost
    # Every camera change is mirrored by a status message.
    assert sum(m["type"] == "status" for m in seen) >= 2


def test_second_capture_while_busy_is_refused(connected):
    assert connected.post("/api/camera/live", json=SHORT, headers=AUTH).status_code == 200
    for route in ("capture", "live"):
        response = connected.post(f"/api/camera/{route}", json=SHORT, headers=AUTH)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "busy"
    assert connected.post("/api/camera/stop", headers=AUTH).json()["state"] == "idle"


def test_live_streams_until_stop(connected):
    with connected.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        response = connected.post("/api/camera/live", json=SHORT, headers=AUTH)
        assert response.json()["state"] == "live"
        seqs = [decode_frame(receive_bytes(frames))[0]["seq"] for _ in range(4)]
        assert seqs == sorted(seqs) and len(set(seqs)) == 4

        stopped = connected.post("/api/camera/stop", headers=AUTH)
        assert stopped.status_code == 200
        assert stopped.json()["state"] == "idle"
    camera = _camera(connected)
    assert camera["state"] == "idle"
    assert camera["last_frame_seq"] >= seqs[-1]
    # Stopped means stopped: the sequence no longer moves.
    last = camera["last_frame_seq"]
    time.sleep(0.15)  # several exposure periods
    assert _camera(connected)["last_frame_seq"] == last


def test_stop_interrupts_a_long_exposure(connected):
    connected.post("/api/camera/capture", json={"exposure_s": 30.0, "gain": 80}, headers=AUTH)
    assert _camera(connected)["state"] == "exposing"
    response = connected.post("/api/camera/stop", headers=AUTH)
    assert response.json()["state"] == "idle"
    assert _camera(connected)["last_frame_seq"] is None


def test_stop_when_idle_is_harmless(connected):
    assert connected.post("/api/camera/stop", headers=AUTH).json()["state"] == "idle"


def test_capture_after_capture(connected):
    for expected in (1, 2):
        connected.post("/api/camera/capture", json=SHORT, headers=AUTH)
        wait_for(lambda: _camera(connected)["last_frame_seq"] == expected)


def test_frame_client_gets_latest_frame_on_connect(connected):
    connected.post("/api/camera/capture", json=SHORT, headers=AUTH)
    wait_for(lambda: _camera(connected)["last_frame_seq"] == 1)
    with connected.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        header, _ = decode_frame(receive_bytes(frames))
    assert header["seq"] == 1


def test_disconnect_during_live_view(connected):
    connected.post("/api/camera/live", json=SHORT, headers=AUTH)
    response = connected.delete("/api/connection", headers=AUTH)
    assert response.json() == {
        "state": "disconnected",
        "mode": None,
        "device_name": None,
        "message": None,
    }
    status = connected.get("/api/status", headers=AUTH).json()
    assert status["camera"]["state"] == "idle"
    assert status["camera"]["sensor"] is None
    # Disconnecting twice is fine.
    assert connected.delete("/api/connection", headers=AUTH).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"exposure_s": 0, "gain": 80},
        {"exposure_s": -1, "gain": 80},
        {"exposure_s": 3601, "gain": 80},
        {"exposure_s": "1", "gain": 80},
        {"exposure_s": 1, "gain": 80.5},
        {"exposure_s": 1, "gain": -1},
        {"exposure_s": 1, "gain": 80, "binning": 2},
        {"exposure_s": 1, "frame_type": "science"},
        {"save": "yes"},
    ],
)
def test_exposure_validation(connected, body):
    response = connected.post("/api/camera/capture", json=body, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


def test_capture_fields_default_to_the_settings(connected):
    """Wave 3 (A23): a v1 body stays valid, and every field is now optional."""
    response = connected.post("/api/camera/capture", json={"exposure_s": 0.02}, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["gain"] == 80  # the settings' gain
    wait_for(lambda: _camera(connected)["state"] == "idle")
    assert connected.post("/api/camera/capture", headers=AUTH).status_code == 200


def test_reconnect_same_mode_is_idempotent_and_alpaca_while_connected_is_busy(connected):
    again = connected.post("/api/connection", json={"mode": "simulator"}, headers=AUTH)
    assert again.status_code == 200 and again.json()["state"] == "connected"
    other = connected.post(
        "/api/connection", json={"mode": "alpaca", "host": "10.0.0.1", "port": 32323}, headers=AUTH
    )
    assert other.status_code == 409 and other.json()["error"]["code"] == "busy"


def test_alpaca_mode_needs_host_and_port(client):
    response = client.post("/api/connection", json={"mode": "alpaca"}, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


def test_simulator_flag_connects_at_startup(make_client):
    client = make_client(simulator=True)
    status = client.get("/api/status", headers=AUTH).json()
    assert status["connection"]["state"] == "connected"
    assert status["connection"]["mode"] == "simulator"


# -- Changing exposure and gain while live (PATCH /api/camera/live) ------------


def test_live_settings_apply_from_the_next_frame(connected):
    with connected.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        connected.post("/api/camera/live", json=SHORT, headers=AUTH)
        decode_frame(receive_bytes(frames))
        response = connected.patch(
            "/api/camera/live", json={"exposure_s": 0.03, "gain": 120}, headers=AUTH
        )
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "live"
        # The camera record follows when the next exposure starts…
        wait_for(lambda: _camera(connected)["exposure_s"] == 0.03)
        assert _camera(connected)["gain"] == 120
        # …and the frames say what they were taken with.
        headers = [decode_frame(receive_bytes(frames))[0] for _ in range(3)]
    assert headers[-1]["exposure_s"] == 0.03
    connected.post("/api/camera/stop", headers=AUTH)


def test_live_settings_need_a_running_live_view(connected):
    response = connected.patch("/api/camera/live", json=SHORT, headers=AUTH)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_live"


def test_live_settings_are_validated(connected):
    connected.post("/api/camera/live", json=SHORT, headers=AUTH)
    response = connected.patch("/api/camera/live", json={"exposure_s": 0, "gain": 80}, headers=AUTH)
    assert response.status_code == 400
    connected.post("/api/camera/stop", headers=AUTH)


def test_no_job_can_start_while_disconnecting(connected, monkeypatch):
    """A live request landing inside the teardown is refused, and no thread survives it."""
    import threading

    from argos.server.devices.sim_camera import SimCamera
    from argos.server.errors import ApiError

    hub = connected.app.state.hub
    connected.post("/api/camera/live", json={"exposure_s": 5.0, "gain": 80}, headers=AUTH)
    outcome: list[str] = []

    def abort_then_request(self):
        try:
            hub.live(5.0, 80)
            outcome.append("started")
        except ApiError as exc:
            outcome.append(exc.code)

    monkeypatch.setattr(SimCamera, "abort", abort_then_request)
    connected.delete("/api/connection", headers=AUTH)
    assert outcome == ["not_connected"]
    wait_for(lambda: not any(t.name == "argos-live" for t in threading.enumerate()), timeout=2)
    assert _camera(connected)["state"] == "idle"


def test_frame_clients_are_capped(client):
    from contextlib import ExitStack

    from starlette.websockets import WebSocketDisconnect

    from argos.server.app import MAX_FRAME_CLIENTS

    with ExitStack() as stack:
        for _ in range(MAX_FRAME_CLIENTS):
            stack.enter_context(client.websocket_connect(f"/ws/frames?token={TOKEN}"))
        wait_for(lambda: client.app.state.hub.bus.frame_client_count == MAX_FRAME_CLIENTS)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/frames?token={TOKEN}") as extra:
                extra.receive_bytes()
        assert exc.value.code == 1013
