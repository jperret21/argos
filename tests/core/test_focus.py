"""Tests for the pure focus V-curve fit (``argos.core.imaging.focus``)."""

from __future__ import annotations

import math

from argos.core.imaging.focus import FocusResult, fit_v_curve


def _parabola(positions, vertex, a=1e-4, floor=1.5):
    """Synthetic HFD samples on an upward parabola with its minimum at vertex."""
    return [(p, a * (p - vertex) ** 2 + floor) for p in positions]


def test_recovers_parabola_vertex() -> None:
    vertex = 4100
    positions = list(range(3600, 4600, 100))
    result = fit_v_curve(_parabola(positions, vertex))

    assert result.method == "parabola"
    assert result.is_reliable
    assert abs(result.best_position - vertex) <= 1  # within a step of the true minimum
    assert result.best_hfd is not None and result.best_hfd >= 1.5
    assert result.coeffs is not None and result.coeffs[0] > 0


def test_fit_curve_points_lie_on_parabola() -> None:
    vertex = 4100
    positions = list(range(3600, 4600, 100))
    result = fit_v_curve(_parabola(positions, vertex))

    xs, ys = result.fit_curve(num=50)
    assert len(xs) == len(ys) == 50
    assert xs[0] == positions[0] and xs[-1] == positions[-1]
    # The fitted minimum is at the vertex, so curve endpoints sit above it.
    assert min(ys) <= ys[0] and min(ys) <= ys[-1]


def test_nan_samples_are_dropped() -> None:
    positions = list(range(3600, 4600, 100))
    samples = _parabola(positions, 4100)
    samples[0] = (samples[0][0], float("nan"))  # a failed frame
    result = fit_v_curve(samples)

    assert result.method == "parabola"
    assert all(not math.isnan(h) for _, h in result.samples)
    assert (positions[0], float("nan")) not in result.samples


def test_falls_back_to_raw_minimum_when_not_a_v() -> None:
    # Monotonic (no minimum inside the range) — the fit should not be trusted.
    samples = [(p, 10.0 - 0.001 * p) for p in range(3600, 4600, 100)]
    result = fit_v_curve(samples)

    assert result.method == "raw"
    assert not result.is_reliable
    assert result.best_position == 4500  # the lowest measured HFD
    assert result.coeffs is None
    assert result.fit_curve() == ([], [])


def test_vertex_outside_range_rejected() -> None:
    # A valid upward parabola but with its vertex far outside the scanned band:
    # clamp to the raw minimum rather than extrapolating off the sweep.
    samples = _parabola(range(3600, 4600, 100), vertex=8000)
    result = fit_v_curve(samples)
    assert result.method == "raw"


def test_too_few_samples_uses_raw() -> None:
    result = fit_v_curve([(4000, 3.0), (4100, 2.0)])
    assert result.method == "raw"
    assert result.best_position == 4100


def test_empty_is_method_none() -> None:
    result = fit_v_curve([])
    assert isinstance(result, FocusResult)
    assert result.method == "none"
    assert result.best_hfd is None
    assert result.samples == ()
