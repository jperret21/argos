"""Sequences (wave 6a, rows A62-A64): run a plan, the mount interlock, the preflight.

A Qt-free port of the **fixed** (release 0.5.0) Qt sequence path:

- ``AcquisitionEngine.start_sequence`` / ``stop_sequence`` / ``pause_sequence``
  / ``resume_sequence_run`` / ``_on_seq_frame_saved`` /
  ``_on_seq_autofocus_due`` / ``_on_seq_finished`` /
  ``_run_on_complete_action`` / ``_sequence_frame_context``
  (``argos/core/session/acquisition_engine.py:712-945``);
- ``SequenceWorker._run`` / ``_set_filter`` / ``_read_back_filter`` /
  ``_shoot_one`` / ``_append_session`` / ``_write_observation_metadata`` /
  ``_dither`` / ``_await_autofocus`` (``argos/workers/sequence_worker.py:162-503``);
- the readiness line of ``sequence_panel.py:1125-1141``, grown into the
  preflight of ``web/lab/PROPOSAL.md`` §7.

The core does the science unchanged: ``expand_plan`` and ``total_frames``
(``sequencer.py``), ``FITSWriter`` (folders, names, headers), ``SessionLog``,
``TargetSet``. The run has its own thread; the FITS of a sub is written on
it (as the Qt worker does), never on the event loop; each photometry point
is measured on the photometry thread (``PhotometryService.measure_saved_frame``).

State lives under the hub lock, as every service's; nothing here holds it
across device I/O, a thread join or a file write.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import statistics
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from argos import SOFTWARE_ID
from argos.core.catalog.targets import ROLE_TARGET
from argos.core.config import observing_site
from argos.core.imaging.fits_writer import FITSWriter, FrameContext
from argos.core.imaging.metrics import detect_stars, frame_metrics
from argos.core.imaging.sequencer import (
    DARK_FILTER_NAME,
    FRAME_TYPES,
    ON_COMPLETE_CHOICES,
    FrameSpec,
    SequencePlan,
    estimated_duration_s,
    expand_plan,
    plan_to_dict,
    total_frames,
)
from argos.core.imaging.session_log import SESSION_FILENAME, FrameRecord, SessionLog
from argos.core.imaging.sky_geometry import horizontal_at
from argos.core.photometry.airmass import julian_date
from argos.server.capture import FrameSettings, wheel_filter_name
from argos.server.devices.base import DeviceError, ExposureCancelled
from argos.server.errors import ApiError
from argos.server.frames import encode_frame
from argos.server.photometry import MeasureRequest
from argos.server.state import CAMERA_BUSY, utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

OBSERVATION_FILENAME = "observation.json"  # sequence_worker.py:42

#: Every state but ``idle`` is an active run (the plan is locked, Q-P9).
STATES = ("idle", "waiting", "running", "pausing", "paused", "autofocus", "stopping")
ACTIVE = frozenset(STATES[1:])
#: States in which a mount motion would move the field under an exposure (D2).
MOTION_LOCKED = frozenset({"running", "pausing", "autofocus", "stopping"})
#: The four aperture-geometry settings locked during a run (S15).
GEOMETRY_KEYS = (
    "photometry.aperture_fwhm_mult",
    "photometry.aperture_min_px",
    "photometry.annulus_in_px",
    "photometry.annulus_out_px",
)

#: sequence_worker.py:47 — the longest wait for the wheel to settle.
FILTER_SETTLE_S = 20.0
#: sequence_worker.py:52-57 — dither pulse and settle.
DITHER_RATE_DEG_S = 0.05
DITHER_PULSE_S = 1.0
DITHER_SETTLE_S = 3.0
#: sequencer.py:178 — per-frame overhead of the estimate (planned cadence).
FRAME_OVERHEAD_S = 3.0
#: A scheduled start waits at most this long for an autofocus to release the camera.
START_AF_WAIT_S = 300.0
#: A start time further ahead is refused (no silent clamp).
START_AHEAD_MAX_S = 24 * 3600.0
#: Before an exposure the run waits this long at most for a slew to end, then pauses.
SLEW_WAIT_MAX_S = 300.0
#: Joining the run thread at shutdown.
SHUTDOWN_JOIN_S = 15.0
#: FITS header and padding of one sub (6 blocks of 2880 bytes, generous).
HEADER_BYTES = 17_280
#: Altitude limit when the site has none (Q-P6).
DEFAULT_MIN_ALT_DEG = 30.0
#: Subs whose start-to-start intervals make the observed cadence.
CADENCE_WINDOW = 10

ClockFn = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(text: Any) -> datetime:
    """An ISO 8601 time **with** a zone, as an aware UTC datetime; ``ValueError`` else."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("expected an ISO 8601 UTC time")
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("the time needs a zone (end it with Z for UTC)")
    return value.astimezone(timezone.utc)


