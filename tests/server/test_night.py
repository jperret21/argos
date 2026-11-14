"""Wave 6b, the night: keep-awake, the wrap-up, the sequence record's autofocus.

Keep-awake runs with the OS call faked (:class:`FakeBackend`): held from Start
to the end of a run however it ends (completed, stopped, failed, the run
thread crashed, the server shut down), never outside a run. The real
command lines are checked with ``subprocess.Popen`` faked; the one real
assertion on this Mac is checked by hand with ``pmset -g assertions``
(``web/spec/progress.md`` Wave 6b), never in the suite.
"""

from __future__ import annotations

import subprocess
import threading
import time

import pytest

from argos.server import keepawake, wrapup
from tests.server.conftest import (
    AUTH,
    TOKEN,
    log_messages,
    receive_until,
    science_client,
    status,
    wait_for,
)
from tests.server.test_sequence import (
    ALL,
    SEQ_SIM,
    dark,
    light,
    put_plan,
    start,
    state,
    wait_state,
)


class FakeAssertion:
    def __init__(self, backend: "FakeBackend") -> None:
        self.backend = backend
        self.released = False

    def release(self) -> None:
        self.released = True
        self.backend.held -= 1


class FakeBackend:
    method = "fake"

    def __init__(self, fail: str | None = None, available: bool = True) -> None:
        self.fail = fail
        self.ok = available
        self.held = 0
        self.reasons: list[str] = []
        self.lock = threading.Lock()

    def available(self):
        return (True, None) if self.ok else (False, "no fake here")

    def acquire(self, reason: str):
        if self.fail:
            raise OSError(self.fail)
        self.reasons.append(reason)
        self.held += 1
        return FakeAssertion(self)


@pytest.fixture
def seq(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=ALL, sim=SEQ_SIM, autofocus_settle_s=0.0)
    client.hub = client.app.state.hub  # type: ignore[attr-defined]
    return client


def fake(client, **kw) -> FakeBackend:
    backend = FakeBackend(**kw)
    client.hub.keep_awake.backend = backend
    client.hub.keep_awake._record = client.hub.keep_awake._idle_record()
    return backend


def awake(client) -> dict:
    return status(client)["keep_awake"]


# -- keep-awake: the lifecycle --------------------------------------------------------


def test_the_assertion_is_held_from_start_to_the_end_of_the_run(seq):
    backend = fake(seq)
    assert awake(seq)["state"] == "off"
    put_plan(seq, steps=[light(count=3, exposure_s=0.2)])
    start(seq)
    record = wait_for(lambda: (a := awake(seq))["state"] == "held" and a, timeout=5)
    assert record["method"] == "fake" and record["since"]
    assert record["reason"] == "A sequence is running (SYN Var)."
    assert backend.held == 1
    assert "Keeping the computer awake during the run (fake)." in log_messages(seq)
    wait_state(seq, "idle")
    wait_for(lambda: awake(seq)["state"] == "off", timeout=5)
    assert backend.held == 0 and seq.hub.keep_awake.released == 1
    assert "The computer may sleep again: the run ended." in log_messages(seq)


def test_released_on_stop_and_on_a_failed_run(seq):
    backend = fake(seq)
    put_plan(seq, steps=[light(count=20, exposure_s=0.3)])
    start(seq)
    wait_for(lambda: backend.held == 1, timeout=5)
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")
    wait_for(lambda: backend.held == 0, timeout=5)
    start(seq)
    wait_for(lambda: state(seq)["frames_done"] >= 1 and backend.held == 1, timeout=8)
    seq.delete("/api/devices/camera", headers=AUTH)  # the run ends: device_lost
    assert wait_state(seq, "idle")["last_result"]["reason"] == "device_lost"
    wait_for(lambda: backend.held == 0, timeout=5)
    assert seq.hub.keep_awake.acquired == 2 == seq.hub.keep_awake.released


def test_released_when_the_run_thread_crashes(seq, monkeypatch):
    backend = fake(seq)

    def crash(run):
        time.sleep(0.2)
        raise RuntimeError("boom")

    monkeypatch.setattr(seq.hub.sequence, "_loop", crash)
    put_plan(seq, steps=[light(count=2)])
    start(seq)
    done = wait_state(seq, "idle")
    assert done["last_result"]["reason"] == "camera_error"  # the worker's safety net
    wait_for(lambda: backend.held == 0, timeout=5)
    assert seq.hub.keep_awake.acquired == 1


