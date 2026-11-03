"""Settings site against the mount (PROPOSAL §7; port of release/0.5.0 commit de5732f).

The fixture is the first frame of the owner's 2026-09-25 RR Lyr run: the
Settings site was still Berkeley while the telescope was in France. The
mount put RR Lyr at altitude 75.4°, azimuth 258.9°; seen from Berkeley the
same RA/Dec was at altitude 13.8°, azimuth 45.9°, 88.5° apart. From Paris
(the right site) the two directions agree within 2.8°.
"""

from __future__ import annotations

import math
import re
import threading
from datetime import datetime, timezone

import pytest

from argos.server.devices import alpaca as adapter
from argos.server.devices.base import MountReading
from argos.server.site_check import (
    SITE_CHECK_TOLERANCE_DEG,
    SiteCheck,
    angle_between_directions,
    evaluate,
    ground_distance_km,
    horizontal_at,
    observing_site,
)
from argos.core.photometry.airmass import julian_date
from tests.server.conftest import AUTH, TOKEN, receive_until, wait_for

FIRST_FRAME = datetime(2026, 9, 25, 20, 4, 56, 567000, tzinfo=timezone.utc)
RR_LYR = (19.4246239451336, 42.7853574181895)  # RA (h), Dec (°) of that frame
MOUNT_ALT, MOUNT_AZ = 75.375833, 258.927222  # FITS of that frame (the mount's own view)
BERKELEY = {"site.name": "Berkeley", "site.latitude": 37.87084, "site.longitude": -122.27286}
PARIS = {"site.name": "Paris", "site.latitude": 48.8566, "site.longitude": 2.3522}


def _reading(state: str = "tracking", alt: float | None = MOUNT_ALT, az: float | None = MOUNT_AZ):
    return MountReading(
        state=state,
        ra_hours=RR_LYR[0],
        dec_deg=RR_LYR[1],
        alt_deg=alt,
        az_deg=az,
        tracking=True,
        pier_side=None,
    )


def _getter(values: dict):
    return lambda key, default=None: values.get(key, default)


@pytest.fixture
def offline_iers():
    """No IERS download (as tests/server/test_sim_mount.py), restored after.

    The bundled predictive table may be older than astropy's 30-day limit for a
    2026 date; UT1-UTC stays within a second of it, about 0.004° of sky.
    """
    from astropy.utils import iers

    with iers.conf.set_temp("auto_download", False), iers.conf.set_temp("auto_max_age", None):
        yield


# -- geometry ---------------------------------------------------------------------


