"""Wave 5: live photometry (A50, A54-A58) and the wave 4 follow-ups.

PARITY. The server's live points are compared with the fixed Qt engine's
(``AcquisitionEngine``, driven offscreen in this process as
``tests/workers/test_acquisition_engine.py`` does): the same FITS files are
opened by both (Open FITS: epoch from the header), the same solution is applied
(the fake ASTAP's WCS keys, read by both through ``frame_wcs``), and each
measures one point per solution. Every ``LcPoint`` field, the CSVs byte for
byte and the leave-one-out report must be identical: **no tolerance**, the
same core functions run on the same inputs. Qt's series FWHM is fed from the
same ``detect_stars`` call its display pipeline makes; frames 0 and 1 are the
same image, so the Qt 0.5.0 freeze-order defect (S31: frame 2's FWHM) and the
fix (frame 1's) give the same series here; ``test_series_fwhm_*`` covers S31.

The synthetic frames are a rigid field drifting and rotating under a fixed
solution (so the tracker matters), a variable target, five comparisons with V
magnitudes, a check star, one frame with a saturated target and one with a hot
pixel on the check (suspect).
"""

from __future__ import annotations

import copy
import csv
import json
import math
import os
import statistics
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from argos.core.catalog.targets import TargetSet, TargetStar  # noqa: E402
from argos.core.imaging.metrics import detect_stars  # noqa: E402
from argos.core.imaging.platesolve import frame_wcs  # noqa: E402
from argos.core.photometry.aperture import measure_aperture  # noqa: E402
from argos.core.photometry.uncertainty import estimate_lightcurve_scatter  # noqa: E402
from argos.server.photometry import MeasureRequest, point_record  # noqa: E402
from tests.server.conftest import (  # noqa: E402
    AUTH,
    TOKEN,
    log_messages,
    receive_until,
    science_client,
    wait_for,
)
from tests.server.test_field import FakeAstap  # noqa: E402


def _core_has_s49() -> bool:
    """GUARD (pending merge of release/0.5.0): the Qt core keeps one curve per (star,
    filter) (S49: ``lightcurve.curve_key``). The Qt parity tests compare the server
    with that core; before the merge they skip, after it they run."""
    from argos.core.photometry import lightcurve

    return hasattr(lightcurve, "curve_key")


requires_s49_core = pytest.mark.skipif(
    not _core_has_s49(), reason="the core has no S49 yet (release/0.5.0 not merged)"
)


def core_has_s57() -> bool:
    """GUARD (pending merge of release/0.5.0): the Qt core writes the vetting file's
    ``filter`` key (S57: ``save_comparison_quality_report(..., filter_token=)``). Before
    the merge the Qt file has no such key; the server's always does."""
    import inspect

    from argos.core.photometry.quality import save_comparison_quality_report

    return "filter_token" in inspect.signature(save_comparison_quality_report).parameters


def core_has_s71() -> bool:
    """GUARD (pending merge of release/0.5.0): the core weighs each comparison by its
    error and returns the zero point's error (S71: ``DiffResult.zp_err``). Before the
    merge the zero point is the clipped plain mean."""
    from dataclasses import fields

    from argos.core.photometry.differential import DiffResult

    return "zp_err" in {f.name for f in fields(DiffResult)}


def _s71_zero_point(rows: list[tuple[float, float]]) -> tuple[float, float, float, int, int]:
    """S71 by hand: ``rows`` are ``(cat − inst, inst_mag_err)``; weights
    ``1/(err² + 0.01²)``, clip at 2.5 normalised residuals about the weighted median
    (≤ 2 passes, ≥ 3 rows, never below 2 kept) → ``(zp, rms, zp_err, n, clipped)``."""
    rows = [(d, math.hypot(e, 0.01)) for d, e in rows]
    clipped = 0
    for _ in range(2):
        if len(rows) < 3:
            break
        ordered = sorted(rows)
        weights = [1 / (s * s) for _d, s in ordered]
        acc, med = 0.0, ordered[-1][0]
        for i, w in enumerate(weights):
            acc += w
            if math.isclose(acc, sum(weights) / 2, rel_tol=1e-12) and i + 1 < len(ordered):
                med = (ordered[i][0] + ordered[i + 1][0]) / 2
                break
            if acc > sum(weights) / 2:
                med = ordered[i][0]
                break
        kept = [(d, s) for d, s in rows if abs(d - med) <= 2.5 * s]
        if len(kept) == len(rows) or len(kept) < 2:
            break
        clipped += len(rows) - len(kept)
        rows = kept
    w = [1 / (s * s) for _d, s in rows]
    n, total = len(rows), sum(w)
    zp = sum(wi * d for wi, (d, _s) in zip(w, rows)) / total
    var = sum(wi * (d - zp) ** 2 for wi, (d, _s) in zip(w, rows)) / total
    rms = math.sqrt(var * n / (n - 1)) if n > 1 else 0.0
    return zp, rms, max(math.sqrt(1 / total), rms / math.sqrt(n)), n, clipped


def _star(curves, star_key: str):
    """The one curve of a star (S49: keys are ``<star>@<filter>``)."""
    (curve,) = [c for c in curves if c["key"].rpartition("@")[0] == star_key]
    return curve


GH, GW = 160, 200  # green plane
SCALE = 7.35 / 3600.0  # deg per green px
CRVAL = (291.366, 42.784)
WCS_FIELDS = {
    "CRVAL1": CRVAL[0],
    "CRVAL2": CRVAL[1],
    "CRPIX1": GW / 2 + 0.5,
    "CRPIX2": GH / 2 + 0.5,
    "CD1_1": -SCALE,
    "CD1_2": 0.0,
    "CD2_1": 0.0,
    "CD2_2": SCALE,
}
GREEN_WCS = frame_wcs(WCS_FIELDS, (GH, GW))
OBJECT = "SYN Var"
SITE = {"name": "Test site", "latitude": 48.85, "longitude": 2.35, "elevation": 60.0}
EGAIN = 0.5
SIGMA = 1.1  # PSF sigma, green px
T0 = datetime(2026, 9, 25, 20, 0, 0, tzinfo=timezone.utc)

#: (key, role, green x, green y, V or None)
STARS = [
    ("T", "target", 100.0, 80.0, None),
    ("C1", "comparison", 42.0, 38.0, 10.0),
    ("C2", "comparison", 158.0, 40.0, 10.4),
    ("C3", "comparison", 40.0, 124.0, 10.8),
    ("C4", "comparison", 160.0, 122.0, 11.1),
    ("C5", "comparison", 100.0, 30.0, 10.2),
    ("K", "check", 100.0, 132.0, 10.6),
]


def sky(gx: float, gy: float) -> tuple[float, float]:
    ra, dec = GREEN_WCS.pixel_to_world_deg(gx, gy)
    return float(ra), float(dec)


def target_set(*, mags: bool = True) -> TargetSet:
    stars = []
    for key, role, gx, gy, v in STARS:
        ra, dec = sky(gx, gy)
        if role == "target":
            stars.append(TargetStar(role, ra, dec, name=OBJECT, source="vsx"))
        else:
            stars.append(
                TargetStar(
                    role,
                    ra,
                    dec,
                    auid=f"000-SYN-{key}",
                    name=key,
                    source="vsp",
                    mags={"V": v} if mags else {},
                    chart_id="X99",
                )
            )
    return TargetSet(object_name=OBJECT, stars=stars)


def target_v(i: int) -> float:
    return 10.5 + 0.3 * math.sin(i / 3.0)


def synthetic_raw(i: int, *, drift: bool = True, saturate: bool = False, hot: bool = False):
    """One raw frame (each green value repeated over its 2x2 tile)."""
    rng = np.random.default_rng(1000 + i)
    k = max(0, i - 1) if drift else 0  # frames 0 and 1 are the same image
    theta = math.radians(0.04 * k)
    dx, dy = 0.35 * k, -0.22 * k
    cx, cy = GW / 2.0, GH / 2.0
    yy, xx = np.mgrid[0:GH, 0:GW]
    green = np.full((GH, GW), 300.0)
    for key, _role, gx, gy, v in STARS:
        x = cx + math.cos(theta) * (gx - cx) - math.sin(theta) * (gy - cy) + dx
        y = cy + math.sin(theta) * (gx - cx) + math.cos(theta) * (gy - cy) + dy
        mag = target_v(i) if key == "T" else v
        flux = 10 ** (-0.4 * (mag - 21.0))
        if key == "T" and saturate:
            flux *= 40.0
        green += (
            flux
            / (2 * math.pi * SIGMA**2)
            * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * SIGMA**2))
        )
        if key == "K" and hot:
            green[int(round(y)), int(round(x)) + 1] = 30000.0
    green += rng.normal(0.0, 6.0, green.shape)
    green = np.clip(green, 0, 65535)
    return np.kron(green, np.ones((2, 2))).astype(np.uint16)


def write_frame(path: Path, raw: np.ndarray, i: int) -> Path:
    from astropy.io import fits

    hdu = fits.PrimaryHDU(data=raw)
    start = T0 + timedelta(seconds=30 * i)
    hdu.header["DATE-OBS"] = start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    hdu.header["EXPTIME"] = 10.0
    hdu.header["IMAGETYP"] = "Light Frame"
    hdu.header["OBJECT"] = OBJECT
    hdu.writeto(path)
    return path


def frames(folder: Path, n: int = 14) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(n):
        raw = synthetic_raw(i, saturate=(i == 6), hot=(i == 9))
        out.append(write_frame(folder / f"syn_{i:03d}.fit", raw, i))
    return out


