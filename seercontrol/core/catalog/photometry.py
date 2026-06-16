"""Comparison-star selection for differential photometry (Qt-free).

Given a variable star (the target) and the field's VSP comparison stars, rank the
comparisons for photometry of that target. The standard differential-photometry
criteria are: comparisons **close** to the target (same region of the chip, same
airmass/vignetting) and of **similar brightness**. VSP already guarantees they
are non-variable and calibrated, so this module just scores + orders them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .aavso import ComparisonStar, VariableStar


def separation_arcmin(ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
    """Great-circle separation between two J2000 points, in arcminutes."""
    r1, d1, r2, d2 = (math.radians(v) for v in (ra1_deg, dec1_deg, ra2_deg, dec2_deg))
    a = (
        math.sin((d2 - d1) / 2.0) ** 2
        + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2.0) ** 2
    )
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(a)))) * 60.0


@dataclass(frozen=True)
class ScoredComparison:
    """A comparison star scored against a target."""

    star: ComparisonStar
    separation_arcmin: float
    delta_mag: float | None  # |comp − target| in the chosen band, if both known


def rank_comparisons(
    target_ra_deg: float,
    target_dec_deg: float,
    comparisons: list[ComparisonStar],
    *,
    target_mag: float | None = None,
    band: str = "V",
    mag_tol: float | None = None,
    max_results: int | None = None,
) -> list[ScoredComparison]:
    """Rank ``comparisons`` for photometry of a target, closest first.

    ``target_mag`` + ``mag_tol`` (if both given) drops comparisons whose ``band``
    magnitude differs from the target by more than ``mag_tol`` (and any lacking
    that band, since they can't be judged). ``max_results`` caps the list.
    """
    scored: list[ScoredComparison] = []
    for c in comparisons:
        sep = separation_arcmin(target_ra_deg, target_dec_deg, c.ra_deg, c.dec_deg)
        cmag = c.mag(band)
        delta = abs(cmag - target_mag) if (cmag is not None and target_mag is not None) else None
        if mag_tol is not None and target_mag is not None:
            if delta is None or delta > mag_tol:
                continue  # too far in brightness, or unmeasured in this band
        scored.append(ScoredComparison(star=c, separation_arcmin=sep, delta_mag=delta))
    scored.sort(key=lambda s: s.separation_arcmin)
    if max_results is not None:
        scored = scored[:max_results]
    return scored


def comparisons_for_variable(
    variable: VariableStar,
    comparisons: list[ComparisonStar],
    *,
    band: str = "V",
    mag_tol: float | None = None,
    max_results: int | None = None,
) -> list[ScoredComparison]:
    """:func:`rank_comparisons` for a :class:`VariableStar`, using its brightest
    magnitude as the reference for the (optional) magnitude-similarity filter."""
    return rank_comparisons(
        variable.ra_deg,
        variable.dec_deg,
        comparisons,
        target_mag=variable.brightest_mag,
        band=band,
        mag_tol=mag_tol,
        max_results=max_results,
    )
