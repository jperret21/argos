"""The sequence plan draft, its presets and plan files (rows A59-A61).

A Qt-free port of the Plan editor's model side (``sequence_panel.py``,
``sequencer_page.py``) over the unchanged core model (``argos.core.imaging.
sequencer``): ``SequencePlan`` / ``SequenceStep``, ``total_frames``,
``estimated_duration_s``, ``plan_to_dict`` and ``plan_from_dict``, so the
totals, the estimate and the preset files are Qt's by construction.

Two things change on purpose (``web/spec/06-plan-sequencer.md`` §1.16):

- **No silent clamp** (P11, S7). The Qt spin boxes clamp a value to their
  range and the combos substitute an unknown filter or frame type; here the
  plan is stored exactly as typed and every such value is an *issue*
  (:func:`plan_issues`). Issues of level ``error`` refuse a run
  (:meth:`PlanService.plan_for_run`).
- **The draft persists** (P13, Q-P3) in ``sequence_draft.json`` beside
  ``config.json``, written atomically, and keeps its planning ``metadata``
  for the object it was prepared for (P1, S5).
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
import tempfile
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Callable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from argos.core.hardware import active
from argos.core.imaging.sequencer import (
    DARK_FILTER_NAME,
    FRAME_TYPES,
    ON_COMPLETE_CHOICES,
    SequencePlan,
    SequenceStep,
    estimated_duration_s,
    plan_from_dict,
    plan_to_dict,
    total_frames,
)
from argos.server.errors import ApiError
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

PLAN_SCHEMA = 2
DRAFT_FILENAME = "sequence_draft.json"
#: Qt's Plan editor filters before a wheel reports its slots (``sequence_panel.py:66``).
DEFAULT_FILTERS: tuple[str, ...] = ("IR", "LP", "Dark")
#: Qt's fallback spin-box limits without a camera (``sequence_panel.py:70-71``).
DEFAULT_GAIN_RANGE: tuple[int, int] = (0, 600)
DEFAULT_EXPOSURE_RANGE: tuple[float, float] = (0.01, 600.0)
#: The other Qt spin-box ranges (``sequence_panel.py:333, 338, 410, 766, 772, 780``).
COUNT_RANGE = (1, 9999)
INTERVAL_RANGE = (0.0, 3600.0)
DITHER_RANGE = (0, 999)
CADENCE_RANGE = (0.01, 3600.0)
REPEAT_RANGE = (1, 999)
AUTOFOCUS_EVERY_RANGE = (0, 999)
MAX_STEPS = 200
#: Bodies beyond these magnitudes are refused (400), not flagged: no plan needs them.
_BIG = 1e9

METADATA_NOT_RESTORED = "Planning metadata not restored: use Prepare transit for tonight's window."
LOCKED_MESSAGE = "The plan is locked while the sequence runs."


# ---------------------------------------------------------------------------
# Bodies (strict, as every request body of the server)
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class StepBody(_Strict):
    """One ``SequenceStep``; missing keys take the model's defaults."""

    enabled: bool = True
    frame_type: str = Field(default="Light", max_length=16)
    filter_name: str = Field(default=SequenceStep.filter_name, max_length=64)
    exposure_s: float = Field(default=10.0, ge=-_BIG, le=_BIG)
    gain: int = Field(default=80, ge=-_BIG, le=_BIG)
    count: int = Field(default=10, ge=-_BIG, le=_BIG)
    interval_s: float = Field(default=0.0, ge=-_BIG, le=_BIG)
    cadence_s: float | None = Field(default=None, ge=-_BIG, le=_BIG)
    dither_every: int = Field(default=0, ge=-_BIG, le=_BIG)


_MetaKey = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class PlanBody(_Strict):
    """A plan as ``plan_to_dict`` writes it, plus ``schema`` and ``start_at_utc``."""

    schema_: int | None = Field(default=None, alias="schema")
    object_name: str = Field(default="", max_length=200)
    repeat: int = Field(default=1, ge=-_BIG, le=_BIG)
    autofocus_every_n: int = Field(default=0, ge=-_BIG, le=_BIG)
    autofocus_on_filter_change: bool = False
    on_complete: str = Field(default="Nothing", max_length=32)
    base_dir: str | None = Field(default=None, max_length=4096)
    metadata: dict[_MetaKey, str | int | float | bool | None] = Field(
        default_factory=dict, max_length=64
    )
    start_at_utc: str | None = Field(default=None, max_length=40)
    steps: list[StepBody] = Field(default_factory=list, max_length=MAX_STEPS)


class ImportBody(_Strict):
    path: str | None = Field(default=None, min_length=1, max_length=4096)
    preset: str | None = Field(default=None, min_length=1, max_length=120)


