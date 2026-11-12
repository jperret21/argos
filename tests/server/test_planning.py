"""Wave 6a, plan: visibility, exoplanet lookups and the transit planner (A42, A65, A66).

Parity with the Qt Plan page: the transit window, its UTC instants and the
transit plan are the core functions Qt calls (``predict_next_transit``,
``utc_from_bjd_tdb``, ``make_transit_sequence``) on the same inputs; the
observation.json of a run of the web's transit plan is compared byte for
byte with the one the Qt editor's plan makes the Qt worker write (S5).
Sky geometry is checked against astropy. The NASA archive is never reached:
its HTTP call is faked (this network cannot reach it).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone

import pytest

from argos.core.catalog import exoplanets
from argos.core.catalog.exoplanets import ExoplanetTarget, _cache_key
from argos.core.exoplanet.transit import make_transit_sequence, predict_next_transit
from argos.core.imaging.sequencer import plan_to_dict
from argos.core.imaging.sky_geometry import altitude_at
from argos.core.photometry.airmass import (
    _bundled_iers_only,
    bjd_tdb,
    julian_date,
    utc_from_bjd_tdb,
)
from argos.server import planning
from argos.server import sequence_plan as sp
from argos.server.state import utc_iso
from tests.server.conftest import AUTH
from tests.server.test_sequence_plan import force_run_active

#: A made-up site (never the owner's).
LAT, LON, ELEV = 45.0, 5.0, 200.0

HD189733B = ExoplanetTarget(
    planet_name="HD 189733 b",
    host_name="HD 189733",
    ra_degrees=300.1821,
    dec_degrees=22.7099,
    period_days=2.21857567,
    epoch_bjd_tdb=2454279.436714,
    duration_hours=1.827,
    depth_percent=2.4,
    epoch_system="BJD TDB",
    retrieved_utc="2026-11-01T00:00:00+00:00",
)


def _astropy_alt(t: datetime, ra_deg: float | None, dec_deg: float | None, lat, lon) -> float:
    """Astropy altitude of a star, or of the Sun when *ra_deg* is None (no refraction)."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
    from astropy.time import Time

    _bundled_iers_only()
    when = Time(t)
    frame = AltAz(obstime=when, location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg))
    body = get_body("sun", when) if ra_deg is None else SkyCoord(ra_deg * u.deg, dec_deg * u.deg)
    return float(body.transform_to(frame).alt.deg)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):  # pragma: no cover - a test failure if reached
        raise AssertionError("the NASA archive must not be queried")

    monkeypatch.setattr(exoplanets.requests, "get", refuse)


@pytest.fixture
def planner(make_client, tmp_path, no_network):
    """A client with a site, temporary data paths and HD 189733 b in the exoplanet cache."""
    cache = tmp_path / "cache" / "exoplanets.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({_cache_key(HD189733B.planet_name): asdict(HD189733B)}))
    client = make_client(config_dir=tmp_path / "config")
    answer = client.patch(
        "/api/config",
        json={
            "sessions_path": str(tmp_path / "sessions"),
            "data_paths.exoplanet_cache": str(cache),
            "data_paths.sequence_presets_directory": str(tmp_path / "presets"),
            "site.name": "Test site",
            "site.latitude": LAT,
            "site.longitude": LON,
            "site.elevation": ELEV,
        },
        headers=AUTH,
    )
    assert answer.status_code == 200, answer.text
    client.hub = client.app.state.hub  # type: ignore[attr-defined]
    client.cache = cache  # type: ignore[attr-defined]
    client.tmp = tmp_path  # type: ignore[attr-defined]
    return client


def _set_clock(client, when: datetime) -> None:
    client.hub.planning.clock = lambda: when
    client.hub.plan.clock = lambda: when


# -- sky geometry -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "when, lat, lon",
    [
        (datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc), 45.0, 5.0),
        (datetime(2026, 6, 21, 3, 30, tzinfo=timezone.utc), 60.0, 10.0),
        (datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc), -33.9, 18.4),
        (datetime(2027, 1, 5, 23, 45, tzinfo=timezone.utc), 19.8, -155.5),
    ],
)
def test_the_sun_altitude_matches_astropy(when, lat, lon):
    got = planning.sun_altitude(when.timestamp(), lat, lon)
    assert got == pytest.approx(_astropy_alt(when, None, None, lat, lon), abs=0.05)


