"""Filter wheel (A28), focuser (A34, A35) and capture settings (A21, A22) routes."""

from __future__ import annotations

import time

import pytest

from argos.server.devices.sim_aux import SimFilterWheel, SimFocuser
from argos.server.devices.base import DeviceError
from tests.server.conftest import (
    AUTH,
    TOKEN,
    log_messages,
    receive_json,
    receive_until,
    science_client,
    status,
    wait_for,
)


def _wheel(client) -> dict:
    return client.get("/api/filterwheel", headers=AUTH).json()


def _focuser(client) -> dict:
    return client.get("/api/focuser", headers=AUTH).json()


# ---------------------------------------------------------------------------
# Filter wheel
# ---------------------------------------------------------------------------


def test_wheel_record_before_and_after_connect(make_client, tmp_path):
    client = science_client(make_client, tmp_path)
    assert _wheel(client)["state"] == "disconnected"
    client.post("/api/devices/filterwheel/connect", json={"mode": "simulator"}, headers=AUTH)
    wheel = wait_for(lambda: (w := _wheel(client))["state"] == "idle" and w)
    assert wheel["slots"] == ["Dark", "IR", "LP"] and wheel["dark_slot"] is True
    assert wheel["slot"] == "IR" and wheel["position"] == 1
    assert status(client)["filterwheel"] == wheel
    client.delete("/api/devices/filterwheel", headers=AUTH)
    assert _wheel(client)["state"] == "disconnected"


def test_select_moves_then_settles_and_the_settings_follow(science):
    with science.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        answer = science.post("/api/filterwheel/select", json={"name": "lp"}, headers=AUTH)
        assert answer.status_code == 200
        assert answer.json()["state"] == "moving" and answer.json()["target"] == "LP"
        done = receive_until(events, lambda m: m["type"] == "filterwheel" and m["state"] == "idle")
    assert done["slot"] == "LP" and done["settled_utc"].endswith("Z")
    assert status(science)["camera"]["settings"]["filter"] == "LP"  # S3: follows the wheel
    assert "Filter → LP" in log_messages(science)


def test_select_refusals(science, make_client, tmp_path):
    unknown = science.post("/api/filterwheel/select", json={"name": "Ha"}, headers=AUTH)
    assert unknown.status_code == 400
    assert unknown.json()["error"]["message"] == "No wheel slot named 'Ha' (slots: Dark, IR, LP)"
    science.app.state.hub._sim_optics.wheel._slot_s = 1.0
    science.post("/api/filterwheel/select", json={"name": "Dark"}, headers=AUTH)
    busy = science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    assert busy.status_code == 409 and busy.json()["error"]["owner"] == "filterwheel"
    other = science_client(make_client, tmp_path / "other")
    nothing = other.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    assert nothing.status_code == 409 and nothing.json()["error"]["code"] == "not_connected"


def test_a_refused_move_ends_moving_and_reports_the_real_slot(science, monkeypatch):
    """H9: the record never stays "moving"; the slot read back is the truth."""

    def refuse(self, index):
        raise DeviceError("Invalid filter position")

    monkeypatch.setattr(SimFilterWheel, "set_position", refuse)
    science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    wheel = wait_for(lambda: (w := _wheel(science))["state"] != "moving" and w)
    assert wheel["state"] == "idle" and wheel["slot"] == "IR"
    assert wheel["message"] == "Invalid filter position"
    assert "Filter move: Invalid filter position" in log_messages(science)
    assert status(science)["camera"]["settings"]["filter"] == "IR"


def test_an_unreadable_wheel_after_a_refusal_is_an_error(science, monkeypatch):
    def refuse(self, index):
        raise DeviceError("refused")

    def unreadable(self):
        raise DeviceError("no answer")

    monkeypatch.setattr(SimFilterWheel, "set_position", refuse)
    monkeypatch.setattr(SimFilterWheel, "get_position", unreadable)
    science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    wheel = wait_for(lambda: (w := _wheel(science))["state"] != "moving" and w)
    assert wheel["state"] == "error" and "position unknown" in wheel["message"]
    assert wheel["slot"] is None
    # A Dark shot is refused then: its position is unknown (S1).
    science.app.state.hub.wheel._record["dark_slot"] = True
    assert science.app.state.hub.wheel.not_on_dark().startswith(
        "the filter wheel's position is unknown"
    )


