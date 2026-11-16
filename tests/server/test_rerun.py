"""Wave 7, Review: re-run photometry over a session's saved frames (row A76).

Synthetic sessions: frames painted with stars where a real TAN solution puts the
target set. ASTAP is replaced by that solution (the reference solve) so the suite
needs no solver; the server's port is compared with the Qt worker it ports where
PyQt6 is installed (byte-identical CSVs).
"""

from __future__ import annotations

import json
import math
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.platesolve import FrameWCS
from argos.core.photometry.params import PhotometryParams
from argos.server import rerun as rerun_module
from argos.server.rerun import (
    BatchRequest,
    BatchRun,
    discover_light_frames,
    rerun_output_dir,
)
from tests.server.conftest import AUTH, wait_for

START = datetime(2026, 9, 25, 20, 4, 56, 567000, tzinfo=timezone.utc)
GREEN = (120, 160)  # green-plane shape (h, w): raw 240 x 320
WCS = FrameWCS(291.30, 42.78, 80.5, 60.5, (-1.0e-3, 0.0, 0.0, 1.0e-3))  # 3.6"/green px

TARGET = TargetStar("target", 291.300, 42.780, auid="000-AAA-001", name="XX Test", source="vsx")
COMPS = [
    TargetStar(
        "comparison",
        291.345,
        42.815,
        auid="000-AAA-002",
        name="101",
        source="vsp",
        mags={"V": 10.1},
        chart_id="X1",
    ),
    TargetStar(
        "comparison",
        291.250,
        42.745,
        auid="000-AAA-003",
        name="103",
        source="vsp",
        mags={"V": 10.3},
        chart_id="X1",
    ),
    TargetStar(
        "comparison",
        291.350,
        42.740,
        auid="000-AAA-004",
        name="105",
        source="vsp",
        mags={"V": 10.5},
        chart_id="X1",
    ),
]
CHECK = TargetStar(
    "check",
    291.255,
    42.820,
    auid="000-AAA-005",
    name="107",
    source="vsp",
    mags={"V": 10.7},
    chart_id="X1",
)
PEAKS = {"000-AAA-001": 9000.0, "000-AAA-002": 12000.0, "000-AAA-003": 10000.0}
PEAKS.update({"000-AAA-004": 8000.0, "000-AAA-005": 7000.0})


def target_set() -> TargetSet:
    tset = TargetSet(object_name="XX Test")
    for star in (TARGET, *COMPS, CHECK):
        tset.set_role(star)
    return tset


def _frame(i: int, shift: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """A raw GRBG frame whose green plane holds the set's stars (seeded noise)."""
    gh, gw = GREEN
    rng = np.random.default_rng(100 + i)
    yy, xx = np.mgrid[0:gh, 0:gw]
    plane = np.zeros(GREEN, dtype=np.float64)
    for star in (TARGET, *COMPS, CHECK):
        x, y = WCS.world_to_pixel_deg(star.ra_deg, star.dec_deg)
        peak = PEAKS[star.auid] * (1.0 + (0.05 * np.sin(i) if star is TARGET else 0.0))
        cx, cy = float(x) + shift[0], float(y) + shift[1]
        plane += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 1.4**2))
    raw = np.full((gh * 2, gw * 2), 300.0)
    raw[0::2, 0::2] += plane
    raw[1::2, 1::2] += plane
    raw += rng.normal(0.0, 6.0, raw.shape)
    return np.clip(raw, 0, 65535).astype(np.uint16)


def _write(path: Path, i: int, *, obj="XX Test", imagetyp="Light Frame", filt="IR", date=True):
    header = fits.Header()
    if date:
        when = START + timedelta(seconds=22 * i)
        header["DATE-OBS"] = when.isoformat(timespec="milliseconds").replace("+00:00", "")
    header["EXPTIME"] = 10.0
    header["IMAGETYP"] = imagetyp
    header["OBJECT"] = obj
    header["FILTER"] = filt
    header["GAIN"] = 80
    header["EGAIN"] = 0.8
    header["OBJCTRA"] = "19 25 12.00"
    header["OBJCTDEC"] = "+42 46 48.0"
    fits.PrimaryHDU(data=_frame(i), header=header).writeto(path)