def test_horizontal_at_matches_astropy_to_a_fraction_of_a_degree(offline_iers):
    """de5732f's test: the fast formula stays well inside the 5° tolerance."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time

    ra_h, dec = RR_LYR
    for lat, lon in ((37.87084, -122.27286), (48.8566, 2.3522), (-33.87, 151.21)):
        alt, az = horizontal_at(julian_date(FIRST_FRAME), ra_h, dec, lat, lon)
        frame = AltAz(
            obstime=Time(FIRST_FRAME),
            location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg),
            pressure=0 * u.hPa,
        )
        ref = SkyCoord(ra=ra_h * 15.0 * u.deg, dec=dec * u.deg).transform_to(frame)
        assert angle_between_directions(alt, az, ref.alt.deg, ref.az.deg) < 0.3


def test_horizontal_at_sweep_against_astropy(offline_iers):
    """Random 2026 directions and sites: the claim of :func:`horizontal_at`'s docstring.

    Coordinates of date (what the mount reports) agree within 0.05°; J2000
    coordinates fed in directly are off by the precession since 2000, up to
    about 0.4° in 2026 (bounded here at 0.5°).
    """
    import random

    import astropy.units as u
    from astropy.coordinates import FK5, AltAz, EarthLocation, SkyCoord
    from astropy.time import Time

    rng = random.Random(20261102)
    worst_of_date = worst_j2000 = 0.0
    n = 0
    while n < 120:
        ra_h, dec = rng.uniform(0, 24), math.degrees(math.asin(rng.uniform(-1, 1)))
        lat, lon = math.degrees(math.asin(rng.uniform(-0.95, 0.95))), rng.uniform(-180, 180)
        when = (
            datetime(2026, 1, 1, tzinfo=timezone.utc)
            + (
                datetime(2027, 1, 1, tzinfo=timezone.utc)
                - datetime(2026, 1, 1, tzinfo=timezone.utc)
            )
            * rng.random()
        )
        t = Time(when)
        frame = AltAz(
            obstime=t, location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg), pressure=0 * u.hPa
        )
        ref = SkyCoord(ra=ra_h * 15 * u.deg, dec=dec * u.deg, frame=FK5(equinox=t))
        ref = ref.transform_to(frame)
        if ref.alt.deg < 2.0:
            continue  # below the horizon: never compared
        n += 1
        alt, az = horizontal_at(julian_date(when), ra_h, dec, lat, lon)
        worst_of_date = max(
            worst_of_date, angle_between_directions(alt, az, ref.alt.deg, ref.az.deg)
        )
        icrs = SkyCoord(ra=ra_h * 15 * u.deg, dec=dec * u.deg).transform_to(frame)
        worst_j2000 = max(worst_j2000, angle_between_directions(alt, az, icrs.alt.deg, icrs.az.deg))
    assert worst_of_date < 0.05, worst_of_date
    assert worst_j2000 < 0.5, worst_j2000


def test_angle_between_directions():
    assert angle_between_directions(90.0, 0.0, 90.0, 123.0) < 1e-6  # zenith, any azimuth
    assert abs(angle_between_directions(0.0, 0.0, 0.0, 90.0) - 90.0) < 1e-9
    assert abs(angle_between_directions(10.0, 350.0, 10.0, 10.0) - 19.70) < 0.01


def test_ground_distance():
    # Paris to Berkeley, about 8 950 km on a sphere.
    assert ground_distance_km(48.8566, 2.3522, 37.87084, -122.27286) == pytest.approx(
        8950, rel=0.01
    )
    assert ground_distance_km(10.0, 20.0, 10.0, 20.0) == 0.0


def test_observing_site_rule():
    assert observing_site(_getter({})) is None  # 0/0 default, no name: not a site
    assert observing_site(_getter({"site.name": "Null Island"})) == (0.0, 0.0, 0.0)
    assert observing_site(_getter({"site.latitude": 45.0})) == (45.0, 0.0, 0.0)
    assert observing_site(_getter({"site.latitude": "x"})) is None


# -- the rule on the 2026-09-25 fixture ----------------------------------------------


def test_berkeley_site_is_a_mismatch_of_88_5_degrees():
    record = evaluate(_reading(), _getter(BERKELEY), FIRST_FRAME, trigger="connect")
    assert record["state"] == "mismatch"
    assert record["reason"] is None
    assert record["separation_deg"] == pytest.approx(88.5, abs=0.3)
    # Fast trig, good to about 0.1-0.2° (astropy gives altitude 13.8°, azimuth 45.9°).
    assert record["expected"]["alt_deg"] == pytest.approx(13.8, abs=0.3)
    assert record["expected"]["az_deg"] == pytest.approx(45.9, abs=0.3)
    assert record["altitude_diff_deg"] == pytest.approx(75.4 - 13.8, abs=0.3)
    assert record["mount"] == {
        "ra_hours": RR_LYR[0],
        "dec_deg": RR_LYR[1],
        "alt_deg": MOUNT_ALT,
        "az_deg": MOUNT_AZ,
    }
    assert record["site"] == {"name": "Berkeley", "latitude": 37.87084, "longitude": -122.27286}
    assert record["checked_utc"] == "2026-09-25T20:04:56.567Z"
    assert record["tolerance_deg"] == SITE_CHECK_TOLERANCE_DEG == 5.0
    assert "Observer & site" in record["message"]


def test_paris_site_agrees_within_2_8_degrees():
    record = evaluate(_reading(), _getter(PARIS), FIRST_FRAME)
    assert record["state"] == "ok"
    assert record["separation_deg"] == pytest.approx(2.8, abs=0.2)
    assert record["message"] == "The Settings site agrees with the mount (2.8° apart)."


def test_direction_not_altitude_decides():
    """Altitudes can cross while the directions stay far apart (end of the 2026-09-25
    run: 6.2° in altitude, 83.6° in direction). Same altitude, opposite azimuth:
    the altitude alone would say "fine"."""
    site = _getter(PARIS)
    expected = evaluate(_reading(), site, FIRST_FRAME)["expected"]
    mirrored = _reading(alt=expected["alt_deg"], az=(expected["az_deg"] + 180.0) % 360.0)
    record = evaluate(mirrored, site, FIRST_FRAME)
    assert abs(record["altitude_diff_deg"]) < 0.01
    assert record["state"] == "mismatch"
    assert record["separation_deg"] > 20.0


def test_no_site_and_no_position_are_unknown():
    no_site = evaluate(_reading(), _getter({}), FIRST_FRAME)
    assert no_site["state"] == "unknown" and no_site["reason"] == "no_site"
    assert no_site["separation_deg"] is None and no_site["expected"] is None
    assert no_site["mount"]["alt_deg"] == MOUNT_ALT  # the reading is still shown
    no_position = evaluate(_reading(alt=None, az=None), _getter(PARIS), FIRST_FRAME)
    assert no_position["state"] == "unknown" and no_position["reason"] == "no_position"


def test_driver_site_is_compared_directly():
    paris_driver = (48.85, 2.35, 35.0)
    agree = evaluate(_reading(), _getter(PARIS), FIRST_FRAME, driver_site=paris_driver)
    assert agree["state"] == "ok"
    assert agree["driver_site"]["state"] == "ok"
    assert agree["driver_site"]["distance_km"] < 2.0
    # Settings say Berkeley, the driver says Paris: both comparisons disagree.
    stale = evaluate(_reading(), _getter(BERKELEY), FIRST_FRAME, driver_site=paris_driver)
    assert stale["state"] == "mismatch"
    assert stale["driver_site"]["state"] == "mismatch"
    assert stale["driver_site"]["distance_km"] == pytest.approx(8950, rel=0.01)
    assert "km from the Settings site" in stale["message"]
    # A site 300 km off: pointing within 5°, but the driver says it is elsewhere.
    lyon_ish = {"site.name": "300 km south", "site.latitude": 46.16, "site.longitude": 2.35}
    near = evaluate(_reading(), _getter(lyon_ish), FIRST_FRAME, driver_site=paris_driver)
    assert near["separation_deg"] < SITE_CHECK_TOLERANCE_DEG
    assert near["driver_site"]["state"] == "mismatch" and near["state"] == "mismatch"
    # Without a Settings site the driver's site cannot be judged.
    unknown = evaluate(_reading(), _getter({}), FIRST_FRAME, driver_site=paris_driver)
    assert unknown["driver_site"]["state"] == "unknown"
    assert unknown["driver_site"]["distance_km"] is None


# -- the checker: when it runs ---------------------------------------------------------


class _Recorder:
    def __init__(self, values: dict):
        self.values = dict(values)
        self.announced = 0
        self.logs: list[tuple[str, str]] = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def announce(self):
        self.announced += 1

    def log(self, level, message):
        self.logs.append((level, message))

    def checks(self):
        return [(lvl, m) for lvl, m in self.logs if m.startswith("Site check")]


def _checker(values: dict, period_s: float = 300.0, settle_s: float = 0.0, monotonic=None):
    rec = _Recorder(values)
    extra = {"monotonic": monotonic} if monotonic is not None else {}
    check = SiteCheck(
        rec.get,
        rec.announce,
        rec.log,
        period_s=period_s,
        settle_s=settle_s,
        clock=lambda: FIRST_FRAME,
        **extra,
    )
    return check, rec


def test_checked_once_per_connection_on_the_first_reading_that_is_not_a_slew():
    check, rec = _checker(BERKELEY)
    assert check.record()["reason"] == "no_mount"
    check.mount_connected(1, None)
    assert check.record()["reason"] == "waiting"
    check.on_reading(_reading(state="slewing", alt=30.0, az=0.0), 1)
    assert check.record()["reason"] == "waiting" and rec.checks() == []
    check.on_reading(_reading(), 1)
    check.on_reading(_reading(), 1)  # once per connection (until the period)
    checks = rec.checks()
    assert len(checks) == 1
    level, message = checks[0]
    assert level == "warning"
    found = re.search(r"altitude ([\d.]+)°.* altitude ([\d.]+)°.* ([\d.]+)° apart", message)
    assert found is not None, message
    mount, expected, apart = (float(v) for v in found.groups())
    assert mount == 75.4
    assert abs(expected - 13.8) < 0.3 and abs(apart - 88.5) < 0.3
    assert "(37.871°, -122.273°)" in message and "Observer & site" in message
    assert check.record()["trigger"] == "connect"


def test_agreeing_site_is_confirmed_with_an_info_line():
    check, rec = _checker(PARIS)
    check.mount_connected(1, None)
    check.on_reading(_reading(), 1)
    assert rec.checks() == [
        ("info", "Site check: the Settings site agrees with the mount (2.8° apart).")
    ]


def test_driver_site_mismatch_alone_is_never_logged_as_agreeing():
    """Pointing within 5° but the driver's own site 111 km away: one WARN, no INFO 'agrees'."""
    check, rec = _checker(PARIS)
    check.mount_connected(1, (47.9029, 1.9093, None))  # Orléans
    check.on_reading(_reading(), 1)
    assert check.record()["state"] == "mismatch"
    checks = rec.checks()
    assert [lvl for lvl, _ in checks] == ["warning"], checks
    message = checks[0][1]
    assert "pointing agrees with the Settings site (2.8° apart), but" in message
    assert "111 km from the Settings site" in message
    assert not any(lvl == "info" for lvl, _ in checks)


