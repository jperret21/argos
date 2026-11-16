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


def precess_j2000_to_date(ra_hours: float, dec_deg: float, jd: float) -> tuple[float, float]:
    """Mean J2000 coordinates precessed to the mean equator and equinox of ``jd`` (S51).

    IAU 1976 precession (Lieske et al. 1977; Meeus, *Astronomical Algorithms*,
    eq. 21.2-21.4): the angles ζ, z, θ in Julian centuries from J2000. The JD
    is UTC (TT − UTC ≈ 69 s moves the angles by 1e-6″). Returns ``(RA hours,
    Dec degrees)`` of the date, for the date's sidereal time.
    """
    t = (jd - 2451545.0) / 36525.0
    arcsec = math.pi / (180.0 * 3600.0)
    zeta = (2306.2181 * t + 0.30188 * t * t + 0.017998 * t**3) * arcsec
    z = (2306.2181 * t + 1.09468 * t * t + 0.018203 * t**3) * arcsec
    theta = (2004.3109 * t - 0.42665 * t * t - 0.041833 * t**3) * arcsec
    ra0 = math.radians(ra_hours * 15.0)
    dec0 = math.radians(dec_deg)
    a = math.cos(dec0) * math.sin(ra0 + zeta)
    b = math.cos(theta) * math.cos(dec0) * math.cos(ra0 + zeta) - math.sin(theta) * math.sin(dec0)
    c = math.sin(theta) * math.cos(dec0) * math.cos(ra0 + zeta) + math.cos(theta) * math.sin(dec0)
    ra = (math.degrees(math.atan2(a, b) + z) / 15.0) % 24.0
    dec = math.degrees(math.asin(max(-1.0, min(1.0, c))))
    return ra, dec


def altitude_at(
    jd_utc: float,
    ra_hours: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
) -> float:
    """Target altitude (degrees) at a JD — fast spherical trig, no astropy.

    The J2000 coordinates are precessed to the date (IAU 1976, S51), then
    GMST from the JD (IAU 1982 linear term), LST from the site longitude and
    the standard HA→altitude formula. No nutation, aberration or refraction:
    within 0.02° of astropy over 2000-2035 (0.05° tested). Before S51 the
    J2000 coordinates met the date's sidereal time unprecessed: up to 0.3° off
    in 2026, an airmass about 0.002 low at 41° and 0.01-0.02 at 20-30°. Exists
    so a batch of hundreds of frames doesn't pay astropy's ~50 ms per transform.
    """
    ra_hours, dec_deg = precess_j2000_to_date(ra_hours, dec_deg, jd_utc)
    gmst_h = (18.697374558 + 24.06570982441908 * (jd_utc - 2451545.0)) % 24.0
    lst_h = (gmst_h + lon_deg / 15.0) % 24.0
    ha_rad = math.radians((lst_h - ra_hours) * 15.0)
    lat = math.radians(lat_deg)
    dec = math.radians(dec_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha_rad)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def horizontal_at(
    jd_utc: float,
    ra_hours: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
) -> tuple[float, float]:
    """Altitude and azimuth (degrees, azimuth north through east) at a JD.

    The same fast spherical trig as :func:`altitude_at` (precessed to the date,
    S51; no nutation, aberration or refraction: within 0.02° of astropy), for
    checks that need the whole direction.
    """
    ra_hours, dec_deg = precess_j2000_to_date(ra_hours, dec_deg, jd_utc)
    gmst_h = (18.697374558 + 24.06570982441908 * (jd_utc - 2451545.0)) % 24.0
    lst_h = (gmst_h + lon_deg / 15.0) % 24.0
    ha = math.radians((lst_h - ra_hours) * 15.0)
    lat = math.radians(lat_deg)
    dec = math.radians(dec_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))
    az = math.atan2(
        -math.cos(dec) * math.sin(ha),
        math.sin(dec) * math.cos(lat) - math.cos(dec) * math.cos(ha) * math.sin(lat),
    )
    return math.degrees(alt), math.degrees(az) % 360.0


def angle_between_directions(alt1: float, az1: float, alt2: float, az2: float) -> float:
    """Angle (degrees) between two horizontal directions given in degrees."""
    a1, z1, a2, z2 = (math.radians(v) for v in (alt1, az1, alt2, az2))
    cos_d = math.sin(a1) * math.sin(a2) + math.cos(a1) * math.cos(a2) * math.cos(z1 - z2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_d))))


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


# ---------------------------------------------------------------------------
# S78: the site the mount computes its altitude and azimuth from
# ---------------------------------------------------------------------------

#: S78: a fitted site needs this many pointings spanning this long (seconds): with one
#: direction the (latitude, hour angle) pair has two solutions; the field's motion over
#: minutes tells them apart.
SITE_FIT_MIN_SAMPLES = 3
SITE_FIT_MIN_SPAN_S = 600.0
#: S78: the fit is used only when the mount's directions agree with it this well (rms,
#: degrees). The owner's runs: 0.0005-0.0055° median, 0.018° at most (astropy fits).
SITE_FIT_MAX_RMS_DEG = 0.1
#: S78: the fit uses at most this many pointings, spread over the run.
SITE_FIT_MAX_SAMPLES = 60