class ExportBody(_Strict):
    path: str = Field(min_length=1, max_length=4096)
    overwrite: bool = False


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def normalise_object(name: Any) -> str:
    """The observation's own rule (``ObservationService.set_name``): one space."""
    return " ".join(str(name or "").split())


def _canonical_frame_type(value: str) -> str:
    """``plan_from_dict``'s case-insensitive match; an unknown type stays as typed."""
    canonical = {name.casefold(): name for name in FRAME_TYPES}
    return canonical.get(str(value).casefold(), value)


def parse_utc(text: str) -> datetime:
    """An ISO 8601 instant; a naive one is UTC. ``ValueError`` when unreadable."""
    value = str(text).strip()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    when = datetime.fromisoformat(value)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _describe(exc: ValidationError) -> str:
    """One readable line from a plan's validation error ("step 2: gain: …")."""
    first = exc.errors()[0]
    loc = [part for part in first.get("loc", ()) if part != "body"]
    parts: list[str] = []
    index = 0
    while index < len(loc):
        part = loc[index]
        if part == "steps" and index + 1 < len(loc) and isinstance(loc[index + 1], int):
            parts.append(f"step {loc[index + 1] + 1}")
            index += 2
            continue
        parts.append(str(part))
        index += 1
    message = str(first.get("msg", "invalid value"))
    if first.get("type") == "extra_forbidden":
        message = "unknown key"
    return f"{': '.join(parts)}: {message}" if parts else message


def plan_dict_from_body(body: PlanBody) -> dict[str, Any]:
    """The stored plan (schema 2): the body's values as typed, frame types canonical."""
    if body.schema_ not in (None, PLAN_SCHEMA):
        raise ApiError(
            400, "invalid_argument", f"schema: this server reads plans of schema {PLAN_SCHEMA}"
        )
    if body.start_at_utc is not None:
        try:
            start = parse_utc(body.start_at_utc)
        except ValueError as exc:
            raise ApiError(
                400, "invalid_argument", "start_at_utc: not an ISO 8601 instant"
            ) from exc
        start_at: str | None = utc_iso(start)
    else:
        start_at = None
    steps = []
    for step in body.steps:
        raw = step.model_dump()
        raw["frame_type"] = _canonical_frame_type(raw["frame_type"])
        steps.append(raw)
    return {
        "schema": PLAN_SCHEMA,
        "object_name": normalise_object(body.object_name),
        "repeat": body.repeat,
        "autofocus_every_n": body.autofocus_every_n,
        "autofocus_on_filter_change": body.autofocus_on_filter_change,
        "on_complete": body.on_complete,
        "base_dir": body.base_dir if body.base_dir else None,
        "metadata": dict(body.metadata),
        "start_at_utc": start_at,
        "steps": steps,
    }


def plan_dict_from_json(data: Any) -> dict[str, Any]:
    """A plan read from a file (a Qt preset, an export, the draft).

    The file must be one the Qt app can read too (``plan_from_dict``: an
    unknown step key or frame type is refused), then it is checked as a
    request body. ``ValueError`` with the reason otherwise.
    """
    if not isinstance(data, dict):
        raise ValueError("the file is not a JSON object")
    try:
        plan_from_dict(data)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(_qt_reason(exc)) from exc
    known = set(PlanBody.model_fields) | {"schema"}
    known.discard("schema_")
    # Qt ignores unknown top-level keys (plan_from_dict reads what it knows).
    body = {key: value for key, value in data.items() if key in known}
    try:
        model = PlanBody.model_validate(body)
    except ValidationError as exc:
        raise ValueError(_describe(exc)) from exc
    try:
        return plan_dict_from_body(model)
    except ApiError as exc:
        raise ValueError(exc.message) from exc


def _qt_reason(exc: Exception) -> str:
    text = str(exc)
    match = re.search(r"unexpected keyword argument '([^']+)'", text)
    if match:
        return f"unknown step key '{match.group(1)}'"
    return text


def core_plan(plan: dict[str, Any]) -> SequencePlan:
    """The stored plan as the core model the engine runs."""
    base = plan.get("base_dir")
    return SequencePlan(
        steps=[SequenceStep(**step) for step in plan["steps"]],
        object_name=plan["object_name"],
        repeat=plan["repeat"],
        autofocus_every_n=plan["autofocus_every_n"],
        autofocus_on_filter_change=plan["autofocus_on_filter_change"],
        on_complete=plan["on_complete"],
        base_dir=Path(base) if base else None,
        metadata=dict(plan["metadata"]),
    )


def qt_preset_text(plan: dict[str, Any]) -> str:
    """The file Qt's Save preset writes (``sequence_panel.py:973-985``)."""
    return json.dumps(plan_to_dict(core_plan(plan)), indent=2)


