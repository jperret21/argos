"""Measure a target set on one solved frame (docs/photometry_plan.md §6 C4).

Glue between the catalog (``TargetSet``), the WCS and the aperture/differential
primitives: project each saved star to green px, aperture-measure it, then
calibrate every *target* against the *comparison* ensemble. Pure + Qt-free; the
per-frame cost is a handful of small aperture sums, so it runs synchronously.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from seercontrol.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar
from seercontrol.core.photometry.aperture import AperturePhot, measure_aperture
from seercontrol.core.photometry.differential import DiffResult, differential_mag


@dataclass
class TargetResult:
    """A target star's per-frame outcome."""

    star: TargetStar
    diff: DiffResult | None  # differential magnitude (None when uncomputable)
    phot: AperturePhot | None  # raw aperture measurement


def _cat_mag(star: TargetStar, band: str) -> float | None:
    """Catalog magnitude in ``band`` (green ≈ V/TG), falling back to V."""
    return star.mags.get(band) if band in star.mags else star.mags.get("V")


def measure_targets(
    green: np.ndarray,
    wcs,
    target_set: TargetSet,
    *,
    r_ap: float,
    r_in: float,
    r_out: float,
    egain: float = 1.0,
    read_noise_e: float = 1.5,
    sat_adu: float = 60000.0,
    band: str = "V",
    min_comps: int = 2,
) -> list[TargetResult]:
    """Aperture-measure every saved star, then calibrate targets vs comparisons.

    ``wcs`` only needs ``world_to_pixel_deg(ra_deg, dec_deg) -> (x, y)`` (green px).
    Comparisons without a catalog magnitude in ``band``/V are skipped from the
    ensemble. Returns one :class:`TargetResult` per ``role == 'target'`` star.
    """
    measured: list[tuple[TargetStar, AperturePhot | None]] = []
    for s in target_set.stars:
        x, y = wcs.world_to_pixel_deg(s.ra_deg, s.dec_deg)
        phot = measure_aperture(
            green, float(x), float(y), r_ap, r_in, r_out,
            egain=egain, read_noise_e=read_noise_e, sat_adu=sat_adu,
        )
        measured.append((s, phot))

    comps = [
        (phot.inst_mag, _cat_mag(s, band))
        for s, phot in measured
        if s.role == ROLE_COMPARISON
        and phot is not None
        and phot.inst_mag is not None
        and _cat_mag(s, band) is not None
        and not phot.saturated
    ]

    out: list[TargetResult] = []
    for s, phot in measured:
        if s.role != ROLE_TARGET:
            continue
        if phot is None or phot.inst_mag is None:
            out.append(TargetResult(s, None, phot))
            continue
        diff = differential_mag(phot.inst_mag, phot.inst_mag_err, comps, min_comps=min_comps)
        out.append(TargetResult(s, diff, phot))
    return out