def make_session(root: Path, n: int = 4, *, folder: str = "20260925T200453Z_XX_Test") -> Path:
    path = root / folder
    (path / "lights").mkdir(parents=True)
    for i in range(n):
        _write(path / "lights" / f"XX_Test_ir_light_{i + 1:05d}.fit", i)
    _write(path / "lights" / "XX_Test_dark_00001.fit", n, imagetyp="Dark Frame")
    (path / "session.json").write_text(
        json.dumps({"schema": 1, "object": "XX Test", "frames": []}), encoding="utf-8"
    )
    target_set().save(path / "targets.json")
    return path


@pytest.fixture
def rerun_client(client, tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    root.mkdir()
    response = client.patch("/api/config", json={"sessions_path": str(root)}, headers=AUTH)
    assert response.status_code == 200, response.text
    hub = client.app.state.hub
    service = hub.rerun
    monkeypatch.setattr(service, "_astap", lambda: True)
    monkeypatch.setattr(service, "_solve_reference", lambda path, ctx: WCS)
    # S43/S58 re-solves: the reference solution (no ASTAP in the suite).
    monkeypatch.setattr(rerun_module, "_frame_solver", lambda *a, **k: (lambda green: WCS))
    client.root = root  # type: ignore[attr-defined]
    client.hub = hub  # type: ignore[attr-defined]
    return client


def run_job(client, response, timeout: float = 30.0) -> dict:
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    def finished():
        job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        return job if job["state"] in ("done", "failed", "cancelled") else None

    return wait_for(finished, timeout=timeout)


# ---------------------------------------------------------------------------
# Frames and folders
# ---------------------------------------------------------------------------


def test_discover_keeps_lights_of_the_object_s12_s62(tmp_path):
    session = make_session(tmp_path, n=2)
    other = tmp_path / "20260925T210000Z_RR_Lyr" / "lights"
    other.mkdir(parents=True)
    _write(other / "RR_Lyr_light_00001.fit", 5, obj="RR Lyr")
    _write(session / "lights" / "XX_Test_light_nodate.fits", 9, date=False)

    selection = discover_light_frames(tmp_path, "XX_Test")
    names = [p.name for p in selection.paths]
    assert names == [
        "XX_Test_ir_light_00001.fit",
        "XX_Test_ir_light_00002.fit",
        "XX_Test_light_nodate.fits",  # undated last (skipped and counted by the run)
    ]
    assert (selection.calibration, selection.other_object) == (1, 1)
    assert len(discover_light_frames(tmp_path).paths) == 4  # no object: every light


def test_a_session_s_frames_are_its_lights_s63(tmp_path):
    """Siril's process/ beside the lights (star_var_script): a link to each light and
    a registered copy with the same cards. The owner's RR Lyr 2026-09-25 folder gave
    585 frames for 195 lights before S63."""
    session = make_session(tmp_path, n=2)
    process = session / "process"
    process.mkdir()
    (process / "light_00001.fit").symlink_to(session / "lights" / "XX_Test_ir_light_00001.fit")
    _write(process / "r_light_00001.fit", 0)
    selection = discover_light_frames(session, "XX Test")
    assert [p.name for p in selection.paths] == [
        "XX_Test_ir_light_00001.fit",
        "XX_Test_ir_light_00002.fit",
    ]
    assert (selection.outside_lights, selection.duplicates, selection.calibration) == (2, 0, 1)
    loose = tmp_path / "loose"  # not a session: every FITS, each file once
    loose.mkdir()
    _write(loose / "a.fit", 0)
    (loose / "b.fit").symlink_to(loose / "a.fit")
    selection = discover_light_frames(loose)
    assert [p.name for p in selection.paths] == ["a.fit"] and selection.duplicates == 1


def test_output_folder_is_new_inside_the_session(tmp_path):
    session = make_session(tmp_path, n=1)
    now = datetime(2026, 11, 15, 10, 0, 0, tzinfo=timezone.utc)
    first = rerun_output_dir(session / "lights", now)
    assert first == session / "photometry_rerun_20261115T100000Z"
    first.mkdir()
    assert rerun_output_dir(session, now).name == "photometry_rerun_20261115T100000Z-2"


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------


def test_plan_says_what_a_start_would_do(rerun_client):
    session = make_session(rerun_client.root)
    plan = rerun_client.post(
        "/api/review/rerun/plan", json={"session": str(session)}, headers=AUTH
    ).json()
    assert plan["frames"] == 4 and plan["left_out"] == {
        "calibration": 1,
        "other_object": 0,
        "outside_lights": 0,
        "duplicates": 0,
    }
    assert plan["stars"] == {"object": "XX Test", "target": 1, "comparison": 3, "check": 1}
    assert plan["reference"]["frame"] == "XX_Test_ir_light_00001.fit"
    assert plan["refusal"] is None
    assert Path(plan["out_dir"]).parent == session
    assert not any(session.glob("photometry_rerun_*"))  # the plan writes nothing


def test_rerun_writes_a_new_folder_in_the_session(rerun_client):
    session = make_session(rerun_client.root)
    job = run_job(
        rerun_client,
        rerun_client.post("/api/review/rerun", json={"session": str(session)}, headers=AUTH),
    )
    assert job["state"] == "done", job
    result = job["result"]
    out = Path(result["out_dir"])
    assert out.parent == session and out.name.startswith("photometry_rerun_")
    assert result["frames_done"] == 4 and result["frames_total"] == 4
    assert result["left_out"]["calibration"] == 1
    files = sorted(p.name for p in out.iterdir())
    assert "targets.json" in files
    assert "target_XX_Test_ir_000-AAA-001.csv" in files
    assert "check_XX_Test_ir_000-AAA-005.csv" in files
    assert {c["role"] for c in result["curves"]} == {"target", "comparison", "check"}
    assert result["source"] == {
        "kind": "import",
        "path": str(out / "target_XX_Test_ir_000-AAA-001.csv"),
    }
    (check,) = result["check_rms"]
    assert check["key"] == "000-AAA-005@ir" and check["n"] == 4
    assert any("frames measured" in note for note in result["notes"])
    # The check star recovers its catalogue magnitude through the ensemble.
    rows = (out / "check_XX_Test_ir_000-AAA-005.csv").read_text().splitlines()[1:]
    mags = [float(r.split(",")[2]) for r in rows]
    assert abs(np.mean(mags) - 10.7) < 0.05

    second = run_job(
        rerun_client,
        rerun_client.post("/api/review/rerun", json={"session": str(session)}, headers=AUTH),
    )
    assert second["state"] == "done"
    assert second["result"]["out_dir"] != result["out_dir"]  # never overwritten
    assert sorted(p.name for p in out.iterdir()) == files


def test_rerun_cancel_writes_nothing(rerun_client, monkeypatch):
    session = make_session(rerun_client.root, n=6)
    gate = threading.Event()
    original = BatchRun._process_frame

    def slow(self, *args, **kwargs):
        gate.wait(5.0)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(BatchRun, "_process_frame", slow)
    response = rerun_client.post("/api/review/rerun", json={"session": str(session)}, headers=AUTH)
    job_id = response.json()["job_id"]
    busy = rerun_client.post("/api/review/rerun", json={"session": str(session)}, headers=AUTH)
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "busy"
    rerun_client.delete(f"/api/jobs/{job_id}", headers=AUTH)
    gate.set()
    job = run_job(rerun_client, response)
    assert job["state"] == "cancelled" and job["result"] is None
    assert not any(session.glob("photometry_rerun_*"))
    assert job["message"].startswith("Cancelled after ") and "no curve saved" in job["message"]


def test_rerun_cancel_keeps_only_the_flight_recorder_and_says_so(rerun_client, monkeypatch):
    # Settings diagnostics on (the owner's): the per-frame notes stay, no curve, and the
    # job's last words say so (the job strip showed the last frame's name, 2026-11-15).
    session = make_session(rerun_client.root, n=6)
    gate = threading.Event()
    original = BatchRun._process_frame

    def slow(self, *args, **kwargs):
        gate.wait(5.0)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(BatchRun, "_process_frame", slow)
    body = {"session": str(session), "diagnostics": True}
    response = rerun_client.post("/api/review/rerun", json=body, headers=AUTH)
    rerun_client.delete(f"/api/jobs/{response.json()['job_id']}", headers=AUTH)
    gate.set()
    job = run_job(rerun_client, response)
    assert job["state"] == "cancelled" and job["result"] is None
    (folder,) = session.glob("photometry_rerun_*")
    assert [p.name.endswith("_diagnostics.jsonl") for p in folder.iterdir()] == [True]
    assert "no curve saved" in job["message"] and f"kept in {folder.name}/" in job["message"]


def test_rerun_refusals(rerun_client, monkeypatch):
    session = make_session(rerun_client.root, n=1)

    def post(**body):
        return rerun_client.post(
            "/api/review/rerun", json={"session": str(session), **body}, headers=AUTH
        )

    empty = rerun_client.root / "empty"
    empty.mkdir()
    response = post(frames=str(empty))
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_frames"
    assert "of XX Test" in response.json()["error"]["message"]

    response = post(reference="live")  # no live field solution
    assert response.json()["error"]["code"] == "not_solved"

    tset = TargetSet(object_name="XX Test")
    tset.set_role(TARGET)
    tset.save(session / "targets.json")
    assert post().json()["error"]["code"] == "no_comparisons"
    (session / "targets.json").unlink()
    assert post().json()["error"]["code"] == "no_targets"

    target_set().save(session / "targets.json")
    monkeypatch.setattr(rerun_client.hub.rerun, "_astap", lambda: False)
    assert post().json()["error"]["code"] == "astap_missing"
    outside = post(frames="/")
    assert outside.status_code == 403


def test_reference_that_does_not_solve_fails_the_job(rerun_client, monkeypatch):
    from argos.server.errors import ApiError

    session = make_session(rerun_client.root, n=1)

    def no_solution(path, ctx):
        raise ApiError(422, "not_solved", f"The reference frame {path.name} did not solve: x")

    monkeypatch.setattr(rerun_client.hub.rerun, "_solve_reference", no_solution)
    job = run_job(
        rerun_client,
        rerun_client.post("/api/review/rerun", json={"session": str(session)}, headers=AUTH),
    )
    assert job["state"] == "failed" and job["error"]["code"] == "not_solved"
    assert not any(session.glob("photometry_rerun_*"))


# ---------------------------------------------------------------------------
# Parity with the Qt worker it ports
# ---------------------------------------------------------------------------


_QT: list = []  # the QApplication of the parity test, never garbage-collected


def _request(paths, out_dir, solver=None, tset=None) -> BatchRequest:
    return BatchRequest(
        fits_paths=list(paths),
        wcs=WCS,
        target_set=tset or target_set(),
        params=PhotometryParams.from_config(lambda k, d: d, egain=0.8),
        out_dir=out_dir,
        object_name="XX Test",
        site=(12.0, 34.0, 100.0),  # a made-up site
        diagnostics=True,
        egain_table={},
        solver=solver,
    )


def _turned_wcs(deg: float) -> FrameWCS:
    """``WCS`` turned ``deg`` about its reference pixel: an alt-az field's rotation."""
    a = math.radians(deg)
    cd = np.array([[WCS.cd[0], WCS.cd[1]], [WCS.cd[2], WCS.cd[3]]])
    turned = cd @ np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
    return FrameWCS(WCS.crval1, WCS.crval2, WCS.crpix1, WCS.crpix2, tuple(turned.ravel()))


#: S69: the turning session's rotation per frame; comparison 105's star 2.5 green px
#: from where its catalogue puts it, too faint to steer the tracker (SNR about 7: not
#: an anchor, but seen), so its aperture is off-centre on every frame.
TURN_DEG = 0.9
OFF_AUID, OFF_PX, OFF_PEAK = "000-AAA-004", 2.5, 170.0


def make_turning_session(root: Path, n: int = 8) -> tuple[Path, dict[bytes, FrameWCS]]:
    """A session whose field turns ``TURN_DEG`` per frame about the frame's centre,
    and each frame's own solution keyed by its green plane (the solver's answer)."""
    from argos.core.imaging.green import green_plane

    path = make_session(root, n=n)
    solutions: dict[bytes, FrameWCS] = {}
    gh, gw = GREEN
    yy, xx = np.mgrid[0:gh, 0:gw]
    for i in range(n):
        wcs = _turned_wcs(-TURN_DEG * i)
        rng = np.random.default_rng(100 + i)
        plane = np.zeros(GREEN, dtype=np.float64)
        for star in (TARGET, *COMPS, CHECK):
            x, y = (float(v) for v in wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg))
            peak = PEAKS[star.auid]
            if star.auid == OFF_AUID:
                x, peak = x + OFF_PX, OFF_PEAK
            plane += peak * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.4**2))
        raw = np.full((gh * 2, gw * 2), 300.0)
        raw[0::2, 0::2] += plane
        raw[1::2, 1::2] += plane
        raw += rng.normal(0.0, 6.0, raw.shape)
        frame = path / "lights" / f"XX_Test_ir_light_{i + 1:05d}.fit"
        with fits.open(frame, mode="update") as hdul:
            hdul[0].data = np.clip(raw, 0, 65535).astype(np.uint16)
            green = green_plane(np.asarray(hdul[0].data, dtype=np.float32))
        solutions[green.tobytes()] = wcs
    return path, solutions


