"""Wave 6a PARITY: a sequence through the server against the fixed Qt sequence path.

The same frames are served to both: the server's simulator replays a folder of
FITS files (``--sim-replay``); the Qt ``AcquisitionEngine`` runs its real
``SequenceWorker`` thread (offscreen, queued signals processed by the event
loop) with a fake camera that serves the same files in the same order. Both
use the same reference solution (the fake ASTAP's WCS keys, read by both
through ``frame_wcs``; no re-solve during the run), the same target set, the
same site and gain table, and **one scripted clock** (run id, then the start
and the end of each exposure), so even the times agree.

Compared with **no tolerance** (the same core functions on the same inputs):
the run folder layout; every FITS header card and the pixels; ``session.json``;
``observation.json`` (S5) byte for byte; ``targets.json``; every field of every
light-curve point; the per-curve CSVs byte for byte; ``photometry_quality.json``
and ``photometry_selection.json`` minus their ``generated_utc`` (wall clock).
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from astropy.io import fits  # noqa: E402

from argos.core.imaging.metrics import detect_stars  # noqa: E402
from argos.core.imaging.sequencer import SequencePlan, SequenceStep  # noqa: E402
from argos.server.photometry import point_record  # noqa: E402
from argos.server.settings import SimOptions  # noqa: E402
from tests.server.conftest import AUTH, science_client, wait_for  # noqa: E402
from tests.server.test_field import FakeAstap  # noqa: E402
from tests.server.test_photometry import (  # noqa: E402
    EGAIN,
    requires_s49_core,
    OBJECT,
    SITE,
    WCS_FIELDS,
    EmptyCatalog,
    frames,
    target_set,
)

T_RUN = datetime(2026, 9, 25, 20, 0, 0, 123456, tzinfo=timezone.utc)
EXPOSURE_S = 0.05
METADATA = {
    "programme": "exoplanet",
    "planet_name": "SYN b",
    "period_days": 1.2345,
    "epoch_bjd_tdb": 2460000.5,
    "predicted_mid_utc": "2026-09-25T21:00:00Z",
}


class ScriptedClock:
    """Run id, then (start, end) of each exposure: the same instants on both sides."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls = 0

    def __call__(self) -> datetime:
        with self._lock:
            n = self._calls
            self._calls += 1
        if n == 0:
            return T_RUN
        frame, part = divmod(n - 1, 2)
        start = T_RUN + timedelta(seconds=30 * frame + 1.5, microseconds=137 * frame)
        return start + timedelta(seconds=EXPOSURE_S + 0.25) if part else start


def the_plan(count: int) -> SequencePlan:
    return SequencePlan(
        steps=[
            SequenceStep(
                frame_type="Light", filter_name="IR", exposure_s=EXPOSURE_S, gain=80, count=count
            )
        ],
        object_name=OBJECT,
        metadata=dict(METADATA),
    )


# -- Qt: the fixed engine and its SequenceWorker thread, offscreen ----------------------


class _QtReplayCamera:
    """The Qt Camera calls the worker and the context provider make."""

    def __init__(self, paths: list[Path]) -> None:
        self._paths = list(paths)
        self._i = -1
        self.gain = None

    def set_gain(self, gain) -> None:
        self.gain = gain

    def try_get_gain(self):
        return None  # the server's drivers have no read-back: the plan's gain on both

    def start_exposure(self, exposure, light=True) -> None:
        self._i += 1

    def is_image_ready(self) -> bool:
        return True

    def get_image_array(self):
        from argos.server.fits_source import load_raw_fits_frame

        return load_raw_fits_frame(self._paths[self._i]).pixels

    def stop_exposure(self) -> None:
        pass

    def get_ccd_temperature(self):
        return None

    def get_electrons_per_adu(self):
        return None

    def get_offset(self):
        return None

    def get_readout_mode_name(self):
        return None