def test_twilight_instants_are_where_astropy_puts_the_sun():
    night = planning.night_of(date(2026, 11, 12), LAT, LON)
    tw = night["twilight"]
    for key, level in [
        ("sunset_utc", planning.SUNSET_DEG),
        ("civil_dusk_utc", -6.0),
        ("nautical_dusk_utc", -12.0),
        ("astronomical_dusk_utc", -18.0),
        ("astronomical_dawn_utc", -18.0),
        ("sunrise_utc", planning.SUNSET_DEG),
    ]:
        when = datetime.fromtimestamp(tw[key], tz=timezone.utc)
        assert _astropy_alt(when, None, None, LAT, LON) == pytest.approx(level, abs=0.06), key
    assert night["dusk"] == tw["astronomical_dusk_utc"]
    assert night["dawn"] == tw["astronomical_dawn_utc"]
    # The night of the 12th ends on the morning of the 13th (S26).
    assert datetime.fromtimestamp(night["dawn"], tz=timezone.utc).date() == date(2026, 11, 13)


def test_target_altitudes_are_the_core_s_and_agree_with_astropy(planner):
    answer = planner.get(
        "/api/visibility",
        params={"ra_hours": 19.4411, "dec_deg": 42.7844, "night": "2026-11-12"},
        headers=AUTH,
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["step_min"] == 10 and len(body["samples"]) > 60
    for sample in body["samples"][::12]:
        t = datetime.fromisoformat(sample["t_utc"].replace("Z", "+00:00"))
        core = altitude_at(t.timestamp() / 86400 + 2440587.5, 19.4411, 42.7844, LAT, LON)
        assert sample["alt_deg"] == pytest.approx(core, abs=0.001)  # Qt's plot function
        assert sample["alt_deg"] == pytest.approx(
            _astropy_alt(t, 19.4411 * 15, 42.7844, LAT, LON), abs=0.3
        )
        assert t.minute % 10 == 0 and t.second == 0
    times = [s["t_utc"] for s in body["samples"]]
    assert times == sorted(times)


# -- A65 ----------------------------------------------------------------------------------


def test_visibility_needs_a_site_never_0_0(make_client, tmp_path):
    client = make_client(config_dir=tmp_path / "config")
    params = {"ra_hours": 5.0, "dec_deg": 10.0}
    answer = client.get("/api/visibility", params=params, headers=AUTH)
    assert answer.status_code == 409
    assert answer.json()["error"] == {
        "code": "site_missing",
        "message": "Set the observing site in Settings to compute altitudes.",
    }
    # A site with a name counts, even at 0/0 (X2's rule).
    client.patch("/api/config", json={"site.name": "Gulf"}, headers=AUTH)
    assert client.get("/api/visibility", params=params, headers=AUTH).status_code == 200


def test_the_night_spans_midnight_and_the_window_uses_the_site_minimum(planner):
    params = {"ra_hours": 19.4411, "dec_deg": 42.7844, "night": "2026-11-12"}
    body = planner.get("/api/visibility", params=params, headers=AUTH).json()
    assert body["night"]["date"] == "2026-11-12"
    assert body["night"]["dusk_utc"].startswith("2026-11-12T")
    assert body["night"]["dawn_utc"].startswith("2026-11-13T")
    assert body["min_alt_deg"] == 30.0 and body["min_alt_source"] == "site"
    assert body["site"]["name"] == "Test site"
    window = body["window"]
    assert body["night"]["dusk_utc"] <= window["start_utc"] < window["end_utc"]
    assert window["end_utc"] <= body["night"]["dawn_utc"]
    end = datetime.fromisoformat(window["end_utc"].replace("Z", "+00:00")).timestamp()
    # RR Lyr sets through 30° that evening: the window ends on the limit.
    assert altitude_at(end / 86400 + 2440587.5, 19.4411, 42.7844, LAT, LON) == pytest.approx(
        30.0, abs=0.01
    )
    # The site setting (Q-P6) and a dragged handle (query).
    planner.patch("/api/config", json={"site.min_altitude_deg": 50.0}, headers=AUTH)
    higher = planner.get("/api/visibility", params=params, headers=AUTH).json()
    assert higher["min_alt_deg"] == 50.0 and higher["window"]["end_utc"] < window["end_utc"]
    handle = planner.get(
        "/api/visibility", params={**params, "min_alt_deg": 20.0}, headers=AUTH
    ).json()
    assert handle["min_alt_source"] == "query" and handle["min_alt_deg"] == 20.0
    low = planner.get("/api/visibility", params={**params, "dec_deg": -60.0}, headers=AUTH).json()
    assert low["window"] is None and low["windows"] == []
    assert low["notes"] == ["The target stays below 20° during the astronomical night."] or low[
        "notes"
    ] == ["The target stays below 50° during the astronomical night."]


@pytest.mark.parametrize(
    "now, night",
    [
        # 02:00 belongs to the night that began the evening before (P3, S26).
        (datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc), "2026-11-12"),
        (datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc), "2026-11-13"),  # dawn passed
        (datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc), "2026-11-13"),
    ],
)
def test_without_a_date_the_night_whose_dawn_has_not_passed(planner, now, night):
    _set_clock(planner, now)
    body = planner.get(
        "/api/visibility", params={"ra_hours": 3.0, "dec_deg": 20.0}, headers=AUTH
    ).json()
    assert body["night"]["date"] == night


