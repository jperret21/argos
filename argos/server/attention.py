"""Attention for unattended runs (wave 6b; PROPOSAL §7, owner decision D3).

The rules of ``web/lab/research/functional-spaces.md`` §4.10, computed by the
server so that every client shows the same list and an acknowledgement made
on one is seen by all (``protocol.md`` "Night (wave 6b)").

A port of ``web/src/lab/workspace/model/rules.ts``, whose tests are the
oracle (``tests/server/test_attention.py`` replays the lab's synthetic
night). The lab evaluates the whole record list each time (``evaluate``,
rules.ts:65-152); here the same thresholds run per frame with hysteresis:

- ``RULES`` (rules.ts:33-39) → :class:`Thresholds`, config keys ``alerts.*``;
- ``firstRun`` (rules.ts:42-49), K records in a row → :class:`_Streak`, which
  also clears after K records in a row back inside the threshold;
- ``silenceLimit`` (rules.ts:52-56): max(2 × median cadence, median + 60 s),
  the cadence and the silence measured between saves (a client learns of a
  frame when it is saved); before two saves 2 × floor + 60 s;
- the HFD and star-count baselines: the median of the first 20 frames
  (rules.ts:88-121), here per filter (one curve per filter, S49);
- comparisons used below 3, K frames in a row (rules.ts:124-138);
- every message states the rule and the numbers (rules.ts:7-8).

The service observes the published events through an ``EventBus`` tap (the
tap only queues them) and evaluates them on its own thread, plus a 1 s
timer for the timed rules (no new frame, altitude, disk): evaluation never
runs on the event loop.
"""

from __future__ import annotations

import logging
import math
import os
import queue
import shutil
import statistics
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

LEVELS = ("critical", "attention", "info")
_RANK = {level: i for i, level in enumerate(LEVELS)}

#: The rules in words (the lab's ``rule`` strings, rules.ts).
RULE_NAMES = {
    "no_frame": "No new frame",
    "hfd_rise": "HFD rise",
    "star_drop": "Star count drop",
    "comps_low": "Comparisons used",
    "tracker_lost": "Tracker lost",
    "altitude": "Altitude",
    "disk": "Disk space",
    "device_lost": "Device lost",
    "run_error": "Run stopped",
    "autofocus_failed": "Autofocus failed",
    "run_started": "Run started",
    "run_ended": "Run ended",
    "autofocus_done": "Autofocus done",
}
RULE_LEVELS = {
    "no_frame": "critical",
    "device_lost": "critical",
    "run_error": "critical",
    "hfd_rise": "attention",
    "star_drop": "attention",
    "comps_low": "attention",
    "tracker_lost": "attention",
    "altitude": "attention",
    "disk": "attention",
    "autofocus_failed": "attention",
    "run_started": "info",
    "run_ended": "info",
    "autofocus_done": "info",
}
_ACTIONS = {
    "no_frame": {"to": "watch", "label": "Watch"},
    "hfd_rise": {"to": "focus", "label": "Focus view"},
    "comps_low": {"to": "field", "label": "Field view"},
    "tracker_lost": {"to": "field", "label": "Field view"},
    "altitude": {"to": "run", "label": "Run"},
    "device_lost": {"to": "devices", "label": "Devices"},
    "run_error": {"to": "run", "label": "Run"},
    "autofocus_failed": {"to": "focus", "label": "Focus view"},
    "run_ended": {"to": "run", "label": "Run"},
}
#: Run outcomes that are a critical "run stopped on error" (protocol.md RunResult).
ERROR_REASONS = frozenset(
    {"camera_error", "device_lost", "wheel_error", "save_error", "autofocus_timeout", "refused"}
)
#: Photometry skip reasons that mean "the stars are not where the solution puts them".
TRACKER_LOST_REASONS = ("field_lost", "lock_lost")  # S35, S48
#: States of a run (sequence.py STATES) whose subs are being taken.
_RUN_STATES = frozenset({"running", "pausing", "paused", "autofocus", "stopping"})
#: A cause that fires again within this time of its clear reopens its item.
REOPEN_S = 600.0
#: A non-critical item reopened within this time of its last tone gets no new
#: tone and no new log line (a value flapping across its threshold all night).
REOPEN_QUIET_S = 900.0
#: Items kept in the history.
HISTORY_MAX = 200
#: Items of one run kept for its wrap-up, and the runs kept.
RUN_ITEMS_MAX = 500
RUNS_KEPT = 20
#: Start-to-start intervals kept for the cadence of the "no new frame" rule.
CADENCE_KEEP = 200
#: Period of the slow timed rules (altitude, disk).
SLOW_PERIOD_S = 60.0
#: Hysteresis of the timed rules.
ALTITUDE_CLEAR_MARGIN_DEG = 0.5
DISK_CLEAR_FACTOR = 1.1
#: A FITS sub's header and padding (sequence.HEADER_BYTES).
_HEADER_BYTES = 17_280
#: Altitude limit when the site has none (Q-P6, sequence.DEFAULT_MIN_ALT_DEG).
_DEFAULT_MIN_ALT_DEG = 30.0