def core_has_s69() -> bool:
    """GUARD (pending merge of release/0.5.0): the core's tracker has S69's centring
    check and rotation rule (``tracking.centring_offsets``, ``rotation_resolve_due``)."""
    from argos.core.photometry import tracking

    return hasattr(tracking, "centring_offsets") and hasattr(tracking, "rotation_resolve_due")


requires_s69_core = pytest.mark.skipif(
    not core_has_s69(), reason="the core has no S69 yet (release/0.5.0 not merged)"
)


@requires_s69_core
def test_a_re_run_re_solves_a_turning_field_and_leaves_an_off_centre_star_out_s69(tmp_path):
    """Release S69: (a) a frame is re-solved once the field turned more than 2° since
    its solution (the tracker carried the reference over all 16.5° of XX Cyg
    2026-09-07); (b) a comparison or check star more than 1 px from its aperture
    centre leaves the frame's ensemble, its row flagged suspect, counted. A failing
    solver is tried once per 2° of rotation, never on every frame."""
    session, solutions = make_turning_session(tmp_path, n=8)
    paths = discover_light_frames(session, "XX Test").paths
    calls: list[int] = []

    def solver(green):
        calls.append(1)
        return solutions[green.tobytes()]

    result = BatchRun(_request(paths, tmp_path / "out", solver)).run()
    assert result.ok and result.frames_done == 8
    assert len(calls) == 2  # at 2.7° (frame 3) and frame 6; none before the port
    target = result.curves["000-AAA-001@ir"].points
    assert all(p.comps_used == 2 for p in target)  # 105 left out (3 before the port)
    assert not any(p.suspect for p in target)
    assert all(p.suspect for p in result.curves[f"{OFF_AUID}@ir"].points)
    assert not any(p.suspect for p in result.curves["000-AAA-005@ir"].points)  # the check
    assert result.frames_rotation_solved == 2
    assert result.stars_off_centre == 8  # comparison 105, every frame
    recorder = (tmp_path / "out" / "XX_Test_diagnostics.jsonl").read_text().splitlines()
    events = [json.loads(line).get("what") for line in recorder]
    assert events.count("re_solved_rotation") == 2

    failed: list[int] = []
    result = BatchRun(_request(paths, tmp_path / "fail", lambda g: failed.append(1))).run()
    assert result.ok and result.frames_rotation_solved == 0
    assert len(failed) == 2  # 2.7° (frame 3), then 5.4° (frame 6): 2° apart, of 5 frames
    # Technical review: counted and said, never worded as flagging the points.
    assert result.frames_rotation_unsolved == 2
    notes = rerun_module.RerunService._notes(result, 8, tmp_path / "fail", True)
    assert any("did not re-solve" in text for _level, text in notes)


