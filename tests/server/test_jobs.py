"""The generic job model (``web/spec/README.md`` §4.2, row A80)."""

from __future__ import annotations

import threading
import time

import pytest

from argos.server.errors import ApiError
from argos.server.jobs import JobCancelled, JobManager
from tests.server.conftest import AUTH, wait_for


class Recorder:
    """Collects published job events (kind, record)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.lock = threading.Lock()

    def __call__(self, kind: str, payload: dict) -> None:
        assert payload["type"] == "job"
        with self.lock:
            self.events.append((kind, payload["job"]))

    def states(self) -> list[str]:
        with self.lock:
            return [job["state"] for _, job in self.events]

    def last(self) -> dict:
        with self.lock:
            return self.events[-1][1]


def _wait_final(manager: JobManager, job_id: str) -> dict:
    return wait_for(
        lambda: (j := manager.get(job_id))["state"] in ("done", "failed", "cancelled") and j
    )


def test_lifecycle_progress_and_result():
    events = Recorder()
    manager = JobManager(events, min_interval_s=0.0)

    def body(ctx):
        ctx.progress(1, 2, "first", "one of two")
        ctx.progress(2, 2, "second")
        return {"answer": 42}

    record = manager.start("demo", body, total=2, stage="start")
    assert record["state"] == "running" and record["kind"] == "demo" and record["total"] == 2
    final = _wait_final(manager, record["id"])
    assert final["state"] == "done" and final["result"] == {"answer": 42}
    assert final["error"] is None and final["ended_utc"].endswith("Z")
    assert final["done"] == 2 and final["stage"] == "second" and final["message"] == "one of two"
    assert events.states() == ["running", "running", "running", "done"]
    kinds = {kind for kind, _ in events.events}
    assert kinds == {f"job:{record['id']}"}  # one compaction key per job
    seqs = [job["seq"] for _, job in events.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_failure_is_reported_with_code_and_message():
    manager = JobManager(Recorder())

    def body(ctx):
        raise ApiError(502, "connection_failed", "nothing answered")

    failed = _wait_final(manager, manager.start("demo", body)["id"])
    assert failed["state"] == "failed" and failed["result"] is None
    assert failed["error"] == {"code": "connection_failed", "message": "nothing answered"}

    def crash(ctx):
        raise RuntimeError("boom")

    crashed = _wait_final(manager, manager.start("demo", crash)["id"])
    assert crashed["error"] == {"code": "internal_error", "message": "boom"}


def test_cancel_is_honoured_at_a_safe_boundary():
    events = Recorder()
    manager = JobManager(events, min_interval_s=0.0)
    entered = threading.Event()

    def body(ctx):
        entered.set()
        for i in range(1000):
            ctx.sleep(0.01)  # wakes at once on cancel
            ctx.progress(i)

    job = manager.start("demo", body)
    entered.wait(2)
    started = time.monotonic()
    requested = manager.cancel(job["id"])
    assert requested["cancel_requested"] is True
    final = _wait_final(manager, job["id"])
    assert time.monotonic() - started < 0.5
    assert final["state"] == "cancelled" and final["result"] is None
    assert manager.cancel(job["id"])["state"] == "cancelled"  # idempotent once finished


def test_uncancellable_kind_and_unknown_job():
    manager = JobManager(Recorder())
    gate = threading.Event()
    job = manager.start("bundle", lambda ctx: gate.wait(2), cancellable=False)
    with pytest.raises(ApiError) as caught:
        manager.cancel(job["id"])
    assert (caught.value.status, caught.value.code) == (409, "unsupported")
    gate.set()
    with pytest.raises(ApiError) as missing:
        manager.get("nope")
    assert (missing.value.status, missing.value.code) == (404, "not_found")


def test_same_kind_and_resource_is_busy_with_owner():
    manager = JobManager(Recorder())
    gate = threading.Event()
    first = manager.start("discovery", lambda ctx: gate.wait(2))
    with pytest.raises(ApiError) as caught:
        manager.start("discovery", lambda ctx: None)
    assert caught.value.code == "busy" and caught.value.details == {"owner": first["id"]}
    other = manager.start("discovery", lambda ctx: None, resource="elsewhere")
    assert other["id"] != first["id"]
    gate.set()


def test_progress_is_throttled_to_four_per_second_and_the_final_state_always_sent():
    events = Recorder()
    manager = JobManager(events)  # default 0.25 s

    def body(ctx):
        deadline = time.monotonic() + 0.6
        i = 0
        while time.monotonic() < deadline:
            i += 1
            ctx.progress(i, None, "busy")
            time.sleep(0.001)
        return {"steps": i}

    job = manager.start("demo", body)
    final = _wait_final(manager, job["id"])
    assert final["result"]["steps"] > 100
    states = events.states()
    assert states[-1] == "done"
    running = len(states) - 1
    # 0.6 s of progress at <= 4 Hz: the start event plus at most 3-4 updates.
    assert 2 <= running <= 5, states
    with events.lock:
        published = [job["done"] for _, job in events.events]
    assert published[-1] == final["result"]["steps"]  # the final event is complete


def test_list_shows_active_then_recent_and_expires():
    manager = JobManager(Recorder(), keep_s=0.2, keep_listed=2)
    gate = threading.Event()
    active = manager.start("slow", lambda ctx: gate.wait(2))
    finished = [manager.start("quick", lambda ctx: None, resource=str(i))["id"] for i in range(3)]
    for job_id in finished:
        _wait_final(manager, job_id)
    listed = manager.list()
    assert listed[0]["id"] == active["id"]
    assert len(listed) == 3  # the active one + the last two finished
    time.sleep(0.3)
    with pytest.raises(ApiError):
        manager.get(finished[0])
    gate.set()
    manager.shutdown()


def test_shutdown_cancels_running_jobs():
    manager = JobManager(Recorder())

    def body(ctx):
        while True:
            ctx.sleep(0.05)

    job = manager.start("demo", body)
    manager.shutdown(timeout_s=2)
    assert manager.get(job["id"])["state"] == "cancelled"
    with pytest.raises(ApiError):
        manager.start("demo", lambda ctx: None)


def test_job_routes(client):
    hub = client.app.state.hub
    gate = threading.Event()

    def body(ctx):
        while not gate.is_set():
            ctx.sleep(0.02)
        raise JobCancelled()

    job = hub.jobs.start("demo", body)
    listed = client.get("/api/jobs", headers=AUTH).json()
    assert [j["id"] for j in listed["jobs"]] == [job["id"]]
    assert client.get(f"/api/jobs/{job['id']}", headers=AUTH).json()["state"] == "running"
    cancelled = client.delete(f"/api/jobs/{job['id']}", headers=AUTH)
    assert cancelled.status_code == 200 and cancelled.json()["cancel_requested"] is True
    wait_for(
        lambda: client.get(f"/api/jobs/{job['id']}", headers=AUTH).json()["state"] == "cancelled"
    )
    assert client.get("/api/jobs/unknown", headers=AUTH).status_code == 404
    assert client.delete("/api/jobs/unknown", headers=AUTH).status_code == 404