def test_no_astronomical_night_is_said_not_drawn(planner):
    planner.patch("/api/config", json={"site.latitude": 60.0, "site.longitude": 10.0}, headers=AUTH)
    body = planner.get(
        "/api/visibility",
        params={"ra_hours": 18.0, "dec_deg": 40.0, "night": "2026-06-21"},
        headers=AUTH,
    ).json()
    assert body["night"]["dusk_utc"] is None and body["window"] is None
    assert "no astronomical darkness" in body["notes"][0]
    assert body["twilight"]["sunset_utc"] is not None  # the Sun does set
    assert body["samples"]


def test_min_altitude_is_a_site_setting_with_meta(planner):
    config = planner.get("/api/config", headers=AUTH).json()
    assert config["values"]["site.min_altitude_deg"] == 30.0
    meta = config["meta"]["site.min_altitude_deg"]
    assert meta["category"] == "observer_site" and meta["unit"] == "°"
    bad = planner.patch("/api/config", json={"site.min_altitude_deg": 95.0}, headers=AUTH)
    assert bad.status_code == 400  # refused, never clamped


# -- A42 ----------------------------------------------------------------------------------


class _Response:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


_ROW = {
    "pl_name": "WASP-12 b",
    "hostname": "WASP-12",
    "ra": 97.6366,
    "dec": 29.6723,
    "pl_orbper": 1.09142,
    "pl_orbpererr1": 1e-7,
    "pl_tranmid": 2457010.512,
    "pl_tranmiderr1": 1e-4,
    "pl_tranmid_systemref": "BJD-TDB",
    "pl_trandur": 3.0,
    "pl_trandep": 1.4,
}


