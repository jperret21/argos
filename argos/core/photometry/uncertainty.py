"""Run-level photometric uncertainty model.

The formal error for an individual image is incomplete: scintillation,
flat-field residuals and small tracking/calibration effects are shared by a
run but do not appear in the CCD photon budget.  This module implements the
same robust systematic-floor method used by ``star_var_script`` so live and
post-processed Argos measurements have one uncertainty contract.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SystematicErrorFloor:
    """Measured systematic contribution for one target/filter/run."""

    sigma_real: float
    median_formal: float
    sigma_systematic: float
    points_used: int


def robust_sigma(values: Iterable[float]) -> float:
    """Return the MAD-based robust standard deviation of finite values."""
    valid = [float(value) for value in values if math.isfinite(value)]
    if not valid:
        return 0.0
    median = statistics.median(valid)
    mad = statistics.median(abs(value - median) for value in valid)
    return 1.4826 * mad


def estimate_lightcurve_scatter(jd_mag: Iterable[tuple[float, float]]) -> float | None:
    """Estimate the per-point scatter using robust second differences.

    For independent errors, ``m[i-1] - 2*m[i] + m[i+1]`` has variance
    ``6*sigma²``.  Second differences remove a locally linear variable-star
    trend, matching the uncertainty model used by ``star_var_script``.
    """
    points = sorted(
        (float(jd), float(mag)) for jd, mag in jd_mag if math.isfinite(jd) and math.isfinite(mag)
    )
    if len(points) < 10:
        return None
    second_differences = [
        points[index - 1][1] - 2.0 * points[index][1] + points[index + 1][1]
        for index in range(1, len(points) - 1)
    ]
    return robust_sigma(second_differences) / math.sqrt(6.0)


def estimate_systematic_floor(
    points: Iterable[tuple[float, float, float]], *, manual_floor: float | None = None
) -> SystematicErrorFloor | None:
    """Measure the systematic uncertainty floor for a light-curve run.

    Args:
        points: ``(JD_UTC, magnitude, formal_error_mag)`` triples.
        manual_floor: Explicit systematic floor in magnitudes. If omitted, it
            is inferred from the robust second-difference scatter.

    Returns:
        The derived floor, or ``None`` until at least ten valid measurements
        are available for an automatic estimate.
    """
    valid = [
        (float(jd), float(mag), float(error))
        for jd, mag, error in points
        if math.isfinite(jd) and math.isfinite(mag) and math.isfinite(error) and error >= 0.0
    ]
    if not valid or (len(valid) < 10 and manual_floor is None):
        return None
    median_formal = statistics.median(error for _jd, _mag, error in valid)
    if manual_floor is not None:
        sigma_systematic = max(0.0, float(manual_floor))
        sigma_real = math.hypot(median_formal, sigma_systematic)
    else:
        sigma_real = estimate_lightcurve_scatter((jd, mag) for jd, mag, _error in valid)
        if sigma_real is None:
            return None
        sigma_systematic = math.sqrt(max(0.0, sigma_real**2 - median_formal**2))
    return SystematicErrorFloor(
        sigma_real=sigma_real,
        median_formal=median_formal,
        sigma_systematic=sigma_systematic,
        points_used=len(valid),
    )


def apply_systematic_floor(formal_error: float, floor: SystematicErrorFloor | None) -> float:
    """Return the final uncertainty, preserving the point's formal error."""
    formal = max(0.0, float(formal_error))
    return math.hypot(formal, floor.sigma_systematic) if floor is not None else formal
