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
        try:
            a, b, c = (float(v) for v in np.polyfit(pos_arr, hfd_arr, 2))
            if a > 0:
                vertex = -b / (2.0 * a)
                if low <= vertex <= high:
                    fitted_hfd = a * vertex * vertex + b * vertex + c
                    return FocusResult(
                        int(round(vertex)),
                        round(float(fitted_hfd), 2),
                        "parabola",
                        (a, b, c),
                        samples,
                    )
        except Exception as exc:  # numpy can raise on ill-conditioned input
            logger.debug("Parabola fit failed: %s", exc)

    return FocusResult(int(best_raw[0]), round(float(best_raw[1]), 2), "raw", None, samples)