class EmptyCatalog:
    """No network: every catalogue query answers nothing (the set is given)."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: []


# -- the two paths -----------------------------------------------------------------


def _star_radius_fwhm(path: Path) -> float | None:
    from argos.server.fits_source import load_raw_fits_frame

    return detect_stars(load_raw_fits_frame(path).pixels, radius=5).mean_fwhm


def run_qt(tmp_path: Path, paths: list[Path], tset: TargetSet) -> dict:
    """The fixed Qt engine on the same files: Open FITS, the solution, one point each."""
    qtwidgets = pytest.importorskip("PyQt6.QtWidgets")
    qtwidgets.QApplication.instance() or qtwidgets.QApplication([])
    from argos.core.config import _DEFAULTS, Config
    from argos.core.session.acquisition_engine import AcquisitionEngine
    from argos.core.session.device_session import DeviceSession
    from argos.ui.widgets.camera_dock import CaptureParams

    sessions = tmp_path / "qt-sessions"
    data = copy.deepcopy(dict(_DEFAULTS))
    data["sessions_path"] = str(sessions)
    data["site"] = dict(SITE)
    data["camera"] = {**data.get("camera", {}), "egain_table": {"80": EGAIN}}
    cfg = Config(data)
    engine = AcquisitionEngine(cfg, DeviceSession(cfg))
    engine.set_providers(lambda: CaptureParams("Light Frame", OBJECT, "IR", 10.0, 80), lambda: 1)
    tset.save(sessions / "targets" / "SYN_Var.json")
    reports = []
    engine.comparison_quality_updated.connect(reports.append)
    for path in paths:
        engine.open_fits_frame(path)
        engine._last_fwhm = _star_radius_fwhm(path)  # on_processed: pf.stars.mean_fwhm
        engine.astrometry._wcs = frame_wcs(WCS_FIELDS, (GH, GW))
        engine._on_reference_solved(None, None, "")
        engine.measure_photometry_if_idle()
    return {"curves": engine.lightcurves, "report": reports[-1], "sessions": sessions}


@pytest.fixture
def phot_client(make_client, tmp_path):
    client = science_client(make_client, tmp_path)
    astap = FakeAstap(tmp_path / "astap")
    astap.set("solve", wcs=WCS_FIELDS)
    db = tmp_path / "astap-db"
    db.mkdir()
    response = client.patch(
        "/api/config",
        json={
            "astrometry.astap_path": str(astap.path),
            "astrometry.database": "D50",
            "astrometry.database_path": str(db),
            "site.name": SITE["name"],
            "site.latitude": SITE["latitude"],
            "site.longitude": SITE["longitude"],
            "site.elevation": SITE["elevation"],
            "camera.egain_table": {"80": EGAIN},
            "catalog.show_cached_exoplanets": False,
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    hub = client.app.state.hub
    hub.field.catalog_api = EmptyCatalog()
    hub.field.identify_point = lambda *args, **kwargs: None
    client.hub = hub  # type: ignore[attr-defined]
    client.astap = astap  # type: ignore[attr-defined]
    return client


def settle(client, timeout: float = 15.0) -> None:
    hub = client.hub
    wait_for(lambda: hub.field.idle() and hub.photometry.idle(), timeout=timeout)


def set_object(client, name: str = OBJECT) -> None:
    response = client.put("/api/observation", json={"object_name": name}, headers=AUTH)
    assert response.status_code == 200, response.text


def open_and_solve(client, path: Path) -> None:
    response = client.post("/api/camera/open-fits", json={"path": str(path)}, headers=AUTH)
    assert response.status_code == 200, response.text
    settle(client)
    started = client.post("/api/field/solve", headers=AUTH)
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]
    wait_for(
        lambda: client.get(f"/api/jobs/{job_id}", headers=AUTH).json()["state"]
        in ("done", "failed", "cancelled"),
        timeout=15.0,
    )
    assert client.get(f"/api/jobs/{job_id}", headers=AUTH).json()["state"] == "done"
    settle(client)


def run_server(client, paths: list[Path], tset: TargetSet) -> dict:
    tset.save(client.sessions_path / "targets" / "SYN_Var.json")
    set_object(client)
    for path in paths:
        open_and_solve(client, path)
    return client.get("/api/photometry/live", headers=AUTH).json()


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return a == b or (math.isnan(a) and math.isnan(b))
    return a == b


# -- PARITY --------------------------------------------------------------------------


@requires_s49_core
def test_live_points_csvs_and_report_are_identical_to_the_qt_engine(
    phot_client, tmp_path, monkeypatch
):
    # The Qt engine's module imports PyQt6 (the monkeypatch below loads it): a Qt-free
    # install (the desktop app's, W8) skips this parity test.
    pytest.importorskip("PyQt6")
    # Outside a run each curve's CSV is named after its start (S40): one clock for both.
    start = lambda: datetime(2026, 11, 9, 20, 15, tzinfo=timezone.utc)  # noqa: E731
    monkeypatch.setattr("argos.core.session.acquisition_engine._utcnow", start)
    monkeypatch.setattr("argos.server.photometry._utcnow", start)
    paths = frames(tmp_path / "frames")
    qt = run_qt(tmp_path, paths, target_set())
    live = run_server(phot_client, paths, target_set())

    assert [c["key"] for c in live["curves"]] == list(qt["curves"])  # Qt's dict order
    roles = {c["key"]: c["role"] for c in live["curves"]}
    assert sorted(roles.values()).count("comparison") == 5
    # S49: the opened frames have no FILTER card: one curve per star, filter "clear".
    assert roles[f"{OBJECT}@clear"] == "target" and roles["000-SYN-K@clear"] == "check"
    compared = 0
    for curve in live["curves"]:
        reference = qt["curves"][curve["key"]]
        assert curve["role"] == reference.role and curve["name"] == reference.name
        assert len(curve["points"]) == len(reference.points) > 0
        for wire, point in zip(curve["points"], reference.points):
            # The zero point is the server's addition (checked by hand below).
            expected = point_record(
                point, wire["frame_seq"], wire["t"], wire["zero_point"], wire["zp_rms"]
            )
            assert wire == expected, (curve["key"], wire, expected)
            compared += 1
    assert compared >= 7 * 13

    # Every point of every frame; the flags of frames 6 (saturated target) and 9
    # (hot pixel on the check) are in both.
    target = next(c for c in live["curves"] if c["role"] == "target")["points"]
    check = next(c for c in live["curves"] if c["role"] == "check")["points"]
    assert len(target) == len(check) == 14
    assert target[6]["saturated"] and not any(p["saturated"] for p in check)
    assert check[9]["suspect"]
    assert all(p["bjd_tdb"] is not None and p["airmass"] is not None for p in target)
    assert target[-1]["sigma_syst"] is not None  # the run-level floor applied

    # CSVs: the same files, byte for byte (outside a run: <sessions>/targets).
    qt_csvs = sorted((qt["sessions"] / "targets").glob("*.csv"))
    web_csvs = sorted((phot_client.sessions_path / "targets").glob("*.csv"))
    assert [p.name for p in web_csvs] == [p.name for p in qt_csvs] and len(qt_csvs) == 7
    assert all(p.name.startswith("SYN_Var_20261109T201500Z_") for p in web_csvs)
    for ours, theirs in zip(web_csvs, qt_csvs):
        assert ours.read_bytes() == theirs.read_bytes(), ours.name
    assert {c["csv"] for c in live["curves"]} == {str(p) for p in web_csvs}

    # The leave-one-out report (S17), minus its time stamp and the wire's additions.
    ours = dict(live["quality"])
    theirs = dict(qt["report"])
    ours.pop("generated_utc"), theirs.pop("generated_utc")
    entries = [
        {k: v for k, v in e.items() if k not in ("key", "star_key", "last")}
        for e in ours.pop("comparison_stars")
    ]
    assert entries == theirs.pop("comparison_stars")
    assert ours == theirs


def test_series_fwhm_is_frozen_on_the_first_measured_frame(phot_client, tmp_path):
    """S31: Qt 0.5.0 read the FWHM before _diagnostics reset it for a new object,
    so its first point had its own aperture and the series used frame 2's."""
    folder = tmp_path / "fwhm"
    folder.mkdir()
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    for i, fwhm in enumerate((2.0, 3.0, 2.5)):
        hub.photometry.measure(
            MeasureRequest(
                frame_seq=100 + i,
                raw=synthetic_raw(i + 2),
                wcs=GREEN_WCS,
                epoch=T0 + timedelta(minutes=i),
                generation=1,
                fwhm=fwhm,
            )
        )
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    target = next(c for c in live["curves"] if c["role"] == "target")
    assert [p["fwhm"] for p in target["points"]] == [2.0, 2.0, 2.0]
    assert live["geometry"]["series_fwhm_px"] == 2.0
    # A frame without a measurable FWHM uses 3.0 px and leaves the series unfrozen.
    set_object(phot_client, "Other")
    TargetSet("Other", tset.stars).save(phot_client.sessions_path / "targets" / "Other.json")
    hub.targets.reload()
    for i, fwhm in enumerate((None, 2.2, 2.6)):
        hub.photometry.measure(
            MeasureRequest(
                frame_seq=200 + i,
                raw=synthetic_raw(i + 2),
                wcs=GREEN_WCS,
                epoch=T0 + timedelta(minutes=10 + i),
                generation=1,
                fwhm=fwhm if fwhm is not None else 0.0,
            )
        )
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    target = next(c for c in live["curves"] if c["role"] == "target")
    assert [p["fwhm"] for p in target["points"]] == [3.0, 2.2, 2.2]


# -- events, snapshot, status --------------------------------------------------------


def test_points_stream_on_the_socket_with_seq_bjd_and_the_floor(phot_client, tmp_path):
    paths = frames(tmp_path / "frames", n=11)
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    with phot_client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        receive_until(ws, lambda m: m["type"] == "photometry")
        seen: list[dict] = []
        for path in paths:
            open_and_solve(phot_client, path)
        live = phot_client.get("/api/photometry/live", headers=AUTH).json()
        receive_until(
            ws,
            lambda m: m["type"] == "photometry" and m["points"] == 7 * 11,
            timeout=10.0,
            seen=seen,
        )
    points = [m for m in seen if m["type"] == "photometry_point"]
    assert [m["seq"] for m in points] == list(range(points[0]["seq"], live["seq"] + 1))
    assert len(points) == 7 * 11
    floor = [m for m in points if m["sigma_syst"] is not None]
    assert floor and all(m["index"] >= 9 for m in floor)  # the floor from the 10th point
    assert all("mag_errs" not in m for m in points)  # never the whole column again
    curves = {c["key"]: c for c in live["curves"]}
    for m in points:
        point = curves[m["key"]]["points"][m["index"]]
        assert m["point"]["jd_utc"] == point["jd_utc"] and m["point"]["mag"] == point["mag"]
        assert m["point"]["bjd_tdb"] is not None and m["frame_seq"] == point["frame_seq"]
    # Every earlier bar is hypot(formal, sigma_syst): what the client recomputes.
    for key in curves:
        last = [m for m in points if m["key"] == key][-1]
        assert last["sigma_syst"] is not None
        for p in curves[key]["points"]:
            final = math.hypot(max(0.0, p["formal_mag_err"]), last["sigma_syst"])
            assert p["mag_err"] == final, (key, p)
    statuses = [m for m in seen if m["type"] == "photometry"]
    assert statuses[-1]["state"] == "measured" and statuses[-1]["points"] == 7 * 11
    assert statuses[-1]["last"]["target"]["key"] == f"{OBJECT}@clear"  # S49
    quality = [m for m in seen if m["type"] == "comparison_quality"]
    assert quality[-1]["filter"] == "clear"  # the filter it vets (S49)
    assert quality[-1]["report"]["comparison_stars"][0]["key"] == "000-SYN-C1@clear"
    # A client that joins now gets the status, the report and the newest metrics.
    with phot_client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        first = []
        receive_until(ws, lambda m: m["type"] == "frame_metrics", seen=first)
        kinds = [m["type"] for m in first]
        assert "photometry" in kinds and "comparison_quality" in kinds


