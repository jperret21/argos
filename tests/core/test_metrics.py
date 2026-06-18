"""Tests for per-frame quality metrics (Qt-free, no hardware)."""

from __future__ import annotations

import numpy as np

from argos.core.imaging.metrics import (
    DetectedStar,
    FrameMetrics,
    StarField,
    StarMeasurement,
    detect_stars,
    frame_metrics,
    measure_star_at,
)


def _gaussian_star_frame(
    centers: list[tuple[int, int]], sigma: float = 1.6, bg: int = 500, peak: int = 30000
) -> np.ndarray:
    """A GRBG frame with Gaussian PSF stars on green (even,even) positions.

    ``centers`` are raw-frame (y, x) of green pixels (both even). Returns uint16.
    """
    arr = np.full((128, 128), bg, dtype=np.float32)
    yy, xx = np.mgrid[0:128, 0:128]
    for cy, cx in centers:
        arr += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2))
    return np.clip(arr, 0, 65535).astype(np.uint16)


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


# --------------------------------------------------------------------------- #
# detect_stars (§5) — star list with FWHM + eccentricity                       #
# --------------------------------------------------------------------------- #


def test_detect_stars_returns_starfield() -> None:
    field = detect_stars(_gaussian_star_frame([(20, 20), (20, 60), (60, 40)]))
    assert isinstance(field, StarField)
    assert field.count == 3
    assert all(isinstance(s, DetectedStar) for s in field.stars)


def test_detect_stars_positions_in_green_plane_coords() -> None:
    # Raw green pixel (40, 60) → green-plane (20, 30).
    field = detect_stars(_gaussian_star_frame([(40, 60)]))
    assert field.count == 1
    star = field.stars[0]
    assert abs(star.x - 30) < 1.0
    assert abs(star.y - 20) < 1.0


def test_detect_stars_measures_positive_fwhm() -> None:
    field = detect_stars(_gaussian_star_frame([(30, 30)], sigma=2.0))
    assert field.mean_fwhm is not None and field.mean_fwhm > 0
    # A round Gaussian should read low eccentricity.
    assert field.mean_eccentricity is not None and field.mean_eccentricity < 0.5


def test_detect_stars_empty_on_flat_frame() -> None:
    field = detect_stars(np.full((64, 64), 1000, dtype=np.uint16))
    assert field.count == 0
    assert field.mean_fwhm is None
    assert field.mean_eccentricity is None


def test_detect_stars_respects_max_cap() -> None:
    centers = [(8 + 8 * (i % 12), 8 + 8 * (i // 12)) for i in range(40)]
    field = detect_stars(_gaussian_star_frame(centers, sigma=1.0), max_stars=10)
    assert field.count <= 10


def test_detect_stars_rejects_hot_pixels() -> None:
    # A lone bright pixel (no PSF wing) must not be detected as a star.
    arr = np.full((128, 128), 500, dtype=np.uint16)
    arr[40, 40] = 60000  # green (20,20)
    arr[70, 70] = 55000  # green (35,35)
    assert detect_stars(arr).count == 0


def test_detect_stars_deduplicates_one_star() -> None:
    # A single fat star must yield exactly one detection, not a cluster.
    field = detect_stars(_gaussian_star_frame([(40, 40)], sigma=2.5), radius=6)
    assert field.count == 1


def test_measure_star_at_snaps_and_measures() -> None:
    # Star at raw (40, 60) → green (20, 30); click slightly off and snap to it.
    arr = _gaussian_star_frame([(40, 60)], sigma=2.0)
    meas = measure_star_at(arr, x=31, y=21, radius=6)
    assert isinstance(meas, StarMeasurement)
    assert abs(meas.x - 30) < 1.5 and abs(meas.y - 20) < 1.5
    assert meas.fwhm is not None and meas.fwhm > 0
    assert meas.hfd is not None and meas.hfd > 0
    assert meas.snr > 5
    assert meas.peak_adu > 1000
    assert meas.radius == 6


def test_measure_star_at_out_of_bounds_returns_none() -> None:
    arr = _gaussian_star_frame([(40, 40)])
    assert measure_star_at(arr, x=-5, y=-5) is None
