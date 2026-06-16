"""Tests for the canonical green plane (Qt-free, no hardware)."""

from __future__ import annotations

import numpy as np

from seercontrol.core.imaging.debayer import VIEW_G, extract_plane
from seercontrol.core.imaging.green import green_plane, green_shape


def test_green_shape_is_half() -> None:
    assert green_shape(np.zeros((100, 80), np.uint16)) == (50, 40)


def test_green_shape_floors_odd_dims() -> None:
    # Odd dimensions floor-divide (the spare row/col is dropped on extraction).
    assert green_shape(np.zeros((101, 81), np.uint16)) == (50, 40)


def test_green_plane_is_g1_g2_average() -> None:
    # GRBG tile: G1 = [0::2, 0::2], G2 = [1::2, 1::2].
    raw = np.zeros((4, 4), np.uint16)
    raw[0::2, 0::2] = 100  # G1
    raw[1::2, 1::2] = 200  # G2
    g = green_plane(raw)
    assert g.dtype == np.float32
    assert g.shape == (2, 2)
    assert np.allclose(g, 150.0)  # (100 + 200) / 2


def test_green_plane_matches_extract_plane_grid() -> None:
    # The float (G1+G2)/2 plane must agree with the uint16 ``extract_plane(VIEW_G)``
    # sibling on the same grid, to within integer-floor vs float-round (≤1 ADU).
    rng = np.random.default_rng(0)
    raw = rng.integers(0, 60000, (64, 48), dtype=np.uint16)
    g = green_plane(raw)
    eg = extract_plane(raw, VIEW_G).astype(np.float32)
    assert g.shape == eg.shape
    assert float(np.max(np.abs(g - eg))) <= 1.0
