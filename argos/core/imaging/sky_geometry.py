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
    denom = math.sin(math.radians(altitude_deg + 244.0 / (165.0 + 47.0 * altitude_deg ** 1.1)))
    if denom <= 0:
        return None
    return round(1.0 / denom, 4)


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

    Keys (any may be missing if astropy fails or inputs are incomplete):
        altitude:    Target altitude in degrees (negative = below horizon).
        azimuth:     Target azimuth in degrees (north = 0, increasing east).
        airmass:     Pickering airmass, or absent below the horizon.
        hour_angle:  Hour angle in decimal hours, wrapped to [-12, 12).
        transit_in:  Hours until the next meridian transit (>= 0).
        transit_utc: Datetime (UTC) of the next meridian transit.
        moon_sep:    Angular separation target-Moon in degrees.

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
