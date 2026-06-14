"""Tests for the GRBG CFA split + debayer render modes (Qt-free, no hardware).

Verifies the data-pipeline primitives: real-pixel channel split, the three
render modes, and that rendering never mutates the raw array.
"""

from __future__ import annotations

import numpy as np
import pytest

from seercontrol.core.imaging import debayer as d


def _grbg(g1: int = 10, r: int = 20, b: int = 30, g2: int = 40) -> np.ndarray:
    """A 4×4 GRBG frame with one constant per CFA position."""
    arr = np.zeros((4, 4), dtype=np.uint16)
    arr[0::2, 0::2] = g1  # G1
    arr[0::2, 1::2] = r  # R
    arr[1::2, 0::2] = b  # B
    arr[1::2, 1::2] = g2  # G2
    return arr


def test_split_cfa_picks_real_pixels() -> None:
    r, g1, g2, b = d.split_cfa(_grbg())
    assert r.shape == (2, 2)
    assert np.all(r == 20)
    assert np.all(g1 == 10)
    assert np.all(g2 == 40)
    assert np.all(b == 30)


def test_extract_plane_channels() -> None:
    arr = _grbg()
    assert np.all(d.extract_plane(arr, "R") == 20)
    assert np.all(d.extract_plane(arr, "B") == 30)
    assert np.all(d.extract_plane(arr, "G1") == 10)
    assert np.all(d.extract_plane(arr, "G2") == 40)
    assert np.all(d.extract_plane(arr, "G") == 25)  # mean of the two greens
    lum = d.extract_plane(arr, "Luminance")
    assert lum.shape == (2, 2)
    assert lum.dtype == np.uint16
    assert int(lum[0, 0]) == 24  # 0.299*20 + 0.587*25 + 0.114*30


def test_extract_plane_unknown_raises() -> None:
    with pytest.raises(ValueError):
        d.extract_plane(_grbg(), "Q")


def test_superpixel_rgb_shape_and_values() -> None:
    rgb = d.superpixel_rgb(_grbg())
    assert rgb.shape == (2, 2, 3)
    assert rgb.dtype == np.uint16
    assert rgb[0, 0, 0] == 20  # R
    assert rgb[0, 0, 1] == 25  # G
    assert rgb[0, 0, 2] == 30  # B


def test_bilinear_full_res_keeps_known_samples() -> None:
    arr = _grbg()
    rgb = d.bilinear_rgb(arr)
    assert rgb.shape == (4, 4, 3)
    assert rgb.dtype == np.uint16
    # A known R sample (row 0, col 1) must be preserved untouched.
    assert rgb[0, 1, 0] == 20
    # A known B sample (row 1, col 0).
    assert rgb[1, 0, 2] == 30


def test_render_view_shapes_and_dtypes() -> None:
    arr = _grbg()
    raw = d.render_view(arr, d.VIEW_RAW)
    assert raw.shape == (4, 4) and raw.dtype == np.uint16

    plane = d.render_view(arr, d.VIEW_G)
    assert plane.shape == (2, 2) and plane.dtype == np.uint16

    sp = d.render_view(arr, d.VIEW_SUPERPIXEL)
    assert sp.shape == (2, 2, 3) and sp.dtype == np.uint16  # linear; stretch is separate

    interp = d.render_view(arr, d.VIEW_INTERP)
    assert interp.shape == (4, 4, 3) and interp.dtype == np.uint16


def test_render_view_does_not_mutate_raw() -> None:
    arr = _grbg()
    before = arr.copy()
    for view in d.VIEWS:
        d.render_view(arr, view)
    assert np.array_equal(arr, before)


def test_views_are_complete() -> None:
    assert d.VIEW_RAW in d.VIEWS
    assert d.VIEW_SUPERPIXEL in d.VIEWS
    assert d.VIEW_INTERP in d.VIEWS
    for ch in ("R", "G", "B", "G1", "G2", "Luminance"):
        assert ch in d.VIEWS
