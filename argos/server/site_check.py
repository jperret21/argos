"""Settings site against the mount (``web/lab/PROPOSAL.md`` §7).

The mount reports where it points (altitude, azimuth) from **its own** site
and clock; the Seestar takes them from the phone. ARGOS computes airmass,
BJD_TDB and FITS ``SITELAT`` / ``SITELONG`` from the **Settings** site.
Nothing compared the two, so a site left from an earlier trip went unnoticed
for a whole run: on 2026-09-25 the Settings site was Berkeley while the
telescope was in France, the mount put RR Lyr at altitude 75.4°, azimuth
258.9°, the Settings site at 13.8°, 45.9° (88.5° apart), and that run's
photometry airmass and AAVSO AMASS are wrong.

This is a Qt-free port of the reference implementation of release 0.5.0
(X3, merged into this branch):

- :func:`horizontal_at` and :func:`angle_between_directions` are
  ``argos.core.imaging.sky_geometry``'s (``sky_geometry.py:60-90``),
  imported since the 0.5.0 merge (wave 3; the wave 2 copies were identical);
- :func:`observing_site` is ``argos.core.config.observing_site``
  (``config.py:277-297``, X2) behind a getter adapter (the store passes
  ``get``);
- :class:`SiteCheck` follows ``DeviceSession._check_site_against_mount``
  (``device_session.py:646-676``): the whole direction is compared, never
  the altitude alone, with the same 5° tolerance and the same texts.

The server adds what the Qt release does not do: a periodic re-check every
:data:`SITE_CHECK_PERIOD_S` while the mount is connected, a re-check after a
site change, the comparison with the driver's own ``SiteLatitude`` /
``SiteLongitude`` when it exposes them, and a published record.
"""

from __future__ import annotations

import copy
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from argos.core.config import observing_site as core_observing_site
from argos.core.imaging.sky_geometry import angle_between_directions, horizontal_at
from argos.core.photometry.airmass import julian_date
from argos.server.devices.base import MountReading

#: More than this between the direction the mount reports and the one
#: computed from the Settings site means the site is not where the telescope
#: is (``de5732f``: ``SITE_CHECK_TOLERANCE_DEG``). The owner's sessions with
#: the right site agree within 1.9-3.1°; the 2026-09-25 run with a stale site
#: was 83.6-88.5° off, while its altitudes alone came within 6.2° at the end.
SITE_CHECK_TOLERANCE_DEG = 5.0
#: Driver site farther than this from the Settings site is a mismatch. About
#: 0.9° of arc on the Earth, so at most about 0.9° of altitude: a choice of
#: this server (the direct comparison has no pointing-model noise), not a
#: bound measured on sessions.
DRIVER_SITE_TOLERANCE_KM = 100.0
#: Re-check period while the mount is connected (s).
SITE_CHECK_PERIOD_S = 300.0
#: A site change is checked once the site has stayed unchanged this long (s):
#: latitude and longitude are separate commits, so checking at once compared
#: the mount with a half-typed site (one WARN said 174 km while Paris was
#: being typed, wave 2 integration). Find a place and Saved sites commit the
#: keys together and are checked after the same pause.
SITE_CHANGE_SETTLE_S = 2.0
#: Config keys whose change re-runs the check.
SITE_KEYS = frozenset({"site.name", "site.latitude", "site.longitude"})

_EARTH_RADIUS_KM = 6371.0

#: Observer texts of the ``unknown`` reasons.
_UNKNOWN_TEXT = {
    "no_mount": "No mount connected.",
    "no_site": (
        "No observing site set in Settings › Observer & site: airmass, BJD and the FITS "
        "site cannot be computed."
    ),
    "waiting": "Waiting for a mount reading that is not a slew.",
    "no_position": "The mount reports no altitude and azimuth.",
}


# ---------------------------------------------------------------------------
# Geometry: argos.core.imaging.sky_geometry (0.5.0), re-exported for the tests
# ---------------------------------------------------------------------------

__all__ = [
    "SiteCheck",
    "angle_between_directions",
    "ground_distance_km",
    "horizontal_at",
    "observing_site",
]


