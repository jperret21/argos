"""Airmass + Julian date helpers (docs/photometry_plan.md §6 C4).

Qt-free, dependency-light. Airmass uses Kasten & Young (1989); JD is the standard
calendar→Julian-date conversion for an exposure-midpoint UTC datetime. (BJD_TDB,
the publishable standard, is a post-processing step.)
"""

from __future__ import annotations

import math
from datetime import datetime


def airmass_from_altitude(alt_deg: float | None) -> float | None:
    """Airmass for a target at altitude ``alt_deg`` (Kasten–Young 1989).

    Returns ``None`` at or below the horizon (no useful airmass).
    """
    if alt_deg is None or alt_deg <= 0.0:
        return None
    z = 90.0 - float(alt_deg)  # zenith angle, degrees
    denom = math.cos(math.radians(z)) + 0.50572 * (96.07995 - z) ** (-1.6364)
    if denom <= 0.0:
        return None
    return round(1.0 / denom, 4)


def julian_date(dt: datetime) -> float:
    """Julian date of a UTC ``datetime`` (Fliegel–Van Flandern day number).

    The input should be timezone-aware UTC (the exposure midpoint); the tz is not
    re-converted here — pass UTC.
    """
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = (
        dt.day
        + (153 * m + 2) // 5
        + 365 * y
        + y // 4
        - y // 100
        + y // 400
        - 32045
    )
    frac = (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0 + dt.microsecond / 86_400_000_000.0
    return jdn + frac


def bjd_tdb(
    jd_utc: float,
    ra_deg: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
    elev_m: float = 0.0,
) -> float | None:
    """Barycentric Julian Date (TDB) for an exposure-midpoint ``jd_utc``.

    The publishable time standard: UTC→TDB plus the barycentric light-travel-time
    correction for the target's direction from the observing site. Uses astropy
    (imported lazily). Returns ``None`` if astropy can't do the conversion.
    """
    try:
        import astropy.units as u
        from astropy.coordinates import EarthLocation, SkyCoord
        from astropy.time import Time

        t = Time(jd_utc, format="jd", scale="utc")
        loc = EarthLocation.from_geodetic(
            lon=lon_deg * u.deg, lat=lat_deg * u.deg, height=elev_m * u.m
        )
        target = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
        ltt = t.light_travel_time(target, kind="barycentric", location=loc)
        return float((t.tdb + ltt).jd)
    except Exception:  # astropy missing / bad inputs → caller falls back to JD
        return None
