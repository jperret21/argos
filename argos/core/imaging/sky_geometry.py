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
from datetime import datetime, timezone
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