def test_bjd_tdb_and_airmass_follow_the_site_rule(phot_client, tmp_path):
    """BJD_TDB against an independent astropy computation; X2 without a site."""
    import astropy.units as u
    from astropy.coordinates import EarthLocation, SkyCoord
    from astropy.time import Time

    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    epoch = T0 + timedelta(seconds=5)
    request = MeasureRequest(1, synthetic_raw(0), GREEN_WCS, epoch, 1, fwhm=2.4)
    hub.photometry.measure(request)
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    target = next(c for c in live["curves"] if c["role"] == "target")
    point = target["points"][0]
    ra, dec = sky(100.0, 80.0)
    when = Time(
        epoch,
        scale="utc",
        location=EarthLocation.from_geodetic(
            SITE["longitude"] * u.deg, SITE["latitude"] * u.deg, SITE["elevation"] * u.m
        ),
    )
    ltt = when.light_travel_time(SkyCoord(ra * u.deg, dec * u.deg), kind="barycentric")
    expected = (when.tdb + ltt).jd
    assert point["jd_utc"] == pytest.approx(when.jd, abs=1e-9)
    assert abs(point["bjd_tdb"] - expected) * 86400.0 < 1e-3  # under a millisecond
    assert point["t"] == "2026-09-25T20:00:05.000Z"
    assert 1.0 < point["airmass"] < 3.0

    # X2: no site → no BJD_TDB, and the mount's airmass (none without a mount).
    phot_client.patch(
        "/api/config",
        json={"site.name": "", "site.latitude": 0.0, "site.longitude": 0.0},
        headers=AUTH,
    )
    hub.photometry.measure(MeasureRequest(2, synthetic_raw(1), GREEN_WCS, epoch, 1, fwhm=2.4))
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    target = next(c for c in live["curves"] if c["role"] == "target")
    assert target["points"][1]["bjd_tdb"] is None and target["points"][1]["airmass"] is None
    assert live["site_set"] is False