def test_lookup_asks_the_archive_at_most_twice_for_12_s_and_caches(planner, monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((params["query"], timeout))
        return _Response([] if len(calls) == 1 else [_ROW])

    monkeypatch.setattr(exoplanets.requests, "get", fake_get)
    answer = planner.get("/api/exoplanets/lookup", params={"q": "wasp12"}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["planet_name"] == "WASP-12 b" and body["host_name"] == "WASP-12"
    assert body["ra_hours"] == pytest.approx(97.6366 / 15) and body["dec_deg"] == 29.6723
    assert body["epoch_system"] == "BJD-TDB" and body["duration_hours"] == 3.0
    assert [timeout for _q, timeout in calls] == [12.0, 12.0]
    assert "like" in calls[1][0]  # the partial-designation fallback
    cached = json.loads(planner.cache.read_text())
    assert any(row["planet_name"] == "WASP-12 b" for row in cached.values())
    calls.clear()
    assert (
        planner.get("/api/exoplanets/lookup", params={"q": "wasp12"}, headers=AUTH).json()[
            "planet_name"
        ]
        == "WASP-12 b"
    )
    assert calls == []  # the cache answered
    names = planner.get("/api/exoplanets/suggest", params={"q": "wasp"}, headers=AUTH).json()
    assert names == {"query": "wasp", "names": ["WASP-12 b"]}


@pytest.mark.parametrize(
    "rows, status, code",
    [
        ("down", 502, "lookup_failed"),
        ([], 404, "not_found"),
        ([{**_ROW, "pl_tranmid_systemref": "HJD"}], 422, "ephemeris_unusable"),
        ([{**_ROW, "pl_orbper": None}], 422, "ephemeris_unusable"),
    ],
)
def test_lookup_errors_keep_the_core_s_text(planner, monkeypatch, rows, status, code):
    import requests

    def fake_get(url, params=None, timeout=None):
        if rows == "down":
            raise requests.ConnectionError("no route")
        return _Response(rows)

    monkeypatch.setattr(exoplanets.requests, "get", fake_get)
    answer = planner.get("/api/exoplanets/lookup", params={"q": "Kepler-999 b"}, headers=AUTH)
    assert answer.status_code == status, answer.text
    assert answer.json()["error"]["code"] == code
    if code == "lookup_failed":
        assert answer.json()["error"]["message"] == (
            "NASA Exoplanet Archive is unavailable. Connect to the internet or use a cached planet."
        )


def test_an_empty_lookup_is_a_400(planner):
    answer = planner.get("/api/exoplanets/lookup", params={"q": "  "}, headers=AUTH)
    assert answer.status_code == 400


# -- A66 ----------------------------------------------------------------------------------

FROM = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def _qt_window(start: datetime, baseline: float = 60.0, target=HD189733B):
    """``SequencerPage._current_bjd_tdb`` then ``predict_next_transit`` (Qt)."""
    now_bjd = bjd_tdb(julian_date(start), target.ra_degrees, target.dec_degrees, LAT, LON, ELEV)
    return predict_next_transit(target, now_bjd, baseline_minutes=baseline)


def _qt_utc(bjd: float, target=HD189733B) -> str:
    when = utc_from_bjd_tdb(bjd, target.ra_degrees, target.dec_degrees, LAT, LON, ELEV)
    return utc_iso(when)


def test_the_next_transit_is_qt_s_window_and_instants(planner):
    body = {
        "planet_name": "hd189733b",
        "baseline_minutes": 45,
        "from_utc": FROM.isoformat(),
        "observable_only": False,
    }
    answer = planner.post("/api/transit/predict", json=body, headers=AUTH)
    assert answer.status_code == 200, answer.text
    got = answer.json()
    window = _qt_window(FROM, 45.0)
    assert got["window"] == {**asdict(window), "coverage_hours": window.coverage_hours}
    # S26: Find uses the Baseline field (45 min each side, not 60).
    assert got["window"]["coverage_hours"] == pytest.approx(1.827 + 1.5)
    assert got["utc"]["coverage_start"] == _qt_utc(window.coverage_start_bjd_tdb)
    assert got["utc"]["mid"] == _qt_utc(window.mid_bjd_tdb)
    assert got["utc"]["coverage_end"] == _qt_utc(window.coverage_end_bjd_tdb)
    assert got["planet"]["planet_name"] == "HD 189733 b" and got["skipped"] == []
    mid = datetime.fromisoformat(got["utc"]["mid"].replace("Z", "+00:00"))
    assert got["altitude_deg"]["mid"] == pytest.approx(
        _astropy_alt(mid, HD189733B.ra_degrees, HD189733B.dec_degrees, LAT, LON), abs=0.3
    )


def _dark_and_high(t: datetime, min_alt: float = 30.0) -> tuple[bool, bool]:
    sun = _astropy_alt(t, None, None, LAT, LON)
    star = _astropy_alt(t, HD189733B.ra_degrees, HD189733B.dec_degrees, LAT, LON)
    return sun < -18.0, star >= min_alt - 0.3


def test_daylight_and_low_transits_are_skipped_q_p10(planner):
    # A start whose next transit (Qt's choice) cannot be observed from the site.
    start = FROM
    for _ in range(40):
        window = _qt_window(start)
        mid = datetime.fromisoformat(_qt_utc(window.mid_bjd_tdb).replace("Z", "+00:00"))
        if not all(_dark_and_high(mid)):
            break
        start += timedelta(days=1)
    else:  # pragma: no cover - HD 189733 b has a daytime transit every few days
        pytest.fail("no unobservable transit found")
    body = {"planet_name": "HD 189733 b", "from_utc": start.isoformat()}
    got = planner.post("/api/transit/predict", json=body, headers=AUTH).json()
    assert got["skipped"][0]["epoch_number"] == window.epoch_number
    assert got["skipped"][0]["reason"] in ("daylight", "below_limit")
    assert got["window"]["epoch_number"] > window.epoch_number
    assert got["skipped_count"] == got["window"]["epoch_number"] - window.epoch_number
    assert got["observable"]["transit"] is True
    for key in ("ingress", "mid", "egress"):
        t = datetime.fromisoformat(got["utc"][key].replace("Z", "+00:00"))
        assert _dark_and_high(t) == (True, True), key
    assert got["night"]["dusk_utc"] <= got["utc"]["ingress"]
    assert got["utc"]["egress"] <= got["night"]["dawn_utc"]
    usable = got["usable"]
    assert usable["start_utc"] <= got["utc"]["ingress"] or got["observable"]["coverage"] is False


def test_a_chosen_epoch_is_planned_as_predicted(planner):
    body = {"planet_name": "HD 189733 b", "epoch_number": 1500, "baseline_minutes": 30}
    got = planner.post("/api/transit/predict", json=body, headers=AUTH).json()
    assert got["window"]["epoch_number"] == 1500
    assert got["window"]["mid_bjd_tdb"] == HD189733B.epoch_bjd_tdb + 1500 * HD189733B.period_days


@pytest.mark.parametrize(
    "target, body, status, text",
    [
        (replace(HD189733B, epoch_system="HJD"), {}, 400,
         "A BJD_TDB transit epoch is required for prediction."),
        (replace(HD189733B, duration_hours=None), {}, 400,
         "A published transit duration is required to prepare coverage."),
        (HD189733B, {"baseline_minutes": -5}, 400, "baseline_minutes must not be negative"),
        (HD189733B, {"baseline_minutes": 300}, 400, "The baseline is at most 240 min"),
        (replace(HD189733B, dec_degrees=-80.0), {}, 422, "No transit of HD 189733 b is observable"),
        (HD189733B, {"date": "2026-11-12", "from_utc": "2026-11-12T00:00:00Z"}, 400, "not both"),
    ],
)  # fmt: skip
def test_transit_errors(planner, target, body, status, text):
    planner.cache.write_text(json.dumps({_cache_key(target.planet_name): asdict(target)}))
    answer = planner.post(
        "/api/transit/predict", json={"planet_name": "HD 189733 b", **body}, headers=AUTH
    )
    assert answer.status_code == status, answer.text
    assert text in answer.json()["error"]["message"]


def test_transit_needs_a_site(make_client, tmp_path, no_network):
    client = make_client(config_dir=tmp_path / "config")
    answer = client.post("/api/transit/predict", json={"planet_name": "x"}, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "site_missing"


def _qt_run_observation_json(plan, tmp_path) -> str:
    """The Qt worker's observation.json for *plan* (one frame)."""
    import numpy as np

    from argos.core.imaging.fits_writer import FrameContext
    from argos.workers.sequence_worker import OBSERVATION_FILENAME, SequenceWorker

    class Camera:
        def set_gain(self, gain):
            pass

        def try_get_gain(self):
            return 80

        def start_exposure(self, exposure_s, light=True):
            pass

        def is_image_ready(self):
            return True

        def get_image_array(self):
            return np.full((32, 32), 1000, dtype=np.uint16)

        def stop_exposure(self):
            pass

    plan.steps[0].count = 1
    plan.steps[0].exposure_s = plan.steps[0].cadence_s = 0.01
    SequenceWorker(
        camera=Camera(),
        telescope=None,
        filterwheel=None,
        plan=plan,
        frame_context_provider=lambda object_name, filter_name: FrameContext(
            object_name=object_name, filter_name=filter_name
        ),
        base_dir=tmp_path,
    ).run()
    (path,) = tmp_path.glob("*/" + OBSERVATION_FILENAME)
    return path.read_text(encoding="utf-8")


def test_s5_a_web_transit_plan_writes_qt_s_observation_json(planner, tmp_path):
    """Exit criterion: the same inputs give the same observation.json as Qt's."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from argos.ui.widgets.sequence_panel import SequencePanel

    app = QApplication.instance() or QApplication(["test"])
    settings = {"exposure_s": 10.0, "cadence_s": 13.0, "gain": 80, "filter_name": "IR"}
    # Qt: Find planet, then Prepare transit sequence (sequencer_page.py:248-286).
    window = _qt_window(FROM, 60.0)
    transit = make_transit_sequence(HD189733B, window, **settings)
    panel = SequencePanel()
    try:
        notes = panel.load_plan(transit)
        qt_plan = panel.to_plan()
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()
    assert notes == []
    # Web: the same inputs.
    answer = planner.post(
        "/api/transit/plan",
        json={"planet_name": "HD 189733 b", "baseline_minutes": 60,
              "from_utc": FROM.isoformat(), "observable_only": False, **settings},
        headers=AUTH,
    )  # fmt: skip
    assert answer.status_code == 200, answer.text
    got = answer.json()
    record = got["plan"]
    assert record["plan"]["object_name"] == "HD 189733"
    assert record["plan"]["start_at_utc"] == got["prediction"]["utc"]["coverage_start"]
    assert record["notes"][0] == (
        f"Transit sequence prepared: {transit.steps[0].count} light frames at a 13.0 s cadence."
    )
    start = got["prediction"]["utc"]["coverage_start"]
    assert record["notes"][1] == f"Starts at the coverage start, {start[:10]} {start[11:16]} UTC."
    web_plan = planner.hub.plan.plan_for_run()
    assert plan_to_dict(web_plan) == plan_to_dict(qt_plan)
    assert len(web_plan.metadata) == 13
    # The observation follows the host star, its target armed (Qt's Find did it).
    observation = planner.get("/api/observation", headers=AUTH).json()
    assert observation["object_name"] == "HD 189733"
    assert observation["target"]["programme"] == "exoplanet"
    qt_text = _qt_run_observation_json(qt_plan, tmp_path / "qt")
    web_text = _qt_run_observation_json(web_plan, tmp_path / "web")
    assert web_text == qt_text
    assert sp.observation_json(planner.hub.plan.plan_for_run()) == qt_text


def test_a_transit_plan_out_of_the_camera_range_is_an_issue_not_a_clamp(planner):
    answer = planner.post(
        "/api/transit/plan",
        json={"planet_name": "HD 189733 b", "from_utc": FROM.isoformat(),
              "observable_only": False, "exposure_s": 700.0, "cadence_s": 800.0, "gain": 900},
        headers=AUTH,
    )  # fmt: skip
    assert answer.status_code == 200, answer.text
    record = answer.json()["plan"]
    step = record["plan"]["steps"][0]
    assert step["exposure_s"] == 700.0 and step["gain"] == 900 and step["cadence_s"] == 800.0
    codes = {(i["field"], i["code"]) for i in record["issues"]}
    assert {("exposure_s", "out_of_range"), ("gain", "out_of_range")} <= codes
    short = planner.post(
        "/api/transit/plan",
        json={"planet_name": "HD 189733 b", "exposure_s": 10.0, "cadence_s": 5.0},
        headers=AUTH,
    )
    assert short.status_code == 400
    assert short.json()["error"]["message"] == "cadence_s cannot be shorter than exposure_s"


def test_a_transit_plan_is_refused_while_a_run_is_active(planner, monkeypatch):
    force_run_active(monkeypatch, planner.hub)
    answer = planner.post("/api/transit/plan", json={"planet_name": "HD 189733 b"}, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "run_active"
    # Prediction stays available.
    predict = planner.post(
        "/api/transit/predict", json={"planet_name": "HD 189733 b"}, headers=AUTH
    )
    assert predict.status_code == 200


def test_the_batched_bjd_corrections_equal_the_core_s_scalar_ones():
    """Technical review: one astropy call per candidate stalled the event loop."""
    ra, dec = HD189733B.ra_degrees, HD189733B.dec_degrees
    site = (48.85, 2.35, 35.0)
    start = julian_date(datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc))
    mids = [start + 0.5 + k * HD189733B.period_days for k in range(0, 300, 7)]
    coarse = bjd_tdb(start, ra, dec, *site) - start
    batched = planning._corrections(mids, coarse, ra, dec, site)
    for mid, corr in zip(mids, batched):
        exact = bjd_tdb(mid - corr, ra, dec, *site)
        assert abs(exact - (mid - corr) - corr) * 86400.0 < 1e-3  # converged: < 1 ms
