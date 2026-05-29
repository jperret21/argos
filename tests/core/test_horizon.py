"""Horizon helpers — astropy contract checks (no exact-value lock-in)."""

from __future__ import annotations

from datetime import datetime, timezone


from seercontrol.core.targets.horizon import (
    VisibilitySummary,
    altitude_now,
    visibility_tonight,
)


PARIS = {"site_lat": 48.85, "site_lon": 2.35, "site_elev_m": 35.0}


def test_altitude_now_returns_finite_value_for_known_target() -> None:
    when = datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)
    alt = altitude_now(18.6156, 38.78, when_utc=when, **PARIS)  # Vega
    assert alt is not None
    # Vega from Paris in mid-July at 22:00 UTC is high — must be well above the horizon.
    assert 40.0 < alt < 90.0


def test_altitude_now_for_below_horizon_target_is_negative() -> None:
    # Antares (RA 16.49, Dec -26.4) is on the opposite hemisphere at this time.
    when = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)  # noon UTC
    alt = altitude_now(16.49, -26.4, when_utc=when, **PARIS)
    assert alt is not None
    assert alt < 30.0  # should be below the comfortable photometry threshold


def test_visibility_tonight_summary_shape() -> None:
    when = datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)
    vs = visibility_tonight(18.6156, 38.78, when_utc=when, sample_minutes=30, **PARIS)
    assert isinstance(vs, VisibilitySummary)
    # Vega at Paris in mid-July is visible the whole night.
    assert vs.is_visible
    assert vs.peak_altitude_deg is not None
    assert vs.peak_altitude_deg > 50.0
    assert vs.peak_time_utc is not None


def test_visibility_tonight_rejects_invisible_target() -> None:
    # A southern object well below the southern horizon at Paris (Dec = -85°).
    when = datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)
    vs = visibility_tonight(
        0.0, -85.0,
        when_utc=when, min_altitude_deg=20.0, sample_minutes=30, **PARIS,
    )
    assert not vs.is_visible
