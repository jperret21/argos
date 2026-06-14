"""Tests for display stretch + measurement stats (Qt-free, no hardware)."""

from __future__ import annotations

import numpy as np

from seercontrol.core.imaging import stretch as s


def test_apply_stretch_linear_endpoints_and_monotonic() -> None:
    ramp = np.linspace(0, 65535, 256, dtype=np.uint16)
    out = s.apply_stretch(ramp, 0, 65535, s.STRETCH_LINEAR)
    assert out.dtype == np.uint8
    assert out[0] == 0
    assert out[-1] == 255
    assert np.all(np.diff(out.astype(int)) >= 0)  # monotonic non-decreasing


def test_apply_stretch_clips_outside_black_white() -> None:
    arr = np.array([[10, 100, 1000, 5000]], dtype=np.uint16)
    out = s.apply_stretch(arr, black=100, white=1000, mode=s.STRETCH_LINEAR)
    assert out[0, 0] == 0  # below black
    assert out[0, 1] == 0  # at black
    assert out[0, 2] == 255  # at white
    assert out[0, 3] == 255  # above white


def test_apply_stretch_modes_keep_endpoints() -> None:
    ramp = np.linspace(0, 65535, 64, dtype=np.uint16)
    for mode in (s.STRETCH_LOG, s.STRETCH_ASINH):
        out = s.apply_stretch(ramp, 0, 65535, mode)
        assert out[0] == 0
        assert out[-1] == 255
        assert np.all(np.diff(out.astype(int)) >= 0)


def test_apply_stretch_rgb_shape() -> None:
    rgb = (np.random.rand(4, 4, 3) * 65535).astype(np.uint16)
    out = s.apply_stretch(rgb, 0, 65535)
    assert out.shape == (4, 4, 3)
    assert out.dtype == np.uint8


def test_apply_stretch_does_not_mutate_input() -> None:
    arr = np.array([[1000, 2000]], dtype=np.uint16)
    before = arr.copy()
    s.apply_stretch(arr, 0, 65535, s.STRETCH_ASINH, midtones=0.3)
    assert np.array_equal(arr, before)


def test_auto_levels_percentiles() -> None:
    arr = np.arange(100, dtype=np.uint16).reshape(10, 10)
    black, white = s.auto_levels(arr, 1, 99)
    assert black < white
    assert 0 <= black <= 5
    assert 94 <= white <= 99


def test_auto_stf_returns_sane_levels() -> None:
    rng = np.random.default_rng(0)
    arr = rng.normal(12, 3, (200, 200)).clip(0, None).astype(np.float32)
    arr[50, 50] = 8000.0  # a bright star
    black, white, mid = s.auto_stf(arr)
    assert black < white
    assert 0.0 < mid < 1.0
    assert black <= 20  # near the ~12 background
    assert white < 8000  # hottest pixel clipped by the 99.8 percentile


def test_region_stats() -> None:
    arr = np.array([[0, 10], [20, 30]], dtype=np.uint16)
    st = s.region_stats(arr)
    assert st["n"] == 4
    assert st["mean"] == 15.0
    assert st["min"] == 0.0
    assert st["max"] == 30.0
    assert st["median"] == 15.0


def test_channel_histograms_shapes() -> None:
    raw = (np.random.rand(16, 16) * 65535).astype(np.uint16)
    centers, rh, gh, bh = s.channel_histograms(raw, bins=64)
    assert len(centers) == 64
    assert len(rh) == len(gh) == len(bh) == 64
    # each green plane has H/2*W/2 = 64 px; r/b same; g merges both greens
    assert rh.sum() == 64
    assert bh.sum() == 64
