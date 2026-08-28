"""Sky geometry helpers — airmass, Moon distance, phase.

Pure functions, no Qt, no network. Used by the FITS writer to fill the
photometry-relevant headers (``AIRMASS``, ``MOONSEP``, ``MOONALT``, ``MOONPHAS``)
without ever blocking the UI thread.

The astropy calls are not cheap (~50 ms for the Moon position), so callers
should invoke them from the exposure worker, not the main thread.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def compute_airmass(altitude_deg: float) -> Optional[float]:
    """Return Pickering (2002) airmass for ``altitude_deg`` (degrees).

    Returns ``None`` if the target is below the horizon. Pickering's formula
    is accurate to better than 0.01 airmass down to 1° altitude and stays
    finite at the horizon, unlike the naive ``sec(z)``.
    """
    if altitude_deg <= 0:
        return None
    # Pickering 2002, "The Southern Limits of the Ancient Star Catalog"
    denom = math.sin(math.radians(altitude_deg + 244.0 / (165.0 + 47.0 * altitude_deg**1.1)))
    if denom <= 0:
        return None
    return round(1.0 / denom, 4)


def altitude_at(
    jd_utc: float,
    ra_hours: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
) -> float:
    """Target altitude (degrees) at a JD — fast spherical trig, no astropy.

    GMST from the JD (IAU 1982 linear term), LST from the site longitude,
    then the standard HA→altitude formula. Accurate to ~0.1° (no nutation or
    refraction), which is far below what airmass needs; exists so a batch of
    hundreds of frames doesn't pay astropy's ~50 ms per transform.
    """
    gmst_h = (18.697374558 + 24.06570982441908 * (jd_utc - 2451545.0)) % 24.0
    lst_h = (gmst_h + lon_deg / 15.0) % 24.0
    ha_rad = math.radians((lst_h - ra_hours) * 15.0)
    lat = math.radians(lat_deg)
    dec = math.radians(dec_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha_rad)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def upcoming_night_altitudes(
    ra_hours: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
    *,
    now: datetime | None = None,
    interval_minutes: int = 10,
) -> list[tuple[datetime, float]]:
    """Sample an object's altitude over the next local observing night.

    The planning view deliberately uses 18:00–06:00 local civil time: it is
    predictable, works without a network/ephemeris download, and is labelled
    as such in the UI.  ``datetime`` values retain the computer's local time
    zone so axis labels agree with the observer's clock.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    local_now = (now or datetime.now().astimezone()).astimezone()
    start = local_now.replace(hour=18, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=12)
    step = timedelta(minutes=interval_minutes)
    samples: list[tuple[datetime, float]] = []
    point = start
    while point <= end:
        jd = point.astimezone(timezone.utc).timestamp() / 86400.0 + 2440587.5
        samples.append((point, altitude_at(jd, ra_hours, dec_deg, lat_deg, lon_deg)))
        point += step
    return samples


def field_rotation_rate(
    altitude_deg: float, azimuth_deg: float, latitude_deg: float
) -> Optional[float]:
    """Alt-az field rotation rate in degrees/hour (signed), or None near zenith.

    On an alt-az mount the field rotates at the rate the parallactic angle
    changes: ``15.041 · cos(lat) · cos(az) / cos(alt)`` (azimuth from north,
    eastward — the astropy AltAz convention). Zero for a target due east/west,
    divergent at the zenith (returns None above 89°, where the mount can't
    track anyway). Irrelevant on a wedge (EQ mode) — the caller gates on the
    mount mode.
    """
    if altitude_deg > 89.0:
        return None
    cos_alt = math.cos(math.radians(altitude_deg))
    if cos_alt <= 0:
        return None
    return (
        15.041
        * math.cos(math.radians(latitude_deg))
        * math.cos(math.radians(azimuth_deg))
        / cos_alt
    )


