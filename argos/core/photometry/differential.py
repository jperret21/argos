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
    zp_rms: float | None = None  # ensemble scatter about the zero-point
    formal_mag_err: float | None = None  # before the run-level systematic floor


@dataclass(frozen=True)
class RelativeFluxResult:
    """Unnormalised target/comparison ensemble flux ratio.

    ``flux_ratio`` is ``F_target / sum(F_comparisons)``.  It needs no
    catalogue magnitudes, unlike :class:`DiffResult`, and is intended for the
    live transit preview.  Normalising to an out-of-transit baseline and
    detrending remain post-processing operations.
    """

    flux_ratio: float | None
    flux_ratio_err: float | None
    comps_used: int
    note: str = ""


#: Outlier threshold for the ensemble clip, in robust sigmas (P3).
_CLIP_SIGMA = 2.5
#: Floor on the clip threshold — with 3–4 near-identical comps the MAD can be
#: ~0 and photon noise alone must not reject a good comp (10 mmag).
_CLIP_FLOOR_MAG = 0.01
#: Maximum clip iterations.
_CLIP_ITERS = 2


def _median(values: list[float]) -> float:
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else 0.5 * (s[mid - 1] + s[mid])


def ensemble_zero_point(
    comps: Iterable[tuple[float | None, float | None]],
) -> tuple[float | None, float | None, int, int]:
    """Zero-point from ``(inst_mag, cat_mag)`` pairs → ``(zp, zp_rms, n, n_rejected)``.

    ``zp = mean(cat − inst)`` over the kept pairs; ``zp_rms`` is the sample RMS
    about it (0 for a single comp). Pairs with a missing magnitude are skipped.

    Outlier rejection (P3): with ≥3 pairs, pairs deviating from the *median*
    by more than ``max(2.5 · 1.4826 · MAD, 10 mmag)`` are dropped (≤2
    iterations). Median+MAD rather than mean+RMS because a single bad comp in
    a small ensemble inflates the RMS enough to hide itself.
    """
    diffs = [cat - inst for inst, cat in comps if inst is not None and cat is not None]
    if not diffs:
        return None, None, 0, 0

    rejected = 0
    for _ in range(_CLIP_ITERS):
        if len(diffs) < 3:
            break
        med = _median(diffs)
        mad = _median([abs(d - med) for d in diffs])
        threshold = max(_CLIP_SIGMA * 1.4826 * mad, _CLIP_FLOOR_MAG)
        kept = [d for d in diffs if abs(d - med) <= threshold]
        if len(kept) == len(diffs) or len(kept) < 2:
            break
        rejected += len(diffs) - len(kept)
        diffs = kept

    n = len(diffs)
    zp = sum(diffs) / n
    rms = math.sqrt(sum((d - zp) ** 2 for d in diffs) / (n - 1)) if n >= 2 else 0.0
    return zp, rms, n, rejected


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
    ``rms/√n``. ``note`` flags a provisional result (no flux / too few comps)
    and reports clipped outliers; ``comps_used`` counts the *kept* comps.
    """
    comps = list(comps)
    zp, rms, n, rejected = ensemble_zero_point(comps)
    if zp is None:
        return DiffResult(None, None, None, 0, note="no valid comparisons")
    zp_rms = round(rms, 4) if rms is not None else None
    clip_note = f"{rejected} comp(s) clipped" if rejected else ""
    if target_inst_mag is None:
        note = "; ".join(x for x in ("no target flux", clip_note) if x)
        return DiffResult(None, None, round(zp, 4), n, note=note, zp_rms=zp_rms)
    mag = target_inst_mag + zp
    terr = target_inst_err or 0.0
    ens = (rms / math.sqrt(n)) if (rms and n) else 0.0
    formal_mag_err = math.sqrt(terr * terr + ens * ens)
    low = f"only {n} comparison(s)" if n < min_comps else ""
    note = "; ".join(x for x in (low, clip_note) if x)
    return DiffResult(
        round(mag, 4),
        round(formal_mag_err, 4),
        round(zp, 4),
        n,
        note,
        zp_rms=zp_rms,
        formal_mag_err=round(formal_mag_err, 4),
    )


def relative_flux(
    target_flux_adu: float | None,
    target_snr: float | None,
    comparisons: Iterable[tuple[float | None, float | None]],
    *,
    min_comps: int = 2,
) -> RelativeFluxResult:
    """Return a raw flux ratio and propagated photon-noise uncertainty.

    Each comparison is ``(flux_adu, snr)``. Invalid/non-positive fluxes and
    non-positive SNR values are excluded.  The ensemble is deliberately the
    *sum* of comparison fluxes: it has the correct ratio uncertainty and does
    not require catalogue magnitudes.  It is not an out-of-transit-normalised
    or detrended science product.
    """
    if target_flux_adu is None or target_flux_adu <= 0 or not target_snr or target_snr <= 0:
        return RelativeFluxResult(None, None, 0, "no valid target flux")
    comps = [(float(f), float(s)) for f, s in comparisons if f and f > 0 and s and s > 0]
    if not comps:
        return RelativeFluxResult(None, None, 0, "no valid comparisons")
    comp_flux = sum(f for f, _snr in comps)
    ratio = float(target_flux_adu) / comp_flux
    target_fractional_err = 1.0 / float(target_snr)
    comp_variance = sum((f / snr) ** 2 for f, snr in comps)
    comp_fractional_err = math.sqrt(comp_variance) / comp_flux
    err = ratio * math.sqrt(target_fractional_err**2 + comp_fractional_err**2)
    note = f"only {len(comps)} comparison(s)" if len(comps) < min_comps else ""
    return RelativeFluxResult(ratio, err, len(comps), note)