#: Event kinds the service watches.
WATCHED = frozenset({"sequence", "frame_saved", "photometry", "photometry_point", "devices"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime | float | None) -> str | None:
    if t is None:
        return None
    if not isinstance(t, datetime):
        t = datetime.fromtimestamp(float(t), timezone.utc)
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse(text: Any) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _hhmmss(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M:%S")


def _hhmm(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M")


_MINUS = "\u2212"  # BRAND §5: U+2212 for negatives (web/src/lib/format/number.ts)
_GROUP = "\u202f"  # U+202F groups thousands from 1 000 up


def _fixed(value: float, digits: int) -> str:
    """number.ts ``fixed``: U+2212 for negatives, never "−0"."""
    text = f"{abs(value):.{digits}f}"
    return _MINUS + text if value < 0 and any(c in "123456789" for c in text) else text


def _int(value: float) -> str:
    """number.ts ``int``: rounded, thousands grouped with U+202F ("2 948")."""
    n = round(value)
    digits = str(abs(n))
    if len(digits) >= 4:
        head = len(digits) % 3 or 3
        digits = digits[:head] + "".join(
            _GROUP + digits[i : i + 3] for i in range(head, len(digits), 3)
        )
    return _MINUS + digits if n < 0 else digits


def _span(first: int, last: int) -> str:
    """number.ts ``formatRange``: one way to write a range ("23 … 25")."""
    return f"{_int(first)} … {_int(last)}"


def _median(values: list[float]) -> float:
    finite = [v for v in values if v is not None and math.isfinite(v)]
    return float(statistics.median(finite)) if finite else math.nan


def _bytes(value: float) -> str:
    for unit, size in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if value >= size:
            return f"{value / size:.1f} {unit}"
    return f"{int(value)} B"


# ---------------------------------------------------------------------------
# Thresholds (rules.ts RULES) and their config keys
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """``RULES`` of rules.ts:33-39 plus the timed rules; config keys ``alerts.*``."""

    consecutive: int = 3
    baseline: int = 20
    hfd_factor: float = 1.5
    star_factor: float = 0.7
    comps_min: int = 3
    no_frame_factor: float = 2.0
    no_frame_margin_s: float = 60.0
    altitude_warn_min: float = 15.0
    disk_minutes: float = 30.0

    KEYS = {
        "consecutive": "alerts.consecutive_frames",
        "baseline": "alerts.baseline_frames",
        "hfd_factor": "alerts.hfd_factor",
        "star_factor": "alerts.star_factor",
        "comps_min": "alerts.comparisons_min",
        "no_frame_factor": "alerts.no_frame_factor",
        "no_frame_margin_s": "alerts.no_frame_margin_s",
        "altitude_warn_min": "alerts.altitude_warn_min",
        "disk_minutes": "alerts.disk_minutes",
    }

    @classmethod
    def from_config(cls, get: Callable[[str, Any], Any]) -> "Thresholds":
        values: dict[str, Any] = {}
        for name, key in cls.KEYS.items():
            default = getattr(cls, name)
            raw = get(key, default)
            try:
                value = type(default)(raw)
            except (TypeError, ValueError):
                value = default
            if isinstance(value, float) and not math.isfinite(value):
                value = default
            values[name] = value
        values["consecutive"] = max(1, values["consecutive"])
        values["baseline"] = max(1, values["baseline"])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, name) for name, key in self.KEYS.items()}


# ---------------------------------------------------------------------------
# The rules (pure: the lab oracle's tests drive these directly)
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    """A rule's verdict for one cause: on (fire or keep) or off (clear)."""

    cause: str
    rule: str
    on: bool
    title: str = ""
    short: str = ""
    detail: str = ""
    values: dict[str, Any] = field(default_factory=dict)
    since: float | None = None  # unix s
    frame: int | None = None
    why: str = ""  # clear: what ended the cause


class _Streak:
    """K records in a row past the threshold fire; K in a row back inside clear.

    ``firstRun`` of rules.ts:42-49 for the firing side (the K-th record is the
    one that fires); the clearing side is the same count, which is the
    hysteresis: one good frame never clears, one bad frame never fires.
    """

    __slots__ = ("bad", "good", "on")

    def __init__(self) -> None:
        self.bad = 0
        self.good = 0
        self.on = False

    def feed(self, bad: bool, k: int) -> str | None:
        if bad:
            self.bad += 1
            self.good = 0
            if not self.on and self.bad >= k:
                self.on = True
                return "fire"
            return "hold" if self.on else None
        self.good += 1
        self.bad = 0
        if self.on and self.good >= k:
            self.on = False
            return "clear"
        return None


@dataclass
class Sub:
    """One saved Light sub of the run (the lab's ``FrameRecord``, night.ts:29-47)."""

    n: int  # the run's sub number, 1-based
    t: float  # DATE-OBS, unix s
    hfd: float | None
    stars: int | None
    filter: str = ""
    #: When the file was saved (unix s): what a client sees arrive. None: ``t``.
    saved: float | None = None


class _FilterSeries:
    """The HFD and star-count baselines and streaks of one filter."""

    def __init__(self) -> None:
        self.count = 0
        self.hfd0: list[float] = []
        self.stars0: list[float] = []
        self.hfd_base = math.nan
        self.stars_base = math.nan
        self.hfd_streak = _Streak()
        self.star_streak = _Streak()
        self.recent: deque[Sub] = deque(maxlen=20)


class NightRules:
    """The frame and timed rules of one run (no items, no I/O)."""

    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.th = thresholds or Thresholds()
        self._series: dict[str, _FilterSeries] = {}
        self.comps_streak = _Streak()
        self._comps_recent: deque[tuple[int | None, int]] = deque(maxlen=20)
        self.tracker_streak = _Streak()
        self._tracker_reasons: deque[str] = deque(maxlen=20)
        # no new frame: the save times of the subs (a client learns of a frame at its save)
        self._starts: deque[float] = deque(maxlen=CADENCE_KEEP + 1)
        self.last_start: float | None = None
        self.last_saved: float | None = None
        self.last_n: int | None = None
        #: The newest sub's start-to-save time (s): a floor of the cadence before two subs.
        self.sub_cost: float | None = None
        self.silence_on = False

    @property
    def filters(self) -> list[str]:
        return list(self._series)

    # -- frames ------------------------------------------------------------------------

    def add_sub(self, sub: Sub) -> list[Signal]:
        """One saved Light sub: the HFD and star-count rules (rules.ts:88-122)."""
        th = self.th
        arrived = sub.saved if sub.saved is not None else sub.t
        self._starts.append(arrived)
        self.last_start, self.last_saved, self.last_n = sub.t, arrived, sub.n
        series = self._series.setdefault(sub.filter, _FilterSeries())
        series.count += 1
        series.recent.append(sub)
        tag = f"{sub.filter}: " if len(self._series) > 1 else ""
        out: list[Signal] = []
        if series.count <= th.baseline:
            # rules.ts:89: the first B records are the baseline, never judged.
            series.hfd0.append(sub.hfd if sub.hfd is not None else math.nan)
            series.stars0.append(float(sub.stars) if sub.stars is not None else math.nan)
            if series.count == th.baseline:
                series.hfd_base = _median(series.hfd0)
                series.stars_base = _median(series.stars0)
            return out
        k = th.consecutive
        hfd0 = series.hfd_base
        if sub.hfd is not None and math.isfinite(sub.hfd) and math.isfinite(hfd0) and hfd0 > 0:
            limit = th.hfd_factor * hfd0
            verdict = series.hfd_streak.feed(sub.hfd > limit, k)
            cause = f"hfd_rise:{sub.filter}"
            if verdict == "fire":
                tail = [x for x in series.recent if x.hfd is not None][-k:]
                hfds = ", ".join(_fixed(x.hfd, 1) for x in tail)  # type: ignore[arg-type]
                ratio = sub.hfd / hfd0
                out.append(
                    Signal(
                        cause,
                        "hfd_rise",
                        True,
                        title=f"{tag}HFD {_fixed(sub.hfd, 1)} px = {_fixed(ratio, 1)}× the "
                        f"first {th.baseline} frames",
                        short=f"HFD {_fixed(sub.hfd, 1)} px · {_fixed(ratio, 1)}× baseline",
                        detail=f"Rule: HFD above {th.hfd_factor:g} × {_fixed(hfd0, 2)} px for "
                        f"{k} frames in a row ({hfds} px, frames {_span(tail[0].n, sub.n)}).",
                        values={
                            "hfd_px": sub.hfd,
                            "baseline_px": hfd0,
                            "ratio": ratio,
                            "factor": th.hfd_factor,
                            "filter": sub.filter,
                        },
                        since=sub.t,
                        frame=sub.n,
                    )
                )
            elif verdict == "clear":
                out.append(
                    Signal(
                        cause,
                        "hfd_rise",
                        False,
                        why=f"HFD back under {th.hfd_factor:g} × {_fixed(hfd0, 2)} px for "
                        f"{k} frames (frame {sub.n}: {_fixed(sub.hfd, 1)} px).",
                    )
                )
        stars0 = series.stars_base
        if sub.stars is not None and math.isfinite(stars0) and stars0 > 0:
            verdict = series.star_streak.feed(sub.stars < th.star_factor * stars0, k)
            cause = f"star_drop:{sub.filter}"
            if verdict == "fire":
                ratio = sub.stars / stars0
                out.append(
                    Signal(
                        cause,
                        "star_drop",
                        True,
                        title=f"{tag}{_int(sub.stars)} stars = {_fixed(ratio, 2)}× the first "
                        f"{th.baseline} frames",
                        short=f"{_int(sub.stars)} stars · {_fixed(ratio, 2)}× baseline",
                        detail=f"Rule: fewer than {th.star_factor:g} × {_int(stars0)} stars "
                        f"for {k} frames in a row.",
                        values={
                            "stars": sub.stars,
                            "baseline": stars0,
                            "ratio": ratio,
                            "factor": th.star_factor,
                            "filter": sub.filter,
                        },
                        since=sub.t,
                        frame=sub.n,
                    )
                )
            elif verdict == "clear":
                out.append(
                    Signal(
                        cause,
                        "star_drop",
                        False,
                        why=f"{k} frames with {th.star_factor:g} × {_int(stars0)} stars or "
                        f"more (frame {sub.n}: {_int(sub.stars)}).",
                    )
                )
        return out

    def add_measured(self, comps_used: int | None, n: int | None, t: float | None) -> list[Signal]:
        """A Light sub measured: comparisons used (rules.ts:124-138); the tracker is fine."""
        out = self._tracker(False, None, n, t)
        if comps_used is None:
            return out  # no target point on that sub: it does not count
        th, k = self.th, self.th.consecutive
        self._comps_recent.append((n, comps_used))
        verdict = self.comps_streak.feed(comps_used < th.comps_min, k)
        if verdict == "fire":
            out.append(
                Signal(
                    "comps_low",
                    "comps_low",
                    True,
                    title=f"{comps_used} comparisons used for {k} frames",
                    short=f"{comps_used} comparisons used",
                    detail=f"Rule: fewer than {th.comps_min} comparisons kept after clipping, "
                    f"{k} frames in a row.",
                    values={"comps_used": comps_used, "min": th.comps_min},
                    since=t,
                    frame=n,
                )
            )
        elif verdict == "clear":
            out.append(
                Signal(
                    "comps_low",
                    "comps_low",
                    False,
                    why=f"{th.comps_min} or more comparisons used for {k} frames.",
                )
            )
        return out

    def add_skipped(self, reason: str, n: int | None, t: float | None) -> list[Signal]:
        """A Light sub without a point (photometry skipped): the tracker rule."""
        if reason in TRACKER_LOST_REASONS:
            return self._tracker(True, reason, n, t)
        return []

    def _tracker(self, lost: bool, reason: str | None, n: int | None, t: float | None):
        k = self.th.consecutive
        if reason is not None:
            self._tracker_reasons.append(reason)
        verdict = self.tracker_streak.feed(lost, k)
        if verdict == "fire":
            reasons = list(self._tracker_reasons)[-k:]
            s48 = "lock_lost" in reasons
            how = (
                "fewer than half the anchor stars show a star where the tracked solution "
                "puts them (S48)"
                if s48
                else "no star of the set where the solution puts it (S35)"
            )
            return [
                Signal(
                    "tracker_lost",
                    "tracker_lost",
                    True,
                    title=f"No point on {k} frames in a row: the stars are not where the "
                    f"solution puts them",
                    short=f"Tracker lost · {k} frames",
                    detail=f"Rule: {k} Light frames in a row without a point: {how}. "
                    "The field moved since the solve, or clouds; a new solution is due.",
                    values={"frames": k, "reasons": ", ".join(reasons)},  # number|string
                    since=t,
                    frame=n,
                )
            ]
        if verdict == "clear":
            return [
                Signal("tracker_lost", "tracker_lost", False, why=f"{k} frames measured again.")
            ]
        return []

    # -- no new frame (rules.ts:51-86) ----------------------------------------------------

    def break_segment(self) -> None:
        """A pause, an autofocus or a new step: the cadence restarts."""
        self._starts.clear()

    def median_cadence(self) -> float:
        starts = list(self._starts)
        if len(starts) < 2:
            return math.nan
        return float(statistics.median(b - a for a, b in zip(starts, starts[1:])))

    def cadence(self, planned: float | None = None) -> float:
        """The median cadence; before two subs since the last break, the larger of the planned
        cadence and the newest sub's start-to-save time (a Seestar's download makes a
        10 s sub cost 20-45 s, against 13 s planned: RR Lyr 2026-09-25), else NaN."""
        c = self.median_cadence()
        if math.isfinite(c):
            return c
        floor = max(float(planned or 0.0), float(self.sub_cost or 0.0))
        return floor if floor > 0 else math.nan

    def silence_limit(self, planned: float | None = None) -> float:
        """max(F × cadence, cadence + M) s (rules.ts:52-56), the cadence between saves.

        Before two saves since the last break, F × floor + M (floor: :meth:`cadence`):
        the first interval also carries the run's start-up and the next sub's
        start-to-save time. max(F × floor, floor + M) there raised a false critical
        alarm at the start of all 9 of the owner's runs (the science review's replay;
        RR Lyr 2026-09-25: sub 2 saved 112 s after sub 1 started, limit 104.5 s).
        """
        c = self.median_cadence()
        if math.isfinite(c):
            return max(self.th.no_frame_factor * c, c + self.th.no_frame_margin_s)
        floor = self.cadence(planned)
        if not math.isfinite(floor):
            return math.inf
        return self.th.no_frame_factor * floor + self.th.no_frame_margin_s

    def silence(
        self, now: float, running: bool, reference: float | None, planned: float | None = None
    ) -> list[Signal]:
        """The liveness rule: a frozen run looks exactly like a healthy one between frames."""
        if reference is None:
            return []
        limit = self.silence_limit(planned)
        quiet = running and now - reference > limit
        if quiet and not self.silence_on:
            self.silence_on = True
            c = self.cadence(planned)
            if self.last_n is not None and self.last_saved == reference:
                last = f"Last frame #{self.last_n} saved at {_hhmmss(reference)} UTC"
            elif self.last_n is not None and self.last_start == reference:
                last = f"Last frame #{self.last_n} started at {_hhmmss(reference)} UTC"
            else:
                last = f"No frame since {_hhmmss(reference)} UTC"
            F, M = self.th.no_frame_factor, self.th.no_frame_margin_s
            if math.isfinite(self.median_cadence()):
                formula = f"max({F:g} × cadence {_fixed(c, 1)} s, cadence + {M:g} s)"
            else:
                formula = f"{F:g} × cadence {_fixed(c, 1)} s + {M:g} s (before two frames)"
            return [
                Signal(
                    "no_frame",
                    "no_frame",
                    True,
                    title=f"No new frame since {_hhmmss(reference)} UTC "
                    f"(limit {_int(limit)} s)",
                    short=f"No frame since {_hhmm(reference)} UTC",
                    detail=f"{last}; limit {_int(limit)} s = {formula}.",
                    values={
                        "last_frame_utc": _iso(reference),
                        "limit_s": limit,
                        "cadence_s": c,
                        "frame": self.last_n,
                    },
                    since=reference + limit,
                    frame=self.last_n,
                )
            ]
        if not quiet and self.silence_on:
            self.silence_on = False
            return [Signal("no_frame", "no_frame", False, why="Frames arrive again.")]
        return []

    def end_silence(self, why: str) -> list[Signal]:
        if not self.silence_on:
            return []
        self.silence_on = False
        return [Signal("no_frame", "no_frame", False, why=why)]


# ---------------------------------------------------------------------------
# The service: items, acknowledgement, the event
# ---------------------------------------------------------------------------


@dataclass
class _RunWatch:
    """What the service follows of the run in progress."""

    run_id: str | None
    rules: NightRules
    state: str = "waiting"
    object_name: str = ""
    started: bool = False
    subs: int = 0
    lights: int = 0
    step_index: int | None = None
    reference: float | None = None  # silence: the newest save, or the (re)start
    frames_total: int = 0
    planned_cadence: float | None = None
    devices: set[str] = field(default_factory=set)
    af_seen: int = 0
    pending_comps: dict[int, int] = field(default_factory=dict)
    measured_seqs: deque[int] = field(default_factory=lambda: deque(maxlen=64))
    last_skip: str | None = None
    sub_by_seq: dict[int, tuple[int, float]] = field(default_factory=dict)
    last_sub_bytes: int | None = None
    run_root: str | None = None
    frames_measured: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    next_slow: float = 0.0
    ended: bool = False


class AttentionService:
    """The attention list of the server (rules, items, acknowledgement)."""

    def __init__(self, hub: "Hub", *, tick_s: float = 1.0) -> None:
        self._hub = hub
        self._lock = threading.Lock()
        self._inbox: queue.SimpleQueue = queue.SimpleQueue()
        self._tick_s = tick_s
        #: The wall clock (tests: a scripted one).
        self.clock: Callable[[], datetime] = _utcnow
        self._active: dict[str, dict[str, Any]] = {}
        self._open: dict[str, str] = {}  # cause -> active condition item id
        self._cleared: dict[str, tuple[float, str]] = {}  # cause -> (unix s, item id)
        self._history: deque[dict[str, Any]] = deque(maxlen=HISTORY_MAX)
        self._items_by_run: dict[str, list[dict[str, Any]]] = {}
        self._counter = 0
        self._revision = 0
        self._last_change: dict[str, Any] | None = None
        self._run: _RunWatch | None = None
        self._seq_state = "idle"
        self._thread: threading.Thread | None = None
        self._closed = False
        #: Evaluation time of the last events (s), for the "never blocks" check.
        self.timings: deque[float] = deque(maxlen=1000)
        hub.bus.add_tap(self._tap)

    # -- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._worker, name="argos-attention", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed = True
        self._inbox.put(("_close", {}))
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(2.0)

    def flush(self, timeout: float = 2.0) -> bool:
        """Wait until every event queued so far is evaluated (wrap-up, tests)."""
        if self._thread is None or not self._thread.is_alive():
            return False
        done = threading.Event()
        self._inbox.put(("_flush", {"done": done}))
        return done.wait(timeout)

    # -- the tap (publishing thread: queue only) -------------------------------------------

    def _tap(self, kind: str, payload: dict[str, Any]) -> None:
        if kind in WATCHED:
            self._inbox.put((kind, payload))

    # -- records -----------------------------------------------------------------------

    def thresholds(self) -> Thresholds:
        return Thresholds.from_config(self._hub.config.get)

    def _sound(self) -> dict[str, Any]:
        get = self._hub.config.get
        level = str(get("alerts.sound", "normal") or "normal")
        if level not in ("off", "soft", "normal"):
            level = "normal"
        try:
            repeat = int(get("alerts.repeat_critical_s", 30))
        except (TypeError, ValueError):
            repeat = 30
        return {"level": level, "info": bool(get("alerts.sound_info", False)), "repeat_s": repeat}

    def _build(self) -> dict[str, Any]:
        """Lock held: the ``attention`` snapshot."""
        # Critical, attention, info; newest first within a level (rules.ts:151), then
        # the latest raised first (the active dict keeps the raise order).
        ordered = list(enumerate(self._active.values()))
        active = [
            item
            for _i, item in sorted(
                ordered,
                key=lambda p: (
                    _RANK[p[1]["level"]],
                    -(_parse(p[1]["since"]) or _utcnow()).timestamp(),
                    -p[0],
                ),
            )
        ]
        counts = {level: 0 for level in LEVELS}
        unacked = 0
        for item in active:
            counts[item["level"]] += 1
            if item["level"] != "info" and not item["acked"]:
                unacked += 1
        sound = self._sound() if hasattr(self._hub, "config") else {}
        return {
            "active": [dict(i) for i in active],
            "history": [dict(i) for i in reversed(self._history)],
            "counts": {**counts, "unacked": unacked},
            "sound": sound,
            "thresholds": self.thresholds().to_dict() if hasattr(self._hub, "config") else {},
            "last_change": dict(self._last_change) if self._last_change else None,
            "revision": self._revision,
        }

    def record(self) -> dict[str, Any]:
        with self._lock:
            return self._build()

    def snapshots(self, seq: int) -> list[tuple[str, int, dict[str, Any]]]:
        """Hub lock held: the ``attention`` snapshot a new client receives."""
        with self._lock:
            return [("attention", seq, {"type": "attention", **self._build()})]

    def _publish(self) -> dict[str, Any]:
        """Publish a new revision (hub lock, then this one: the snapshots' order)."""
        hub = self._hub
        with hub._lock:
            with self._lock:
                self._revision += 1
                record = self._build()
            hub._publish("attention", record)
        return record

    # -- acknowledgement ---------------------------------------------------------------

    def ack(self, item_id: str, by: str | None = None) -> dict[str, Any]:
        from argos.server.errors import ApiError

        who = (by or "observer").strip()[:64] or "observer"
        now = _iso(self.clock())
        with self._lock:
            item = self._active.get(item_id)
            if item is None:
                if any(i["id"] == item_id for i in self._history):
                    return self._build()  # already acknowledged or cleared
                raise ApiError(404, "not_found", f"No attention item '{item_id}'.")
            if item["acked"]:
                return self._build()
            self._acknowledge(item, who, now)
        self._hub.log(
            "info",
            f"Acknowledged: {item['name']} ({item['title']})",
            source="attention",
            topic="attention",
        )
        return self._publish()

    def ack_all(self, by: str | None = None) -> dict[str, Any]:
        who = (by or "observer").strip()[:64] or "observer"
        now = _iso(self.clock())
        with self._lock:
            pending = [i for i in self._active.values() if not i["acked"]]
            for item in pending:
                self._acknowledge(item, who, now)
        if pending:
            self._hub.log(
                "info",
                f"Acknowledged {len(pending)} attention item(s).",
                source="attention",
                topic="attention",
            )
            return self._publish()
        return self.record()

    def _acknowledge(self, item: dict[str, Any], who: str, now: str | None) -> None:
        """Lock held."""
        item["acked"] = True
        item["acked_utc"] = now
        item["acked_by"] = who
        item["updated_utc"] = now
        self._last_change = {"change": "acked", "id": item["id"]}
        if item["kind"] == "event":
            self._retire(item, "acknowledged", now)

    def _retire(self, item: dict[str, Any], reason: str, now: str | None) -> None:
        """Lock held: from the active list to the history."""
        self._active.pop(item["id"], None)
        if self._open.get(item["cause"]) == item["id"]:
            del self._open[item["cause"]]
        item["active"] = False
        item["cleared_utc"] = now
        item["cleared_reason"] = reason
        self._history.append(item)

    # -- items -------------------------------------------------------------------------

    def _new_item(self, rule: str, cause: str, kind: str, signal: Signal) -> dict[str, Any]:
        """Lock held."""
        self._counter += 1
        run = self._run
        now = _iso(self.clock())
        level = RULE_LEVELS[rule]
        repeat = self._sound()["repeat_s"]
        sound = level != "info" or self._sound()["info"]
        return {
            "id": f"{rule}-{(run.run_id if run and run.run_id else 'server')}-{self._counter}",
            "rule": rule,
            "cause": cause,
            "name": RULE_NAMES[rule],
            "level": level,
            "kind": kind,
            "title": signal.title,
            "short": signal.short or signal.title,
            "detail": signal.detail,
            "values": dict(signal.values),
            "since": _iso(signal.since) if signal.since is not None else now,
            "raised_utc": now,
            "updated_utc": now,
            "frame": signal.frame,
            "run_id": run.run_id if run else None,
            "action": dict(_ACTIONS[rule]) if rule in _ACTIONS else None,
            "active": True,
            "cleared_utc": None,
            "cleared_reason": None,
            "acked": False,
            "acked_utc": None,
            "acked_by": None,
            "occurrences": 1,
            "tone": 1,
            "toned_utc": now,
            "sound": bool(sound),
            "repeat_s": repeat if level == "critical" and repeat > 0 else None,
        }

    def _apply(self, signals: list[Signal], kind: str = "condition") -> None:
        """Turn rule verdicts into item changes, log them, publish once."""
        if not signals:
            return
        logs: list[tuple[str, str]] = []
        changed = False
        now_dt = self.clock()
        now = _iso(now_dt)
        with self._lock:
            for sig in signals:
                if sig.on:
                    changed |= self._raise(sig, kind, now, now_dt, logs)
                else:
                    item_id = self._open.get(sig.cause)
                    if item_id is None:
                        continue
                    item = self._active[item_id]
                    self._retire(item, "resolved", now)
                    self._cleared[sig.cause] = (now_dt.timestamp(), item_id)
                    self._last_change = {"change": "cleared", "id": item_id}
                    logs.append(("info", f"Cleared: {item['name']} — {sig.why}".rstrip(" —")))
                    changed = True
        for level, text in logs:
            self._hub.log(level, text, source="attention", topic="attention")  # type: ignore[arg-type]
        if changed:
            self._publish()

    def _raise(self, sig: Signal, kind: str, now, now_dt, logs) -> bool:
        """Lock held: a new item, a reopened one, or an update of the open one."""
        rule = sig.rule
        level = RULE_LEVELS[rule]
        log_level = {"critical": "error", "attention": "warning", "info": "info"}[level]
        open_id = self._open.get(sig.cause) if kind == "condition" else None
        if open_id is not None:
            item = self._active[open_id]
            if item["title"] == sig.title and item["detail"] == sig.detail:
                return False
            item.update(
                title=sig.title,
                short=sig.short or sig.title,
                detail=sig.detail,
                values=dict(sig.values),
                updated_utc=now,
            )
            self._last_change = {"change": "updated", "id": open_id}
            return True
        last = self._cleared.get(sig.cause) if kind == "condition" else None
        if last is not None and now_dt.timestamp() - last[0] < REOPEN_S:
            item = next((i for i in self._history if i["id"] == last[1]), None)
            if item is not None and item["cleared_reason"] == "resolved":
                self._history.remove(item)
                # A new episode needs a new acknowledgement: an acknowledged "No new
                # frame" or "Mount lost" that came back stayed silent (technical review).
                # A non-critical one flapping within REOPEN_QUIET_S of its last tone
                # neither sounds nor logs again; its count says how often it came back.
                toned = _parse(item.get("toned_utc")) or _parse(item["raised_utc"])
                quiet = (
                    level != "critical"
                    and toned is not None
                    and now_dt.timestamp() - toned.timestamp() < REOPEN_QUIET_S
                )
                item.update(
                    active=True,
                    cleared_utc=None,
                    cleared_reason=None,
                    acked=False,
                    acked_utc=None,
                    acked_by=None,
                    title=sig.title,
                    short=sig.short or sig.title,
                    detail=sig.detail,
                    values=dict(sig.values),
                    updated_utc=now,
                    occurrences=item["occurrences"] + 1,
                )
                if not quiet:
                    item["tone"] = int(item.get("tone") or 1) + 1
                    item["toned_utc"] = now
                    times = f" (×{item['occurrences']})" if item["occurrences"] > 2 else ""
                    logs.append((log_level, f"{item['name']} again{times}: {sig.title}"))
                self._active[item["id"]] = item
                self._open[sig.cause] = item["id"]
                del self._cleared[sig.cause]
                self._last_change = {"change": "reopened", "id": item["id"]}
                return True
        item = self._new_item(rule, sig.cause, kind, sig)
        self._active[item["id"]] = item
        if kind == "condition":
            self._open[sig.cause] = item["id"]
        run = self._run
        if run is not None and run.run_id is not None:
            if run.run_id not in self._items_by_run and len(self._items_by_run) >= RUNS_KEPT:
                self._items_by_run.pop(next(iter(self._items_by_run)))  # the oldest run
            bucket = self._items_by_run.setdefault(run.run_id, [])
            if len(bucket) < RUN_ITEMS_MAX:
                bucket.append(item)
        self._last_change = {"change": "raised", "id": item["id"]}
        title = item["title"]
        # "Run stopped: Run stopped: …": a title that already starts with the name.
        logs.append(
            (log_level, title if title.startswith(item["name"]) else f"{item['name']}: {title}")
        )
        return True

    def _is_open(self, cause: str) -> bool:
        with self._lock:
            return cause in self._open

    def _open_title(self, cause: str) -> str | None:
        with self._lock:
            item_id = self._open.get(cause)
            return self._active[item_id]["title"] if item_id in self._active else None

    def _event(self, rule: str, cause: str, title: str, **extra: Any) -> None:
        self._apply([Signal(cause, rule, True, title=title, **extra)], kind="event")

    # -- the worker --------------------------------------------------------------------

    def _worker(self) -> None:
        import time

        next_tick = time.monotonic() + self._tick_s
        while True:
            timeout = max(0.0, next_tick - time.monotonic())
            try:
                kind, payload = self._inbox.get(timeout=timeout)
            except queue.Empty:
                kind, payload = None, None
            if kind == "_close" or self._closed:
                return
            if kind == "_flush":
                payload["done"].set()
                continue
            started = time.perf_counter()
            try:
                if kind is not None:
                    self._handle(kind, payload)
                if time.monotonic() >= next_tick:
                    next_tick = time.monotonic() + self._tick_s
                    self.tick()
            except Exception:
                logger.exception("Attention: evaluation failed on %s", kind)
            self.timings.append(time.perf_counter() - started)

    def _handle(self, kind: str, payload: dict[str, Any]) -> None:
        if kind == "sequence":
            self._on_sequence(payload)
        elif kind == "frame_saved":
            self._on_frame_saved(payload)
        elif kind == "photometry_point":
            self._on_point(payload)
        elif kind == "photometry":
            self._on_photometry(payload)
        elif kind == "devices":
            self._on_devices(payload.get("devices") or {})

    # -- the run -----------------------------------------------------------------------

    def _on_sequence(self, rec: dict[str, Any]) -> None:
        state = str(rec.get("state") or "idle")
        previous, self._seq_state = self._seq_state, state
        run = self._run
        if state != "idle" and (run is None or run.ended):
            run = self._begin_run(rec)
        if run is None:
            return
        if rec.get("run_id") and run.run_id != rec.get("run_id"):
            run.run_id = rec.get("run_id")
        run.object_name = str(rec.get("object_name") or "")
        run.planned_cadence = rec.get("cadence_s")
        run.frames_total = int(rec.get("frames_total") or 0)
        run.run_root = rec.get("run_root") or run.run_root
        now = self.clock().timestamp()
        if state in ("running", "pausing") and run.state not in ("running", "pausing"):
            run.reference = now if run.reference is None else max(run.reference, now)
            if run.state in ("paused", "autofocus", "waiting"):
                run.rules.break_segment()
        if state in ("paused", "autofocus", "waiting", "stopping"):
            self._apply(run.rules.end_silence("The run is " + state + "."))
        step = rec.get("step_index")
        if step is not None and step != run.step_index:
            if run.step_index is not None:
                run.rules.break_segment()
            run.step_index = step
        run.state = state
        if not run.started and state in _RUN_STATES and run.run_id:
            run.started = True
            self._run_started(run, rec)
        self._autofocus_passes(run, rec)
        if state == "idle" and previous != "idle" and not run.ended:
            self._end_run(run, rec.get("last_result") or {})

    def _begin_run(self, rec: dict[str, Any]) -> _RunWatch:
        now = _iso(self.clock())
        with self._lock:
            # The previous run's events (unacknowledged) leave the active list.
            moved = [i for i in self._active.values() if i["kind"] == "event"]
            for item in moved:
                self._retire(item, "new_run", now)
            if moved:
                self._last_change = {"change": "cleared", "id": moved[-1]["id"]}
            self._cleared.clear()
        if moved:
            self._publish()
        run = _RunWatch(run_id=rec.get("run_id"), rules=NightRules(self.thresholds()))
        try:
            devices = self._hub.devices()
        except Exception:
            devices = {}
        run.devices = {
            dev
            for dev in ("mount", "focuser")
            if (devices.get(dev) or {}).get("state") in ("connected", "busy")
        }
        self._run = run
        return run

    def _run_started(self, run: _RunWatch, rec: dict[str, Any]) -> None:
        total = int(rec.get("frames_total") or 0)
        end = _parse(rec.get("end_utc"))
        parts = [f"Run started · {run.object_name or 'Unknown'}", f"{total} frames"]
        if end is not None:
            parts.append(f"ends about {end.strftime('%H:%M')} UTC")
        started = _parse(rec.get("started_utc"))
        self._event(
            "run_started",
            f"run_started:{run.run_id}",
            " · ".join(parts),
            short="Run started",
            detail=f"Started at {started.strftime('%H:%M:%S') if started else '?'} UTC.",
            values={"frames_total": total, "end_utc": rec.get("end_utc")},
            since=started.timestamp() if started else None,
        )

    def _autofocus_passes(self, run: _RunWatch, rec: dict[str, Any]) -> None:
        passes = rec.get("autofocus_passes") or []
        for p in passes[run.af_seen :]:
            if p.get("ended_utc") is None:
                break
            run.af_seen += 1
            state = p.get("state")
            ended = _parse(p.get("ended_utc"))
            since = ended.timestamp() if ended else None
            if state == "done":
                hfd = p.get("hfd_px")
                text = f"Autofocus done · best {p.get('position')} steps"
                if isinstance(hfd, (int, float)):
                    text += f" · HFD {hfd:.2f} px"
                self._event(
                    "autofocus_done",
                    f"autofocus_done:{run.af_seen}",
                    text,
                    short="Autofocus done",
                    detail=p.get("message") or "",
                    values={"position": p.get("position"), "hfd_px": hfd},
                    since=since,
                    frame=p.get("frames_done"),
                )
            elif state in ("rejected", "failed", "timeout", "not_started") or (
                state == "cancelled" and run.state not in ("stopping", "idle")
            ):
                self._event(
                    "autofocus_failed",
                    f"autofocus_failed:{run.af_seen}",
                    f"Autofocus {state}: {p.get('message') or 'no message'}",
                    short=f"Autofocus {state}",
                    detail="A mid-run autofocus did not end with a new focus; the run went on "
                    "at the focuser's position.",
                    values={"state": state, "position": p.get("position")},
                    since=since,
                    frame=p.get("frames_done"),
                )

    def _end_run(self, run: _RunWatch, result: dict[str, Any]) -> None:
        run.ended = True
        now = _iso(self.clock())
        logs = []
        with self._lock:
            for cause, item_id in list(self._open.items()):
                item = self._active.get(item_id)
                if item is None or item.get("run_id") != run.run_id:
                    continue
                self._retire(item, "run_ended", now)
                logs.append(f"Cleared: {item['name']} — the run ended.")
                self._last_change = {"change": "cleared", "id": item_id}
            self._cleared.clear()
        for text in logs:
            self._hub.log("info", text, source="attention", topic="attention")
        if logs:
            self._publish()
        reason = str(result.get("reason") or "")
        saved, total = int(result.get("frames_saved") or 0), int(result.get("frames_total") or 0)
        ended = _parse(result.get("ended_utc"))
        since = ended.timestamp() if ended else None
        values = {"reason": reason, "frames_saved": saved, "frames_total": total}
        if reason in ERROR_REASONS:
            self._event(
                "run_error",
                f"run_error:{run.run_id}",
                f"Run stopped: {result.get('message') or reason}",
                short="Run stopped",
                detail=f"Reason {reason}; {saved} of {total} frames saved.",
                values=values,
                since=since,
                frame=saved or None,
            )
        elif reason == "completed":
            self._event(
                "run_ended",
                f"run_ended:{run.run_id}",
                f"Run complete · {saved} frames",
                short="Run complete",
                detail=result.get("message") or "",
                values=values,
                since=since,
                frame=saved or None,
            )
        elif reason in ("stopped", "cancelled"):
            text = (
                f"Run stopped by the observer · {saved} of {total} frames"
                if reason == "stopped"
                else "Run cancelled before its start time"
            )
            self._event(
                "run_ended",
                f"run_ended:{run.run_id}",
                text,
                short="Run stopped" if reason == "stopped" else "Run cancelled",
                detail=result.get("message") or "",
                values=values,
                since=since,
                frame=saved or None,
            )

    # -- frames and photometry -------------------------------------------------------------

    def _on_frame_saved(self, ev: dict[str, Any]) -> None:
        run = self._run
        if run is None or run.ended or ev.get("source") != "sequence":
            return
        run.subs += 1
        start = _parse(ev.get("date_obs"))
        saved = _parse(ev.get("t"))
        t = start.timestamp() if start else self.clock().timestamp()
        # The silence runs from the save: a client learns of a frame when it is saved
        # (from its start, the first interval raised a false alarm on all 9 owner runs).
        arrived = (
            saved.timestamp() if saved is not None and (start is None or saved >= start) else t
        )
        run.reference = arrived if run.reference is None else max(arrived, run.reference)
        if start is not None and saved is not None and saved >= start:
            run.rules.sub_cost = (saved - start).total_seconds()
        run.run_root = ev.get("run_root") or run.run_root
        try:
            run.last_sub_bytes = os.stat(str(ev.get("path"))).st_size
        except (OSError, TypeError, ValueError):
            pass
        signals = run.rules.end_silence("A new frame was saved.")
        if str(ev.get("frame_type") or "").lower() == "light":
            run.lights += 1
            seq = ev.get("frame_seq")
            if isinstance(seq, int):
                run.sub_by_seq[seq] = (run.subs, t)
                if len(run.sub_by_seq) > 64:
                    run.sub_by_seq.pop(next(iter(run.sub_by_seq)))
            record = ev.get("record") or {}
            hfd = record.get("hfd")
            stars = record.get("star_count")
            signals += run.rules.add_sub(
                Sub(
                    n=run.subs,
                    t=t,
                    hfd=float(hfd) if isinstance(hfd, (int, float)) else None,
                    stars=int(stars) if isinstance(stars, (int, float)) else None,
                    filter=str(ev.get("filter") or ""),
                    saved=arrived,
                )
            )
        else:
            run.rules.last_start, run.rules.last_saved, run.rules.last_n = t, arrived, run.subs
        self._apply(signals)
        self._check_disk(run)

    def _counting(self) -> _RunWatch | None:
        """The run whose photometry outcomes count (its subs are being measured)."""
        run = self._run
        if run is None or run.ended or run.lights == 0 or run.state not in _RUN_STATES:
            return None
        return run

    def _on_point(self, ev: dict[str, Any]) -> None:
        run = self._counting()
        if run is None or ev.get("role") != "target":
            return
        seq = ev.get("frame_seq")
        comps = (ev.get("point") or {}).get("comps_used")
        if isinstance(seq, int) and isinstance(comps, int):
            previous = run.pending_comps.get(seq)
            run.pending_comps[seq] = comps if previous is None else min(previous, comps)
            if len(run.pending_comps) > 64:
                run.pending_comps.pop(next(iter(run.pending_comps)))

    def _on_photometry(self, status: dict[str, Any]) -> None:
        run = self._counting()
        if run is None:
            return
        state = status.get("state")
        if state == "measured":
            last = status.get("last") or {}
            seq = last.get("frame_seq")
            if not isinstance(seq, int) or seq in run.measured_seqs:
                return
            run.measured_seqs.append(seq)
            run.frames_measured += 1
            n, t = run.sub_by_seq.get(seq, (None, None))
            self._apply(run.rules.add_measured(run.pending_comps.pop(seq, None), n, t))
        elif state == "skipped":
            key = str(status.get("message") or "")
            if key == run.last_skip:
                return  # the same outcome re-sent: counted once
            run.last_skip = key
            reason = str(status.get("reason") or "other")
            bucket = reason if reason in TRACKER_LOST_REASONS else "other"
            run.skipped[bucket] = run.skipped.get(bucket, 0) + 1
            self._apply(run.rules.add_skipped(reason, run.subs, run.reference))

    def _on_devices(self, devices: dict[str, Any]) -> None:
        run = self._run
        if run is None or run.ended or run.state == "waiting":
            return
        signals = []
        for dev in sorted(run.devices):
            rec = devices.get(dev) or {}
            lost = rec.get("state") not in ("connected", "busy")
            cause = f"device_lost:{dev}"
            is_open = self._is_open(cause)
            if lost and not is_open:
                name = {"mount": "Mount", "focuser": "Focuser"}[dev]
                why = rec.get("error") or rec.get("info") or rec.get("state") or "disconnected"
                effect = (
                    "subs are saved without pointing and dithers are skipped"
                    if dev == "mount"
                    else "the autofocus passes are skipped"
                )
                signals.append(
                    Signal(
                        cause,
                        "device_lost",
                        True,
                        title=f"{name} lost during the run",
                        short=f"{name} lost",
                        detail=f"{name}: {why}. The run goes on: {effect}.",
                        values={"device": dev, "state": rec.get("state")},
                    )
                )
            elif not lost and is_open:
                signals.append(Signal(cause, "device_lost", False, why="connected again."))
        self._apply(signals)

    # -- timed rules ---------------------------------------------------------------------

    def tick(self) -> None:
        """Every second (the worker): no new frame; every 60 s: altitude and disk."""
        run = self._run
        if run is None or run.ended:
            return
        now = self.clock().timestamp()
        running = run.state in ("running", "pausing")
        self._apply(run.rules.silence(now, running, run.reference, run.planned_cadence))
        if now >= run.next_slow and run.state in _RUN_STATES:
            run.next_slow = now + SLOW_PERIOD_S
            self._check_altitude(run, now)
            self._check_disk(run)

    def _check_altitude(self, run: _RunWatch, now: float) -> None:
        """The target below the site limit now or within ``altitude_warn_min``.

        A run with Light frames only (``target_radec`` is None otherwise: the
        preflight says "Calibration frames only: no altitude needed"). The mount's
        own altitude when it points at the target; the Settings site extrapolates
        ahead only while the X3 site check does not say it disagrees with the mount
        (RR Lyr 2026-09-25, a wrong Settings site: 13.9° from the site while the
        mount read 75°). With a disagreeing site and no mount reading, no verdict.
        """
        from argos.core.config import observing_site
        from argos.core.imaging.platesolve import angular_separation_deg
        from argos.core.imaging.sky_geometry import horizontal_at
        from argos.core.photometry.airmass import julian_date

        hub = self._hub
        site = observing_site(hub.config)
        target = getattr(hub.sequence, "target_radec", lambda: None)()
        if target is None:
            return
        try:
            check = hub.site_check.record() if hasattr(hub, "site_check") else {}
        except Exception:
            check = {}
        site_ok = site is not None and check.get("state") != "mismatch"
        pointing = hub._pointing() if hasattr(hub, "_pointing") else None
        mount_alt: float | None = None
        if pointing is not None and pointing.alt_deg is not None:
            apart = angular_separation_deg(
                pointing.ra_hours * 15.0, pointing.dec_deg, target[0] * 15.0, target[1]
            )
            if apart <= 1.0:  # the mount points at the target
                mount_alt = float(pointing.alt_deg)
        if not site_ok and mount_alt is None:
            return
        try:
            limit = float(hub.config.get("site.min_altitude_deg", _DEFAULT_MIN_ALT_DEG))
        except (TypeError, ValueError):
            limit = _DEFAULT_MIN_ALT_DEG
        warn_min = float(self.thresholds().altitude_warn_min)

        def alt_at(t: float) -> float:
            when = datetime.fromtimestamp(t, timezone.utc)
            return float(
                horizontal_at(julian_date(when), target[0], target[1], site[0], site[1])[0]
            )

        alt_now = mount_alt if mount_alt is not None else alt_at(now)
        if site is not None and not site_ok:
            source = "from the mount: the Settings site disagrees with it (site check)"
        elif mount_alt is not None:
            source = "from the mount"
        else:
            source = "from the Settings site"
        cause = "altitude"
        signals: list[Signal] = []
        below_at: float | None = now if alt_now < limit else None
        if below_at is None and site_ok:
            step = 60.0
            t = now + step
            while t <= now + warn_min * 60.0 + 1e-6:
                if alt_at(t) < limit:
                    below_at = t
                    break
                t += step
        if below_at is not None:
            if below_at <= now:
                title = f"Target below the {limit:g}° limit ({_fixed(alt_now, 1)}°)"
                short = f"Alt {_fixed(alt_now, 1)}° · limit {limit:g}°"
            else:
                title = f"Target drops below {limit:g}° at {_hhmm(below_at)} UTC"
                short = f"Below {limit:g}° at {_hhmm(below_at)} UTC"
            current = self._open_title(cause)
            if current is None or current.startswith("Target drops") != title.startswith(
                "Target drops"
            ):
                signals.append(
                    Signal(
                        cause,
                        "altitude",
                        True,
                        title=title,
                        short=short,
                        detail=f"Rule: the target below the site limit "
                        f"(site.min_altitude_deg {limit:g}°) now or within {warn_min:g} min; "
                        f"{_fixed(alt_now, 1)}° at {_hhmm(now)} UTC, {source}.",
                        values={
                            "alt_deg": alt_now,
                            "limit_deg": limit,
                            "below_utc": _iso(below_at),
                        },
                        since=below_at if below_at > now else now,
                        frame=run.subs or None,
                    )
                )
        elif self._is_open(cause) and alt_now >= limit + ALTITUDE_CLEAR_MARGIN_DEG:
            signals.append(
                Signal(
                    cause,
                    "altitude",
                    False,
                    why=f"target at {_fixed(alt_now, 1)}°, above {limit:g}° ({source}).",
                )
            )
        self._apply(signals)

    def _check_disk(self, run: _RunWatch) -> None:
        hub = self._hub
        root = run.run_root
        if not root:
            return
        probe = Path(root)
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        try:
            free = float(shutil.disk_usage(probe).free)
        except OSError:
            return
        size = run.last_sub_bytes
        if size is None:
            with hub._lock:
                sensor = hub._camera_state.sensor
            if sensor is None:
                return
            size = sensor.width * sensor.height * 2 + _HEADER_BYTES
        cadence = run.rules.median_cadence()
        if not math.isfinite(cadence):
            cadence = float(run.planned_cadence or 0.0)
        if cadence <= 0:
            return
        minutes = float(self.thresholds().disk_minutes)
        frames = minutes * 60.0 / cadence
        # A run ending sooner needs only its remaining frames (science review: a
        # 1.3 GB run of 80 short subs raised "under 30 min" with 18.9 GB free).
        remaining = run.frames_total - run.subs if run.frames_total > 0 else None
        if remaining is not None and remaining < frames:
            frames = max(remaining, 0)
            need_text = f"the run's {_int(frames)} remaining frames"
            title = f"Disk space short of {need_text} ({_bytes(free)} free)"
        else:
            need_text = f"{minutes:g} min of frames"
            title = f"Disk space for under {need_text} ({_bytes(free)} free)"
        needed = size * frames
        cause = "disk"
        is_open = self._is_open(cause)
        if free < needed and not is_open:
            left_min = free / size * cadence / 60.0
            self._apply(
                [
                    Signal(
                        cause,
                        "disk",
                        True,
                        title=title,
                        short=f"Disk: about {left_min:.0f} min left",
                        detail=f"Rule: free space below {need_text} at the "
                        f"{_fixed(cadence, 1)} s cadence ({_bytes(size)} per frame).",
                        values={
                            "free_bytes": int(free),
                            "needed_bytes": int(needed),
                            "minutes_left": left_min,
                        },
                        frame=run.subs or None,
                    )
                ]
            )
        elif free >= DISK_CLEAR_FACTOR * needed and is_open:
            self._apply([Signal(cause, "disk", False, why=f"{_bytes(free)} free.")])

    # -- the wrap-up -----------------------------------------------------------------------

    def run_summary(self, run_id: str | None) -> dict[str, Any]:
        """The run's items and photometry outcomes, for its wrap-up."""
        with self._lock:
            items = list(self._items_by_run.get(run_id or "", []))
            counts = {level: 0 for level in LEVELS}
            for item in items:
                counts[item["level"]] += 1
            run = self._run if self._run is not None and self._run.run_id == run_id else None
            return {
                **counts,
                "items": [
                    {
                        "id": i["id"],
                        "rule": i["rule"],
                        "name": i["name"],
                        "level": i["level"],
                        "title": i["title"],
                        "since": i["since"],
                        "cleared_utc": i["cleared_utc"],
                        "acked": i["acked"],
                    }
                    for i in items
                ],
                "frames_measured": run.frames_measured if run else 0,
                "frames_skipped": {
                    "field_lost": run.skipped.get("field_lost", 0) if run else 0,
                    "lock_lost": run.skipped.get("lock_lost", 0) if run else 0,
                    "other": run.skipped.get("other", 0) if run else 0,
                },
            }


__all__ = [
    "AttentionService",
    "NightRules",
    "RULE_LEVELS",
    "RULE_NAMES",
    "Signal",
    "Sub",
    "Thresholds",
]
