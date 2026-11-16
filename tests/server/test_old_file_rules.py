"""S66, S67, S68 in Review, the exports and the re-run (release/0.5.0's core rules).

S66 (owner's option b): each Argos frame's header ``AIRMASS`` is used, whatever the
Settings site, unless its pointing is frozen (X1); the site check warns. S67: the points of a frame without a detection in the run's flight
recorder are flagged suspect and left out of the AAVSO export, ``sigma_syst``
recomputed without them. S68: a VSP answer names the chart of comparisons kept without
one. The server calls the core's own rules, so its files are the fixed Qt's byte for
byte. GUARD: the core functions arrive with the merge of release/0.5.0; until then
these tests are skipped (the guard-off behaviour is the other tests').
"""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import pytest
from astropy.io import fits

from argos.core.catalog.targets import TargetSet, TargetStar, comparison_chart_id
from argos.core.imaging.sky_geometry import compute_airmass, horizontal_at
from argos.core.photometry.airmass import julian_date
from argos.core.photometry.lightcurve import (
    read_curves_csv,
    write_aavso,
    write_curves_csv,
)
from argos.core.photometry.uncertainty import apply_systematic_floor, estimate_systematic_floor
from argos.server import rerun as rerun_module
from argos.server.review import core_rules
from tests.server.conftest import AUTH
from tests.server.test_exports import OBSCODE, _preview, _source, run_job
from tests.server.test_review_sessions import CADENCE_S, START, make_session

pytestmark = pytest.mark.skipif(
    core_rules() is None, reason="GUARD: needs release/0.5.0's core (S66, S67, S68)"
)
FAR_SITE = (-30.0, 150.0)  # the Settings site of another trip (made up)


