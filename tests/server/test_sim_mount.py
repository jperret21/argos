"""The simulated mount model, driven by a fake clock; alt/az against astropy."""

from __future__ import annotations

import math

import pytest

from argos.server.devices.base import MountParked
from argos.server.devices.sim_mount import DEFAULT_SITE, SimMount, altaz, gmst_hours


class Clock:
    def __init__(self, t: float = 1_793_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def mount(clock) -> SimMount:
    m = SimMount(slew_rate_deg_s=10.0, clock=clock)
    m.unpark()
    return m


def test_slew_takes_distance_over_rate(mount, clock):
    mount.set_tracking(True)
    start = mount.read()
    mount.goto(start.ra_hours, 60.0)  # 30° of Dec at 10°/s
    clock.t += 1.5
    halfway = mount.read()
    assert halfway.state == "slewing"
    assert halfway.dec_deg == pytest.approx(75.0)
    clock.t += 1.6
    done = mount.read()
    assert done.state == "tracking" and done.dec_deg == pytest.approx(60.0)


def test_ra_takes_the_short_way_round(mount, clock):
    mount.goto(23.9, 0.0)
    clock.t += 100
    mount.goto(0.1, 0.0)  # 0.2 h = 3° the short way, not 357°
    clock.t += 0.31
    assert mount.read().state == "tracking"


def test_tracking_holds_radec_and_idle_drifts_at_sidereal_rate(mount, clock):
    mount.goto(6.0, 10.0)
    clock.t += 100
    tracked = mount.read()
    clock.t += 3600
    assert mount.read().ra_hours == pytest.approx(tracked.ra_hours)
    mount.set_tracking(False)
    clock.t += 3600
    drifted = mount.read()
    assert drifted.state == "idle"
    assert drifted.ra_hours - tracked.ra_hours == pytest.approx(1.0027379, abs=1e-6)
    assert drifted.dec_deg == pytest.approx(10.0)


def test_park_and_aborted_park(mount, clock):
    mount.goto(6.0, 0.0)
    clock.t += 100
    mount.park()
    assert mount.read().state == "slewing" and not mount.read().tracking
    clock.t += 3.0  # 30° of the 90° to the pole
    mount.stop()
    stopped = mount.read()
    assert stopped.state == "idle"  # an aborted park leaves the mount unparked
    assert stopped.dec_deg == pytest.approx(30.0)
    mount.park()
    clock.t += 10.0
    parked = mount.read()
    assert parked.state == "parked" and parked.dec_deg == pytest.approx(90.0)
    with pytest.raises(MountParked):
        mount.goto(1.0, 1.0)
    with pytest.raises(MountParked):
        mount.set_tracking(True)


@pytest.fixture
def offline_iers():
    """No IERS download (offline-safe, like the core telescope wrapper), restored after.

    Setting ``iers.conf.auto_download`` for good leaked into the core tests run
    after this module (they then failed on predictive IERS values).
    """
    from astropy.utils import iers

    with iers.conf.set_temp("auto_download", False):
        yield


def test_gmst_matches_astropy(offline_iers):
    from astropy.time import Time

    t = Time("2024-06-01T22:00:00", scale="utc")
    expected = t.sidereal_time("mean", "greenwich", model="IAU1982").hour
    assert gmst_hours(t.unix) == pytest.approx(expected, abs=2e-4)  # < 1 s of time


@pytest.mark.parametrize("ra,dec", [(0.0, 0.0), (6.0, 45.0), (12.5, -20.0), (18.6, 38.8)])
def test_altaz_within_half_a_degree_of_astropy(offline_iers, ra, dec):
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time

    t = Time("2024-06-01T22:00:00", scale="utc")
    site = EarthLocation.from_geodetic(
        DEFAULT_SITE.longitude_deg * u.deg,
        DEFAULT_SITE.latitude_deg * u.deg,
        DEFAULT_SITE.elevation_m * u.m,
    )
    frame = AltAz(obstime=t, location=site, pressure=0 * u.hPa)  # no refraction
    expected = SkyCoord(ra=ra * 15 * u.deg, dec=dec * u.deg, frame="icrs").transform_to(frame)
    alt, az = altaz(ra, dec, t.unix, DEFAULT_SITE)
    # Great-circle distance between the two directions. The closed form ignores
    # precession since J2000 (~0.34° by 2024), nutation and aberration.
    a1, a2 = math.radians(alt), expected.alt.rad
    cos_sep = math.sin(a1) * math.sin(a2) + math.cos(a1) * math.cos(a2) * math.cos(
        math.radians(az) - expected.az.rad
    )
    separation = math.degrees(math.acos(min(1.0, cos_sep)))
    assert separation < 0.5
