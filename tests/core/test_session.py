"""session.json roundtrip + permissiveness."""

from __future__ import annotations

import json
from pathlib import Path

from seercontrol.core.imaging.session import (
    SCHEMA_VERSION,
    Session,
    load_session_json,
    write_session_json,
)
from seercontrol.core.targets.resolver import Target


def _make_target() -> Target:
    return Target(
        name="M 42", queried_name="M42",
        ra_hours=5.59, dec_degrees=-5.39,
        object_type="HII", magnitude=4.0,
    )


def test_session_records_frames_and_finalizes(tmp_path: Path) -> None:
    s = Session.from_target(
        _make_target(),
        profile_name="Deep sky — wide",
        profile_summary="60×60s LRGB",
        frames_planned=2,
    )
    assert s.finished_at_utc is None
    s.record_frame(tmp_path / "f1.fits")
    s.record_frame(tmp_path / "f2.fits")
    s.finish()
    assert s.frames_acquired == 2
    assert s.finished_at_utc is not None


def test_session_json_roundtrip_preserves_all_fields(tmp_path: Path) -> None:
    s = Session.from_target(
        _make_target(),
        profile_name="P",
        profile_summary="2×10s",
        frames_planned=2,
        observer="JP",
        site_lat=48.85, site_lon=2.35, site_elev=35.0,
    )
    s.weather = {"clouds_pct": 5}
    s.notes = "First-light test of T CrB monitoring run."
    s.record_frame(tmp_path / "frame.fits")
    s.finish()

    written = write_session_json(tmp_path, s)
    assert written.is_file()

    reborn = load_session_json(tmp_path)
    assert reborn is not None
    assert reborn.target_name == "M 42"
    assert reborn.frames_acquired == 1
    assert reborn.weather["clouds_pct"] == 5
    assert reborn.notes.startswith("First-light")
    assert reborn.schema_version == SCHEMA_VERSION
    assert reborn.finished_at_utc is not None


def test_load_session_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_session_json(tmp_path) is None


def test_load_session_accepts_old_iso_timestamps(tmp_path: Path) -> None:
    """The strict ms-precision format is preferred but isoformat() must still parse."""
    payload = {
        "target_name": "X", "target_ra_hours": 0.0, "target_dec_degrees": 0.0,
        "started_at_utc": "2026-05-29T22:30:00",
        "finished_at_utc": "2026-05-29T22:35:00",
        "frames_planned": 0, "frames_acquired": 0, "frames_paths": [],
    }
    (tmp_path / "session.json").write_text(json.dumps(payload))
    s = load_session_json(tmp_path)
    assert s is not None
    assert s.started_at_utc.year == 2026
    assert s.finished_at_utc is not None


def test_load_session_tolerates_missing_optional_fields(tmp_path: Path) -> None:
    minimal = {"target_name": "X", "target_ra_hours": 0.0, "target_dec_degrees": 0.0}
    (tmp_path / "session.json").write_text(json.dumps(minimal))
    s = load_session_json(tmp_path)
    assert s is not None
    assert s.observer == ""
    assert s.site_lat is None
    assert s.target_magnitude is None