def _hhmm(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%H:%M UTC")


def _day_hhmm(when: datetime) -> str:
    """A start on another day says which (it read "21:30 UTC" for a start 3 days ahead)."""
    w = when.astimezone(timezone.utc)
    return f"{w.day} {w.strftime('%b %H:%M')} UTC"


def wire_plan(plan: SequencePlan) -> dict[str, Any]:
    """The schema-2 record of a plan (``plan_to_dict`` plus ``schema``)."""
    return {"schema": 2, **plan_to_dict(plan)}


def observation_payload(plan: SequencePlan) -> dict[str, Any] | None:
    """``SequenceWorker._write_observation_metadata`` (sequence_worker.py:462-480)."""
    if not plan.metadata:
        return None
    return {"schema_version": 1, "object_name": plan.object_name, **plan.metadata}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class _RunEnded(Exception):
    """Ends a run with a reason (camera, wheel, save, autofocus)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class _Run:
    """One run, from the start request to its outcome."""

    plan: SequencePlan
    base_dir: Path
    start_at: datetime | None
    frames_total: int
    #: Stop: aborts the exposure in progress (it is also the camera's cancel).
    stop: threading.Event = field(default_factory=threading.Event)
    #: Pause gate: set = run, cleared = hold before the next exposure.
    gate: threading.Event = field(default_factory=threading.Event)
    #: Wakes a cadence / interval wait (pause or stop).
    wake: threading.Event = field(default_factory=threading.Event)
    #: Set by the autofocus end callback.
    af_done: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    run_id: str | None = None
    run_root: Path | None = None
    started_utc: str | None = None
    #: Why the run was stopped from outside (stopped, cancelled, device_lost, shutdown).
    stop_reason: str | None = None
    stop_message: str | None = None
    paused_by: str | None = None
    #: The sub being exposed (state "pausing" until it is saved).
    busy_frame: bool = False
    exposure_started_mono: float | None = None
    current: dict[str, Any] | None = None
    step_index: int | None = None
    pass_index: int | None = None
    frames_done: int = 0
    frames_saved: int = 0
    #: Run time spent exposing (monotonic), pauses and autofocus taken out (ETA).
    active_s: float = 0.0
    segment_start: float | None = None
    eta_s: float | None = None
    last_frame_utc: str | None = None
    last_saved_utc: str | None = None
    last_frame_name: str | None = None
    #: DATE-OBS of the current step's subs since its last break (observed cadence).
    starts: list[datetime] = field(default_factory=list)
    frames_since_af: int = 0
    autofocus_runs: int = 0
    session_log: SessionLog | None = None
    session_root: Path | None = None
    targets_written: bool = False
    af_skip_logged: bool = False
    dark_skip_logged: bool = False
    dither_sign: int = 1
    camera_generation: int = -1
    #: Wave 6b: (DATE-OBS → save duration, exposure) of each Light sub (wrap-up overhead).
    costs: list[tuple[float, float]] = field(default_factory=list)
    #: Wave 6b: subs saved per frame type (wrap-up).
    by_type: dict[str, int] = field(default_factory=dict)
    #: Wave 6b: the run's mid-run autofocus passes (record ``autofocus_passes``).
    af_passes: list[dict[str, Any]] = field(default_factory=list)


class SequenceService:
    """The sequence engine: one run at a time, its record, the interlock."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._state = "idle"
        self._run: _Run | None = None
        self._last_result: dict[str, Any] | None = None
        self._revision = 0
        # -- wave 6b: the wrap-up, the last run's autofocus passes, keep-awake --------
        self._wrapup: dict[str, Any] | None = None
        self._last_plan: SequencePlan | None = None
        self._last_passes: list[dict[str, Any]] = []
        self._awake = False
        #: How long the end waits for the last sub's photometry (s); shutdown: 2 s.
        self.photometry_wait_s = 10.0
        self._record: dict[str, Any] = self._build_record()
        #: The clock of DATE-OBS / DATE-AVG and the run id (tests: a scripted one).
        self.clock: ClockFn = _utcnow
        #: Tests without the plan half: a callable returning a core SequencePlan.
        self.plan_provider: Callable[[], SequencePlan] | None = None
        self._closed = False
        #: A start is being prepared (camera taken, plan checked): one at a time, so
        #: two clients pressing Start never share the camera (hub lock).
        self._starting = False
        hub.bus.add_tap(self._on_event)

    # ------------------------------------------------------------------
    # State and records
    # ------------------------------------------------------------------

    @property
    def active(self) -> bool:
        with self._hub._lock:
            return self._state in ACTIVE

    def run_active(self) -> bool:
        """The plan half's question (protocol.md "In-process interface")."""
        return self.active

    def motion_locked(self) -> bool:
        with self._hub._lock:
            return self._state in MOTION_LOCKED

    def holds_camera(self) -> bool:
        """Lock held: a run owns the camera (it hands it to a mid-run autofocus)."""
        return self._run is not None and self._state in (
            "running",
            "pausing",
            "paused",
            "autofocus",
            "stopping",
        )

    def run_root(self) -> Path | None:
        with self._hub._lock:
            run = self._run
            return run.run_root if run is not None and run.run_id is not None else None

    def summary(self) -> dict[str, Any]:
        """Lock held: the status record's ``sequence`` member."""
        return {
            "state": self._state,
            "active": self._state in ACTIVE,
            "run_id": self._record.get("run_id"),
            "object_name": self._record.get("object_name"),
        }

    def record(self) -> dict[str, Any]:
        with self._hub._lock:
            return dict(self._record)

    def snapshots(self, seq: int) -> list[tuple[str, int, dict[str, Any]]]:
        """Lock held: the ``sequence`` snapshot a new client receives."""
        return [("sequence", seq, {"type": "sequence", **self._record})]

    def _planned_cadence(self, run: _Run) -> float | None:
        if run.step_index is None:
            return None
        step = run.plan.steps[run.step_index]
        if step.cadence_s is not None:
            return float(step.cadence_s)
        return float(step.exposure_s) + float(step.interval_s) + FRAME_OVERHEAD_S

    @staticmethod
    def _observed_cadence(run: _Run) -> float | None:
        starts = run.starts[-(CADENCE_WINDOW + 1) :]
        if len(starts) < 2:
            return None
        gaps = [(b - a).total_seconds() for a, b in zip(starts, starts[1:])]
        return float(statistics.median(gaps))

    def _next_autofocus(self, run: _Run) -> dict[str, Any] | None:
        every = int(run.plan.autofocus_every_n or 0)
        if every <= 0:
            return None
        return {"reason": "every_n", "in_frames": max(0, every - run.frames_since_af)}

    def _build_record(self) -> dict[str, Any]:
        run = self._run
        state = self._state
        now = _utcnow()
        if run is None:
            return {
                "state": state,
                "active": state in ACTIVE,
                "run_id": None,
                "run_root": None,
                "object_name": None,
                "plan": None,
                "start_at_utc": None,
                "started_utc": None,
                "step_index": None,
                "step": None,
                "pass_index": None,
                "repeat": None,
                "frames_done": 0,
                "frames_total": 0,
                "eta_s": None,
                "end_utc": None,
                "current": None,
                "last_frame_utc": None,
                "last_saved_utc": None,
                "last_frame_name": None,
                "cadence_s": None,
                "observed_cadence_s": None,
                "next_autofocus": None,
                "autofocus_runs": 0,
                "paused_by": None,
                "end_action": "Nothing",
                "last_result": self._last_result,
                "autofocus": None,
                "autofocus_passes": [dict(p) for p in self._last_passes],
                "wrapup": self._wrapup,
                "revision": self._revision,
            }
        plan = run.plan
        eta = run.eta_s
        if state == "waiting" and run.start_at is not None:
            end = run.start_at + timedelta(seconds=estimated_duration_s(plan))
        elif eta is not None and state in ("running", "autofocus", "pausing"):
            end = now + timedelta(seconds=eta)
        else:
            end = None
        step = plan.steps[run.step_index] if run.step_index is not None else None
        return {
            "state": state,
            "active": state in ACTIVE,
            "run_id": run.run_id,
            "run_root": str(run.run_root) if run.run_root is not None else None,
            "object_name": plan.object_name,
            "plan": wire_plan(plan),
            "start_at_utc": utc_iso(run.start_at) if run.start_at is not None else None,
            "started_utc": run.started_utc,
            "step_index": run.step_index,
            "step": wire_plan(SequencePlan(steps=[step]))["steps"][0] if step else None,
            "pass_index": run.pass_index,
            "repeat": max(1, int(plan.repeat or 1)),
            "frames_done": run.frames_done,
            "frames_total": run.frames_total,
            "eta_s": eta,
            "end_utc": utc_iso(end) if end is not None else None,
            "current": dict(run.current) if run.current else None,
            "last_frame_utc": run.last_frame_utc,
            "last_saved_utc": run.last_saved_utc,
            "last_frame_name": run.last_frame_name,
            "cadence_s": self._planned_cadence(run),
            "observed_cadence_s": self._observed_cadence(run),
            "next_autofocus": self._next_autofocus(run),
            "autofocus_runs": run.autofocus_runs,
            # In "autofocus", a pause asked meanwhile is pending (it holds after the AF).
            "paused_by": run.paused_by if state in ("pausing", "paused", "autofocus") else None,
            "end_action": plan.on_complete,
            "last_result": self._last_result,
            "autofocus": self._af_progress() if state == "autofocus" else None,
            "autofocus_passes": [dict(p) for p in run.af_passes],
            "wrapup": None,
            "revision": self._revision,
        }

    def _af_progress(self) -> dict[str, Any] | None:
        """Lock held: the mid-run sweep in progress (the run strip's ``afStep``)."""
        record = self._hub._autofocus_record()
        if record.get("state") not in ("running", "stopping"):
            return None
        return {
            "started_utc": record.get("started_utc"),
            "stage": record.get("stage"),
            "step": int(record.get("step") or 0),
            "total": int(record.get("total") or 0),
            "position": record.get("position"),
        }

    def _on_event(self, kind: str, payload: dict[str, Any]) -> None:
        """Bus tap: a mid-run autofocus sample re-sends the record (sweep progress).

        Autofocus records are published under the hub lock (``AutofocusRun._update``),
        so re-publishing here takes no new lock.
        """
        if kind != "autofocus" or self._state != "autofocus":
            return
        with self._hub._lock:
            if self._state == "autofocus" and self._run is not None:
                self._publish()

    def _publish(self, *, status: bool = False) -> dict[str, Any]:
        """Lock held: a new revision of the record, on the ``sequence`` event."""
        self._revision += 1
        self._record = self._build_record()
        self._hub._publish("sequence", dict(self._record))
        active = self._state in ACTIVE
        if active != self._awake:
            # Wave 6b: the OS sleep assertion follows the run (want() never blocks).
            self._awake = active
            keep = getattr(self._hub, "keep_awake", None)
            if keep is not None:
                name = self._record.get("object_name") or "Unknown"
                keep.want(f"A sequence is running ({name})." if active else None)
        if status:
            self._hub._publish_status()
        return dict(self._record)

    def _set_state(self, state: str) -> dict[str, Any]:
        """Lock held."""
        changed = state != self._state
        self._state = state
        return self._publish(status=changed)

    def _log(self, level: str, message: str) -> None:
        self._hub.log(level, message, source="sequence", topic="sequence")  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # The plan
    # ------------------------------------------------------------------

    def _plan_for_run(self) -> SequencePlan:
        """The draft as a core plan: the plan half's (``hub.plan.plan_for_run``)."""
        if self.plan_provider is not None:
            return self.plan_provider()
        service = getattr(self._hub, "plan", None)
        if service is None or not hasattr(service, "plan_for_run"):
            raise ApiError(409, "not_ready", "The plan service is not available.")
        return service.plan_for_run()

    def _draft_start_at(self) -> str | None:
        """The draft's ``start_at_utc`` (Q-P2), when the plan half keeps one."""
        service = getattr(self._hub, "plan", None)
        getter = getattr(service, "draft_start_at", None)
        if getter is not None:
            return getter()
        record = getattr(service, "record", None)
        if record is not None:
            try:
                value = record()
            except Exception:  # the draft is the plan half's; never fail a start on it
                return None
            plan = value.get("plan") if isinstance(value, dict) else None
            if isinstance(plan, dict):
                return plan.get("start_at_utc")
        return None

    def _plan_publish(self) -> None:
        service = getattr(self._hub, "plan", None)
        publish = getattr(service, "publish", None)
        if publish is not None:
            try:
                publish()
            except Exception:
                logger.warning("Plan publish failed", exc_info=True)

    def plan_issues(self, plan: SequencePlan) -> list[dict[str, Any]]:
        """The engine's own checks: what the run relies on (never clamped, S7)."""
        hub = self._hub
        issues: list[dict[str, Any]] = []

        def add(step: int | None, fld: str, code: str, message: str) -> None:
            issues.append(
                {"step": step, "field": fld, "code": code, "level": "error", "message": message}
            )

        with hub._lock:
            limits = hub._camera_limits
            wheel_on = hub.wheel.connected
            slots = list(hub.wheel.record().get("slots") or []) if wheel_on else []
            binning = hub._capture_settings.binning
        runnable = [s for s in plan.steps if s.enabled and int(s.count or 0) > 0]
        if not runnable:
            add(None, "steps", "no_enabled_step", "Add an enabled step with a count.")
        if plan.on_complete not in ON_COMPLETE_CHOICES:
            add(
                None,
                "on_complete",
                "unknown_on_complete",
                f"Unknown end action '{plan.on_complete}'.",
            )
        if binning != 1:
            add(
                None,
                "binning",
                "binning",
                f"Binning is {binning}×{binning}: sequences save unbinned frames only "
                "(FITS XBINNING and pixel size assume 1×1). Set Binning to 1.",
            )
        dark = DARK_FILTER_NAME.lower()
        for i, step in enumerate(plan.steps):
            if not step.enabled or int(step.count or 0) <= 0:
                continue
            n = i + 1
            if step.frame_type not in FRAME_TYPES:
                add(i, "frame_type", "unknown_frame_type", f"Step {n}: unknown frame type.")
                continue
            exposure = float(step.exposure_s)
            if not math.isfinite(exposure) or exposure <= 0:
                add(i, "exposure_s", "out_of_range", f"Step {n}: exposure must be positive.")
            elif limits is not None and not (
                limits.exposure_min_s <= exposure <= limits.exposure_max_s
            ):
                add(
                    i,
                    "exposure_s",
                    "out_of_range",
                    f"Step {n}: exposure {exposure:g} s is outside the camera's "
                    f"{limits.exposure_min_s:g}–{limits.exposure_max_s:g} s.",
                )
            if limits is not None and not (limits.gain_min <= int(step.gain) <= limits.gain_max):
                add(
                    i,
                    "gain",
                    "out_of_range",
                    f"Step {n}: gain {step.gain} is outside the camera's "
                    f"{limits.gain_min}–{limits.gain_max}.",
                )
            if step.cadence_s is not None and float(step.cadence_s) < exposure:
                add(
                    i,
                    "cadence_s",
                    "cadence_short",
                    f"Step {n}: cadence {float(step.cadence_s):g} s is shorter than the "
                    f"{exposure:g} s exposure.",
                )
            if step.frame_type in ("Light", "Flat"):
                name = str(step.filter_name or "").strip()
                if name.lower() == dark and (not wheel_on or dark in [s.lower() for s in slots]):
                    add(
                        i,
                        "filter_name",
                        "dark_slot",
                        f"Step {n} is a {step.frame_type} step on the opaque '{name}' slot: "
                        "its frames would be black. Choose a filter that passes light.",
                    )
                elif wheel_on and name.lower() not in [s.lower() for s in slots]:
                    add(
                        i,
                        "filter_name",
                        "unknown_filter",
                        f"Step {n}: the wheel has no '{name}' slot "
                        f"(slots: {', '.join(slots) or 'none'}).",
                    )
        return issues

    # ------------------------------------------------------------------
    # Start (A62)
    # ------------------------------------------------------------------

    def start(self, start_at_utc: str | None = None, *, given: bool = False) -> dict[str, Any]:
        """``POST /api/sequence/start``. *given*: the body had a ``start_at_utc`` member."""
        hub = self._hub
        with hub._lock:
            if self._closed:
                raise ApiError(409, "busy", "The server is shutting down.")
            if self._state in ACTIVE or self._starting:
                raise ApiError(
                    409, "busy", "A sequence is already running.", details={"owner": "sequence"}
                )
            self._starting = True
        try:
            return self._start(start_at_utc, given)
        finally:
            with hub._lock:
                self._starting = False

    def _start(self, start_at_utc: str | None, given: bool) -> dict[str, Any]:
        """``start`` once this call holds the start reservation."""
        hub = self._hub
        self._check_camera()
        text = start_at_utc if given else self._draft_start_at()
        start_at = self._start_time(text)
        plan = self._plan_for_run()
        issues = self.plan_issues(plan)
        if issues:
            raise ApiError(
                400, "invalid_argument", issues[0]["message"], details={"issues": issues}
            )
        base_dir = Path(plan.base_dir) if plan.base_dir is not None else hub._sessions_root()
        blocks = [
            c
            for c in (self._check_output(base_dir), self._check_disk(plan, base_dir)[0])
            if c["level"] == "block"
        ]
        if blocks:
            raise ApiError(
                409, "preflight_blocked", blocks[0]["message"], details={"checks": blocks}
            )
        run = _Run(
            plan=plan,
            base_dir=base_dir,
            start_at=start_at,
            frames_total=total_frames(plan),
        )
        run.gate.set()
        if start_at is None:
            self._acquire_camera(run)  # 409s reach the client
        with hub._lock:
            if self._state in ACTIVE or self._closed:
                if start_at is None:
                    self._release_camera()
                raise ApiError(
                    409, "busy", "A sequence is already running.", details={"owner": "sequence"}
                )
            self._run = run
            self._last_result = None
            self._wrapup = None
            self._last_passes = []
            self._state = "waiting" if start_at is not None else "running"
            run.thread = threading.Thread(
                target=self._thread_main, args=(run,), name="argos-sequence", daemon=True
            )
            self._publish(status=True)
        try:
            self._lock_observation(plan)
            self._plan_publish()
            if start_at is not None:
                self._log(
                    "cmd",
                    f"Sequence scheduled — {run.frames_total} frame(s), starts at "
                    f"{_hhmm(start_at)}.",
                )
            else:
                self._begin(run)
            run.thread.start()
        except Exception as exc:
            # Never leave a registered run without its thread: the engine would stay
            # "running" with the camera owned until a restart.
            logger.exception("Sequence start failed")
            text = exc.message if isinstance(exc, ApiError) else str(exc) or type(exc).__name__
            self._finish(run, False, "refused", f"The sequence could not start: {text}")
            if isinstance(exc, ApiError):
                raise
            raise ApiError(500, "internal_error", f"The sequence could not start: {text}") from exc
        with hub._lock:
            return dict(self._record)

    def _start_time(self, text: str | None) -> datetime | None:
        if text is None:
            return None
        try:
            when = parse_utc(text)
        except ValueError as exc:
            raise ApiError(400, "invalid_argument", f"start_at_utc: {exc}") from exc
        now = self.clock()
        if (when - now).total_seconds() > START_AHEAD_MAX_S:
            raise ApiError(
                400,
                "invalid_argument",
                f"The start time {_day_hhmm(when)} is more than 24 h ahead.",
            )
        if when <= now:
            return None  # already passed: the plan's start_in_past warning, start now
        return when

    def _check_camera(self) -> None:
        hub = self._hub
        with hub._lock:
            if hub._slots["camera"].state != "connected" or hub._camera is None:
                raise ApiError(
                    409, "not_connected", "Connect the camera before running a sequence."
                )
            if hub._camera_state.owner == "autofocus" or hub._autofocus is not None:
                raise ApiError(
                    409,
                    "busy",
                    "Autofocus is running — it owns the camera. Wait for it to finish.",
                    details={"owner": "autofocus"},
                )

    def _acquire_camera(self, run: _Run) -> None:
        """``camera_service.acquire(SEQUENCE)``: live view and Take shot are pre-empted."""
        hub = self._hub
        self._check_camera()
        with hub._lock:
            owner = hub._camera_state.owner
            preempt = owner in ("live", "single") or hub._job is not None
        if preempt:
            hub._stop_job(join_s=2.0)
            self._log("info", "Live preview stopped — the sequence owns the camera.")
        with hub._lock:
            if hub._slots["camera"].state != "connected" or hub._camera is None:
                raise ApiError(
                    409, "not_connected", "Connect the camera before running a sequence."
                )
            if hub._job is not None:
                raise ApiError(409, "busy", "Camera is still stopping — try again in a moment")
            if hub._autofocus is not None:
                raise ApiError(
                    409,
                    "busy",
                    "Autofocus is running — it owns the camera. Wait for it to finish.",
                    details={"owner": "autofocus"},
                )
            hub._save = None
            changes: dict[str, Any] = {
                "owner": "sequence",
                "current": None,
                "save_pending": 0,
                "waiting_for": None,
            }
            if hub._camera_state.state in CAMERA_BUSY or hub._camera_state.state == "error":
                changes["state"] = "idle"
            hub._refresh_camera(**changes)
            run.camera_generation = hub._slots["camera"].generation
        hub.focuser.lock("sequence")

    def _release_camera(self) -> None:
        """Lock held (``_on_seq_finished``: release SEQUENCE)."""
        hub = self._hub
        if hub._camera_state.owner == "sequence":
            changes: dict[str, Any] = {"owner": "idle", "current": None}
            if hub._camera_state.state in CAMERA_BUSY:
                changes["state"] = "idle"
            hub._refresh_camera(**changes)

    def _lock_observation(self, plan: SequencePlan) -> None:
        """Q-P1: the run's object is Observe's; locked until the run ends."""
        hub = self._hub
        name = " ".join(str(plan.object_name or "").split())
        if name and name != hub.observation.object_name:
            try:
                hub.observation.set_name(name)
                self._log("info", f"Observe object → {name} (the plan's object).")
            except ApiError as exc:
                self._log("warning", f"Observe object not changed: {exc.message}")
        hub.observation.set_locked(f"A sequence is running ({name or 'Unknown'}).")

    def _begin(self, run: _Run) -> None:
        """The run really starts: run id, photometry reset, identification armed."""
        hub = self._hub
        now = self.clock()
        run_id = now.strftime("%Y%m%dT%H%M%SZ")
        base, n = run_id, 1
        while FITSWriter.session_root(
            run.base_dir, run.plan.object_name, now, run_id=run_id
        ).exists():
            n += 1
            run_id = f"{base}-{n}"
        with hub._lock:
            run.run_id = run_id
            run.run_root = FITSWriter.session_root(
                run.base_dir, run.plan.object_name, now, run_id=run_id
            )
            run.started_utc = utc_iso(now)
            run.segment_start = time.monotonic()
            run.eta_s = estimated_duration_s(run.plan)
            self._publish(status=True)
        hub.jog.stop_all_before("Sequence")  # a jog left running while waiting
        # clear_lightcurves (start_sequence); the recorder and series FWHM restart
        # with the run (_on_seq_frame_saved at its first save).
        hub.photometry.begin_run()
        lights = any(
            s.enabled and int(s.count or 0) > 0 and s.frame_type == "Light" for s in run.plan.steps
        )
        if lights:
            self._arm_identification()
        self._log("cmd", f"Sequence started — {run.frames_total} frame(s).")

    def _arm_identification(self) -> None:
        """S14 (``imaging_page._on_sequence_running``, 2606-2631)."""
        hub = self._hub
        from argos.core.imaging.platesolve import find_astap

        configured = str(hub.config.get("astrometry.astap_path", "") or "")
        if find_astap(str(Path(configured).expanduser()) if configured else "") is None:
            self._log(
                "warning",
                "Sequence: ASTAP not found — the field cannot be identified, so no live "
                "photometry will be measured.",
            )
            return
        hub.field.arm_for_sequence()

    # ------------------------------------------------------------------
    # Pause, resume, stop (A62)
    # ------------------------------------------------------------------

    def pause(self, *, by: str = "observer") -> dict[str, Any]:
        hub = self._hub
        with hub._lock:
            run, state = self._run, self._state
            if run is None or state == "idle":
                raise ApiError(409, "not_running", "No sequence is running.")
            if state == "waiting":
                raise ApiError(
                    409, "not_running", "The sequence has not started yet — Stop cancels it."
                )
            if state in ("pausing", "paused", "stopping"):
                return dict(self._record)
            run.gate.clear()
            run.paused_by = by
            run.wake.set()
            step = run.plan.steps[run.step_index] if run.step_index is not None else None
            if state == "running":
                self._state = "pausing"
            record = self._publish(status=True)
        if by == "observer":
            self._log("cmd", "Pausing after the current frame…")
        else:
            self._log(
                "cmd", "Pausing the run for a mount motion (the frame in progress completes)…"
            )
        if step is not None and step.cadence_s is not None:
            self._log(
                "warning",
                f"Pausing breaks the {float(step.cadence_s):g} s cadence of step "
                f"{run.step_index + 1}.",
            )
        return record

    def resume(self) -> dict[str, Any]:
        hub = self._hub
        with hub._lock:
            run, state = self._run, self._state
            if run is None or state == "idle":
                raise ApiError(409, "not_running", "No sequence is running.")
            if state == "waiting":
                raise ApiError(
                    409, "not_running", "The sequence has not started yet — Stop cancels it."
                )
            if state == "autofocus" and not run.gate.is_set():
                # A pause asked during a mid-run autofocus is still pending: cancel it.
                run.paused_by = None
                run.gate.set()
                record = self._publish(status=True)
                cancelled = True
            elif state not in ("pausing", "paused"):
                return dict(self._record)
            else:
                run.paused_by = None
                run.gate.set()
                self._state = "running"
                record = self._publish(status=True)
                cancelled = False
        if cancelled:
            self._log("cmd", "Pause cancelled: the run goes on after the autofocus.")
            return record
        hub.jog.stop_all_before("Resume")  # never expose while a jog moves the field
        self._log("cmd", "Sequence resumed.")
        return record

    def stop(self, reason: str = "stopped", message: str | None = None) -> dict[str, Any]:
        hub = self._hub
        with hub._lock:
            run, state = self._run, self._state
            if run is None or state == "idle":
                return dict(self._record)
            if run.stop_reason is None:
                if state == "waiting" and reason == "stopped":
                    reason = "cancelled"
                run.stop_reason = reason
                run.stop_message = message
            run.stop.set()
            run.gate.set()
            run.wake.set()
            af = hub._autofocus if state == "autofocus" else None
            if state != "waiting":
                self._state = "stopping"
            record = self._publish(status=True)
        if reason == "stopped" and state != "waiting":
            self._log("info", "Stopping sequence…")
        if af is not None:
            hub.stop_autofocus()  # the focuser returns to its start (S23)
        return record

    # ------------------------------------------------------------------
    # The run thread (SequenceWorker.run / _run)
    # ------------------------------------------------------------------

    def _thread_main(self, run: _Run) -> None:
        completed = False
        reason, message = "completed", "Sequence complete."
        try:
            if run.start_at is not None:
                self._wait_for_start(run)
                if run.stop.is_set():
                    raise _RunEnded(
                        run.stop_reason or "cancelled", "Cancelled before the start time."
                    )
            completed = self._loop(run)
            if not completed:
                reason = run.stop_reason or "stopped"
                message = run.stop_message or "Stopped by the observer."
        except _RunEnded as end:
            reason, message = end.reason, end.message
        except Exception as exc:  # pragma: no cover - a safety net, as the Qt worker's
            logger.exception("Sequence error")
            reason, message = "camera_error", str(exc) or type(exc).__name__
        finally:
            self._finish(run, completed, reason, message)

    def _wait_for_start(self, run: _Run) -> None:
        """Q-P2: the server waits (cancellable, whatever the clients do)."""
        while not run.stop.is_set():
            left = (run.start_at - self.clock()).total_seconds()
            if left <= 0:
                break
            run.stop.wait(min(left, 0.5))
        if run.stop.is_set():
            return
        deadline = time.monotonic() + START_AF_WAIT_S
        told = False
        while True:
            try:
                self._acquire_camera(run)
                break
            except ApiError as exc:
                if exc.details.get("owner") != "autofocus" or time.monotonic() > deadline:
                    raise _RunEnded("refused", exc.message) from exc
                if not told:
                    self._log("info", "Sequence: waiting for autofocus to end before starting.")
                    told = True
                if run.stop.wait(0.5):
                    return
        with self._hub._lock:
            if self._state == "waiting":
                self._state = "running"
                self._publish(status=True)
        self._begin(run)

    def _gate(self, run: _Run) -> bool:
        """``_wait_if_paused``: hold while paused; False when stopped meanwhile."""
        if run.gate.is_set():
            return not run.stop.is_set()
        hub = self._hub
        with hub._lock:
            if self._state in ("running", "pausing"):
                self._close_segment(run)
                self._state = "paused"
                self._publish(status=True)
        self._log("info", "Sequence paused.")
        run.gate.wait()
        with hub._lock:
            run.segment_start = time.monotonic()
            run.starts.clear()  # a pause breaks the observed cadence
            if self._state == "paused":
                self._state = "running"
                self._publish(status=True)
        return not run.stop.is_set()

    @staticmethod
    def _close_segment(run: _Run) -> None:
        """Lock held: add the time since the last segment start to the active time."""
        if run.segment_start is not None:
            run.active_s += time.monotonic() - run.segment_start
            run.segment_start = None

    def _loop(self, run: _Run) -> bool:
        """``SequenceWorker._run`` (sequence_worker.py:162-243)."""
        plan = run.plan
        total = run.frames_total
        per_pass = total // max(1, int(plan.repeat or 1)) if total else 0
        current_filter: str | None = None
        current_step = -1
        hub = self._hub
        logger.info("Sequence start: %d frame(s) → %s", total, run.base_dir)
        for spec in expand_plan(plan):
            if run.stop.is_set() or not self._gate(run):
                return False
            if spec.step_index != current_step:
                current_step = spec.step_index
                step = plan.steps[current_step]
                with hub._lock:
                    run.step_index = current_step
                    run.starts.clear()
                    self._publish()
                self._log(
                    "info",
                    f"Step {current_step + 1}/{len(plan.steps)}: {step.count} × "
                    f"{step.frame_type} {step.filter_name if spec.needs_filter else ''} "
                    f"{step.exposure_s:g} s".replace("  ", " "),
                )
            with hub._lock:
                run.pass_index = (run.frames_done // per_pass + 1) if per_pass else 1
            # Wheel: Light/Flat to the step's filter, Dark/Bias to the opaque slot.
            wanted = spec.wheel_filter
            if hub.wheel.connected and wanted != current_filter:
                self._set_filter(run, wanted)
                if run.stop.is_set():
                    return False
                if (
                    spec.needs_filter
                    and current_filter is not None
                    and plan.autofocus_on_filter_change
                ):
                    self._await_autofocus(run)
                    run.frames_since_af = 0
                    if run.stop.is_set():
                        return False
                current_filter = wanted
            # Periodic autofocus.
            if plan.autofocus_every_n > 0 and run.frames_since_af >= plan.autofocus_every_n:
                self._await_autofocus(run)
                run.frames_since_af = 0
                if run.stop.is_set():
                    return False
            # A pause asked during the wheel move or the autofocus holds before the
            # exposure (Qt only checked at the top of the loop); never expose while the
            # mount moves (a scheduled start, a Resume after "Pause the run and slew").
            while True:
                if not run.gate.is_set() and not self._gate(run):
                    return False
                settled = self._settle_mount(run)
                if settled is None:
                    return False
                if settled:
                    break
            frame_boundary = time.monotonic()
            if not self._shoot_one(run, spec):
                return False
            with hub._lock:
                run.frames_done += 1
                run.frames_since_af += 1
                elapsed = run.active_s + (
                    time.monotonic() - run.segment_start if run.segment_start is not None else 0.0
                )
                run.eta_s = elapsed / run.frames_done * (total - run.frames_done)
                self._publish()
            if spec.dither_every > 0 and run.frames_done % spec.dither_every == 0:
                self._dither(run)
                if run.stop.is_set():
                    return False
            wait_s = spec.interval_s
            if spec.cadence_s is not None:
                # Transit cadence is start-to-start (sequence_worker.py:234-239).
                wait_s = max(0.0, spec.cadence_s - (time.monotonic() - frame_boundary))
            if wait_s > 0 and not self._sleep(run, wait_s):
                return False
        return not run.stop.is_set()

    def _settle_mount(self, run: _Run) -> bool | None:
        """Before an exposure: stop any jog, then hold while the mount slews.

        True: the mount is still. False: the run is paused (a pause asked meanwhile, or
        the slew outlasted ``SLEW_WAIT_MAX_S`` and the run paused itself, by "motion"):
        the caller holds at the gate, then asks again. None: stopped meanwhile. Not in
        Qt, whose Plan page locks the mount controls instead (D2, PROPOSAL §7).
        """
        hub = self._hub
        hub.jog.stop_all_before("Sequence")
        deadline = time.monotonic() + SLEW_WAIT_MAX_S
        told = False
        while True:
            if run.stop.is_set():
                return None
            with hub._lock:
                slewing = (
                    hub._slots["mount"].state == "connected" and hub._mount_state.state == "slewing"
                )
            if not slewing:
                if told:
                    self._log("info", "Slew finished — the run goes on.")
                return True
            if not run.gate.is_set():
                return False  # a pause meanwhile: the gate holds, then this runs again
            if time.monotonic() > deadline:
                with hub._lock:
                    run.gate.clear()
                    run.paused_by = "motion"
                    self._publish(status=True)
                self._log(
                    "error",
                    f"The mount still reports a slew after {SLEW_WAIT_MAX_S:g} s: the run is "
                    "paused. Resume once the mount is still.",
                )
                return False
            if not told:
                self._log("info", "Waiting for the slew to end before the next frame…")
                told = True
            run.stop.wait(0.25)

    def _sleep(self, run: _Run, seconds: float) -> bool:
        """``_interruptible_sleep``; a pause cuts it short. False when stopped."""
        deadline = time.monotonic() + seconds
        while not run.stop.is_set():
            left = deadline - time.monotonic()
            if left <= 0 or not run.gate.is_set():
                return True
            run.wake.wait(min(left, 0.2))
            run.wake.clear()
        return False

    # -- wheel ---------------------------------------------------------------------

    def _set_filter(self, run: _Run, name: str) -> None:
        """``_set_filter``: move and wait for the wheel to settle (≤ 20 s)."""
        hub = self._hub
        wheel = hub.wheel
        target = wheel.canonical(name)
        if target is None:
            if name == DARK_FILTER_NAME:
                if not run.dark_skip_logged:
                    self._log(
                        "warning",
                        "The filter wheel has no Dark slot: dark and bias frames are only dark "
                        "if the telescope is covered.",
                    )
                    run.dark_skip_logged = True
                return
            raise _RunEnded("wheel_error", f"The filter wheel has no '{name}' slot.")
        with hub._lock:
            settled_on = wheel.slot if not wheel.moving else None
        if settled_on == target:
            return
        try:
            wheel.select(target, reason=f"Filter → {target}")
        except ApiError as exc:
            raise _RunEnded("wheel_error", f"Filter wheel: {exc.message}") from exc
        if not wheel.wait_settled(run.stop, timeout_s=FILTER_SETTLE_S):
            if run.stop.is_set():
                return
            raise _RunEnded(
                "wheel_error",
                f"The filter wheel did not settle on '{target}' within {FILTER_SETTLE_S:g} s.",
            )
        with hub._lock:
            slot = wheel.slot
        if slot is None or slot.lower() != target.lower():
            raise _RunEnded(
                "wheel_error",
                f"The filter wheel is on '{slot or 'unknown'}', not on '{target}'.",
            )

    # -- one sub ---------------------------------------------------------------------

    def _shoot_one(self, run: _Run, spec: FrameSpec) -> bool:
        """``_shoot_one`` (sequence_worker.py:338-439); False when stopped."""
        hub = self._hub
        plan = run.plan
        with hub._lock:
            camera = hub._camera
            generation = hub._slots["camera"].generation
            wheel_handle = hub.wheel.handle if hub.wheel.connected else None
        if camera is None or generation != run.camera_generation:
            raise _RunEnded("device_lost", "The camera was disconnected.")

        def log(level: str, message: str) -> None:
            self._log(level, message)

        # P1 header truthfulness, before the exposure (Qt reads both back first).
        filter_actual = wheel_filter_name(wheel_handle, spec.wheel_filter, log)
        gain = int(spec.gain)
        times: dict[str, datetime] = {}

        def on_start() -> None:
            times["start"] = self.clock()  # S36: just before StartExposure

        def on_readout() -> None:
            times["end"] = self.clock()  # S36: at ImageReady
            with hub._lock:
                if hub._camera_state.owner == "sequence":
                    hub._set_camera(state="downloading")

        frame = FrameSettings(
            exposure_s=float(spec.exposure_s),
            gain=gain,
            frame_type=spec.frame_type.lower(),
            filter=filter_actual,
            object_name=plan.object_name,
            light=spec.is_light,
            origin="sequence",  # type: ignore[arg-type]
            save=True,
        )
        with hub._lock:
            run.busy_frame = True
            run.exposure_started_mono = time.monotonic()
            run.current = {
                "frame_type": spec.frame_type,
                "image_type": spec.image_type,
                "filter": filter_actual,
                "exposure_s": float(spec.exposure_s),
                "gain": gain,
                "index": spec.frame_index,
                "step_index": spec.step_index,
                "started_utc": utc_iso(),
            }
            hub._refresh_camera(state="exposing", current=frame.to_dict())
            self._publish()
        try:
            try:
                pixels = camera.expose(
                    float(spec.exposure_s),
                    gain,
                    run.stop,
                    on_readout,
                    light=spec.is_light,
                    on_start=on_start,
                )
            except ExposureCancelled:
                return False
            except (DeviceError, OSError, RuntimeError, ValueError) as exc:
                if run.stop.is_set():
                    return False
                raise _RunEnded("camera_error", f"Camera: {exc}") from exc
            if run.stop.is_set():
                return False
            end = times.get("end") or self.clock()
            start = times.get("start") or (end - timedelta(seconds=float(spec.exposure_s)))
            frame = FrameSettings(**{**frame.to_dict(), "started_utc": utc_iso(start)})
            seq = self._publish_frame(run, camera, pixels, frame, start, end, spec)
            record, path = self._save(run, spec, pixels, start, end, filter_actual, gain, camera)
            self._after_save(run, spec, seq, pixels, start, path, record, filter_actual)
            return True
        finally:
            with hub._lock:
                run.busy_frame = False
                run.current = None
                if hub._camera_state.owner == "sequence":
                    hub._refresh_camera(state="idle", current=None)
                if self._state == "pausing" and not run.gate.is_set():
                    pass  # the gate check flips it to "paused" at once
                self._publish()

    def _publish_frame(
        self,
        run: _Run,
        camera: Any,
        pixels: np.ndarray,
        frame: FrameSettings,
        start: datetime,
        end: datetime,
        spec: FrameSpec,
    ) -> int:
        """``frame_image``: Observe shows the sub; metrics; a Light feeds identification."""
        hub = self._hub
        with hub._lock:
            hub._frame_seq += 1
            seq = hub._frame_seq
            job = hub._metrics_job(seq, pixels, frame, start, end)
            bayer = hub._camera_state.sensor.bayer if hub._camera_state.sensor else None
        encoded = encode_frame(
            pixels,
            seq=seq,
            exposure_s=frame.exposure_s,
            timestamp=utc_iso(end),
            source=getattr(camera, "source", "simulator"),
            extra={
                "bayer": bayer,
                "origin": "sequence",
                "frame_type": frame.frame_type,
                "gain": frame.gain,
                "filter": frame.filter,
                "started_utc": frame.started_utc,
                "save": True,
            },
        )
        with hub._lock:
            hub.bus.publish_frame(encoded)
            hub._refresh_camera(last_frame_seq=seq)
        hub.metrics.submit(job)
        if spec.frame_type == "Light":
            hub.field.on_frame(seq, pixels, "sequence", epoch=start + (end - start) / 2)
        return seq

    def _frame_context(self, run: _Run, filter_name: str, camera: Any) -> FrameContext:
        """``_sequence_frame_context`` (acquisition_engine.py:920-945)."""
        hub = self._hub
        readings: dict[str, Any] = {}
        reader = getattr(camera, "fits_readings", None)
        if reader is not None:
            try:
                readings = dict(reader())
            except Exception as exc:  # reads are best-effort, as the Qt ones
                logger.warning("Camera reads for the FITS header failed: %s", exc)
        with hub._lock:
            pos = hub._pointing()  # X1: a live mount only
            target = hub._goto_target
        site = observing_site(hub.config) or (None, None, None)
        return FrameContext(
            ra=pos.ra_hours if pos else None,
            dec=pos.dec_deg if pos else None,
            altitude=pos.alt_deg if pos else None,
            azimuth=pos.az_deg if pos else None,
            target_ra=target[0] if target else None,
            target_dec=target[1] if target else None,
            object_name=run.plan.object_name,
            filter_name=filter_name,
            observer=str(hub.config.get("observer.name", "") or "").strip(),
            site_lat=site[0],
            site_lon=site[1],
            site_elev=site[2],
            software=SOFTWARE_ID,
            ccd_temp=readings.get("ccd_temp"),
            egain_driver=readings.get("egain_driver"),
            egain_table=dict(hub.config.get("camera.egain_table", {}) or {}),
            offset=readings.get("offset"),
            readout_mode=readings.get("readout_mode"),
        )

    def _save(
        self,
        run: _Run,
        spec: FrameSpec,
        arr: np.ndarray,
        start: datetime,
        end: datetime,
        filter_actual: str,
        gain: int,
        camera: Any,
    ) -> tuple[FrameRecord, Path]:
        """The FITS and ``session.json`` of one sub (sequence_worker.py:378-439)."""
        metrics = fwhm = ecc = None
        try:
            metrics = frame_metrics(arr)
            stars = detect_stars(arr)
            fwhm, ecc = stars.mean_fwhm, stars.mean_eccentricity
        except Exception:  # pragma: no cover - metrics are best-effort
            logger.warning("Frame metrics failed — writing frame without QA", exc_info=True)
        ctx = self._frame_context(run, filter_actual, camera)
        if metrics is not None:
            ctx.hfd = metrics.hfd
            ctx.star_count = metrics.star_count
            ctx.sky_adu = metrics.sky_adu
            ctx.fwhm = fwhm
            ctx.eccentricity = ecc
        plan = run.plan
        folder = FITSWriter.session_folder(
            run.base_dir, plan.object_name, start, spec.image_type, filter_actual, run_id=run.run_id
        )
        filename = FITSWriter.build_filename(
            plan.object_name,
            spec.image_type,
            start,
            spec.exposure_s,
            filter_actual,
            spec.frame_index,
            gain,
        )
        path = folder / filename
        try:
            FITSWriter.write(
                arr,
                path,
                start,
                end,
                spec.exposure_s,
                gain,
                spec.image_type,
                context=ctx,
                overwrite=False,
            )
        except Exception as exc:
            raise _RunEnded("save_error", f"FITS save failed: {exc}") from exc
        record = FrameRecord(
            filename=filename,
            image_type=spec.image_type,
            filter_name=filter_actual,
            exposure_s=spec.exposure_s,
            gain=gain,
            timestamp=start.isoformat(),
            hfd=metrics.hfd if metrics else None,
            fwhm=fwhm,
            star_count=metrics.star_count if metrics else None,
            sky_adu=round(metrics.sky_adu, 1) if metrics else None,
            peak_adu=metrics.peak_adu if metrics else None,
            eccentricity=ecc,
        )
        self._append_session(run, start, record)
        return record, path

    def _append_session(self, run: _Run, start: datetime, record: FrameRecord) -> None:
        """``_append_session`` (sequence_worker.py:441-457)."""
        if run.session_log is None:
            run.session_root = FITSWriter.session_root(
                run.base_dir, run.plan.object_name, start, run_id=run.run_id or ""
            )
            run.session_log = SessionLog(
                object_name=run.plan.object_name,
                software=SOFTWARE_ID,
                started_utc=start.isoformat(),
            )
            self._write_observation(run)
        run.session_log.add(record)
        try:
            run.session_log.write(run.session_root / SESSION_FILENAME)
        except OSError:  # a disk hiccup must not abort the run (as Qt)
            logger.warning("Could not write %s", SESSION_FILENAME, exc_info=True)

    def _write_observation(self, run: _Run) -> None:
        """``_write_observation_metadata`` (sequence_worker.py:459-477), S5."""
        payload = observation_payload(run.plan)
        if payload is None or run.session_root is None:
            return
        try:
            path = run.session_root / OBSERVATION_FILENAME
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:  # a disk hiccup must not abort the run (as Qt)
            logger.warning("Could not write %s", OBSERVATION_FILENAME, exc_info=True)

    def _after_save(
        self,
        run: _Run,
        spec: FrameSpec,
        seq: int,
        pixels: np.ndarray,
        start: datetime,
        path: Path,
        record: FrameRecord,
        filter_actual: str,
    ) -> None:
        """``_on_seq_frame_saved`` (acquisition_engine.py:837-862) and the page's log line."""
        hub = self._hub
        run_root = path.parent.parent
        if not run.targets_written:
            run.targets_written = True
            try:
                tset = hub.targets.target_set()
                tset.save(run_root / "targets.json")
                self._write_selection(tset, run_root)
            except OSError as exc:
                self._log("warning", f"Save run targets: {exc}")
        saved = utc_iso()
        with hub._lock:
            run.frames_saved += 1
            run.by_type[spec.frame_type] = run.by_type.get(spec.frame_type, 0) + 1
            if spec.frame_type == "Light" and run.exposure_started_mono is not None:
                # Monotonic, never the injectable clock: one more clock() call per sub
                # would shift a scripted clock and every later DATE-OBS (parity tests).
                duration = time.monotonic() - run.exposure_started_mono
                run.costs.append((duration, float(spec.exposure_s)))
            run.last_frame_utc = utc_iso(start)
            run.last_saved_utc = saved
            run.last_frame_name = path.name
            run.starts.append(start)
            hub._save_seq += 1
            event = {
                "type": "frame_saved",
                "seq": hub._save_seq,
                "frame_seq": seq,
                "path": str(path),
                "name": path.name,
                "source": "sequence",
                "object": run.plan.object_name.strip() or "Unknown",
                "filter": filter_actual,
                "frame_type": spec.frame_type.lower(),
                "image_type": spec.image_type,
                "exposure_s": float(spec.exposure_s),
                "gain": int(record.gain),
                "date_obs": utc_iso(start),
                "t": saved,
                "run_root": str(run_root),
                "index": spec.frame_index,
                "record": {
                    "hfd": record.hfd,
                    "fwhm": record.fwhm,
                    "star_count": record.star_count,
                    "sky_adu": _finite(record.sky_adu),
                    "peak_adu": int(record.peak_adu) if record.peak_adu is not None else None,
                    "eccentricity": record.eccentricity,
                },
            }
            hub._saves.append(event)
            hub.bus.publish("frame_saved", None, dict(event))
        if record.hfd is not None:
            fwhm = f" FWHM={record.fwhm:.1f}" if record.fwhm is not None else ""
            self._log(
                "ok", f"Saved {path.name}  HFD={record.hfd:.1f}{fwhm}  stars={record.star_count}"
            )
        else:
            self._log("ok", f"Saved {path.name}")
        # P5: one differential point per saved Light sub, through the reference solution.
        if spec.frame_type != "Light":
            return
        reference = hub.field.reference_solution()
        if reference is None or not hub.targets.target_set().by_role(ROLE_TARGET):
            return
        wcs, generation = reference
        hub.photometry.measure_saved_frame(
            MeasureRequest(
                frame_seq=seq,
                raw=pixels,
                wcs=wcs,
                epoch=start + timedelta(seconds=float(spec.exposure_s) / 2.0),
                generation=generation,
                run_root=run_root,
                origin="sequence",
                filter_name=filter_actual,  # its read-back FILTER: its curve (S49)
                solved_seq=hub.field.reference_frame_seq(wcs),  # S56: fresh when seq - 1
            )
        )

    @staticmethod
    def _write_selection(tset: Any, run_root: Path) -> None:
        """``_write_active_selection`` (acquisition_engine.py:1332-1345)."""
        tset.save_selection_manifest(
            run_root / "photometry_selection.json", generated_by=SOFTWARE_ID
        )
        tset.append_selection_history(
            run_root / "photometry_selection_history.jsonl", generated_by=SOFTWARE_ID
        )

    def on_target_set_saved(self, tset: Any) -> None:
        """An in-run target-set edit is journalled in the run folder (Q-P9)."""
        root = self.run_root()
        if root is None or not root.exists():
            return
        try:
            self._write_selection(tset, root)
        except OSError as exc:
            self._log("warning", f"Save run selection: {exc}")

    # -- dither and autofocus ---------------------------------------------------------

    def _dither(self, run: _Run) -> None:
        """``_dither`` (sequence_worker.py:249-278): best effort, never aborts the run."""
        hub = self._hub
        with hub._lock:
            mount = hub._slots["mount"].handle if hub._slots["mount"].state == "connected" else None
        move = getattr(mount, "move_axis", None)
        if move is None:
            return
        run.dither_sign = -run.dither_sign
        sign = run.dither_sign
        try:
            move(0, sign * DITHER_RATE_DEG_S)
            move(1, -sign * DITHER_RATE_DEG_S)
            run.stop.wait(DITHER_PULSE_S)
            move(0, 0.0)
            move(1, 0.0)
            logger.info(
                "Dither: ±%.0f″ nudge, settling %.0fs",
                DITHER_RATE_DEG_S * DITHER_PULSE_S * 3600,
                DITHER_SETTLE_S,
            )
            run.stop.wait(DITHER_SETTLE_S)
        except Exception:
            logger.warning("Dither move failed — continuing without", exc_info=True)
            for axis in (0, 1):
                try:
                    move(axis, 0.0)
                except Exception:
                    pass

    def _await_autofocus(self, run: _Run) -> None:
        """``_on_seq_autofocus_due`` + ``_await_autofocus``: hand the camera to AF, wait."""
        hub = self._hub
        with hub._lock:
            focuser = hub.focuser.handle
            on_dark = hub.wheel.has_dark_slot and (
                hub.wheel.slot is not None and hub.wheel.slot.lower() == DARK_FILTER_NAME.lower()
            )
        if focuser is None:
            if not run.af_skip_logged:
                self._log("info", "Sequence: autofocus skipped — no focuser connected.")
                run.af_skip_logged = True
            return
        if on_dark:
            self._log("info", "Sequence: autofocus skipped — the wheel is on the Dark slot.")
            return
        run.af_done.clear()
        # Wave 6b: the pass on the run strip (``autofocus_passes``).
        af_pass: dict[str, Any] = {
            "started_utc": utc_iso(),
            "ended_utc": None,
            "state": "running",
            "position": None,
            "hfd_px": None,
            "message": None,
            "frames_done": run.frames_done,
        }
        with hub._lock:
            self._close_segment(run)
            run.af_passes.append(af_pass)
            self._state = "autofocus"
            self._publish(status=True)
        self._log("cmd", "Sequence: autofocus…")
        exposure = 0.0
        not_started: str | None = None
        try:
            started = hub.start_autofocus(for_sequence=True)
            exposure = float((started.get("params") or {}).get("exposure_s") or 0.0)
            with hub._lock:
                run.autofocus_runs += 1
        except ApiError as exc:
            self._log("warning", f"Sequence: autofocus not started — {exc.message}")
            not_started = exc.message
            run.af_done.set()
        if run.stop.is_set():
            hub.stop_autofocus()  # stopped while the sweep was starting
        # Stop during the sweep: stop() stops it, the focuser returns to its start
        # (S23) and the run ends once the camera is back.
        bound = 9 * (exposure + 10.0) + 120.0
        if not run.af_done.wait(bound):
            hub.stop_autofocus()
            run.af_done.wait(30.0)
            if not run.stop.is_set():
                self._end_pass(af_pass, "timeout", f"No end within {bound:.0f} s.")
                raise _RunEnded(
                    "autofocus_timeout",
                    f"Autofocus did not end within {bound:.0f} s — sequence aborted.",
                )
        if not_started is not None:
            self._end_pass(af_pass, "not_started", not_started)
        else:
            self._end_pass(af_pass, None, None)
        with hub._lock:
            run.segment_start = time.monotonic()
            run.starts.clear()
            if self._state == "autofocus":
                self._state = "pausing" if not run.gate.is_set() else "running"
                self._publish(status=True)

    def _end_pass(self, af_pass: dict[str, Any], state: str | None, message: str | None) -> None:
        """Record how a mid-run pass ended (from the autofocus record unless *state*)."""
        hub = self._hub
        with hub._lock:
            record = hub._autofocus_record()
            best = record.get("best") or {}
            af_pass.update(
                ended_utc=utc_iso(),
                state=state or str(record.get("state") or "failed"),
                position=record.get("position") if state is None else None,
                hfd_px=best.get("hfd_px") if state is None else None,
                message=message if state is not None else record.get("message"),
            )
            self._publish()

    def on_autofocus_end(self) -> None:
        """The hub's autofocus ended (any outcome): wake a run waiting for it."""
        with self._hub._lock:
            run = self._run
        if run is not None:
            run.af_done.set()

    # -- the end ------------------------------------------------------------------------

    def _finish(self, run: _Run, completed: bool, reason: str, message: str) -> None:
        """``_on_seq_finished`` (acquisition_engine.py:889-904)."""
        hub = self._hub
        ended = utc_iso()
        # Wave 6b: the last sub's point belongs to the run (its wrap-up, its rules).
        wait_s = 2.0 if reason == "shutdown" else self.photometry_wait_s
        deadline = time.monotonic() + wait_s
        while not hub.photometry.idle() and time.monotonic() < deadline:
            time.sleep(0.05)
        result = {
            "completed": bool(completed),
            "reason": "completed" if completed else reason,
            "message": message,
            "frames_saved": run.frames_saved,
            "frames_total": run.frames_total,
            "run_root": (
                str(run.run_root) if run.run_root is not None and run.frames_saved else None
            ),
            "started_utc": run.started_utc,
            "ended_utc": ended,
        }
        with hub._lock:
            self._release_camera()
            if self._run is run:
                self._run = None
            self._state = "idle"
            self._last_result = result
            self._last_plan = run.plan
            self._last_passes = [dict(p) for p in run.af_passes]
            self._publish(status=True)
        if hub.focuser.record().get("locked_by") == "sequence":
            hub.focuser.lock(None)
            hub.focuser.wake()
        hub.observation.set_locked(None)
        hub.field.disarm_after_sequence()
        self._plan_publish()
        if completed:
            self._log("ok", "Sequence complete.")
            hub.set_activity("Sequence complete", source="sequence", topic="sequence", log=False)
            self._end_action(run.plan.on_complete)
        elif reason == "cancelled":
            self._log("info", "Sequence cancelled before its start time.")
        else:
            level = "info" if reason in ("stopped", "shutdown") else "error"
            self._log(level, f"Sequence stopped: {message}")
            hub.set_activity("Sequence stopped", source="sequence", topic="sequence", log=False)
        if reason != "shutdown":
            try:
                self._wrap_up(run, result)
            except Exception:  # the outcome is already published; never fail the end
                logger.exception("Wrap-up failed")

    # -- the wrap-up (wave 6b) -----------------------------------------------------------

    def _calibration(self, plan: SequencePlan, run: _Run | None, darks: int, biases: int):
        """Darks and biases matching *plan*'s Light steps, with tonight's counts."""
        from argos.server import wrapup

        hub = self._hub
        started = parse_utc(run.started_utc) if run is not None and run.started_utc else None
        tonight = _night_frames(hub._sessions_root(), _night_start(started or self.clock()))
        with hub._lock:
            limits = hub._camera_limits
            dark_slot = bool(hub.wheel.connected and hub.wheel.has_dark_slot)
        if run is not None:
            overhead = wrapup.overhead_s(run.costs)
            cadence = self._observed_cadence(run)
        else:
            overhead = cadence = None
        return wrapup.calibration(
            plan,
            tonight=tonight,
            overhead=overhead,
            cadence=cadence,
            min_exposure_s=limits.exposure_min_s if limits is not None else None,
            dark_slot=dark_slot,
            darks=darks,
            biases=biases,
        )

    def _wrap_up(self, run: _Run, result: dict[str, Any]) -> None:
        """Build the wrap-up after the end (and its end action), then re-send the record."""
        from argos.server import wrapup

        hub = self._hub
        attention = getattr(hub, "attention", None)
        summary: dict[str, Any] = {}
        if attention is not None:
            attention.flush(2.0)  # the end's own items (run_error, run_ended) are in
            summary = attention.run_summary(run.run_id)
        try:
            points = wrapup.point_counts(hub.photometry.live_record())
        except Exception:
            logger.warning("Wrap-up: the live curves could not be read", exc_info=True)
            points = {"target": 0, "all": 0, "flagged": 0}
        root = result.get("run_root")
        with hub._lock:
            mount_slot = hub._slots["mount"]
            mount_connected = mount_slot.state in ("connected", "busy")
            mount = hub._mount_state
        record = {
            "run_id": run.run_id,
            "object_name": str(run.plan.object_name or "") or "Unknown",
            "outcome": dict(result),
            "started_utc": run.started_utc,
            "ended_utc": result["ended_utc"],
            "frames": {
                "saved": run.frames_saved,
                "total": run.frames_total,
                "by_type": dict(run.by_type),
            },
            "points": {
                **points,
                "frames_measured": int(summary.get("frames_measured", 0)),
                "frames_skipped": summary.get(
                    "frames_skipped", {"field_lost": 0, "lock_lost": 0, "other": 0}
                ),
            },
            "attention": {
                "critical": int(summary.get("critical", 0)),
                "attention": int(summary.get("attention", 0)),
                "info": int(summary.get("info", 0)),
                "items": list(summary.get("items", [])),
            },
            "run_root": root,
            "run_folder": Path(root).name if root else None,
            "run_bytes": wrapup.folder_bytes(root),
            "mount": {
                "connected": mount_connected,
                "state": mount.state if mount_connected else None,
                "tracking": bool(mount.tracking) if mount_connected else None,
                "end_action": run.plan.on_complete,
            },
            "calibration": self._calibration(
                run.plan, run, wrapup.DEFAULT_DARKS, wrapup.DEFAULT_BIASES
            ),
        }
        with hub._lock:
            if self._run is None and self._last_result is result:
                self._wrapup = record
                self._publish()

    def wrapup(self) -> dict[str, Any]:
        """``GET /api/sequence/wrapup``."""
        with self._hub._lock:
            record = self._wrapup
        if record is None:
            raise ApiError(404, "not_found", "No run has ended yet.")
        return dict(record)

    def calibration_plan(self, darks: int | None = None, biases: int | None = None):
        """``POST /api/sequence/calibration-plan``: the draft takes tonight's darks and biases."""
        from argos.server import wrapup
        from argos.server.sequence_plan import PlanBody

        hub = self._hub
        darks = wrapup.DEFAULT_DARKS if darks is None else int(darks)
        biases = wrapup.DEFAULT_BIASES if biases is None else int(biases)
        if not (0 <= darks <= 999 and 0 <= biases <= 999) or darks + biases == 0:
            raise ApiError(400, "invalid_argument", "Counts: 0-999 darks and biases, not both 0.")
        if self.active:
            raise ApiError(409, "run_active", "The plan is locked while the sequence runs.")
        with hub._lock:
            plan = self._last_plan
        if plan is None:
            plan = self._plan_for_run()  # the draft (its 400 is passed on)
        if not wrapup.light_series(plan):
            raise ApiError(
                400,
                "invalid_argument",
                "No Light step to match: the calibration frames follow the Light steps.",
            )
        calib = self._calibration(plan, None, darks, biases)  # exposures and gains
        body = wrapup.calibration_plan(plan, calib, darks=darks, biases=biases)
        previous = hub.plan.record().get("plan")
        record = hub.plan.put(PlanBody.model_validate(body))
        self._log(
            "cmd",
            f"Calibration plan prepared: {darks} darks and {biases} biases per Light series "
            "(not started).",
        )
        return {"plan": record, "replaced": previous}

    def target_radec(self) -> tuple[float, float] | None:
        """The running plan's target (hours, degrees), for the altitude rule; None for a
        run without Light frames (the preflight's "Calibration frames only: no altitude
        needed": the wrap-up's darks at dawn raised a false altitude alert)."""
        with self._hub._lock:
            run = self._run
        if run is None or not any(
            s.enabled and int(s.count or 0) > 0 and s.frame_type == "Light" for s in run.plan.steps
        ):
            return None
        return self._target_radec(run.plan)

    def _end_action(self, action: str) -> None:
        """``_run_on_complete_action``: only on full completion, logged."""
        hub = self._hub
        if action not in ("Stop tracking", "Park mount"):
            return
        with hub._lock:
            connected = hub._slots["mount"].state == "connected"
        if not connected:
            self._log("warning", f"Sequence complete → {action.lower()} skipped: no mount.")
            return
        try:
            if action == "Stop tracking":
                self._log("cmd", "Sequence complete → stopping tracking (plan option).")
                hub._mount_command("set_tracking", False)
            else:
                self._log("cmd", "Sequence complete → parking the mount (plan option).")
                hub.jog.stop_all_before("Park")
                hub._mount_command("park", target=None)
        except ApiError as exc:
            self._log("error", f"End-of-run action failed: {exc.message}")

    # ------------------------------------------------------------------
    # Devices, shutdown
    # ------------------------------------------------------------------

    def device_lost(self, device_id: str) -> None:
        """The hub is disconnecting a device: a run that needs it ends now."""
        with self._hub._lock:
            run, state = self._run, self._state
        if run is None or state in ("idle", "waiting"):
            return
        if device_id == "camera":
            self.stop("device_lost", "The camera was disconnected.")
        elif device_id == "filterwheel":
            self.stop("device_lost", "The filter wheel was disconnected.")

    def close(self) -> None:
        """Server shutdown: stop the run and wait for it (≤ 15 s)."""
        with self._hub._lock:
            self._closed = True
            run = self._run
        if run is None:
            return
        self.stop("shutdown", "The server shut down during the run.")
        thread = run.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(SHUTDOWN_JOIN_S)

    # ------------------------------------------------------------------
    # Interlock (PROPOSAL §7, D2) and the geometry lock (S15)
    # ------------------------------------------------------------------

    def guard_motion(self, action: str, pause_run: bool = False) -> None:
        """409 ``run_active`` for a mount motion during a run; ``pause_run`` pauses first."""
        hub = self._hub
        with hub._lock:
            state, run = self._state, self._run
            details = {
                "state": state,
                "run_id": run.run_id if run is not None else None,
                "action": action,
            }
        if state not in MOTION_LOCKED:
            return
        if not pause_run:
            raise ApiError(
                409,
                "run_active",
                f"A sequence is running — {action} would move the field under it. "
                "Pause the run first.",
                details=details,
            )
        if state != "stopping":
            try:
                self.pause(by="motion")
            except ApiError:
                pass  # ended meanwhile
        deadline = time.monotonic() + self._pause_bound()
        while time.monotonic() < deadline:
            with hub._lock:
                if self._state in ("paused", "idle", "waiting"):
                    return
            time.sleep(0.05)
        with hub._lock:
            details["state"] = self._state
        raise ApiError(
            409, "run_active", "The run did not pause in time — nothing moved.", details=details
        )

    def _pause_bound(self) -> float:
        """How long a ``pause_run`` motion waits: the sub in progress + 60 s, or the AF's bound."""
        with self._hub._lock:
            run, state = self._run, self._state
            if run is None:
                return 1.0
            if state == "autofocus":
                return 9 * (10.0 + 10.0) + 180.0
            exposure = float((run.current or {}).get("exposure_s") or 0.0)
            elapsed = (
                time.monotonic() - run.exposure_started_mono
                if run.busy_frame and run.exposure_started_mono is not None
                else exposure
            )
            return max(0.0, exposure - elapsed) + 60.0

    def guard_config(self, changes: Any) -> None:
        """``PATCH /api/config`` during a run: the aperture geometry is locked (S15)."""
        if not isinstance(changes, dict):
            return
        keys = sorted(k for k in changes if k in GEOMETRY_KEYS)
        if not keys:
            return
        with self._hub._lock:
            if self._state not in ACTIVE:
                return
            details = {"state": self._state, "run_id": self._record.get("run_id"), "keys": keys}
        raise ApiError(
            409,
            "run_active",
            "The aperture geometry is locked while a sequence runs (one curve, one aperture).",
            details=details,
        )

    # ------------------------------------------------------------------
    # Preflight (A64)
    # ------------------------------------------------------------------

    def preflight(self, start_at_utc: str | None = None, *, given: bool = False) -> dict[str, Any]:
        """``GET /api/sequence/preflight``: worst level first."""
        hub = self._hub
        checks: list[dict[str, Any]] = []
        used: dict[str, int] = {}

        def add(cid: str, level: str, message: str, details: Any = None) -> None:
            # Ids are unique within one answer (clients and 6b attention address them).
            used[cid] = used.get(cid, 0) + 1
            if used[cid] > 1:
                cid = f"{cid}:{used[cid]}"
            check: dict[str, Any] = {"id": cid, "level": level, "message": message}
            if details is not None:
                check["details"] = details
            checks.append(check)

        with hub._lock:
            run = self._run
            state = self._state
        if run is not None:
            add("run", "block", f"A sequence is {state} ({run.plan.object_name or 'Unknown'}).")
            plan: SequencePlan | None = run.plan
        else:
            add("run", "ok", "No sequence is running.")
            plan = None
        # camera
        with hub._lock:
            cam_slot = hub._slots["camera"]
            cam_ok = cam_slot.state == "connected" and hub._camera is not None
            cam_name = cam_slot.name
            sensor = hub._camera_state.sensor
            af = hub._autofocus is not None or hub._camera_state.owner == "autofocus"
        if not cam_ok:
            add("camera", "block", "Connect the camera before running a sequence.")
        elif af and run is None:
            add(
                "camera",
                "block",
                "Autofocus is running — it owns the camera. Wait for it to finish.",
            )
        else:
            size = (
                f"{_grouped(sensor.width)} × {_grouped(sensor.height)}"
                if sensor
                else "sensor unknown"
            )
            add("camera", "ok", f"{cam_name or 'Camera'} connected ({size}).")
        # plan
        plan_notes: list[dict[str, Any]] = []
        if plan is None:
            try:
                plan = self._plan_for_run()
            except ApiError as exc:
                add("plan", "block", exc.message, exc.details or None)
                plan = None
            plan_notes = self._draft_warnings()
        if plan is not None:
            issues = self.plan_issues(plan) if run is None else []
            for issue in issues:
                add(_issue_id(issue), "block", issue["message"], issue)
            if not issues:
                n = total_frames(plan)
                add(
                    "plan",
                    "ok",
                    f"{n} frame{'' if n == 1 else 's'}, about "
                    f"{_duration(estimated_duration_s(plan))}.",
                )
        for issue in plan_notes:
            add(_issue_id(issue), "note", str(issue.get("message") or issue.get("code")), issue)
        # start time
        now = self.clock()
        start = now
        text = start_at_utc if given else (None if run is not None else self._draft_start_at())
        if run is not None:
            start = run.start_at or now
            add(
                "start_at",
                "ok",
                "The run has started." if state != "waiting" else f"Starts at {_hhmm(start)}.",
            )
        elif text is None:
            add("start_at", "ok", "Starts now.")
        else:
            try:
                when = parse_utc(text)
                if (when - now).total_seconds() > START_AHEAD_MAX_S:
                    add(
                        "start_at",
                        "block",
                        f"The start time {_day_hhmm(when)} is more than 24 h ahead.",
                    )
                elif when <= now:
                    add(
                        "start_at",
                        "note",
                        f"The start time {_hhmm(when)} has passed: Start runs at once.",
                    )
                else:
                    start = when
                    add("start_at", "ok", f"Starts at {_hhmm(when)}.")
            except ValueError as exc:
                add("start_at", "block", f"start_at_utc: {exc}")
        estimate = estimated_duration_s(plan) if plan is not None else 0.0
        end = start + timedelta(seconds=estimate)
        frames = total_frames(plan) if plan is not None else 0
        lights = bool(plan) and any(
            s.enabled and int(s.count or 0) > 0 and s.frame_type == "Light" for s in plan.steps
        )
        # object
        if plan is not None:
            if plan.object_name.strip():
                add("object", "ok", f"Object: {plan.object_name}.")
            else:
                add("object", "note", "No object name: the files will say 'Unknown' (as Qt).")
        self._check_mount(add, lights)
        self._check_site(add)
        if plan is not None:
            self._check_wheel(add, plan)
            self._check_focuser(add, plan)
            self._check_altitude(add, plan, start, end, lights)
            base = Path(plan.base_dir) if plan.base_dir is not None else hub._sessions_root()
            checks.append(self._check_output(base))
            disk, needed, free = self._check_disk(plan, base)
            checks.append(disk)
            self._check_calibration(add, plan, start)
            self._check_lid(add, plan)
            self._check_sleep(add)
        else:
            needed, free = 0, None
        order = {"block": 0, "note": 1, "ok": 2}
        checks.sort(key=lambda c: order[c["level"]])
        worst = checks[0]["level"] if checks else "ok"
        return {
            "checks": checks,
            "level": worst,
            "can_start": all(c["level"] != "block" for c in checks),
            "frames_total": frames,
            "estimate_s": float(estimate),
            "start_utc": utc_iso(start),
            "end_utc": utc_iso(end),
            "bytes_needed": int(needed),
            "bytes_free": free,
        }

    def _draft_warnings(self) -> list[dict[str, Any]]:
        """The plan half's non-blocking issues (``level`` other than ``error``)."""
        service = getattr(self._hub, "plan", None)
        record = getattr(service, "record", None)
        if record is None:
            return []
        try:
            value = record()
        except Exception:
            return []
        issues = value.get("issues") if isinstance(value, dict) else None
        return [i for i in issues or [] if isinstance(i, dict) and i.get("level") != "error"]

    def _check_mount(self, add: Callable[..., None], lights: bool) -> None:
        hub = self._hub
        with hub._lock:
            connected = hub._slots["mount"].state == "connected"
            mount = hub._mount_state
        if not connected:
            add(
                "mount",
                "note",
                "No mount: the frames carry no pointing (RA, DEC) and field "
                "identification has no hint.",
            )
        elif lights and mount.state in ("parked", "idle", "slewing"):
            what = {"parked": "parked", "idle": "not tracking", "slewing": "slewing"}[mount.state]
            add("mount", "note", f"The mount is {what}: Light frames need it tracking the target.")
        else:
            add("mount", "ok", "Mount connected" + (", tracking." if mount.tracking else "."))

    def _check_site(self, add: Callable[..., None]) -> None:
        hub = self._hub
        site = observing_site(hub.config)
        if site is None:
            add(
                "site",
                "note",
                "No observing site: no BJD_TDB, the mount's airmass and no "
                "altitude check (set it in Settings).",
            )
            return
        name = str(hub.config.get("site.name", "") or "").strip() or "set"
        with hub._lock:
            check = hub.site_check.record()
        verdict = check.get("state") if isinstance(check, dict) else None
        if verdict in ("mismatch", "warning", "far"):
            add(
                "site",
                "note",
                str(check.get("message") or "The Settings site disagrees with the mount."),
            )
        else:
            add("site", "ok", f"Site: {name}.")

    def _check_wheel(self, add: Callable[..., None], plan: SequencePlan) -> None:
        hub = self._hub
        with hub._lock:
            connected = hub.wheel.connected
            slots = list(hub.wheel.record().get("slots") or []) if connected else []
        names = sorted(
            {
                str(s.filter_name)
                for s in plan.steps
                if s.enabled and int(s.count or 0) > 0 and s.frame_type in ("Light", "Flat")
            }
        )
        if not names:
            add("wheel", "ok", "No filter needed.")
            return
        if not connected:
            add(
                "wheel",
                "note",
                f"No filter wheel: FITS FILTER records the plan's "
                f"{', '.join(names)} unverified.",
            )
            return
        lower = [s.lower() for s in slots]
        missing = [n for n in names if n.lower() not in lower]
        if missing:
            add(
                "wheel",
                "block",
                f"The wheel has no {', '.join(repr(m) for m in missing)} slot "
                f"(slots: {', '.join(slots)}).",
            )
        else:
            add("wheel", "ok", f"Filters on the wheel: {', '.join(names)}.")

    def _check_focuser(self, add: Callable[..., None], plan: SequencePlan) -> None:
        planned = plan.autofocus_every_n > 0 or plan.autofocus_on_filter_change
        with self._hub._lock:
            focuser = self._hub.focuser.handle is not None
        if not planned:
            add("focuser", "ok", "No autofocus planned.")
        elif not focuser:
            add(
                "focuser",
                "note",
                "Autofocus is planned but no focuser is connected: the passes " "will be skipped.",
            )
        else:
            add("focuser", "ok", "Focuser connected for the planned autofocus.")

    def _target_radec(self, plan: SequencePlan) -> tuple[float, float] | None:
        target = self._hub.observation.target
        if target is not None:
            return float(target["ra_hours"]), float(target["dec_deg"])
        meta = plan.metadata or {}
        ra, dec = meta.get("ra_deg"), meta.get("dec_deg")
        if isinstance(ra, (int, float)) and isinstance(dec, (int, float)):
            return float(ra) / 15.0, float(dec)
        return None

    def _check_altitude(
        self,
        add: Callable[..., None],
        plan: SequencePlan,
        start: datetime,
        end: datetime,
        lights: bool,
    ) -> None:
        if not lights:
            add("altitude", "ok", "Calibration frames only: no altitude needed.")
            return
        site = observing_site(self._hub.config)
        radec = self._target_radec(plan)
        if site is None:
            add("altitude", "note", "No observing site: the target's altitude cannot be checked.")
            return
        if radec is None:
            add("altitude", "note", "No target coordinates: the altitude cannot be checked.")
            return
        limit = self._hub.config.get("site.min_altitude_deg", None)
        try:
            limit = float(limit) if limit is not None else DEFAULT_MIN_ALT_DEG
        except (TypeError, ValueError):
            limit = DEFAULT_MIN_ALT_DEG
        t = start
        lowest: tuple[float, datetime] | None = None
        first_below: datetime | None = None
        while True:
            alt, _az = horizontal_at(julian_date(t), radec[0], radec[1], site[0], site[1])
            if lowest is None or alt < lowest[0]:
                lowest = (alt, t)
            if alt < limit and first_below is None:
                first_below = t
            if t >= end:
                break
            t = min(end, t + timedelta(minutes=5))
        details = {"limit_deg": limit, "min_alt_deg": round(lowest[0], 2)}
        if first_below is not None:
            add(
                "altitude",
                "note",
                f"The target is below {limit:g}° from {_hhmm(first_below)} "
                f"(lowest {lowest[0]:.0f}°; planned end {_hhmm(end)}).",
                details,
            )
        else:
            add(
                "altitude",
                "ok",
                f"Above {limit:g}° over the run (lowest {lowest[0]:.0f}°).",
                details,
            )

    def _check_output(self, base: Path) -> dict[str, Any]:
        probe = base
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        if not probe.is_dir():
            return {"id": "output", "level": "block", "message": f"{probe} is not a folder."}
        try:
            fd, name = tempfile.mkstemp(prefix=".argos-write-test-", dir=probe)
            os.close(fd)
            os.unlink(name)
        except OSError as exc:
            return {
                "id": "output",
                "level": "block",
                "message": f"The run folder cannot be written in {probe}: "
                f"{exc.strerror or exc}.",
            }
        return {"id": "output", "level": "ok", "message": f"Runs are written in {base}."}

    def _check_disk(self, plan: SequencePlan, base: Path) -> tuple[dict[str, Any], int, int | None]:
        hub = self._hub
        with hub._lock:
            sensor = hub._camera_state.sensor
        width, height = (sensor.width, sensor.height) if sensor else (0, 0)
        frames = total_frames(plan)
        needed = frames * (width * height * 2 + HEADER_BYTES)
        probe = base
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        try:
            free = int(shutil.disk_usage(probe).free)
        except OSError:
            free = None
        details = {"bytes_needed": needed, "bytes_free": free, "frames": frames}
        if sensor is None:
            check = {
                "id": "disk",
                "level": "note",
                "message": "Disk space needed is unknown " "until the camera is connected.",
                "details": details,
            }
        elif free is None:
            check = {
                "id": "disk",
                "level": "note",
                "message": "Free disk space unknown.",
                "details": details,
            }
        elif needed > free:
            check = {
                "id": "disk",
                "level": "block",
                "message": f"Not enough disk space: "
                f"{_bytes(needed)} needed, {_bytes(free)} free.",
                "details": details,
            }
        elif needed > 0.8 * free:
            check = {
                "id": "disk",
                "level": "note",
                "message": f"{_bytes(needed)} needed, only " f"{_bytes(free)} free.",
                "details": details,
            }
        else:
            check = {
                "id": "disk",
                "level": "ok",
                "message": f"{_bytes(needed)} needed, " f"{_bytes(free)} free.",
                "details": details,
            }
        return check, needed, free

    def _check_calibration(
        self, add: Callable[..., None], plan: SequencePlan, start: datetime
    ) -> None:
        lights = [
            (i, s)
            for i, s in enumerate(plan.steps)
            if s.enabled and int(s.count or 0) > 0 and s.frame_type == "Light"
        ]
        if not lights:
            add("calibration", "ok", "No Light step to calibrate.")
            return
        night_start = _night_start(start)
        frames = _night_frames(self._hub._sessions_root(), night_start)
        for s in plan.steps:  # the plan's own calibration steps count
            if s.enabled and int(s.count or 0) > 0 and s.frame_type != "Light":
                frames.extend(
                    [(s.frame_type, float(s.exposure_s), int(s.gain), str(s.filter_name))]
                    * int(s.count)
                )
        per_step = []
        missing = []
        for i, s in lights:
            darks = sum(
                1
                for t, e, g, _f in frames
                if t == "Dark" and math.isclose(e, float(s.exposure_s)) and g == int(s.gain)
            )
            biases = sum(1 for t, _e, g, _f in frames if t == "Bias" and g == int(s.gain))
            flats = sum(
                1
                for t, _e, _g, f in frames
                if t == "Flat" and f.lower() == str(s.filter_name).lower()
            )
            per_step.append({"step": i, "darks": darks, "flats": flats, "biases": biases})
            kinds = [
                k for k, n in (("darks", darks), ("flats", flats), ("biases", biases)) if not n
            ]
            if kinds:
                missing.append(
                    f"step {i + 1} ({s.exposure_s:g} s, gain {s.gain}, {s.filter_name}): "
                    + _and_list(kinds)
                )
        details = {"night_start_utc": utc_iso(night_start), "per_step": per_step}
        if missing:
            add("calibration", "note", "Missing tonight: " + "; ".join(missing) + ".", details)
        else:
            add(
                "calibration",
                "ok",
                "Darks, flats and biases matching the Light steps this night.",
                details,
            )

    def _check_sleep(self, add: Callable[..., None]) -> None:
        """Keep-awake (wave 6b); lid-closed sleep is out of software reach (PROPOSAL §7)."""
        keep = getattr(self._hub, "keep_awake", None)
        works, method, why = keep.capability() if keep is not None else (False, None, None)
        if works:
            add(
                "sleep",
                "ok",
                f"The computer is kept awake during the run ({method}). Keep its lid open: "
                "a closed lid still sleeps most laptops.",
                {"method": method},
            )
        else:
            add(
                "sleep",
                "note",
                f"The computer is not kept awake{f': {why}' if why else ''}. Keep it awake "
                "and its lid open for the whole run: a sleeping computer stops the run.",
                {"method": None, "reason": why},
            )

    def _check_lid(self, add: Callable[..., None], plan: SequencePlan) -> None:
        calib = any(
            s.enabled and int(s.count or 0) > 0 and s.frame_type in ("Dark", "Bias")
            for s in plan.steps
        )
        if not calib:
            return
        with self._hub._lock:
            dark_slot = self._hub.wheel.connected and self._hub.wheel.has_dark_slot
        if dark_slot:
            add("lid", "ok", "Dark and bias frames are taken through the wheel's Dark slot.")
        else:
            add(
                "lid",
                "note",
                "No filter wheel with a Dark slot: dark and bias frames are only "
                "dark with the telescope covered — put the lid on.",
            )


def _grouped(n: int) -> str:
    """An integer with a narrow no-break space between thousands (BRAND 5): "3 840"."""
    return f"{int(n):,}".replace(",", "\u202f")


def _issue_id(issue: dict[str, Any]) -> str:
    """A plan issue's check id: ``plan:<code>`` (``:<step number>`` for a step's)."""
    step = issue.get("step")
    code = str(issue.get("code") or "issue")
    return f"plan:{code}:{int(step) + 1}" if isinstance(step, int) else f"plan:{code}"


def _and_list(words: list[str]) -> str:
    """Join words in prose: a; a and b; a, b and c."""
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def _bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000.0
    return f"{value:.1f} TB"  # pragma: no cover


def _night_start(start: datetime) -> datetime:
    """Local noon before *start*, in UTC (the night the run belongs to)."""
    local = start.astimezone()
    noon = local.replace(hour=12, minute=0, second=0, microsecond=0)
    if local < noon:
        noon -= timedelta(days=1)
    return noon.astimezone(timezone.utc)


def _night_frames(sessions: Path, night_start: datetime) -> list[tuple[str, float, int, str]]:
    """``(type, exposure, gain, filter)`` of every sub of the runs started that night."""
    out: list[tuple[str, float, int, str]] = []
    night_end = night_start + timedelta(hours=24)
    try:
        folders = [p for p in sessions.iterdir() if p.is_dir()]
    except OSError:
        return out
    for folder in folders:
        path = folder / SESSION_FILENAME
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            started = parse_utc(str(data.get("started_utc") or ""))
        except (OSError, ValueError, AttributeError):
            continue
        if not (night_start <= started < night_end):
            continue
        for frame in data.get("frames") or []:
            kind = str(frame.get("image_type") or "").split(" ")[0].capitalize()
            try:
                out.append(
                    (
                        kind,
                        float(frame.get("exposure_s") or 0.0),
                        int(frame.get("gain") or 0),
                        str(frame.get("filter_name") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
    return out


__all__ = [
    "ACTIVE",
    "GEOMETRY_KEYS",
    "MOTION_LOCKED",
    "SequenceService",
    "observation_payload",
    "parse_utc",
    "wire_plan",
]