def observation_payload(plan: SequencePlan) -> dict[str, Any] | None:
    """``observation.json`` of a run, as ``SequenceWorker._write_observation_metadata``
    (``sequence_worker.py:462-480``); ``None`` when the plan has no metadata."""
    if not plan.metadata:
        return None
    return {"schema_version": 1, "object_name": plan.object_name, **plan.metadata}


def observation_json(plan: SequencePlan) -> str | None:
    """The exact text Qt writes (``indent=2, sort_keys=True``)."""
    payload = observation_payload(plan)
    return None if payload is None else json.dumps(payload, indent=2, sort_keys=True)


def light_filter_default(filters: list[str]) -> str:
    """``_light_filter_default`` (``sequence_panel.py:694-703``): never the Dark slot."""
    for name in filters:
        if name.casefold() != DARK_FILTER_NAME.casefold():
            return name
    return filters[0] if filters else ""


def default_plan(filters: list[str], object_name: str = "") -> dict[str, Any]:
    """Qt's first editor row (``SequencePanel.__init__``: ``_add_row()``), on a light slot."""
    step = asdict(SequenceStep())
    step["filter_name"] = light_filter_default(filters) or step["filter_name"]
    return {
        "schema": PLAN_SCHEMA,
        "object_name": normalise_object(object_name),
        "repeat": 1,
        "autofocus_every_n": 0,
        "autofocus_on_filter_change": False,
        "on_complete": ON_COMPLETE_CHOICES[0],
        "base_dir": None,
        "metadata": {},
        "start_at_utc": None,
        "steps": [step],
    }


def qt_ranges(limits: dict[str, Any] | None) -> tuple[tuple[float, float], tuple[int, int]]:
    """Exposure and gain ranges as ``set_camera_limits`` (``sequence_panel.py:1016-1041``)."""
    gain_range = DEFAULT_GAIN_RANGE
    exposure_range = DEFAULT_EXPOSURE_RANGE
    if limits:
        gain_min, gain_max = limits.get("gain_min"), limits.get("gain_max")
        if gain_min is not None and gain_max is not None and gain_max > gain_min:
            gain_range = (int(gain_min), int(gain_max))
        exp_min, exp_max = limits.get("exposure_min_s"), limits.get("exposure_max_s")
        if exp_min is not None and exp_max is not None:
            low = max(float(exp_min), DEFAULT_EXPOSURE_RANGE[0])
            if exp_max > low:
                exposure_range = (low, float(exp_max))
    return exposure_range, gain_range


def _fmt(value: float) -> str:
    """A number in an issue's words (BRAND 5, as web/src/lib/format/number.ts): the true minus
    sign (U+2212) and a narrow no-break space (U+202F) between thousands: "−5", "5 000"."""
    text = f"{value:g}"
    if "e" not in text:
        sign, digits = ("-", text[1:]) if text.startswith("-") else ("", text)
        whole, dot, frac = digits.partition(".")
        if len(whole) > 3:
            groups = []
            while whole:
                groups.insert(0, whole[-3:])
                whole = whole[:-3]
            whole = "\u202f".join(groups)
        text = sign + whole + dot + frac
    return text.replace("-", "\u2212")


def _issue(step: int | None, field: str, code: str, level: str, message: str) -> dict[str, Any]:
    return {"step": step, "field": field, "code": code, "level": level, "message": message}


