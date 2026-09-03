"""Live, auditable quality assessment for a comparison-star ensemble.

The acquisition preview is deliberately not a substitute for calibrated Siril
photometry. It can nevertheless catch a bad reference before it poisons a
night: every comparison already has a leave-one-out differential curve, so its
own stability can be assessed against the other comparisons.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

from argos.core.catalog.targets import ROLE_COMPARISON, TargetSet
from argos.core.photometry.uncertainty import estimate_lightcurve_scatter


def comparison_quality_report(
    target_set: TargetSet,
    curves: dict,
    *,
    min_points: int = 10,
    max_scatter_mag: float = 0.10,
    max_formal_error_mag: float = 0.10,
) -> dict:
    """Assess every comparison's leave-one-out curve without changing it.

    ``stable`` means only that the *live preview* has enough internally
    consistent samples. It is not a calibrated-photometry certification;
    that belongs to the registered and calibrated Siril sequence.
    """
    entries: list[dict] = []
    for star in target_set.by_role(ROLE_COMPARISON):
        key = star.auid or star.display_name
        curve = curves.get(key)
        points = [] if curve is None else curve.points
        valid = [
            point
            for point in points
            if not point.saturated
            and math.isfinite(point.jd_utc)
            and math.isfinite(point.mag)
            and math.isfinite(point.formal_mag_err or point.mag_err)
        ]
        scatter = estimate_lightcurve_scatter((point.jd_utc, point.mag) for point in valid)
        formal_median = (
            statistics.median(point.formal_mag_err or point.mag_err for point in valid)
            if valid
            else None
        )
        if len(valid) < min_points or scatter is None or formal_median is None:
            status = "insufficient_data"
        elif formal_median > max_formal_error_mag:
            status = "noisy"
        elif scatter > max_scatter_mag:
            status = "unstable"
        else:
            status = "stable"
        entries.append(
            {
                "name": star.display_name,
                "auid": star.auid,
                "n_valid": len(valid),
                "scatter_mag": None if scatter is None else round(float(scatter), 5),
                "median_formal_error_mag": (
                    None if formal_median is None else round(float(formal_median), 5)
                ),
                "status": status,
            }
        )

    stable = sum(entry["status"] == "stable" for entry in entries)
    assessed = sum(entry["status"] != "insufficient_data" for entry in entries)
    if not entries or assessed < len(entries):
        status = "insufficient_data"
    elif stable < 3:
        status = "not_ready"
    else:
        status = "live_preview_consistent"
    return {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "selection_status": status,
        "scientific_note": (
            "Leave-one-out live-preview assessment only. Confirm the ensemble on "
            "registered, calibrated frames in Siril / star_var_script."
        ),
        "criteria": {
            "min_points": int(min_points),
            "max_scatter_mag": float(max_scatter_mag),
            "max_formal_error_mag": float(max_formal_error_mag),
        },
        "comparison_stars": entries,
    }


def save_comparison_quality_report(path, report: dict) -> None:
    """Atomically persist the live assessment beside the observing session."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    os.replace(tmp, path)