def _core_rules_merged() -> bool:
    from argos.server.review import core_rules

    return core_rules() is not None


@pytest.mark.parametrize(
    "case",
    [
        "clouds_s43",
        "two_anchors_s58",
        pytest.param("alt_az_s69", marks=requires_s69_core),
        pytest.param(
            "faint_target_s67",
            marks=pytest.mark.skipif(
                not _core_rules_merged(), reason="GUARD: needs release/0.5.0's S67 rules"
            ),
        ),
    ],
)
def test_server_port_writes_the_qt_workers_bytes(tmp_path, case):
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from argos.workers import photometry_batch_worker as qt_worker

    # A QApplication (not a QCoreApplication): the UI tests reuse the instance.
    _QT.append(QApplication.instance() or QApplication([]))  # kept alive
    session = make_session(tmp_path, n=5)
    tset = None
    solution = WCS
    if case == "clouds_s43":
        # Frame 3 clouded out: the lock check fails, the frame is re-solved (in vain)
        # and flagged; the next frame is re-solved and the apertures re-anchored.
        with fits.open(session / "lights" / "XX_Test_ir_light_00003.fit", mode="update") as hdul:
            hdul[0].data = np.full_like(hdul[0].data, 300)
    elif case == "two_anchors_s58":  # two comparisons, no check: 2 anchors, S58's rule
        tset = TargetSet(object_name="XX Test")
        for star in (TARGET, *COMPS[:2]):
            tset.set_role(star)
    elif case == "faint_target_s67":
        # Frame 3: the target below SNR 3 (at minimum), the field and its zero point fine.
        bright = PEAKS[TARGET.auid]
        PEAKS[TARGET.auid] = 0.0
        try:
            faint = _frame(2)
        finally:
            PEAKS[TARGET.auid] = bright
        with fits.open(session / "lights" / "XX_Test_ir_light_00003.fit", mode="update") as hdul:
            hdul[0].data = faint
    solutions: dict[bytes, FrameWCS] = {}
    if case == "alt_az_s69":
        shutil.rmtree(session)
        session, solutions = make_turning_session(tmp_path, n=8)
    paths = discover_light_frames(session, "XX Test").paths
    calls: list[str] = []

    def solver(green):
        calls.append("x")
        return solutions.get(green.tobytes(), solution)

    server = BatchRun(_request(paths, tmp_path / "server", solver, tset)).run()
    server_calls = len(calls)
    qt = qt_worker.PhotometryBatchWorker(
        qt_worker.BatchRequest(**vars(_request(paths, tmp_path / "qt", solver, tset)))
    )
    box = []
    qt.finished_batch.connect(box.append)
    qt.run()
    (qt_result,) = box
    assert server.ok and qt_result.ok
    counts = ("frames_done", "frames_resolved", "frames_unanchored", "frames_unverified")
    if case == "alt_az_s69":
        counts += ("frames_rotation_solved", "stars_off_centre")
    if case == "faint_target_s67":
        counts += ("frames_no_detection",)
    assert [getattr(server, k) for k in counts] == [getattr(qt_result, k) for k in counts]
    assert server_calls == len(calls) - server_calls  # the solver was used alike...
    assert server_calls > 0 or case == "faint_target_s67"  # ...where a case needs it
    if case == "clouds_s43":
        assert (server.frames_unanchored, server.frames_resolved) == (1, 1)
        flagged = [p.suspect for p in server.curves["000-AAA-001@ir"].points]
        assert flagged == [False, False, False, False]  # no target point on the blank frame
    elif case == "alt_az_s69":
        assert (server.frames_rotation_solved, server.stars_off_centre) == (2, 8)
        recorders = [tmp_path / side / "XX_Test_diagnostics.jsonl" for side in ("server", "qt")]
        stars = [
            [json.loads(line) for line in p.read_text().splitlines() if '"star"' in line]
            for p in recorders
        ]
        keys = ("auid", "x", "y", "snr", "centroid_offset_px", "off_centre")
        assert [[r.get(k) for k in keys] for r in stars[0]] == [
            [r.get(k) for k in keys] for r in stars[1]
        ]
    elif case == "faint_target_s67":
        # S67 in the re-run, per target: only the target's own point is flagged.
        assert server.frames_no_detection == 1
        for key, lc in server.curves.items():
            flagged = [i for i, p in enumerate(lc.points) if p.no_detection]
            assert flagged == ([2] if key == "000-AAA-001@ir" else []), key
    else:
        assert server.frames_unverified == 0 and server_calls >= 2
    names = sorted(p.name for p in (tmp_path / "qt").glob("*.csv"))
    assert names and names == sorted(p.name for p in (tmp_path / "server").glob("*.csv"))
    for name in names:
        assert (tmp_path / "server" / name).read_bytes() == (tmp_path / "qt" / name).read_bytes()
    assert (tmp_path / "server" / "targets.json").read_bytes() == (
        tmp_path / "qt" / "targets.json"
    ).read_bytes()