def test_pointing_and_driver_mismatch_log_two_warnings_and_no_info():
    check, rec = _checker(BERKELEY)
    check.mount_connected(1, (48.85, 2.35, None))
    check.on_reading(_reading(), 1)
    levels = [lvl for lvl, _ in rec.checks()]
    assert levels == ["warning", "warning"]
    assert "pointing agrees" not in rec.checks()[1][1]


def test_no_site_means_no_log_and_unknown():
    check, rec = _checker({})
    check.mount_connected(1, None)
    check.on_reading(_reading(), 1)
    assert rec.checks() == []
    assert check.record()["state"] == "unknown" and check.record()["reason"] == "no_site"


def test_checked_again_after_a_reconnect_and_forgotten_on_disconnect():
    check, rec = _checker(BERKELEY)
    check.mount_connected(1, None)
    check.on_reading(_reading(), 1)
    check.mount_disconnected()
    assert check.record()["state"] == "unknown" and check.record()["reason"] == "no_mount"
    check.on_reading(_reading(), 1)  # a late poll of the gone mount: ignored
    assert len(rec.checks()) == 1
    check.mount_connected(2, None)
    check.on_reading(_reading(), 2)
    assert len(rec.checks()) == 2


def test_a_newer_connection_is_not_cleared_by_an_older_disconnect():
    check, _rec = _checker(PARIS)
    check.mount_connected(5, None)
    check.mount_disconnected(before=4)  # the teardown of generation 4 arrives late
    assert check.record()["reason"] == "waiting"
    check.mount_disconnected(before=6)
    assert check.record()["reason"] == "no_mount"