def test_a_wheel_still_turning_after_the_budget_is_an_error(science, monkeypatch):
    from argos.server import wheel as wheel_module

    monkeypatch.setattr(wheel_module, "SETTLE_TIMEOUT_S", 0.3)
    monkeypatch.setattr(SimFilterWheel, "get_position", lambda self: -1)
    science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    wheel = wait_for(lambda: (w := _wheel(science))["state"] != "moving" and w, timeout=3)
    assert wheel["state"] == "error" and wheel["message"] == wheel_module.STILL_TURNING


# ---------------------------------------------------------------------------
# Capture settings (PUT /api/camera/settings)
# ---------------------------------------------------------------------------


def test_camera_record_carries_limits_offset_and_temperature(science):
    camera = status(science)["camera"]
    assert camera["owner"] == "idle" and camera["save_pending"] == 0
    assert camera["limits"] == {
        "gain_min": 0,
        "gain_max": 600,
        "exposure_min_s": 0.001,
        "exposure_max_s": 3600.0,
    }
    assert camera["offset"] == {"min": 0, "max": 255} and camera["binning"] is None
    assert camera["temperature_c"] == 21.0
    assert camera["settings"] == {
        "exposure_s": 2.0,
        "gain": 80,
        "frame_type": "light",
        "filter": "IR",
        "offset": 10,
        "binning": 1,
    }


def test_settings_are_one_checked_commit_never_clamped(science):
    good = science.put(
        "/api/camera/settings",
        json={"exposure_s": 1.5, "gain": 120, "frame_type": "flat", "offset": 30},
        headers=AUTH,
    )
    assert good.status_code == 200, good.text
    settings = good.json()["settings"]
    assert settings["exposure_s"] == 1.5 and settings["gain"] == 120
    assert settings["frame_type"] == "flat" and settings["offset"] == 30
    assert good.json()["exposure_s"] == 1.5  # v1 field: the settings while idle
    assert science.app.state.hub._camera.get_offset() == 30  # sent to the driver
    for body, text in (
        ({"gain": 601}, "Gain 601 is outside 0–600 (the camera's range)."),
        ({"offset": 300}, "Offset 300 is outside 0–255."),
        ({"binning": 2}, "Binning 2 is outside 1–1 (this camera does not bin)."),
        ({"filter": "Ha"}, "No wheel slot named 'Ha' (slots: Dark, IR, LP)"),
    ):
        bad = science.put("/api/camera/settings", json={"exposure_s": 3.0, **body}, headers=AUTH)
        assert bad.status_code == 400 and bad.json()["error"]["message"] == text
    # Nothing of a refused commit was applied.
    assert status(science)["camera"]["settings"]["exposure_s"] == 1.5
    assert (
        science.put(
            "/api/camera/settings", json={"frame_type": "science"}, headers=AUTH
        ).status_code
        == 400
    )


