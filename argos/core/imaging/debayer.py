"""Bayer demosaicing, CFA channel split and focus metrics for the IMX585 (GRBG).

**Data pipeline ≠ display pipeline** (see ``docs/capture_panel.md`` §0): every
function here takes the raw linear CFA array and returns a *new* display or
measurement array. The raw array is never mutated — it is what gets written to
FITS (linear, 16-bit, ``BAYERPAT='GRBG'``).

GRBG tile (2×2)::

    G R
    B G

CFA pixel positions in a raw array (H, W) — these are **real sensor pixels**,
no interpolation (the photometry / astrometry measurement primitive)::

    G1 = arr[0::2, 0::2]    R  = arr[0::2, 1::2]
    B  = arr[1::2, 0::2]    G2 = arr[1::2, 1::2]

All split planes have shape (H//2, W//2).
"""

from __future__ import annotations

import numpy as np

BAYER_PATTERN = "GRBG"

# --------------------------------------------------------------------------- #
# View identifiers. Only the five observer-facing views belong in ``VIEWS``.  #
# --------------------------------------------------------------------------- #

VIEW_SUPERPIXEL = "Super-pixel"
VIEW_INTERP = "Interpolated"
VIEW_RAW = "Raw CFA"
VIEW_R = "R"
VIEW_G = "G"
VIEW_B = "B"
VIEW_G1 = "G1"
VIEW_G2 = "G2"
VIEW_LUM = "Luminance"

#: Ordered for the image toolbar.  Every one is rendered onto the *full sensor
#: geometry*, so changing display mode never changes the annotation coordinate
#: frame or the apparent field size.
VIEWS: tuple[str, ...] = (
    VIEW_SUPERPIXEL,
    VIEW_RAW,
    VIEW_R,
    VIEW_G,
    VIEW_B,
)

#: Views that return a real-pixel single plane (valid for measurement).
MEASUREMENT_CHANNELS: tuple[str, ...] = (VIEW_R, VIEW_G, VIEW_B, VIEW_G1, VIEW_G2, VIEW_LUM)


# --------------------------------------------------------------------------- #
# CFA split — the measurement primitive (real pixels, no interpolation)        #
# --------------------------------------------------------------------------- #