class SiteFit:
    """S78: the observing site (latitude, longitude) fitted to the mount's pointings.

    A pointing is the mount's RA/Dec (J2000) and the altitude and azimuth it reports
    for them at a JD (a light's header ``RA``, ``DEC``, ``ALTITUDE``, ``AZIMUTH`` at
    ``DATE-OBS``, or a live mount poll). The mount computes altitude and azimuth from
    its own site and clock (the Seestar takes them from the phone), so the site that
    reproduces them is the telescope's, whatever the Settings site says (X3, S66).
    Gauss-Newton on (lat, lon) from a coarse grid, then from the last solution; the
    same fast spherical trig as :func:`horizontal_at`.
    """

    def __init__(self) -> None:
        self._samples: list[tuple[float, float, float, float, float]] = []
        self._fitted: tuple[float, float, float] | None = None  # lat, lon, rms
        self._fitted_n = 0

    def add(self, jd: float, ra_hours: float, dec_deg: float, alt: float, az: float) -> None:
        values = (jd, ra_hours, dec_deg, alt, az)
        if all(v is not None and math.isfinite(float(v)) for v in values) and alt > 0:
            self._samples.append(tuple(float(v) for v in values))

    def __len__(self) -> int:
        return len(self._samples)

    @property
    def last_jd(self) -> float | None:
        """The JD of the newest pointing added, or None."""
        return max((s[0] for s in self._samples), default=None)

    def site(self) -> tuple[float, float] | None:
        """(latitude, longitude) degrees, or None: too few pointings, too short a span,
        or the pointings disagree with every site (``SITE_FIT_MAX_RMS_DEG``)."""
        samples = self._samples
        if len(samples) < SITE_FIT_MIN_SAMPLES:
            return None
        jds = [s[0] for s in samples]
        if (max(jds) - min(jds)) * 86_400.0 < SITE_FIT_MIN_SPAN_S:
            return None
        if self._fitted is None or self._fitted_n != len(samples):
            self._fitted = _fit_site(_spread(samples, SITE_FIT_MAX_SAMPLES), self._fitted)
            self._fitted_n = len(samples)
        if self._fitted is None or self._fitted[2] > SITE_FIT_MAX_RMS_DEG:
            return None
        return self._fitted[0], self._fitted[1]

    @property
    def rms_deg(self) -> float | None:
        """The fit's rms (degrees) over the pointings it used, once fitted."""
        return self._fitted[2] if self._fitted is not None else None


def _spread(samples, n: int):
    """At most ``n`` of ``samples`` (time-ordered), evenly spread, first and last kept."""
    ordered = sorted(samples)
    if len(ordered) <= n:
        return ordered
    step = (len(ordered) - 1) / (n - 1)
    return [ordered[round(i * step)] for i in range(n)]


def _site_residuals(samples, lat: float, lon: float) -> list[float]:
    out = []
    for jd, ra, dec, alt, az in samples:
        a, z = horizontal_at(jd, ra, dec, lat, lon)
        out.append(a - alt)
        out.append(((z - az + 180.0) % 360.0 - 180.0) * math.cos(math.radians(alt)))
    return out


def _fit_site(samples, start: tuple[float, float, float] | None):
    """Gauss-Newton on (lat, lon) -> (lat, lon, rms) or None. From ``start`` when given
    (the last fit), else from the best of a 10° x 15° grid."""

    def cost(p):
        return sum(r * r for r in _site_residuals(samples, p[0], p[1]))

    if start is not None:
        p = [start[0], start[1]]
    else:
        coarse = samples[:: max(1, len(samples) // 8)]
        best = None
        for lat in range(-80, 81, 10):
            for lon in range(-180, 180, 15):
                c = sum(r * r for r in _site_residuals(coarse, lat, lon))
                if best is None or c < best[0]:
                    best = (c, [float(lat), float(lon)])
        p = best[1]
    step = 1e-4
    for _ in range(30):
        r0 = _site_residuals(samples, p[0], p[1])
        cols = []
        for k in range(2):
            q = list(p)
            q[k] += step
            rk = _site_residuals(samples, q[0], q[1])
            cols.append([(b - a) / step for a, b in zip(r0, rk)])
        # 2x2 normal equations J^T J d = -J^T r
        a11 = sum(x * x for x in cols[0])
        a12 = sum(x * y for x, y in zip(cols[0], cols[1]))
        a22 = sum(y * y for y in cols[1])
        b1 = -sum(x * r for x, r in zip(cols[0], r0))
        b2 = -sum(y * r for y, r in zip(cols[1], r0))
        det = a11 * a22 - a12 * a12
        if abs(det) < 1e-18:
            return None
        d0 = (b1 * a22 - b2 * a12) / det
        d1 = (a11 * b2 - a12 * b1) / det
        p = [max(-90.0, min(90.0, p[0] + d0)), (p[1] + d1 + 180.0) % 360.0 - 180.0]
        if abs(d0) < 1e-7 and abs(d1) < 1e-7:
            break
    rms = math.sqrt(cost(p) / (2 * len(samples)))
    return p[0], p[1], rms
