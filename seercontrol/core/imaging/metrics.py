"""Per-frame quality metrics — focus (§5) and acquisition QA (§7).

Pure numpy, Qt-free, unit-tested. Computed on the green CFA plane (densest
sampling, best SNR for stars). These are *analysis* outputs — they never modify
the raw frame.

Seestar context: 2.9 µm @ 160 mm ≈ 3.74″/px (undersampled), so HFD/FWHM are
coarse — treat the trend, not the absolute value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from seercontrol.core.imaging.debayer import compute_hfd

logger = logging.getLogger(__name__)

#: Detection threshold above the sky background, in robust sigmas.
_DETECT_SIGMA = 5.0


@dataclass(frozen=True)
class FrameMetrics:
    """Quality summary of a single frame (display/QA only)."""

    hfd: float | None  # half-flux diameter of the brightest star (px, subsampled)
    star_count: int  # detected stars (local maxima above threshold)
    sky_adu: float  # median background (ADU)
    peak_adu: int  # brightest pixel in the raw frame (ADU)


def frame_metrics(raw: np.ndarray) -> FrameMetrics:
    """Compute focus + quality metrics for a raw GRBG frame."""
    g = raw[0::2, 0::2].astype(np.float32)  # green half-res
    sky = float(np.median(g))
    mad = float(np.median(np.abs(g - sky)))
    std = mad * 1.4826 if mad > 0 else float(g.std())
    threshold = sky + _DETECT_SIGMA * std
    return FrameMetrics(
        hfd=compute_hfd(raw),
        star_count=_count_stars(g, threshold),
        sky_adu=sky,
        peak_adu=int(raw.max()),
    )


def _count_stars(g: np.ndarray, threshold: float) -> int:
    """Count 3×3 local maxima above ``threshold`` (cheap star-count proxy)."""
    above = g > threshold
    if not above.any():
        return 0
    is_max = np.ones(g.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            shifted = np.roll(np.roll(g, dy, axis=0), dx, axis=1)
            is_max &= g >= shifted
    return int(np.count_nonzero(above & is_max))
