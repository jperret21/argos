"""The end-of-night wrap-up (wave 6b; PROPOSAL §3.1, owner decision D2).

When a run ends the Run card turns into the next steps
(``web/lab/research/functional-spaces.md`` §4.14): what the run produced, the
attention items it raised, the tracking state, and the calibration frames
matching tonight's Lights, prefilled with a time estimate from the run's own
per-frame cost (exposure + download + save, measured on its subs), not the
exposure alone (functional-spaces finding 1). No calibration frame exists in
any of the owner's 19 session folders (functional-spaces §1.2).

Pure helpers here; :class:`argos.server.sequence.SequenceService` gathers
the inputs and publishes the record (``protocol.md`` "Wrap-up").
"""

from __future__ import annotations

import math
import os
import statistics
from pathlib import Path
from typing import Any, Iterable

from argos.core.imaging.sequencer import SequencePlan

#: The guide's counts (functional-spaces §4.14: darks 15-20, biases 20-30).
DEFAULT_DARKS = 20
DEFAULT_BIASES = 30
#: The shortest exposure a plan accepts without camera limits (Qt's 0.01 s floor).
PLAN_MIN_EXPOSURE_S = 0.01
#: The per-frame overhead of the plan estimate (sequencer.py:178).
MIN_OVERHEAD_S = 3.0
#: A folder walk stops counting after this many files (a wrong run root).
_WALK_MAX_FILES = 200_000


def light_series(plan: SequencePlan) -> list[tuple[float, int, str]]:
    """``(exposure, gain, filter)`` of the plan's enabled Light steps, first seen first."""
    seen: list[tuple[float, int, str]] = []
    for step in plan.steps:
        if not (step.enabled and int(step.count or 0) > 0 and step.frame_type == "Light"):
            continue
        key = (float(step.exposure_s), int(step.gain), str(step.filter_name))
        if not any(math.isclose(k[0], key[0]) and k[1] == key[1] for k in seen):
            seen.append(key)
    return seen


def overhead_s(costs: Iterable[tuple[float, float]]) -> float | None:
    """Median of (sub duration − exposure) over the run's subs, at least 3 s.

    A sub's duration is DATE-OBS to its save (exposure, download, FITS write):
    what a dark costs too; a cadence or an interval wait is not in it.
    """
    extra = [d - e for d, e in costs if math.isfinite(d) and d >= e]
    if not extra:
        return None
    return max(MIN_OVERHEAD_S, float(statistics.median(extra)))


def calibration(
    plan: SequencePlan,
    *,
    tonight: list[tuple[str, float, int, str]],
    overhead: float | None,
    cadence: float | None,
    min_exposure_s: float | None,
    dark_slot: bool,
    darks: int = DEFAULT_DARKS,
    biases: int = DEFAULT_BIASES,
) -> dict[str, Any]:
    """Darks per (exposure, gain) and biases per gain of the Light steps."""
    per_frame = overhead if overhead is not None else MIN_OVERHEAD_S
    bias_exposure = max(float(min_exposure_s or 0.0), PLAN_MIN_EXPOSURE_S)
    dark_rows, bias_rows, gains = [], [], []
    for exposure, gain, _filter in light_series(plan):
        existing = sum(
            1 for t, e, g, _f in tonight if t == "Dark" and math.isclose(e, exposure) and g == gain
        )
        dark_rows.append(
            {
                "exposure_s": exposure,
                "gain": gain,
                "count": int(darks),
                "existing": existing,
                "estimate_s": round(int(darks) * (exposure + per_frame), 1),
            }
        )
        if gain not in gains:
            gains.append(gain)
    for gain in gains:
        existing = sum(1 for t, _e, g, _f in tonight if t == "Bias" and g == gain)
        bias_rows.append(
            {
                "exposure_s": bias_exposure,
                "gain": gain,
                "count": int(biases),
                "existing": existing,
                "estimate_s": round(int(biases) * (bias_exposure + per_frame), 1),
            }
        )
    note = None
    if not dark_slot:
        note = (
            "No Dark slot on a filter wheel: put the lid on the telescope before the darks "
            "and biases."
        )
    elif overhead is None:
        note = "No sub was timed: the estimate uses 3 s per frame on top of the exposure."
    return {
        "darks": dark_rows,
        "biases": bias_rows,
        "overhead_s": round(per_frame, 2),
        "cadence_s": round(cadence, 3) if cadence is not None else None,
        "dark_slot": bool(dark_slot),
        "note": note,
    }


def calibration_plan(
    plan: SequencePlan, calib: dict[str, Any], *, darks: int, biases: int
) -> dict[str, Any]:
    """The draft (``PlanBody`` keys) taking *calib*'s darks and biases: one step each."""
    series = light_series(plan)
    filters = {(round(e, 6), g): f for e, g, f in series}
    steps = []
    for row in calib["darks"]:
        if darks > 0:
            steps.append(
                {
                    "enabled": True,
                    "frame_type": "Dark",
                    "filter_name": filters.get(
                        (round(row["exposure_s"], 6), row["gain"]), series[0][2]
                    ),
                    "exposure_s": float(row["exposure_s"]),
                    "gain": int(row["gain"]),
                    "count": int(darks),
                    "interval_s": 0.0,
                    "cadence_s": None,
                    "dither_every": 0,
                }
            )
    for row in calib["biases"]:
        if biases > 0:
            steps.append(
                {
                    "enabled": True,
                    "frame_type": "Bias",
                    "filter_name": series[0][2],
                    "exposure_s": float(row["exposure_s"]),
                    "gain": int(row["gain"]),
                    "count": int(biases),
                    "interval_s": 0.0,
                    "cadence_s": None,
                    "dither_every": 0,
                }
            )
    return {
        "schema": 2,
        "object_name": str(plan.object_name or ""),
        "repeat": 1,
        "autofocus_every_n": 0,
        "autofocus_on_filter_change": False,
        "on_complete": "Nothing",
        "base_dir": str(plan.base_dir) if plan.base_dir else None,
        "metadata": {},
        "start_at_utc": None,
        "steps": steps,
    }


def folder_bytes(path: str | os.PathLike | None) -> int | None:
    """Total size of the files under *path* (``None`` when it does not exist)."""
    if not path:
        return None
    root = Path(path)
    if not root.is_dir():
        return None
    total, files = 0, 0
    for folder, _dirs, names in os.walk(root):
        for name in names:
            files += 1
            if files > _WALK_MAX_FILES:
                return total
            try:
                total += os.stat(os.path.join(folder, name)).st_size
            except OSError:
                continue
    return total


def point_counts(live: dict[str, Any]) -> dict[str, int]:
    """Points of the live curves (the run's: they restart with it), by role and flags."""
    target = all_points = flagged = 0
    for curve in live.get("curves") or []:
        points = curve.get("points") or []
        all_points += len(points)
        if curve.get("role") == "target":
            target += len(points)
        flagged += sum(1 for p in points if p.get("suspect") or p.get("saturated"))
    return {"target": target, "all": all_points, "flagged": flagged}


__all__ = [
    "DEFAULT_BIASES",
    "DEFAULT_DARKS",
    "calibration",
    "calibration_plan",
    "folder_bytes",
    "light_series",
    "overhead_s",
    "point_counts",
]
