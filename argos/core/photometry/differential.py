"""Ensemble differential photometry (docs/photometry_plan.md §6 C2).

Zero-point from a comparison ensemble (mean of catalog − instrumental in the
chosen band), then the target magnitude + an honest uncertainty that combines the
target's photon error with the ensemble scatter (the realistic field error).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class DiffResult:
    """A single differential-magnitude estimate."""

    mag: float | None
    mag_err: float | None
    zero_point: float | None
    comps_used: int
    note: str = ""  # "" when fully calibrated; else why it's provisional


def ensemble_zero_point(
    comps: Iterable[tuple[float | None, float | None]],
) -> tuple[float | None, float | None, int]:
    """Zero-point from ``(inst_mag, cat_mag)`` pairs → ``(zp, zp_rms, n)``.

    ``zp = mean(cat − inst)``; ``zp_rms`` is the sample RMS about it (0 for a
    single comp). Pairs with a missing magnitude are skipped.
    """
    diffs = [
        cat - inst for inst, cat in comps if inst is not None and cat is not None
    ]
    n = len(diffs)
    if n == 0:
        return None, None, 0
    zp = sum(diffs) / n
    rms = math.sqrt(sum((d - zp) ** 2 for d in diffs) / (n - 1)) if n >= 2 else 0.0
    return zp, rms, n


def differential_mag(
    target_inst_mag: float | None,
    target_inst_err: float | None,
    comps: Iterable[tuple[float | None, float | None]],
    *,
    min_comps: int = 2,
) -> DiffResult:
    """Calibrate the target against the comparison ensemble.

    ``comps`` are the comparisons' ``(inst_mag, cat_mag)`` in the same band. The
    error combines the target's photon error with the ensemble standard error
    ``rms/√n``. ``note`` flags a provisional result (no flux / too few comps).
    """
    comps = list(comps)
    zp, rms, n = ensemble_zero_point(comps)
    if zp is None:
        return DiffResult(None, None, None, 0, note="no valid comparisons")
    if target_inst_mag is None:
        return DiffResult(None, None, round(zp, 4), n, note="no target flux")
    mag = target_inst_mag + zp
    terr = target_inst_err or 0.0
    ens = (rms / math.sqrt(n)) if (rms and n) else 0.0
    mag_err = math.sqrt(terr * terr + ens * ens)
    note = "" if n >= min_comps else f"only {n} comparison(s)"
    return DiffResult(round(mag, 4), round(mag_err, 4), round(zp, 4), n, note)
