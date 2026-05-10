"""Bayer demosaicing and focus metrics for Seestar IMX585 (GRBG pattern).

GRBG tile (2×2):
    G R
    B G

Pixel extraction from raw array (H, W):
    R  = arr[0::2, 1::2]   even rows, odd  cols
    G1 = arr[0::2, 0::2]   even rows, even cols
    G2 = arr[1::2, 1::2]   odd  rows, odd  cols
    B  = arr[1::2, 0::2]   odd  rows, even cols

All extracted channels have shape (H//2, W//2).
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Debayer
# ---------------------------------------------------------------------------

def extract_channel(arr: np.ndarray, channel: str) -> np.ndarray:
    """Extract a display channel from a GRBG Bayer raw array.

    Args:
        arr:     Raw 2-D uint16 array, shape (H, W), GRBG Bayer pattern.
        channel: One of "raw", "R", "G", "B", "RGB".

    Returns:
        "raw"         → original arr, shape (H, W), uint16.
        "R"/"G"/"B"   → grayscale plane, shape (H//2, W//2), uint16.
        "RGB"         → colour image, shape (H//2, W//2, 3), uint8 (0–255,
                         per-channel percentile stretch for display).
    """
    if channel == "raw":
        return arr

    r  = arr[0::2, 1::2]
    g1 = arr[0::2, 0::2].astype(np.uint32)
    g2 = arr[1::2, 1::2].astype(np.uint32)
    g  = ((g1 + g2) >> 1).astype(np.uint16)
    b  = arr[1::2, 0::2]

    if channel == "R":
        return r
    if channel == "G":
        return g
    if channel == "B":
        return b

    # RGB — normalize each channel independently for display
    rgb = np.stack([_norm8(r), _norm8(g), _norm8(b)], axis=2)
    return rgb


def _norm8(ch: np.ndarray) -> np.ndarray:
    """Stretch a uint16 plane to uint8 using 1%–99% percentile."""
    ch = ch.astype(np.float32)
    lo = float(np.percentile(ch, 1))
    hi = float(np.percentile(ch, 99))
    if hi <= lo:
        hi = lo + 1.0
    out = np.clip((ch - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------------------
# HFD — Half-Flux Diameter
# ---------------------------------------------------------------------------

def compute_hfd(arr: np.ndarray, search_radius: int = 32) -> float | None:
    """Compute the Half-Flux Diameter of the brightest star in the frame.

    Uses the green channel (densest sampling, best SNR for stars).
    Returns HFD in pixels (at the subsampled scale), or None if the frame
    is empty / no star found.

    Args:
        arr:           Raw 2-D uint16 array, shape (H, W).
        search_radius: Pixel radius around the peak used for HFD integration.

    Returns:
        HFD in pixels, rounded to 1 decimal, or None.
    """
    # Green channel at half resolution (fast)
    g = arr[0::2, 0::2].astype(np.float32)

    # Subtract median background
    bg = float(np.median(g))
    g -= bg
    np.clip(g, 0.0, None, out=g)

    total = g.sum()
    if total < 1.0:
        return None

    # Peak location
    cy, cx = np.unravel_index(int(np.argmax(g)), g.shape)

    # Guard against bright hot pixels (peak should have neighbours)
    r = search_radius
    y0 = max(0, cy - r)
    y1 = min(g.shape[0], cy + r + 1)
    x0 = max(0, cx - r)
    x1 = min(g.shape[1], cx + r + 1)
    roi = g[y0:y1, x0:x1]

    roi_flux = roi.sum()
    if roi_flux < 1.0:
        return None

    # Distance map from the peak inside the ROI
    cy_roi = cy - y0
    cx_roi = cx - x0
    ys, xs = np.mgrid[0:roi.shape[0], 0:roi.shape[1]]
    dist = np.sqrt((ys - cy_roi) ** 2 + (xs - cx_roi) ** 2)

    hfd = 2.0 * float((dist * roi).sum() / roi_flux)
    return round(hfd, 1)