def split_cfa(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split a GRBG raw array into ``(r, g1, g2, b)`` real-pixel planes.

    Each plane has shape (H//2, W//2), same dtype — real sensor pixels, no
    interpolation, so noise/flux statistics are preserved. Odd dimensions are
    cropped by one row/column so the four planes line up.
    """
    h = arr.shape[0] - (arr.shape[0] % 2)
    w = arr.shape[1] - (arr.shape[1] % 2)
    a = arr[:h, :w]
    r = a[0::2, 1::2]
    g1 = a[0::2, 0::2]
    g2 = a[1::2, 1::2]
    b = a[1::2, 0::2]
    return r, g1, g2, b


def extract_plane(arr: np.ndarray, channel: str) -> np.ndarray:
    """Return a single real-pixel plane (uint16, H//2×W//2) for a CFA channel.

    ``'G'`` averages the two green pixels (both real greens — no cross-colour
    interpolation), which is the OSC "TG" photometric channel. ``'Luminance'``
    is a weighted grey of the super-pixel.

    Args:
        arr:     Raw 2-D array (GRBG).
        channel: One of R, G, B, G1, G2, Luminance.

    Raises:
        ValueError: for an unknown channel.
    """
    r, g1, g2, b = split_cfa(arr)
    if channel == VIEW_R:
        return r
    if channel == VIEW_G1:
        return g1
    if channel == VIEW_G2:
        return g2
    if channel == VIEW_B:
        return b
    if channel == VIEW_G:
        return ((g1.astype(np.uint32) + g2.astype(np.uint32)) >> 1).astype(np.uint16)
    if channel == VIEW_LUM:
        g = (g1.astype(np.float32) + g2.astype(np.float32)) * 0.5
        lum = 0.299 * r.astype(np.float32) + 0.587 * g + 0.114 * b.astype(np.float32)
        return lum.astype(np.uint16)
    raise ValueError(f"unknown channel {channel!r}")


# --------------------------------------------------------------------------- #
# Debayer modes                                                                #
# --------------------------------------------------------------------------- #


def superpixel_rgb(arr: np.ndarray) -> np.ndarray:
    """2×2 → 1 RGB pixel, no interpolation. Returns (H//2, W//2, 3) uint16.

    The scientifically clean colour preview: every output pixel uses only real
    sensor samples, introducing no spatial correlation.
    """
    r, g1, g2, b = split_cfa(arr)
    g = ((g1.astype(np.uint32) + g2.astype(np.uint32)) >> 1).astype(np.uint16)
    h = min(r.shape[0], g.shape[0], b.shape[0])
    w = min(r.shape[1], g.shape[1], b.shape[1])
    return np.stack([r[:h, :w], g[:h, :w], b[:h, :w]], axis=2)


def expand_cfa_cells(plane: np.ndarray, sensor_shape: tuple[int, int]) -> np.ndarray:
    """Magnify a CFA-cell view onto the original sensor geometry.

    ``superpixel_rgb`` and individual CFA planes naturally live at half the
    sensor dimensions.  Showing them at that size made the image jump whenever
    the observer switched to Raw CFA or back, and invited overlay-coordinate
    mistakes.  Nearest-neighbour expansion is intentional: it introduces no
    synthetic image detail; each 2×2 sensor cell simply occupies its original
    on-screen footprint.
    """
    h, w = (int(sensor_shape[0]), int(sensor_shape[1]))
    if plane.size == 0:
        shape = (h, w) + plane.shape[2:]
        return np.zeros(shape, dtype=plane.dtype)
    expanded = np.repeat(np.repeat(plane, 2, axis=0), 2, axis=1)
    # A raw FITS can have an odd trailing row/column. split_cfa rightly drops
    # an incomplete Bayer cell; repeat the final complete cell for display so
    # all view modes still retain the exact same outer geometry.
    if expanded.shape[0] < h:
        expanded = np.concatenate((expanded, expanded[-1:, ...]), axis=0)
    if expanded.shape[1] < w:
        expanded = np.concatenate((expanded, expanded[:, -1:, ...]), axis=1)
    return expanded[:h, :w, ...]


def downsample_cfa(arr: np.ndarray, factor: int = 2) -> np.ndarray:
    """Reduce a raw CFA frame while preserving its Bayer tile.

    A plain ``arr[::2, ::2]`` retains only one Bayer colour (for GRBG, G1),
    then wrongly presents those samples as a complete colour mosaic.  Instead,
    downsample each like-colour plane and interleave the four results back into
    a smaller GRBG mosaic.  This is display-only; saved FITS and photometry
    continue to use the untouched full-resolution frame.
    """
    factor = max(1, int(factor))
    if factor == 1:
        return arr
    r, g1, g2, b = split_cfa(arr)
    h = (r.shape[0] // factor) * factor
    w = (r.shape[1] // factor) * factor
    if h == 0 or w == 0:
        return arr

    def reduce_plane(plane: np.ndarray) -> np.ndarray:
        cropped = plane[:h, :w].astype(np.uint64)
        reduced = cropped.reshape(h // factor, factor, w // factor, factor).mean(axis=(1, 3))
        return np.rint(reduced).astype(arr.dtype)

    rr, gg1, gg2, bb = (reduce_plane(plane) for plane in (r, g1, g2, b))
    out = np.empty((rr.shape[0] * 2, rr.shape[1] * 2), dtype=arr.dtype)
    out[0::2, 0::2] = gg1
    out[0::2, 1::2] = rr
    out[1::2, 0::2] = bb
    out[1::2, 1::2] = gg2
    return out


def neutralise_rgb_for_display(rgb: np.ndarray) -> np.ndarray:
    """Apply a background-neutral display balance to a linear RGB preview.

    OSC sensors and light-pollution filters commonly leave the green background
    brighter than red/blue.  The balance is deliberately confined to preview
    RGB values: raw data, per-channel histograms and photometry are unchanged.
    """
    if rgb.ndim != 3 or rgb.shape[-1] != 3:
        return rgb
    values = rgb.astype(np.float32, copy=False)
    backgrounds = np.median(values.reshape(-1, 3), axis=0)
    valid = backgrounds > 0
    if not np.any(valid):
        return rgb
    reference = float(np.median(backgrounds[valid]))
    gains = np.ones(3, dtype=np.float32)
    gains[valid] = np.clip(reference / backgrounds[valid], 0.25, 4.0)
    balanced = values * gains
    return np.clip(balanced, 0, np.iinfo(rgb.dtype).max).astype(rgb.dtype)


def bilinear_rgb(arr: np.ndarray) -> np.ndarray:
    """Full-resolution bilinear demosaic — COSMETIC ONLY.

    Interpolates each missing colour from its known neighbours, which correlates
    pixels and breaks photometric statistics. Use for framing/presentation, never
    for measurement. Returns (H, W, 3) uint16.
    """
    a = arr.astype(np.float32)
    planes = []
    for known, positions in (
        ("R", (slice(0, None, 2), slice(1, None, 2))),
        ("G", None),
        ("B", (slice(1, None, 2), slice(0, None, 2))),
    ):
        value = np.zeros_like(a)
        mask = np.zeros_like(a)
        if known == "G":
            value[0::2, 0::2] = a[0::2, 0::2]
            value[1::2, 1::2] = a[1::2, 1::2]
            mask[0::2, 0::2] = 1.0
            mask[1::2, 1::2] = 1.0
        else:
            value[positions] = a[positions]
            mask[positions] = 1.0
        num = _box3_sum(value)
        den = _box3_sum(mask)
        interp = num / np.maximum(den, 1.0)
        planes.append(np.where(mask > 0, value, interp))
    rgb = np.stack(planes, axis=2)
    return np.clip(rgb, 0, 65535).astype(np.uint16)


def render_view(arr: np.ndarray, view: str) -> np.ndarray:
    """Render the raw array for a given display view (see ``VIEWS``).

    Returns a **linear** array on the original sensor geometry — 2-D uint16
    (raw / single channel) or 3-D uint16 RGB (colour modes). CFA-cell views are
    nearest-neighbour expanded rather than interpolated, preserving their
    native samples while keeping marker coordinates identical in every mode.
    The stretch stage (see ``imaging.stretch``) maps it to the screen; the
    input ``arr`` is never mutated.
    """
    if view == VIEW_RAW:
        return arr
    if view == VIEW_SUPERPIXEL:
        return expand_cfa_cells(superpixel_rgb(arr), arr.shape[:2])
    if view == VIEW_INTERP:
        return bilinear_rgb(arr)
    return expand_cfa_cells(extract_plane(arr, view), arr.shape[:2])


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _box3_sum(x: np.ndarray) -> np.ndarray:
    """Sum over each pixel's 3×3 neighbourhood (zero-padded edges)."""
    p = np.pad(x, 1, mode="constant")
    return (
        p[0:-2, 0:-2]
        + p[0:-2, 1:-1]
        + p[0:-2, 2:]
        + p[1:-1, 0:-2]
        + p[1:-1, 1:-1]
        + p[1:-1, 2:]
        + p[2:, 0:-2]
        + p[2:, 1:-1]
        + p[2:, 2:]
    )


# --------------------------------------------------------------------------- #
# HFD — Half-Flux Diameter                                                     #
# --------------------------------------------------------------------------- #


def compute_hfd(arr: np.ndarray, search_radius: int = 32) -> float | None:
    """Compute the Half-Flux Diameter of the brightest star in the frame.

    Uses the canonical green plane (densest sampling, best SNR for stars; see
    ``core/imaging/green.py``). Returns HFD in pixels (at the subsampled scale),
    or None if the frame is empty / no star.
    """
    from argos.core.imaging.green import green_plane

    g = green_plane(arr)

    bg = float(np.median(g))
    g -= bg
    np.clip(g, 0.0, None, out=g)

    total = g.sum()
    if total < 1.0:
        return None

    cy, cx = np.unravel_index(int(np.argmax(g)), g.shape)

    r = search_radius
    y0 = max(0, cy - r)
    y1 = min(g.shape[0], cy + r + 1)
    x0 = max(0, cx - r)
    x1 = min(g.shape[1], cx + r + 1)
    roi = g[y0:y1, x0:x1]

    roi_flux = roi.sum()
    if roi_flux < 1.0:
        return None

    cy_roi = cy - y0
    cx_roi = cx - x0
    ys, xs = np.mgrid[0 : roi.shape[0], 0 : roi.shape[1]]
    dist = np.sqrt((ys - cy_roi) ** 2 + (xs - cx_roi) ** 2)

    hfd = 2.0 * float((dist * roi).sum() / roi_flux)
    return round(hfd, 1)
