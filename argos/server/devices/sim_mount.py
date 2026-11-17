"""Simulated equatorial mount: slews, sidereal tracking, park/unpark, abort.

The model is evaluated lazily from the wall clock: every call first
*advances* the state to "now" (finishing a slew whose time is up), so no
thread is needed and :meth:`SimMount.read` is microseconds.

- **Slew** — each axis moves at ``slew_rate_deg_s`` (RA measured as an angle,
  15°/h, the short way round); the slew ends when the slower axis arrives.
  A GoTo turns tracking on, like ``Telescope.slew_to``.
- **Tracking on** — RA/Dec stay fixed on the sky.
- **Tracking off** (idle or parked) — the axes stand still, so the hour angle
  is fixed and the RA advances with local sidereal time.
- **Park** — slews to the celestial pole and stops tracking.

- **Jog** (wave 3) — ``MoveAxis`` moves the primary axis (RA, positive
  east) and the secondary axis (Dec, positive north) at up to
  :data:`MAX_AXIS_RATE_DEG_S`, on top of tracking or drift; a GoTo, an
  abort or a park stops both axes.
- **Tracking rates** (wave 3) — sidereal, lunar, solar and king are listed
  and read back; the model tracks at the sidereal rate whatever is set.

Alt/az use a closed-form GMST and the textbook spherical triangle — no
astropy in a 4 Hz loop, and no IERS table to download in the field. They
ignore precession, nutation and refraction (≈0.4° from J2000 in 2026), which
``tests/server/test_sim_mount.py`` checks against astropy. Pier side follows
the German-equatorial convention from the hour angle (the real Seestar is
alt-az and reports none).
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

from argos.server.devices.base import DeviceError, MountParked, MountReading

#: Sidereal day / solar day: hours of LST per hour of UTC.
_SIDEREAL_RATIO = 1.00273790935


@dataclass(frozen=True)
class Site:
    latitude_deg: float
    longitude_deg: float  # east positive
    elevation_m: float = 0.0


#: APC laboratory, Paris — a fixed, plausible default observing site.
DEFAULT_SITE = Site(latitude_deg=48.8277, longitude_deg=2.3826, elevation_m=60.0)

#: Park position: the celestial pole, as on an equatorial mount.
PARK_DEC_DEG = 90.0
#: Fastest MoveAxis rate the simulator accepts (deg/s), the Qt dialog's top speed.
MAX_AXIS_RATE_DEG_S = 5.0
#: ASCOM DriveRates the simulator lists, in enum order.
TRACKING_RATES = ("sidereal", "lunar", "solar", "king")


def gmst_hours(unix_time: float) -> float:
    """Greenwich mean sidereal time (h) — IAU 1982 linear form, ~0.1 s accuracy."""
    days = unix_time / 86400.0 + 2440587.5 - 2451545.0
    return (18.697374558 + 24.06570982441908 * days) % 24.0


def lst_hours(unix_time: float, longitude_deg: float) -> float:
    return (gmst_hours(unix_time) + longitude_deg / 15.0) % 24.0


def altaz(ra_hours: float, dec_deg: float, unix_time: float, site: Site) -> tuple[float, float]:
    """(altitude, azimuth) in degrees, azimuth from north through east."""
    ha = math.radians((lst_hours(unix_time, site.longitude_deg) - ra_hours) * 15.0)
    dec = math.radians(dec_deg)
    lat = math.radians(site.latitude_deg)
    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(ha)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))
    east = -math.cos(dec) * math.sin(ha)
    north = math.sin(dec) * math.cos(lat) - math.cos(dec) * math.sin(lat) * math.cos(ha)
    # Rounded to 1e-6° (3.6 mas): far below the model's accuracy, and it keeps
    # float dust such as 8e-25 or 360.0 out of the telemetry.
    az = round(math.degrees(math.atan2(east, north)) % 360.0, 6) % 360.0
    return round(math.degrees(alt), 6), az


def _wrap_hours(delta: float) -> float:
    """Signed RA difference folded into [-12, 12) h — the short way round."""
    return (delta + 12.0) % 24.0 - 12.0


@dataclass
class _Slew:
    start_ra: float
    start_dec: float
    target_ra: float
    target_dec: float
    t_start: float
    duration_ra: float
    duration_dec: float
    parking: bool

    @property
    def t_end(self) -> float:
        return self.t_start + max(self.duration_ra, self.duration_dec)

    def position(self, now: float) -> tuple[float, float]:
        elapsed = max(0.0, now - self.t_start)
        f_ra = 1.0 if self.duration_ra <= 0 else min(1.0, elapsed / self.duration_ra)
        f_dec = 1.0 if self.duration_dec <= 0 else min(1.0, elapsed / self.duration_dec)
        ra = self.start_ra + _wrap_hours(self.target_ra - self.start_ra) * f_ra
        dec = self.start_dec + (self.target_dec - self.start_dec) * f_dec
        return ra % 24.0, dec


class SimMount:
    """Implements :class:`~argos.server.devices.base.MountDevice`."""

    name = "ARGOS mount simulator"
    #: ASCOM AlignmentMode (wave 3): a German equatorial model.
    alignment = "eq_gem"
    #: Mount-vs-computer clock offset: the simulator uses the computer's clock.
    clock_error_s: float | None = None

    def __init__(
        self,
        slew_rate_deg_s: float = 4.0,
        site: Site = DEFAULT_SITE,
        poll_interval_s: float = 0.25,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if slew_rate_deg_s <= 0:
            raise ValueError("slew rate must be positive")
        self.poll_interval_s = float(poll_interval_s)
        #: The mount's own site, as an Alpaca driver's SiteLatitude /
        #: SiteLongitude / SiteElevation (the hub's site check compares it).
        self.driver_site = (site.latitude_deg, site.longitude_deg, site.elevation_m)
        self._rate = float(slew_rate_deg_s)
        self._site = site
        self._clock = clock
        self._lock = threading.Lock()
        now = clock()
        # Pointing at the reference time _t0. With tracking off the hour angle
        # is what stays constant, so RA(t) = _ra0 + ΔLST.
        self._ra0 = lst_hours(now, site.longitude_deg)  # hour angle 0
        self._dec0 = PARK_DEC_DEG
        self._t0 = now
        self._tracking = False
        self._parked = True
        self._slew: _Slew | None = None
        #: MoveAxis rates (deg/s) of the primary and secondary axes.
        self._axis_rates = [0.0, 0.0]
        self._tracking_rate = TRACKING_RATES[0]
        #: Every MoveAxis call, oldest first (tests read them).
        self.axis_calls: list[tuple[int, float]] = []

    # -- model ---------------------------------------------------------------

    def _drifted_ra(self, now: float) -> float:
        if self._tracking:
            return self._ra0
        return (self._ra0 + (now - self._t0) / 3600.0 * _SIDEREAL_RATIO) % 24.0

    def _advance(self, now: float) -> None:
        """Finish a slew whose time is up (with the lock held)."""
        slew = self._slew
        if slew is None or now < slew.t_end:
            return
        self._slew = None
        self._ra0, self._dec0 = slew.target_ra % 24.0, slew.target_dec
        self._t0 = slew.t_end
        if slew.parking:
            self._parked = True
            self._tracking = False

    def _position(self, now: float) -> tuple[float, float]:
        if self._slew is not None:
            return self._slew.position(now)
        ra, dec = self._drifted_ra(now), self._dec0
        if self._axis_rates[0] or self._axis_rates[1]:
            elapsed = max(0.0, now - self._t0)
            ra = (ra + self._axis_rates[0] * elapsed / 15.0) % 24.0
            dec = max(-90.0, min(90.0, dec + self._axis_rates[1] * elapsed))
        return ra, dec

    def _stop_axes(self, now: float) -> None:
        """Lock held: stop any MoveAxis, keeping the pointing reached."""
        if self._axis_rates[0] or self._axis_rates[1]:
            self._rebase(now)
            self._axis_rates = [0.0, 0.0]

    def _rebase(self, now: float) -> None:
        """Freeze the current pointing as the new reference (with the lock held)."""
        self._ra0, self._dec0 = self._position(now)
        self._t0 = now

    def _start_slew(self, now: float, ra: float, dec: float, parking: bool) -> None:
        start_ra, start_dec = self._position(now)
        self._slew = _Slew(
            start_ra=start_ra,
            start_dec=start_dec,
            target_ra=ra % 24.0,
            target_dec=dec,
            t_start=now,
            duration_ra=abs(_wrap_hours(ra - start_ra)) * 15.0 / self._rate,
            duration_dec=abs(dec - start_dec) / self._rate,
            parking=parking,
        )

    # -- MountDevice -----------------------------------------------------------

    def read(self) -> MountReading:
        with self._lock:
            now = self._clock()
            self._advance(now)
            ra, dec = self._position(now)
            if self._parked:
                state = "parked"
            elif self._slew is not None:
                state = "slewing"
            elif self._tracking:
                state = "tracking"
            else:
                state = "idle"
            tracking = self._tracking
            parked = self._parked
        alt, az = altaz(ra, dec, now, self._site)
        hour_angle = _wrap_hours(lst_hours(now, self._site.longitude_deg) - ra)
        # GEM convention: looking west (HA ≥ 0) the mount sits east of the pier.
        pier = None if parked else ("east" if hour_angle >= 0 else "west")
        return MountReading(
            state=state,
            ra_hours=ra,
            dec_deg=dec,
            alt_deg=alt,
            az_deg=az,
            tracking=tracking,
            pier_side=pier,
        )

    def goto(self, ra_hours: float, dec_deg: float) -> None:
        with self._lock:
            now = self._clock()
            self._advance(now)
            if self._parked:
                raise MountParked("Mount is parked — unpark before slewing")
            self._stop_axes(now)
            self._tracking = True
            self._start_slew(now, ra_hours, dec_deg, parking=False)

    def stop(self) -> None:
        with self._lock:
            now = self._clock()
            self._advance(now)
            self._stop_axes(now)
            if self._slew is None:
                return
            # Freeze where the axes are; an aborted park leaves the mount unparked.
            self._rebase(now)
            self._slew = None

    def park(self) -> None:
        with self._lock:
            now = self._clock()
            self._advance(now)
            if self._parked:
                return
            self._stop_axes(now)
            # Cancel any GoTo and rebase, so the RA reference stays continuous
            # when tracking switches off for the park slew.
            self._rebase(now)
            self._slew = None
            self._tracking = False
            ra_now, _ = self._position(now)
            self._start_slew(now, ra_now, PARK_DEC_DEG, parking=True)

    def unpark(self) -> None:
        with self._lock:
            now = self._clock()
            self._advance(now)
            if not self._parked:
                return
            self._rebase(now)
            self._parked = False

    def set_tracking(self, enabled: bool) -> None:
        with self._lock:
            now = self._clock()
            self._advance(now)
            if self._parked:
                raise MountParked("Mount is parked — unpark before changing tracking")
            if self._slew is None:
                self._rebase(now)  # RA reference continuous across the switch
            self._tracking = bool(enabled)

    def sync(self, ra_hours: float, dec_deg: float) -> None:
        """ASCOM ``SyncToCoordinates`` (``telescope.py:540-562``): the current
        pointing now reads *ra_hours*, *dec_deg* (wave 4, A32 / A33)."""
        with self._lock:
            now = self._clock()
            self._advance(now)
            if self._parked:
                raise MountParked("Mount is parked — unpark before syncing")
            if self._slew is not None:
                raise DeviceError("The mount is slewing — sync once the slew has ended")
            if not self._tracking:
                raise DeviceError("Tracking must be enabled before syncing — enable tracking first")
            self._stop_axes(now)
            self._ra0, self._dec0 = float(ra_hours) % 24.0, float(dec_deg)
            self._t0 = now

    # -- wave 3: jog and tracking rate -----------------------------------------

    def move_axis(self, axis: int, rate_deg_s: float) -> None:
        """ASCOM ``MoveAxis`` (``telescope.py:564-583``): 0 = RA, 1 = Dec; 0.0 stops."""
        if axis not in (0, 1):
            raise DeviceError(f"No axis {axis}")
        rate = float(rate_deg_s)
        if abs(rate) > MAX_AXIS_RATE_DEG_S:
            raise DeviceError(f"Rate {rate:g}°/s is outside ±{MAX_AXIS_RATE_DEG_S:g}°/s")
        with self._lock:
            now = self._clock()
            self._advance(now)
            self.axis_calls.append((axis, rate))
            if rate and self._parked:
                raise MountParked("Mount is parked — unpark before jogging")
            if rate and self._slew is not None:
                raise DeviceError("The mount is slewing")
            if self._slew is None:
                self._rebase(now)  # the motion so far is kept, then the new rate
            self._axis_rates[axis] = rate

    def axis_rates(self) -> tuple[float, float]:
        with self._lock:
            return self._axis_rates[0], self._axis_rates[1]

    def tracking_rates(self) -> list[str]:
        return list(TRACKING_RATES)

    def tracking_rate(self) -> str | None:
        with self._lock:
            return self._tracking_rate

    def set_tracking_rate(self, rate: str) -> None:
        if rate not in TRACKING_RATES:
            raise DeviceError(f"Tracking rate {rate!r} is not supported")
        with self._lock:
            self._tracking_rate = rate

    def close(self) -> None:
        pass