def test_held_while_a_scheduled_start_waits(seq):
    backend = fake(seq)
    put_plan(seq, steps=[light(count=1)])
    future = time.time() + 3600
    from datetime import datetime, timezone

    start(seq, start_at_utc=datetime.fromtimestamp(future, timezone.utc).isoformat())
    assert state(seq)["state"] == "waiting"
    wait_for(lambda: backend.held == 1, timeout=5)
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_for(lambda: backend.held == 0, timeout=5)


def test_released_at_shutdown(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=ALL, sim=SEQ_SIM)
    client.hub = client.app.state.hub  # type: ignore[attr-defined]
    backend = fake(client)
    put_plan(client, steps=[light(count=20, exposure_s=0.3)])
    start(client)
    wait_for(lambda: backend.held == 1, timeout=5)
    client.__exit__(None, None, None)  # lifespan shutdown
    assert backend.held == 0
    assert client.hub.keep_awake.record()["state"] == "off"
    assert client.hub.sequence.record()["wrapup"] is None  # no wrap-up at shutdown


def test_a_failed_assertion_is_said_and_the_run_goes_on(seq):
    fake(seq, fail="caffeinate exited at once (code 1)")
    put_plan(seq, steps=[light(count=2)])
    start(seq)
    record = wait_for(lambda: (a := awake(seq))["state"] == "failed" and a, timeout=5)
    assert record["message"] == "caffeinate exited at once (code 1)"
    assert wait_state(seq, "idle")["last_result"]["completed"]
    assert any(
        m.startswith("The computer could not be kept awake (fake)") for m in log_messages(seq)
    )
    wait_for(lambda: awake(seq)["state"] == "off", timeout=5)


def test_disabled_in_settings_and_the_preflight_row(seq):
    backend = fake(seq)
    checks = seq.get("/api/sequence/preflight", headers=AUTH).json()["checks"]
    row = next(c for c in checks if c["id"] == "sleep")
    assert row["level"] == "ok"
    assert row["message"] == (
        "The computer is kept awake during the run (fake). Keep its lid open: a closed lid "
        "still sleeps most laptops."
    )
    assert (
        seq.patch("/api/config", json={"alerts.keep_awake": False}, headers=AUTH).status_code == 200
    )
    row = next(
        c
        for c in seq.get("/api/sequence/preflight", headers=AUTH).json()["checks"]
        if c["id"] == "sleep"
    )
    assert row["level"] == "note" and "keep-awake is off in Settings › Alerts" in row["message"]
    assert "lid open" in row["message"]
    put_plan(seq, steps=[light(count=1)])
    start(seq)
    wait_for(lambda: awake(seq)["state"] == "disabled", timeout=5)
    wait_state(seq, "idle")
    assert backend.held == 0 and seq.hub.keep_awake.acquired == 0


def test_without_a_method_the_row_is_a_note(seq):
    # In-process servers take no OS assertion (NullBackend): honest "unsupported".
    assert awake(seq)["state"] == "unsupported"
    row = next(
        c
        for c in seq.get("/api/sequence/preflight", headers=AUTH).json()["checks"]
        if c["id"] == "sleep"
    )
    assert row["level"] == "note" and row["details"] == {
        "method": None,
        "reason": "keep-awake is off in this process",
    }


# -- keep-awake: the OS command lines (Popen faked) -------------------------------------