# ---------------------------------------------------------------------------
# W7 technical review: inputs, output folder, the scan's cost
# ---------------------------------------------------------------------------


def test_plan_refuses_a_reference_that_is_not_a_fits_and_a_file_as_session(rerun_client):
    session = make_session(rerun_client.root)
    bad_ref = rerun_client.post(
        "/api/review/rerun/plan",
        json={"session": str(session), "reference_frame": str(session / "session.json")},
        headers=AUTH,
    )
    assert bad_ref.status_code == 400 and bad_ref.json()["error"]["code"] == "invalid_argument"
    light = next((session / "lights").glob("*_light_*.fit"))
    as_session = rerun_client.post(
        "/api/review/rerun/plan", json={"session": str(light)}, headers=AUTH
    )
    assert as_session.status_code == 400
    assert "is not a session folder" in as_session.json()["error"]["message"]


def test_rerun_of_frames_elsewhere_writes_inside_the_session(rerun_client):
    """protocol A76: a new folder <session>/photometry_rerun_…, also when the frames are in
    another folder (it went into the frames' folder)."""
    session = make_session(rerun_client.root)
    elsewhere = rerun_client.root / "copies"
    elsewhere.mkdir()
    for p in sorted((session / "lights").glob("*_light_*.fit")):
        shutil.copy(p, elsewhere / p.name)
    plan = rerun_client.post(
        "/api/review/rerun/plan",
        json={"session": str(session), "frames": str(elsewhere)},
        headers=AUTH,
    ).json()
    assert plan["frames"] == 4 and Path(plan["out_dir"]).parent == session


def test_the_plan_and_the_start_scan_the_frames_once(rerun_client, monkeypatch):
    """discover_light_frames reads one header per frame (about 4 ms): the dialog's plans
    and the start reuse one scan while no FITS file below changes."""
    session = make_session(rerun_client.root)
    calls = []
    real = rerun_module.discover_light_frames
    monkeypatch.setattr(
        rerun_module, "discover_light_frames", lambda *a, **k: calls.append(a) or real(*a, **k)
    )
    for _ in range(3):
        rerun_client.post("/api/review/rerun/plan", json={"session": str(session)}, headers=AUTH)
    assert len(calls) == 1
    _write(session / "lights" / "XX_Test_ir_light_00009.fit", 9)
    plan = rerun_client.post(
        "/api/review/rerun/plan", json={"session": str(session)}, headers=AUTH
    ).json()
    assert len(calls) == 2 and plan["frames"] == 5