def test_periodic_check_speaks_only_when_the_verdict_changes():
    check, rec = _checker(PARIS, period_s=0.0)
    check.mount_connected(1, None)
    check.on_reading(_reading(), 1)  # connect: INFO
    check.on_reading(_reading(), 1)  # periodic, still ok: silent
    assert len(rec.checks()) == 1
    assert check.record()["trigger"] == "periodic"
    check.on_reading(_reading(az=(MOUNT_AZ + 90.0) % 360.0), 1)  # now far off: WARN
    assert rec.checks()[-1][0] == "warning"
    check.on_reading(_reading(), 1)  # back: INFO "again"
    assert rec.checks()[-1] == (
        "info",
        "Site check: the Settings site agrees with the mount again (2.8° apart).",
    )
    assert len(rec.checks()) == 3


def test_periodic_check_waits_for_its_period():
    check, rec = _checker(PARIS, period_s=3600.0)
    check.mount_connected(1, None)
    check.on_reading(_reading(), 1)
    announced = rec.announced
    check.on_reading(_reading(), 1)
    assert rec.announced == announced  # nothing due, nothing published


def test_site_change_rechecks_on_the_next_reading():
    check, rec = _checker(PARIS)
    check.mount_connected(1, None)
    check.on_reading(_reading(), 1)
    assert check.record()["state"] == "ok"
    rec.values.update(BERKELEY)
    check.site_changed()
    check.on_reading(_reading(state="slewing"), 1)  # never during a slew
    assert check.record()["state"] == "ok"
    check.on_reading(_reading(), 1)
    assert check.record()["state"] == "mismatch"
    assert check.record()["trigger"] == "site_change"
    assert rec.checks()[-1][0] == "warning"