def run_qt(tmp_path: Path, paths: list[Path], wcs, plan: SequencePlan) -> dict:
    qtwidgets = pytest.importorskip("PyQt6.QtWidgets")
    app = qtwidgets.QApplication.instance() or qtwidgets.QApplication([])
    import argos.workers.sequence_worker as worker_module
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
    engine._session._camera = _QtReplayCamera(paths)
    target_set().save(sessions / "targets" / "SYN_Var.json")
    engine.astrometry._wcs = copy.deepcopy(wcs)
    engine._on_reference_solved(None, None, "")
    # The page's display pipeline sets _last_fwhm on every frame (on_processed).
    engine.frame_ready.connect(
        lambda f: setattr(engine, "_last_fwhm", detect_stars(f.full, radius=5).mean_fwhm)
    )
    reports: list = []
    engine.comparison_quality_updated.connect(reports.append)

    clock = ScriptedClock()

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102
            return clock()

    original = worker_module.datetime
    worker_module.datetime = _Clock
    try:
        assert engine.start_sequence(plan)
        deadline = time.monotonic() + 60
        while engine._sequence is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert engine._sequence is None, "the Qt sequence did not end"
        app.processEvents()
    finally:
        worker_module.datetime = original
    return {"engine": engine, "curves": engine.lightcurves, "sessions": sessions}


# -- the server ---------------------------------------------------------------------------