def plan_issues(
    plan: dict[str, Any],
    *,
    exposure_range: tuple[float, float],
    gain_range: tuple[int, int],
    limits_source: str,
    filters: list[str],
    filters_source: str,
    now: datetime,
) -> list[dict[str, Any]]:
    """Every value the Qt editor would clamp or substitute, and what would refuse a run."""
    issues: list[dict[str, Any]] = []
    cam = {
        "camera": "the camera's range",
        "last_camera": "the last camera's range",
        "default": "the range without a camera",
    }[limits_source]

    def out_of_range(
        step: int | None, field: str, label: str, value: float, low: float, high: float, unit: str
    ) -> None:
        where = f"Step {step + 1}: " if step is not None else ""
        issues.append(
            _issue(
                step,
                field,
                "out_of_range",
                "error",
                f"{where}{label} {_fmt(value)}{unit} is outside {_fmt(low)}–{_fmt(high)}{unit}"
                + (f" ({cam})." if field in ("exposure_s", "gain") else "."),
            )
        )

    steps = plan["steps"]
    if not any(s["enabled"] and s["count"] > 0 for s in steps):
        issues.append(_issue(None, "steps", "no_enabled_step", "error", "Add an enabled step."))
    slot_names = {name.casefold(): name for name in filters}
    for index, step in enumerate(steps):
        where = f"Step {index + 1}: "
        frame_type = step["frame_type"]
        if frame_type not in FRAME_TYPES:
            issues.append(
                _issue(
                    index,
                    "frame_type",
                    "unknown_frame_type",
                    "error",
                    f"{where}unknown frame type '{frame_type}' "
                    f"(expected one of {', '.join(FRAME_TYPES)}).",
                )
            )
        low, high = exposure_range
        if not low <= step["exposure_s"] <= high:
            out_of_range(index, "exposure_s", "exposure", step["exposure_s"], low, high, " s")
        glow, ghigh = gain_range
        if not glow <= step["gain"] <= ghigh:
            out_of_range(index, "gain", "gain", step["gain"], glow, ghigh, "")
        if not COUNT_RANGE[0] <= step["count"] <= COUNT_RANGE[1]:
            out_of_range(index, "count", "count", step["count"], *COUNT_RANGE, "")
        if not INTERVAL_RANGE[0] <= step["interval_s"] <= INTERVAL_RANGE[1]:
            out_of_range(index, "interval_s", "interval", step["interval_s"], *INTERVAL_RANGE, " s")
        if not DITHER_RANGE[0] <= step["dither_every"] <= DITHER_RANGE[1]:
            out_of_range(
                index, "dither_every", "dither every", step["dither_every"], *DITHER_RANGE, ""
            )
        cadence = step["cadence_s"]
        if cadence is not None:
            if not CADENCE_RANGE[0] <= cadence <= CADENCE_RANGE[1]:
                out_of_range(index, "cadence_s", "cadence", cadence, *CADENCE_RANGE, " s")
            elif cadence < step["exposure_s"]:
                issues.append(
                    _issue(
                        index,
                        "cadence_s",
                        "cadence_short",
                        "error",
                        f"{where}cadence {_fmt(cadence)} s is shorter than the "
                        f"{_fmt(step['exposure_s'])} s exposure.",
                    )
                )
            if step["interval_s"] > 0:
                issues.append(
                    _issue(
                        index,
                        "interval_s",
                        "interval_ignored",
                        "warning",
                        f"{where}the interval is ignored: the {_fmt(cadence)} s cadence "
                        "sets the start-to-start period.",
                    )
                )
        if frame_type in ("Light", "Flat") and filters:
            name = str(step["filter_name"])
            if name.casefold() not in slot_names:
                on = "on the wheel" if filters_source == "wheel" else "on this telescope's wheel"
                issues.append(
                    _issue(
                        index,
                        "filter_name",
                        "unknown_filter",
                        "error" if filters_source == "wheel" else "warning",
                        f"{where}filter '{name}' is not {on} ({', '.join(filters)}).",
                    )
                )
            elif name.casefold() == DARK_FILTER_NAME.casefold():
                issues.append(
                    _issue(
                        index,
                        "filter_name",
                        "dark_slot",
                        "error",
                        f"{where}a {frame_type} step on the opaque Dark slot gives black frames.",
                    )
                )
    if not REPEAT_RANGE[0] <= plan["repeat"] <= REPEAT_RANGE[1]:
        out_of_range(None, "repeat", "Repeat", plan["repeat"], *REPEAT_RANGE, "")
    if not AUTOFOCUS_EVERY_RANGE[0] <= plan["autofocus_every_n"] <= AUTOFOCUS_EVERY_RANGE[1]:
        out_of_range(
            None,
            "autofocus_every_n",
            "Autofocus every",
            plan["autofocus_every_n"],
            *AUTOFOCUS_EVERY_RANGE,
            " frames",
        )
    if plan["on_complete"] not in ON_COMPLETE_CHOICES:
        issues.append(
            _issue(
                None,
                "on_complete",
                "unknown_on_complete",
                "error",
                f"End of run '{plan['on_complete']}' is not one of "
                f"{', '.join(ON_COMPLETE_CHOICES)}.",
            )
        )
    base = plan.get("base_dir")
    if base and not Path(str(base)).expanduser().is_absolute():
        issues.append(
            _issue(
                None,
                "base_dir",
                "base_dir_relative",
                "error",
                f"The output folder must be absolute: {base}",
            )
        )
    if not plan["object_name"]:
        issues.append(
            _issue(
                None,
                "object_name",
                "no_object",
                "warning",
                "No object name: frames and the run folder will say Unknown.",
            )
        )
    start_at = plan.get("start_at_utc")
    if start_at and parse_utc(start_at) <= now:
        issues.append(
            _issue(
                None,
                "start_at_utc",
                "start_in_past",
                "warning",
                "The scheduled start has passed: Start runs at once.",
            )
        )
    return issues