def test_site_change_waits_until_the_site_settles():
    """Latitude and longitude are separate commits: never compare a half-typed site."""
    now = [1000.0]
    check, rec = _checker(PARIS, settle_s=2.0, monotonic=lambda: now[0])
    check.mount_connected(1, None)
    check.on_reading(_reading(), 1)  # the connect check is not delayed
    assert check.record()["trigger"] == "connect"
    rec.values["site.latitude"] = 37.87084  # Berkeley's latitude, Paris's longitude
    check.site_changed()
    now[0] += 1.0
    check.on_reading(_reading(), 1)
    assert check.record()["trigger"] == "connect"  # not checked yet
    rec.values["site.longitude"] = -122.27286
    check.site_changed()  # the second commit restarts the pause
    now[0] += 1.5
    check.on_reading(_reading(), 1)
    assert check.record()["trigger"] == "connect"
    now[0] += 0.6
    check.on_reading(_reading(), 1)
    record = check.record()
    assert record["trigger"] == "site_change" and record["state"] == "mismatch"
    warnings = [m for lvl, m in rec.checks() if lvl == "warning"]
    assert len(warnings) == 1 and "(37.871°, -122.273°)" in warnings[0]  # the whole new site


def test_manual_check_uses_the_latest_reading():
    check, _rec = _checker(PARIS)
    assert check.check_now() is None  # no mount
    check.mount_connected(1, None)
    assert check.check_now()["reason"] == "waiting"  # no reading yet
    check.on_reading(_reading(state="slewing"), 1)
    record = check.check_now()
    assert record["trigger"] == "manual" and record["state"] in ("ok", "mismatch")


# -- through the server --------------------------------------------------------------


class FixtureTelescope:
    """The Seestar of the 2026-09-25 run, as the core Telescope wrapper sees it."""

    site: tuple | None = None

    def __init__(self, host, port):
        self._site = FixtureTelescope.site

    def connect(self):
        return "Seestar S30 Pro"

    def get_position(self):
        from argos.core.alpaca.telescope import MountPosition

        return MountPosition(
            ra=RR_LYR[0],
            dec=RR_LYR[1],
            altitude=MOUNT_ALT,
            azimuth=MOUNT_AZ,
            tracking=True,
            slewing=False,
        )

    def is_parked(self):
        return False

    def side_of_pier(self):
        return None

    def disconnect(self):
        pass


@pytest.fixture
def fixture_mount(monkeypatch):
    FixtureTelescope.site = None
    monkeypatch.setattr(adapter, "Telescope", FixtureTelescope)
    monkeypatch.setattr(adapter.AlpacaMount, "poll_interval_s", 0.25)


