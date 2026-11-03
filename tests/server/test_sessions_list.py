"""The session list (row A67, list only) against a temporary sessions folder."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from tests.server.conftest import AUTH


def _frame(name: str, image_type: str = "Light Frame", filter_name: str = "IR") -> dict:
    return {
        "filename": name,
        "image_type": image_type,
        "filter_name": filter_name,
        "exposure_s": 10.0,
        "gain": 80,
        "timestamp": "2026-09-25T20:04:56.567116+00:00",
        "hfd": 3.1,
        "fwhm": 2.9,
        "star_count": 812,
        "sky_adu": 2100.0,
        "peak_adu": 41000,
        "eccentricity": 0.2,
    }


def _session(root: Path, folder: str, started: str, frames: list[dict], fits: list[str]) -> Path:
    path = root / folder
    (path / "lights").mkdir(parents=True)
    document = {
        "schema": 1,
        "object": folder.split("_", 1)[1].replace("_", " "),
        "software": "Argos 0.4.2",
        "started_utc": started,
        "observer": "J. Observer",
        "summary": {},
        "frames": frames,
    }
    (path / "session.json").write_text(json.dumps(document), encoding="utf-8")
    for name in fits:
        (path / "lights" / name).write_bytes(b"SIMPLE")
    return path


def _setup(client, tmp_path) -> Path:
    root = tmp_path / "sessions"
    root.mkdir()
    client.patch("/api/config", json={"sessions_path": str(root)}, headers=AUTH)
    rr = _session(
        root,
        "20260925T200453Z_RR_Lyr",
        "2026-09-25T20:04:56.567116+00:00",
        [_frame("rr_0001.fits"), _frame("rr_0002.fits"), _frame("rr_0003.fits", filter_name="")],
        ["rr_0001.fits", "rr_0002.fits"],  # one FITS missing
    )
    (rr / "photometry").mkdir()
    for name in (
        "target_RR_Lyr_000-BCG-719.csv",
        "comparison_RR_Lyr_000-BCG-523.csv",
        "comparison_RR_Lyr_000-BCG-953.csv",
        "check_RR_Lyr_000-BJW-665.csv",
        "notes.csv",
    ):
        (rr / "photometry" / name).write_text("jd,mag\n")
    (rr / "photometry_quality.json").write_text("{}")
    (rr / "targets.json").write_text("{}")
    _session(
        root,
        "20260829T034413Z_XX_Cyg",
        "2026-08-29T03:44:13+00:00",
        [_frame("d1.fits", image_type="Dark Frame", filter_name="Dark")],
        ["d1.fits"],
    )
    broken = root / "20260907T044527Z_Broken"
    broken.mkdir()
    (broken / "session.json").write_text("{not json")
    (root / "not_a_session").mkdir()  # no session.json: not listed
    (root / "loose.txt").write_text("x")
    return root


def test_sessions_newest_first_with_summaries(client, tmp_path):
    root = _setup(client, tmp_path)
    body = client.get("/api/sessions", headers=AUTH).json()
    assert body["root"] == str(root) and body["exists"] is True
    assert body["total"] == 3 and body["offset"] == 0 and body["limit"] == 50
    folders = [s["folder"] for s in body["sessions"]]
    # started_utc newest first; the unreadable one has no date and comes last.
    assert folders == ["20260925T200453Z_RR_Lyr", "20260829T034413Z_XX_Cyg",
                       "20260907T044527Z_Broken"]  # fmt: skip
    rr, xx, broken = body["sessions"]
    assert rr["object"] == "RR Lyr"
    assert rr["started_utc"] == "2026-09-25T20:04:56.567116+00:00"
    assert rr["frames"] == 3 and rr["lights"] == 3
    assert rr["filters"] == {"IR": 2, "—": 1}
    assert rr["image_types"] == {"Light Frame": 3}
    assert rr["missing_frames"] == 1
    assert rr["curves"] == {"target": 1, "comparison": 2, "check": 1}
    assert rr["has_quality"] is True and rr["has_targets"] is True
    assert rr["issues"] == ["1 FITS frame listed in session.json is missing"]
    assert xx["lights"] == 0
    assert "No light frames were recorded." in xx["issues"]
    assert xx["curves"] == {"target": 0, "comparison": 0, "check": 0}
    assert broken["frames"] == 0
    assert broken["issues"][0].startswith("Could not read session.json")


def test_pagination(client, tmp_path):
    _setup(client, tmp_path)
    page = client.get("/api/sessions", params={"offset": 1, "limit": 1}, headers=AUTH).json()
    assert page["total"] == 3 and [s["folder"] for s in page["sessions"]] == [
        "20260829T034413Z_XX_Cyg"
    ]
    assert client.get("/api/sessions", params={"limit": 0}, headers=AUTH).status_code == 400
    assert client.get("/api/sessions", params={"limit": 501}, headers=AUTH).status_code == 400


def test_summaries_follow_changes_and_are_cached(client, tmp_path):
    root = _setup(client, tmp_path)
    hub = client.app.state.hub
    first = client.get("/api/sessions", headers=AUTH).json()
    cached = hub.sessions._cache[str(root / "20260925T200453Z_RR_Lyr")][1]
    second = client.get("/api/sessions", headers=AUTH).json()
    assert second["sessions"] == first["sessions"]
    assert hub.sessions._cache[str(root / "20260925T200453Z_RR_Lyr")][1] is cached
    # A frame is written: session.json changes, the summary follows.
    session_json = root / "20260925T200453Z_RR_Lyr" / "session.json"
    document = json.loads(session_json.read_text())
    document["frames"].append(_frame("rr_0004.fits"))
    time.sleep(0.01)
    session_json.write_text(json.dumps(document))
    (root / "20260925T200453Z_RR_Lyr" / "lights" / "rr_0004.fits").write_bytes(b"x")
    third = client.get("/api/sessions", headers=AUTH).json()
    assert third["sessions"][0]["frames"] == 4
    # A session removed disappears.
    for path in sorted((root / "20260829T034413Z_XX_Cyg").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (root / "20260829T034413Z_XX_Cyg").rmdir()
    assert client.get("/api/sessions", headers=AUTH).json()["total"] == 2


def test_missing_sessions_folder_is_an_empty_list(client, tmp_path):
    client.patch("/api/config", json={"sessions_path": str(tmp_path / "none")}, headers=AUTH)
    body = client.get("/api/sessions", headers=AUTH).json()
    assert body["exists"] is False and body["total"] == 0 and body["sessions"] == []


def test_listing_never_writes_into_a_session(client, tmp_path):
    root = _setup(client, tmp_path)
    before = {
        str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in root.rglob("*") if p.is_file()
    }
    names_before = sorted(str(p) for p in root.rglob("*"))
    client.get("/api/sessions", headers=AUTH)
    assert sorted(str(p) for p in root.rglob("*")) == names_before
    after = {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in root.rglob("*")
             if p.is_file()}  # fmt: skip
    assert after == before


def test_linked_session_folders_are_not_followed(client, tmp_path):
    root = _setup(client, tmp_path)
    elsewhere = _session(tmp_path / "elsewhere", "20261001T000000Z_Far", "2026-10-01T00:00:00Z",
                         [_frame("a.fits")], ["a.fits"])  # fmt: skip
    os.symlink(elsewhere, root / "linked", target_is_directory=True)
    folders = [s["folder"] for s in client.get("/api/sessions", headers=AUTH).json()["sessions"]]
    assert "linked" not in folders
