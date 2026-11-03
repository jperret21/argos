"""AcquisitionEngine unit tests — no hardware, no event loop.

A ``QApplication`` is required because the engine is a ``QObject``; signals
are observed through direct connections into plain lists.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from argos.core.config import _DEFAULTS, Config
from argos.core.session.acquisition_engine import AcquisitionEngine
from argos.core.session.device_session import DeviceSession


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_ingest_frame_feeds_the_live_pipeline(qapp, tmp_path) -> None:
    """Offline replay: an opened FITS must land exactly where a camera frame
    would — authoritative full-res raw + a frame_ready for the display."""
    cfg = Config(dict(_DEFAULTS, sessions_path=str(tmp_path)))
    engine = AcquisitionEngine(cfg, DeviceSession(cfg))
    frames = []
    engine.frame_ready.connect(frames.append)

    raw = np.arange(64, dtype=np.uint16).reshape(8, 8)
    engine.ingest_frame(raw)

    assert len(frames) == 1
    assert frames[0].full is raw and frames[0].preview is raw
    assert frames[0].decimated is False
    # Solve/photometry read the same authoritative frame.
    assert engine._last_raw is raw and engine._last_raw_decimated is False


# ---------------------------------------------------------------------------
# Take shot: a real engine, a fake camera/wheel/preview worker, and a
# synchronous thread pool, so the FITS save really writes under tmp_path.
# ---------------------------------------------------------------------------


class _Sig:
    """Stand-in for a worker signal: records the connected slots."""

    def __init__(self) -> None:
        self.slots: list = []

    def connect(self, slot) -> None:
        self.slots.append(slot)


class _FakePreviewWorker:
    """Records how the engine created it; never exposes anything."""

    created: list[dict] = []

    def __init__(self, camera, **kwargs) -> None:
        self.kw = kwargs
        _FakePreviewWorker.created.append(kwargs)
        self.frame_ready = _Sig()
        self.status_updated = _Sig()
        self.error_occurred = _Sig()
        self.finished = _Sig()
        self.updates: list = []

    def start(self) -> None:
        pass

    def isRunning(self) -> bool:  # noqa: N802 (QThread API)
        return False

    def update_settings(self, *args, **kwargs) -> None:
        self.updates.append((args, kwargs))

    def stop(self) -> None:
        pass

    def wait(self, _ms: int = 0) -> bool:
        return True


class _FakeCamera:
    def __init__(self) -> None:
        self.gains: list = []
        self.exposures: list = []

    def get_ccd_temperature(self):
        return 20.0

    def get_electrons_per_adu(self):
        return None

    def get_offset(self):
        return None

    def get_readout_mode_name(self):
        return None

    def set_gain(self, gain) -> None:
        self.gains.append(gain)

    def try_get_gain(self):
        return self.gains[-1] if self.gains else None

    def start_exposure(self, exposure, light=True) -> None:
        self.exposures.append((exposure, light))

    def is_image_ready(self) -> bool:
        return True

    def get_image_array(self):
        return _star_frame()

    def stop_exposure(self) -> None:
        pass


class _FakeWheel:
    """Seestar wheel: 0 = Dark, 1 = IR, 2 = LP. Moves are instantaneous."""

    names = {0: "Dark", 1: "IR", 2: "LP"}

    def __init__(self, position: int = 1) -> None:
        self.position = position
        self.set_calls: list[int] = []

    def get_position(self) -> int:
        return self.position

    def set_position(self, position: int) -> None:
        self.set_calls.append(position)
        self.position = position

    def position_name(self) -> str:
        return self.names[self.position]


class _SyncPool:
    """QThreadPool stand-in: runs the task at once, on this thread."""

    def start(self, task) -> None:
        task.run()


def _star_frame(h: int = 120, w: int = 160, sigma: float = 2.0) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    star = 20000.0 * np.exp(-((xx - 80.0) ** 2 + (yy - 60.0) ** 2) / (2 * sigma**2))
    return (star + 300.0).astype(np.uint16)


@pytest.fixture
def shot_rig(qapp, tmp_path, monkeypatch):
    """(engine, session, form, logs): ``form["p"]`` is what the Camera form shows."""
    import argos.core.session.acquisition_engine as ae
    from argos.ui.widgets.camera_dock import CaptureParams

    _FakePreviewWorker.created = []
    monkeypatch.setattr(ae, "LivePreviewWorker", _FakePreviewWorker)
    monkeypatch.setattr(ae.QThreadPool, "globalInstance", staticmethod(lambda: _SyncPool()))
    cfg = Config(dict(_DEFAULTS, sessions_path=str(tmp_path / "sessions")))
    session = DeviceSession(cfg)
    session._camera = _FakeCamera()
    engine = AcquisitionEngine(cfg, session)
    form = {"p": CaptureParams("Light Frame", "V1", "IR", 10.0, 80)}
    engine.set_providers(lambda: form["p"], lambda: 1)
    logs: list[tuple[str, str]] = []
    engine.log_message.connect(lambda level, msg: logs.append((level, msg)))
    return engine, session, form, logs


def test_dark_take_shot_refused_unless_the_wheel_is_on_the_dark_slot(shot_rig) -> None:
    """S1: the Seestar has no shutter — its wheel's Dark slot is the only one.

    A Dark/Bias Take shot with the wheel on a light filter used to expose a
    light frame and label it IMAGETYP=Dark; used as a master dark it corrupts
    every calibrated science frame.
    """
    from argos.ui.widgets.camera_dock import CaptureParams
    from argos.workers.camera_service import CameraState

    engine, session, form, logs = shot_rig
    session._filterwheel = _FakeWheel(position=1)  # wheel on IR

    for frame_type in ("Dark Frame", "Bias Frame"):
        form["p"] = CaptureParams(frame_type, "V1", "IR", 10.0, 80)
        logs.clear()
        engine.take_shot()
        assert _FakePreviewWorker.created == [], f"{frame_type} exposed behind IR"
        assert engine.camera_state is CameraState.IDLE
        assert engine._capture_pending == 0
        assert any(level == "WARN" and "Dark" in msg for level, msg in logs), logs

    # Live owns the camera: the shot must not tag the next (light) frame either.
    form["p"] = CaptureParams("Light Frame", "V1", "IR", 10.0, 80)
    engine.start_live()
    form["p"] = CaptureParams("Dark Frame", "V1", "IR", 10.0, 80)
    engine.take_shot()
    assert engine._capture_pending == 0
    engine.stop_live()

    # Filter "Dark" selected (the Camera form moves the wheel; it settles at
    # once here): the shot goes, shutter closed.
    session.move_filter(0)
    _FakePreviewWorker.created = []
    form["p"] = CaptureParams("Dark Frame", "V1", "Dark", 10.0, 80)
    engine.take_shot()
    assert len(_FakePreviewWorker.created) == 1
    assert _FakePreviewWorker.created[0]["light"] is False
    assert engine._capture_pending == 1


def test_dark_take_shot_without_a_wheel_warns_that_the_scope_must_be_covered(shot_rig) -> None:
    from argos.ui.widgets.camera_dock import CaptureParams

    engine, session, form, logs = shot_rig
    assert session.filterwheel is None
    form["p"] = CaptureParams("Dark Frame", "V1", "IR", 10.0, 80)
    engine.take_shot()
    assert len(_FakePreviewWorker.created) == 1  # no wheel to check: trust the observer
    assert any(level == "WARN" and "cover" in msg for level, msg in logs), logs


class _OneFrameCamera(_FakeCamera):
    """Lets a real LivePreviewWorker deliver exactly one frame, then stop."""

    worker = None

    def get_image_array(self):
        self.worker.stop()  # the loop ends after this frame is emitted
        return _star_frame()


@pytest.fixture
def real_preview_rig(qapp, tmp_path, monkeypatch):
    """The engine with the real LivePreviewWorker, run on this thread."""
    import argos.core.session.acquisition_engine as ae
    from argos.ui.widgets.camera_dock import CaptureParams
    from argos.workers.exposure_worker import LivePreviewWorker

    monkeypatch.setattr(LivePreviewWorker, "start", lambda self: None)
    monkeypatch.setattr(ae.QThreadPool, "globalInstance", staticmethod(lambda: _SyncPool()))
    cfg = Config(dict(_DEFAULTS, sessions_path=str(tmp_path / "sessions")))
    session = DeviceSession(cfg)
    camera = _OneFrameCamera()
    session._camera = camera
    engine = AcquisitionEngine(cfg, session)
    form = {"p": CaptureParams("Light Frame", "V1", "IR", 10.0, 80)}
    engine.set_providers(lambda: form["p"], lambda: 1)

    def deliver_one_frame() -> None:
        camera.worker = engine._preview
        engine._preview.run()  # synchronous: frame_ready reaches the engine directly

    return engine, camera, form, deliver_one_frame, tmp_path / "sessions"


def _saved_headers(root) -> list:
    from astropy.io import fits

    return [(path, fits.getheader(path)) for path in sorted(root.rglob("*.fit"))]


def test_take_shot_header_records_the_settings_the_frame_was_exposed_with(
    real_preview_rig,
) -> None:
    """S2: the form edited during the exposure must not rewrite its header."""
    from argos.ui.widgets.camera_dock import CaptureParams

    engine, camera, form, deliver_one_frame, root = real_preview_rig
    engine.take_shot()  # the worker is created with 10 s / gain 80 / Light / IR
    form["p"] = CaptureParams("Flat Frame", "V1", "LP", 30.0, 200)  # edited meanwhile
    deliver_one_frame()

    assert camera.exposures == [(10.0, True)] and camera.gains == [80]
    ((path, hdr),) = _saved_headers(root)
    assert hdr["EXPTIME"] == 10.0
    assert hdr["GAIN"] == 80
    assert hdr["IMAGETYP"] == "Light Frame"
    assert hdr["FILTER"] == "IR"
    assert "_ir_" in path.name.lower() and "e010000ms" in path.name and "g080" in path.name


def test_live_take_shot_saves_the_in_flight_frame_with_its_own_exposure(
    real_preview_rig,
) -> None:
    """S2: Live at 10 s, set 30 s and press Take shot during the exposure."""
    from argos.ui.widgets.camera_dock import CaptureParams

    engine, camera, form, deliver_one_frame, root = real_preview_rig
    engine.start_live()
    form["p"] = CaptureParams("Light Frame", "V1", "IR", 30.0, 80)
    engine.take_shot()  # Live: tags the next frame to arrive (exposed at 10 s)
    deliver_one_frame()

    assert camera.exposures == [(10.0, True)]
    ((_, hdr),) = _saved_headers(root)
    assert hdr["EXPTIME"] == 10.0


def _deliver(engine, frame=None) -> None:
    """Hand the engine one frame as the preview worker would, with the
    settings snapshot the worker took when it started the exposure."""
    from datetime import datetime, timedelta, timezone

    from argos.workers.exposure_worker import FrameSettings

    params = engine._preview.kw["tag"]
    used = FrameSettings(params.exposure_s, params.gain, engine._preview.kw["light"], params)
    frame = _star_frame() if frame is None else frame
    start = datetime(2026, 10, 1, 22, 0, 0, tzinfo=timezone.utc)
    engine._on_frame(frame, frame, start, start + timedelta(seconds=10.4), used)


def test_take_shot_after_a_sequence_records_the_filter_the_wheel_is_on(shot_rig, tmp_path) -> None:
    """S3: a sequence moves the wheel itself; the Camera form is not told.

    A Take shot afterwards wrote the form's filter (IR) into FILTER and the
    folder/file name while the wheel sat on LP.
    """
    from argos.core.imaging.sequencer import SequencePlan, SequenceStep
    from argos.ui.widgets.camera_dock import CaptureParams
    from argos.workers.sequence_worker import SequenceWorker

    engine, session, form, logs = shot_rig
    wheel = _FakeWheel(position=1)  # IR; the Camera form shows IR
    session._filterwheel = wheel
    moved: list[tuple[int, str]] = []
    session.filter_moved.connect(lambda pos, name: moved.append((pos, name)))

    plan = SequencePlan(
        steps=[SequenceStep(frame_type="Light", filter_name="LP", exposure_s=0.0, count=1)],
        object_name="V1",
        base_dir=tmp_path / "seq",
    )
    SequenceWorker(
        camera=session.camera,
        telescope=None,
        filterwheel=wheel,
        plan=plan,
        frame_context_provider=engine._sequence_frame_context,
        base_dir=tmp_path / "seq",
    ).run()  # synchronous
    assert wheel.position_name() == "LP"
    assert moved == []  # the sequence moved the wheel behind the Camera form's back

    # (1) The header reads the wheel, whatever the form still shows.
    form["p"] = CaptureParams("Light Frame", "V1", "IR", 10.0, 80)
    engine.take_shot()
    _deliver(engine)
    ((path, hdr),) = _saved_headers(tmp_path / "sessions")
    assert hdr["FILTER"] == "LP"
    assert "_lp_" in path.name.lower()  # the file name carries the filter (not the folder)
    assert any(level == "WARN" and "LP" in msg for level, msg in logs), logs

    # (2) The end of the run re-reads the wheel so the Camera form resyncs.
    engine._on_seq_finished(True)  # what the worker's finished signal triggers
    assert moved == [(2, "LP")]


def test_take_shot_keeps_the_form_filter_when_the_wheel_cannot_be_read(shot_rig, tmp_path) -> None:
    engine, session, form, logs = shot_rig
    wheel = _FakeWheel(position=1)
    wheel.position = -1  # still turning: position_name() would say "Moving…"
    wheel.names = {**_FakeWheel.names, -1: "Moving…"}
    session._filterwheel = wheel
    engine.take_shot()
    _deliver(engine)
    ((_, hdr),) = _saved_headers(tmp_path / "sessions")
    assert hdr["FILTER"] == "IR"


class _HeldWheelPool(_SyncPool):
    """Runs every task at once except wheel moves, held until ``settle()``:
    the wheel turns for as long as the test wants."""

    def __init__(self) -> None:
        self.held: list = []

    def start(self, task) -> None:
        if type(task).__name__ == "_FilterMoveRunnable":
            self.held.append(task)
        else:
            task.run()

    def settle(self) -> None:
        while self.held:
            self.held.pop(0).run()


def _frame_with(engine, tag, start) -> None:
    """Hand the engine one frame exposed from ``start`` with the form ``tag``."""
    from datetime import timedelta

    from argos.workers.exposure_worker import FrameSettings

    light = tag.frame_type == "Light Frame"
    used = FrameSettings(tag.exposure_s, tag.gain, light, tag)
    frame = _star_frame()
    engine._on_frame(frame, frame, start, start + timedelta(seconds=10.4), used)


def test_dark_take_shot_waits_for_the_wheel_to_settle_on_dark(
    shot_rig, tmp_path, monkeypatch
) -> None:
    """S1 (gap found in review): the Filter combo shows 'Dark' as soon as it
    is picked, while the wheel still turns. The guard read only the combo,
    so a Dark shot taken at once exposed through the moving wheel and was
    saved as a clean IMAGETYP='Dark Frame', FILTER='Dark'. Same when a
    refused move could not be read back (the combo stayed on 'Dark')."""
    import argos.core.session.acquisition_engine as ae
    from argos.ui.widgets.camera_dock import CaptureParams
    from argos.workers.camera_service import CameraState

    engine, session, form, logs = shot_rig
    pool = _HeldWheelPool()
    monkeypatch.setattr(ae.QThreadPool, "globalInstance", staticmethod(lambda: pool))
    wheel = _FakeWheel(position=1)
    session._filterwheel = wheel
    form["p"] = CaptureParams("Dark Frame", "V1", "Dark", 10.0, 80)

    session.move_filter(0)  # Dark picked: the wheel starts turning
    engine.take_shot()
    assert _FakePreviewWorker.created == [], "a dark exposed through a turning wheel"
    assert engine.camera_state is CameraState.IDLE and engine._capture_pending == 0
    assert any(level == "WARN" and "turning" in msg for level, msg in logs), logs

    pool.settle()  # the wheel reports it is on Dark
    assert session.filter_slot == "Dark"
    engine.take_shot()
    assert len(_FakePreviewWorker.created) == 1
    assert _FakePreviewWorker.created[0]["light"] is False
    engine._capture_pending = 0
    engine._camera_service.release(CameraState.SINGLE)

    # A refused move that cannot be read back: filter_moved(-1, "") leaves
    # the combo on the slot that was asked for.
    from argos.core.alpaca.client import AlpacaError

    wheel.set_position = lambda _p: (_ for _ in ()).throw(AlpacaError(1025, "Invalid value"))
    wheel.get_position = lambda: (_ for _ in ()).throw(AlpacaError(0, "Timeout"))
    session.move_filter(0)
    pool.settle()
    assert session.filter_slot is None and not session.filter_moving
    _FakePreviewWorker.created = []
    logs.clear()
    engine.take_shot()
    assert _FakePreviewWorker.created == []
    assert any(level == "WARN" and "unknown" in msg for level, msg in logs), logs


def test_dark_shot_is_dropped_if_the_wheel_leaves_the_dark_slot(
    shot_rig, tmp_path, monkeypatch
) -> None:
    """S1: a Dark shot accepted on the Dark slot must not be saved once the
    wheel has been turned to a light filter before its frame arrives."""
    from datetime import datetime, timezone

    from argos.ui.widgets.camera_dock import CaptureParams
    from argos.workers.camera_service import CameraState

    engine, session, form, logs = shot_rig
    session._filterwheel = _FakeWheel(position=1)
    session.move_filter(0)  # settles at once (synchronous pool)
    dark = CaptureParams("Dark Frame", "V1", "Dark", 10.0, 80)
    form["p"] = dark
    engine.take_shot()
    assert engine._capture_pending == 1

    start = datetime.now(timezone.utc)
    session.move_filter(1)  # IR picked during the exposure
    _frame_with(engine, dark, start)  # exposed while the wheel turned: skipped
    assert _saved_headers(tmp_path / "sessions") == []
    assert engine._capture_pending == 1

    # The loop's next frame starts after the move, the form still on Dark Frame.
    _frame_with(
        engine, CaptureParams("Dark Frame", "V1", "IR", 10.0, 80), datetime.now(timezone.utc)
    )
    assert _saved_headers(tmp_path / "sessions") == []
    assert engine._capture_pending == 0
    assert engine.camera_state is CameraState.IDLE
    assert any(level == "WARN" and "not saved" in msg for level, msg in logs), logs


def test_take_shot_never_saves_a_frame_exposed_while_the_wheel_turned(shot_rig, tmp_path) -> None:
    """S3 (gap found in review): in Live the Filter combo stays usable, so the
    wheel could turn during the exposure a Take shot then saved, and FITS
    FILTER recorded the slot the wheel ended on, read after the exposure."""
    from datetime import datetime, timezone

    from argos.ui.widgets.camera_dock import CaptureParams

    engine, session, form, logs = shot_rig
    session._filterwheel = _FakeWheel(position=1)
    ir = CaptureParams("Light Frame", "V1", "IR", 10.0, 80)
    form["p"] = ir
    engine.start_live()
    in_flight_start = datetime.now(timezone.utc)  # the exposure starts on IR
    lp = CaptureParams("Light Frame", "V1", "LP", 10.0, 80)
    form["p"] = lp
    session.move_filter(2)  # LP picked mid-exposure (settles at once here)
    engine.take_shot()

    _frame_with(engine, ir, in_flight_start)
    assert _saved_headers(tmp_path / "sessions") == []
    assert any(level == "INFO" and "moved during" in msg for level, msg in logs), logs

    _frame_with(engine, lp, datetime.now(timezone.utc))  # the next frame, all on LP
    ((path, hdr),) = _saved_headers(tmp_path / "sessions")
    assert hdr["FILTER"] == "LP" and "_lp_" in path.name.lower()
    assert not any("not on the form" in msg for _level, msg in logs)
    engine.stop_live()


def _write_fits(path, header: dict) -> None:
    from astropy.io import fits

    hdu = fits.PrimaryHDU(_star_frame())
    for key, value in header.items():
        hdu.header[key] = value
    hdu.writeto(path)


def _open_fits_from_the_page(engine, path, monkeypatch, logs) -> list:
    """Run ImagingPage._on_open_fits on a stand-in page around the real engine."""
    from types import SimpleNamespace

    import argos.ui.pages.imaging_page as ip

    cleared: list[bool] = []

    def clear_astrometry() -> None:
        cleared.append(True)
        engine.invalidate_astrometry()

    monkeypatch.setattr(
        ip.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), ""))
    )
    page = SimpleNamespace(
        _cfg=lambda key, default: default,
        _engine=engine,
        _frame_context_lbl=SimpleNamespace(setText=lambda text: None),
        log_message=SimpleNamespace(emit=lambda level, msg: logs.append((level, msg))),
        _clear_astrometry=clear_astrometry,
    )
    ip.ImagingPage._on_open_fits(page)
    return cleared


def test_opened_fits_is_dated_by_its_header_and_drops_the_previous_wcs(
    shot_rig, tmp_path, monkeypatch
) -> None:
    """S4: Open FITS used to keep the previous field's WCS and the previous
    live frame's epoch, so the point measured after a solve was stamped with
    the wrong time (and could land in the last run's CSV)."""
    from datetime import datetime, timezone

    engine, session, form, logs = shot_rig
    engine._last_exposure_mid = datetime(2026, 11, 1, 3, 0, 5, tzinfo=timezone.utc)  # live
    engine.astrometry._wcs = object()  # ... solved: the previous field
    engine._active_run_root = tmp_path / "last_run"  # ... of the last sequence
    path = tmp_path / "archived.fit"
    _write_fits(path, {"DATE-OBS": "2026-09-15T21:00:00", "EXPTIME": 10.0})

    cleared = _open_fits_from_the_page(engine, path, monkeypatch, logs)

    assert engine.last_raw is not None and engine.last_raw.shape == (120, 160)
    assert engine.astrometry.wcs is None
    assert engine._last_exposure_mid == datetime(2026, 9, 15, 21, 0, 5, tzinfo=timezone.utc)
    assert engine._active_run_root is None
    assert cleared  # the page dropped its overlays/markers too

    # DATE-AVG, when present, is the midpoint itself.
    _write_fits(
        tmp_path / "avg.fit",
        {"DATE-OBS": "2026-09-15T21:00:00", "DATE-AVG": "2026-09-15T21:00:07.5", "EXPTIME": 10.0},
    )
    engine.open_fits_frame(tmp_path / "avg.fit")
    assert engine._last_exposure_mid == datetime(2026, 9, 15, 21, 0, 7, 500000, tzinfo=timezone.utc)


def test_opened_fits_without_a_date_measures_no_point(shot_rig, tmp_path, monkeypatch) -> None:
    """S4: no DATE-OBS → no epoch → no point (never 'now', never the last frame's)."""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    import argos.core.session.acquisition_engine as ae
    from argos.core.catalog.targets import ROLE_TARGET, TargetSet, TargetStar

    engine, session, form, logs = shot_rig
    engine._last_exposure_mid = datetime(2026, 11, 1, 3, 0, 5, tzinfo=timezone.utc)  # live
    path = tmp_path / "undated.fit"
    _write_fits(path, {"EXPTIME": 10.0})
    _open_fits_from_the_page(engine, path, monkeypatch, logs)

    star = TargetStar(role=ROLE_TARGET, ra_deg=10.0, dec_deg=20.0, name="V1")
    tset = TargetSet(object_name="V1", stars=[star])
    monkeypatch.setattr(engine, "target_set", lambda: tset)
    engine.astrometry._wcs = object()  # solved since
    diff = SimpleNamespace(
        mag=12.0,
        mag_err=0.01,
        formal_mag_err=0.01,
        comps_used=3,
        zero_point=0.0,
        zp_rms=0.0,
        note="",
    )
    phot = SimpleNamespace(sky_adu=300.0, saturated=False, suspect=False)
    result = SimpleNamespace(star=star, diff=diff, relative=None, phot=phot)
    monkeypatch.setattr(ae, "measure_frame", lambda *a, **k: [result])
    monkeypatch.setattr(engine, "_wcs_for_frame", lambda *a: None)
    monkeypatch.setattr(engine, "_write_live_quality_report", lambda tset: None)
    points: list = []
    engine.photometry_point.connect(points.append)
    engine.curves_changed.connect(lambda: points.append("curves"))

    engine._measure_photometry()

    assert engine._last_exposure_mid is None
    assert points == [] and engine.lightcurves == {}
    assert any(level == "WARN" and "time" in msg.lower() for level, msg in logs), logs


def test_opened_fits_that_is_not_raw_16_bit_data_is_refused(
    shot_rig, tmp_path, monkeypatch
) -> None:
    """S4 (part left open, found in review): Open FITS cast any data to
    uint16. A negative value (dark-subtracted, calibrated frame) wrapped to
    about 65535 and 70000 to 4464; the frame still solved and was measured
    with wrong sky and aperture sums, now dated as if trustworthy."""
    from datetime import datetime, timezone

    from astropy.io import fits

    engine, session, form, logs = shot_rig
    live = _star_frame()
    engine.ingest_frame(live)
    mid = datetime(2026, 11, 1, 3, 0, 5, tzinfo=timezone.utc)
    engine._last_exposure_mid = mid
    wcs = object()
    engine.astrometry._wcs = wcs
    header = {"DATE-OBS": "2026-09-15T21:00:00", "EXPTIME": 10.0}

    calibrated = _star_frame().astype(np.float32) - 300.5  # negative sky, fractions
    stacked = _star_frame().astype(np.int32) * 4  # beyond 16 bits
    for name, data in (("calibrated.fit", calibrated), ("stacked.fit", stacked)):
        path = tmp_path / name
        hdu = fits.PrimaryHDU(data)
        for key, value in header.items():
            hdu.header[key] = value
        hdu.writeto(path)
        logs.clear()
        _open_fits_from_the_page(engine, path, monkeypatch, logs)
        assert any(level == "ERROR" and "raw" in msg for level, msg in logs), logs
        # The engine is untouched: the live frame, its time and its WCS stay.
        assert engine.last_raw is live
        assert engine._last_exposure_mid == mid and engine.astrometry.wcs is wcs

    # Raw counts stored in another type are accepted as they are.
    path = tmp_path / "raw_as_float.fit"
    hdu = fits.PrimaryHDU(_star_frame().astype(np.float32))
    hdu.header["DATE-OBS"] = "2026-09-15T21:00:00"
    hdu.writeto(path)
    engine.open_fits_frame(path)
    assert engine.last_raw.dtype == np.uint16
    assert np.array_equal(engine.last_raw, _star_frame())


def test_take_shot_qa_headers_describe_the_saved_frame(shot_rig, tmp_path) -> None:
    """S20: HFD/NSTARS/SKYLEVEL came from the last frame the display had
    processed (the previous frame at best, a half-res preview otherwise)."""
    from argos.core.imaging.metrics import detect_stars, frame_metrics

    engine, session, form, logs = shot_rig
    stale = frame_metrics(_star_frame(sigma=6.0) + np.uint16(2000))  # an earlier, defocused frame
    engine._last_metrics = stale
    engine.take_shot()
    saved = _star_frame(sigma=1.5)
    _deliver(engine, saved)

    ((_, hdr),) = _saved_headers(tmp_path / "sessions")
    truth = frame_metrics(saved)
    assert abs(truth.hfd - stale.hfd) > 1.0 and abs(truth.sky_adu - stale.sky_adu) > 100
    assert hdr["HFD"] == pytest.approx(truth.hfd, abs=0.01)
    assert hdr["SKYLEVEL"] == pytest.approx(truth.sky_adu, abs=0.1)
    assert hdr["NSTARS"] == truth.star_count
    # As for a sequence frame, FWHM is measured on the saved array too.
    assert hdr["FWHM"] == pytest.approx(detect_stars(saved).mean_fwhm, abs=0.01)


def test_frames_saved_after_the_mount_went_away_carry_no_pointing(shot_rig, tmp_path) -> None:
    """X1: a disconnected (or lost) mount's last polled position went into
    the next frames' RA, DEC, ALTITUDE, AZIMUTH and AIRMASS."""
    from unittest.mock import MagicMock

    from argos.core.alpaca.telescope import MountPosition

    engine, session, form, logs = shot_rig
    session._telescope = MagicMock()
    session._on_position(MountPosition(5.0, 20.0, 45.0, 120.0, True, False))
    assert engine._sequence_frame_context("V1", "IR").altitude == 45.0  # mount up: used

    session.disconnect_mount()

    ctx = engine._sequence_frame_context("V1", "IR")
    assert (ctx.ra, ctx.dec, ctx.altitude, ctx.azimuth) == (None, None, None, None)
    engine.take_shot()
    _deliver(engine)
    ((_, hdr),) = _saved_headers(tmp_path / "sessions")
    for key in ("RA", "DEC", "OBJCTRA", "OBJCTDEC", "ALTITUDE", "AZIMUTH", "AIRMASS"):
        assert key not in hdr, f"{key} written from a disconnected mount"


def test_no_site_set_means_no_site_products_not_latitude_0_longitude_0(
    shot_rig, tmp_path, monkeypatch
) -> None:
    """With no site set, the config's 0/0 defaults were used as the site:
    the live point's airmass (the CSV airmass column and AAVSO AMASS) was
    computed for 0/0 (1.379 for SS Cyg at 2026-11-01 19:00 UTC, where the
    mount said 1.154 and Paris sees 1.005), and FITS got SITELAT/SITELONG 0."""
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import argos.core.session.acquisition_engine as ae
    from argos.core.alpaca.telescope import MountPosition
    from argos.core.catalog.targets import ROLE_TARGET, TargetSet, TargetStar
    from argos.core.photometry.airmass import airmass_at, airmass_from_altitude, julian_date

    engine, session, form, logs = shot_rig
    assert engine._config.get("site.name") == "" and engine._config.get("site.latitude") == 0.0
    session._telescope = MagicMock()
    session._on_position(MountPosition(21.7, 43.6, 60.0, 270.0, True, False))
    star = TargetStar(role=ROLE_TARGET, ra_deg=325.678, dec_deg=43.586, name="SS Cyg")
    monkeypatch.setattr(engine, "target_set", lambda: TargetSet("SS Cyg", [star]))
    diff = SimpleNamespace(
        mag=11.0, mag_err=0.02, formal_mag_err=0.02, comps_used=3, zero_point=0.0, zp_rms=0.0
    )
    diff.note = ""
    phot = SimpleNamespace(sky_adu=300.0, saturated=False, suspect=False)
    result = SimpleNamespace(star=star, diff=diff, relative=None, phot=phot)
    monkeypatch.setattr(ae, "measure_frame", lambda *a, **k: [result])
    monkeypatch.setattr(engine, "_wcs_for_frame", lambda *a: None)
    monkeypatch.setattr(engine, "_write_live_quality_report", lambda tset: None)
    mid = datetime(2026, 11, 1, 19, 0, tzinfo=timezone.utc)
    jd = julian_date(mid)

    def measure():
        engine.astrometry._wcs = object()
        engine._last_raw, engine._last_raw_decimated = _star_frame(), False
        engine._last_exposure_mid = mid
        engine._measure_photometry()
        return engine.lightcurves["SS Cyg"].points[-1]

    point = measure()
    assert point.airmass == pytest.approx(airmass_from_altitude(60.0))  # the mount's
    assert point.airmass != pytest.approx(airmass_at(jd, 325.678, 43.586, 0.0, 0.0))
    assert point.bjd_tdb is None
    ctx = engine._sequence_frame_context("SS Cyg", "IR")
    assert (ctx.site_lat, ctx.site_lon, ctx.site_elev) == (None, None, None)
    engine.take_shot()
    _deliver(engine)
    ((_, hdr),) = _saved_headers(tmp_path / "sessions")
    assert "SITELAT" not in hdr and "SITELONG" not in hdr

    # A site that was set (here typed, without a name) is used as before.
    engine._config._data["site"] = {"name": "", "latitude": 48.85, "longitude": 2.35}
    point = measure()
    assert point.airmass == pytest.approx(airmass_at(jd, 325.678, 43.586, 48.85, 2.35))
    assert point.bjd_tdb is not None
    assert engine._sequence_frame_context("SS Cyg", "IR").site_lat == 48.85


def test_engine_reports_whether_the_running_sequence_shoots_lights(shot_rig, monkeypatch) -> None:
    """S14: the page arms field identification only for runs with Light frames."""
    import argos.core.session.acquisition_engine as ae
    from argos.core.imaging.sequencer import SequencePlan, SequenceStep

    class _Worker:
        """Stands in for SequenceWorker: signals to connect, never runs."""

        def __init__(self, **_kwargs) -> None:
            for name in (
                "step_started",
                "frame_image",
                "frame_saved",
                "progress",
                "autofocus_due",
                "paused",
                "error_occurred",
                "finished",
            ):
                setattr(self, name, _Sig())

        def start(self) -> None:
            pass

        def isRunning(self) -> bool:  # noqa: N802 (QThread API)
            return True

    monkeypatch.setattr(ae, "SequenceWorker", _Worker)
    engine, session, form, logs = shot_rig
    assert engine.sequence_has_light_frames() is False  # nothing running

    darks = SequencePlan(steps=[SequenceStep(frame_type="Dark", count=5)])
    assert engine.start_sequence(darks)
    assert engine.sequence_has_light_frames() is False
    engine._on_seq_finished(False)

    mixed = SequencePlan(
        steps=[SequenceStep(frame_type="Light", count=0), SequenceStep(frame_type="Light")]
    )
    assert engine.start_sequence(mixed)
    assert engine.sequence_has_light_frames() is True
    engine._on_seq_finished(True)
    assert engine.sequence_has_light_frames() is False


def test_quality_report_emitted_in_live_preview(qapp, tmp_path) -> None:
    """S17: the comparison vetting was computed only once a sequence had
    saved a frame, so plain live preview never got a report."""
    from argos.core.catalog.targets import ROLE_COMPARISON, TargetSet, TargetStar
    from argos.core.photometry.lightcurve import LcPoint, LightCurve

    cfg = Config(dict(_DEFAULTS, sessions_path=str(tmp_path)))
    engine = AcquisitionEngine(cfg, DeviceSession(cfg))
    stars = [TargetStar(ROLE_COMPARISON, float(i), 10.0, auid=f"C{i}") for i in (1, 2, 3)]
    for star in stars:
        curve = LightCurve(auid=star.auid, name=star.auid, role=ROLE_COMPARISON)
        for i in range(12):
            mag = 10.0 + 0.01 * (i % 3 - 1)
            curve.append(LcPoint(2461315.5 + i / 1440.0, mag, 0.02, formal_mag_err=0.02))
        engine._lightcurves[star.auid] = curve
    reports: list = []
    engine.comparison_quality_updated.connect(reports.append)
    assert engine._active_run_root is None  # live preview, no sequence yet

    engine._write_live_quality_report(TargetSet(object_name="Test", stars=stars))

    assert len(reports) == 1  # 0 on 0.4.2
    assert [entry["auid"] for entry in reports[0]["comparison_stars"]] == ["C1", "C2", "C3"]
    assert engine.comparison_quality_report is reports[0]
    # Outside a run there is no session folder to write the report into.
    assert list(tmp_path.rglob("photometry_quality.json")) == []


def test_floor_change_rerenders_once_per_frame(shot_rig, monkeypatch) -> None:
    """S19: once the systematic floor applies (10th point), each star of each
    frame emitted curves_changed, i.e. a whole-store re-render per star."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    import argos.core.session.acquisition_engine as ae
    from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar

    engine, _session, _form, _logs = shot_rig
    stars = [TargetStar(role=ROLE_TARGET, ra_deg=10.0, dec_deg=20.0, name="V1")] + [
        TargetStar(role=ROLE_COMPARISON, ra_deg=10.0 + k / 100, dec_deg=20.0, auid=f"C{k}")
        for k in (1, 2)
    ]
    tset = TargetSet(object_name="V1", stars=stars)
    frame = {"i": 0}

    def measure(*_args, **_kwargs):
        mag = 12.0 + 0.01 * ((7 * frame["i"]) % 5 - 2)
        diff = SimpleNamespace(
            mag=mag,
            mag_err=0.01,
            formal_mag_err=0.01,
            comps_used=2,
            zero_point=0.0,
            zp_rms=0.0,
            note="",
        )
        phot = SimpleNamespace(sky_adu=300.0, saturated=False, suspect=False)
        return [SimpleNamespace(star=s, diff=diff, relative=None, phot=phot) for s in stars]

    monkeypatch.setattr(engine, "target_set", lambda: tset)
    monkeypatch.setattr(engine, "_wcs_for_frame", lambda *a: None)
    monkeypatch.setattr(engine, "_write_live_quality_report", lambda tset: None)
    monkeypatch.setattr(ae, "measure_frame", measure)
    monkeypatch.setattr(ae, "bjd_tdb", lambda *a: None)  # no IERS download
    monkeypatch.setattr(ae, "airmass_at", lambda *a: None)
    engine.astrometry._wcs = object()
    engine._last_raw = np.zeros((16, 16), np.uint16)
    engine._last_raw_decimated = False
    renders: list[int] = []
    engine.curves_changed.connect(lambda: renders.append(frame["i"]))

    t0 = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)
    for i in range(15):
        frame["i"] = i
        engine._last_exposure_mid = t0 + timedelta(minutes=i)
        engine._measure_photometry()

    per_frame = [renders.count(i) for i in range(15)]
    assert sum(per_frame) > 0  # the floor applied (and re-rendered) from the 10th point
    assert max(per_frame) == 1, per_frame  # 3 per frame (one per star) on 0.4.2
    assert sorted(len(lc.points) for lc in engine.lightcurves.values()) == [15, 15, 15]
    assert all(p.sigma_syst is not None for lc in engine.lightcurves.values() for p in lc.points)


class _ReturningAfWorker:
    """Stands in for an AutofocusWorker still driving the focuser back to its
    start after a stop (its return may take up to 30 s; Stop AF waits 10 s)."""

    created: list = []

    def __init__(self, **_kwargs) -> None:
        _ReturningAfWorker.created.append(self)
        self.running = False
        self.stops = 0
        self.waits: list[int] = []
        for name in ("step_done", "best_found", "error_occurred", "finished"):
            setattr(self, name, _Sig())

    def start(self) -> None:
        self.running = True

    def isRunning(self) -> bool:  # noqa: N802 (QThread API)
        return self.running

    def stop(self) -> None:
        self.stops += 1

    def wait(self, ms: int = 0) -> bool:
        self.waits.append(ms)
        return not self.running


def test_stop_af_keeps_a_returning_worker_and_refuses_a_second_sweep(shot_rig, monkeypatch) -> None:
    """S23 (gap found in review): when the return to the start outlasted the
    10 s wait, Stop AF dropped the worker and released the camera while the
    worker still drove the focuser; a new Start AF then ran a second worker
    on the same focuser, both commanding moves."""
    from unittest.mock import MagicMock

    import argos.core.session.acquisition_engine as ae
    from argos.workers.camera_service import CameraState

    engine, session, form, logs = shot_rig
    _ReturningAfWorker.created = []
    monkeypatch.setattr(ae, "AutofocusWorker", _ReturningAfWorker)
    session._focuser = MagicMock()

    engine.start_autofocus()
    (first,) = _ReturningAfWorker.created
    engine.stop_autofocus()  # the return outlasts the wait

    assert first.stops == 1 and first.running
    assert engine._autofocus is first
    assert engine.camera_state is CameraState.AUTOFOCUS
    assert any(level == "INFO" and "returning" in msg for level, msg in logs), logs
    engine.start_autofocus()
    engine.request_autofocus()  # the Focus screen's toggle: a second Stop
    assert len(_ReturningAfWorker.created) == 1  # no second sweep
    assert first.waits == [engine._AF_STOP_WAIT_MS]  # no second 10 s freeze

    first.running = False  # back at the start: the worker ends
    engine._on_af_finished()
    assert engine.camera_state is CameraState.IDLE
    engine.start_autofocus()
    assert len(_ReturningAfWorker.created) == 2