def run_server(make_client, tmp_path: Path, folder: Path, plan: SequencePlan):
    sim = SimOptions(replay_dir=folder, mount_poll_s=0.05)
    client = science_client(make_client, tmp_path / "web", connect=("camera",), sim=sim)
    hub = client.app.state.hub
    astap = FakeAstap(tmp_path / "astap")
    astap.set("solve", wcs=WCS_FIELDS)
    db = tmp_path / "astap-db"
    db.mkdir(exist_ok=True)
    response = client.patch(
        "/api/config",
        json={
            "astrometry.astap_path": str(astap.path),
            "astrometry.database": "D50",
            "astrometry.database_path": str(db),
            "astrometry.live_resolve_s": 3600,
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
    hub.field.catalog_api = EmptyCatalog()
    hub.field.identify_point = lambda *args, **kwargs: None
    assert (
        client.put("/api/observation", json={"object_name": OBJECT}, headers=AUTH).status_code
        == 200
    )
    # Frame 0 of the replay: one frame to identify the field before the run.
    assert (
        client.post("/api/camera/capture", json={"exposure_s": 0.01}, headers=AUTH).status_code
        == 200
    )
    wait_for(lambda: hub.camera_owner() == "idle" and hub.field.idle(), timeout=10)
    job = client.post("/api/field/solve", headers=AUTH).json()["job_id"]
    wait_for(lambda: client.get(f"/api/jobs/{job}", headers=AUTH).json()["state"] == "done", 15)
    wait_for(lambda: hub.field.idle() and hub.photometry.idle(), timeout=10)
    wcs, _generation = hub.field.reference_solution()
    # The target set after the solve (no pre-run point: both trackers start empty).
    target_set().save(client.sessions_path / "targets" / "SYN_Var.json")
    hub.targets.reload()
    hub.sequence.plan_provider = lambda: copy.deepcopy(plan)
    hub.sequence.clock = ScriptedClock()
    started = client.post("/api/sequence/start", headers=AUTH)
    assert started.status_code == 200, started.text
    wait_for(lambda: hub.sequence.record()["state"] == "idle", timeout=60)
    wait_for(lambda: hub.photometry.idle() and hub.field.idle(), timeout=30)
    assert hub.sequence.record()["last_result"]["completed"]
    live = client.get("/api/photometry/live", headers=AUTH).json()
    return {"client": client, "live": live, "wcs": wcs, "sessions": client.sessions_path}


# -- the comparison --------------------------------------------------------------------------


def run_root(sessions: Path) -> Path:
    (root,) = [p for p in sessions.iterdir() if p.is_dir() and p.name != "targets"]
    return root


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def without_time(path: Path) -> dict:
    data = json.loads(path.read_text())
    data.pop("generated_utc", None)
    return data


@requires_s49_core  # GUARD: the run's CSV names and curve keys carry the filter (S49)
def test_a_sequence_gives_the_qt_files_and_points(make_client, tmp_path):
    paths = frames(tmp_path / "frames", n=14)
    count = len(paths) - 1  # frame 0 identifies the field first, on the server
    plan = the_plan(count)
    web = run_server(make_client, tmp_path, tmp_path / "frames", plan)
    qt = run_qt(tmp_path, paths[1:], web["wcs"], plan)

    ours, theirs = run_root(web["sessions"]), run_root(qt["sessions"])
    assert ours.name == theirs.name == "20260925T200000Z_SYN_Var"
    assert tree(ours) == tree(theirs)
    lights = sorted((ours / "lights").iterdir())
    assert len(lights) == count

    # FITS: every card and the pixels.
    for path in lights:
        with fits.open(path) as a, fits.open(theirs / "lights" / path.name) as b:
            ha, hb = a[0].header, b[0].header
            assert list(ha.keys()) == list(hb.keys()), path.name
            for key in ha.keys():
                if key in ("COMMENT", "HISTORY"):
                    continue
                assert ha[key] == hb[key], (path.name, key, ha[key], hb[key])
            assert np.array_equal(a[0].data, b[0].data)

    # Files of the run.
    assert (ours / "session.json").read_bytes() == (theirs / "session.json").read_bytes()
    assert (ours / "observation.json").read_bytes() == (theirs / "observation.json").read_bytes()
    assert json.loads((ours / "observation.json").read_text())["planet_name"] == "SYN b"
    assert (ours / "targets.json").read_bytes() == (theirs / "targets.json").read_bytes()
    assert without_time(ours / "photometry_selection.json") == without_time(
        theirs / "photometry_selection.json"
    )
    assert without_time(ours / "photometry_quality.json") == without_time(
        theirs / "photometry_quality.json"
    )
    csvs = sorted(p.name for p in (ours / "photometry").iterdir())
    assert csvs == sorted(p.name for p in (theirs / "photometry").iterdir()) and len(csvs) == 7
    for name in csvs:
        a = (ours / "photometry" / name).read_bytes()
        assert a == (theirs / "photometry" / name).read_bytes(), name

    # Every field of every point (one per saved Light sub and star).
    live = web["live"]
    assert live["run_root"] is None and live["sequence_running"] is False  # the run ended
    assert [c["key"] for c in live["curves"]] == list(qt["curves"])
    compared = 0
    for curve in live["curves"]:
        reference = qt["curves"][curve["key"]]
        assert len(curve["points"]) == len(reference.points) > 0
        for wire, point in zip(curve["points"], reference.points):
            expected = point_record(
                point, wire["frame_seq"], wire["t"], wire["zero_point"], wire["zp_rms"]
            )
            assert wire == expected, (curve["key"], wire, expected)
            compared += 1
    target = next(c for c in live["curves"] if c["role"] == "target")["points"]
    assert len(target) == count
    assert compared >= 7 * (count - 1)


def test_the_last_sub_keeps_the_series_fwhm_when_its_point_is_measured_after_the_end(
    make_client, tmp_path, monkeypatch
):
    """The run's end must not restart the series under a sub still queued for
    photometry (found by the real-frame parity: the last XX Cyg sub took its
    own FWHM, 2.26 instead of the series' 2.19, and its 7 points differed)."""
    from argos.server.photometry import PhotometryService

    original = PhotometryService.measure
    calls: list[int] = []

    def slow(self, request):
        if request.run_root is not None:
            calls.append(request.frame_seq)
        if request.run_root is not None and len(calls) == 4:  # the last sub, after the end
            deadline = time.monotonic() + 10
            while self._hub.sequence.record()["state"] != "idle":
                assert time.monotonic() < deadline
                time.sleep(0.02)
        return original(self, request)

    monkeypatch.setattr(PhotometryService, "measure", slow)
    import tests.server.test_photometry as synthetic

    folder = tmp_path / "frames"
    folder.mkdir()
    for i in range(5):  # a PSF that widens frame after frame: each has its own FWHM
        monkeypatch.setattr(synthetic, "SIGMA", 1.0 + 0.15 * i)
        synthetic.write_frame(folder / f"syn_{i:03d}.fit", synthetic.synthetic_raw(i), i)
    web = run_server(make_client, tmp_path, folder, the_plan(4))
    fwhms = {p["fwhm"] for c in web["live"]["curves"] for p in c["points"] if p["fwhm"] is not None}
    assert len(calls) == 4 and len(fwhms) == 1, fwhms