def ground_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two sites on a 6 371 km sphere (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


class _Getter:
    """``config.get`` for a bare getter, so ``argos.core.config.observing_site`` reads it."""

    def __init__(self, get: Callable[[str, Any], Any]) -> None:
        self.get = get


def observing_site(get: Callable[[str, Any], Any]) -> tuple[float, float, float] | None:
    """The site the observer set, ``(lat, lon, elev)``, or ``None`` (X2).

    ``argos.core.config.observing_site`` on a getter: the 0/0 default is never
    a site; a site counts as set when it has a name, or coordinates other
    than 0/0.
    """
    return core_observing_site(_Getter(get))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _unknown(reason: str) -> dict[str, Any]:
    return {
        "state": "unknown",
        "reason": reason,
        "message": _UNKNOWN_TEXT[reason],
        "tolerance_deg": SITE_CHECK_TOLERANCE_DEG,
        "checked_utc": None,
        "trigger": None,
        "site": None,
        "mount": None,
        "expected": None,
        "separation_deg": None,
        "altitude_diff_deg": None,
        "driver_site": None,
    }


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def evaluate(
    reading: MountReading,
    get: Callable[[str, Any], Any],
    when: datetime,
    driver_site: tuple[float, float, float | None] | None = None,
    trigger: str | None = None,
) -> dict[str, Any]:
    """One comparison: the SiteCheck record for *reading* at the clock *when*."""
    site = observing_site(get)
    if reading.alt_deg is None or reading.az_deg is None:
        record = _unknown("no_position")
    elif site is None:
        record = _unknown("no_site")
    else:
        record = _unknown("no_site")  # replaced below
        lat, lon, _elev = site
        alt, az = horizontal_at(julian_date(when), reading.ra_hours, reading.dec_deg, lat, lon)
        separation = angle_between_directions(alt, az, reading.alt_deg, reading.az_deg)
        mismatch = separation > SITE_CHECK_TOLERANCE_DEG
        if mismatch:
            message = (
                f"The mount points at altitude {reading.alt_deg:.1f}°, azimuth "
                f"{reading.az_deg:.1f}°; from the Settings site the same RA/Dec is at altitude "
                f"{alt:.1f}°, azimuth {az:.1f}°, {separation:.1f}° apart. Airmass, BJD and the "
                "FITS site use the Settings site: correct Settings › Observer & site if the "
                "telescope is elsewhere."
            )
        else:
            message = f"The Settings site agrees with the mount ({separation:.1f}° apart)."
        record.update(
            state="mismatch" if mismatch else "ok",
            reason=None,
            message=message,
            expected={"alt_deg": round(alt, 3), "az_deg": round(az, 3)},
            separation_deg=round(separation, 3),
            altitude_diff_deg=round(reading.alt_deg - alt, 3),
        )
    record["checked_utc"] = _iso(when)
    record["trigger"] = trigger
    if site is not None:
        record["site"] = {
            "name": str(get("site.name", "") or ""),
            "latitude": site[0],
            "longitude": site[1],
        }
    record["mount"] = {
        "ra_hours": reading.ra_hours,
        "dec_deg": reading.dec_deg,
        "alt_deg": reading.alt_deg,
        "az_deg": reading.az_deg,
    }
    if driver_site is not None:
        d_lat, d_lon, d_elev = driver_site
        distance = None
        d_state = "unknown"
        if site is not None:
            distance = ground_distance_km(site[0], site[1], d_lat, d_lon)
            d_state = "mismatch" if distance > DRIVER_SITE_TOLERANCE_KM else "ok"
        record["driver_site"] = {
            "latitude": d_lat,
            "longitude": d_lon,
            "elevation_m": d_elev,
            "distance_km": round(distance, 1) if distance is not None else None,
            "state": d_state,
        }
        if d_state == "mismatch":
            note = (
                f"The mount's own site ({d_lat:.3f}°, {d_lon:.3f}°) is {distance:.0f} km from "
                "the Settings site."
            )
            if record["state"] == "ok":
                record["state"] = "mismatch"
                record["message"] = (
                    f"{note} The pointing agrees within {record['separation_deg']:.1f}°, but "
                    "airmass, BJD and the FITS site use the Settings site: correct Settings › "
                    "Observer & site if the telescope is elsewhere."
                )
            elif record["state"] == "mismatch":
                record["message"] = f"{record['message']} {note}"
    return record


class SiteCheck:
    """The site check of the connected mount; thread-safe.

    The hub calls :meth:`mount_connected`, :meth:`mount_disconnected`,
    :meth:`on_reading` (every successful poll), :meth:`site_changed` and
    :meth:`check_now`. *announce* is called (no argument, no lock of this
    object held) after every change: the hub reads :meth:`record` under its
    own lock and publishes it, so the lock order is hub → this object.
    *log* receives ``(level, message)``.
    """

    def __init__(
        self,
        get: Callable[[str, Any], Any],
        announce: Callable[[], None],
        log: Callable[[str, str], None],
        *,
        period_s: float = SITE_CHECK_PERIOD_S,
        settle_s: float = SITE_CHANGE_SETTLE_S,
        clock: Callable[[], datetime] = _utcnow,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._get = get
        self._announce = announce
        self._log = log
        self.period_s = float(period_s)
        self.settle_s = float(settle_s)
        self.clock = clock
        self._monotonic = monotonic
        self._site_changed_at = -math.inf
        self._lock = threading.Lock()
        self._record = _unknown("no_mount")
        self._generation: int | None = None
        self._driver_site: tuple[float, float, float | None] | None = None
        self._pending: str | None = None
        self._last_check = 0.0
        self._last_reading: MountReading | None = None

    def record(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._record)

    # -- mount lifecycle ------------------------------------------------------

    def mount_connected(
        self, generation: int, driver_site: tuple[float, float, float | None] | None
    ) -> None:
        """A (re)connection: check again on its first reading that is not a slew."""
        with self._lock:
            self._generation = generation
            self._driver_site = driver_site
            self._pending = "connect"
            self._last_reading = None
            self._record = _unknown("waiting")
        self._announce()

    def mount_disconnected(self, before: int | None = None) -> None:
        """The mount went away; *before*: only a connection older than that generation."""
        with self._lock:
            if before is not None and self._generation is not None and self._generation >= before:
                return  # a newer connection already took over
            if self._generation is None and self._record["reason"] == "no_mount":
                return
            self._generation = None
            self._driver_site = None
            self._pending = None
            self._last_reading = None
            self._record = _unknown("no_mount")
        self._announce()

    def site_changed(self) -> None:
        """``site.*`` changed: check again on the next reading that is not a slew."""
        with self._lock:
            if self._generation is None:
                return
            self._site_changed_at = self._monotonic()
            if self._pending != "connect":
                self._pending = "site_change"

    # -- checks -------------------------------------------------------------------

    def on_reading(self, reading: MountReading, generation: int) -> None:
        """Every successful poll; checks when one is due and the mount is not slewing."""
        with self._lock:
            if generation != self._generation:
                return  # a poll of a mount that was disconnected meanwhile
            self._last_reading = reading
            if reading.state == "slewing":
                return
            trigger = self._pending
            now = self._monotonic()
            if trigger is not None and now - self._site_changed_at < self.settle_s:
                return  # the site is still being edited: wait until it settles
            if trigger is None and now - self._last_check >= self.period_s:
                trigger = "periodic"
            if trigger is None:
                return
        self._check(reading, trigger, generation)

    def check_now(self) -> dict[str, Any] | None:
        """``POST /api/site/check``: compare the latest reading now (``None``: no mount)."""
        with self._lock:
            generation, reading = self._generation, self._last_reading
        if generation is None:
            return None
        if reading is None:
            return self.record()  # still waiting for the first reading
        self._check(reading, "manual", generation)
        return self.record()

    def _check(self, reading: MountReading, trigger: str, generation: int) -> None:
        when = self.clock()
        with self._lock:
            driver_site = self._driver_site
        record = evaluate(reading, self._get, when, driver_site, trigger)
        with self._lock:
            if generation != self._generation:
                return
            previous = self._record["state"]
            self._record = record
            self._pending = None
            self._last_check = self._monotonic()
        self._announce()
        self._log_result(record, previous, trigger)

    def _log_result(self, record: dict[str, Any], previous: str, trigger: str) -> None:
        state = record["state"]
        if state == "unknown":
            return  # no site set or no position: nothing was compared (de5732f)
        if trigger == "periodic" and state == previous:
            return  # a periodic check speaks only when the verdict changes
        separation = record["separation_deg"]
        pointing_off = separation is not None and separation > SITE_CHECK_TOLERANCE_DEG
        if state == "mismatch" and pointing_off:
            mount, expected, site = record["mount"], record["expected"], record["site"]
            self._log(
                "warning",
                f"Site check: the mount points at altitude {mount['alt_deg']:.1f}°, azimuth "
                f"{mount['az_deg']:.1f}°; from the Settings site ({site['latitude']:.3f}°, "
                f"{site['longitude']:.3f}°) the same RA/Dec is at altitude "
                f"{expected['alt_deg']:.1f}°, azimuth {expected['az_deg']:.1f}°, "
                f"{separation:.1f}° apart. Airmass, BJD and the FITS site use the Settings "
                "site: correct Settings › Observer & site if the telescope is elsewhere.",
            )
        driver = record["driver_site"]
        driver_off = driver is not None and driver["state"] == "mismatch"
        if driver_off:
            # The verdict is a mismatch even when the pointing agrees: never log
            # "agrees" at INFO next to it (the log would contradict the screen).
            pointing = (
                f"the pointing agrees with the Settings site ({separation:.1f}° apart), but "
                if separation is not None and not pointing_off
                else ""
            )
            self._log(
                "warning",
                f"Site check: {pointing}the mount's own site ({driver['latitude']:.3f}°, "
                f"{driver['longitude']:.3f}°) is {driver['distance_km']:.0f} km from the "
                "Settings site.",
            )
        elif separation is not None and not pointing_off:
            again = " again" if trigger == "periodic" and previous == "mismatch" else ""
            self._log(
                "info",
                f"Site check: the Settings site agrees with the mount{again} "
                f"({separation:.1f}° apart).",
            )
