"""Tests for the per-session QA log (§7) — Qt-free, no hardware."""

from __future__ import annotations

import json

from argos.core.imaging.session_log import (
    SESSION_SCHEMA,
    FrameRecord,
    SessionLog,
)


def _record(idx: int, image_type: str = "Light Frame", **kw) -> FrameRecord:
    base = dict(
        filename=f"M42_Light_{idx:04d}.fits",
        image_type=image_type,
        filter_name="LRGB",
        exposure_s=10.0,
        gain=80,
        timestamp="2026-06-14T22:00:00+00:00",
        hfd=3.0 + idx * 0.1,
        fwhm=2.5,
        star_count=120 + idx,
        sky_adu=510.0,
        peak_adu=40000,
        eccentricity=0.2,
    )
    base.update(kw)
    return FrameRecord(**base)


def test_to_dict_structure() -> None:
    log = SessionLog(object_name="M42", software="Argos", started_utc="2026-06-14T22:00:00")
    log.add(_record(1))
    log.add(_record(2))
    doc = log.to_dict()
    assert doc["schema"] == SESSION_SCHEMA
    assert doc["object"] == "M42"
    assert len(doc["frames"]) == 2
    assert doc["frames"][0]["filename"] == "M42_Light_0001.fits"
    assert doc["summary"]["frame_count"] == 2
    assert doc["summary"]["light_count"] == 2


def test_summary_means_over_lights_only() -> None:
    log = SessionLog(object_name="M42")
    log.add(_record(1, hfd=3.0, star_count=100))
    log.add(_record(2, hfd=5.0, star_count=200))
    log.add(_record(3, image_type="Dark Frame", hfd=None, star_count=None))
    summary = log.summary()
    assert summary["light_count"] == 2
    assert summary["mean_hfd"] == 4.0
    assert summary["mean_star_count"] == 150


def test_write_is_valid_json_and_roundtrips(tmp_path) -> None:
    log = SessionLog(object_name="T CrB", started_utc="2026-06-14T22:00:00")
    log.add(_record(1))
    path = tmp_path / "sessions" / "20260614_TCrB" / "session.json"
    log.write(path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["object"] == "T CrB"
    assert data["frames"][0]["fwhm"] == 2.5
    # No stray temp file left behind.
    assert not (path.parent / "session.json.tmp").exists()


def test_write_is_atomic_overwrite(tmp_path) -> None:
    path = tmp_path / "session.json"
    log = SessionLog(object_name="M42")
    log.add(_record(1))
    log.write(path)
    log.add(_record(2))
    log.write(path)  # overwrite in place
    data = json.loads(path.read_text())
    assert len(data["frames"]) == 2