def compute_moon_info(
    when_utc: datetime,
    site_lat: Optional[float],
    site_lon: Optional[float],
    site_elev: Optional[float],
    target_ra_hours: Optional[float],
    target_dec_deg: Optional[float],
) -> dict:
    """Return Moon altitude, target separation, and illuminated fraction.

    Keys (any may be missing if astropy fails or inputs incomplete):
        moon_alt:    Moon altitude at the site in degrees.
        moon_sep:    Angular separation target–Moon in degrees.
        moon_phase:  Illuminated fraction 0.0 (new) .. 1.0 (full).

    Args:
        when_utc:        Observation time, naive treated as UTC.
        site_lat:        Site latitude in degrees (north positive).
        site_lon:        Site longitude in degrees (east positive).
        site_elev:       Site elevation in metres above sea level.
        target_ra_hours: Target RA in decimal hours (J2000).
        target_dec_deg:  Target Dec in decimal degrees (J2000).
    """
    try:
        from astropy.coordinates import (
            AltAz,
            EarthLocation,
            SkyCoord,
            get_body,
        )
        from astropy.time import Time
        import astropy.units as u
    except ImportError:
        logger.warning("astropy not available — Moon headers will be omitted")
        return {}

    out: dict = {}

    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)
    t = Time(when_utc)

    try:
        moon_icrs = get_body("moon", t)

        if site_lat is not None and site_lon is not None:
            location = EarthLocation(
                lat=site_lat * u.deg,
                lon=site_lon * u.deg,
                height=(site_elev or 0.0) * u.m,
            )
            altaz_frame = AltAz(obstime=t, location=location)
            moon_altaz = moon_icrs.transform_to(altaz_frame)
            out["moon_alt"] = round(float(moon_altaz.alt.deg), 3)

        if target_ra_hours is not None and target_dec_deg is not None:
            target = SkyCoord(
                ra=target_ra_hours * 15.0 * u.deg,
                dec=target_dec_deg * u.deg,
                frame="icrs",
            )
            sep = target.separation(moon_icrs)
            out["moon_sep"] = round(float(sep.deg), 3)

        # Illuminated fraction from Sun–Moon phase angle.
        sun_icrs = get_body("sun", t)
        elong = sun_icrs.separation(moon_icrs).rad
        phase_angle = math.pi - elong
        illum = (1.0 + math.cos(phase_angle)) / 2.0
        out["moon_phase"] = round(illum, 4)

    except Exception as exc:
        # Astropy errors should never block FITS writing — log and continue.
        logger.warning("compute_moon_info failed: %s", exc)

    return out


def compute_target_geometry(
    when_utc: datetime,
    site_lat: Optional[float],
    site_lon: Optional[float],
    site_elev: Optional[float],
    ra_hours: Optional[float],
    dec_deg: Optional[float],
) -> dict:
    """Return the observing geometry of a target as seen from a site, at a time.

    Returns a mapping whose optional keys include ``altitude`` (degrees),
    ``azimuth`` (degrees north through east), ``airmass``, ``hour_angle``
    (hours), ``transit_in`` (hours), ``transit_utc``, ``moon_sep`` (degrees)
    and ``field_rotation`` (signed degrees/hour while the mount runs alt-az).

    Args mirror :func:`compute_moon_info`; ``when_utc`` naive is treated as UTC.
    Pure and network-free (astropy built-in ephemeris), but ~50 ms — call off the
    UI thread for tight cadences.
    """
    if site_lat is None or site_lon is None or ra_hours is None or dec_deg is None:
        return {}

    try:
        import astropy.units as u
        from astropy.coordinates import AltAz, EarthLocation, SkyCoord
        from astropy.time import Time
    except ImportError:
        logger.warning("astropy not available — target geometry omitted")
        return {}

    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)

    out: dict = {}
    try:
        t = Time(when_utc)
        location = EarthLocation(
            lat=site_lat * u.deg, lon=site_lon * u.deg, height=(site_elev or 0.0) * u.m
        )
        target = SkyCoord(ra=ra_hours * 15.0 * u.deg, dec=dec_deg * u.deg, frame="icrs")

        altaz = target.transform_to(AltAz(obstime=t, location=location))
        alt = float(altaz.alt.deg)
        out["altitude"] = round(alt, 3)
        out["azimuth"] = round(float(altaz.az.deg), 3)
        airmass = compute_airmass(alt)
        if airmass is not None:
            out["airmass"] = airmass
        rot = field_rotation_rate(alt, float(altaz.az.deg), site_lat)
        if rot is not None:
            out["field_rotation"] = round(rot, 2)  # deg/hour, alt-az mounts only

        # Hour angle + next meridian transit from local apparent sidereal time.
        lst_hours = float(t.sidereal_time("apparent", longitude=site_lon * u.deg).hour)
        hour_angle = (lst_hours - ra_hours + 12.0) % 24.0 - 12.0  # wrap to [-12, 12)
        out["hour_angle"] = round(hour_angle, 4)
        # Time until HA returns to 0, in sidereal hours then converted to solar.
        sidereal_to_transit = (-hour_angle) % 24.0
        solar_hours = sidereal_to_transit * 0.9972695663
        out["transit_in"] = round(solar_hours, 4)
        out["transit_utc"] = when_utc + timedelta(hours=solar_hours)
    except Exception as exc:
        logger.warning("compute_target_geometry failed: %s", exc)

    # Moon separation reuses the existing helper (and its own error handling).
    moon = compute_moon_info(when_utc, site_lat, site_lon, site_elev, ra_hours, dec_deg)
    if "moon_sep" in moon:
        out["moon_sep"] = moon["moon_sep"]
    return out
