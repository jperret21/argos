"""Parity tests for the star_var_script systematic uncertainty model."""

from __future__ import annotations

import math

import pytest

from argos.core.photometry.uncertainty import (
    apply_systematic_floor,
    estimate_lightcurve_scatter,
    estimate_systematic_floor,
)


def _smooth_series(noise: float = 0.02) -> list[tuple[float, float, float]]:
    """A locally linear light curve with a repeating deterministic noise term."""
    return [
        (2451545.0 + index / 1440.0, 10.0 + 0.001 * index + noise * ((index % 3) - 1), 0.01)
        for index in range(12)
    ]


def test_second_difference_scatter_removes_a_linear_lightcurve_trend() -> None:
    points = _smooth_series()
    scatter = estimate_lightcurve_scatter((jd, mag) for jd, mag, _error in points)
    assert scatter is not None
    # The underlying slope cancels; the remaining repeated noise has a
    # non-zero, bounded robust scatter.
    assert 0.015 < scatter < 0.04


def test_systematic_floor_matches_star_var_quadrature_contract() -> None:
    points = _smooth_series()
    floor = estimate_systematic_floor(points)
    assert floor is not None
    assert floor.points_used == 12
    assert floor.median_formal == pytest.approx(0.01)
    assert floor.sigma_systematic > 0.0
    assert apply_systematic_floor(0.02, floor) == pytest.approx(
        math.sqrt(0.02**2 + floor.sigma_systematic**2)
    )


def test_automatic_floor_waits_for_ten_valid_points() -> None:
    assert estimate_systematic_floor(_smooth_series()[:9]) is None


def test_manual_floor_can_be_used_before_ten_points() -> None:
    floor = estimate_systematic_floor(_smooth_series()[:2], manual_floor=0.012)
    assert floor is not None
    assert floor.sigma_systematic == pytest.approx(0.012)
