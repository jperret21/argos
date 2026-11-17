"""The generic long-running job model (``web/spec/README.md`` §4.2, row A80).

A job is one-off work of seconds to minutes (discovery today; site search,
support bundle, session scans, file solves, re-runs and exports in later
waves). It runs on its own thread, never on the event loop, and reports
through one record:

- ``POST`` on the domain route starts it and answers ``202 {"job_id"}``;
  a second job of the same kind on the same resource is ``409 busy`` with
  ``owner`` = the running job's id;
- progress is published as ``{"type": "job", "job": {...}}`` events, at most
  every :data:`MIN_PUBLISH_INTERVAL_S` per job, the final state always;
- ``DELETE /api/jobs/{id}`` sets the job's cancel event; the job function
  honours it at a safe boundary by raising :class:`JobCancelled`
  (:meth:`JobContext.check`) and the job ends ``cancelled``;
- finished jobs are kept :data:`KEEP_S` seconds for ``GET /api/jobs/{id}``;
  ``GET /api/jobs`` lists the active ones and the last :data:`KEEP_LISTED`.

Events are published on the bus under the kind ``job:<id>``: the per-client
backlog compaction keeps the newest snapshot *per kind*, so each job keeps
its own latest state instead of one job's event replacing another's.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from argos.server.errors import ApiError
from argos.server.state import utc_iso

logger = logging.getLogger(__name__)

#: Shortest gap between two progress events of one job (≤ 4 Hz).
MIN_PUBLISH_INTERVAL_S = 0.25
#: How long a finished job stays readable.
KEEP_S = 600.0
#: Finished jobs listed by ``GET /api/jobs``.
KEEP_LISTED = 20
#: Hard cap on finished jobs held in memory.
_KEEP_MAX = 200

JOB_STATES = ("queued", "running", "done", "failed", "cancelled")
_FINAL = frozenset({"done", "failed", "cancelled"})

#: ``(bus kind, payload)``.
Publisher = Callable[[str, dict[str, Any]], None]


class JobCancelled(Exception):
    """Raised inside a job function to end it as ``cancelled``."""


@dataclass
class _Job:
    id: str
    kind: str
    resource: str | None
    cancellable: bool
    total: float | None
    stage: str | None
    started_utc: str
    state: str = "running"
    done: float = 0
    message: str | None = None
    ended_utc: str | None = None
    result: Any = None
    error: dict[str, str] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    seq: int = 0
    last_publish: float = 0.0
    dirty: bool = False
    timer: threading.Timer | None = None
    finished_at: float | None = None
    thread: threading.Thread | None = None

    def record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "done": self.done,
            "total": self.total,
            "stage": self.stage,
            "message": self.message,
            "started_utc": self.started_utc,
            "ended_utc": self.ended_utc,
            "result": self.result,
            "error": self.error,
            "cancellable": self.cancellable,
            "cancel_requested": self.cancel_event.is_set(),
            "seq": self.seq,
        }


class JobContext:
    """What a job function receives: progress reporting and the cancel flag."""

    def __init__(self, manager: "JobManager", job: _Job) -> None:
        self._manager = manager
        self._job = job

    @property
    def id(self) -> str:
        return self._job.id

    @property
    def cancel_event(self) -> threading.Event:
        return self._job.cancel_event

    @property
    def cancelled(self) -> bool:
        return self._job.cancel_event.is_set()

    def check(self) -> None:
        """Raise :class:`JobCancelled` if a cancel was requested (a safe boundary)."""
        if self._job.cancel_event.is_set():
            raise JobCancelled()

    def sleep(self, seconds: float) -> None:
        """Wait, waking at once on cancel (then raise :class:`JobCancelled`)."""
        if self._job.cancel_event.wait(max(0.0, seconds)):
            raise JobCancelled()

    def progress(
        self,
        done: float | None = None,
        total: float | None | Any = ...,
        stage: str | None | Any = ...,
        message: str | None | Any = ...,
    ) -> None:
        """Update the record; published within :data:`MIN_PUBLISH_INTERVAL_S`."""
        self._manager._progress(self._job, done, total, stage, message)


class JobManager:
    """Starts, tracks, publishes and cancels jobs; thread-safe."""

    def __init__(
        self,
        publish: Publisher | None = None,
        *,
        keep_s: float = KEEP_S,
        keep_listed: int = KEEP_LISTED,
        min_interval_s: float = MIN_PUBLISH_INTERVAL_S,
    ) -> None:
        self._publish_cb = publish
        self._keep_s = float(keep_s)
        self._keep_listed = int(keep_listed)
        self._interval = float(min_interval_s)
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._seq = 0
        self._closed = False

    # -- starting ----------------------------------------------------------------

    def start(
        self,
        kind: str,
        fn: Callable[[JobContext], Any],
        *,
        resource: str | None = None,
        cancellable: bool = True,
        total: float | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        """Run *fn* on a new thread; returns the job record (``409 busy`` if taken)."""
        with self._lock:
            if self._closed:
                raise ApiError(409, "busy", "The server is shutting down")
            for other in self._jobs.values():
                if other.kind == kind and other.resource == resource and other.state not in _FINAL:
                    raise ApiError(
                        409,
                        "busy",
                        f"A {kind} job is already running",
                        details={"owner": other.id},
                    )
            job = _Job(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                resource=resource,
                cancellable=cancellable,
                total=total,
                stage=stage,
                started_utc=utc_iso(),
            )
            self._jobs[job.id] = job
            self._prune()
            thread = threading.Thread(
                target=self._run, args=(job, fn), name=f"argos-job-{kind}", daemon=True
            )
            job.thread = thread
            self._publish_now(job)
            record = job.record()
        thread.start()
        return record

    def _run(self, job: _Job, fn: Callable[[JobContext], Any]) -> None:
        ctx = JobContext(self, job)
        state, result, error = "done", None, None
        try:
            result = fn(ctx)
        except JobCancelled:
            state = "cancelled"
        except ApiError as exc:
            state, error = "failed", {"code": exc.code, "message": exc.message}
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job.id, job.kind)
            state = "failed"
            error = {"code": "internal_error", "message": str(exc) or exc.__class__.__name__}
        with self._lock:
            job.state = state
            job.result = result if state == "done" else None
            job.error = error
            job.ended_utc = utc_iso()
            job.finished_at = time.monotonic()
            if job.timer is not None:
                job.timer.cancel()
                job.timer = None
            self._publish_now(job)

    # -- progress ----------------------------------------------------------------

    def _progress(self, job: _Job, done, total, stage, message) -> None:
        with self._lock:
            if job.state in _FINAL:
                return
            if done is not None:
                job.done = done
            if total is not ...:
                job.total = total
            if stage is not ...:
                job.stage = stage
            if message is not ...:
                job.message = message
            job.dirty = True
            wait = self._interval - (time.monotonic() - job.last_publish)
            if wait <= 0:
                self._publish_now(job)
            elif job.timer is None:
                timer = threading.Timer(wait, self._flush, args=(job,))
                timer.daemon = True
                job.timer = timer
                timer.start()

    def _flush(self, job: _Job) -> None:
        with self._lock:
            job.timer = None
            if job.dirty and job.state not in _FINAL:
                self._publish_now(job)

    def _publish_now(self, job: _Job) -> None:
        """Publish *job* (lock held, so events leave in the order of the changes)."""
        self._seq += 1
        job.seq = self._seq
        job.dirty = False
        job.last_publish = time.monotonic()
        if self._publish_cb is not None:
            try:
                self._publish_cb(f"job:{job.id}", {"type": "job", "job": job.record()})
            except Exception:
                logger.exception("Publishing job %s failed", job.id)

    # -- queries and cancel --------------------------------------------------------

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
            if job is None:
                raise ApiError(404, "not_found", f"No job {job_id!r} (finished jobs expire)")
            return job.record()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune()
            active = [j for j in self._jobs.values() if j.state not in _FINAL]
            finished = sorted(
                (j for j in self._jobs.values() if j.state in _FINAL),
                key=lambda j: j.finished_at or 0.0,
                reverse=True,
            )[: self._keep_listed]
            active.sort(key=lambda j: j.started_utc)
            return [j.record() for j in (*active, *finished)]

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ApiError(404, "not_found", f"No job {job_id!r} (finished jobs expire)")
            if job.state in _FINAL:
                return job.record()
            if not job.cancellable:
                raise ApiError(409, "unsupported", f"A {job.kind} job cannot be cancelled")
            if not job.cancel_event.is_set():
                job.cancel_event.set()
                self._publish_now(job)
            return job.record()

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.state not in _FINAL)

    def shutdown(self, timeout_s: float = 3.0) -> None:
        """Cancel every running job and wait for them (bounded)."""
        with self._lock:
            self._closed = True
            running = [j for j in self._jobs.values() if j.state not in _FINAL]
            for job in running:
                job.cancel_event.set()
        deadline = time.monotonic() + timeout_s
        for job in running:
            if job.thread is not None:
                job.thread.join(max(0.0, deadline - time.monotonic()))

    def _prune(self) -> None:
        now = time.monotonic()
        finished = [j for j in self._jobs.values() if j.finished_at is not None]
        for job in finished:
            if now - job.finished_at > self._keep_s:
                del self._jobs[job.id]
        finished = sorted(
            (j for j in self._jobs.values() if j.finished_at is not None),
            key=lambda j: j.finished_at,
        )
        for job in finished[: max(0, len(finished) - _KEEP_MAX)]:
            del self._jobs[job.id]