def _connect_alpaca_mount(client):
    response = client.post(
        "/api/devices/mount/connect",
        json={"mode": "alpaca", "host": "192.168.1.42", "port": 32323},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text


def _freeze(client, when=FIRST_FRAME):
    client.app.state.hub.site_check.clock = lambda: when


def test_server_reports_the_2026_09_25_mismatch(client, fixture_mount):
    _freeze(client)
    assert client.patch("/api/config", json=BERKELEY, headers=AUTH).status_code == 200
    assert client.get("/api/site/check", headers=AUTH).json()["reason"] == "no_mount"
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        _connect_alpaca_mount(client)
        event = receive_until(
            ws, lambda m: m["type"] == "site_check" and m["state"] != "unknown", timeout=5
        )
        warn = receive_until(
            ws,
            lambda m: m["type"] == "log" and m["message"].startswith("Site check"),
            timeout=5,
        )
    assert event["state"] == "mismatch"
    assert event["separation_deg"] == pytest.approx(88.5, abs=0.3)
    assert event["trigger"] == "connect"
    assert warn["level"] == "warning" and warn["source"] == "mount" and warn["topic"] == "mount"
    status = client.get("/api/status", headers=AUTH).json()
    assert status["site_check"]["state"] == "mismatch"
    assert status["site_check"]["driver_site"] is None  # this driver does not say
    assert client.get("/api/site/check", headers=AUTH).json() == status["site_check"]


def test_server_compares_the_driver_site(client, fixture_mount):
    FixtureTelescope.site = (48.8566, 2.3522, 35.0)  # the driver's SiteLatitude/Longitude
    _freeze(client)
    client.patch("/api/config", json=BERKELEY, headers=AUTH)
    _connect_alpaca_mount(client)
    record = wait_for(
        lambda: (r := client.get("/api/site/check", headers=AUTH).json())["state"] != "unknown"
        and r
    )
    assert record["driver_site"]["latitude"] == 48.8566
    assert record["driver_site"]["state"] == "mismatch"
    assert record["driver_site"]["distance_km"] == pytest.approx(8950, rel=0.01)


def test_site_change_on_the_server_rechecks(client, fixture_mount):
    _freeze(client)
    client.app.state.hub.site_check.settle_s = 0.3  # the 2 s default, shortened
    client.patch("/api/config", json=BERKELEY, headers=AUTH)
    _connect_alpaca_mount(client)
    wait_for(lambda: client.get("/api/site/check", headers=AUTH).json()["state"] == "mismatch")
    client.patch("/api/config", json=PARIS, headers=AUTH)
    record = wait_for(
        lambda: (r := client.get("/api/site/check", headers=AUTH).json())["state"] == "ok" and r
    )
    assert record["trigger"] == "site_change"
    assert record["separation_deg"] == pytest.approx(2.8, abs=0.2)
    manual = client.post("/api/site/check", headers=AUTH).json()
    assert manual["trigger"] == "manual" and manual["state"] == "ok"
    client.delete("/api/devices/mount", headers=AUTH)
    assert client.get("/api/site/check", headers=AUTH).json()["reason"] == "no_mount"
    response = client.post("/api/site/check", headers=AUTH)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_connected"


def test_simulator_mount_agrees_with_its_own_site(connected):
    """The simulator's mount sits at APC, Paris (48.8277°, 2.3826°) on the real clock."""
    connected.patch(
        "/api/config",
        json={"site.name": "APC", "site.latitude": 48.8277, "site.longitude": 2.3826},
        headers=AUTH,
    )
    record = wait_for(
        lambda: (r := connected.get("/api/site/check", headers=AUTH).json())["state"] != "unknown"
        and r["reason"] is None
        and r,
        timeout=5,
    )
    assert record["state"] == "ok", record
    # The simulator ignores precession (about 0.4° from J2000 in 2026).
    assert record["separation_deg"] < 1.0
    assert record["driver_site"]["state"] == "ok" and record["driver_site"]["distance_km"] < 1.0


def test_simulator_without_a_site_is_unknown(connected):
    record = wait_for(
        lambda: (r := connected.get("/api/site/check", headers=AUTH).json())["reason"] == "no_site"
        and r
    )
    assert record["state"] == "unknown"
    assert record["mount"] is not None


def test_site_check_is_thread_safe_under_concurrent_triggers():
    check, _rec = _checker(PARIS, period_s=0.0)
    check.mount_connected(1, None)
    errors: list[BaseException] = []

    def hammer():
        try:
            for _ in range(200):
                check.on_reading(_reading(), 1)
                check.site_changed()
                check.check_now()
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors
    assert check.record()["state"] == "ok"
    assert math.isfinite(check.record()["separation_deg"])


class _Device:
    """The alpyca telescope behind ``Telescope``: Site* properties or none."""

    def __init__(self, site: tuple | None):
        self._site = site

    @property
    def SiteLatitude(self):  # noqa: N802 - ASCOM property name
        if self._site is None:
            raise RuntimeError("Property SiteLatitude is not implemented in this driver.")
        return self._site[0]

    @property
    def SiteLongitude(self):  # noqa: N802
        return self._site[1]

    @property
    def SiteElevation(self):  # noqa: N802
        raise RuntimeError("not implemented")


def test_alpaca_adapter_reads_the_driver_site(monkeypatch):
    class NonTopocentric(FixtureTelescope):
        device_site: tuple | None = (48.85, 2.35)

        def __init__(self, host, port):
            self._site = None  # Telescope reads Site* only for topocentric drivers
            self._scope = _Device(NonTopocentric.device_site)

    monkeypatch.setattr(adapter, "Telescope", NonTopocentric)
    assert adapter.AlpacaMount("h", 1).driver_site == (48.85, 2.35, None)
    NonTopocentric.device_site = None
    assert adapter.AlpacaMount("h", 1).driver_site is None
    FixtureTelescope.site = (37.0, -122.0, 50.0)  # what Telescope.connect kept (topocentric)
    monkeypatch.setattr(adapter, "Telescope", FixtureTelescope)
    assert adapter.AlpacaMount("h", 1).driver_site == (37.0, -122.0, 50.0)
    FixtureTelescope.site = None
