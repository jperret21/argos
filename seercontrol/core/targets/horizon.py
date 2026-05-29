"""Target visibility helpers — altitude now, peak altitude tonight, visibility.

Used by the Quick Session wizard to refuse targets that won't get above the
observer's horizon during the upcoming night. All math goes through astropy;
no manual coordinate transforms.

These calls are not microscopic (astropy spins up its IERS tables on first
use, ~50–200 ms). The wizard runs them in a worker, not on the UI thread.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisibilitySummary:
    """One-shot snapshot of a target's visibility for the wizard.

    Attributes:
        altitude_now_deg:   Current altitude in degrees, or None if astropy fails.
        peak_altitude_deg:  Highest altitude tonight in degrees, or None.
        peak_time_utc:      UTC time at which the peak is reached, or None.
        is_visible:         True if peak_altitude >= ``min_altitude_deg``.
    """

    altitude_now_deg:  float | None
    peak_altitude_deg: float | None
    peak_time_utc:     datetime | None
    is_visible:        bool


def altitude_now(
    ra_hours: float,
    dec_degrees: float,
    site_lat: float,
    site_lon: float,
    site_elev_m: float = 0.0,
    when_utc: datetime | None = None,
) -> float | None:
    """Return the target's altitude in degrees at ``when_utc`` (default now)."""
    try:
        target, _location, frame = _target_and_frame(
            ra_hours, dec_degrees, site_lat, site_lon, site_elev_m, when_utc
        )
    except Exception as exc:
        logger.warning("altitude_now failed: %s", exc)
        return None
    return round(float(target.transform_to(frame).alt.deg), 3)


def visibility_tonight(
    ra_hours: float,
    dec_degrees: float,
    site_lat: float,
    site_lon: float,
    site_elev_m: float = 0.0,
    when_utc: datetime | None = None,
    min_altitude_deg: float = 20.0,
    sample_minutes: int = 10,
) -> VisibilitySummary:
    """Sample the upcoming 12 h at ``sample_minutes`` cadence; report peak.

    The window starts at the later of (a) ``when_utc`` (or now) and (b) the
    next sunset; it ends at the next sunrise. Inside that window we sample
    altitude and return the maximum.
    """
    if when_utc is None:
        when_utc = datetime.now(tz=timezone.utc)
    elif when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)

    alt_now = altitude_now(ra_hours, dec_degrees, site_lat, site_lon, site_elev_m, when_utc)

    try:
        from astropy.coordinates import EarthLocation, SkyCoord
        import astropy.units as u
    except ImportError:
        logger.warning("astropy not available — visibility check skipped")
        return VisibilitySummary(alt_now, None, None, False)

    try:
        location = EarthLocation(
            lat=site_lat * u.deg, lon=site_lon * u.deg, height=site_elev_m * u.m
        )
        target = SkyCoord(
            ra=ra_hours * 15.0 * u.deg, dec=dec_degrees * u.deg, frame="icrs"
        )
        window_start, window_end = _night_window(location, when_utc)
        peak_alt, peak_time = _scan_peak(target, location, window_start, window_end, sample_minutes)
    except Exception as exc:
        logger.warning("visibility_tonight failed: %s", exc)
        return VisibilitySummary(alt_now, None, None, False)

    visible = peak_alt is not None and peak_alt >= min_altitude_deg
    return VisibilitySummary(alt_now, peak_alt, peak_time, visible)


# --------------------------------------------------------------------------- #
# Internals                                                                    #
# --------------------------------------------------------------------------- #

def _target_and_frame(
    ra_hours: float,
    dec_degrees: float,
    site_lat: float,
    site_lon: float,
    site_elev_m: float,
    when_utc: datetime | None,
):
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    import astropy.units as u
    from astropy.time import Time

    if when_utc is None:
        when_utc = datetime.now(tz=timezone.utc)
    elif when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)

    location = EarthLocation(
        lat=site_lat * u.deg, lon=site_lon * u.deg, height=site_elev_m * u.m
    )
    target = SkyCoord(
        ra=ra_hours * 15.0 * u.deg, dec=dec_degrees * u.deg, frame="icrs"
    )
    frame = AltAz(obstime=Time(when_utc), location=location)
    return target, location, frame


def _night_window(location, when_utc: datetime) -> tuple[datetime, datetime]:
    """Return (start, end) UTC of the upcoming night.

    Defined as: from max(now, next sunset) to next sunrise. Falls back to the
    next 12 h if sunrise/sunset cannot be found (polar day/night).
    """
    from astropy.coordinates import AltAz, get_sun
    import astropy.units as u
    from astropy.time import Time

    horizon_deg = -0.833  # standard atmospheric refraction at the horizon
    base = Time(when_utc)

    # Sample sun altitude every 15 minutes over the next 24 h.
    samples = base + (15 * u.min) * range(0, 96)
    sun_alt = get_sun(samples).transform_to(AltAz(obstime=samples, location=location)).alt.deg

    set_t  = _first_crossing(samples, sun_alt, going_down=True, horizon_deg=horizon_deg)
    rise_t = _first_crossing(samples, sun_alt, going_down=False, horizon_deg=horizon_deg)

    if set_t is None or rise_t is None or rise_t <= set_t:
        # Polar / edge case — give the wizard a 12 h block to scan
        end = when_utc + timedelta(hours=12)
        return when_utc, end

    start = max(when_utc, set_t)
    return start, rise_t


def _first_crossing(samples, alt_deg, *, going_down: bool, horizon_deg: float) -> datetime | None:
    """First time the sun crosses ``horizon_deg`` going in the requested direction."""
    for i in range(len(alt_deg) - 1):
        a, b = alt_deg[i], alt_deg[i + 1]
        if going_down and a > horizon_deg >= b:
            return samples[i + 1].to_datetime(timezone=timezone.utc)
        if (not going_down) and a < horizon_deg <= b:
            return samples[i + 1].to_datetime(timezone=timezone.utc)
    return None


def _scan_peak(
    target,
    location,
    start_utc: datetime,
    end_utc: datetime,
    sample_minutes: int,
) -> tuple[float | None, datetime | None]:
    from astropy.coordinates import AltAz
    import astropy.units as u
    from astropy.time import Time

    span = end_utc - start_utc
    if span.total_seconds() <= 0:
        return None, None

    n = max(2, int(span.total_seconds() // (sample_minutes * 60)) + 1)
    samples = Time(start_utc) + (span.total_seconds() / (n - 1)) * u.s * range(0, n)
    altaz = target.transform_to(AltAz(obstime=samples, location=location))
    alt = altaz.alt.deg

    # numpy array; find max + its time
    import numpy as np
    idx = int(np.argmax(alt))
    peak = round(float(alt[idx]), 3)
    peak_time = samples[idx].to_datetime(timezone=timezone.utc)
    return peak, peak_time