def test_leave_one_out_matches_a_hand_computation(phot_client):
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    n = 12
    for i in range(n):
        hub.photometry.measure(
            MeasureRequest(
                i + 1,
                synthetic_raw(i, drift=False),
                GREEN_WCS,
                T0 + timedelta(minutes=i),
                1,
                fwhm=2.4,
            )
        )
        if i == 0:
            transform = hub.photometry._tracker.transform  # frame 0's fit
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    curves = {c["key"]: c for c in live["curves"]}
    curves.update({k.rpartition("@")[0]: c for k, c in curves.items()})  # by star (S49)
    params = hub.targets.params(EGAIN)
    r_ap = params.aperture_px(2.4)
    r_in = max(params.annulus_in_px, r_ap + 1.0)
    r_out = max(params.annulus_out_px, r_in + 2.0)
    comps = [s for s in tset.stars if s.role == "comparison"]
    # Frame 0 by hand: instrumental mags at the tracked positions.
    green = synthetic_raw(0, drift=False)[0::2, 0::2].astype(np.float32)
    inst = {}
    for star in comps:
        x, y = transform.apply(*map(float, GREEN_WCS.world_to_pixel_deg(star.ra_deg, star.dec_deg)))
        phot = measure_aperture(
            green,
            float(x),
            float(y),
            r_ap,
            r_in,
            r_out,
            egain=EGAIN,
            read_noise_e=params.read_noise_e,
            sat_adu=params.sat_adu,
            **(
                {"black_adu": params.black_adu, "plane_pixels": params.plane_pixels}
                if hasattr(params, "plane_pixels")  # GUARD: S72's core
                else {}
            ),
        )
        inst[star.auid] = (phot.inst_mag, phot.inst_mag_err)
    clipped = 0
    for star in comps:
        if core_has_s71():  # GUARD: the merged core's weighted zero point (S71)
            zp, rms, zp_err, n_used, n_clipped = _s71_zero_point(
                [(s.mags["V"] - inst[s.auid][0], inst[s.auid][1]) for s in comps if s is not star]
            )
            clipped += n_clipped
            point = curves[star.auid]["points"][0]
            assert point["mag"] == round(inst[star.auid][0] + zp, 4), star.auid
            assert point["formal_mag_err"] == round(math.hypot(inst[star.auid][1], zp_err), 4)
            assert point["zero_point"] == round(zp, 4) and point["zp_rms"] == round(rms, 4)
            assert point["comps_used"] == n_used
            continue
        # Leave-one-out: the ensemble minus this star; ZP = mean(V - inst) after the
        # median / MAD clip (max(2.5 x 1.4826 x MAD, 0.01 mag), at most 2 passes, >= 3).
        diffs = [s.mags["V"] - inst[s.auid][0] for s in comps if s is not star]
        for _ in range(2):
            if len(diffs) < 3:
                break
            med = statistics.median(diffs)
            mad = statistics.median(abs(d - med) for d in diffs)
            kept = [d for d in diffs if abs(d - med) <= max(2.5 * 1.4826 * mad, 0.01)]
            if len(kept) == len(diffs) or len(kept) < 2:
                break
            clipped += len(diffs) - len(kept)
            diffs = kept
        zp = sum(diffs) / len(diffs)
        rms = math.sqrt(sum((d - zp) ** 2 for d in diffs) / (len(diffs) - 1))
        mag = round(inst[star.auid][0] + zp, 4)
        formal = round(math.hypot(inst[star.auid][1], rms / math.sqrt(len(diffs))), 4)
        point = curves[star.auid]["points"][0]
        assert point["mag"] == mag and point["formal_mag_err"] == formal, star.auid
        assert point["zero_point"] == round(zp, 4) and point["zp_rms"] == round(rms, 4)
        assert point["comps_used"] == len(diffs)
    # The old rule's clip is exercised on this frame; S71's normalised clip keeps every
    # comparison here (its clip is the core's test_reddish_comparison_still_clipped_s71).
    assert clipped or core_has_s71()
    # The report's status per comparison, by hand (quality.py:22-98 rules).
    report = live["quality"]
    for entry in report["comparison_stars"]:
        pts = curves[entry["key"]]["points"]
        scatter = estimate_lightcurve_scatter((p["jd_utc"], p["mag"]) for p in pts)
        formal = sorted(p["formal_mag_err"] for p in pts)
        median = (formal[n // 2 - 1] + formal[n // 2]) / 2
        status = "noisy" if median > 0.10 else "unstable" if scatter > 0.10 else "stable"
        assert entry["n_valid"] == n and entry["status"] == status
        assert entry["scatter_mag"] == round(scatter, 5)
        assert entry["last"]["mag"] == pts[-1]["mag"]
    assert report["selection_status"] == "live_preview_consistent"


def test_ratio_only_points_without_catalogue_magnitudes(phot_client):
    """S18: comparisons without a catalogue magnitude still give the flux ratio."""
    target_set(mags=False).save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    kept = hub.photometry.measure(MeasureRequest(1, synthetic_raw(0), GREEN_WCS, T0, 1, fwhm=2.4))
    assert kept == 7
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    target = next(c for c in live["curves"] if c["role"] == "target")["points"][0]
    assert target["mag"] is None and target["mag_err"] is None
    assert target["relative_flux"] > 0 and target["relative_comps_used"] == 5
    rows = list(csv.DictReader(open(live["curves"][0]["csv"], encoding="utf-8")))
    assert rows[0]["mag"] == "nan"


def test_status_says_why_nothing_is_measured(phot_client, tmp_path):
    hub = phot_client.hub
    set_object(phot_client)
    status = phot_client.get("/api/photometry/live", headers=AUTH).json()["status"]
    assert status["state"] == "off" and status["reason"] == "no_target"
    target_set().save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    hub.targets.reload()
    status = phot_client.get("/api/photometry/live", headers=AUTH).json()["status"]
    assert status["state"] == "waiting" and status["reason"] == "not_solved"
    # An opened file without a date: no point, the Qt warning.
    path = tmp_path / "undated.fit"
    from astropy.io import fits

    fits.PrimaryHDU(data=synthetic_raw(0)).writeto(path)
    open_and_solve(phot_client, path)
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert live["curves"] == []
    assert live["status"]["state"] == "skipped" and live["status"]["reason"] == "no_epoch"
    assert "Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME)." in log_messages(
        phot_client
    )


def test_an_object_change_resets_the_curves(phot_client, tmp_path):
    target_set().save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    hub.photometry.measure(MeasureRequest(1, synthetic_raw(0), GREEN_WCS, T0, 1, fwhm=2.4))
    before = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert before["curves"]
    with phot_client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        set_object(phot_client, "Another star")
        reset = receive_until(ws, lambda m: m["type"] == "photometry_reset")
    assert reset["reason"] == "object_changed" and reset["revision"] == before["revision"] + 1
    after = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert after["curves"] == [] and after["quality"] is None
    assert after["object_name"] == "Another star" and after["seq"] == reset["seq"]
    assert Path(before["curves"][0]["csv"]).exists()  # the CSVs stay on disk


# -- A50, A58, wave 4 follow-ups (with the fake catalogue of test_field) --------------


def _solved_field_client(make_client, tmp_path):
    from tests.server.test_field import FakeCatalog

    client = science_client(make_client, tmp_path, connect=("mount", "camera"))
    astap = FakeAstap(tmp_path / "astap")
    db = tmp_path / "astap-db"
    db.mkdir()
    client.patch(
        "/api/config",
        json={
            "astrometry.astap_path": str(astap.path),
            "astrometry.database": "D50",
            "astrometry.database_path": str(db),
            "astrometry.live_resolve_s": 3600,
            "catalog.show_cached_exoplanets": False,
        },
        headers=AUTH,
    )
    hub = client.app.state.hub
    hub.field.catalog_api = FakeCatalog()
    hub.field.identify_point = lambda *args, **kwargs: None
    client.hub = hub  # type: ignore[attr-defined]
    return client


def _solve_sim(client) -> None:
    from tests.server.test_field import settle as field_settle
    from tests.server.test_field import solve, take_frame

    take_frame(client)
    solve(client)
    field_settle(client)
    wait_for(lambda: client.get("/api/field/catalog", headers=AUTH).json()["state"] == "ready")
    field_settle(client)
    wait_for(client.hub.photometry.idle)


def test_field_variables_list(make_client, tmp_path):
    client = _solved_field_client(make_client, tmp_path)
    assert client.get("/api/field/variables", headers=AUTH).json() == {
        "available": False,
        "generation": 0,
        "rows": [],
    }
    _solve_sim(client)
    body = client.get("/api/field/variables", headers=AUTH).json()
    assert body["available"] is True
    (row,) = body["rows"]
    assert row["index"] == 0 and row["name"] == "RR Lyr" and row["var_type"] == "RRAB"
    assert row["mag_text"] == "7.06 V – 8.12 V" and row["period_d"] == 0.567
    assert row["in_set_role"] is None and row["suspected"] is False
    assert row["sep_arcmin"] == pytest.approx(0.0, abs=0.2)
    response = client.post(
        "/api/targets", json={"role": "target", "variable_index": 0}, headers=AUTH
    )
    assert response.status_code == 200
    wait_for(
        lambda: client.get("/api/field/variables", headers=AUTH).json()["rows"][0]["in_set_role"]
        == "target"
    )


def test_undo_of_a_new_target_also_removes_its_automatic_comparisons(make_client, tmp_path):
    client = _solved_field_client(make_client, tmp_path)
    _solve_sim(client)
    answer = client.post(
        "/api/targets", json={"role": "target", "variable_index": 0}, headers=AUTH
    ).json()
    auto = answer["auto_selected"]
    assert auto and all(k.startswith("auid:000-AAA-") for k in auto)
    target_key = next(s["key"] for s in answer["stars"] if s["role"] == "target")
    also = ",".join(auto)
    undone = client.delete(f"/api/targets/{target_key}?also={also}", headers=AUTH).json()
    assert undone["stars"] == [] and undone["removed"]["key"] == target_key
    assert sorted(s["key"] for s in undone["removed_also"]) == sorted(auto)
    saved = json.loads(Path(undone["path"]).read_text())
    assert saved["stars"] == []
    assert any(m.endswith("(and 2 automatic comparison(s))") for m in log_messages(client))
    # A star the observer changed since (no longer vsp_auto) stays.
    answer = client.post(
        "/api/targets", json={"role": "target", "variable_index": 0}, headers=AUTH
    ).json()
    kept = next(s for s in answer["stars"] if s["key"] == answer["auto_selected"][0])
    pending = {k: kept[k] for k in ("ra_deg", "dec_deg", "auid", "name", "mags", "chart_id")}
    changed = client.post(
        "/api/targets", json={"role": "check", "star": {**pending, "source": "vsp"}}, headers=AUTH
    )
    assert changed.status_code == 200, changed.text
    target_key = next(s["key"] for s in answer["stars"] if s["role"] == "target")
    undone = client.delete(
        f"/api/targets/{target_key}?also={','.join(answer['auto_selected'])}", headers=AUTH
    ).json()
    assert [s["key"] for s in undone["stars"]] == [kept["key"]]


def test_recommend_comparisons(make_client, tmp_path):
    client = _solved_field_client(make_client, tmp_path)
    refused = client.post(
        "/api/photometry/comparisons/recommend", json={"mode": "replace"}, headers=AUTH
    )
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "not_solved"
    _solve_sim(client)
    no_target = client.post(
        "/api/photometry/comparisons/recommend", json={"mode": "replace"}, headers=AUTH
    )
    assert no_target.status_code == 409 and no_target.json()["error"]["code"] == "no_target"
    client.post("/api/targets", json={"role": "target", "variable_index": 0}, headers=AUTH)
    body = client.post(
        "/api/photometry/comparisons/recommend", json={"mode": "replace"}, headers=AUTH
    ).json()
    assert body["added"] == 2 and len(body["comparisons"]) == 2
    assert body["removed"] == []  # the same two stars were chosen again
    assert "Photometry: replaced the VSP ensemble with 2 pilot-qualified star(s)." in (
        log_messages(client)
    )
    complete = client.post(
        "/api/photometry/comparisons/recommend",
        json={"mode": "complete", "count": 1},
        headers=AUTH,
    ).json()
    assert complete["added"] == 0
    assert (
        client.get("/api/config", headers=AUTH).json()["values"]["photometry.auto_comparisons"] == 1
    )
    bad = client.post("/api/photometry/comparisons/recommend", json={"mode": "all"}, headers=AUTH)
    assert bad.status_code == 400
    # No VSP stars known (Qt removed the ensemble and added nothing, S32): 409, unchanged.
    client.hub.field._catalog_result.comparisons.clear()
    before = client.get("/api/targets", headers=AUTH).json()["stars"]
    empty = client.post(
        "/api/photometry/comparisons/recommend", json={"mode": "replace"}, headers=AUTH
    )
    assert empty.status_code == 409 and empty.json()["error"]["code"] == "no_comparison"
    assert client.get("/api/targets", headers=AUTH).json()["stars"] == before


def test_a_solution_measures_one_point_through_the_whole_path(make_client, tmp_path):
    """Live view + Identify field: the point lands in A54 and its CSV (Qt's rule)."""
    client = _solved_field_client(make_client, tmp_path)
    _solve_sim(client)
    client.post("/api/targets", json={"role": "target", "variable_index": 0}, headers=AUTH)
    from tests.server.test_field import solve, take_frame

    take_frame(client)
    solve(client)
    wait_for(client.hub.photometry.idle)
    live = client.get("/api/photometry/live", headers=AUTH).json()
    assert live["status"]["frames"] == 1
    assert live["status"]["last"]["frame_seq"] == client.hub.field._frame.seq
    assert live["status"]["last"]["anchors"] is not None


def test_a_run_sub_solved_after_the_run_ended_is_not_measured_again(phot_client):
    """Wave 6b integration: a run's last sub whose solve ends after "Run ended" (the
    camera has no owner by then) gets no second point from the live path: the sequence
    measured it (one curve per star and filter, S49, not a one-point curve under no
    filter). A live frame's solution still measures it once."""
    hub = phot_client.hub
    submitted: list = []
    hub.photometry.submit = submitted.append  # type: ignore[method-assign]
    with hub._lock:
        assert hub._camera_state.owner not in ("sequence", "autofocus")
    sub = MeasureRequest(31, synthetic_raw(0), GREEN_WCS, T0, 1, origin="sequence")
    hub.photometry.on_solved(sub)
    assert submitted == []
    live = MeasureRequest(32, synthetic_raw(1), GREEN_WCS, T0, 2, origin="camera")
    hub.photometry.on_solved(live)
    assert [(r.frame_seq, r.reset_tracker) for r in submitted] == [(32, True)]


def test_a_role_change_starts_a_new_curve(phot_client):
    """S33: Qt appended a check star's points to its leave-one-out comparison curve."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    hub.photometry.measure(MeasureRequest(1, synthetic_raw(0), GREEN_WCS, T0, 1, fwhm=2.4))
    check = next(s for s in tset.stars if s.role == "check")
    pending = {
        "ra_deg": check.ra_deg,
        "dec_deg": check.dec_deg,
        "auid": check.auid,
        "name": check.name,
        "source": "vsp",
        "mags": check.mags,
    }
    with phot_client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        answer = phot_client.post(
            "/api/targets", json={"role": "comparison", "star": pending}, headers=AUTH
        )
        assert answer.status_code == 200, answer.text
        later = T0 + timedelta(minutes=1)
        hub.photometry.measure(MeasureRequest(2, synthetic_raw(1), GREEN_WCS, later, 1, fwhm=2.4))
        reset = receive_until(ws, lambda m: m["type"] == "photometry_reset")
    assert reset["reason"] == "role_changed"
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    curve = _star(live["curves"], check.auid)
    assert curve["role"] == "comparison" and len(curve["points"]) == 1
    rows = list(csv.DictReader(open(curve["csv"], encoding="utf-8")))
    assert len(rows) == 1  # outside a run the file is rewritten from the new curve


def test_also_keys_accept_repeats_and_position_keys():
    from argos.server.app import _target_keys

    assert _target_keys(["auid:A,pos:1.00000,+2.00000", "auid:B"]) == [
        "auid:A",
        "pos:1.00000,+2.00000",
        "auid:B",
    ]
    assert _target_keys([]) == [] and _target_keys([" , "]) == []


def test_an_opened_frame_never_takes_the_mount_airmass(make_client, tmp_path):
    """S34: without a site, a camera frame's airmass is the mount's (X2); an opened
    file (another night) has none (Qt gave it the mount's current altitude)."""
    client = science_client(make_client, tmp_path, connect=("mount",))
    for path, body in (("/api/mount/unpark", None), ("/api/mount/tracking", {"enabled": True})):
        assert client.post(path, json=body, headers=AUTH).status_code == 200
    target_set().save(client.sessions_path / "targets" / "SYN_Var.json")
    set_object(client)
    hub = client.app.state.hub
    wait_for(lambda: hub._pointing() is not None and hub._pointing().alt_deg is not None)
    raw = synthetic_raw(0)
    for seq, origin in ((1, "file"), (2, "live")):  # one filter: one curve (S49)
        request = MeasureRequest(seq, raw, GREEN_WCS, T0, 1, fwhm=2.4, origin=origin)
        hub.photometry.measure(replace(request, filter_name="IR"))
    live = client.get("/api/photometry/live", headers=AUTH).json()
    target = next(c for c in live["curves"] if c["role"] == "target")["points"]
    assert target[0]["airmass"] is None
    assert target[1]["airmass"] is not None and target[1]["bjd_tdb"] is None


def test_a_field_that_moved_since_the_solve_gets_no_point(phot_client, monkeypatch):
    """Release S35: with no anchor where the solution places the stars (the field
    moved more than the 15 px search radius since the solve), core's fallback
    took every star of the set unseen and noise centroids for anchors: a point
    measured on blank sky, unflagged, with no warning."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    monkeypatch.setattr(type(hub.field), "solved", property(lambda self: True))
    raw = synthetic_raw(0, drift=False)
    moved = np.roll(raw, 60, axis=1)  # 30 green px
    assert hub.photometry.measure(MeasureRequest(1, raw, GREEN_WCS, T0, 1, fwhm=2.4)) == 7
    later = T0 + timedelta(minutes=1)
    lost = MeasureRequest(2, moved, GREEN_WCS, later, 1, fwhm=2.4, reset_tracker=True)
    assert hub.photometry.measure(lost) == 0  # a point on blank sky before the fix
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert all(len(c["points"]) == 1 for c in live["curves"])
    assert live["status"]["state"] == "skipped" and live["status"]["reason"] == "field_lost"
    assert "field moved since the solve" in live["status"]["message"]
    assert any("Photometry skipped: no star of the set" in m for m in log_messages(phot_client))
    # Back on the solved field without a new solution: the tracker finds its stars.
    back = MeasureRequest(3, raw, GREEN_WCS, later + timedelta(minutes=1), 1, fwhm=2.4)
    assert hub.photometry.measure(back) == 7


def test_live_star_key_is_null_once_the_star_left_the_set(phot_client, monkeypatch):
    """A54: a curve whose star was removed from the set says so (star_key null)."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    monkeypatch.setattr(type(hub.field), "solved", property(lambda self: True))
    hub.photometry.measure(MeasureRequest(1, synthetic_raw(0), GREEN_WCS, T0, 1, fwhm=2.4))
    status = phot_client.get("/api/photometry/live", headers=AUTH).json()["status"]
    assert status["state"] == "measured"
    check = next(s for s in tset.stars if s.role == "check")
    assert phot_client.delete(f"/api/targets/{check.key()}", headers=AUTH).status_code == 200
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    curve = _star(live["curves"], check.auid)
    assert curve["star_key"] is None  # its old key before the fix
    others = [c for c in live["curves"] if c is not curve]
    assert all(c["star_key"] is not None for c in others)
    # The status no longer reports the previous set's measurement.
    assert live["status"]["state"] == "waiting"  # "measured" before the fix


def test_recommend_keeps_the_ensemble_when_no_vsp_star_passes_the_gate(
    make_client, tmp_path, monkeypatch
):
    """Release S32 (extended): VSP stars exist but none passes the pilot gate
    (on the RR Lyr field all six are 27-59' away); replace removed the ensemble
    and saved it empty."""
    import argos.server.targets as targets_module

    client = _solved_field_client(make_client, tmp_path)
    _solve_sim(client)
    client.post("/api/targets", json={"role": "target", "variable_index": 0}, headers=AUTH)
    before = client.get("/api/targets", headers=AUTH).json()
    assert len([s for s in before["stars"] if s["role"] == "comparison"]) == 2
    saved = Path(before["path"]).read_bytes()
    monkeypatch.setattr(targets_module, "auto_comparison_stars", lambda *a, **k: [])
    body = client.post(
        "/api/photometry/comparisons/recommend", json={"mode": "replace"}, headers=AUTH
    )
    assert body.status_code == 200, body.text
    body = body.json()
    assert body["added"] == 0 and body["removed"] == []  # removed 2, set emptied before
    assert client.get("/api/targets", headers=AUTH).json()["stars"] == before["stars"]
    assert Path(before["path"]).read_bytes() == saved
    assert "Photometry: no pilot-qualified comparison found — the ensemble is unchanged." in (
        log_messages(client)
    )


def test_identifying_the_field_keeps_the_check_star(make_client, tmp_path, monkeypatch):
    """Release S46 (parity): the VSP proposal carries the check star too, and
    set_role() replaced the check (same AUID) with a comparison."""
    import argos.server.targets as targets_module

    hub = science_client(make_client, tmp_path, connect=()).app.state.hub
    target = TargetStar(role="target", ra_deg=10.0, dec_deg=20.0, auid="000-VAR-000")
    check = TargetStar(role="check", ra_deg=10.1, dec_deg=20.0, auid="000-CHK-001")
    tset = TargetSet(object_name="V1", stars=[target, check])
    proposal = [TargetStar(role="comparison", ra_deg=10.1, dec_deg=20.0, auid="000-CHK-001")]
    proposal += [
        TargetStar(role="comparison", ra_deg=10.0 + k / 50, dec_deg=20.1, auid=f"000-CMP-{k}")
        for k in range(1, 6)
    ]
    monkeypatch.setattr(
        targets_module, "auto_comparison_stars", lambda *a, count, **k: proposal[:count]
    )
    monkeypatch.setattr(hub.field, "comparisons", lambda: [object()])
    monkeypatch.setattr(hub.field, "pilot", lambda: None)
    monkeypatch.setattr(hub.targets, "_pilot_quality", lambda *a: (None, None))
    real_get = hub.config.get
    monkeypatch.setattr(
        hub.config,
        "get",
        lambda key, default=None: (
            3 if key == "photometry.auto_comparisons" else real_get(key, default)
        ),
    )

    assert hub.targets._auto_select_comparisons(tset, target) == 3

    assert [s.auid for s in tset.by_role("check")] == ["000-CHK-001"]  # [] before the fix
    assert [s.auid for s in tset.by_role("comparison")] == ["000-CMP-1", "000-CMP-2", "000-CMP-3"]


_BJD_OFFLINE = """
import json, warnings
warnings.simplefilter("ignore")
import astropy.utils.data as data
calls = []
def blocked(*args, **kwargs):
    calls.append(str(args[0]) if args else "")
    raise OSError("network blocked")
data.download_file = blocked
from argos.core.photometry.airmass import bjd_tdb
from argos.server.photometry import bundled_iers_only
bundled_iers_only()
print(json.dumps({"bjd": bjd_tdb(2461290.67, 316.0, 42.0, 48.85, 2.35, 50.0), "calls": calls}))
"""


def test_bjd_tdb_is_computed_offline(tmp_path):
    """Release S37: astropy downloaded IERS tables on the first BJD; offline it
    refused its bundled table and no point had a BJD_TDB. A fresh process (astropy
    caches its tables) with the network blocked."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    blocked = "http://127.0.0.1:9"
    env = dict(
        os.environ,
        PYTHONPATH=str(root),
        HOME=str(tmp_path),
        XDG_CACHE_HOME=str(tmp_path / "cache"),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        HTTP_PROXY=blocked,
        HTTPS_PROXY=blocked,
        http_proxy=blocked,
        https_proxy=blocked,
    )
    out = subprocess.run(
        [sys.executable, "-c", _BJD_OFFLINE], env=env, capture_output=True, text=True, timeout=120
    )
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["calls"] == []
    assert result["bjd"] == pytest.approx(2461290.6741261533, abs=2e-9)  # online astropy 7.2


def test_a_failed_csv_rewrite_leaves_the_previous_file(tmp_path, monkeypatch):
    """Release S38: the live CSV was truncated and rewritten in place each point."""
    from argos.core.photometry.lightcurve import LcPoint, LightCurve
    from argos.server.photometry import write_csv_atomic

    curve = LightCurve(auid="000-SYN-T", name="SYN Var")
    for i in range(3):
        curve.append(LcPoint(jd_utc=2461290.5 + i, mag=11.0, mag_err=0.02))
    path = tmp_path / "SYN_Var.csv"
    write_csv_atomic(curve, path)
    before = path.read_bytes()
    curve.to_csv(tmp_path / "plain.csv")
    assert (tmp_path / "plain.csv").read_bytes() == before  # the same bytes as to_csv

    def broken(self, target):
        Path(target).write_text("jd_utc,bjd")
        raise OSError("disk full")

    monkeypatch.setattr(LightCurve, "to_csv", broken)
    with pytest.raises(OSError):
        write_csv_atomic(curve, path)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["SYN_Var.csv", "plain.csv"]


# -- saved frames and preview CSVs (S39-S41, fixed for 0.5.0) --------------------------


def test_a_frame_written_before_0_5_is_dated_by_its_start():
    """S39: the port dates a 0.4.x sequence frame as Qt's fits_exposure_mid does."""
    from argos.server.capture import fits_exposure_mid

    frame = {
        "DATE-OBS": "2026-09-25T20:04:57",
        "DATE-AVG": "2026-09-25T20:05:20.4",
        "EXPTIME": 30.0,
    }
    start_plus_half = datetime(2026, 9, 25, 20, 5, 12, tzinfo=timezone.utc)
    for software in ("Argos v0.4.2", "Argos"):
        assert fits_exposure_mid({**frame, "SOFTWARE": software}) == start_plus_half
    for software in ("Argos v0.5.0", "N.I.N.A. 3.1"):
        assert fits_exposure_mid({**frame, "SOFTWARE": software}) == datetime(
            2026, 9, 25, 20, 5, 20, 400000, tzinfo=timezone.utc
        )


def test_measuring_an_object_again_keeps_its_earlier_csv(phot_client, monkeypatch):
    """S40: outside a run, measuring an object again (A → B → A) rewrote its CSVs
    from the new curve; each curve now has its own file."""
    clock = {"now": datetime(2026, 11, 9, 20, 15, tzinfo=timezone.utc)}
    monkeypatch.setattr("argos.server.photometry._utcnow", lambda: clock["now"])
    tset = target_set()
    folder = phot_client.sessions_path / "targets"
    tset.save(folder / "SYN_Var.json")
    TargetSet("Other", tset.stars).save(folder / "Other.json")
    hub = phot_client.hub

    def measure(name: str, count: int, seq: int) -> None:
        set_object(phot_client, name)
        hub.targets.reload()
        for i in range(count):
            hub.photometry.measure(
                MeasureRequest(
                    frame_seq=seq + i,
                    raw=synthetic_raw(i + 2),
                    wcs=GREEN_WCS,
                    epoch=T0 + timedelta(minutes=seq + i),
                    generation=1,
                    fwhm=2.0,
                )
            )

    measure(OBJECT, 2, 100)
    clock["now"] += timedelta(minutes=5)
    measure("Other", 1, 200)
    clock["now"] += timedelta(minutes=5)
    measure(OBJECT, 1, 300)

    def rows(name: str) -> int:
        with (folder / name).open() as fh:
            return sum(1 for _ in csv.DictReader(fh))

    # The filter between start time and star (S49): the Camera form's, no wheel.
    assert rows("SYN_Var_20261109T201500Z_ir_000-SYN-K.csv") == 2  # kept: one file per curve
    assert rows("SYN_Var_20261109T202500Z_ir_000-SYN-K.csv") == 1
    assert rows("Other_20261109T202000Z_ir_000-SYN-K.csv") == 1


def test_an_opened_frame_uses_its_own_gain_for_errors(phot_client, tmp_path, monkeypatch):
    """S41: an opened frame's errors used the capture settings' e-/ADU; the port
    takes the gain table at the frame's GAIN, else its EGAIN, as Qt does."""
    import argos.server.photometry as photometry

    seen: list[float] = []
    real = photometry.measure_frame

    def spy(green, wcs, tset, params, **kwargs):
        seen.append(params.egain)
        return real(green, wcs, tset, params, **kwargs)

    monkeypatch.setattr(photometry, "measure_frame", spy)
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    from astropy.io import fits

    path = write_frame(tmp_path / "gain200.fit", synthetic_raw(2), 0)
    with fits.open(path, mode="update") as hdul:
        hdul[0].header["GAIN"] = 200
        hdul[0].header["EGAIN"] = 0.31
    open_and_solve(phot_client, path)
    assert seen[-1] == pytest.approx(0.31)  # the table's EGAIN at gain 80 before the fix
    assert phot_client.hub.field.pilot().egain == pytest.approx(0.31)

    response = phot_client.patch(
        "/api/config", json={"camera.egain_table": {"80": EGAIN, "200": 0.29}}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    open_and_solve(phot_client, path)
    assert seen[-1] == pytest.approx(0.29)

    plain = write_frame(tmp_path / "plain.fit", synthetic_raw(3), 1)
    open_and_solve(phot_client, plain)
    assert seen[-1] == pytest.approx(EGAIN)  # nothing recorded: the live chain at gain 80


# -- 0.5.0 S48, S49 (release branch; ported) -----------------------------------------


def _add_star(raw: np.ndarray, gx: float, gy: float, mag: float) -> np.ndarray:
    """``raw`` with one more star at green (gx, gy) (each green value over its 2x2 tile)."""
    yy, xx = np.mgrid[0:GH, 0:GW]
    flux = 10 ** (-0.4 * (mag - 21.0))
    star = (
        flux / (2 * math.pi * SIGMA**2) * np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / 2 / SIGMA**2)
    )
    out = raw.astype(np.float64) + np.kron(star, np.ones((2, 2)))
    return np.clip(out, 0, 65535).astype(np.uint16)


def test_a_sub_whose_anchors_show_no_star_gets_no_point_s48(phot_client, monkeypatch):
    """Release S48: after a 30 px jump one tracker window centroided a neighbour
    5 px from where comparison C1 was; the tracker moved every aperture by that
    offset, S35 (no anchor at all) did not fire and the sub was measured on the
    wrong stars, unflagged (the 6a review's replay of RR Lyr 40-79: 8 points
    21-67 px off). Now: no point, status ``lock_lost``, a re-solve due at once."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    monkeypatch.setattr(type(hub.field), "solved", property(lambda self: True))
    raw = synthetic_raw(0, drift=False)
    first = MeasureRequest(1, raw, GREEN_WCS, T0, 1, fwhm=2.4, origin="sequence")
    assert hub.photometry.measure(first) == 7
    lock = phot_client.get("/api/photometry/live", headers=AUTH).json()["status"]["lock"]
    assert lock["held"] and lock["seen"] == lock["anchors"] >= 2
    jumped = _add_star(_add_star(np.roll(raw, 60, axis=1), 46.0, 41.0, 10.0), 104.0, 83.0, 10.5)
    later = T0 + timedelta(minutes=1)
    lost = MeasureRequest(2, jumped, GREEN_WCS, later, 1, fwhm=2.4, origin="sequence")
    assert hub.photometry.measure(lost) == 0  # 2 points, on the wrong stars, before the fix
    assert hub.photometry._tracker.anchors_used >= 1  # S35 alone would have measured it
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert all(len(c["points"]) == 1 for c in live["curves"])
    status = live["status"]
    assert status["state"] == "skipped" and status["reason"] == "lock_lost"
    assert "#2" in status["message"]
    assert status["lock"]["frame_seq"] == 2 and not status["lock"]["held"]
    assert status["lock"]["seen"] < status["lock"]["needed"]
    assert any("fewer than half the anchor stars" in m for m in log_messages(phot_client))
    assert hub.field._resolve_due_flag  # the next frame is solved whatever the cadence


def test_the_lock_check_keeps_every_drifting_frame_s48(phot_client):
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    for i in range(6):  # drift 0.35, -0.22 px and 0.04° per frame (the fixture's)
        request = MeasureRequest(i + 1, synthetic_raw(i), GREEN_WCS, T0 + timedelta(minutes=i), 1)
        assert hub.photometry.measure(replace(request, fwhm=2.4)) == 7
    assert not hub.field._resolve_due_flag


def test_a_set_change_never_re_anchors_on_a_stale_solution_s52(phot_client, monkeypatch):
    """Release S52: a set change between two solves (the VSP backfill, a role
    edit) dropped the tracker and the next sub rebuilt it on the raw solution,
    30 px behind the drifting field. Only a neighbour near C1's solved position
    was seen there: 1 anchor of 1 passed the S48 check and the apertures sat on
    blank sky until the next solve (the science review's replay of RR Lyr
    0-79: five unflagged target points 30-37 px off). The tracker is now rebuilt
    on the solution as tracked so far, and in a run the next sub is solved."""
    import dataclasses

    import argos.server.photometry as photometry

    placed: list = []
    real = photometry.measure_frame

    def spy(green, wcs, tset, params, **kwargs):
        placed.append(wcs.world_to_pixel_deg(*sky(100.0, 80.0)))  # the target's aperture
        return real(green, wcs, tset, params, **kwargs)

    monkeypatch.setattr(photometry, "measure_frame", spy)
    full = target_set()
    fewer = TargetSet(object_name=OBJECT, stars=[s for s in full.stars if s.name != "C5"])
    path = phot_client.sessions_path / "targets" / "SYN_Var.json"
    fewer.save(path)
    set_object(phot_client)
    hub = phot_client.hub
    monkeypatch.setattr(
        hub, "_camera_state", dataclasses.replace(hub._camera_state, owner="sequence")
    )
    raw = synthetic_raw(0, drift=False)

    def sub(i: int, dx: float) -> int:
        # The field drifts east; a field star rides along 30 px west of C1, so it
        # sits 5 px from C1's solved position once the field has moved 30 px.
        frame = _add_star(np.roll(raw, int(2 * dx), axis=1), 16.0 + dx, 41.0, 10.0)
        when = T0 + timedelta(minutes=i)
        request = MeasureRequest(i + 1, frame, GREEN_WCS, when, 1, fwhm=2.4, origin="sequence")
        return hub.photometry.measure(request)

    for i, dx in enumerate((0.0, 10.0, 20.0, 30.0)):  # the tracker follows the drift
        assert sub(i, dx) == 6
    assert not hub.field._resolve_due_flag

    full.save(path)
    hub.targets.reload()  # the set changes between solves: C5 added
    assert hub.field._resolve_due_flag  # in a run, the next sub is solved at once

    assert sub(4, 30.0) == 7
    x, y = placed[-1]
    # True position (130, 80): about (104, 83), on blank sky, before the fix.
    assert math.hypot(x - 130.0, y - 80.0) < 5.0
    assert hub.photometry._tracker.anchors_used >= 3


def test_each_filter_has_its_own_curve_csv_and_vetting_s49(phot_client, tmp_path):
    """Release S49: a run alternating two filters mixed both in one curve per star
    (one CSV, one floor, one leave-one-out vetting). Now one per (star, filter)."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    run = tmp_path / "20260925T200000Z_SYN_Var"
    (run / "photometry").mkdir(parents=True)
    with phot_client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        for i, filt in enumerate(["V", "B", "V", "B", "V"]):
            request = MeasureRequest(
                i + 1,
                synthetic_raw(i),
                GREEN_WCS,
                T0 + timedelta(minutes=i),
                1,
                fwhm=2.4,
                run_root=run,
                origin="sequence",
                filter_name=filt,
            )
            assert hub.photometry.measure(request) == 7
        seen: list[dict] = []
        receive_until(ws, lambda m: m["type"] == "photometry" and m["points"] == 35, seen=seen)
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    by_key = {c["key"]: c for c in live["curves"]}
    assert len(by_key[f"{OBJECT}@v"]["points"]) == 3 and len(by_key[f"{OBJECT}@b"]["points"]) == 2
    assert by_key[f"{OBJECT}@b"]["filter"] == "b" and by_key[f"{OBJECT}@b"]["star_key"]
    assert len(live["curves"]) == 14  # 7 stars x 2 filters
    names = sorted(p.name for p in (run / "photometry").iterdir())
    assert "target_SYN_Var_v_SYN_Var.csv" in names and "target_SYN_Var_b_SYN_Var.csv" in names
    assert "comparison_SYN_Var_b_000-SYN-C1.csv" in names and len(names) == 14
    assert (run / "photometry_quality.json").exists()  # the run's first filter
    assert (run / "photometry_quality_b.json").exists()
    points = [m for m in seen if m["type"] == "photometry_point"]
    assert {m["filter"] for m in points} == {"v", "b"}
    assert all(m["key"].endswith("@" + m["filter"]) for m in points)
    quality = [m for m in seen if m["type"] == "comparison_quality"]
    assert quality[-1]["filter"] == "v"  # the last sub's filter
    assert all(e["key"].endswith("@v") for e in quality[-1]["report"]["comparison_stars"])
    assert live["status"]["last"]["filter"] == "v"


# -- 0.5.0 S54, S56, S57 (release branch; ported) --------------------------------------


def test_a_new_solution_the_anchors_do_not_confirm_is_refused_s54(phot_client):
    """Release S54: a new solution rebuilt the tracker from the stars seen where it
    put them, so a wrong match passed S48 (XX Cyg 2026-09-07 045156Z frame 1: 1
    anchor of 6 seen). Fewer than half the current tracker's anchors showing a star
    where a new solution puts them now refuses it; only a tracker built for the
    field's current solution counts."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    raw = synthetic_raw(0, drift=False)
    assert hub.photometry.measure(MeasureRequest(1, raw, GREEN_WCS, T0, 1, fwhm=2.4)) == 7
    anchors = len(hub.photometry._tracker_anchor_stars)
    assert anchors >= 3
    wrong = frame_wcs({**WCS_FIELDS, "CRPIX1": WCS_FIELDS["CRPIX1"] + 25.0}, (GH, GW))
    refusal = hub.photometry.solution_refusal(raw, wrong, 1)
    assert refusal is not None and f"of the {anchors} anchor stars" in refusal
    assert hub.photometry.solution_refusal(raw, GREEN_WCS, 1) is None  # the right one
    shifted = frame_wcs({**WCS_FIELDS, "CRPIX1": WCS_FIELDS["CRPIX1"] + 30.0}, (GH, GW))
    moved = np.roll(raw, 60, axis=1)  # the field jumped 30 px: its own solution passes
    assert hub.photometry.solution_refusal(moved, shifted, 1) is None
    assert hub.photometry.solution_refusal(raw, wrong, 2) is None  # another solution's tracker


def test_a_lock_on_fewer_than_three_anchors_flags_its_points_s56(phot_client, tmp_path):
    """Release S56: with 1 or 2 anchors the S48 check is met by the very anchor that
    moved the solution, so it verifies nothing. The points are flagged ``suspect``
    (the stream's flag, the CSV's column), a re-solve is due at once, the status's
    ``lock.verified`` is false, and the log says so once per episode."""
    from argos.core.photometry.lightcurve import LightCurve

    full = target_set()
    two = TargetSet(
        object_name=OBJECT,
        stars=[
            s for s in full.stars if s.role == "target" or s.auid in ("000-SYN-C1", "000-SYN-C2")
        ],
    )
    two.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    run = tmp_path / "20260925T200000Z_SYN_Var"
    (run / "photometry").mkdir(parents=True)
    with phot_client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        for i in range(2):
            request = MeasureRequest(
                i + 1,
                synthetic_raw(i),
                GREEN_WCS,
                T0 + timedelta(minutes=i),
                1,
                fwhm=2.4,
                run_root=run,
                origin="sequence",
            )
            assert hub.photometry.measure(request) == 3  # kept, flagged
        seen: list[dict] = []
        receive_until(ws, lambda m: m["type"] == "photometry" and m["points"] == 6, seen=seen)
    assert len(hub.photometry._tracker_anchor_stars) == 2
    points = [m for m in seen if m["type"] == "photometry_point"]
    assert len(points) == 6 and all(m["point"]["suspect"] for m in points)  # unflagged before
    status = phot_client.get("/api/photometry/live", headers=AUTH).json()["status"]
    assert status["lock"]["held"] and status["lock"]["verified"] is False
    assert hub.field._resolve_due_flag  # a re-solve at once
    texts = [m for m in log_messages(phot_client) if "cannot be verified" in m]
    assert len(texts) == 1
    csv = run / "photometry" / "target_SYN_Var_clear_SYN_Var.csv"
    assert [p.suspect for p in LightCurve.from_csv(csv).points] == [True, True]


def test_a_lock_on_three_anchors_or_more_is_verified_s56(phot_client):
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    request = MeasureRequest(1, synthetic_raw(0), GREEN_WCS, T0, 1, fwhm=2.4, origin="sequence")
    assert hub.photometry.measure(request) == 7
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert live["status"]["lock"]["verified"] is True
    assert not any(p["suspect"] for c in live["curves"] for p in c["points"])
    assert not hub.field._resolve_due_flag


def _two_anchor_set(client) -> None:
    """Target, C1 and C2: a tracker of 2 anchors (S56)."""
    full = target_set()
    two = TargetSet(
        object_name=OBJECT,
        stars=[
            s for s in full.stars if s.role == "target" or s.auid in ("000-SYN-C1", "000-SYN-C2")
        ],
    )
    two.save(client.sessions_path / "targets" / "SYN_Var.json")
    set_object(client)


def _measure_target(hub, seq: int, raw, solved_seq, *, reset: bool = False) -> bool:
    """One sub measured through GREEN_WCS (solved on frame ``solved_seq``): its target
    point's ``suspect`` flag."""
    request = MeasureRequest(
        seq,
        raw,
        GREEN_WCS,
        T0 + timedelta(minutes=seq),
        1,
        fwhm=2.4,
        origin="sequence",
        reset_tracker=reset,
        solved_seq=solved_seq,
    )
    assert hub.photometry.measure(request) == 3
    (curve,) = [c for k, c in hub.photometry._curves.items() if k.startswith(OBJECT)]
    return curve.points[-1].suspect


def test_a_few_anchor_lock_near_a_fresh_solution_is_verified_s56(phot_client):
    """Release S56 as amended (2026-11-15): with 1-2 anchors a frame is verified when
    it is measured through a solution of this sub or the previous one and the
    tracker moved no aperture 2 px or more from where it puts it (XX Cyg 2026-08-29
    050148Z: 2 anchors, all 22 points flagged before, 21 within 2 px of the star).
    No re-solve is due then. Two subs after the solve, or 3 px from it: flagged."""
    _two_anchor_set(phot_client)
    hub = phot_client.hub
    raw = synthetic_raw(0, drift=False)
    assert _measure_target(hub, 1, raw, 1) is False  # this sub's solution
    assert len(hub.photometry._tracker_anchor_stars) == 2
    assert not hub.field._resolve_due_flag
    assert _measure_target(hub, 2, raw.copy(), 1) is False  # the previous sub's
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert live["status"]["lock"]["verified"] is True
    assert hub.field._resolve_due_flag  # its own solve is due too (2026-11-15, second set)
    hub.field._resolve_due_flag = False
    assert _measure_target(hub, 3, raw.copy(), 1) is True  # two subs after it
    assert hub.field._resolve_due_flag
    for seq, (shift, flagged) in enumerate(((1, False), (3, True)), start=10):
        hub.field._resolve_due_flag = False
        moved = np.roll(raw, 2 * shift, axis=1)  # the field drifted ``shift`` green px
        assert _measure_target(hub, seq, moved, seq - 1, reset=True) is flagged, shift
        assert hub.field._resolve_due_flag  # a re-solve, or (verified) the sub in hand solved


def test_the_unverified_lock_warns_once_per_episode_s56(phot_client):
    """Release S56 as amended: one log line per episode; a solve that lands does not
    end it (it warned on every sub of a field that never reaches 3 anchors), a
    verified frame, an invalidation or a set change does."""
    _two_anchor_set(phot_client)
    hub = phot_client.hub
    raw = synthetic_raw(0, drift=False)

    def warnings() -> list[str]:
        return [m for m in log_messages(phot_client) if "cannot be verified" in m]

    assert _measure_target(hub, 1, raw, None) is True
    assert _measure_target(hub, 2, raw, None) is True
    hub.photometry.on_solved(
        MeasureRequest(2, raw, GREEN_WCS, T0, 1, origin="sequence", solved_seq=0)
    )
    assert _measure_target(hub, 3, raw, 0) is True  # a solve of an older frame
    assert _measure_target(hub, 4, raw, 0) is True
    assert len(warnings()) == 1, warnings()  # 2 before the amendment
    assert "while fewer than 3 anchor stars steer the apertures" in warnings()[0]
    assert _measure_target(hub, 5, raw, 5, reset=True) is False  # verified: ends it
    assert _measure_target(hub, 6, raw, 4, reset=True) is True
    assert len(warnings()) == 2
    hub.photometry.on_field_invalidated()
    assert hub.photometry._unverified_logged is False


def test_the_lock_check_uses_anchors_chosen_on_the_solved_frame_s56(phot_client, monkeypatch):
    """Release S56 as amended (2026-11-15, second set): the anchors were chosen on the
    measured sub through the previous sub's solution. After a jump only a star that
    happened to show at a stale position qualified (here a field star 1.1 px from
    C1's solved spot): 1 anchor of 1, seen by construction (S48), moving the
    apertures 1.1 px, so S56 verified it and the sub was measured off its stars,
    unflagged (real RR Lyr subs moved 500 px: 1 anchor, the target 496 px off,
    flagged by a 0.16 px margin). The anchors are now chosen on the frame the
    solution was solved on (``solved_raw``): 1 of them shows a star on the moved
    sub, the lock is lost, no point, a re-solve due."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    monkeypatch.setattr(type(hub.field), "solved", property(lambda self: True))
    solved = synthetic_raw(0, drift=False)
    rng = np.random.default_rng(77)  # another field: none of the set's stars
    sky_only = np.clip(300.0 + rng.normal(0.0, 6.0, (GH, GW)), 0, 65535)
    moved = np.kron(sky_only, np.ones((2, 2))).astype(np.uint16)
    moved = _add_star(_add_star(moved, 43.0, 38.5, 10.0), 101.0, 80.5, 10.5)
    request = MeasureRequest(
        2,
        moved,
        GREEN_WCS,
        T0,
        1,
        fwhm=2.4,
        origin="sequence",
        solved_seq=1,  # the previous sub's solution
        solved_raw=solved,
    )
    assert hub.photometry.measure(request) == 0  # points off the stars, unflagged, before
    assert len(hub.photometry._tracker_anchor_stars) >= 3  # 1 (the field star) before
    status = phot_client.get("/api/photometry/live", headers=AUTH).json()["status"]
    assert status["state"] == "skipped" and status["reason"] == "lock_lost"
    assert status["lock"]["seen"] == 1 and status["lock"]["anchors"] >= 3
    assert hub.field._resolve_due_flag


def test_a_run_solves_the_sub_verified_through_the_previous_solution_s56(phot_client, monkeypatch):
    """Release S56 as amended (2026-11-15, second set): a sub of 1-2 anchors verified
    through the previous sub's solution made no solve due, so the next sub was two
    subs from a solution: with one solve per run the subs alternated verified and
    flagged (XX Cyg 2026-08-29 050148Z: 12 of 22 flagged). In a run the sub in hand
    is now solved too; outside a run a live point follows each solve."""
    _two_anchor_set(phot_client)
    hub = phot_client.hub
    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(hub.field, "resolve_due", lambda seq, now=False: calls.append((seq, now)))
    raw = synthetic_raw(0, drift=False)
    assert _measure_target(hub, 1, raw, 1) is False  # this sub's own solution
    assert calls == []
    assert _measure_target(hub, 2, raw.copy(), 1) is False  # the previous sub's
    assert calls == [(2, True)]  # [] before the fix
    solved = 2  # one solve per run: a sub's solve lands when it is due
    for seq in range(3, 7):
        calls.clear()
        assert _measure_target(hub, seq, raw.copy(), solved, reset=True) is False, seq
        solved = seq if calls else solved  # subs 4 and 6 flagged before the fix
    calls.clear()
    live = MeasureRequest(
        8, raw.copy(), GREEN_WCS, T0, 1, fwhm=2.4, reset_tracker=True, solved_seq=7
    )
    assert hub.photometry.measure(live) == 3  # a live frame: nothing more is due
    assert calls == []


def test_the_anchor_check_needs_half_the_anchors_s54(phot_client, monkeypatch):
    """Release S54's threshold is ceil(k/2) of the tracker's k anchors: 1 of 4 seen
    refuses the solution (045156Z frame 1 was 1 of 6), 2 of 4 accept it."""
    import argos.server.photometry as photometry

    comps = {f"000-SYN-C{i}" for i in (1, 2, 3, 4)}
    four = TargetSet(
        object_name=OBJECT,
        stars=[s for s in target_set().stars if s.role == "target" or s.auid in comps],
    )
    four.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    raw = synthetic_raw(0, drift=False)
    assert hub.photometry.measure(MeasureRequest(1, raw, GREEN_WCS, T0, 1, fwhm=2.4)) == 5
    assert len(hub.photometry._tracker_anchor_stars) == 4
    monkeypatch.setattr(photometry, "anchors_seen", lambda *a, **k: 1)
    reason = hub.photometry.solution_refusal(raw, GREEN_WCS, 1)
    assert reason is not None and "only 1 of the 4 anchor stars" in reason
    assert "(2 needed" in reason
    monkeypatch.setattr(photometry, "anchors_seen", lambda *a, **k: 2)
    assert hub.photometry.solution_refusal(raw, GREEN_WCS, 1) is None


def test_three_agreeing_refused_solutions_are_a_re_pointing_s54(phot_client, monkeypatch):
    """Release S54 as amended (2026-11-15): when the field moved without a reported
    slew, the previous anchors are off the frame and every correct solution was
    refused. 3 consecutive refused solutions that agree within 20 px are accepted
    and logged; 3 that disagree stay refused."""
    import argos.server.photometry as photometry

    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    raw = synthetic_raw(0, drift=False)
    assert hub.photometry.measure(MeasureRequest(1, raw, GREEN_WCS, T0, 1, fwhm=2.4)) == 7
    monkeypatch.setattr(photometry, "anchors_seen", lambda *a, **k: 0)  # the field moved

    def solution(dx: float):
        return frame_wcs({**WCS_FIELDS, "CRPIX1": WCS_FIELDS["CRPIX1"] + dx}, (GH, GW))

    for dx in (300.0, 400.0, 500.0, 600.0, 604.0):  # 3 disagree, then 2 of a new field
        assert hub.photometry.solution_refusal(raw, solution(dx), 1) is not None, dx
    assert hub.photometry.solution_refusal(raw, solution(608.0), 1) is None  # refused before
    texts = [m for m in log_messages(phot_client) if "re-pointing the mount did not" in m]
    assert len(texts) == 1 and "agree within 8.0 px" in texts[0]
    assert hub.photometry._repoint_refused == []


def test_every_vetting_file_names_its_filter_s57(phot_client, tmp_path):
    """Release S57: ``photometry_quality.json`` vets the run's first filter and did
    not say which. Each vetting file now carries an additive ``filter`` key (the
    S49 token); the session list still reads the run."""
    from argos.server.sessions import summarise

    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    run = tmp_path / "20260925T200000Z_SYN_Var"
    (run / "photometry").mkdir(parents=True)
    for i, filt in enumerate(["IR", "LP", "IR"]):
        request = MeasureRequest(
            i + 1,
            synthetic_raw(i),
            GREEN_WCS,
            T0 + timedelta(minutes=i),
            1,
            fwhm=2.4,
            run_root=run,
            origin="sequence",
            filter_name=filt,
        )
        assert hub.photometry.measure(request) == 7
    first = json.loads((run / "photometry_quality.json").read_text())
    other = json.loads((run / "photometry_quality_lp.json").read_text())
    assert first["filter"] == "ir" and other["filter"] == "lp"  # no key before the fix
    assert list(first)[-1] == "filter"  # last, as the release core writes it
    (run / "session.json").write_text(json.dumps({"object": OBJECT, "frames": []}))
    summary = summarise(run)
    assert summary["has_quality"]
    assert not any("photometry_quality" in issue for issue in summary["issues"])


def _core_filter_token():
    """GUARD (pending merge of release/0.5.0): the core's S49 ``filter_token``, or None."""
    from argos.core.imaging import fits_writer

    return getattr(fits_writer, "filter_token", None)


@pytest.mark.skipif(
    _core_filter_token() is None, reason="the core has no S49 yet (release/0.5.0 not merged)"
)
def test_the_filter_token_is_the_cores_s49():
    """Curve keys and CSV names spell the filter as the Qt frame names do."""
    from argos.server.photometry import filter_token

    core = _core_filter_token()
    names = [None, "", "  ", "IR", "LP", "V", "B", "Ha", "ha", "OIII", " SII ", "IR-cut"]
    names += ["LRGB", "Clear", "Dark", "Sloan r'", "Hα", "R/G", "L-eXtreme", "UV/IR cut"]
    for name in names:
        assert filter_token(name) == core(name), name


def test_a_live_frame_takes_the_filter_of_the_settled_wheel_s49(phot_client, monkeypatch):
    """Release ``_live_filter``: the wheel's settled slot, else the frame's form filter."""
    tset = target_set()
    tset.save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    request = MeasureRequest(1, synthetic_raw(0), GREEN_WCS, T0, 1, fwhm=2.4, filter_name="IR")
    assert hub.photometry._frame_filter(request) == "IR"  # no wheel: the form's
    monkeypatch.setattr(type(hub.wheel), "connected", property(lambda self: True))
    monkeypatch.setattr(type(hub.wheel), "moving", property(lambda self: False))
    monkeypatch.setattr(type(hub.wheel), "slot", property(lambda self: "LP"))
    assert hub.photometry._frame_filter(request) == "LP"
    opened = replace(request, origin="file", filter_name=None)
    assert hub.photometry._frame_filter(opened) == ""  # an opened file says, or nothing


# -- 0.5.0 S69 (release branch; ported) -------------------------------------------------


def core_has_s69() -> bool:
    """GUARD (pending merge of release/0.5.0): the core's tracker has S69's centring
    check and rotation rule (``tracking.centring_offsets``, ``rotation_resolve_due``)."""
    from argos.core.photometry import tracking

    return hasattr(tracking, "centring_offsets") and hasattr(tracking, "rotation_resolve_due")


requires_s69_core = pytest.mark.skipif(
    not core_has_s69(), reason="the core has no S69 yet (release/0.5.0 not merged)"
)


def turned_raw(deg: float, *, moved: dict[str, tuple[float, float]] | None = None) -> np.ndarray:
    """``synthetic_raw``'s field turned ``deg`` about the frame centre (an alt-az run);
    ``moved``: stars whose light sits ``(dx, dy)`` green px from their catalogue place."""
    rng = np.random.default_rng(2000 + int(deg * 10))
    theta = math.radians(deg)
    cx, cy = GW / 2.0, GH / 2.0
    yy, xx = np.mgrid[0:GH, 0:GW]
    green = np.full((GH, GW), 300.0)
    for key, _role, gx, gy, v in STARS:
        x = cx + math.cos(theta) * (gx - cx) - math.sin(theta) * (gy - cy)
        y = cy + math.sin(theta) * (gx - cx) + math.cos(theta) * (gy - cy)
        dx, dy = (moved or {}).get(key, (0.0, 0.0))
        flux = 10 ** (-0.4 * ((target_v(0) if key == "T" else v) - 21.0))
        green += (
            flux
            / (2 * math.pi * SIGMA**2)
            * np.exp(-((xx - x - dx) ** 2 + (yy - y - dy) ** 2) / (2 * SIGMA**2))
        )
    green += rng.normal(0.0, 6.0, green.shape)
    return np.kron(np.clip(green, 0, 65535), np.ones((2, 2))).astype(np.uint16)


@requires_s69_core
def test_a_field_turned_more_than_2_deg_since_the_solution_makes_a_solve_due_s69(phot_client):
    """Release S69 (a): the tracker carried one solution over the whole rotation while
    its lock held (XX Cyg 2026-09-07: 16.5° in 32 min, apertures up to 8.5 px off). A
    solve is now due once the tracked rotation since the solution exceeds 2°; while
    none lands, again only after 2° more (never on every frame)."""
    target_set().save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    due: list[float] = []
    for seq, deg in enumerate((0.0, 1.0, 2.5, 3.5, 4.0, 4.7), start=1):
        hub.field._resolve_due_flag = False
        request = MeasureRequest(seq, turned_raw(deg), GREEN_WCS, T0, 1, fwhm=2.4)
        assert hub.photometry.measure(request) == 7
        if hub.field._resolve_due_flag:
            due.append(deg)
    assert due == [2.5, 4.7]  # never before the port (the lock held on 6 anchors)
    assert abs(hub.photometry._tracker.transform.rotation_deg - 4.7) < 0.1
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    assert not any(p["suspect"] for c in live["curves"] for p in c["points"])


@requires_s69_core
def test_an_off_centre_comparison_leaves_the_ensemble_s69(phot_client):
    """Release S69 (b): a comparison whose centroid is more than 1 px from its aperture
    centre is left out of the frame's ensemble and its own point is flagged suspect;
    the target keeps its point from the other comparisons (C4's light 2.5 px from its
    catalogue place: the tracker rejects it as an anchor)."""
    target_set().save(phot_client.sessions_path / "targets" / "SYN_Var.json")
    set_object(phot_client)
    hub = phot_client.hub
    raw = turned_raw(0.0, moved={"C4": (2.5, 0.0)})
    assert hub.photometry.measure(MeasureRequest(1, raw, GREEN_WCS, T0, 1, fwhm=2.4)) == 7
    live = phot_client.get("/api/photometry/live", headers=AUTH).json()
    (target,) = [c for c in live["curves"] if c["role"] == "target"]
    assert target["points"][-1]["comps_used"] == 4  # 5 before the port
    assert not target["points"][-1]["suspect"]
    assert _star(live["curves"], "000-SYN-C4")["points"][-1]["suspect"]
    assert any("more than 1 px from the aperture centre" in m for m in log_messages(phot_client))
