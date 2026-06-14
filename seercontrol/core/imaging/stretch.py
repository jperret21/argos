"""Display stretch transforms + measurement stats — display/analysis only.

Pure numpy, Qt-free, unit-tested. None of this touches the raw data written to
FITS (see ``docs/capture_panel.md`` §0/§3): ``apply_stretch`` returns a *new*
uint8 array for the screen; the linear array is passed in unchanged.
"""

from __future__ import annotations

import numpy as np

from seercontrol.core.imaging.debayer import split_cfa

STRETCH_LINEAR = "Linear"
STRETCH_LOG = "Log"
STRETCH_ASINH = "Asinh"
STRETCH_MODES: tuple[str, ...] = (STRETCH_LINEAR, STRETCH_LOG, STRETCH_ASINH)

# Steepness of the non-linear transfers (display aesthetics only).
_LOG_K = 1000.0
_ASINH_K = 30.0


def auto_levels(arr: np.ndarray, lo_pct: float = 1.0, hi_pct: float = 99.0) -> tuple[float, float]:
    """Return (black, white) display levels from percentiles of ``arr``."""
    flat = np.asarray(arr, dtype=np.float32).ravel()
    black = float(np.percentile(flat, lo_pct))
    white = float(np.percentile(flat, hi_pct))
    if white <= black:
        white = black + 1.0
    return black, white


def auto_stf(
    arr: np.ndarray, target_bg: float = 0.25, shadow_clip: float = 2.8
) -> tuple[float, float, float]:
    """PixInsight-style auto screen-transfer: returns (black, white, midtones).

    Robust median/MAD shadow clip + a midtones value that maps the median to
    ``target_bg`` — brings out faint signal without blowing the stars, so astro
    frames look right with no manual tweaking. Display only.
    """
    a = np.asarray(arr, dtype=np.float32).ravel()
    med = float(np.median(a))
    mad = float(np.median(np.abs(a - med)))
    sigma = mad * 1.4826 if mad > 0 else (float(a.std()) or 1.0)
    black = max(float(a.min()), med - shadow_clip * sigma)
    white = float(np.percentile(a, 99.8))  # clip a few hot pixels, keep the stars
    if white <= black:
        white = black + 1.0
    x0 = min(max((med - black) / (white - black), 1e-4), 0.5)
    denom = 2.0 * target_bg * x0 - target_bg - x0
    midtones = (x0 * (target_bg - 1.0)) / denom if denom != 0 else 0.5
    return black, white, min(max(midtones, 0.01), 0.99)


def apply_stretch(
    arr: np.ndarray,
    black: float,
    white: float,
    mode: str = STRETCH_LINEAR,
    midtones: float = 0.5,
) -> np.ndarray:
    """Map ``arr`` through black/white + transfer + midtones to a uint8 display array.

    Works on 2-D (grayscale) or 3-D (RGB) input. ``midtones`` is a PixInsight-style
    MTF balance in (0, 1); 0.5 is neutral. The input array is not modified.
    """
    a = np.asarray(arr, dtype=np.float32)
    if white <= black:
        white = black + 1.0
    n = np.clip((a - black) / (white - black), 0.0, 1.0)

    if mode == STRETCH_LOG:
        n = np.log1p(_LOG_K * n) / np.log1p(_LOG_K)
    elif mode == STRETCH_ASINH:
        n = np.arcsinh(_ASINH_K * n) / np.arcsinh(_ASINH_K)

    m = float(np.clip(midtones, 0.001, 0.999))
    if abs(m - 0.5) > 1e-3:
        n = _mtf(n, m)

    return (np.clip(n, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _mtf(x: np.ndarray, m: float) -> np.ndarray:
    """PixInsight midtones transfer function (maps [0,1]→[0,1], mtf(m)=0.5)."""
    return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m)


def channel_histograms(
    raw: np.ndarray, bins: int = 128, lo: float = 0.0, hi: float = 65535.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-channel (R, G, B) histograms from the raw CFA, on real pixels.

    Binned over ``[lo, hi]`` (pass the frame's actual data range so the curves
    fill the plot instead of collapsing to the left edge).
    Returns ``(centers, r_counts, g_counts, b_counts)``.
    """
    r, g1, g2, b = split_cfa(raw)
    g = (g1.astype(np.uint32) + g2.astype(np.uint32)) >> 1
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, bins + 1)
    rh, _ = np.histogram(r, bins=edges)
    gh, _ = np.histogram(g, bins=edges)
    bh, _ = np.histogram(b, bins=edges)
    centers = (edges[:-1] + edges[1:]) * 0.5
    return centers, rh, gh, bh


def region_stats(plane: np.ndarray) -> dict[str, float]:
    """Summary statistics of a region (for sky background / noise / object level)."""
    a = np.asarray(plane, dtype=np.float64)
    return {
        "n": float(a.size),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "std": float(a.std()),
        "min": float(a.min()),
        "max": float(a.max()),
    }
