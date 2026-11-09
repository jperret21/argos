"""Take shot through the server (rows A21-A24): FITS metadata, the 0.5.0 science fixes.

Every check is against the fixed Qt engine's rules (``notes/release_0_5_0.md``):
S1 (Dark/Bias need the wheel settled on Dark), S2 (settings snapshotted per
frame), S3 (FILTER read back; never a frame exposed while the wheel turned),
S20 (QA headers measured on the saved array), X1 (pointing only from a live
mount), X2 (the site only when one is set). The FITS parity tests compare a
server Take shot with ``FITSWriter`` fed the ``FrameContext`` that
``AcquisitionEngine._save_fits_async`` builds (``acquisition_engine.py:
1796-1910``) for the same inputs.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from argos import SOFTWARE_ID
from argos.core.imaging.fits_writer import FITSWriter, FrameContext
from argos.core.imaging.metrics import detect_stars, frame_metrics
from argos.server.capture import (
    FrameSettings,
    Pointing,
    SaveJob,
    save_frame,
    wheel_filter_name,
)
from argos.server.devices.base import MountReading
from argos.server.devices.sim_camera import PEDESTAL_ADU, SimCamera
from argos.server.devices.sim_mount import SimMount
from tests.server.conftest import (
    AUTH,
    TOKEN,
    decode_frame,
    log_messages,
    receive_bytes,
    receive_until,
    science_client,
    status,
    wait_for,
)

FIXED = MountReading(
    state="tracking",
    ra_hours=21.71268,
    dec_deg=43.58612,
    alt_deg=61.25,
    az_deg=280.5,
    tracking=True,
    pier_side="west",
)
PARIS = {"site.name": "Paris", "site.latitude": 48.8566, "site.longitude": 2.3522,
         "site.elevation": 35.0}  # fmt: skip


def _saved(client, count: int = 1, timeout: float = 10.0) -> list[dict]:
    return wait_for(
        lambda: (s := client.get("/api/camera/saved", headers=AUTH).json()["saves"])
        and len(s) >= count
        and s,
        timeout=timeout,
    )


def _idle(client, timeout: float = 10.0) -> dict:
    return wait_for(
        lambda: (c := status(client)["camera"])["owner"] == "idle" and c["state"] == "idle" and c,
        timeout=timeout,
    )


def _shot(client, **body) -> dict:
    response = client.post("/api/camera/capture", json={"save": True, **body}, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _header(path: str) -> fits.Header:
    with fits.open(path) as hdul:
        return hdul[0].header.copy()


def _data(path: str) -> np.ndarray:
    with fits.open(path) as hdul:
        return np.asarray(hdul[0].data).astype(np.uint16)


def _fixed_mount(monkeypatch) -> None:
    """A mount that always reports FIXED: the pointing a frame records is known."""
    monkeypatch.setattr(SimMount, "read", lambda self: FIXED)


# ---------------------------------------------------------------------------
# The basic Take shot
# ---------------------------------------------------------------------------


def test_take_shot_writes_the_fits_and_announces_it(science):
    science.put("/api/observation", json={"object_name": "SS Cyg"}, headers=AUTH)
    with science.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        _shot(science, exposure_s=0.05, gain=80)
        saved = receive_until(events, lambda m: m["type"] == "frame_saved", timeout=10)
    assert saved["seq"] == 1 and saved["source"] == "single"
    assert saved["object"] == "SS Cyg" and saved["filter"] == "IR"
    assert saved["frame_type"] == "light" and saved["image_type"] == "Light Frame"
    path = Path(saved["path"])
    assert path.is_file() and path.suffix == ".fit"
    # The Qt Take shot's folder and name (fits_writer.session_folder / build_filename).
    assert path.parent.name == "lights"
    assert path.parent.parent.parent == science.sessions_path
    assert path.parent.parent.name.endswith("_SS_Cyg")
    assert path.name == "SS_Cyg_ir_light_e000050ms_g080_00001.fit"
    header = _header(saved["path"])
    assert header["EXPTIME"] == 0.05 and header["GAIN"] == 80
    assert header["IMAGETYP"] == "Light Frame" and header["FILTER"] == "IR"
    assert header["OBJECT"] == "SS Cyg" and header["SOFTWARE"] == SOFTWARE_ID
    assert header["OFFSET"] == 10 and header["CCD-TEMP"] == 21.0
    assert header["DATE-OBS"] == saved["date_obs"].rstrip("Z")
    assert saved["record"]["hfd"] == header["HFD"]
    listing = science.get("/api/camera/saved?after=0", headers=AUTH).json()
    assert listing["last_seq"] == 1 and listing["saves"][0]["path"] == saved["path"]
    assert science.get("/api/camera/saved?after=1", headers=AUTH).json()["saves"] == []
    assert "Take shot — saving next frame…" in log_messages(science)
    assert f"Saved {path.name}" in log_messages(science)


def test_a_second_shot_never_overwrites(science, monkeypatch):
    """Two shots in one folder (the folder is named by the start second, as in Qt)."""
    from argos.server import capture

    real = capture.FITSWriter.session_folder

    def one_folder(base, object_name, start, image, filt, run_id=""):
        return real(base, object_name, datetime(2026, 11, 1, tzinfo=timezone.utc), image, filt)

    monkeypatch.setattr(capture.FITSWriter, "session_folder", staticmethod(one_folder))
    for _ in range(2):
        _shot(science, exposure_s=0.02)
        _idle(science)
    saves = _saved(science, 2)
    names = [Path(s["path"]).name for s in saves]
    assert names[0].endswith("_00001.fit") and names[1].endswith("_00002.fit")
    assert all(Path(s["path"]).is_file() for s in saves)


def test_object_defaults_to_unknown(science):
    _shot(science, exposure_s=0.02)
    header = _header(_saved(science)[0]["path"])
    assert header["OBJECT"] == "Unknown"  # camera_dock.py:243


def test_date_obs_and_date_avg_come_from_the_exposure(science):
    before = datetime.now(timezone.utc)
    _shot(science, exposure_s=0.3)
    header = _header(_saved(science)[0]["path"])
    after = datetime.now(timezone.utc)
    start = datetime.fromisoformat(header["DATE-OBS"]).replace(tzinfo=timezone.utc)
    mid = datetime.fromisoformat(header["DATE-AVG"]).replace(tzinfo=timezone.utc)
    assert before - timedelta(milliseconds=5) <= start <= after
    # DATE-AVG: midpoint between StartExposure and ImageReady (0.3 s waited).
    assert timedelta(seconds=0.14) <= mid - start <= timedelta(seconds=0.25)


def test_frame_header_fields_and_metrics(science):
    with science.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        with science.websocket_connect(f"/ws/events?token={TOKEN}") as events:
            _shot(science, exposure_s=0.02, gain=90)
            header, pixels = decode_frame(receive_bytes(frames))
            metrics = receive_until(events, lambda m: m["type"] == "frame_metrics")
            row = receive_until(events, lambda m: m["type"] == "conditions")
    assert header["origin"] == "single" and header["save"] is True
    assert header["frame_type"] == "light" and header["gain"] == 90 and header["filter"] == "IR"
    assert header["started_utc"].endswith("Z") and "bayer" in header
    reference = frame_metrics(pixels)
    assert metrics["seq"] == header["seq"] and metrics["hfd_px"] == reference.hfd
    assert metrics["star_count"] == reference.star_count and metrics["plane"] == "green"
    assert row["frame_seq"] == header["seq"] and row["gain"] == 90
    assert row["focuser_position"] == 5000
    page = science.get("/api/session/conditions?since_seq=0", headers=AUTH).json()
    assert page["rows"][-1]["frame_seq"] == header["seq"] and page["last_seq"] == row["seq"]


# ---------------------------------------------------------------------------
# FITS parity with the fixed Qt engine
# ---------------------------------------------------------------------------


def _qt_reference(
    arr,
    start: datetime,
    end: datetime,
    *,
    exposure: float,
    gain: int,
    frame_type: str,
    object_name: str,
    filter_name: str,
    pos: MountReading | None,
    target: tuple[float, float] | None,
    site,
    observer: str,
    camera_reads: dict,
    path: Path,
    egain_table: dict | None = None,
) -> fits.Header:
    """``_save_fits_async`` (acquisition_engine.py:1811-1898), written out independently."""
    site = site or (None, None, None)
    ctx = FrameContext(
        ccd_temp=camera_reads["ccd_temp"],
        egain_driver=camera_reads["egain_driver"],
        egain_table=egain_table or {},
        offset=camera_reads["offset"],
        readout_mode=camera_reads["readout_mode"],
        filter_name=filter_name,
        ra=pos.ra_hours if pos else None,
        dec=pos.dec_deg if pos else None,
        altitude=pos.alt_deg if pos else None,
        azimuth=pos.az_deg if pos else None,
        target_ra=target[0] if target else None,
        target_dec=target[1] if target else None,
        object_name=object_name,
        observer=observer,
        site_lat=site[0],
        site_lon=site[1],
        site_elev=site[2],
        software=SOFTWARE_ID,
    )
    metrics = frame_metrics(arr)
    field = detect_stars(arr)
    ctx.hfd = metrics.hfd
    ctx.star_count = metrics.star_count
    ctx.sky_adu = metrics.sky_adu
    ctx.fwhm = field.mean_fwhm
    ctx.eccentricity = field.mean_eccentricity
    FITSWriter.write(
        arr=arr,
        path=path,
        exposure_start=start,
        exposure_end=end,
        exposure_time=exposure,
        gain=gain,
        image_type=frame_type,
        context=ctx,
        overwrite=False,
    )
    return _header(str(path))


#: Keys computed from the exposure times: the header keeps DATE-OBS to the
#: millisecond, so a reference rebuilt from it may differ below 1 ms.
_TIME_DERIVED = {"MJD-OBS": 1.2e-8, "MJD-AVG": 1.2e-8, "MOONALT": 1e-4, "MOONSEP": 1e-4,
                 "MOONPHAS": 1e-6}  # fmt: skip


def _assert_same_header(server: fits.Header, reference: fits.Header) -> None:
    assert list(server.keys()) == list(reference.keys())
    for key in reference:
        if key in _TIME_DERIVED:
            assert server[key] == pytest.approx(reference[key], abs=_TIME_DERIVED[key]), key
        else:
            assert server[key] == reference[key], key


def test_save_frame_builds_the_qt_context(tmp_path):
    """Unit parity: the port's FrameContext and file equal the Qt task's, key for key."""
    arr = SimCamera(160, 120, n_stars=40).render(3, 2.0, 80)
    start = datetime(2026, 11, 1, 19, 0, 0, 125000, tzinfo=timezone.utc)
    end = start + timedelta(seconds=2.004)
    reads = {"ccd_temp": 18.5, "egain_driver": None, "offset": 25, "readout_mode": "Normal"}

    class Camera:
        def fits_readings(self):
            return dict(reads)

    pos = FIXED
    frame = FrameSettings(
        exposure_s=2.0, gain=80, frame_type="light", filter="LP", object_name="SS Cyg",
        light=True, origin="single", save=True, started_utc=None,
    )  # fmt: skip
    job = SaveJob(
        arr=arr,
        start=start,
        end=end,
        frame=frame,
        frame_seq=7,
        sessions_path=tmp_path / "server",
        pointing=Pointing(pos.ra_hours, pos.dec_deg, pos.alt_deg, pos.az_deg),
        target=(21.71, 43.59),
        site=(48.8566, 2.3522, 35.0),
        observer="J. Perret",
        camera=Camera(),
        wheel=None,
        egain_table={"80": 1.9},
    )
    result = save_frame(job, lambda level, message: None)
    reference = _qt_reference(
        arr, start, end, exposure=2.0, gain=80, frame_type="Light Frame", object_name="SS Cyg",
        filter_name="LP", pos=pos, target=(21.71, 43.59), site=(48.8566, 2.3522, 35.0),
        observer="J. Perret", camera_reads=reads, path=tmp_path / "qt.fit",
        egain_table={"80": 1.9},
    )  # fmt: skip
    _assert_same_header(_header(str(result.path)), reference)
    assert _header(str(result.path))["EGAIN"] == 1.9  # S42: the table's, as the errors use
    np.testing.assert_array_equal(_data(str(result.path)), arr)


def test_server_take_shot_matches_the_qt_engine(make_client, tmp_path, monkeypatch):
    """End to end: a Take shot through the routes equals the Qt engine's file for the
    same inputs (frame, times read back from DATE-OBS / DATE-AVG, a fixed mount)."""
    _fixed_mount(monkeypatch)
    client = science_client(
        make_client, tmp_path, connect=("mount", "camera", "filterwheel", "focuser")
    )
    client.patch("/api/config", json={**PARIS, "observer.name": "J. Perret"}, headers=AUTH)
    client.post("/api/mount/unpark", headers=AUTH)
    client.post("/api/mount/goto", json={"ra_hours": 21.71268, "dec_deg": 43.58612}, headers=AUTH)
    client.put("/api/observation", json={"object_name": "SS Cyg"}, headers=AUTH)
    client.put("/api/camera/settings", json={"filter": "LP", "gain": 100}, headers=AUTH)
    wait_for(lambda: status(client)["filterwheel"]["slot"] == "LP")
    _shot(client, exposure_s=0.2)
    saved = _saved(client)[0]
    server = _header(saved["path"])
    arr = _data(saved["path"])
    start = datetime.fromisoformat(server["DATE-OBS"]).replace(tzinfo=timezone.utc)
    mid = datetime.fromisoformat(server["DATE-AVG"]).replace(tzinfo=timezone.utc)
    end = start + 2 * (mid - start)
    reference = _qt_reference(
        arr, start, end, exposure=0.2, gain=100, frame_type="Light Frame", object_name="SS Cyg",
        filter_name="LP", pos=FIXED, target=(21.71268, 43.58612),
        site=(48.8566, 2.3522, 35.0), observer="J. Perret",
        camera_reads={"ccd_temp": 21.0, "egain_driver": None, "offset": 10,
                      "readout_mode": None},
        path=tmp_path / "qt.fit",
    )  # fmt: skip
    _assert_same_header(server, reference)
    for key in ("RA", "DEC", "ALTITUDE", "AZIMUTH", "AIRMASS", "SITELAT", "MOONALT", "TARGRA"):
        assert key in server, key


# ---------------------------------------------------------------------------
# S1: Dark / Bias need the wheel settled on Dark
# ---------------------------------------------------------------------------


def test_dark_take_shot_moves_the_wheel_to_dark_first(science):
    assert status(science)["filterwheel"]["slot"] == "IR"
    hub = science.app.state.hub
    state = _shot(science, exposure_s=0.05, frame_type="dark")
    assert state["waiting_for"] == "filterwheel" and state["owner"] == "single"
    _idle(science)
    saved = _saved(science)[0]
    header = _header(saved["path"])
    assert header["IMAGETYP"] == "Dark Frame" and header["FILTER"] == "Dark"
    assert Path(saved["path"]).parent.name == "darks"
    # The pixels are dark: the wheel's Dark slot blocked the light.
    assert abs(float(np.median(_data(saved["path"]))) - PEDESTAL_ADU) < 5
    assert hub._camera.light_flags[-1] is False  # Light=False with StartExposure
    messages = log_messages(science)
    assert "Filter → Dark for the Dark Frame (the Seestar has no shutter)." in messages
    assert status(science)["camera"]["settings"]["filter"] == "Dark"  # follows the wheel (S3)


def test_bias_take_shot_on_the_dark_slot_needs_no_move(science):
    science.post("/api/filterwheel/select", json={"name": "Dark"}, headers=AUTH)
    wait_for(lambda: status(science)["filterwheel"]["slot"] == "Dark")
    state = _shot(science, exposure_s=0.01, frame_type="bias")
    assert state["waiting_for"] is None
    header = _header(_saved(science)[0]["path"])
    assert header["IMAGETYP"] == "Bias Frame" and header["FILTER"] == "Dark"


def test_dark_without_a_wheel_is_taken_with_a_warning(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera",))
    _shot(client, exposure_s=0.02, frame_type="dark")
    header = _header(_saved(client)[0]["path"])
    assert header["IMAGETYP"] == "Dark Frame"
    assert (
        "Dark Frame: no filter wheel to block the light — the frame is only dark if the "
        "telescope is covered." in log_messages(client)
    )


def test_dark_while_the_wheel_moves_elsewhere_is_busy(science, monkeypatch):
    science.app.state.hub._sim_optics.wheel._slot_s = 2.0  # a slow wheel
    science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    response = science.post(
        "/api/camera/capture", json={"frame_type": "dark", "save": True}, headers=AUTH
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "busy" and error["owner"] == "filterwheel"


def test_a_pending_dark_is_dropped_if_the_wheel_leaves_dark(science):
    """S1 review (``test_dark_shot_is_dropped_if_the_wheel_leaves_the_dark_slot``)."""
    science.post("/api/filterwheel/select", json={"name": "Dark"}, headers=AUTH)
    wait_for(lambda: status(science)["filterwheel"]["slot"] == "Dark")
    science.put("/api/camera/settings", json={"frame_type": "dark"}, headers=AUTH)
    science.post("/api/camera/live", json={"exposure_s": 0.3}, headers=AUTH)
    _shot(science, frame_type="dark")
    # The wheel leaves Dark during the in-flight exposure.
    science.post("/api/filterwheel/select", json={"name": "IR"}, headers=AUTH)
    wait_for(lambda: status(science)["camera"]["save_pending"] == 0, timeout=5)
    science.post("/api/camera/stop", headers=AUTH)
    assert science.get("/api/camera/saved", headers=AUTH).json()["saves"] == []
    assert "Dark Frame shot not saved: the filter wheel reports 'IR', not 'Dark'." in log_messages(
        science
    )


# ---------------------------------------------------------------------------
# S2: the header describes the settings the frame was exposed with
# ---------------------------------------------------------------------------


def test_live_take_shot_saves_the_in_flight_frame_with_its_own_settings(science):
    with science.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        science.post("/api/camera/live", json={"exposure_s": 0.4, "gain": 80}, headers=AUTH)
        decode_frame(receive_bytes(frames))  # one frame done: the next one is exposing
        time.sleep(0.05)
        _shot(science)  # tags the in-flight frame
        # Changed during that exposure: applies to the NEXT frame only.
        science.put("/api/camera/settings", json={"exposure_s": 0.05, "gain": 120}, headers=AUTH)
        saved = _saved(science)[0]
    science.post("/api/camera/stop", headers=AUTH)
    header = _header(saved["path"])
    assert header["EXPTIME"] == 0.4 and header["GAIN"] == 80  # 0.4.2 wrote the new values
    assert saved["exposure_s"] == 0.4 and saved["gain"] == 80


def test_live_take_shot_of_another_type_waits_for_a_frame_of_that_type(science):
    science.post("/api/camera/live", json={"exposure_s": 0.2}, headers=AUTH)
    time.sleep(0.05)
    science.post("/api/camera/capture", json={"frame_type": "flat", "save": True}, headers=AUTH)
    saved = _saved(science)[0]
    science.post("/api/camera/stop", headers=AUTH)
    assert _header(saved["path"])["IMAGETYP"] == "Flat Frame"
    assert any("saving the next Flat Frame instead" in m for m in log_messages(science))


# ---------------------------------------------------------------------------
# S3: FILTER read back; never a frame exposed while the wheel turned
# ---------------------------------------------------------------------------


def test_filter_is_read_back_from_the_wheel(science):
    hub = science.app.state.hub
    with hub._lock:  # the form says LP, the wheel is on IR (a move made elsewhere)
        hub._capture_settings = hub._capture_settings.__class__(
            **{**hub._capture_settings.to_dict(), "filter": "LP"}
        )
    _shot(science, exposure_s=0.02)
    header = _header(_saved(science)[0]["path"])
    assert header["FILTER"] == "IR"
    assert (
        "The wheel is on 'IR', not on the form's 'LP' — FITS FILTER records 'IR'."
        in log_messages(science)
    )


def test_wheel_filter_name_rules():
    """``_wheel_filter_name`` (acquisition_engine.py:154-180), every branch."""
    lines: list[tuple[str, str]] = []

    def log(level, message):
        lines.append((level, message))

    class Wheel:
        def __init__(self, answer):
            self.answer = answer

        def position_name(self):
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer

    assert wheel_filter_name(None, "IR", log) == "IR" and lines == []
    assert wheel_filter_name(Wheel("LP"), "LP", log) == "LP" and lines == []
    assert wheel_filter_name(Wheel("LP"), "IR", log) == "LP" and lines[-1][0] == "warning"
    assert wheel_filter_name(Wheel("Moving…"), "IR", log) == "IR"
    assert "still moving" in lines[-1][1]
    assert wheel_filter_name(Wheel(RuntimeError("timeout")), "IR", log) == "IR"
    assert "read-back failed" in lines[-1][1]


def test_never_saves_a_frame_exposed_while_the_wheel_turned(science):
    science.app.state.hub._sim_optics.wheel._slot_s = 0.1
    with science.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        science.post("/api/camera/live", json={"exposure_s": 0.4}, headers=AUTH)
        decode_frame(receive_bytes(frames))
        time.sleep(0.05)
        _shot(science)
        science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
        saved = _saved(science)[0]
    science.post("/api/camera/stop", headers=AUTH)
    header = _header(saved["path"])
    assert header["FILTER"] == "LP"  # the slot of the whole exposure
    started = datetime.fromisoformat(header["DATE-OBS"]).replace(tzinfo=timezone.utc)
    settled = status(science)["filterwheel"]["settled_utc"]
    assert started > datetime.fromisoformat(settled.replace("Z", "+00:00"))
    assert (
        "Take shot: the filter wheel moved during this exposure — saving the next frame "
        "instead." in log_messages(science)
    )


# ---------------------------------------------------------------------------
# S20: QA headers measured on the saved array
# ---------------------------------------------------------------------------


def test_qa_headers_describe_the_saved_frame(science):
    _shot(science, exposure_s=1.0)
    path = _saved(science)[0]["path"]
    header, arr = _header(path), _data(path)
    metrics, field = frame_metrics(arr), detect_stars(arr)
    assert header["HFD"] == round(metrics.hfd, 2)
    assert header["NSTARS"] == metrics.star_count
    assert header["SKYLEVEL"] == round(metrics.sky_adu, 1)
    assert header["FWHM"] == round(field.mean_fwhm, 2)
    assert header["ECCENTR"] == round(field.mean_eccentricity, 3)


# ---------------------------------------------------------------------------
# X1: pointing only from a live mount; X2: the site only when set
# ---------------------------------------------------------------------------


def test_no_pointing_without_a_mount(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera",))
    _shot(client, exposure_s=0.02)
    header = _header(_saved(client)[0]["path"])
    for key in ("RA", "DEC", "OBJCTRA", "OBJCTDEC", "ALTITUDE", "AZIMUTH", "AIRMASS"):
        assert key not in header, key


def test_a_disconnected_mounts_pointing_is_forgotten(science, monkeypatch):
    _fixed_mount(monkeypatch)
    science.delete("/api/devices/mount", headers=AUTH)
    science.post("/api/devices/mount/connect", json={"mode": "simulator"}, headers=AUTH)
    _shot(science, exposure_s=0.02)
    assert _header(_saved(science)[0]["path"])["ALTITUDE"] == FIXED.alt_deg
    science.delete("/api/devices/mount", headers=AUTH)
    _idle(science)
    _shot(science, exposure_s=0.02)
    header = _header(_saved(science, 2)[1]["path"])
    for key in ("RA", "DEC", "ALTITUDE", "AZIMUTH", "AIRMASS"):
        assert key not in header, key


def test_a_lost_mount_gives_no_pointing(make_client, tmp_path, monkeypatch):
    calls = {"n": 0}

    def flaky(self):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("no route to host")
        return FIXED

    monkeypatch.setattr(SimMount, "read", flaky)
    client = science_client(
        make_client, tmp_path, connect=("mount", "camera"), mount_lost_after=1,
        mount_retry_s=30.0,
    )  # fmt: skip
    wait_for(lambda: status(client)["devices"]["mount"]["retrying"], timeout=5)
    _shot(client, exposure_s=0.02)
    header = _header(_saved(client)[0]["path"])
    assert "ALTITUDE" not in header and "AIRMASS" not in header


def test_no_site_means_no_site_headers(science):
    _shot(science, exposure_s=0.02)
    header = _header(_saved(science)[0]["path"])
    for key in ("SITELAT", "SITELONG", "SITEELEV", "MOONALT"):
        assert key not in header, key  # never 0/0 (X2)
    science.patch("/api/config", json=PARIS, headers=AUTH)
    _idle(science)
    _shot(science, exposure_s=0.02)
    header = _header(_saved(science, 2)[1]["path"])
    assert header["SITELAT"] == 48.8566 and header["SITELONG"] == 2.3522


# ---------------------------------------------------------------------------
# Ownership and refusals
# ---------------------------------------------------------------------------


def test_take_shot_needs_a_camera(make_client, tmp_path):
    client = science_client(make_client, tmp_path)
    response = client.post("/api/camera/capture", json={"save": True}, headers=AUTH)
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_connected"


def test_a_second_take_shot_while_one_waits_is_busy(science):
    science.post("/api/camera/live", json={"exposure_s": 0.5}, headers=AUTH)
    _shot(science)
    second = science.post("/api/camera/capture", json={"save": True}, headers=AUTH)
    assert second.status_code == 409 and second.json()["error"]["code"] == "busy"
    science.post("/api/camera/stop", headers=AUTH)


def test_stop_cancels_a_pending_take_shot(science):
    _shot(science, exposure_s=5.0)
    stopped = science.post("/api/camera/stop", headers=AUTH).json()
    assert stopped["save_pending"] == 0 and stopped["owner"] == "idle"
    time.sleep(0.2)
    assert science.get("/api/camera/saved", headers=AUTH).json()["saves"] == []


def test_a_binned_take_shot_is_refused(science):
    """fits_writer writes XBINNING = 1: a binned frame would carry false metadata."""
    hub = science.app.state.hub
    with hub._lock:
        hub._capture_settings = hub._capture_settings.__class__(
            **{**hub._capture_settings.to_dict(), "binning": 2}
        )
    answer = science.post("/api/camera/capture", json={"save": True}, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "unsupported"


# ---------------------------------------------------------------------------
# Review of wave 3: Light behind Dark, snapshot after the wheel, offset / binning
# ---------------------------------------------------------------------------


def test_a_light_or_flat_shot_through_the_dark_slot_is_refused(science):
    """The server turned the wheel to Dark for the darks; a light frame there is pedestal."""
    _shot(science, exposure_s=0.02, frame_type="dark")
    _idle(science)
    for frame_type in ("light", "flat"):
        answer = science.post(
            "/api/camera/capture", json={"frame_type": frame_type, "save": True}, headers=AUTH
        )
        assert answer.status_code == 409, answer.text
        error = answer.json()["error"]
        assert error["code"] == "dark_slot" and "which blocks the light" in error["message"]
    assert len(_saved(science)) == 1  # only the dark


def test_a_light_shot_waiting_for_the_wheel_records_the_new_filter(science):
    """The snapshot is taken once the wheel has settled (frame header and conditions row)."""
    science.app.state.hub._sim_optics.wheel._slot_s = 0.3
    science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    _shot(science, exposure_s=0.02, frame_type="light")
    saved = _saved(science)[0]
    assert saved["filter"] == "LP" and _header(saved["path"])["FILTER"] == "LP"
    rows = wait_for(
        lambda: science.get("/api/session/conditions", headers=AUTH).json()["rows"], timeout=5
    )
    assert rows[-1]["filter"] == "LP"
    assert not any("not on the form's" in m for m in log_messages(science))


def test_offset_and_binning_cannot_change_while_a_take_shot_waits(science):
    science.post("/api/camera/live", json={"exposure_s": 0.5}, headers=AUTH)
    _shot(science)
    for body in ({"offset": 30}, {"binning": 1, "offset": 31}):
        answer = science.put("/api/camera/settings", json=body, headers=AUTH)
        assert answer.status_code == 409, answer.text
        assert "A Take shot is waiting for its frame" in answer.json()["error"]["message"]
    _saved(science)
    science.post("/api/camera/stop", headers=AUTH)
    assert status(science)["camera"]["settings"]["offset"] == 10


def test_a_frame_exposed_across_an_offset_change_is_not_saved(science):
    """FITS OFFSET is read at save time: the frame in progress must not carry the new one."""
    with science.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        science.post("/api/camera/live", json={"exposure_s": 0.4}, headers=AUTH)
        decode_frame(receive_bytes(frames))  # the next frame is exposing
        time.sleep(0.05)
        changed = science.put("/api/camera/settings", json={"offset": 30}, headers=AUTH)
        assert changed.status_code == 200
        _shot(science)  # the frame in progress started before the change
        saved = _saved(science)[0]
    science.post("/api/camera/stop", headers=AUTH)
    header = _header(saved["path"])
    assert header["OFFSET"] == 30
    assert any("the offset or binning changed during this exposure" in m
               for m in log_messages(science))  # fmt: skip


def test_the_settings_put_is_one_commit_when_the_wheel_is_busy(science):
    hub = science.app.state.hub
    hub._sim_optics.wheel._slot_s = 2.0
    science.post("/api/filterwheel/select", json={"name": "LP"}, headers=AUTH)
    answer = science.put("/api/camera/settings", json={"offset": 30, "filter": "IR"}, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["owner"] == "filterwheel"
    assert hub._camera.get_offset() == 10  # nothing reached the driver
    assert status(science)["camera"]["settings"]["offset"] == 10


def test_a_live_take_shot_says_when_the_frame_differs_from_the_request(science):
    science.post("/api/camera/live", json={"exposure_s": 0.3, "gain": 80}, headers=AUTH)
    time.sleep(0.05)
    _shot(science, gain=120)  # applies from the next frame; the frame in progress is saved
    saved = _saved(science)[0]
    science.post("/api/camera/stop", headers=AUTH)
    assert _header(saved["path"])["GAIN"] == 80
    assert any(
        "saving the frame in progress, exposed 0.3 s at gain 80 (the shot asked 0.3 s at gain 120)"
        in m
        for m in log_messages(science)
    )
