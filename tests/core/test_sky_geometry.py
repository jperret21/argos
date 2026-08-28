"""Tests for the pure target-observing geometry (Target screen summary)."""

from __future__ import annotations

from datetime import datetime, timezone

import astropy.units as u
from astropy.time import Time

from argos.core.imaging.sky_geometry import compute_target_geometry


def test_missing_inputs_return_empty() -> None:
    when = datetime(2026, 6, 18, 22, 0, 0, tzinfo=timezone.utc)
    assert compute_target_geometry(when, None, None, None, 5.0, 20.0) == {}
    assert compute_target_geometry(when, 45.0, 0.0, 0.0, None, None) == {}


def test_transit_at_zenith_when_dec_equals_latitude() -> None:
    """A target with dec == site latitude, observed as it crosses the meridian,
    sits at the zenith — altitude ~90, airmass ~1, transit ~now."""
    when = datetime(2026, 6, 18, 22, 0, 0, tzinfo=timezone.utc)
    # Put the target on the meridian now: RA == local apparent sidereal time.
    lst = float(Time(when).sidereal_time("apparent", longitude=0.0 * u.deg).hour)

    geo = compute_target_geometry(when, 45.0, 0.0, 0.0, lst, 45.0)

    assert abs(geo["altitude"] - 90.0) < 1.0
    assert geo["airmass"] is not None and geo["airmass"] < 1.05
    assert abs(geo["hour_angle"]) < 0.05
    # Transiting now: either just-passed (~0) or wraps to ~24 h.
    assert geo["transit_in"] < 0.05 or geo["transit_in"] > 23.95
    assert geo["transit_utc"] >= when
    assert 0.0 <= geo["moon_sep"] <= 180.0


def test_ranges_are_sane_for_an_arbitrary_target() -> None:
    when = datetime(2026, 1, 15, 3, 30, 0, tzinfo=timezone.utc)
    geo = compute_target_geometry(when, 48.85, 2.35, 35.0, 6.75, -16.7)  # ~Sirius

    assert -90.0 <= geo["altitude"] <= 90.0
    assert -12.0 <= geo["hour_angle"] < 12.0
    assert 0.0 <= geo["transit_in"] < 24.0
    # Airmass is present only when above the horizon.
    if geo["altitude"] > 0:
        assert geo["airmass"] is not None
    else:
        assert "airmass" not in geo


# ── field_rotation_rate (alt-az mounts) ─────────────────────────────────────


def test_field_rotation_zero_due_east() -> None:
    from argos.core.imaging.sky_geometry import field_rotation_rate

    assert abs(field_rotation_rate(40.0, 90.0, 46.0)) < 1e-9


def test_field_rotation_matches_known_value() -> None:
    from argos.core.imaging.sky_geometry import field_rotation_rate

    # lat = alt = 45°, target due north: 15.041·cos45/cos45 = 15.041 °/h.
    assert abs(field_rotation_rate(45.0, 0.0, 45.0) - 15.041) < 1e-6
    # Due south (az=180) the sign flips.
    assert abs(field_rotation_rate(45.0, 180.0, 45.0) + 15.041) < 1e-6


def test_field_rotation_diverges_at_zenith() -> None:
    from argos.core.imaging.sky_geometry import field_rotation_rate

    assert field_rotation_rate(89.5, 0.0, 46.0) is None
    # …and grows toward it: 80° alt rotates faster than 40° at the same az.
    slow = abs(field_rotation_rate(40.0, 0.0, 46.0))
    fast = abs(field_rotation_rate(80.0, 0.0, 46.0))
    assert fast > slow


def test_target_geometry_includes_field_rotation() -> None:
    from datetime import datetime, timezone

    from argos.core.imaging.sky_geometry import compute_target_geometry

    out = compute_target_geometry(
        datetime(2026, 1, 15, 3, 30, tzinfo=timezone.utc),
        site_lat=46.0,
        site_lon=6.0,
        site_elev=400.0,
        ra_hours=5.5,
        dec_deg=30.0,
    )
    if "altitude" in out and out["altitude"] < 89.0:
        assert "field_rotation" in out
        assert isinstance(out["field_rotation"], float)


# ── altitude_at (fast trig altitude for batch airmass, P4) ──────────────────


def test_altitude_at_matches_astropy() -> None:
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord

    from argos.core.imaging.sky_geometry import altitude_at

    lat, lon = 46.2, 6.1
    t = Time(datetime(2026, 7, 11, 22, 30, tzinfo=timezone.utc))
    for ra_h, dec in ((18.6, 38.8), (5.5, -5.4), (12.0, 89.0)):
        got = altitude_at(t.jd, ra_h, dec, lat, lon)
        loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
        ref = (
            SkyCoord(ra=ra_h * 15 * u.deg, dec=dec * u.deg)
            .transform_to(AltAz(obstime=t, location=loc))
            .alt.deg
        )
        assert abs(got - float(ref)) < 0.3, f"RA={ra_h}h Dec={dec}"


def test_upcoming_night_altitudes_has_a_complete_local_night() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from argos.core.imaging.sky_geometry import upcoming_night_altitudes

    samples = upcoming_night_altitudes(
        20.0,
        22.0,
        43.0,
        1.0,
        now=datetime(2026, 8, 27, 12, tzinfo=ZoneInfo("Europe/Paris")),
        interval_minutes=60,
    )

    assert len(samples) == 13
    assert samples[0][0].hour == 18
    assert samples[-1][0].hour == 6
    assert all(-90.0 <= altitude <= 90.0 for _when, altitude in samples)


def test_airmass_formulas_agree_project_wide() -> None:
    """P4: the photometry entry point delegates to Pickering — no more
    header-vs-curve disagreement."""
    from argos.core.imaging.sky_geometry import compute_airmass
    from argos.core.photometry.airmass import airmass_from_altitude

    for alt in (5.0, 15.0, 30.0, 45.0, 60.0, 89.0):
        assert airmass_from_altitude(alt) == compute_airmass(alt)
    assert airmass_from_altitude(0.0) is None and airmass_from_altitude(-5.0) is None
