"""Tests for per-frame quality metrics (Qt-free, no hardware)."""

from __future__ import annotations

import numpy as np

from seercontrol.core.imaging.metrics import FrameMetrics, frame_metrics


def _frame_with_stars(n: int, bg: int = 500, peak: int = 40000) -> np.ndarray:
    """A GRBG frame with flat background + ``n`` bright green-pixel stars."""
    rng = np.random.default_rng(0)
    arr = np.full((128, 128), bg, dtype=np.uint16)
    arr += rng.integers(0, 20, arr.shape, dtype=np.uint16)  # mild noise
    # Place stars on green (even,even) positions, well separated.
    for i in range(n):
        y = 8 + (i % 6) * 18
        x = 8 + (i // 6) * 18
        arr[y, x] = peak  # G1 position (even,even)
    return arr


def test_frame_metrics_type_and_fields() -> None:
    m = frame_metrics(_frame_with_stars(3))
    assert isinstance(m, FrameMetrics)
    assert m.hfd is None or m.hfd >= 0
    assert m.star_count >= 0
    assert m.sky_adu > 0
    assert m.peak_adu >= 40000


def test_star_count_tracks_number_of_stars() -> None:
    few = frame_metrics(_frame_with_stars(2)).star_count
    many = frame_metrics(_frame_with_stars(10)).star_count
    assert many > few


def test_flat_frame_has_no_stars() -> None:
    flat = np.full((64, 64), 1000, dtype=np.uint16)
    m = frame_metrics(flat)
    assert m.star_count == 0
    assert m.sky_adu == 1000.0
    assert m.peak_adu == 1000


def test_sky_is_robust_to_stars() -> None:
    m = frame_metrics(_frame_with_stars(5, bg=800))
    # A handful of bright stars must not drag the median background far off 800.
    assert abs(m.sky_adu - 800) < 50
