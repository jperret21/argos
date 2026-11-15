"""Wave 6a: sequences (A62-A64), the mount interlock, the replay source.

The run is the fixed Qt sequence path ported to the server (``argos/server/
sequence.py``). These tests drive it through the HTTP routes on the
simulator (every device simulated, temporary folders): the run folder and
files, the ``sequence`` event, pause / resume / stop with Qt's semantics, the
scheduled start, the mid-run autofocus, a device lost, a client gone, a
shutdown, the interlock on every motion route, S7 and "no silent clamp".
The Qt parity of a sequence is ``test_sequence_parity.py``.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from argos.server.sequence import GEOMETRY_KEYS
from argos.server.settings import SimOptions
from tests.server.conftest import (
    AUTH,
    TOKEN,
    log_messages,
    receive_until,
    science_client,
    status,
    wait_for,
)

SEQ_SIM = SimOptions(
    width=160,
    height=120,
    n_stars=40,
    slew_rate_deg_s=400.0,
    wheel_slot_s=0.02,
    focuser_speed_steps_s=200_000.0,
    mount_poll_s=0.05,
)
ALL = ("mount", "camera", "filterwheel", "focuser")


def light(count: int = 2, exposure_s: float = 0.05, **extra) -> dict:
    return {
        "frame_type": "Light",
        "filter_name": "IR",
        "exposure_s": exposure_s,
        "gain": 80,
        "count": count,
        **extra,
    }


def dark(count: int = 1, exposure_s: float = 0.05) -> dict:
    return {
        "frame_type": "Dark",
        "filter_name": "IR",
        "exposure_s": exposure_s,
        "gain": 80,
        "count": count,
    }


@pytest.fixture
def seq(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=ALL, sim=SEQ_SIM, autofocus_settle_s=0.0)
    client.hub = client.app.state.hub  # type: ignore[attr-defined]
    return client


def put_plan(client, object_name: str = "SYN Var", steps=None, **plan) -> dict:
    body = {"object_name": object_name, "steps": steps if steps is not None else [light()]}
    body.update(plan)
    response = client.put("/api/sequence/plan", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def state(client) -> dict:
    return client.get("/api/sequence", headers=AUTH).json()


def start(client, **body) -> dict:
    response = client.post("/api/sequence/start", json=body or None, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def wait_state(client, *names: str, timeout: float = 15.0) -> dict:
    wait_for(lambda: state(client)["state"] in names, timeout=timeout)
    return state(client)


def run_folder(client) -> Path:
    (root,) = [p for p in client.sessions_path.iterdir() if p.is_dir() and p.name != "targets"]
    return root


# -- a whole run: folder, files, events (as Qt) -------------------------------------


def test_a_run_writes_the_qt_run_folder_and_reports_its_outcome(seq):
    put_plan(seq, steps=[light(count=2), dark(count=1)], repeat=2)
    record = start(seq)
    assert record["state"] == "running" and record["active"]
    assert record["frames_total"] == 6 and record["plan"]["schema"] == 2
    assert status(seq)["camera"]["owner"] == "sequence"
    assert status(seq)["sequence"]["active"] is True
    assert status(seq)["focuser"]["locked_by"] == "sequence"
    assert seq.get("/api/observation", headers=AUTH).json()["locked"] is True
    done = wait_state(seq, "idle")

    result = done["last_result"]
    assert result["completed"] and result["reason"] == "completed"
    assert result["frames_saved"] == 6 and result["frames_total"] == 6
    root = run_folder(seq)
    assert result["run_root"] == str(root)
    assert root.name.endswith("_SYN_Var") and root.name[:16].endswith("Z")
    lights = sorted(p.name for p in (root / "lights").iterdir())
    darks = sorted(p.name for p in (root / "darks").iterdir())
    # The Siril series index restarts per (type, filter, exposure, gain) and grows
    # across passes (expand_plan).
    assert lights == [f"SYN_Var_ir_light_e000050ms_g080_{i:05d}.fit" for i in (1, 2, 3, 4)]
    assert darks == [f"SYN_Var_dark_dark_e000050ms_g080_{i:05d}.fit" for i in (1, 2)]
    session = json.loads((root / "session.json").read_text())
    assert [f["image_type"] for f in session["frames"]] == [
        "Light Frame",
        "Light Frame",
        "Dark Frame",
    ] * 2
    assert not (root / "observation.json").exists()  # no metadata, no file (as Qt)
    assert (root / "targets.json").exists() and (root / "photometry_selection.json").exists()
    with fits.open(root / "darks" / darks[0]) as hdul:
        header = hdul[0].header
    assert header["IMAGETYP"] == "Dark Frame" and header["FILTER"] == "Dark"  # S7: the wheel
    with fits.open(root / "lights" / lights[0]) as hdul:
        header = hdul[0].header
    assert header["FILTER"] == "IR" and header["OBJECT"] == "SYN Var"
    assert header["EXPTIME"] == 0.05 and header["GAIN"] == 80

    after = status(seq)
    assert after["camera"]["owner"] == "idle" and after["sequence"]["active"] is False
    assert after["focuser"]["locked_by"] is None
    assert seq.get("/api/observation", headers=AUTH).json()["locked"] is False
    saved = seq.get("/api/camera/saved", headers=AUTH).json()["saves"]
    assert [s["source"] for s in saved] == ["sequence"] * 6
    lines = log_messages(seq)
    assert "Sequence started — 6 frame(s)." in lines and "Sequence complete." in lines
    assert any(line.startswith("Saved SYN_Var_ir_light_e000050ms_g080_00001.fit") for line in lines)


def test_the_sequence_event_streams_and_a_late_client_gets_the_run(seq):
    put_plan(seq, steps=[light(count=3, exposure_s=0.3)])
    with seq.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        receive_until(ws, lambda m: m.get("type") == "sequence")
        start(seq)
        running = receive_until(
            ws, lambda m: m.get("type") == "sequence" and m["frames_done"] >= 1, timeout=10
        )
    assert running["state"] in ("running", "pausing")
    assert running["last_frame_name"] and running["last_frame_utc"]
    assert running["cadence_s"] == pytest.approx(0.3 + 3.0)  # exposure + interval + 3 s
    assert running["step"]["frame_type"] == "Light" and running["pass_index"] == 1
    assert running["end_utc"] is not None and running["eta_s"] is not None
    # A client that connects mid-run receives the run at once.
    with seq.websocket_connect(f"/ws/events?token={TOKEN}") as late:
        snapshot = receive_until(late, lambda m: m.get("type") == "sequence")
    assert snapshot["active"] and snapshot["run_id"]
    wait_state(seq, "idle")


# -- pause, resume, stop (Qt semantics) ------------------------------------------------


def test_pause_completes_the_frame_in_progress_and_resume_goes_on(seq):
    put_plan(seq, steps=[light(count=3, exposure_s=0.6)])
    start(seq)
    wait_for(lambda: state(seq)["current"] is not None, timeout=5)
    paused = seq.post("/api/sequence/pause", headers=AUTH).json()
    assert paused["state"] == "pausing" and paused["paused_by"] == "observer"
    held = wait_state(seq, "paused")
    assert held["frames_done"] == 1  # the exposure in progress was completed and saved
    time.sleep(0.8)
    assert state(seq)["frames_done"] == 1  # nothing exposes while paused
    assert seq.post("/api/sequence/pause", headers=AUTH).json()["state"] == "paused"  # no-op
    assert seq.post("/api/sequence/resume", headers=AUTH).json()["state"] == "running"
    done = wait_state(seq, "idle")
    assert done["last_result"]["completed"] and done["last_result"]["frames_saved"] == 3


def test_stop_mid_exposure_discards_that_frame_and_keeps_the_saved_ones(seq):
    put_plan(seq, steps=[light(count=5, exposure_s=0.5)])
    start(seq)
    wait_for(lambda: state(seq)["frames_done"] >= 1 and state(seq)["current"], timeout=8)
    stopping = seq.post("/api/sequence/stop", headers=AUTH).json()
    assert stopping["state"] in ("stopping", "idle")
    done = wait_state(seq, "idle")
    result = done["last_result"]
    assert not result["completed"] and result["reason"] == "stopped"
    saved = sorted((run_folder(seq) / "lights").iterdir())
    assert len(saved) == result["frames_saved"] >= 1
    assert len(json.loads((run_folder(seq) / "session.json").read_text())["frames"]) == len(saved)
    assert "Sequence stopped: Stopped by the observer." in log_messages(seq)
    # stop when idle answers the idle state
    assert seq.post("/api/sequence/stop", headers=AUTH).json()["state"] == "idle"


def test_pause_and_resume_need_a_run(seq):
    for verb in ("pause", "resume"):
        response = seq.post(f"/api/sequence/{verb}", headers=AUTH)
        assert response.status_code == 409 and response.json()["error"]["code"] == "not_running"


# -- scheduled start (Q-P2) -----------------------------------------------------------


def test_a_scheduled_start_waits_then_runs(seq):
    put_plan(seq, steps=[light(count=1)])
    at = datetime.now(timezone.utc) + timedelta(seconds=1.2)
    record = start(seq, start_at_utc=at.isoformat())
    assert record["state"] == "waiting" and record["start_at_utc"]
    assert record["run_id"] is None
    # The camera is free while waiting: live view and the mount are allowed.
    assert status(seq)["camera"]["owner"] == "idle"
    response = seq.post("/api/sequence/pause", headers=AUTH)
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_running"
    done = wait_state(seq, "idle", timeout=10)
    assert done["last_result"]["completed"]
    run_id = run_folder(seq).name.split("_")[0]
    assert datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) >= at.replace(
        microsecond=0
    )


def test_stop_while_waiting_cancels_and_writes_nothing(seq):
    put_plan(seq, steps=[light(count=1)])
    at = datetime.now(timezone.utc) + timedelta(minutes=30)
    start(seq, start_at_utc=at.isoformat().replace("+00:00", "Z"))
    # A live view during the wait is the observer's (framing, focus).
    assert seq.post("/api/camera/live", json={"exposure_s": 0.05}, headers=AUTH).status_code == 200
    seq.post("/api/camera/stop", headers=AUTH)
    done = seq.post("/api/sequence/stop", headers=AUTH).json()
    done = wait_state(seq, "idle")
    assert done["last_result"]["reason"] == "cancelled" and done["last_result"]["frames_saved"] == 0
    written = list(seq.sessions_path.iterdir()) if seq.sessions_path.exists() else []
    assert not [p for p in written if p.name != "targets"]


@pytest.mark.parametrize(
    "value, text",
    [("tomorrow", "start_at_utc"), ("2026-11-12T21:00:00", "zone"), ("far", "24 h")],
)
def test_start_time_errors(seq, value, text):
    put_plan(seq)
    if value == "far":
        value = (datetime.now(timezone.utc) + timedelta(hours=25)).isoformat()
    response = seq.post("/api/sequence/start", json={"start_at_utc": value}, headers=AUTH)
    assert response.status_code == 400 and text in response.json()["error"]["message"]
    assert state(seq)["state"] == "idle"


def test_a_start_days_ahead_names_its_day(seq):
    """Wave 6b design review: "The start time 21:30 UTC is more than 24 h ahead" for a start
    three days away read as tonight; the refusal and the preflight name the day."""
    put_plan(seq)
    when = (datetime.now(timezone.utc) + timedelta(days=3)).replace(hour=21, minute=30)
    day = f"{when.day} {when.strftime('%b')} 21:30 UTC"
    response = seq.post(
        "/api/sequence/start", json={"start_at_utc": when.isoformat()}, headers=AUTH
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == f"The start time {day} is more than 24 h ahead."
    check = checks(seq, start_at_utc=when.isoformat())["start_at"]
    assert check["level"] == "block" and day in check["message"]


def test_a_start_time_already_passed_starts_now(seq):
    put_plan(seq, steps=[light(count=1)])
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert start(seq, start_at_utc=past)["state"] == "running"
    wait_state(seq, "idle")


# -- refusals, S7, no silent clamp ----------------------------------------------------


def test_start_refusals(seq, make_client, tmp_path):
    put_plan(seq, steps=[light(count=3, exposure_s=0.5)])
    start(seq)
    again = seq.post("/api/sequence/start", headers=AUTH)
    assert again.status_code == 409 and again.json()["error"]["code"] == "busy"
    assert again.json()["error"]["owner"] == "sequence"
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")

    bare = science_client(make_client, tmp_path / "bare")
    bare.put("/api/sequence/plan", json={"object_name": "X", "steps": [light()]}, headers=AUTH)
    refused = bare.post("/api/sequence/start", headers=AUTH)
    assert refused.status_code == 409
    assert refused.json()["error"] == {
        "code": "not_connected",
        "message": "Connect the camera before running a sequence.",
    }


def test_a_light_step_on_the_dark_slot_is_refused_never_remapped_s7(seq):
    put_plan(seq, steps=[light(count=1, filter_name="Dark")])
    response = seq.post("/api/sequence/start", headers=AUTH)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_argument"
    assert "opaque Dark slot" in error["message"] and error["message"].startswith("Fix step 1")
    assert state(seq)["state"] == "idle" and status(seq)["camera"]["owner"] == "idle"
    # The engine's own check refuses it too, whatever the draft says (no remap).
    from argos.core.imaging.sequencer import SequencePlan, SequenceStep

    issues = seq.hub.sequence.plan_issues(
        SequencePlan(steps=[SequenceStep(frame_type="Light", filter_name="Dark")], object_name="X")
    )
    assert [i["code"] for i in issues] == ["dark_slot"]
    assert "opaque 'Dark' slot" in issues[0]["message"]
    preflight = seq.get("/api/sequence/preflight", headers=AUTH).json()
    assert not preflight["can_start"]
    assert any(c["id"] == "plan" and c["level"] == "block" for c in preflight["checks"])


def test_an_out_of_range_value_is_refused_never_clamped(seq):
    put_plan(seq, steps=[light(count=1, exposure_s=5000.0)])  # simulator max 3600 s
    response = seq.post("/api/sequence/start", headers=AUTH)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"
    assert "Fix step 1" in response.json()["error"]["message"]
    # the draft is unchanged: 5000 s is still what the plan says
    assert (
        seq.get("/api/sequence/plan", headers=AUTH).json()["plan"]["steps"][0]["exposure_s"]
        == 5000.0
    )
    # and the engine's own check refuses it too (a draft that bypassed the plan half)
    from argos.core.imaging.sequencer import SequencePlan, SequenceStep

    hub = seq.hub
    issues = hub.sequence.plan_issues(
        SequencePlan(
            steps=[SequenceStep(frame_type="Light", filter_name="IR", exposure_s=5000.0)],
            object_name="X",
        )
    )
    assert [i["code"] for i in issues] == ["out_of_range"]


def test_a_filter_the_wheel_lacks_is_refused(seq):
    hub = seq.hub
    from argos.core.imaging.sequencer import SequencePlan, SequenceStep

    issues = hub.sequence.plan_issues(
        SequencePlan(steps=[SequenceStep(frame_type="Light", filter_name="Ha")], object_name="X")
    )
    assert [i["code"] for i in issues] == ["unknown_filter"]
    assert "slots: Dark, IR, LP" in issues[0]["message"]


def test_the_plan_is_locked_while_a_run_is_active(seq):
    put_plan(seq, steps=[light(count=3, exposure_s=0.5)])
    start(seq)
    response = seq.put(
        "/api/sequence/plan", json={"object_name": "SYN Var", "steps": [light()]}, headers=AUTH
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "run_active"
    assert seq.get("/api/sequence/plan", headers=AUTH).json()["locked"] is True
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")
    assert seq.get("/api/sequence/plan", headers=AUTH).json()["locked"] is False


# -- the geometry lock (S15) -----------------------------------------------------------


def test_the_aperture_geometry_is_locked_during_a_run(seq):
    put_plan(seq, steps=[light(count=3, exposure_s=0.5)])
    start(seq)
    for key in GEOMETRY_KEYS:
        response = seq.patch("/api/config", json={key: 9}, headers=AUTH)
        assert response.status_code == 409, key
        error = response.json()["error"]
        assert error["code"] == "run_active" and error["keys"] == [key]
    # the comparison selection stays editable (as Qt)
    ok = seq.patch("/api/config", json={"photometry.min_comparisons": 3}, headers=AUTH)
    assert ok.status_code == 200, ok.text
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")
    assert seq.patch("/api/config", json={GEOMETRY_KEYS[0]: 3.0}, headers=AUTH).status_code == 200


# -- the mount interlock (PROPOSAL §7, D2) ---------------------------------------------

MOTIONS = [
    ("GoTo", "/api/mount/goto", {"ra_hours": 5.0, "dec_deg": 20.0}),
    ("Centre", "/api/mount/center", {"target": {"ra_hours": 5.0, "dec_deg": 20.0}}),
    ("Sync", "/api/mount/sync", {"source": "solution"}),
    ("Park", "/api/mount/park", None),
    ("Unpark", "/api/mount/unpark", None),
    ("Tracking off", "/api/mount/tracking", {"enabled": False}),
    ("Tracking rate", "/api/mount/tracking-rate", {"rate": "lunar"}),
    ("Jog", "/api/mount/jog", {"axis": "primary", "rate_deg_s": 1.0}),
]


def test_every_mount_motion_is_refused_during_a_run(seq):
    unpark = seq.post("/api/mount/unpark", headers=AUTH)
    assert unpark.status_code == 200
    put_plan(seq, steps=[light(count=4, exposure_s=0.5)])
    start(seq)
    for action, path, body in MOTIONS:
        response = seq.post(path, json=body, headers=AUTH)
        assert response.status_code == 409, (action, response.text)
        error = response.json()["error"]
        assert error["code"] == "run_active", action
        assert error["action"] == action and error["state"] in ("running", "pausing")
        assert error["message"] == (
            f"A sequence is running — {action} would move the field under it. "
            "Pause the run first."
        )
    # Never refused: tracking on, Abort, jog stop.
    assert seq.post("/api/mount/tracking", json={"enabled": True}, headers=AUTH).status_code == 200
    assert seq.post("/api/mount/stop", headers=AUTH).status_code == 200
    assert seq.post("/api/mount/jog/stop", headers=AUTH).status_code == 200
    # The Stellarium bridge has no answer channel: a WARN line.
    seq.hub._stellarium_goto(5.0, 20.0)
    assert "Stellarium GoTo not sent: a sequence is running — pause it first" in log_messages(seq)
    assert state(seq)["state"] in ("running", "pausing")  # nothing paused the run
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")
    assert seq.post("/api/mount/goto", json=MOTIONS[0][2], headers=AUTH).status_code == 200


def test_pause_the_run_and_slew(seq):
    assert seq.post("/api/mount/unpark", headers=AUTH).status_code == 200
    put_plan(seq, steps=[light(count=3, exposure_s=0.6)])
    start(seq)
    wait_for(lambda: state(seq)["current"] is not None, timeout=5)
    began = time.monotonic()
    response = seq.post(
        "/api/mount/goto", json={"ra_hours": 6.0, "dec_deg": 10.0, "pause_run": True}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    held = state(seq)
    assert held["state"] == "paused" and held["paused_by"] == "motion"
    assert held["frames_done"] == 1  # the sub in progress was completed first
    assert time.monotonic() - began < 5
    assert status(seq)["mount"]["target"] == {"ra_hours": 6.0, "dec_deg": 10.0}
    # While paused the mount is free (no pause_run needed).
    wait_for(lambda: status(seq)["mount"]["state"] != "slewing", timeout=5)
    rate = seq.post("/api/mount/tracking-rate", json={"rate": "sidereal"}, headers=AUTH)
    assert rate.status_code == 200
    seq.post("/api/sequence/resume", headers=AUTH)
    done = wait_state(seq, "idle")
    assert done["last_result"]["completed"] and done["last_result"]["frames_saved"] == 3


# -- mid-run autofocus ---------------------------------------------------------------------


def test_a_mid_run_autofocus_hands_the_camera_over_and_back(seq):
    put_plan(seq, steps=[light(count=3)], autofocus_every_n=2)
    seq.put("/api/camera/settings", json={"exposure_s": 0.05}, headers=AUTH)
    owners: list[str] = []
    with seq.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        start(seq)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = receive_until(ws, lambda m: m.get("type") in ("status", "sequence"))
            if message["type"] == "status":
                owners.append(message["camera"]["owner"])
            elif message["state"] == "idle" and message["last_result"]:
                break
    done = state(seq)
    assert done["last_result"]["completed"] and done["last_result"]["frames_saved"] == 3
    assert "autofocus" in owners and "sequence" in owners
    assert owners.index("autofocus") > owners.index("sequence")
    assert "Sequence: autofocus…" in log_messages(seq)
    assert status(seq)["focuser"]["locked_by"] is None


def test_stop_during_autofocus_stops_the_sweep_too(seq):
    put_plan(seq, steps=[light(count=3)], autofocus_every_n=1)
    seq.put("/api/camera/settings", json={"exposure_s": 0.2}, headers=AUTH)
    start(seq)
    wait_for(lambda: state(seq)["state"] == "autofocus", timeout=10)
    seq.post("/api/sequence/stop", headers=AUTH)
    done = wait_state(seq, "idle", timeout=30)
    assert done["last_result"]["reason"] == "stopped"
    # The run ends once the sweep has ended and the focuser is back (S23).
    assert seq.get("/api/autofocus", headers=AUTH).json()["state"] == "cancelled"
    assert status(seq)["camera"]["owner"] == "idle"


def test_without_a_focuser_the_autofocus_passes_are_skipped(seq):
    seq.delete("/api/devices/focuser", headers=AUTH)
    put_plan(seq, steps=[light(count=2)], autofocus_every_n=1)
    preflight = seq.get("/api/sequence/preflight", headers=AUTH).json()
    assert any(c["id"] == "focuser" and c["level"] == "note" for c in preflight["checks"])
    start(seq)
    done = wait_state(seq, "idle")
    assert done["last_result"]["completed"]
    assert log_messages(seq).count("Sequence: autofocus skipped — no focuser connected.") == 1


# -- device lost, client gone, shutdown -------------------------------------------------


def test_a_camera_lost_mid_run_ends_it_with_its_reason(seq):
    put_plan(seq, steps=[light(count=5, exposure_s=0.5)])
    start(seq)
    wait_for(lambda: state(seq)["frames_done"] >= 1, timeout=8)
    seq.delete("/api/devices/camera", headers=AUTH)
    done = wait_state(seq, "idle")
    assert done["last_result"]["reason"] == "device_lost"
    assert done["last_result"]["message"] == "The camera was disconnected."
    assert status(seq)["focuser"]["locked_by"] is None


def test_a_client_that_goes_away_changes_nothing(seq):
    put_plan(seq, steps=[light(count=3, exposure_s=0.2)])
    with seq.websocket_connect(f"/ws/events?token={TOKEN}&client=web-1") as ws:
        receive_until(ws, lambda m: m.get("type") == "status")
        start(seq)
    done = wait_state(seq, "idle")
    assert done["last_result"]["completed"]


def test_a_shutdown_during_a_run_stops_it_cleanly(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=ALL, sim=SEQ_SIM)
    hub = client.app.state.hub
    put_plan(client, steps=[light(count=20, exposure_s=0.3)])
    start(client)
    wait_for(lambda: state(client)["frames_done"] >= 1, timeout=8)
    client.__exit__(None, None, None)  # lifespan shutdown
    record = hub.sequence.record()
    assert record["state"] == "idle"
    assert record["last_result"]["reason"] == "shutdown"
    root = Path(record["last_result"]["run_root"])
    frames = json.loads((root / "session.json").read_text())["frames"]
    assert (
        len(frames)
        == record["last_result"]["frames_saved"]
        == len(list((root / "lights").iterdir()))
    )


# -- preflight (A64) ------------------------------------------------------------------------


def checks(client, **query) -> dict:
    response = client.get("/api/sequence/preflight", params=query, headers=AUTH)
    assert response.status_code == 200, response.text
    return {c["id"]: c for c in response.json()["checks"]}


def test_preflight_reports_each_check(seq):
    put_plan(seq, steps=[light(count=4), dark(count=2)])
    body = seq.get("/api/sequence/preflight", headers=AUTH).json()
    assert body["can_start"] and body["frames_total"] == 6
    assert body["bytes_needed"] == 6 * (160 * 120 * 2 + 17_280)
    assert [c["level"] for c in body["checks"]] == sorted(
        (c["level"] for c in body["checks"]), key=["block", "note", "ok"].index
    )
    by_id = {c["id"]: c for c in body["checks"]}
    assert by_id["camera"]["level"] == "ok" and by_id["run"]["level"] == "ok"
    assert by_id["wheel"]["level"] == "ok" and by_id["lid"]["level"] == "ok"
    assert by_id["site"]["level"] == "note"  # no site in a fresh config (X2)
    assert by_id["mount"]["level"] == "note"  # parked at start
    assert by_id["disk"]["level"] == "ok" and by_id["output"]["level"] == "ok"
    # the plan's own darks count; no flat and no bias tonight
    assert by_id["calibration"]["level"] == "note"
    assert by_id["calibration"]["details"]["per_step"][0] == {
        "step": 0,
        "darks": 2,
        "flats": 0,
        "biases": 0,
    }


def test_preflight_blocks_what_start_refuses(seq):
    put_plan(seq, steps=[light(count=1)])
    seq.delete("/api/devices/camera", headers=AUTH)
    by_id = checks(seq)
    assert by_id["camera"]["level"] == "block"
    assert by_id["camera"]["message"] == "Connect the camera before running a sequence."
    assert checks(seq, start_at_utc="nonsense")["start_at"]["level"] == "block"


def test_preflight_lid_note_without_a_wheel_and_calibration_counts(seq):
    put_plan(seq, steps=[light(count=1), dark(count=1)])
    start(seq)
    wait_state(seq, "idle")  # tonight: 1 light, 1 dark at 0.05 s gain 80
    seq.delete("/api/devices/filterwheel", headers=AUTH)
    put_plan(seq, steps=[light(count=1, exposure_s=0.05), light(count=1, exposure_s=0.2)])
    by_id = checks(seq)
    per_step = by_id["calibration"]["details"]["per_step"]
    assert per_step[0]["darks"] == 1 and per_step[1]["darks"] == 0
    assert by_id["calibration"]["level"] == "note"
    assert by_id["calibration"]["message"].startswith("Missing tonight: ")
    assert "step 2 (0.2 s, gain 80, IR): darks, flats and biases" in by_id["calibration"]["message"]
    assert by_id["wheel"]["level"] == "note"
    put_plan(seq, steps=[dark(count=1)])
    assert checks(seq)["lid"]["level"] == "note"


def test_preflight_altitude_and_disk(seq, monkeypatch):
    seq.patch(
        "/api/config",
        json={"site.name": "Test", "site.latitude": 48.85, "site.longitude": 2.35},
        headers=AUTH,
    )
    seq.post(
        "/api/observation/target",
        json={"name": "SYN Var", "ra_hours": 6.0, "dec_deg": -80.0},
        headers=AUTH,
    )
    put_plan(seq, steps=[light(count=2)])
    by_id = checks(seq)
    assert by_id["altitude"]["level"] == "note" and "below 30°" in by_id["altitude"]["message"]
    import shutil as _shutil

    monkeypatch.setattr(
        "argos.server.sequence.shutil.disk_usage",
        lambda _p: _shutil._ntuple_diskusage(10, 9, 1),  # type: ignore[attr-defined]
    )
    by_id = checks(seq)
    assert by_id["disk"]["level"] == "block"
    refused = seq.post("/api/sequence/start", headers=AUTH)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "preflight_blocked"


# -- in-run target-set edits are journalled (Q-P9) -------------------------------------------


def test_an_in_run_target_set_edit_is_journalled(seq):
    from argos.core.catalog.targets import TargetSet, TargetStar

    tset = TargetSet(
        object_name="SYN Var",
        stars=[
            TargetStar("target", 291.0, 42.0, name="SYN Var", source="vsx"),
            TargetStar("comparison", 291.1, 42.1, auid="000-AAA-001", name="C1", source="vsp"),
        ],
    )
    tset.save(seq.sessions_path / "targets" / "SYN_Var.json")
    put_plan(seq, steps=[light(count=4, exposure_s=0.4)])
    start(seq)
    wait_for(lambda: state(seq)["frames_done"] >= 1, timeout=8)
    key = next(s["key"] for s in seq.get("/api/targets", headers=AUTH).json()["stars"] if s["auid"])
    assert seq.delete(f"/api/targets/{key}", headers=AUTH).status_code == 200
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")
    history = (run_folder(seq) / "photometry_selection_history.jsonl").read_text().splitlines()
    assert len(history) == 2  # the run's first save, then the edit


def test_a_sub_is_measured_with_the_frame_its_solution_was_solved_on_s56(seq, monkeypatch):
    """Release S56 as amended (2026-11-15, second set), through a run: each saved
    Light sub is measured with the reference solution and the frame it was solved on,
    read together (``FieldService.reference_with_frame``): its freshness
    (``solved_seq``) and the frame its tracker's anchors are chosen on
    (``solved_raw``). Without them the anchors were chosen on the measured sub again
    and the 500 px jump passed the lock check with 1 anchor."""
    from argos.core.catalog.targets import TargetSet, TargetStar

    TargetSet(
        object_name="SYN Var",
        stars=[TargetStar("target", 291.0, 42.0, name="SYN Var", source="vsx")],
    ).save(seq.sessions_path / "targets" / "SYN_Var.json")
    wcs, raw = object(), np.zeros((4, 4), dtype=np.uint16)
    monkeypatch.setattr(seq.hub.field, "reference_with_frame", lambda: (wcs, 7, 41, raw))
    requests: list = []
    monkeypatch.setattr(seq.hub.photometry, "measure_saved_frame", requests.append)
    put_plan(seq, steps=[light(count=2)])
    start(seq)
    assert wait_state(seq, "idle")["last_result"]["completed"]
    assert len(requests) == 2
    for request in requests:
        assert request.origin == "sequence" and request.wcs is wcs and request.generation == 7
        assert request.solved_seq == 41 and request.solved_raw is raw  # None before


# -- the simulator replay source ---------------------------------------------------------


def write_replay(folder: Path, n: int = 3) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(n):
        data = np.full((40, 60), 1000 + i, dtype=np.uint16)
        data[5, 7] = 50000
        hdu = fits.PrimaryHDU(data=data)
        hdu.header["BAYERPAT"] = "GRBG"
        hdu.header["SOFTWARE"] = "Argos v0.5.0"
        hdu.header["RA"] = 19.4 + 0.001 * i
        hdu.header["DEC"] = 42.78
        hdu.header["ALTITUDE"] = 60.0 + i
        hdu.header["AZIMUTH"] = 250.0
        hdu.header["CCD-TEMP"] = 18.5
        hdu.header["OFFSET"] = 7
        path = folder / f"f_{i:03d}.fit"
        hdu.writeto(path)
        out.append(path)
    return out


def test_the_replay_source_plays_the_folder_and_the_mount_reports_its_pointing(
    make_client, tmp_path
):
    from tests.server.conftest import decode_frame, receive_bytes

    write_replay(tmp_path / "replay")
    sim = SimOptions(replay_dir=tmp_path / "replay", mount_poll_s=0.05)
    client = science_client(make_client, tmp_path, connect=("mount", "camera"), sim=sim)
    record = status(client)
    assert record["camera"]["sensor"] == {"width": 60, "height": 40, "bitpix": 16, "bayer": "GRBG"}
    wait_for(lambda: status(client)["mount"]["state"] == "tracking", timeout=5)
    mount = status(client)["mount"]
    assert mount["ra_hours"] == pytest.approx(19.4) and mount["alt_deg"] == pytest.approx(60.0)
    seen = []
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as ws:
        for _ in range(4):
            assert (
                client.post(
                    "/api/camera/capture", json={"exposure_s": 0.01}, headers=AUTH
                ).status_code
                == 200
            )
            _header, pixels = decode_frame(receive_bytes(ws))
            seen.append(int(pixels[0, 0]))
            wait_for(lambda: status(client)["camera"]["state"] == "idle", timeout=5)
    assert seen == [1000, 1001, 1002, 1000]  # in order, then from the first again
    wait_for(lambda: status(client)["mount"]["ra_hours"] == pytest.approx(19.4), timeout=5)


def test_a_replay_folder_without_fits_stops_the_server(tmp_path):
    from argos.server.app import create_app
    from tests.server.conftest import make_settings

    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="holds no FITS image"):
        create_app(make_settings(sim=SimOptions(replay_dir=tmp_path / "empty")))


def test_the_sim_replay_flag(tmp_path, capsys):
    from argos.server.__main__ import _parse_args

    write_replay(tmp_path / "replay", n=1)
    assert _parse_args(["--sim-replay", str(tmp_path / "replay")]).sim_replay == tmp_path / "replay"
    for bad in ("relative/dir", str(tmp_path / "missing")):
        with pytest.raises(SystemExit):
            _parse_args(["--sim-replay", bad])
    assert "--sim-replay must name an existing folder" in capsys.readouterr().err


def test_the_run_owns_the_camera_the_wheel_and_the_focuser(seq):
    put_plan(seq, steps=[light(count=4, exposure_s=0.5)])
    start(seq)
    refused = {
        "capture": seq.post("/api/camera/capture", json={"exposure_s": 0.1}, headers=AUTH),
        "live": seq.post("/api/camera/live", json={"exposure_s": 0.1}, headers=AUTH),
        "wheel": seq.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH),
        "focuser": seq.post("/api/focuser/move", json={"position": 4000}, headers=AUTH),
        "autofocus": seq.post("/api/autofocus/start", headers=AUTH),
    }
    for what, response in refused.items():
        assert response.status_code == 409, (what, response.text)
        error = response.json()["error"]
        assert error["code"] == "busy" and error["owner"] == "sequence", (what, error)
    assert refused["focuser"].json()["error"]["message"] == "A sequence owns the focuser."
    assert seq.post("/api/focuser/halt", headers=AUTH).status_code == 200  # safety: always
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")


# -- fixer, wave 6a technical review -------------------------------------------------------


def test_two_starts_at_once_never_share_the_camera(seq, monkeypatch):
    """Two clients pressing Start: one run, the camera owned by it, idle after it."""
    import threading

    from argos.server.errors import ApiError

    put_plan(seq, steps=[light(count=3, exposure_s=0.3)])
    service = seq.hub.sequence
    real = service._check_camera

    def slow_check() -> None:  # widens the window both starts used to share
        real()
        time.sleep(0.3)

    monkeypatch.setattr(service, "_check_camera", slow_check)
    barrier = threading.Barrier(2)
    codes: list[int] = []

    def press_start() -> None:
        barrier.wait()
        try:
            service.start()
            codes.append(200)
        except ApiError as exc:
            codes.append(exc.status)

    threads = [threading.Thread(target=press_start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(codes) == [200, 409]
    assert status(seq)["camera"]["owner"] == "sequence"
    done = wait_state(seq, "idle")
    assert done["last_result"]["completed"]
    camera = status(seq)["camera"]
    assert camera["owner"] == "idle" and camera["state"] == "idle"


def test_a_start_that_fails_half_way_frees_the_engine(seq, monkeypatch):
    put_plan(seq, steps=[light(count=1)])
    calls = {"n": 0}
    real = seq.hub.photometry.begin_run

    def failing_once() -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        real()

    monkeypatch.setattr(seq.hub.photometry, "begin_run", failing_once)
    response = seq.post("/api/sequence/start", headers=AUTH)
    assert response.status_code == 500
    assert "disk full" in response.json()["error"]["message"]
    after = state(seq)
    assert after["state"] == "idle" and after["last_result"]["reason"] == "refused"
    assert status(seq)["camera"]["owner"] == "idle"
    assert status(seq)["focuser"]["locked_by"] is None
    assert seq.get("/api/observation", headers=AUTH).json()["locked"] is False
    start(seq)  # the engine is free: the next Start runs
    assert wait_state(seq, "idle")["last_result"]["completed"]


def test_resume_during_a_mid_run_autofocus_cancels_the_pending_pause(seq):
    put_plan(seq, steps=[light(count=2)], autofocus_every_n=1)
    seq.put("/api/camera/settings", json={"exposure_s": 0.2}, headers=AUTH)
    start(seq)
    wait_for(lambda: state(seq)["state"] == "autofocus", timeout=10)
    paused = seq.post("/api/sequence/pause", headers=AUTH).json()
    assert paused["state"] == "autofocus" and paused["paused_by"] == "observer"  # pending
    resumed = seq.post("/api/sequence/resume", headers=AUTH).json()
    assert resumed["state"] == "autofocus" and resumed["paused_by"] is None
    assert "Pause cancelled: the run goes on after the autofocus." in log_messages(seq)
    done = wait_state(seq, "idle", timeout=40)
    assert done["last_result"]["completed"] and done["last_result"]["frames_saved"] == 2


def test_a_resumed_run_waits_for_the_slew_to_end(make_client, tmp_path):
    from dataclasses import replace

    sim = replace(SEQ_SIM, slew_rate_deg_s=2.0)
    client = science_client(make_client, tmp_path, connect=ALL, sim=sim, autofocus_settle_s=0.0)
    assert client.post("/api/mount/unpark", headers=AUTH).status_code == 200
    put_plan(client, steps=[light(count=3, exposure_s=0.3)])
    start(client)
    wait_for(lambda: state(client)["current"] is not None, timeout=5)
    moved = client.post(
        "/api/mount/goto", json={"ra_hours": 6.0, "dec_deg": 10.0, "pause_run": True}, headers=AUTH
    )
    assert moved.status_code == 200, moved.text
    assert status(client)["mount"]["state"] == "slewing"
    done_before = state(client)["frames_done"]
    client.post("/api/sequence/resume", headers=AUTH)
    time.sleep(1.0)
    assert status(client)["mount"]["state"] == "slewing"
    held = state(client)
    assert held["frames_done"] == done_before and held["current"] is None
    assert "Waiting for the slew to end before the next frame…" in log_messages(client)
    assert client.post("/api/mount/stop", headers=AUTH).status_code == 200  # never refused
    done = wait_state(client, "idle", timeout=20)
    assert done["last_result"]["completed"] and done["last_result"]["frames_saved"] == 3


def test_preflight_ids_are_unique_and_plan_notes_name_their_issue(seq):
    put_plan(seq, steps=[light(count=2, interval_s=5.0, cadence_s=1.0)])
    body = seq.get("/api/sequence/preflight", headers=AUTH).json()
    ids = [c["id"] for c in body["checks"]]
    assert len(ids) == len(set(ids)), ids
    assert "plan" in ids and "plan:interval_ignored:1" in ids
    by_id = {c["id"]: c for c in body["checks"]}
    assert by_id["plan"]["message"].startswith("2 frames, about ")
    # Wave 6b: "ok" only when keep-awake works (test_night.py); in-process tests take no
    # OS assertion, so the row is a note; the lid stays out of software reach either way.
    assert by_id["sleep"]["level"] == "note" and "lid open" in by_id["sleep"]["message"]