@pytest.fixture
def client_root(client, tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    response = client.patch(
        "/api/config",
        json={"sessions_path": str(root), "observer.obscode": OBSCODE},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    client.root = root  # type: ignore[attr-defined]
    client.hub = client.app.state.hub  # type: ignore[attr-defined]
    return client


def _qt_session_curves(path: Path):
    """Qt's Review: ``load_session_curves`` (the core reader, which applies the rules)."""
    core = core_rules()
    return core.load_session_curves(core.load_session(path, read_temperature=False))


def _qt_aavso(curves, path: Path, out: Path) -> None:
    """The Photometry window's Export AAVSO on Review's curves (photometry_window.py)."""
    targets = TargetSet.load(path / "targets.json")
    write_aavso(
        out,
        [lc for lc in curves.values() if lc.points],
        obscode=OBSCODE,
        filt="TG",
        chart=comparison_chart_id(targets.stars),
    )


def _export(client, body, out: Path) -> dict:
    job = run_job(
        client, client.post("/api/export/aavso", json={**body, "path": str(out)}, headers=AUTH)
    )
    assert job["state"] == "done", job
    return job["result"]


_SCATTER = (0.015, -0.025, 0.005, 0.03, -0.01, -0.02, 0.025, -0.005, 0.01, -0.03, 0.02, -0.015)


def _automatic_floors(path: Path, blank: int = 2) -> None:
    """Rewrite the run's CSVs with some scatter, the target measured on blank sky at frame
    ``blank``, and the live path's automatic floor over all points."""
    for csv_path in (path / "photometry").glob("*.csv"):
        (lc,) = read_curves_csv(csv_path).values()
        for i, p in enumerate(lc.points):
            p.mag += _SCATTER[i % len(_SCATTER)] + (
                1.4 if i == blank and lc.role == "target" else 0
            )
        floor = estimate_systematic_floor([(p.jd_utc, p.mag, p.formal_mag_err) for p in lc.points])
        for p in lc.points:
            p.mag_err = apply_systematic_floor(p.formal_mag_err, floor)
            p.sigma_syst = floor.sigma_systematic
        lc.to_csv(csv_path)


def test_a_wrong_site_s_curves_and_report_take_the_header_airmass_s66(client_root, tmp_path):
    path = make_session(client_root.root, header_site=FAR_SITE, recorder=False)
    curves = client_root.get(
        "/api/review/session/curves", params={"path": str(path)}, headers=AUTH
    ).json()
    assert (curves["airmass_source"], curves["airmass_column"]) == ("header", "header")
    target = next(c for c in curves["curves"] if c["role"] == "target")
    assert target["columns"]["airmass"] == [1.2] * 4  # the frames' header AIRMASS
    assert curves["old_file_rules"]["airmass_from_header"] == 12  # 3 curves x 4 points
    record = client_root.get("/api/review/session", params={"path": str(path)}, headers=AUTH).json()
    issue = next(i for i in record["readiness"]["issues"] if i["code"] == "site_mismatch")
    assert "S66" in issue["message"] and "header" in issue["message"]

    preview = _preview(client_root, source=_source(path))
    assert preview["airmass"]["source"] == "header" and "S66" in preview["airmass"]["message"]
    out = client_root.root / "server.txt"
    _export(client_root, {"source": _source(path)}, out)
    reference = tmp_path / "qt.txt"
    _qt_aavso(_qt_session_curves(path), path, reference)
    assert out.read_bytes() == reference.read_bytes()
    rows = [ln.split(",") for ln in out.read_text().splitlines() if not ln.startswith("#")]
    assert {row[11] for row in rows} == {"1.200"}


def test_a_right_site_s_curves_take_the_header_airmass_too_s66(client_root, tmp_path):
    """S66 option (b): the header AIRMASS whatever the site check says (the CSV's was
    computed for the Settings site, off by up to 0.015 under the 5° tolerance); no site
    warning, and the report is Qt Review's byte for byte."""
    path = make_session(client_root.root, recorder=False)  # the right site
    curves = client_root.get(
        "/api/review/session/curves", params={"path": str(path)}, headers=AUTH
    ).json()
    assert (curves["airmass_source"], curves["airmass_column"]) == ("csv", "header")
    target = next(c for c in curves["curves"] if c["role"] == "target")
    assert target["columns"]["airmass"] == [1.2] * 4
    assert curves["old_file_rules"]["airmass_computed"] == 0
    record = client_root.get("/api/review/session", params={"path": str(path)}, headers=AUTH).json()
    assert "site_mismatch" not in {i["code"] for i in record["readiness"]["issues"]}
    preview = _preview(client_root, source=_source(path))
    assert "airmass_wrong_site" not in {w["code"] for w in preview["warnings"]}
    out = client_root.root / "server.txt"
    _export(client_root, {"source": _source(path)}, out)
    reference = tmp_path / "qt.txt"
    _qt_aavso(_qt_session_curves(path), path, reference)
    assert out.read_bytes() == reference.read_bytes()


def test_a_no_detection_frame_is_left_out_named_and_sigma_syst_recomputed_s67(
    client_root, tmp_path
):
    path = make_session(client_root.root, filters=("V",) * 12)  # recorder: frame 2 blank
    _automatic_floors(path)
    written = {
        p.name: read_curves_csv(p) for p in sorted((path / "photometry").glob("target_*.csv"))
    }
    (before,) = {p.sigma_syst for lc in next(iter(written.values())).values() for p in lc.points}

    curves = client_root.get(
        "/api/review/session/curves", params={"path": str(path)}, headers=AUTH
    ).json()
    target = next(c for c in curves["curves"] if c["role"] == "target")
    cols = target["columns"]
    assert [i for i, f in enumerate(cols["flags"]) if "no_detection" in f] == [2]
    assert cols["suspect"][2] is True
    (after,) = set(cols["sigma_syst"])
    assert after != before
    assert curves["old_file_rules"]["sigma_syst"]["XX Test"] == [before, after]

    preview = _preview(client_root, source=_source(path))
    assert preview["excluded"]["no_detection"] == 1 and preview["excluded"]["suspect"] == 1
    assert preview["rows"] == 10 and preview["recorder_flagged"] == 0
    assert any("1 suspect (no detection), 1 suspect" in n for n in preview["notes"])

    out = client_root.root / "server.txt"
    result = _export(client_root, {"source": _source(path)}, out)
    assert result["excluded"]["no_detection"] == 1
    assert "1 suspect (no detection)" in result["notes"][0]
    qt = _qt_session_curves(path)
    reference = tmp_path / "qt.txt"
    _qt_aavso(qt, path, reference)
    assert out.read_bytes() == reference.read_bytes()
    # A79: the measurements export is write_curves_csv over Review's curves, as Qt's.
    csv_out = client_root.root / "server.csv"
    job = run_job(
        client_root,
        client_root.post(
            "/api/export/csv", json={"source": _source(path), "path": str(csv_out)}, headers=AUTH
        ),
    )
    assert job["state"] == "done", job
    csv_ref = tmp_path / "qt.csv"
    write_curves_csv(csv_ref, [lc for lc in qt.values() if lc.points])
    assert csv_out.read_bytes() == csv_ref.read_bytes()


def test_a_run_csv_imported_alone_gets_the_rules_as_analyze_s66_s67(client_root, tmp_path):
    path = make_session(client_root.root, header_site=FAR_SITE)
    csv_path = path / "photometry" / "target_XX_Test_v_000-AAA-001.csv"
    source = {"kind": "import", "path": str(csv_path)}
    imported = client_root.post(
        "/api/review/import-csv", json={"path": str(csv_path)}, headers=AUTH
    ).json()
    assert imported["airmass_column"] == "header"
    (target,) = imported["curves"]
    assert target["columns"]["airmass"] == [1.2] * 4
    assert "no_detection" in target["columns"]["flags"][2]

    out = client_root.root / "server.txt"
    _export(client_root, {"source": source}, out)
    # Analyze's Open curve CSV: read, identify, the session's rules, Export AAVSO.
    core = core_rules()
    targets = TargetSet.load(path / "targets.json")
    curves, problems = core.identify_curve_file(csv_path, read_curves_csv(csv_path), targets)
    assert not problems and core.apply_old_file_rules_to_file(csv_path, curves) is not None
    reference = tmp_path / "qt.txt"
    write_aavso(
        reference,
        [lc for lc in curves.values() if lc.points],
        obscode=OBSCODE,
        filt="TG",
        chart=comparison_chart_id(targets.stars),
    )
    assert out.read_bytes() == reference.read_bytes()


def _pointing_frames(
    session: Path, n: int, header_site, frozen_after: int | None = None
) -> list[Path]:
    """test_rerun's frames with the headers Argos writes: where the mount pointed from
    the true site (test_review_sessions.SITE), and ``header_site`` as SITELAT/SITELONG.
    ``frozen_after``: later frames keep that frame's pointing keys and AIRMASS (X1)."""
    from tests.server import test_rerun as tr
    from tests.server.test_review_sessions import SITE

    paths = []
    for i in range(n):
        path = session / "lights" / f"XX_Test_ir_light_{i + 1:05d}.fit"
        tr._write(path, i)
        with fits.open(path, mode="update") as hdul:
            h = hdul[0].header
            when = START + timedelta(seconds=22 * i)
            ra_h, dec = tr.TARGET.ra_deg / 15.0, tr.TARGET.dec_deg
            alt, az = horizontal_at(julian_date(when), ra_h, dec, *SITE)
            h["RA"], h["DEC"] = ra_h, dec
            h["ALTITUDE"], h["AZIMUTH"] = alt, az
            h["AIRMASS"] = round(compute_airmass(alt), 4)
            h["SITELAT"], h["SITELONG"] = header_site
            h["SOFTWARE"] = "Argos v0.4.2"
            if frozen_after is not None and i > frozen_after:
                polled = fits.getheader(paths[frozen_after])
                for key in ("RA", "DEC", "ALTITUDE", "AZIMUTH", "AIRMASS"):
                    h[key] = polled[key]
        paths.append(path)
    return paths


def _qt_batch(request, out: Path):
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from argos.workers import photometry_batch_worker as qt_worker
    from tests.server import test_rerun as tr

    tr._QT.append(QApplication.instance() or QApplication([]))
    box = []
    qt = qt_worker.PhotometryBatchWorker(tr.qt_request(qt_worker, request(out)))
    qt.finished_batch.connect(box.append)
    qt.run()
    return box[0]


def test_a_re_run_at_the_right_site_takes_the_header_airmass_unless_frozen_s66(tmp_path, caplog):
    """S66 option (b): a right Settings site's computed airmass gave way to the frame's
    header AIRMASS too (under the 5° tolerance the site still erred by up to 0.015). A
    frozen frame (X1: a minute or more after the frame whose pointing it keeps) is
    computed for the site, as before. No site WARN; Qt's worker writes the same bytes."""
    from argos.core.photometry.airmass import airmass_at
    from tests.server import test_rerun as tr
    from tests.server.test_review_sessions import SITE

    session = tmp_path / "session"
    (session / "lights").mkdir(parents=True)
    paths = _pointing_frames(session, 6, SITE, frozen_after=1)  # 22 s apart
    header_airmass = [fits.getheader(p)["AIRMASS"] for p in paths]

    def request(out):
        req = tr._request(paths, out)
        req.site = (*SITE, 0.0)
        return req

    with caplog.at_level("WARNING"):
        server = rerun_module.BatchRun(request(tmp_path / "server")).run()
    assert server.ok and (server.frames_header_airmass, server.frames_site_wrong) == (4, 0)
    target = server.curves["000-AAA-001@ir"].points
    assert [p.airmass for p in target[:4]] == header_airmass[:4]  # 0-44 s after the poll
    star = tr.TARGET
    assert [p.airmass for p in target[4:]] == [
        airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, *SITE) for p in target[4:]
    ]
    assert not [r for r in caplog.records if "not where the telescope" in r.getMessage()]

    qt = _qt_batch(request, tmp_path / "qt")
    assert (qt.frames_header_airmass, qt.frames_site_wrong) == (4, 0)
    names = sorted(p.name for p in (tmp_path / "qt").glob("*.csv"))
    assert names == sorted(p.name for p in (tmp_path / "server").glob("*.csv"))
    for name in names:
        assert (tmp_path / "server" / name).read_bytes() == (tmp_path / "qt" / name).read_bytes()


def test_a_re_run_on_a_wrong_settings_site_takes_the_header_airmass_s66(tmp_path, caplog):
    """The request's site is FAR_SITE, the frames say the mount was at SITE: every point's
    airmass is its frame's header AIRMASS, one WARN, one note; Qt's worker writes the
    same bytes."""
    from tests.server import test_rerun as tr

    session = tmp_path / "session"
    (session / "lights").mkdir(parents=True)
    paths = _pointing_frames(session, 4, FAR_SITE)
    header_airmass = [fits.getheader(p)["AIRMASS"] for p in paths]

    def request(out):
        req = tr._request(paths, out)
        req.site = (*FAR_SITE, 0.0)
        return req

    with caplog.at_level("WARNING"):
        server = rerun_module.BatchRun(request(tmp_path / "server")).run()
    assert server.ok and (server.frames_header_airmass, server.frames_site_wrong) == (4, 4)
    for lc in server.curves.values():
        assert [p.airmass for p in lc.points] == header_airmass
    assert len([r for r in caplog.records if "not where the telescope" in r.getMessage()]) == 1
    notes = rerun_module.RerunService._notes(server, 4, tmp_path / "server", True)
    assert any("S66" in text for _level, text in notes)

    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from argos.workers import photometry_batch_worker as qt_worker

    tr._QT.append(QApplication.instance() or QApplication([]))
    box = []
    qt = qt_worker.PhotometryBatchWorker(tr.qt_request(qt_worker, request(tmp_path / "qt")))
    qt.finished_batch.connect(box.append)
    qt.run()
    names = sorted(p.name for p in (tmp_path / "qt").glob("*.csv"))
    assert names == sorted(p.name for p in (tmp_path / "server").glob("*.csv"))
    for name in names:
        assert (tmp_path / "server" / name).read_bytes() == (tmp_path / "qt" / name).read_bytes()


def test_a_vsp_answer_names_the_chart_of_comparisons_kept_without_one_s68(client_root):
    from argos.core.catalog.aavso import Band, ComparisonStar

    hub = client_root.hub
    tset, path = hub.targets._current()
    TargetSet(
        object_name=tset.object_name,
        stars=[
            TargetStar("target", 300.0, 22.5, auid="000-AAA-000", name="V1", source="vsx"),
            TargetStar(
                "comparison", 300.1, 22.4, auid="000-AAA-001", source="vsp_auto", mags={"V": 11.4}
            ),
        ],
    ).save(path)
    hub.targets.reload()
    answer = [ComparisonStar("000-AAA-001", 300.1, 22.4, "114", (Band("V", 11.4),), chart_id="X7")]

    assert hub.targets.backfill_chart_ids(answer) == 1  # TargetService's own (was field.py's)

    assert [s.chart_id for s in TargetSet.load(path).by_role("comparison")] == ["X7"]
    record = hub.targets.record()
    assert [s["chart_id"] for s in record["stars"] if s["role"] == "comparison"] == ["X7"]
    assert hub.targets.backfill_chart_ids(answer) == 0


def test_rules_keep_a_floor_that_is_not_the_automatic_one(client_root):
    """make_session writes sigma_syst 0.016 on every row (not the estimate of its points):
    the point is flagged, the floor kept (S67 recomputes only the automatic floor)."""
    path = make_session(client_root.root)
    curves = client_root.get(
        "/api/review/session/curves", params={"path": str(path)}, headers=AUTH
    ).json()
    target = next(c for c in curves["curves"] if c["role"] == "target")
    assert set(target["columns"]["sigma_syst"]) == {0.016}
    assert target["columns"]["suspect"][2] is True
    assert math.isclose(target["columns"]["mag_err"][0], 0.02)
    assert CADENCE_S > 5  # the frames are farther apart than the 5 s airmass match
