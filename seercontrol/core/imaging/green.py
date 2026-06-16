"""The canonical green plane — one definition for the whole science stack.

See ``docs/photometry_plan.md`` §1.4. Star detection, FWHM/HFD, ``measure_star_at``
and the plate-solver all measure on the **green half-res plane**. Historically two
slightly different greens were used (``metrics`` sampled G1 only, the solver used
``debayer.extract_plane(VIEW_G)`` = (G1+G2)/2). They shared the same pixel grid but
not the same values. This module is the single source of truth so they can never
drift again.

Definition: the per-tile average of the two GRBG green samples, **(G1+G2)/2**, on
the **G1 grid** (top-left green of each 2×2 tile), shape ``(H//2, W//2)``, float32.

Why averaged (not G1 only): ≈√2 better SNR for the detector and the solver — the
difference between a short live sub solving or not. The two greens are sampled one
pixel apart on the diagonal, so the averaged plane is the G1 grid broadened by
≤0.5 green px (≈1 raw px ≈ 3.7″) — an accepted, documented systematic.

``debayer.extract_plane(VIEW_G)`` is the uint16 sibling of :func:`green_plane`
(same grid, integer floor instead of float round); it is what the display "G"
channel and the solver's FITS use. Keep the two in lock-step.
"""

from __future__ import annotations

import numpy as np

GRBG_BAYER = "GRBG"


def green_shape(raw: np.ndarray) -> tuple[int, int]:
    """Return the green plane's ``(h, w)`` = ``(H//2, W//2)``."""
    return raw.shape[0] // 2, raw.shape[1] // 2


def green_plane(raw: np.ndarray) -> np.ndarray:
    """Return the ``(G1+G2)/2`` green plane as float32, shape ``(H//2, W//2)``.

    GRBG tile: ``G1 = raw[0::2, 0::2]``, ``G2 = raw[1::2, 1::2]``. Odd dimensions
    are cropped by one row/column so the two greens line up (same convention as
    :func:`seercontrol.core.imaging.debayer.split_cfa`).
    """
    h = raw.shape[0] - (raw.shape[0] % 2)
    w = raw.shape[1] - (raw.shape[1] % 2)
    a = raw[:h, :w]
    g1 = a[0::2, 0::2].astype(np.float32)
    g2 = a[1::2, 1::2].astype(np.float32)
    return (g1 + g2) * 0.5