class FakePopen:
    calls: list[list[str]] = []

    def __init__(self, argv, **kwargs) -> None:
        FakePopen.calls.append(list(argv))
        self.terminated = False
        self.stderr = None

    def wait(self, timeout=None):
        if not self.terminated:
            raise subprocess.TimeoutExpired("x", timeout)
        return 0

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def test_the_os_command_lines(monkeypatch):
    FakePopen.calls = []
    monkeypatch.setattr(keepawake.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(keepawake.shutil, "which", lambda name: f"/usr/bin/{name}")
    held = keepawake.CaffeinateBackend(pid=4242).acquire("A sequence is running (RR Lyr).")
    assert FakePopen.calls[-1] == ["/usr/bin/caffeinate", "-i", "-w", "4242"]
    held.release()
    assert held.proc.terminated
    keepawake.SystemdInhibitBackend(pid=4242).acquire("A sequence is running (RR Lyr).")
    assert FakePopen.calls[-1] == [
        "/usr/bin/systemd-inhibit",
        "--what=idle:sleep",
        "--who=ARGOS",
        "--why=A sequence is running (RR Lyr).",
        "--mode=block",
        "/usr/bin/tail",
        "--pid=4242",
        "-f",
        "/dev/null",
    ]
    assert type(keepawake.os_backend("darwin")).__name__ == "CaffeinateBackend"
    assert type(keepawake.os_backend("linux")).__name__ == "SystemdInhibitBackend"
    assert keepawake.os_backend("win32").method == "SetThreadExecutionState"
    assert keepawake.os_backend("sunos5").available() == (
        False,
        "no keep-awake method on sunos5",
    )


def test_a_helper_that_exits_at_once_is_a_failure(monkeypatch):
    class Dead(FakePopen):
        def wait(self, timeout=None):
            return 3

    monkeypatch.setattr(keepawake.subprocess, "Popen", Dead)
    monkeypatch.setattr(keepawake.shutil, "which", lambda name: f"/usr/bin/{name}")
    with pytest.raises(OSError, match="caffeinate exited at once"):
        keepawake.CaffeinateBackend(pid=1).acquire("x")
    monkeypatch.setattr(keepawake.shutil, "which", lambda name: None)
    assert keepawake.CaffeinateBackend().available() == (False, "caffeinate was not found")


def test_the_holder_releases_what_it_holds_on_close():
    backend = FakeBackend()
    changes: list[int] = []
    keep = keepawake.KeepAwake(backend, on_change=lambda: changes.append(1))
    keep.want("A sequence is running (X).")
    assert keep.settle(2.0) and keep.record()["state"] == "held"
    keep.want("A sequence is running (Y).")  # a new reason while held: no second assertion
    assert keep.settle(2.0) and keep.record()["reason"] == "A sequence is running (Y)."
    assert backend.held == 1 and keep.acquired == 1
    keep.close()
    assert backend.held == 0 and keep.record()["state"] == "off" and changes


def test_a_close_during_the_acquire_keeps_no_assertion():
    """Technical review: close() while the worker was inside acquire() returned at
    once; the worker then stored the new assertion, never released, record held."""

    class Slow(FakeBackend):
        def acquire(self, reason: str):
            time.sleep(0.5)
            return super().acquire(reason)

    backend = Slow()
    keep = keepawake.KeepAwake(backend)
    keep.want("A sequence is running (X).")
    time.sleep(0.1)  # the worker is inside acquire()
    keep.close()
    time.sleep(0.6)
    assert backend.held == 0  # 1 before the fix
    assert keep.record()["state"] == "off"


def test_the_setting_applies_to_the_run_in_progress():
    """Technical review: alerts.keep_awake turned off during a run kept the assertion
    until the run ended; turned on, it took none until the next run."""
    backend = FakeBackend()
    on = {"value": True}
    keep = keepawake.KeepAwake(backend, enabled=lambda: on["value"])
    keep.want("A sequence is running (X).")
    assert keep.settle(2.0) and backend.held == 1
    on["value"] = False
    keep.recheck()
    assert keep.settle(2.0)
    assert backend.held == 0 and keep.record()["state"] == "disabled"
    on["value"] = True
    keep.recheck()
    assert keep.settle(2.0)
    assert backend.held == 1 and keep.record()["state"] == "held"
    keep.close()
    assert backend.held == 0


def test_the_setting_reaches_the_keep_awake_through_the_config(seq):
    backend = fake(seq)
    put_plan(seq, steps=[light(count=40)])
    start(seq)
    wait_for(lambda: awake(seq)["state"] == "held", timeout=5)
    assert (
        seq.patch("/api/config", json={"alerts.keep_awake": False}, headers=AUTH).status_code == 200
    )
    wait_for(lambda: awake(seq)["state"] == "disabled", timeout=5)
    assert backend.held == 0
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")


# -- the wrap-up --------------------------------------------------------------------------


def wrap(client, timeout: float = 15.0) -> dict:
    return wait_for(lambda: state(client)["wrapup"], timeout=timeout)


def test_no_wrapup_before_a_run_ended(seq):
    answer = seq.get("/api/sequence/wrapup", headers=AUTH)
    assert answer.status_code == 404 and answer.json()["error"]["code"] == "not_found"
    assert state(seq)["wrapup"] is None


def test_a_completed_run_has_its_wrapup(seq):
    put_plan(seq, steps=[light(count=3), dark(count=1)])
    start(seq)
    done = wait_state(seq, "idle")
    record = wrap(seq)
    assert seq.get("/api/sequence/wrapup", headers=AUTH).json() == record
    assert record["outcome"] == done["last_result"]
    assert record["run_id"] == done["last_result"]["run_root"].rsplit("/", 1)[1][:16]
    assert record["object_name"] == "SYN Var"
    assert record["frames"] == {"saved": 4, "total": 4, "by_type": {"Light": 3, "Dark": 1}}
    assert record["run_folder"].endswith("_SYN_Var") and record["run_bytes"] > 4 * 160 * 120 * 2
    assert record["mount"]["connected"]
    assert record["mount"]["tracking"] is status(seq)["mount"]["tracking"]
    assert record["mount"]["state"] == status(seq)["mount"]["state"]
    assert record["mount"]["end_action"] == "Nothing"
    att = record["attention"]
    assert (att["critical"], att["attention"], att["info"]) == (0, 0, 2)
    assert [i["rule"] for i in att["items"]] == ["run_started", "run_ended"]
    assert record["points"]["target"] == 0  # no target set: no photometry
    calib = record["calibration"]
    assert calib["dark_slot"] is True
    (darks,) = calib["darks"]
    assert (darks["exposure_s"], darks["gain"], darks["count"]) == (0.05, 80, 20)
    assert darks["existing"] == 1  # the run's own dark (tonight's session.json)
    (bias,) = calib["biases"]
    assert (bias["exposure_s"], bias["gain"], bias["count"], bias["existing"]) == (0.01, 80, 30, 0)
    overhead = calib["overhead_s"]
    assert overhead >= 3.0
    assert darks["estimate_s"] == pytest.approx(20 * (0.05 + overhead), abs=0.1)
    assert bias["estimate_s"] == pytest.approx(30 * (0.01 + overhead), abs=0.1)


def test_a_new_start_clears_the_wrapup(seq):
    put_plan(seq, steps=[light(count=1)])
    start(seq)
    wait_state(seq, "idle")
    wrap(seq)
    record = start(seq)
    assert record["wrapup"] is None
    wait_state(seq, "idle")


def test_the_calibration_plan_replaces_the_draft_without_starting(seq):
    put_plan(seq, steps=[light(count=2)])
    start(seq)
    wait_state(seq, "idle")
    wrap(seq)
    before = seq.get("/api/sequence/plan", headers=AUTH).json()["plan"]
    answer = seq.post("/api/sequence/calibration-plan", json={"darks": 15}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["replaced"] == before
    plan = body["plan"]["plan"]
    steps = [(s["frame_type"], s["exposure_s"], s["gain"], s["count"]) for s in plan["steps"]]
    assert steps == [("Dark", 0.05, 80, 15), ("Bias", 0.01, 80, 30)]
    assert plan["object_name"] == "SYN Var" and plan["on_complete"] == "Nothing"
    assert body["plan"]["ready"] is True, body["plan"]["issues"]
    assert state(seq)["state"] == "idle"  # nothing starts
    assert any(m.startswith("Calibration plan prepared: 15 darks") for m in log_messages(seq))
    # And it runs: darks and biases through the Dark slot.
    start(seq)
    done = wait_state(seq, "idle", timeout=30)
    assert done["last_result"]["completed"] and done["last_result"]["frames_saved"] == 45


def test_calibration_plan_refusals(seq):
    answer = seq.post(
        "/api/sequence/calibration-plan", json={"darks": 0, "biases": 0}, headers=AUTH
    )
    assert answer.status_code == 400
    answer = seq.post("/api/sequence/calibration-plan", json={"darks": 1000}, headers=AUTH)
    assert answer.status_code == 400
    put_plan(seq, steps=[dark(count=2)])  # no run ended, no Light step in the draft
    answer = seq.post("/api/sequence/calibration-plan", headers=AUTH)
    assert answer.status_code == 400 and "No Light step" in answer.json()["error"]["message"]
    put_plan(seq, steps=[light(count=20, exposure_s=0.3)])
    start(seq)
    answer = seq.post("/api/sequence/calibration-plan", headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "run_active"
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")


def test_a_stopped_run_says_so_in_its_wrapup(seq):
    put_plan(seq, steps=[light(count=20, exposure_s=0.3)])
    start(seq)
    wait_for(lambda: state(seq)["frames_done"] >= 1, timeout=8)
    seq.post("/api/sequence/stop", headers=AUTH)
    wait_state(seq, "idle")
    record = wrap(seq)
    assert record["outcome"]["reason"] == "stopped"
    assert record["frames"]["saved"] < 20
    assert [i["title"].split(" · ")[0] for i in record["attention"]["items"]][-1] == (
        "Run stopped by the observer"
    )


def test_the_wrapup_helpers():
    from argos.core.imaging.sequencer import SequencePlan, SequenceStep

    plan = SequencePlan(
        object_name="RR Lyr",
        steps=[
            SequenceStep(frame_type="Light", filter_name="IR", exposure_s=10.0, gain=80, count=195),
            SequenceStep(frame_type="Light", filter_name="LP", exposure_s=10.0, gain=80, count=5),
            SequenceStep(frame_type="Light", filter_name="IR", exposure_s=30.0, gain=120, count=5),
            SequenceStep(frame_type="Dark", filter_name="IR", exposure_s=10.0, gain=80, count=5),
        ],
    )
    assert wrapup.light_series(plan) == [(10.0, 80, "IR"), (30.0, 120, "IR")]
    # The owner's RR Lyr run: 51.5 s start-to-start for 10 s subs with no wait.
    assert wrapup.overhead_s([(51.5, 10.0), (51.4, 10.0), (51.7, 10.0)]) == pytest.approx(41.5)
    assert wrapup.overhead_s([(10.5, 10.0)]) == 3.0  # never below the plan's 3 s
    assert wrapup.overhead_s([]) is None
    tonight = [("Dark", 10.0, 80, "Dark")] * 4 + [("Bias", 0.01, 80, "Dark")] * 2
    calib = wrapup.calibration(
        plan, tonight=tonight, overhead=41.5, cadence=51.5, min_exposure_s=0.0001, dark_slot=True
    )
    first = calib["darks"][0]
    # "about 17 min at tonight's 51 s cadence" (functional-spaces §4.14).
    assert first == {
        "exposure_s": 10.0,
        "gain": 80,
        "count": 20,
        "existing": 4,
        "estimate_s": 1030.0,
    }
    assert [b["gain"] for b in calib["biases"]] == [80, 120]
    assert calib["biases"][0]["existing"] == 2 and calib["biases"][0]["exposure_s"] == 0.01
    assert calib["note"] is None
    no_slot = wrapup.calibration(
        plan, tonight=[], overhead=None, cadence=None, min_exposure_s=None, dark_slot=False
    )
    assert "put the lid on" in no_slot["note"] and no_slot["overhead_s"] == 3.0
    body = wrapup.calibration_plan(plan, calib, darks=20, biases=0)
    assert [(s["frame_type"], s["filter_name"], s["exposure_s"]) for s in body["steps"]] == [
        ("Dark", "IR", 10.0),
        ("Dark", "IR", 30.0),
    ]
    live = {
        "curves": [
            {"role": "target", "points": [{"suspect": False}, {"suspect": True}]},
            {"role": "comparison", "points": [{"saturated": True}]},
        ]
    }
    assert wrapup.point_counts(live) == {"target": 2, "all": 3, "flagged": 2}
    assert wrapup.folder_bytes(None) is None


# -- the sequence record: mid-run autofocus (afStep) ------------------------------------


def test_mid_run_autofocus_progress_and_passes_are_in_the_record(seq):
    put_plan(seq, steps=[light(count=3)], autofocus_every_n=2)
    seq.put("/api/camera/settings", json={"exposure_s": 0.05}, headers=AUTH)
    progress: list[dict] = []
    with seq.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        start(seq)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = receive_until(ws, lambda m: m.get("type") == "sequence", timeout=30)
            if message["autofocus"] is not None:
                progress.append(message["autofocus"])
            if message["state"] == "idle" and message["last_result"]:
                break
    assert progress, "no sweep progress in the sequence record"
    steps = [p["step"] for p in progress]
    assert steps == sorted(steps) and max(steps) >= 1
    assert all(p["total"] >= p["step"] for p in progress) and progress[0]["started_utc"]
    record = state(seq)
    (af,) = record["autofocus_passes"]
    assert af["frames_done"] == 2 and af["started_utc"] and af["ended_utc"]
    assert af["state"] in ("done", "rejected")
    if af["state"] == "done":
        assert isinstance(af["position"], int)
    att = seq.get("/api/attention", headers=AUTH).json()
    rules = [i["rule"] for i in att["active"]]
    assert ("autofocus_done" if af["state"] == "done" else "autofocus_failed") in rules
    assert record["autofocus"] is None
