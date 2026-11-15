"""Wave 7, Review: AAVSO and CSV exports (rows A77-A79).

Synthetic sessions (``test_review_sessions.make_session``) read through the
sessions backend's curve set. The files must be the fixed core writers' output
as Qt's Review drives them: Analyze **Open curve CSV** then the Photometry
window's **Export AAVSO** / **Export measurements** (driven for real where PyQt6
is installed).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from argos.core.catalog.targets import TargetSet, comparison_chart_id
from argos.core.photometry.lightcurve import (
    LcPoint,
    LightCurve,
    read_curves_csv,
    write_aavso,
    write_curves_csv,
)
from argos.server.review import core_review
from tests.server.conftest import AUTH, wait_for
from tests.server.test_review_sessions import make_session

OBSCODE = "ZZZ01"  # a fake observer code
_QT: list = []  # the QApplication of the Qt parity test, never garbage-collected


@pytest.fixture
def export_client(client, tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    response = client.patch(
        "/api/config",
        json={"sessions_path": str(root), "observer.obscode": OBSCODE},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    client.root = root  # type: ignore[attr-defined]
    return client


def run_job(client, response, timeout: float = 10.0) -> dict:
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    def finished():
        job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        return job if job["state"] in ("done", "failed", "cancelled") else None

    return wait_for(finished, timeout=timeout)


def _source(path: Path) -> dict:
    return {"kind": "session", "path": str(path)}


def _preview(client, **body) -> dict:
    response = client.post("/api/export/aavso/preview", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _qt_reference(csv_paths: list[Path], out: Path, *, obscode=OBSCODE, filt="TG") -> None:
    """``write_aavso`` as Analyze's Open curve CSV + Export AAVSO call it (core chain)."""
    core = core_review()
    curves: dict = {}
    for path in csv_paths:
        targets = TargetSet.load(path.parent.parent / "targets.json")
        identified, problems = core.identify_curve_file(path, read_curves_csv(path), targets)
        assert not problems
        curves.update(identified)
    write_aavso(
        out,
        [lc for lc in curves.values() if lc.points],
        obscode=obscode,
        filt=filt,
        chart=comparison_chart_id(targets.stars),
    )


# ---------------------------------------------------------------------------
# A77: preview
# ---------------------------------------------------------------------------


def test_preview_counts_rows_check_star_and_chart(export_client):
    session = make_session(export_client.root, recorder=False)
    record = _preview(export_client, source=_source(session))
    assert record["refusal"] is None
    assert (record["obscode"], record["obscode_set"]) == (OBSCODE, True)
    assert (record["band"], record["band_source"]) == ("TG", "settings")
    assert record["filter"] == "v" and record["filters"] == ["v"]
    assert record["band_note"] == "The frames were taken through the V filter but FILT is TG."
    assert (record["chart"], record["chart_source"]) == ("X1", "targets")
    (target,) = record["targets"]
    assert target["key"] == "000-AAA-001@v" and target["points"] == 4
    assert (target["rows"], target["suspect"], target["saturated"]) == (3, 1, 0)
    assert record["rows"] == 3 and record["excluded"]["suspect"] == 1
    assert record["check"]["kname"] == "000-AAA-003" and record["check"]["kmag_rows"] == 3
    head = record["head"].splitlines()
    assert head[:2] == ["#TYPE=EXTENDED", f"#OBSCODE={OBSCODE}"]
    assert len([ln for ln in head if not ln.startswith("#")]) == 3
    assert record["default_path"] == str(session / "XX_Test_v_aavso.txt")
    assert any("1 suspect" in note for note in record["notes"])
    assert record["airmass"]["state"] == "ok"


