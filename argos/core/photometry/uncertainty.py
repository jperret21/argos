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


#: Osborn et al. (2015, MNRAS 452, 1707) correction of Young's (1967) scintillation
#: formula, ``C_Y``: the median of their sites is about 1.5 (S74).
OSBORN_CY = 1.5
#: Scale height of the atmosphere in Young's formula (m).
SCINTILLATION_SCALE_HEIGHT_M = 8000.0


def scintillation_sigma(
    aperture_mm: float,
    exposure_s: float | None,
    airmass: float | None,
    height_m: float | None = 0.0,
    c_y: float = OSBORN_CY,
) -> float:
    """Relative flux sigma of scintillation for one star (S74), 0 when unknown.

    Young's formula with Osborn et al.'s coefficient,
    ``sigma^2 = 1e-5 C_Y^2 D^(-4/3) t^(-1) X^3 exp(-2 h / 8000 m)`` (D in m, t in
    s): the long-exposure regime, independent between stars more than a few
    arcseconds apart. Through 30 mm in 10 s at airmass 1 and sea level it is
    0.0155 (0.017 mag). A 30 mm aperture is near the Fresnel scale, where the
    formula's D^(-4/3) is least certain: the RR Lyr star pairs' excess scatter over
    their photon errors measures 0.014-0.020 mag per star (notes S74).
    """
    try:
        d_m = float(aperture_mm) / 1000.0
        t = float(exposure_s) if exposure_s is not None else math.nan
        x = float(airmass) if airmass is not None else math.nan
        h = float(height_m or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not (d_m > 0 and math.isfinite(t) and t > 0 and math.isfinite(x) and x >= 1.0):
        return 0.0
    if not math.isfinite(h):
        h = 0.0
    var = (
        1e-5
        * c_y
        * c_y
        * d_m ** (-4.0 / 3.0)
        / t
        * x**3
        * math.exp(-2.0 * h / SCINTILLATION_SCALE_HEIGHT_M)
    )
    return math.sqrt(var)


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
