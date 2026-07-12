"""Focus V-curve fitting — pure, Qt-free, network-free.

An autofocus sweep samples HFD (half-flux diameter) at a series of focuser
positions; in focus the HFD reaches a minimum, so the samples trace a "V". The
canonical estimate of best focus is the vertex of a parabola fitted to that V.

This module holds that fit as a pure function so it can be unit-tested without
hardware and reused both by the :class:`AutofocusWorker` (which feeds it live
samples) and by the Focus screen (which plots the curve + vertex). Keeping it
here, off the Qt thread, mirrors ``sky_geometry`` and the rest of ``core``.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FocusResult:
    """The outcome of fitting a focuser V-curve.

    Attributes:
        best_position: Estimated best focuser position (steps).
        best_hfd:      HFD at the best position, or ``None`` if unknown.
        method:        ``"parabola"`` (vertex of a reliable fit), ``"raw"``
                       (lowest measured sample — fallback) or ``"none"`` (no
                       usable data).
        coeffs:        ``(a, b, c)`` of the fitted ``a x^2 + b x + c``, present
                       only when ``method == "parabola"``.
        samples:       The valid ``(position, hfd)`` pairs the fit used, sorted
                       by position.
    """

    best_position: int
    best_hfd: Optional[float]
    method: str
    coeffs: Optional[tuple[float, float, float]]
    samples: tuple[tuple[int, float], ...]

    @property
    def is_reliable(self) -> bool:
        """True when a real parabola minimum was found (not a raw fallback)."""
        return self.method == "parabola"

    def fit_curve(self, num: int = 100) -> tuple[list[float], list[float]]:
        """Return ``(positions, hfd)`` tracing the fitted parabola for plotting.

        Spans the sampled position range. Empty if there is no parabola fit.
        """
        if self.coeffs is None or not self.samples:
            return [], []
        a, b, c = self.coeffs
        lo = self.samples[0][0]
        hi = self.samples[-1][0]
        if hi <= lo:
            return [float(lo)], [a * lo * lo + b * lo + c]
        xs = np.linspace(lo, hi, max(2, num))
        ys = a * xs * xs + b * xs + c
        return xs.tolist(), ys.tolist()


#: Minimum relative HFD span (max−min vs min) for a sweep to count as a
#: V-curve. Below this the sweep is flat — clouds, wrong step size, optically
#: decoupled focuser — and any "best" is a fit to noise (P6).
MIN_RELATIVE_SPAN = 0.15

#: A parabola vertex may sit slightly below the lowest sample (that is the
#: point of fitting), but never meaningfully *above* it: a vertex worse than
#: a measured HFD means the samples are not a parabola (e.g. the far-defocus
#: plateau where ``compute_hfd`` saturates) and the fit landed on noise.
#: Tolerance for measurement scatter before the fit is rejected.
MAX_VERTEX_OVER_RAW = 1.2


def sweep_is_degenerate(samples: tuple[tuple[int, float], ...]) -> Optional[str]:
    """None when the sweep looks like a V-curve, else why it doesn't (P6).

    Degenerate cases: fewer than three valid samples, an HFD span under
    :data:`MIN_RELATIVE_SPAN` of the minimum (flat curve), or the minimum
    sitting on a sweep edge (the true focus is outside the scanned range —
    re-centre and re-run rather than trust an extrapolation).
    """
    if len(samples) < 3:
        return "fewer than 3 valid samples"
    hfds = [h for _, h in samples]
    mn, mx = min(hfds), max(hfds)
    if mn <= 0:
        return "non-positive HFD"
    if (mx - mn) < MIN_RELATIVE_SPAN * mn:
        return f"flat HFD curve ({mn:.2f}–{mx:.2f}, span < {MIN_RELATIVE_SPAN:.0%})"
    if hfds.index(mn) in (0, len(hfds) - 1):
        return "HFD minimum at the sweep edge — best focus outside the scanned range"
    return None


def refine_positions(center: int, spacing: int, low: int, high: int, count: int = 4) -> list[int]:
    """Fine-scan focuser positions bracketing ``center``, inside ``[low, high]``.

    ``count`` evenly split offsets strictly inside ±``spacing`` (the coarse
    interval): the coarse sweep already measured ``center`` and its ±spacing
    neighbours, so the fine pass samples the V where ``compute_hfd`` is
    actually informative. Sorted, deduplicated, ``center`` excluded.
    """
    half = max(1, count // 2)
    fractions = [i / (half + 1) for i in range(1, half + 1)]
    offsets = [round(f * spacing) for f in fractions]
    positions = {center - o for o in offsets} | {center + o for o in offsets}
    positions.discard(center)
    return sorted(p for p in positions if low <= p <= high)


def fit_v_curve(
    measurements: list[tuple[int, float]],
    low: Optional[int] = None,
    high: Optional[int] = None,
) -> FocusResult:
    """Estimate best focus from ``(position, hfd)`` samples.

    Fits a 2nd-order polynomial and returns its vertex when the fit is sound —
    the parabola must open upward (``a > 0``) and its vertex must fall within
    the scanned range. Otherwise (degenerate fit, vertex out of range, or fewer
    than three valid samples) it falls back to the lowest measured HFD. ``NaN``
    HFDs (failed frames) are dropped.

    Args:
        measurements: ``(position, hfd)`` pairs; ``hfd`` may be ``NaN``.
        low:          Lower bound for an acceptable vertex. Defaults to the
                      smallest sampled position.
        high:         Upper bound. Defaults to the largest sampled position.
    """
    valid = sorted(
        (int(p), float(h)) for p, h in measurements if h is not None and not math.isnan(h)
    )
    if not valid:
        mid = measurements[len(measurements) // 2][0] if measurements else 0
        return FocusResult(int(mid), None, "none", None, ())

    samples = tuple(valid)
    pos_arr = np.array([p for p, _ in valid], dtype=float)
    hfd_arr = np.array([h for _, h in valid], dtype=float)
    best_raw = valid[int(np.argmin(hfd_arr))]

    if low is None:
        low = int(pos_arr.min())
    if high is None:
        high = int(pos_arr.max())

    if len(valid) >= 3:
        result = _try_parabola(pos_arr, hfd_arr, low, high, best_raw, samples)
        if result is not None:
            return result

    return FocusResult(int(best_raw[0]), round(float(best_raw[1]), 2), "raw", None, samples)


def _try_parabola(
    pos_arr: np.ndarray,
    hfd_arr: np.ndarray,
    low: int,
    high: int,
    best_raw: tuple[int, float],
    samples: tuple[tuple[int, float], ...],
) -> Optional[FocusResult]:
    """Vertex of the fitted parabola, or ``None`` when the fit can't be trusted."""
    try:
        a, b, c = (float(v) for v in np.polyfit(pos_arr, hfd_arr, 2))
    except Exception as exc:  # numpy can raise on ill-conditioned input
        logger.debug("Parabola fit failed: %s", exc)
        return None
    if a <= 0:
        return None
    vertex = -b / (2.0 * a)
    if not low <= vertex <= high:
        return None
    fitted_hfd = a * vertex * vertex + b * vertex + c
    if fitted_hfd > best_raw[1] * MAX_VERTEX_OVER_RAW:
        # The "best" the parabola offers is worse than a point we actually
        # measured — the samples are not a V (far-defocus plateau + a single
        # dip). Trust the data.
        logger.warning(
            "Parabola vertex HFD %.1f worse than measured %.1f at %d "
            "— falling back to the raw minimum",
            fitted_hfd,
            best_raw[1],
            best_raw[0],
        )
        return None
    return FocusResult(int(round(vertex)), round(float(fitted_hfd), 2), "parabola", (a, b, c), samples)
