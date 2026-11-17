"""Ensemble differential photometry (notes/photometry_plan.md §6 C2).

Zero-point from a comparison ensemble (weighted mean of catalog − instrumental in
the chosen band, S71), then the target magnitude + an honest uncertainty that
combines the target's photon error with the zero point's error.
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
    zp_rms: float | None = None  # ensemble scatter about the zero-point (weighted, S71)
    formal_mag_err: float | None = None  # before the run-level systematic floor
    zp_err: float | None = None  # the zero point's own error, in formal_mag_err (S71)
    #: S71: the comparison holding more than half the ensemble's weight disagrees with
    #: the weighted mean of the others by more than 2.5 combined σ: the point rests on
    #: one star that its ensemble contradicts, and is flagged suspect.
    suspect: bool = False


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


#: Outlier threshold for the ensemble clip, in normalised residuals (P3, S71).
_CLIP_SIGMA = 2.5
#: Error floor of every comparison (10 mmag), in its weight and its clip
#: residual (S71): one bright comparison cannot take all the weight, and photon
#: noise alone must not reject a good one when the ensemble is near-identical.
_CLIP_FLOOR_MAG = 0.01
#: Maximum clip iterations.
_CLIP_ITERS = 2


def _weighted_median(rows: list[tuple[float, float]]) -> float:
    """Median of ``d`` over ``(d, sigma)`` rows, each weighing ``1 / sigma²`` (S71).

    The value at which half the total weight lies on either side (the mean of the
    two middle values on an exact tie); with equal weights, the plain median.
    """
    ordered = sorted(rows)
    weights = [1.0 / (s * s) for _d, s in ordered]
    half = 0.5 * sum(weights)
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if math.isclose(acc, half, rel_tol=1e-12) and i + 1 < len(ordered):
            return 0.5 * (ordered[i][0] + ordered[i + 1][0])
        if acc > half:
            return ordered[i][0]
    return ordered[-1][0]  # pragma: no cover - acc reaches the total


def ensemble_zero_point(
    comps: Iterable[tuple],
) -> tuple[float | None, float | None, int, int, float | None]:
    """Zero point from the comparisons → ``(zp, zp_rms, n, n_rejected, zp_err)``.

    ``comps`` are ``(inst_mag, cat_mag)`` or ``(inst_mag, cat_mag, inst_mag_err)``;
    a pair with a missing magnitude is skipped, a missing error counts as 0.

    S71 (inverse-variance weights): each comparison ``d = cat − inst`` weighs
    ``w = 1 / (err² + floor²)`` with the 10 mmag floor, so one bright star cannot
    take all the weight and faint ones barely move the zero point.
    ``zp = Σ w·d / Σ w``; ``zp_rms`` is the weighted sample RMS about it (the
    sample RMS when the weights are equal; 0 for one comparison); ``zp_err`` is
    ``max(sqrt(1 / Σ w), zp_rms / sqrt(n))``: the photon error of the ensemble, or
    its measured scatter when the comparisons disagree by more than their errors.

    Outlier rejection (P3, S71): with ≥3 comparisons, one whose normalised residual
    ``|d − median(d)| / sqrt(err² + floor²)`` exceeds 2.5 is dropped (≤2
    iterations, never below 2 kept). The median rather than the mean because a
    single bad comp in a small ensemble drags the mean toward itself; the
    *weighted* median, because with comparisons of very unequal errors the plain
    median sits among the noisy faint ones and clips the one bright star that
    carries the zero point (XX Cyg 2026-08-29: 13 of 22 frames).
    """
    rows, rejected = _clipped_rows(comps)
    if not rows:
        return None, None, 0, 0, None
    n = len(rows)
    weights = [1.0 / (s * s) for _d, s in rows]
    total = sum(weights)
    zp = sum(w * d for w, (d, _s) in zip(weights, rows)) / total
    if n >= 2:
        var = sum(w * (d - zp) ** 2 for w, (d, _s) in zip(weights, rows)) / total
        rms = math.sqrt(var * n / (n - 1))
    else:
        rms = 0.0
    zp_err = max(math.sqrt(1.0 / total), rms / math.sqrt(n))
    return zp, rms, n, rejected, zp_err


def _clipped_rows(comps: Iterable[tuple]) -> tuple[list[tuple[float, float]], int]:
    """The comparisons' ``(d, sigma)`` rows kept by the S71 clip, and how many it dropped
    (:func:`ensemble_zero_point`)."""
    rows = []
    for comp in comps:
        inst, cat = comp[0], comp[1]
        if inst is None or cat is None:
            continue
        err = comp[2] if len(comp) > 2 and comp[2] is not None else 0.0
        rows.append((cat - inst, math.sqrt(err * err + _CLIP_FLOOR_MAG * _CLIP_FLOOR_MAG)))
    rejected = 0
    for _ in range(_CLIP_ITERS):
        if len(rows) < 3:
            break
        med = _weighted_median(rows)
        kept = [(d, s) for d, s in rows if abs(d - med) <= _CLIP_SIGMA * s]
        if len(kept) == len(rows) or len(kept) < 2:
            break
        rejected += len(rows) - len(kept)
        rows = kept
    return rows, rejected


def dominant_disagreement(comps: Iterable[tuple]) -> tuple[float, float] | None:
    """S71: ``(weight share, z)`` when one comparison outweighs the rest and they
    contradict it, else None.

    The clip is centred on the weighted median, so a comparison holding more than half
    of the weight is never clipped: a bright comparison that is variable, blended or
    strongly coloured would carry the zero point with nothing clipped (0.30 mag off
    against 2 good faint ones: zero point +0.25). After the clip, when the heaviest
    comparison holds more than half the weight, its ``d`` is compared with the
    weighted mean of the others: ``z = |d_dom − d_others| / sqrt(σ_dom² + σ_others²)``
    (``σ_others = sqrt(1 / Σw_others)``) above :data:`_CLIP_SIGMA` is a disagreement.
    The point is flagged, not re-weighted: the plain median would clip the bright star
    on frames where the faint ones are the wrong ones (XX Cyg 2026-08-29). It takes two
    others at least: with one, there is no majority to contradict the heavy star, only
    two stars that disagree, which ``zp_err`` already carries (RR Lyr 2026-09-25 with
    its 2 comparisons: 27 of 195 frames flagged otherwise).
    """
    rows, _rejected = _clipped_rows(comps)
    if len(rows) < 3:
        return None
    weights = [1.0 / (s * s) for _d, s in rows]
    total = sum(weights)
    top = max(range(len(rows)), key=lambda i: weights[i])
    share = weights[top] / total
    if share <= 0.5:
        return None
    rest = total - weights[top]
    others = sum(w * d for i, (w, (d, _s)) in enumerate(zip(weights, rows)) if i != top) / rest
    z = abs(rows[top][0] - others) / math.sqrt(rows[top][1] ** 2 + 1.0 / rest)
    return (share, z) if z > _CLIP_SIGMA else None


def differential_mag(
    target_inst_mag: float | None,
    target_inst_err: float | None,
    comps: Iterable[tuple],
    *,
    min_comps: int = 2,
) -> DiffResult:
    """Calibrate the target against the comparison ensemble.

    ``comps`` are the comparisons' ``(inst_mag, cat_mag[, inst_mag_err])`` in the
    same band (:func:`ensemble_zero_point`). The error combines the target's photon
    error with the zero point's error ``zp_err`` (S71). ``note`` flags a
    provisional result (no flux / too few comps) and reports clipped outliers;
    ``comps_used`` counts the *kept* comps.
    """
    comps = list(comps)
    zp, rms, n, rejected, zp_err = ensemble_zero_point(comps)
    if zp is None:
        return DiffResult(None, None, None, 0, note="no valid comparisons")
    zp_rms = round(rms, 4) if rms is not None else None
    zp_err_r = round(zp_err, 4) if zp_err is not None else None
    clip_note = f"{rejected} comp(s) clipped" if rejected else ""
    if target_inst_mag is None:
        note = "; ".join(x for x in ("no target flux", clip_note) if x)
        return DiffResult(None, None, round(zp, 4), n, note=note, zp_rms=zp_rms, zp_err=zp_err_r)
    mag = target_inst_mag + zp
    terr = target_inst_err or 0.0
    ens = zp_err or 0.0
    formal_mag_err = math.sqrt(terr * terr + ens * ens)
    low = f"only {n} comparison(s)" if n < min_comps else ""
    dominant = dominant_disagreement(comps)
    dominant_note = (
        f"the comparison holding {dominant[0]:.0%} of the weight disagrees with the others"
        f" ({dominant[1]:.1f} sigma)"
        if dominant is not None
        else ""
    )
    note = "; ".join(x for x in (low, clip_note, dominant_note) if x)
    return DiffResult(
        round(mag, 4),
        round(formal_mag_err, 4),
        round(zp, 4),
        n,
        note,
        zp_rms=zp_rms,
        formal_mag_err=round(formal_mag_err, 4),
        zp_err=zp_err_r,
        suspect=dominant is not None,
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