def derived_values(plan: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Totals and estimate with the core's own functions (``sequencer.py:172-198``)."""
    core = core_plan(plan)
    per_step = [
        (
            estimated_duration_s(SequencePlan(steps=[step], repeat=1))
            if step.enabled and step.count > 0
            else 0.0
        )
        for step in core.steps
    ]
    estimate = estimated_duration_s(core)
    start = now
    if plan.get("start_at_utc"):
        scheduled = parse_utc(plan["start_at_utc"])
        if scheduled > now:
            start = scheduled
    try:
        end = utc_iso(datetime.fromtimestamp(start.timestamp() + estimate, tz=timezone.utc))
    except (OverflowError, OSError, ValueError):
        end = None  # an estimate beyond the calendar: the issues say why
    return {
        "total_frames": total_frames(core),
        "estimate_s": estimate if math.isfinite(estimate) else None,
        "per_step_s": per_step,
        "start_utc": utc_iso(start),
        "end_utc": end,
    }


def preset_name(raw: str) -> str:
    """A preset name, validated (no path, no hidden file); a ``.json`` suffix is ignored."""
    name = str(raw)
    if name.lower().endswith(".json"):
        name = name[:-5]
    if (
        not 1 <= len(name) <= 100
        or re.search(r'[/\\:*?"<>|\x00-\x1f\x7f]', name)
        or name[0] in ". "
        or name[-1] in ". "
    ):
        raise ApiError(
            400,
            "invalid_argument",
            'A preset name is 1-100 characters, without / \\ : * ? " < > |, '
            "and does not start with a dot or a space.",
        )
    return name


#: The process umask, read once at import (``os.umask`` sets it while reading it).
_UMASK = os.umask(0)
os.umask(_UMASK)


def _atomic_write(path: Path, text: str, *, make_parents: bool = True) -> None:
    """Temporary file in the same folder, fsync, rename (``ConfigStore._write``).

    The file gets the mode a plain ``open`` would give it (0644 under the usual
    umask), or keeps the mode of the file it replaces: ``mkstemp`` creates 0600.
    """
    if make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        mode = 0o666 & ~_UMASK
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


class PlanService:
    """The draft plan (A59), its presets (A60) and plan files (A61)."""

    def __init__(self, hub: "Hub", clock: Callable[[], datetime] | None = None) -> None:
        self._hub = hub
        self._lock = threading.RLock()
        self.clock: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        self._revision = 0
        self._notes: list[str] = []
        #: The object the draft's metadata was prepared for (S5).
        self._metadata_object = ""
        #: The newest camera limits seen: Qt keeps the ranges after a disconnect (S7).
        self._last_limits: dict[str, Any] | None = None
        self._record: dict[str, Any] | None = None
        directory = getattr(hub.config, "directory", None)
        self._path: Path | None = (
            Path(directory) / DRAFT_FILENAME if directory is not None else None
        )
        self._plan = self._load_draft()

    # -- context gathered outside the lock (the hub has its own) ----------------------

    def run_active(self) -> bool:
        """Whether a sequence runs (the plan is then locked, Q-P9)."""
        return self._run_active()

    def filter_names(self) -> list[str]:
        """The filter names a step is checked against (wheel, profile, Qt's defaults)."""
        return list(self._context()["filters"])

    def _run_active(self) -> bool:
        sequence = getattr(self._hub, "sequence", None)
        probe = getattr(sequence, "run_active", None)
        if probe is None:
            return False
        try:
            return bool(probe() if callable(probe) else probe)
        except Exception:  # pragma: no cover - the engine's own failure
            logger.exception("run_active failed")
            return False

    def _context(self) -> dict[str, Any]:
        status = self._hub.status()
        limits = (status.get("camera") or {}).get("limits")
        if limits:
            self._last_limits = dict(limits)
            source = "camera"
        elif self._last_limits:
            limits, source = self._last_limits, "last_camera"
        else:
            limits, source = None, "default"
        exposure_range, gain_range = qt_ranges(limits)
        wheel = status.get("filterwheel") or {}
        slots = [str(s) for s in wheel.get("slots") or []]
        if wheel.get("state") not in (None, "disconnected") and slots:
            filters, filters_source = slots, "wheel"
        else:
            profile_slots = [str(s) for s in active.profile().filter_names]
            if profile_slots:
                filters, filters_source = profile_slots, "profile"
            else:
                filters, filters_source = list(DEFAULT_FILTERS), "default"
        observation = status.get("observation") or {}
        return {
            "exposure_range": exposure_range,
            "gain_range": gain_range,
            "limits_source": source,
            "filters": filters,
            "filters_source": filters_source,
            "observation": normalise_object(observation.get("object_name", "")),
            "run_active": self._run_active(),
            "now": self.clock(),
        }

    # -- draft file ---------------------------------------------------------------------

    def _load_draft(self) -> dict[str, Any]:
        filters = [str(s) for s in active.profile().filter_names] or list(DEFAULT_FILTERS)
        if self._path is None or not self._path.exists():
            return default_plan(filters)
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            plan = plan_dict_from_json(data)
            self._metadata_object = normalise_object(
                data.get("metadata_object", plan["object_name"]) if plan["metadata"] else ""
            )
            if self._metadata_object != plan["object_name"]:
                plan["metadata"] = {}
                self._metadata_object = ""
            return plan
        except (OSError, ValueError) as exc:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            kept = self._path.with_name(f"{DRAFT_FILENAME}.unreadable-{stamp}")
            try:
                os.replace(self._path, kept)
            except OSError:
                kept = self._path
            message = f"Sequence draft unreadable ({exc}); kept as {kept.name}, a new plan starts."
            logger.warning(message)
            self._notes = [message]
            return default_plan(filters)

    def _save_draft(self) -> None:
        """Lock held."""
        if self._path is None:
            return
        data = {**self._plan}
        if self._plan["metadata"]:
            data["metadata_object"] = self._metadata_object
        try:
            _atomic_write(self._path, json.dumps(data, indent=2))
        except OSError as exc:
            logger.error("Could not write %s: %s", self._path, exc)
            raise ApiError(
                500, "internal_error", f"Could not save the sequence draft: {exc}"
            ) from exc

    # -- record -----------------------------------------------------------------------------

    def _follow_observation(self, observation: str) -> bool:
        """Lock held: the plan's object is the observation's (Q-P1). True when changed."""
        if not observation or observation == self._plan["object_name"]:
            return False
        self._plan["object_name"] = observation
        notes = [f"Object follows the observation: {observation}."]
        notes += self._drop_foreign_metadata()
        self._notes = notes
        return True

    def _drop_foreign_metadata(self) -> list[str]:
        """Lock held: metadata only for the object it was prepared for (S5)."""
        if self._plan["metadata"] and self._plan["object_name"] != self._metadata_object:
            prepared = self._metadata_object or "another object"
            self._plan["metadata"] = {}
            self._metadata_object = ""
            return [f"Planning metadata dropped: it was prepared for {prepared}."]
        return []

    def _build(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Lock held."""
        plan = copy.deepcopy(self._plan)
        issues = plan_issues(
            plan,
            exposure_range=ctx["exposure_range"],
            gain_range=ctx["gain_range"],
            limits_source=ctx["limits_source"],
            filters=ctx["filters"],
            filters_source=ctx["filters_source"],
            now=ctx["now"],
        )
        record = {
            "plan": plan,
            "derived": derived_values(plan, ctx["now"]),
            "issues": issues,
            "ready": not any(i["level"] == "error" for i in issues),
            "locked": ctx["run_active"],
            "locked_reason": LOCKED_MESSAGE if ctx["run_active"] else None,
            "notes": list(self._notes),
            "filters": {"names": list(ctx["filters"]), "source": ctx["filters_source"]},
            "limits": {
                "exposure_s": list(ctx["exposure_range"]),
                "gain": list(ctx["gain_range"]),
                "source": ctx["limits_source"],
            },
            "path": str(self._path) if self._path is not None else None,
            "revision": self._revision,
        }
        self._record = record
        return record

    def _changed(self, before: tuple[dict[str, Any], str, list[str]]) -> None:
        """Lock held: a new revision, saved; the previous draft back if it cannot be."""
        try:
            self._save_draft()
        except ApiError:
            self._plan, self._metadata_object, self._notes = before
            raise
        self._revision += 1

    def _snapshot(self) -> tuple[dict[str, Any], str, list[str]]:
        """Lock held: what :meth:`_changed` restores when the draft cannot be saved."""
        return copy.deepcopy(self._plan), self._metadata_object, list(self._notes)

    def record(self) -> dict[str, Any]:
        """``GET /api/sequence/plan`` (the draft follows the observation's object)."""
        ctx = self._context()
        with self._lock:
            before = self._snapshot()
            changed = not ctx["run_active"] and self._follow_observation(ctx["observation"])
            if changed:
                self._changed(before)
            record = self._build(ctx)
        if changed:
            self._publish_cached()
        return record

    def publish(self) -> dict[str, Any]:
        """Re-send ``sequence_plan`` (the sequence engine calls it at a run's start and end)."""
        record = self.record()
        self._publish_cached()
        return record

    def _publish_cached(self) -> None:
        """The newest record, under the hub lock (snapshots stay in order)."""
        with self._hub._lock:
            record = self._record
            if record is not None:
                self._hub._publish("sequence_plan", copy.deepcopy(record))

    def _check_unlocked(self, ctx: dict[str, Any]) -> None:
        if ctx["run_active"]:
            raise ApiError(409, "run_active", LOCKED_MESSAGE)

    # -- PUT, import, transit -------------------------------------------------------------

    def put(self, body: PlanBody) -> dict[str, Any]:
        """``PUT /api/sequence/plan``: stored as typed, every clamp an issue."""
        plan = plan_dict_from_body(body)
        return self._replace(plan, keep_metadata_if_echo=True)

    def _replace(
        self,
        plan: dict[str, Any],
        *,
        keep_metadata_if_echo: bool = False,
        metadata_object: str | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        ctx = self._context()
        self._check_unlocked(ctx)
        new_object = plan["object_name"]
        # One object per plan, shared with Observe (Q-P1): a named plan sets the
        # observation; an empty name never clears it (P10).
        if new_object and new_object != ctx["observation"]:
            self._hub.observation.set_name(new_object)
            ctx = self._context()
        with self._lock:
            before = self._snapshot()
            notes = list(notes or [])
            metadata = plan["metadata"]
            if metadata_object is not None:
                self._metadata_object = metadata_object
            elif metadata and keep_metadata_if_echo and metadata == self._plan["metadata"]:
                pass  # an echo keeps the object it was prepared for
            elif metadata:
                self._metadata_object = new_object
            else:
                self._metadata_object = ""
            self._plan = plan
            self._notes = []
            if not new_object and ctx["observation"]:
                self._plan["object_name"] = ctx["observation"]
                notes.append(f"Object follows the observation: {ctx['observation']}.")
            notes += self._drop_foreign_metadata()
            self._notes = notes
            self._changed(before)
            record = self._build(ctx)
        self._publish_cached()
        return record

    def set_transit_plan(
        self, plan: SequencePlan, notes: list[str], start_at_utc: str | None = None
    ) -> dict[str, Any]:
        """``POST /api/transit/plan``: the prepared plan becomes the draft, with its metadata.

        ``start_at_utc`` schedules the run at the coverage start (Q-P2; Qt P7:
        a transit plan is a fixed frame count, started by hand).
        """
        stored = plan_to_dict(plan)
        stored["schema"] = PLAN_SCHEMA
        stored["start_at_utc"] = start_at_utc
        stored["object_name"] = normalise_object(stored["object_name"])
        stored = {key: stored[key] for key in default_plan([]).keys()}
        return self._replace(stored, metadata_object=stored["object_name"], notes=notes)

    def import_plan(self, body: ImportBody) -> dict[str, Any]:
        """``POST /api/sequence/plan/import``: Qt's Load preset (metadata not restored)."""
        if (body.path is None) == (body.preset is None):
            raise ApiError(400, "invalid_argument", "Give either path or preset")
        if self._run_active():
            raise ApiError(409, "run_active", LOCKED_MESSAGE)
        if body.preset is not None:
            name = preset_name(body.preset)
            path = self._preset_path(name)
            if not path.is_file():
                raise ApiError(404, "not_found", f"No preset named {name}")
            label = name
        else:
            path = self._resolve_json(body.path or "", must_exist=True)
            label = path.name
        plan = self._read_plan_file(path)
        notes = [f"Loaded {label}."]
        if plan["metadata"]:
            plan["metadata"] = {}
            notes.append(METADATA_NOT_RESTORED)
        plan["start_at_utc"] = None
        return self._replace(plan, notes=notes)

    def plan_for_run(self) -> SequencePlan:
        """The draft for the engine; ``400`` naming the first error (Fix step N: …)."""
        record = self.record()
        errors = [i for i in record["issues"] if i["level"] == "error"]
        if errors:
            message = errors[0]["message"]
            if message.startswith("Step "):
                message = "Fix s" + message[1:]
            else:
                message = f"Fix the plan: {message[0].lower()}{message[1:]}"
            raise ApiError(400, "invalid_argument", message)
        return core_plan(record["plan"])

    # -- files ------------------------------------------------------------------------------

    def _resolve_json(self, raw: str, *, must_exist: bool) -> Path:
        text = str(raw).strip()
        suffix = Path(text).suffix
        if not must_exist and text and not suffix:
            text += ".json"  # Qt's Save preset appends it
        elif suffix.lower() != ".json":
            raise ApiError(400, "invalid_argument", f"{Path(text).name} is not a .json file")
        path, _root = self._hub.fs_roots.resolve(text, what="file")
        if must_exist and not path.is_file():
            raise ApiError(404, "not_found", f"No file {path}")
        return path

    @staticmethod
    def _read_plan_file(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ApiError(400, "invalid_argument", f"{path.name}: {exc.strerror or exc}") from exc
        except ValueError as exc:
            raise ApiError(400, "invalid_argument", f"{path.name}: not JSON ({exc})") from exc
        try:
            return plan_dict_from_json(data)
        except ValueError as exc:
            raise ApiError(400, "invalid_argument", f"{path.name}: {exc}") from exc

    def export_plan(self, body: ExportBody) -> dict[str, Any]:
        """``POST /api/sequence/plan/export``: Qt's preset format at an absolute path."""
        path = self._resolve_json(body.path, must_exist=False)
        if path.exists() and not body.overwrite:
            raise ApiError(409, "file_exists", f"{path.name} exists; confirm to replace it.")
        if not path.parent.is_dir():
            raise ApiError(400, "invalid_argument", f"No folder {path.parent}.")
        with self._lock:
            text = qt_preset_text(self._plan)
        try:
            _atomic_write(path, text, make_parents=False)
        except OSError as exc:
            raise ApiError(400, "invalid_argument", f"Could not write {path}: {exc}") from exc
        self._hub.log("ok", f"Plan saved to {path}", source="plan", topic="sequence")
        return {"path": str(path)}

    # -- presets ----------------------------------------------------------------------------

    def presets_directory(self) -> Path:
        """``_presets_dir`` (``sequence_panel.py:963-971``)."""
        value = str(self._hub.config.get("data_paths.sequence_presets_directory", "") or "")
        return Path(value).expanduser() if value else Path.home() / "Argos" / "sequences"

    def _preset_path(self, name: str) -> Path:
        return self.presets_directory() / f"{name}.json"

    def list_presets(self) -> dict[str, Any]:
        directory = self.presets_directory()
        rows: list[dict[str, Any]] = []
        try:
            entries = [p for p in directory.iterdir() if p.suffix.lower() == ".json"]
        except OSError:
            entries = []
        for path in entries:
            if path.name.startswith(".") or not path.is_file():
                continue
            row: dict[str, Any] = {
                "name": path.stem,
                "modified_utc": utc_iso(
                    datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                ),
                "object_name": None,
                "steps": None,
                "total_frames": None,
                "estimate_s": None,
                "error": None,
            }
            try:
                preset_name(path.stem)
                plan = self._read_plan_file(path)
                core = core_plan(plan)
                row.update(
                    object_name=plan["object_name"],
                    steps=len(plan["steps"]),
                    total_frames=total_frames(core),
                    estimate_s=estimated_duration_s(core),
                )
            except ApiError as exc:
                row["error"] = exc.message
            rows.append(row)
        rows.sort(key=lambda r: r["name"].casefold())
        return {"directory": str(directory), "presets": rows}

    def get_preset(self, raw_name: str) -> dict[str, Any]:
        name = preset_name(raw_name)
        path = self._preset_path(name)
        if not path.is_file():
            raise ApiError(404, "not_found", f"No preset named {name}")
        plan = self._read_plan_file(path)
        ctx = self._context()
        issues = plan_issues(
            plan,
            exposure_range=ctx["exposure_range"],
            gain_range=ctx["gain_range"],
            limits_source=ctx["limits_source"],
            filters=ctx["filters"],
            filters_source=ctx["filters_source"],
            now=ctx["now"],
        )
        return {
            "name": name,
            "path": str(path),
            "modified_utc": utc_iso(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)),
            "plan": plan,
            "derived": derived_values(plan, ctx["now"]),
            "issues": issues,
            "ready": not any(i["level"] == "error" for i in issues),
        }

    def put_preset(
        self, raw_name: str, body: PlanBody | None, overwrite: bool = False
    ) -> dict[str, Any]:
        name = preset_name(raw_name)
        path = self._preset_path(name)
        if path.exists() and not overwrite:
            raise ApiError(
                409, "file_exists", f"A preset named {name} exists; confirm to replace it."
            )
        if body is not None:
            plan = plan_dict_from_body(body)
        else:
            with self._lock:
                plan = copy.deepcopy(self._plan)
        try:
            _atomic_write(path, qt_preset_text(plan))
        except OSError as exc:
            raise ApiError(400, "invalid_argument", f"Could not save the preset: {exc}") from exc
        self._hub.log("ok", f"Preset saved: {path.name}", source="plan", topic="sequence")
        return self.list_presets()

    def delete_preset(self, raw_name: str) -> dict[str, Any]:
        name = preset_name(raw_name)
        path = self._preset_path(name)
        if not path.is_file():
            raise ApiError(404, "not_found", f"No preset named {name}")
        try:
            path.unlink()
        except OSError as exc:
            raise ApiError(400, "invalid_argument", f"Could not delete the preset: {exc}") from exc
        self._hub.log("info", f"Preset deleted: {path.name}", source="plan", topic="sequence")
        return self.list_presets()
