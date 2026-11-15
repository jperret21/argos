"""Wave 7, Review on the owner's recorded sessions (APFS clones; skipped when absent).

XX Cyg 2026-08-29 and 2026-09-07, RR Lyr 2026-09-25: the curves Review serves are
Qt's ``load_session_curves`` point for point (the parity reference, needs PyQt6);
the frame links, the times against the headers, the site check and the S35 flags
are checked against what the files say. No personal metadata is printed: header
comparisons report key names only.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from argos.server.files import FileService, read_fits_2d
from argos.server.review import open_session, read_recorder
from tests.server.test_review_sessions import assert_curves_equal_qt


def _owner_sessions() -> Path:
    """``$ARGOS_OWNER_SESSIONS``, else ``~/Argos/sessions`` of the real home (the suite
    runs with a temporary ``HOME``)."""
    override = os.environ.get("ARGOS_OWNER_SESSIONS")
    if override:
        return Path(override)
    try:
        import pwd

        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError):  # pragma: no cover - not POSIX
        home = Path.home()
    return home / "Argos" / "sessions"


SESSIONS = _owner_sessions()
OWNER = {
    "xx_cyg_0829": "20260829T050148Z_XX_Cyg",
    "xx_cyg_0907": "20260907T040723Z_XX_Cyg",
    "rr_lyr_0925": "20260925T200453Z_RR_Lyr",
}


def _clone(name: str, tmp_path_factory) -> Path:
    source = SESSIONS / name
    if not (source / "session.json").is_file():
        pytest.skip(f"the owner's session {name} is not on this machine")
    if sys.platform != "darwin":
        pytest.skip("APFS clones (cp -c) are macOS only")
    target = tmp_path_factory.mktemp("owner") / name
    subprocess.run(["cp", "-cR", str(source), str(target)], check=True)
    return target


@pytest.fixture(scope="module", params=sorted(OWNER))
def owner_session(request, tmp_path_factory):
    path = _clone(OWNER[request.param], tmp_path_factory)
    return request.param, path, open_session(path)


def test_curves_are_qts(owner_session):
    pytest.importorskip("PyQt6.QtCore")
    from argos.core.session import review as qt_review

    _key, path, data = owner_session
    assert_curves_equal_qt(data.curves, path)
    qt = qt_review.load_session(path, read_temperature=True)
    assert data.record["warnings"] == qt.warnings
    assert [f["ccd_temp"] for f in data.record["frames"]] == [f.ccd_temp for f in qt.frames]


def test_points_sit_on_their_frames(owner_session):
    """Every point is its light frame's header mid-exposure (DATE-OBS + EXPTIME/2, S39)."""
    _key, _path, data = owner_session
    for curve in data.curves.curves:
        assert None not in curve.frame, curve.key
        assert all(abs(dt) < 0.01 for dt in curve.frame_dt_s), curve.key
        assert curve.filter == "ir" and curve.filter_source == "session"
        assert curve.key.endswith("@ir")
    roles = sorted({c.lc.role for c in data.curves.curves})
    assert roles == ["comparison", "target"]  # the owner's runs have no check star


def test_site_and_flags(owner_session):
    key, _path, data = owner_session
    record = data.record
    frames = record["frames"]
    target = next(c for c in data.curves.curves if c.lc.role == "target")
    no_detection = {"low_snr", "zp_outlier"}
    flagged = {
        frames[i]["filename"] for i, f in zip(target.frame, target.flags) if set(f) & no_detection
    }
    # S56's old-file rule (notes: "flags every frame of XX Cyg 2026-08-29 050148Z (22) ...
    # and RR Lyr 2026-09-25 200453Z frames 52 and 175").
    unverified = {
        frames[i]["filename"] for i, f in zip(target.frame, target.flags) if "few_anchors" in f
    }
    if key == "rr_lyr_0925":
        # The wrong Settings site of that night (release X3) and the two blank-sky
        # points of S35 (lights _00053 and _00176).
        assert record["site_check"]["state"] == "mismatch"
        assert record["site_check"]["median_deg"] > 80.0
        assert record["airmass_source"] == "header"
        assert {name[-9:] for name in flagged} == {"00053.fit", "00176.fit"}
        assert {name[-9:] for name in unverified} == {"00053.fit", "00176.fit"}
        assert target.lc.points[0].airmass == pytest.approx(4.088)  # the CSV as written
        assert 1.0 < min(target.header_airmass) < max(target.header_airmass) < 1.4
    else:
        assert record["site_check"]["state"] == "ok"
        assert record["site_check"]["max_deg"] < 5.0
        assert record["airmass_source"] == "csv"
    if key == "xx_cyg_0829":
        assert flagged == set()
        assert len(unverified) == 22 == len(target.lc.points)
        # The two target files of that run (an AUID and an alias) are one curve.
        assert sum(1 for c in data.curves.curves if c.lc.role == "target") == 1


def test_header_and_measure_equal_qt(owner_session):
    pytest.importorskip("PyQt6.QtWidgets")
    from argos.core.imaging.metrics import measure_star_at
    from argos.ui.analysis_window import read_fits_2d as qt_read_fits_2d
    from argos.ui.analysis_window import read_fits_meta as qt_read_fits_meta

    key, path, data = owner_session
    if key != "rr_lyr_0925":
        pytest.skip("one frame of one session is enough for the per-file parity")
    frame = data.record["frames"][0]
    fits_path = Path(frame["path"])

    class Hub:
        class config:
            @staticmethod
            def get(_key, default=None):
                return default

        @staticmethod
        def _star_radius():
            return 5

    service = FileService(Hub())  # type: ignore[arg-type]
    service.resolve = lambda raw: Path(raw)  # type: ignore[method-assign]
    ours = service.header(str(fits_path))["keywords"]
    qt = qt_read_fits_meta(str(fits_path))
    assert sorted(ours) == sorted(qt)
    assert [k for k in qt if ours[k] != qt[k]] == []
    arr = read_fits_2d(fits_path)
    assert (arr == qt_read_fits_2d(str(fits_path))).all()
    recorder = read_recorder(next((path / "diagnostics").glob("*.jsonl")))
    star = next(s for s in recorder[0].stars if s["role"] == "target")
    gx, gy = float(star["x"]), float(star["y"])
    mine = service.measure(str(fits_path), 2 * gx + 0.5, 2 * gy + 0.5)
    core = measure_star_at(qt_read_fits_2d(str(fits_path)), gx, gy, 5)
    assert mine["found"] and core is not None
    assert (mine["x_green"], mine["y_green"]) == (core.x, core.y)
    assert (mine["fwhm_px"], mine["hfd_px"]) == (2 * core.fwhm, 2 * core.hfd)
    assert (mine["snr"], mine["peak_adu"], mine["sky_adu"]) == (
        core.snr,
        core.peak_adu,
        core.sky_adu,
    )