def test_filter_without_a_wheel_is_metadata_only(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera",))
    answer = client.put("/api/camera/settings", json={"filter": "L-eXtreme"}, headers=AUTH)
    assert answer.status_code == 200 and answer.json()["settings"]["filter"] == "L-eXtreme"
    assert "No filter wheel: 'L-eXtreme' is written to FITS FILTER only." in log_messages(client)


def test_filter_with_a_wheel_moves_it(science):
    science.put("/api/camera/settings", json={"filter": "LP"}, headers=AUTH)
    wait_for(lambda: _wheel(science)["slot"] == "LP")


# ---------------------------------------------------------------------------
# Focuser
# ---------------------------------------------------------------------------


def test_focuser_record_after_connect(science):
    focuser = _focuser(science)
    assert focuser["state"] == "idle" and focuser["position"] == 5000
    assert focuser["max_step"] == 10_000 and focuser["absolute"] is True
    assert focuser["temperature_c"] == 12.5 and focuser["locked_by"] is None


def test_go_to_moves_and_the_poll_reports_it(science):
    answer = science.post("/api/focuser/move", json={"position": 6000}, headers=AUTH).json()
    assert answer["sent"] == 6000 and answer["queued"] is False and answer["clamped"] is False
    wait_for(lambda: _focuser(science)["position"] == 6000, timeout=3)
    assert "Focuser move → 6000" in log_messages(science)


def test_go_to_is_bounded_by_max_step(science):
    """H10: never clamped silently."""
    for position in (10_001, -1):
        bad = science.post("/api/focuser/move", json={"position": position}, headers=AUTH)
        assert bad.status_code == 400
    assert bad.json()["error"]["message"] == (
        "Position -1 is outside 0–10000 (the focuser's MaxStep)."
    )


def test_a_step_is_clamped_and_says_so(science):
    answer = science.post("/api/focuser/step", json={"delta": 9000}, headers=AUTH).json()
    assert answer["requested"] == 14_000 and answer["sent"] == 10_000 and answer["clamped"]
    assert "Focuser step +9000 → 10000 (clamped)" in log_messages(science)


def test_moves_during_a_move_are_queued_and_sent_as_one(make_client, tmp_path):
    """D9: no Move while moving; steps add up."""
    client = science_client(make_client, tmp_path, connect=("focuser",))
    hub = client.app.state.hub
    hub.focuser._poll_moving_s = 0.05
    hub._sim_optics.focuser._speed = 2000.0  # 1000 steps take 0.5 s
    client.post("/api/focuser/move", json={"position": 6000}, headers=AUTH)
    first = client.post("/api/focuser/step", json={"delta": 100}, headers=AUTH).json()
    second = client.post("/api/focuser/step", json={"delta": 50}, headers=AUTH).json()
    assert first["queued"] and second["queued"] and second["sent"] is None
    assert second["focuser"]["queued"] == 6150  # from the queued target
    wait_for(lambda: _focuser(client)["position"] == 6150, timeout=5)
    assert _focuser(client)["queued"] is None


def test_halt_stops_and_clears_the_queue(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("focuser",))
    client.app.state.hub._sim_optics.focuser._speed = 1000.0
    client.post("/api/focuser/move", json={"position": 9000}, headers=AUTH)
    client.post("/api/focuser/step", json={"delta": 100}, headers=AUTH)
    time.sleep(0.2)
    halted = client.post("/api/focuser/halt", headers=AUTH).json()
    assert halted["focuser"]["queued"] is None
    position = halted["focuser"]["position"]
    assert 5000 < position < 9000
    time.sleep(0.3)
    assert abs(_focuser(client)["position"] - position) <= 1  # stopped where it was
    assert "Focuser halted" in log_messages(client)


def test_focuser_commands_need_a_focuser(make_client, tmp_path):
    client = science_client(make_client, tmp_path)
    for route, body in (("move", {"position": 1}), ("step", {"delta": 1}), ("halt", None)):
        answer = client.post(f"/api/focuser/{route}", json=body, headers=AUTH)
        assert answer.status_code == 409 and answer.json()["error"]["code"] == "not_connected"


def test_sim_focuser_clamps_like_the_alpaca_wrapper():
    now = [0.0]
    focuser = SimFocuser(speed_steps_s=1000.0, clock=lambda: now[0])
    focuser.move_to(20_000)
    assert focuser.is_moving()
    now[0] += 10.0
    assert focuser.get_position() == focuser.max_step  # focuser.py:132
    assert not focuser.is_moving()
    focuser.move_to(-5)
    now[0] += 20.0
    assert focuser.get_position() == 0


@pytest.mark.parametrize("body", [{"position": "1"}, {"position": 1.5}, {}])
def test_focuser_bodies_are_strict(science, body):
    assert science.post("/api/focuser/move", json=body, headers=AUTH).status_code == 400
