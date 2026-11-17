"""Autofocus (A36): the sweep, its gain (S22), Stop = return to start (S23), Halt (Q-O6)."""

from __future__ import annotations

import threading
import time

import pytest

from argos.server import autofocus as af
from argos.server.devices.sim_camera import SimCamera
from tests.server.conftest import (
    AUTH,
    TOKEN,
    decode_frame,
    log_messages,
    receive_bytes,
    science_client,
    status,
    wait_for,
)

FAST = {"exposure_s": 0.02, "gain": 80}


def _af(client) -> dict:
    return client.get("/api/autofocus", headers=AUTH).json()


def _ended(client, timeout: float = 20.0) -> dict:
    return wait_for(
        lambda: (a := _af(client))["state"] not in ("running", "stopping") and a, timeout=timeout
    )


def _start(client, **body) -> dict:
    response = client.post("/api/autofocus/start", json={**FAST, **body}, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def focus(make_client, tmp_path):
    """Camera + focuser: the sweep needs nothing else."""
    return science_client(make_client, tmp_path, connect=("camera", "focuser"))


def test_autofocus_finds_the_simulated_best_focus(focus):
    started = _start(focus, exposure_s=0.5)
    assert started["state"] == "running" and started["params"]["half_range"] == 2000
    assert status(focus)["camera"]["owner"] == "autofocus"
    assert status(focus)["focuser"]["locked_by"] == "autofocus"
    done = _ended(focus)
    assert done["state"] == "done", done["message"]
    assert done["start_position"] == 5000 and done["total"] == 14 and done["step"] == 14
    assert len(done["samples"]) == 14
    assert [s["stage"] for s in done["samples"]] == ["coarse"] * 9 + ["fine"] * 4 + ["verify"]
    best = done["best"]["position"]
    assert abs(best - 5300) <= 400  # the simulator's V-curve minimum (SimOptions.focus_best)
    assert done["fit"]["window"][0] < best < done["fit"]["window"][1]
    assert done["message"].startswith("Autofocus complete — best pos=")
    wait_for(lambda: status(focus)["camera"]["owner"] == "idle")
    assert status(focus)["focuser"]["locked_by"] is None
    assert any(m.startswith("Autofocus complete") for m in log_messages(focus))


def test_the_focuser_target_follows_the_sweep_moves(focus):
    """The record's target is the last move sent, autofocus moves included (web Focuser card)."""
    hub = focus.app.state.hub
    targets: list[int] = []
    real = hub.focuser.note_target

    def spy(target: int) -> None:
        targets.append(int(target))
        real(target)

    hub.focuser.note_target = spy
    _start(focus)
    done = _ended(focus)
    assert done["state"] == "done", done["message"]
    best = done["best"]["position"]
    sweep = [s["position"] for s in done["samples"]]
    assert targets[: len(set(sweep[:9]))] == sweep[:9]  # every coarse position was announced
    assert targets[-1] == best
    rec = wait_for(lambda: (f := status(focus)["focuser"])["state"] == "idle" and f)
    assert rec["target"] == best and rec["position"] == best


def test_sample_frames_are_published_and_use_the_af_gain(focus, monkeypatch):
    """S22: every sample exposure carries the requested gain."""
    gains: list[int] = []
    real = SimCamera.expose

    def spy(self, exposure_s, gain, *args, **kwargs):
        gains.append(int(gain))
        return real(self, exposure_s, gain, *args, **kwargs)

    monkeypatch.setattr(SimCamera, "expose", spy)
    with focus.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        _start(focus, gain=150)
        header, _ = decode_frame(receive_bytes(frames))
    assert header["origin"] == "autofocus" and header["gain"] == 150
    _ended(focus)
    assert gains and set(gains) == {150}


def test_stop_returns_the_focuser_to_its_start(focus):
    """S23: cancelled, back at the start, read back; the camera released after."""
    hub = focus.app.state.hub
    hub._sim_optics.focuser._speed = 4000.0  # a real wait for the moves
    _start(focus)
    wait_for(lambda: len(_af(focus)["samples"]) >= 2, timeout=10)
    stopping = focus.post("/api/autofocus/stop", headers=AUTH).json()
    assert stopping["state"] in ("stopping", "cancelled")
    again = focus.post("/api/autofocus/stop", headers=AUTH)  # harmless
    assert again.status_code == 200
    done = _ended(focus)
    assert done["state"] == "cancelled" and done["message"] == "Returned to 5000."
    assert hub._sim_optics.focuser.get_position() == 5000
    assert status(focus)["camera"]["owner"] == "idle"


def test_a_slow_return_keeps_the_camera_and_refuses_a_second_sweep(focus):
    hub = focus.app.state.hub
    _start(focus)
    wait_for(lambda: len(_af(focus)["samples"]) >= 3, timeout=10)
    hub._sim_optics.focuser._speed = 2000.0  # the way back takes about a second
    focus.post("/api/autofocus/stop", headers=AUTH)
    busy = focus.post("/api/autofocus/start", json=FAST, headers=AUTH)
    assert busy.status_code == 409 and busy.json()["error"]["owner"] == "autofocus"
    assert status(focus)["camera"]["owner"] == "autofocus"  # until the focuser is back
    done = _ended(focus)
    assert done["state"] == "cancelled"
    assert hub._sim_optics.focuser.get_position() == 5000


def test_halt_during_autofocus_stops_where_it_is(focus):
    """Q-O6: Halt = stop here, no return to the start."""
    hub = focus.app.state.hub
    hub._sim_optics.focuser._speed = 1500.0
    _start(focus)
    wait_for(lambda: len(_af(focus)["samples"]) >= 2, timeout=10)
    halted = focus.post("/api/focuser/halt", headers=AUTH)
    assert halted.status_code == 200
    done = _ended(focus)
    assert done["state"] == "cancelled"
    assert done["message"].startswith("Halted at ") and done["message"].endswith(
        ": focus left there."
    )
    position = int(done["message"].split()[2].rstrip(":"))
    assert hub._sim_optics.focuser.get_position() == position


def test_halt_never_freezes_the_return_move(focus):
    hub = focus.app.state.hub
    _start(focus)
    wait_for(lambda: len(_af(focus)["samples"]) >= 3, timeout=10)
    hub._sim_optics.focuser._speed = 2000.0
    focus.post("/api/autofocus/stop", headers=AUTH)
    wait_for(lambda: _af(focus)["stage"] == "returning", timeout=5)
    focus.post("/api/focuser/halt", headers=AUTH)
    done = _ended(focus)
    assert done["message"] == "Returned to 5000."
    assert "Halt ignored: autofocus is returning the focuser to its start." in log_messages(focus)


def test_manual_moves_are_refused_during_autofocus(focus):
    """H10: no Go to and no step while autofocus owns the focuser."""
    _start(focus)
    for route, body in (("move", {"position": 4000}), ("step", {"delta": 10})):
        answer = focus.post(f"/api/focuser/{route}", json=body, headers=AUTH)
        assert answer.status_code == 409
        assert answer.json()["error"]["message"] == "Autofocus owns the focuser."
    focus.post("/api/autofocus/stop", headers=AUTH)
    _ended(focus)


def test_camera_commands_are_busy_during_autofocus(focus):
    _start(focus)
    for route, body in (
        ("capture", {"save": True}),
        ("live", None),
        ("stop", None),
    ):
        answer = focus.post(f"/api/camera/{route}", json=body, headers=AUTH)
        assert answer.status_code == 409, route
        assert answer.json()["error"]["owner"] == "autofocus"
    settings = focus.put("/api/camera/settings", json={"gain": 10}, headers=AUTH)
    assert settings.status_code == 409
    focus.post("/api/autofocus/stop", headers=AUTH)
    _ended(focus)


def test_autofocus_preempts_live_view(focus):
    focus.post("/api/camera/live", json={"exposure_s": 0.05}, headers=AUTH)
    _start(focus)
    assert "Live view stopped: autofocus owns the camera." in log_messages(focus)
    focus.post("/api/autofocus/stop", headers=AUTH)
    _ended(focus)
    assert status(focus)["camera"]["state"] == "idle"


def test_a_flat_sweep_is_rejected_and_focus_unchanged(focus, monkeypatch):
    monkeypatch.setattr(af, "compute_hfd", lambda arr: 4.0)
    _start(focus)
    done = _ended(focus)
    assert done["state"] == "rejected"
    assert "flat HFD curve" in done["message"] and "focus unchanged" in done["message"]
    assert focus.app.state.hub._sim_optics.focuser.get_position() == 5000


def test_no_valid_samples_is_rejected(focus, monkeypatch):
    monkeypatch.setattr(af, "compute_hfd", lambda arr: None)
    _start(focus)
    done = _ended(focus)
    assert done["state"] == "rejected" and "fewer than 3 valid samples" in done["message"]


def test_start_refusals(make_client, tmp_path):
    camera_only = science_client(make_client, tmp_path / "a", connect=("camera",))
    answer = camera_only.post("/api/autofocus/start", json=FAST, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "not_connected"
    both = science_client(make_client, tmp_path / "b", connect=("camera", "focuser"))
    too_long = both.post("/api/autofocus/start", json={"exposure_s": 4000.0}, headers=AUTH)
    assert too_long.status_code == 400
    steps = both.post("/api/autofocus/start", json={"num_steps": 2}, headers=AUTH)
    assert steps.status_code == 400
    _start(both)
    second = both.post("/api/autofocus/start", json=FAST, headers=AUTH)
    assert second.status_code == 409 and second.json()["error"]["code"] == "busy"
    both.post("/api/autofocus/stop", headers=AUTH)
    _ended(both)


def test_defaults_follow_the_capture_settings(focus):
    focus.put("/api/camera/settings", json={"exposure_s": 30.0, "gain": 110}, headers=AUTH)
    started = focus.post("/api/autofocus/start", headers=AUTH).json()
    # acquisition_engine.py:945: the capture exposure, at most 10 s.
    assert started["params"] == {"exposure_s": 10.0, "gain": 110, "half_range": 2000,
                                 "num_steps": 9}  # fmt: skip
    focus.post("/api/autofocus/stop", headers=AUTH)
    _ended(focus, timeout=30)


def test_disconnecting_the_camera_returns_the_focuser(focus):
    hub = focus.app.state.hub
    _start(focus)
    wait_for(lambda: len(_af(focus)["samples"]) >= 2, timeout=10)
    focus.delete("/api/devices/camera", headers=AUTH)
    done = _ended(focus)
    assert done["state"] == "cancelled" and done["message"] == "Returned to 5000."
    assert hub._sim_optics.focuser.get_position() == 5000


def test_the_control_lock_orders_stop_before_any_sweep_move():
    """No sweep move after a stop: ``_move`` checks the flag under the control lock."""

    class Focuser:
        max_step = 10_000

        def __init__(self):
            self.calls: list[tuple[str, int | None]] = []
            self.position = 5000

        def get_position(self):
            return self.position

        def is_moving(self):
            return False

        def move_to(self, position):
            self.calls.append(("move", position))
            self.position = position

        def halt(self):
            self.calls.append(("halt", None))

    class Hub:
        _lock = threading.RLock()

        def _publish(self, kind, payload):
            pass

        def log(self, *args, **kwargs):
            pass

    focuser = Focuser()
    ended = threading.Event()
    run = af.AutofocusRun(
        Hub(), None, focuser, af.AutofocusParams(0.01, 80), 1,
        settle_s=0, poll_s=0, publish_frame=lambda *a: 0, on_end=lambda r: ended.set(),
    )  # fmt: skip
    assert run.stop() is True and run.stop() is False
    run.record = af.idle_record(1) | {"start_position": 5000}
    with pytest.raises(af._Stopped):
        run._move(4000)
    assert ("move", 4000) not in focuser.calls
    assert focuser.calls[0] == ("halt", None)  # halt first, then the flag (S23)
    assert run.halt() is False  # a halt after a stop changes nothing
    time.sleep(0)


def test_a_failing_focuser_fails_the_sweep_and_releases_everything(focus, monkeypatch):
    from argos.server.devices.sim_aux import SimFocuser

    hub = focus.app.state.hub
    real = SimFocuser.move_to
    calls = {"n": 0}

    def flaky(self, position):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("focuser timeout")
        return real(self, position)

    monkeypatch.setattr(SimFocuser, "move_to", flaky)
    _start(focus)
    done = _ended(focus)
    assert done["state"] == "failed"
    assert done["message"] == "focuser timeout — focuser returned to 5000"
    assert hub._sim_optics.focuser.get_position() == 5000
    assert status(focus)["camera"]["owner"] == "idle"
    assert status(focus)["focuser"]["locked_by"] is None
    assert "Autofocus: focuser timeout — focuser returned to 5000" in log_messages(focus)


def test_wheel_moves_are_busy_during_autofocus(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera", "focuser", "filterwheel"))
    _start(client)
    answer = client.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["owner"] == "autofocus"
    client.post("/api/autofocus/stop", headers=AUTH)
    _ended(client)


# -- review of wave 3: a return is said only once read back; never behind Dark ---------


def test_stop_says_so_when_the_focuser_is_lost_during_the_return(focus, monkeypatch):
    from argos.server.devices.sim_aux import SimFocuser

    hub = focus.app.state.hub
    hub._sim_optics.focuser._speed = 2000.0
    _start(focus)
    wait_for(lambda: len(_af(focus)["samples"]) >= 3, timeout=10)

    def lost(self, *args):
        raise OSError("no answer")

    focus.post("/api/autofocus/stop", headers=AUTH)
    wait_for(lambda: _af(focus)["stage"] == "returning", timeout=5)
    monkeypatch.setattr(SimFocuser, "is_moving", lost)
    monkeypatch.setattr(SimFocuser, "get_position", lost)
    done = _ended(focus)
    assert done["state"] == "failed"
    assert "could not read the focuser back: it may not be at its start (5000)" in done["message"]
    assert "Returned to" not in done["message"]
    assert any(
        m.startswith("Autofocus: could not read the focuser back") for m in log_messages(focus)
    )


def test_a_return_slower_than_the_wait_limit_is_not_reported_as_done(focus, monkeypatch):
    hub = focus.app.state.hub
    real_init = af.AutofocusRun.__init__

    def short_wait(self, *args, **kwargs):
        kwargs["deadline_s"] = 0.3
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(af.AutofocusRun, "__init__", short_wait)
    _start(focus)
    wait_for(lambda: len(_af(focus)["samples"]) >= 3, timeout=10)
    hub._sim_optics.focuser._speed = 500.0  # about 4 s to come back
    focus.post("/api/autofocus/stop", headers=AUTH)
    done = _ended(focus)
    assert done["state"] == "failed"
    assert "still moving, not yet back at its start (5000)" in done["message"]
    hub._sim_optics.focuser._speed = 1e6


def test_autofocus_is_refused_behind_the_dark_slot(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera", "focuser", "filterwheel"))
    client.post("/api/filterwheel/select", json={"name": "Dark"}, headers=AUTH)
    wait_for(lambda: status(client)["filterwheel"]["slot"] == "Dark")
    answer = client.post("/api/autofocus/start", json=FAST, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "dark_slot"
    assert "which blocks the light" in answer.json()["error"]["message"]
    assert _af(client)["state"] == "idle"
