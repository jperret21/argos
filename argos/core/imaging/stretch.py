"""Display stretch transforms + measurement stats — display/analysis only.

Pure numpy, Qt-free, unit-tested. None of this touches the raw data written to
FITS (see ``docs/capture_panel.md`` §0/§3): ``apply_stretch`` returns a *new*
uint8 array for the screen; the linear array is passed in unchanged.
"""

from __future__ import annotations

import numpy as np

from argos.core.imaging.debayer import split_cfa

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


def quantization_step(arr: np.ndarray, sample: int = 200_000, min_fraction: float = 0.9) -> int:
    """Recover the ADU quantization step of a raw frame from the data itself.

    The Seestar's IMX-series sensor has a 12-bit ADC but the driver delivers
    frames *left-shifted* into 16-bit, so real pixel values land on a grid of
    ``2**(16-12) = 16`` ADU (field frames: sky~1104, max=65520=4095<<4). If the
    histogram bins are narrower than that grid, every other bin is empty and the
    curve degenerates into a comb / "block of spikes" instead of a continuous
    line — exactly the field report this fixes.

    We derive the step *from the pixels* rather than hardcoding 16 (or blindly
    trusting ``camera.adc_bits``) so the histogram stays correct if the driver
    changes bit-depth or a different sensor is used. Because the quantization
    comes from a bit **left-shift**, the grid step is always a power of two, so
    we simply find the *largest* power-of-two grid that most pixels lie on:
    ``mean(pixels % q == 0)`` is monotonically non-increasing in ``q`` (a
    multiple of 32 is also a multiple of 16), so we climb ``q = 2, 4, 8, …`` and
    stop at the first grid fewer than ``min_fraction`` of pixels satisfy.

    Why this and not GCD / bit-mask / unique-value gaps: real frames carry ~0.1%
    off-grid stray pixels (Seestar's own processing leaves a few non-multiples of
    16). Those strays collapse GCD/OR-reduce to 1 and can drag a median-gap
    estimate off the true step when the frame has few distinct levels. Counting
    the *pixel* fraction on each grid is immune to a handful of strays, and the
    ``min_fraction`` gate naturally returns 1 for genuinely *continuous* data
    (random frames: only ~50% are even), so those bin normally.

    Subsampled with a stride for speed (this runs per preview frame): a few ms on
    a 3840x2160 frame.

    Returns the step in ADU (a power of two), or 1 when no dominant grid exists.
    """
    flat = np.asarray(arr).ravel()
    if flat.size > sample:
        flat = flat[:: flat.size // sample]
    if flat.size == 0:
        return 1
    step = 1
    for bit in range(1, 16):  # candidate grids 2, 4, …, 32768 ADU
        q = 1 << bit
        if float(np.count_nonzero(flat % q == 0)) / flat.size >= min_fraction:
            step = q
        else:
            break
    return step


def _histogram_edges(raw: np.ndarray, bins: int, lo: float, hi: float) -> np.ndarray:
    """Bin edges snapped to the frame's ADU quantization grid (anti-comb).

    For a genuinely quantized frame (step ``q >= 2``) we:

    * widen the bin to a whole multiple of ``q`` — never narrower than the grid,
      since sub-grid bins are what create the comb — while still aiming for
      roughly ``bins`` bins (so a wide, bright frame keeps full resolution and a
      narrow sky frame drops to ~range/q bins, which is all the real levels it
      has);
    * offset the edges by half a step so each quantization level sits at a bin
      *centre*, never on an edge (a level landing on a float edge would beat
      between the two neighbouring bins and reintroduce a comb).

    This is honest, not cosmetic smoothing: bins that are empty because a level
    is *truly* absent stay empty — we only remove the binning artefact, never
    interpolate values into ADU levels the sensor never produced.

    Continuous data (``q == 1``) keeps the original uniform ``bins`` edges.
    """
    q = quantization_step(raw)
    if q < 2:
        return np.linspace(lo, hi, bins + 1)
    target_w = (hi - lo) / bins
    width = max(1, int(round(target_w / q))) * q
    # Start half a step below the lowest grid level at/under ``lo`` so levels
    # fall at bin centres.
    start = (np.floor(lo / q) - 0.5) * q
    nbins = max(1, int(np.ceil((hi - start) / width)))
    return start + width * np.arange(nbins + 1)


def channel_histograms(
    raw: np.ndarray, bins: int = 128, lo: float = 0.0, hi: float = 65535.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-channel (R, G, B) histograms from the raw CFA, on real pixels.

    Binned over ``[lo, hi]`` (pass the frame's actual data range so the curves
    fill the plot instead of collapsing to the left edge). Edges are snapped to
    the sensor's ADU quantization grid (see :func:`_histogram_edges`) so quantized
    frames render as a continuous curve rather than a comb of spikes. ``bins`` is
    the *target* resolution; the effective count may be lower when the data has
    fewer real ADU levels than that. Returns ``(centers, r_counts, g_counts,
    b_counts)``.
    """
    r, g1, g2, b = split_cfa(raw)
    g = (g1.astype(np.uint32) + g2.astype(np.uint32)) >> 1
    if hi <= lo:
        hi = lo + 1.0
    edges = _histogram_edges(raw, bins, lo, hi)
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
