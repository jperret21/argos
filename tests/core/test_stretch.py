"""Tests for display stretch + measurement stats (Qt-free, no hardware)."""

from __future__ import annotations

import numpy as np

from argos.core.imaging import stretch as s


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
    # Continuous (non-quantized) data keeps the requested uniform bin count.
    assert len(centers) == 64
    assert len(rh) == len(gh) == len(bh) == 64
    # each green plane has H/2*W/2 = 64 px; r/b same; g merges both greens
    assert rh.sum() == 64
    assert bh.sum() == 64


def test_quantization_step_detects_shifted_12bit() -> None:
    """A 12-bit-in-16-bit frame (values multiple of 16) is detected as step 16,
    even with a sprinkle of off-grid stray pixels that would defeat GCD/bit tricks.
    """
    rng = np.random.default_rng(0)
    raw = ((rng.normal(1104, 120, (256, 256)) / 16).round() * 16).clip(0, 65520)
    raw = raw.astype(np.uint16)
    raw.flat[:50] += 4  # ~0.08% off-grid strays, like the real Seestar frames
    assert s.quantization_step(raw) == 16
    # Genuinely continuous data must NOT be flagged as quantized.
    cont = (rng.random((256, 256)) * 65535).astype(np.uint16)
    assert s.quantization_step(cont) == 1


def test_channel_histograms_no_comb_on_quantized_frame() -> None:
    """Regression for the field report: on left-shifted 12-bit data (values are
    multiples of 16) the naive 128-bin linear histogram is narrower than the
    16-ADU grid, so every other bin is empty -> a comb / "block of spikes".
    The quantization-aware binning must yield a continuous curve: no long run of
    empty bins between populated ones inside the data's own range.
    """

    def max_zero_run(counts: np.ndarray) -> int:
        nz = np.nonzero(counts)[0]
        if nz.size == 0:
            return 0
        span = counts[nz[0] : nz[-1] + 1]
        best = cur = 0
        for v in span:
            cur = cur + 1 if v == 0 else 0
            best = max(best, cur)
        return best

    rng = np.random.default_rng(1)
    # Dense sky: every ADU level in the core is populated, so any empty bin in
    # the middle is a *binning artefact*, not a truly-absent level.
    raw = ((rng.normal(1200, 90, (400, 400)) / 16).round() * 16).clip(784, 4000)
    raw = raw.astype(np.uint16)
    lo = float(raw.min())
    hi = float(np.percentile(raw, 99.8))

    # Baseline: the old naive path combs badly (sanity check that the test frame
    # actually reproduces the bug).
    naive_edges = np.linspace(lo, hi, 128 + 1)
    r, g1, g2, b = s.split_cfa(raw)
    naive_r, _ = np.histogram(r, bins=naive_edges)
    assert max_zero_run(naive_r) >= 3  # comb present without the fix

    centers, rh, gh, bh = s.channel_histograms(raw, bins=128, lo=lo, hi=hi)
    # Bins snapped to the 16-ADU grid: width is a multiple of 16.
    assert round(float(centers[1] - centers[0])) % 16 == 0
    # No comb: the populated support has no long run of empty bins.
    for counts in (rh, gh, bh):
        assert max_zero_run(counts) <= 1