def test_preview_refuses_without_observer_code(export_client):
    session = make_session(export_client.root, recorder=False)
    for code in ("", "xxx"):
        record = _preview(export_client, source=_source(session), obscode=code)
        assert record["refusal"]["code"] == "obscode_unset"
        assert record["obscode_set"] is False
        assert "#OBSCODE=XXX" in record["head"]  # the preview shows what Qt used to write
    response = export_client.post(
        "/api/export/aavso", json={"source": _source(session), "obscode": " "}, headers=AUTH
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "obscode_unset"


def test_two_filters_need_a_choice_and_the_check_of_that_filter_s53(export_client):
    session = make_session(export_client.root, filters=("V", "B", "V", "B"), recorder=False)
    record = _preview(export_client, source=_source(session))
    assert record["refusal"]["code"] == "multiple_filters"
    assert record["refusal"]["details"]["filters"] == ["b", "v"]
    record = _preview(export_client, source=_source(session), filter="b", filt="B")
    assert record["refusal"] is None and record["band_note"] is None
    assert record["check"]["key"] == "000-AAA-003@b"
    rows = [ln for ln in record["head"].splitlines() if not ln.startswith("#")]
    assert all(",B,NO,STD," in row for row in rows)
    wrong = _preview(export_client, source=_source(session), filter="b", check_key="000-AAA-003@v")
    assert wrong["refusal"]["code"] == "unknown_curve"


def test_unidentified_curve_is_refused_s10(export_client):
    session = make_session(export_client.root, recorder=False)
    stray = session / "photometry" / "target_XX_Test_v_000-ZZZ-999.csv"
    stray.write_text(next((session / "photometry").glob("target_*.csv")).read_text())
    curves = export_client.get(
        "/api/review/session/curves", params={"path": str(session)}, headers=AUTH
    ).json()["curves"]
    (unknown,) = [c for c in curves if c["problem"]]
    assert not unknown["exportable"]
    # Every target curve (the default) includes the unknown one: refused, as Qt's
    # Open curve CSV disables Export AAVSO for that file.
    record = _preview(export_client, source=_source(session))
    assert record["refusal"]["code"] == "curve_unidentified"
    record = _preview(export_client, source=_source(session), keys=[unknown["key"]])
    assert record["refusal"]["code"] == "curve_unidentified"
    record = _preview(export_client, source=_source(session), keys=["000-AAA-001@v"])
    assert record["refusal"] is None and record["rows"] == 3


def test_airmass_from_a_wrong_site_is_said(export_client):
    session = make_session(export_client.root, header_site=(-30.0, 150.0), recorder=False)
    record = _preview(export_client, source=_source(session))
    assert record["airmass"]["state"] == "mismatch"
    assert "wrong" in record["airmass"]["message"]
    assert record["refusal"] is None  # still exported (owner decision pending)


def test_recorder_flagged_points_are_said_not_dropped(export_client):
    """The flight recorder marks frame 2 as blank sky (target SNR 1.5, zero point 5 mag
    off). The fixed Qt export writes it (it reads the CSV only); the preview counts it
    and says so while the owner decides (protocol.md "Flight-recorder flags")."""
    session = make_session(export_client.root)  # with the recorder
    record = _preview(export_client, source=_source(session))
    (target,) = record["targets"]
    assert target["recorder_flagged"] == [2] and record["recorder_flagged"] == 1
    assert record["rows"] == 3  # still written: 4 points, 1 suspect left out
    (warning,) = record["warnings"]
    assert warning["code"] == "recorder_flagged" and "flight recorder" in warning["message"]
    assert [p["index"] for p in record["flagged_points"]] == [2]


# ---------------------------------------------------------------------------
# A78: export, byte for byte the Qt writer's
# ---------------------------------------------------------------------------


def test_export_is_qts_file_byte_for_byte(export_client, tmp_path):
    session = make_session(export_client.root, recorder=False)
    out = session / "XX_Test_v_aavso.txt"
    job = run_job(
        export_client,
        export_client.post(
            "/api/export/aavso",
            json={"source": _source(session), "path": str(out), "use_check": False},
            headers=AUTH,
        ),
    )
    assert job["state"] == "done", job
    result = job["result"]
    assert (result["rows"], result["download"], result["path"]) == (3, False, str(out))
    assert result["excluded"]["suspect"] == 1
    reference = tmp_path / "qt.txt"
    _qt_reference(sorted((session / "photometry").glob("target_*.csv")), reference)
    assert out.read_bytes() == reference.read_bytes()

    again = export_client.post(
        "/api/export/aavso", json={"source": _source(session), "path": str(out)}, headers=AUTH
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "file_exists"


def test_export_with_check_star_equals_qt_on_the_measurements_export(export_client, tmp_path):
    """KNAME/KMAG in Qt's Review: Export measurements (target + check), Open curve CSV
    on that file, Export AAVSO. The server writes the same file from the session."""
    session = make_session(export_client.root, recorder=False)
    out = export_client.root / "aavso.txt"  # inside the folders ARGOS may write
    job = run_job(
        export_client,
        export_client.post(
            "/api/export/aavso",
            json={"source": _source(session), "path": str(out)},
            headers=AUTH,
        ),
    )
    assert job["state"] == "done", job
    core = core_review()
    targets = TargetSet.load(session / "targets.json")
    picked = []
    for name in ("target_XX_Test_v_000-AAA-001.csv", "check_XX_Test_v_000-AAA-003.csv"):
        path = session / "photometry" / name
        picked += list(core.identify_curve_file(path, read_curves_csv(path), targets)[0].values())
    measurements = tmp_path / "photometry.csv"
    write_curves_csv(measurements, picked)
    reloaded = read_curves_csv(measurements)
    reference = tmp_path / "qt.txt"
    write_aavso(
        reference,
        list(reloaded.values()),
        obscode=OBSCODE,
        filt="TG",
        chart=comparison_chart_id(targets.stars),
    )
    assert out.read_bytes() == reference.read_bytes()
    rows = [ln.split(",") for ln in out.read_text().splitlines() if not ln.startswith("#")]
    assert {(r[9], r[13]) for r in rows} == {("000-AAA-003", "X1")}


def test_export_for_a_download(export_client):
    session = make_session(export_client.root, recorder=False)
    job = run_job(
        export_client,
        export_client.post("/api/export/aavso", json={"source": _source(session)}, headers=AUTH),
    )
    assert job["state"] == "done" and job["result"]["download"] is True
    assert job["result"]["path"] is None and job["result"]["name"] == "XX_Test_v_aavso.txt"
    response = export_client.get(f"/api/jobs/{job['id']}/download", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.startswith("#TYPE=EXTENDED\n")
    assert not list(session.glob("*.txt"))  # nothing written into the session


def test_undated_points_are_left_out_s60(export_client, tmp_path):
    """A pre-0.5.0 batch CSV dated a frame without DATE-OBS at JD 0 (S13)."""
    folder = export_client.root / "batch"
    folder.mkdir()
    tset = TargetSet.load(make_session(export_client.root, recorder=False) / "targets.json")
    tset.save(folder / "targets.json")
    lc = LightCurve()
    lc.append(LcPoint(jd_utc=2461309.34, mag=7.3, mag_err=0.02))
    lc.append(LcPoint(jd_utc=0.0, mag=7.4, mag_err=0.02))
    csv_path = folder / "target_XX_Test_000-AAA-001.csv"
    lc.to_csv(csv_path)
    record = _preview(export_client, source={"kind": "import", "path": str(csv_path)})
    assert record["refusal"] is None
    assert record["rows"] == 1 and record["excluded"]["undated"] == 1
    rows = [ln for ln in record["head"].splitlines() if not ln.startswith("#")]
    assert len(rows) == 1 and ",0.000000," not in rows[0]
    assert any("1 undated (JD 0)" in note for note in record["notes"])


def test_every_point_left_out_is_refused(export_client):
    session = make_session(export_client.root, recorder=False)
    path = session / "photometry" / "target_XX_Test_v_000-AAA-001.csv"
    lc = LightCurve.from_csv(path)
    for p in lc.points:
        p.saturated = True
    lc.to_csv(path)
    record = _preview(export_client, source=_source(session))
    assert record["refusal"]["code"] == "no_rows"
    assert record["excluded"]["saturated"] == 4


# ---------------------------------------------------------------------------
# A79: CSV
# ---------------------------------------------------------------------------


def test_csv_export_is_write_curves_csv(export_client, tmp_path):
    session = make_session(export_client.root, recorder=False)
    out = export_client.root / "photometry.csv"
    keys = ["000-AAA-001@v", "000-AAA-003@v"]
    job = run_job(
        export_client,
        export_client.post(
            "/api/export/csv",
            json={"source": _source(session), "keys": keys, "path": str(out)},
            headers=AUTH,
        ),
    )
    assert job["state"] == "done", job
    assert (job["result"]["rows"], job["result"]["curves"]) == (8, 2)
    core = core_review()
    targets = TargetSet.load(session / "targets.json")
    picked = []
    for name in ("target_XX_Test_v_000-AAA-001.csv", "check_XX_Test_v_000-AAA-003.csv"):
        path = session / "photometry" / name
        picked += list(core.identify_curve_file(path, read_curves_csv(path), targets)[0].values())
    reference = tmp_path / "qt.csv"
    write_curves_csv(reference, picked)
    assert out.read_bytes() == reference.read_bytes()


def test_csv_export_refuses_two_filters_s61(export_client):
    session = make_session(export_client.root, filters=("V", "B", "V", "B"), recorder=False)
    response = export_client.post(
        "/api/export/csv", json={"source": _source(session)}, headers=AUTH
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "multiple_filters"
    job = run_job(
        export_client,
        export_client.post(
            "/api/export/csv", json={"source": _source(session), "filter": "v"}, headers=AUTH
        ),
    )
    assert job["state"] == "done" and job["result"]["curves"] == 3


# ---------------------------------------------------------------------------
# Parity with Qt's Review driven for real (PyQt6)
# ---------------------------------------------------------------------------


def test_export_equals_the_qt_review_window(export_client, tmp_path, monkeypatch):
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _QT.append(QApplication.instance() or QApplication([]))  # kept alive for the widget
    import argos.ui.panels.photometry_window as pw
    from argos.ui.pages import analyze_page

    session = make_session(export_client.root, recorder=False)
    csv_path = session / "photometry" / "target_XX_Test_v_000-AAA-001.csv"
    qt_out = tmp_path / "qt.txt"
    monkeypatch.setattr(pw.QFileDialog, "getSaveFileName", lambda *a, **k: (str(qt_out), ""))
    monkeypatch.setattr(pw.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(pw.QMessageBox, "warning", lambda *a, **k: None)
    # analyze_page._open_lightcurve, step by step (its dialogs replaced).
    curves = read_curves_csv(csv_path)
    targets = analyze_page._target_set_of_curve(csv_path)
    curves, problems = analyze_page.identify_curve_file(csv_path, curves, targets)
    assert not problems
    window = pw.PhotometryWindow()
    try:
        window.load_curves(curves, obscode=OBSCODE, filt="TG")
        window.set_targets(targets.stars)
        window._export_aavso()
    finally:
        window.close()
        window.deleteLater()
    out = export_client.root / "server.txt"
    job = run_job(
        export_client,
        export_client.post(
            "/api/export/aavso",
            json={
                "source": {"kind": "import", "path": str(csv_path)},
                "path": str(out),
            },
            headers=AUTH,
        ),
    )
    assert job["state"] == "done", job
    assert out.read_bytes() == qt_out.read_bytes()


def test_an_export_never_replaces_the_session_s_own_files(export_client):
    """An export to <session>/photometry/target_….csv with overwrite replaced the raw
    curve by a multi-curve export (W7 technical review): refused, 409 protected_path."""
    session = make_session(export_client.root, recorder=False)
    source_csv = next((session / "photometry").glob("target_*.csv"))
    before = source_csv.read_bytes()
    for path in (source_csv, session / "photometry" / "new.csv", session / "targets.json.csv"):
        answer = export_client.post(
            "/api/export/csv",
            json={"source": _source(session), "path": str(path), "overwrite": True},
            headers=AUTH,
        )
        if path.name == "targets.json.csv":
            assert answer.status_code == 202  # beside the record, not the record: allowed
            run_job(export_client, answer)
            continue
        assert answer.status_code == 409, answer.text
        assert answer.json()["error"]["code"] == "protected_path"
    assert source_csv.read_bytes() == before
    aavso = export_client.post(
        "/api/export/aavso",
        json={"source": _source(session), "path": str(session / "session.json.txt")},
        headers=AUTH,
    )
    assert aavso.status_code in (202, 409)  # obscode refusals may come first; never protected
    assert aavso.json().get("error", {}).get("code") != "protected_path"


def test_protected_reason_inside_a_session(tmp_path):
    from argos.server.exports import protected_reason

    session = tmp_path / "s"
    (session / "photometry").mkdir(parents=True)
    (session / "session.json").write_text("{}")
    assert protected_reason(session / "session.json", []) is not None
    assert protected_reason(session / "targets.json", []) is not None
    assert protected_reason(session / "photometry" / "x.csv", []) is not None
    assert protected_reason(session / "photometry_rerun_20261115T000000Z" / "x.csv", []) is not None
    assert protected_reason(session / "RR_Lyr_ir_aavso.txt", []) is None
    other = tmp_path / "loose.csv"
    assert protected_reason(other, [other]) is not None and protected_reason(other, []) is None
