"""SessionDiagnostics — the P11 flight recorder (Qt-free)."""

from __future__ import annotations

import json

from argos.core.session.diagnostics import SessionDiagnostics


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_records_are_one_json_per_line(tmp_path) -> None:
    p = tmp_path / "diag.jsonl"
    with SessionDiagnostics(p) as diag:
        diag.record("event", what="start", object="TST Tau")
        diag.record("frame", frame=0, jd_utc=2460000.123456789, airmass=1.2345678)
    docs = _lines(p)
    assert [d["kind"] for d in docs] == ["event", "frame"]
    assert docs[0]["what"] == "start"
    assert docs[1]["frame"] == 0
    # Floats are rounded to keep the file small; timestamps present everywhere.
    assert docs[1]["jd_utc"] == 2460000.1235
    assert all("t" in d for d in docs)


def test_none_fields_are_dropped(tmp_path) -> None:
    p = tmp_path / "diag.jsonl"
    with SessionDiagnostics(p) as diag:
        diag.record("frame", frame=3, airmass=None, fwhm=2.5)
    (doc,) = _lines(p)
    assert "airmass" not in doc and doc["fwhm"] == 2.5


def test_disabled_recorder_writes_nothing(tmp_path) -> None:
    p = tmp_path / "diag.jsonl"
    with SessionDiagnostics(p, enabled=False) as diag:
        diag.record("event", what="start")
    assert not p.exists()


def test_unused_recorder_leaves_no_file(tmp_path) -> None:
    p = tmp_path / "diag.jsonl"
    SessionDiagnostics(p).close()
    assert not p.exists()


def test_write_failure_disables_quietly(tmp_path) -> None:
    # A directory where the file should be → open() fails → recorder disables
    # itself instead of raising into the session.
    p = tmp_path / "diag.jsonl"
    p.mkdir()
    diag = SessionDiagnostics(p)
    diag.record("event", what="start")  # must not raise
    assert not diag.enabled
    diag.record("event", what="more")  # no-op, still no raise
    diag.close()


def test_star_record_carries_the_raw_measurement(tmp_path) -> None:
    from argos.core.catalog.targets import ROLE_COMPARISON, TargetStar
    from argos.core.photometry.aperture import AperturePhot

    star = TargetStar(role=ROLE_COMPARISON, ra_deg=1.0, dec_deg=2.0, auid="C1")
    phot = AperturePhot(
        flux_adu=1234.5,
        sky_adu=200.0,
        n_pix=50,
        peak_adu=900.0,
        snr=42.0,
        saturated=False,
        inst_mag=-7.729,
        inst_mag_err=0.026,
    )
    p = tmp_path / "diag.jsonl"
    with SessionDiagnostics(p) as diag:
        diag.star(7, star, phot, 30.25, 40.75)
        diag.star(8, star, None, 30.25, 40.75)  # aperture off-frame
    measured, lost = _lines(p)
    assert measured["kind"] == "star" and measured["frame"] == 7
    assert measured["auid"] == "C1" and measured["role"] == ROLE_COMPARISON
    assert measured["inst_mag"] == -7.729 and measured["measured"] is True
    assert lost["measured"] is False and "inst_mag" not in lost
