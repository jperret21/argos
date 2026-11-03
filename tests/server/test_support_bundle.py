"""Support bundle (row A5) and crash reports (row A6): content and privacy.

The bundle must never hold the bearer token, network addresses or the home
path, and by default neither the observer's coordinates nor session
metadata (decision Q-G17). Everything runs in a temporary HOME, log folder
and sessions folder.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from tests.server.conftest import AUTH, TOKEN, wait_for
from tests.server.test_fs_list import isolate

SITE = {"site.name": "Home", "site.latitude": 48.8566, "site.longitude": 2.3522,
        "site.elevation": 35.0}  # fmt: skip
#: Every way the site appears in the log below.
SITE_WRITINGS = (
    "48.8566",
    "2.3522",
    "48.857",
    "2.352",
    "48.85660",
    "2.35220",
    "-122.27286",
    "43.932",
    "5.713",
)


def _log_text(home: Path) -> str:
    return "\n".join(
        [
            "2026-11-02 21:00:00 [INFO] uvicorn: GET /ws/events?token=" + TOKEN + " 101",
            f"2026-11-02 21:00:01 [INFO] argos: Authorization: Bearer {TOKEN}",
            f"2026-11-02 21:00:02 [INFO] argos: dev token {TOKEN} in use",
            "2026-11-02 21:00:03 [INFO] argos.core.alpaca.telescope: Mount site: "
            "lat=48.85660 lon=2.35220 elev=35m",
            "2026-11-02 21:00:04 [WARNING] argos.server.hub: Site check: the mount points at "
            "altitude 75.4°, azimuth 258.9°; from the Settings site (48.857°, 2.352°) the same "
            "RA/Dec is at altitude 13.8°",
            "2026-11-02 21:00:05 [INFO] argos: favourite at -122.27286 saved",
            "2026-11-02 21:00:05 [WARNING] argos.server.hub: Site check: the mount's own site "
            "(43.932°, 5.713°) is 700 km from the Settings site.",  # a site no longer set
            "2026-11-02 21:00:06 [INFO] argos: Connecting mount 192.168.1.42:32323…",
            f"2026-11-02 21:00:07 [INFO] argos: opened {home}/Argos/sessions/x/frame.fits",
            "2026-11-02 21:00:08 [INFO] argos: Exposing 2.5 s at gain 80",
        ]
    )


@pytest.fixture
def env(make_client, monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    client = make_client(log_dir=logs)
    paths = isolate(client, monkeypatch, tmp_path)
    favorites = [{"name": "Berkeley", "latitude": 37.87084, "longitude": -122.27286,
                  "elevation": 52.0}]  # fmt: skip
    assert client.patch("/api/config", json={**SITE, "site.favorites": favorites},
                        headers=AUTH).status_code == 200  # fmt: skip
    home = paths["home"]
    (logs / "argos.log").write_text(_log_text(home), encoding="utf-8")
    (logs / "argos.log.1").write_text("older line from 10.0.0.7\n", encoding="utf-8")
    (logs / "unrelated.txt").write_text("not a log\n")
    (logs / "crash-20261101T210000Z-4242.txt").write_text(
        "Argos 0.4.2 crash report\nTraceback (most recent call last):\n"
        f'  File "{home}/argos/x.py", line 1\nValueError: boom at 192.168.1.42\n',
        encoding="utf-8",
    )
    (logs / "crash-20261102T080000Z-4243.txt").write_text("RuntimeError: later\n")
    session = paths["sessions_path"] / "20260925T200453Z_RR_Lyr"
    (session / "lights").mkdir(parents=True)
    (session / "lights" / "f1.fits").write_bytes(b"SIMPLE  =")
    (session / "session.json").write_text(json.dumps({
        "object": "RR Lyr", "observer": "J. Observer", "started_utc": "2026-09-25T20:04:56Z",
        "frames": [{"filename": "f1.fits", "ra": 291.369, "dec": 42.785}],
    }))  # fmt: skip
    (session / "observation.json").write_text(json.dumps({
        "site": {"name": "Home", "latitude": 48.8566, "longitude": 2.3522},
        "SITELAT": 48.8566, "obscode": "PJUA", "host": "192.168.1.42", "target": "RR Lyr",
    }))  # fmt: skip
    (session / "photometry").mkdir()
    (session / "photometry" / "target_RR_Lyr.csv").write_text(
        "jd,mag,ra,dec,latitude\n2461309.33,7.712,291.37,42.78,48.8566\n"
    )
    (session / "diagnostics.jsonl").write_text(json.dumps({"lat": 48.8566, "hfd": 3.1}) + "\n")
    return {"client": client, "logs": logs, "home": home, "session": session, **paths}


def _run(client, body: dict) -> dict:
    response = client.post("/api/support-bundle", json=body, headers=AUTH)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert response.json()["job"]["kind"] == "support_bundle"
    return wait_for(
        lambda: (j := client.get(f"/api/jobs/{job_id}", headers=AUTH).json())["state"]
        in ("done", "failed")
        and j
    )


def _zip_texts(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


def test_default_bundle_has_no_token_address_home_coordinates_or_session(env):
    client, home = env["client"], env["home"]
    destination = home / "Desktop" / "bundle"
    (home / "Desktop").mkdir()
    job = _run(client, {"destination": str(destination)})
    assert job["state"] == "done", job
    result = job["result"]
    assert result["path"] == str(destination.with_suffix(".zip"))  # .zip added
    assert result["download"] is False
    assert result["session_included"] is False and result["site_included"] is False
    texts = _zip_texts(Path(result["path"]).read_bytes())
    assert set(texts) == {"README.txt", "manifest.json", "logs/argos.log", "logs/argos.log.1",
                          "crash/crash-20261102T080000Z-4243.txt",
                          "crash/crash-20261101T210000Z-4242.txt"}  # fmt: skip
    assert sorted(result["files"]) == sorted(texts)
    everything = "\n".join(texts.values())
    assert TOKEN not in everything
    assert "192.168.1.42" not in everything and "10.0.0.7" not in everything
    assert str(home) not in everything
    for writing in SITE_WRITINGS:
        assert writing not in everything, writing
    log = texts["logs/argos.log"]
    assert "token=<redacted-token>" in log and "Bearer <redacted-token>" in log
    assert (
        "lat=<redacted-site>" in log and "from the Settings site (<redacted-site>) the same" in log
    )
    assert "Exposing 2.5 s at gain 80" in log  # the diagnostic value stays
    assert "~/Argos/sessions/x/frame.fits" in log
    assert "ValueError: boom at <redacted-ip>" in texts["crash/crash-20261101T210000Z-4242.txt"]
    manifest = json.loads(texts["manifest.json"])
    assert manifest["privacy"] == {
        "created_locally": True,
        "uploaded_by_argos": False,
        "raw_fits_included": False,
        "tokens_included": False,
        "network_addresses_included": False,
        "site_coordinates_included": False,
        "session_metadata_included": False,
    }
    assert manifest["configuration"]["hardware.profile"] == "s30pro"
    assert manifest["configuration"]["api"] == 2
    assert not any(name.startswith("session/") for name in texts)


def test_session_metadata_only_when_asked_and_redacted(env):
    client, home, session = env["client"], env["home"], env["session"]
    job = _run(
        client,
        {"destination": str(home / "b.zip"), "include_session": True, "session_dir": str(session)},
    )
    assert job["state"] == "done", job
    texts = _zip_texts(Path(job["result"]["path"]).read_bytes())
    session_files = sorted(n for n in texts if n.startswith("session/"))
    assert session_files == ["session/diagnostics.jsonl", "session/observation.json",
                             "session/photometry/target_RR_Lyr.csv",
                             "session/session.json"]  # no FITS  # fmt: skip
    observation = json.loads(texts["session/observation.json"])
    assert observation["site"] == observation["SITELAT"] == "<redacted>"
    assert observation["obscode"] == observation["host"] == "<redacted>"
    assert observation["target"] == "RR Lyr"
    frames = json.loads(texts["session/session.json"])["frames"]
    assert frames[0]["ra"] == frames[0]["dec"] == "<redacted>"
    assert json.loads(texts["session/session.json"])["observer"] == "<redacted>"
    assert "48.8566" not in texts["session/photometry/target_RR_Lyr.csv"]
    assert "7.712" in texts["session/photometry/target_RR_Lyr.csv"]
    assert json.loads(texts["session/diagnostics.jsonl"])["lat"] == "<redacted>"
    assert json.loads(texts["manifest.json"])["privacy"]["session_metadata_included"] is True
    # A session folder given without include_session is ignored.
    job = _run(client, {"destination": str(home / "c.zip"), "session_dir": str(session)})
    assert not any(n.startswith("session/") for n in job["result"]["files"])


def test_numeric_coordinates_under_other_keys_are_redacted(env):
    """Technical review: JSON numbers outside the location keys escaped the text pass."""
    client, home, session = env["client"], env["home"], env["session"]
    (session / "extra.json").write_text(json.dumps({
        "geo": {"lat_deg": 48.8566, "lon_deg": 2.3522},
        "where": {"a": 37.87084, "b": -122.27286, "rounded": 48.857},
        "pair": [48.8566, 2.3522], "frames": 52, "gain": 80, "hfd": 3.1,
    }))  # fmt: skip
    (session / "events.jsonl").write_text(json.dumps({"v": [37.87084, -122.27286]}) + "\n")
    job = _run(
        client,
        {"destination": str(home / "n.zip"), "include_session": True, "session_dir": str(session)},
    )
    texts = _zip_texts(Path(job["result"]["path"]).read_bytes())
    extra = json.loads(texts["session/extra.json"])  # still valid JSON
    assert extra["geo"] == "<redacted>"
    assert extra["where"] == {"a": "<redacted-site>", "b": "<redacted-site>",
                              "rounded": "<redacted-site>"}  # fmt: skip
    assert extra["pair"] == ["<redacted-site>", "<redacted-site>"]
    assert extra["frames"] == 52 and extra["gain"] == 80 and extra["hfd"] == 3.1
    assert json.loads(texts["session/events.jsonl"])["v"] == ["<redacted-site>"] * 2
    for text in texts.values():
        assert "48.8566" not in text and "37.87084" not in text and "122.27286" not in text


def test_site_coordinates_only_when_asked(env):
    client, home = env["client"], env["home"]
    job = _run(client, {"destination": str(home / "site.zip"), "include_site": True,
                        "include_crash_reports": False})  # fmt: skip
    texts = _zip_texts(Path(job["result"]["path"]).read_bytes())
    assert "lat=48.85660" in texts["logs/argos.log"]
    assert TOKEN not in "\n".join(texts.values())  # never the token
    assert not any(n.startswith("crash/") for n in texts)
    assert job["result"]["site_included"] is True
    assert json.loads(texts["manifest.json"])["privacy"]["site_coordinates_included"] is True


def test_browser_download(env):
    client = env["client"]
    job = _run(client, {})
    assert job["result"]["download"] is True and job["result"]["path"] is None
    name = job["result"]["name"]
    assert name.startswith("argos-support-") and name.endswith("Z.zip")
    response = client.get(f"/api/jobs/{job['id']}/download", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert name in response.headers["content-disposition"]
    texts = _zip_texts(response.content)
    assert "logs/argos.log" in texts and TOKEN not in "\n".join(texts.values())
    # The kept file lives outside every data folder and goes with the server.
    path, _ = client.app.state.hub.job_download(job["id"])
    assert not str(path).startswith(str(env["home"]))
    assert client.get("/api/jobs/nope/download", headers=AUTH).status_code == 404


def test_download_of_a_job_without_a_file(env):
    client, home = env["client"], env["home"]
    job = _run(client, {"destination": str(home / "kept.zip")})
    response = client.get(f"/api/jobs/{job['id']}/download", headers=AUTH)
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


def test_refusals_before_the_job_starts(env, tmp_path):
    client, home, session = env["client"], env["home"], env["session"]

    def post(body):
        return client.post("/api/support-bundle", json=body, headers=AUTH)

    outside = post({"destination": str(tmp_path / "outside" / "b.zip")})
    assert outside.status_code == 403 and outside.json()["error"]["code"] == "forbidden_path"
    relative = post({"destination": "b.zip"})
    assert relative.status_code == 400
    (home / "exists.zip").write_bytes(b"old")
    exists = post({"destination": str(home / "exists.zip")})
    assert exists.status_code == 409 and exists.json()["error"]["code"] == "file_exists"
    assert (home / "exists.zip").read_bytes() == b"old"
    replaced = _run(client, {"destination": str(home / "exists.zip"), "overwrite": True})
    assert replaced["state"] == "done" and zipfile.is_zipfile(home / "exists.zip")
    no_dir = post({"include_session": True})
    assert no_dir.status_code == 400 and no_dir.json()["error"]["code"] == "invalid_argument"
    not_session = post({"include_session": True, "session_dir": str(home)})
    assert not_session.status_code == 400
    assert not_session.json()["error"]["code"] == "session_invalid"
    outside_session = post({"include_session": True, "session_dir": str(tmp_path / "outside")})
    assert outside_session.status_code == 403
    # A folder is refused, never turned into "<folder>.zip" beside it (technical review).
    (home / "Desktop").mkdir(exist_ok=True)
    folder = post({"destination": str(home / "Desktop")})
    assert folder.status_code == 400 and "is a folder" in folder.json()["error"]["message"]
    assert not (home / "Desktop.zip").exists()
    unknown = post({"destination": str(home / "x.zip"), "upload": True})
    assert unknown.status_code == 400  # strict body
    assert not (home / "x.zip").exists()
    assert session.is_dir()


def test_missing_zip_suffix_is_appended_not_swapped(env):
    client, home = env["client"], env["home"]
    job = _run(client, {"destination": str(home / "c.tar.gz")})
    assert job["state"] == "done", job
    assert (home / "c.tar.gz.zip").is_file()
    assert not (home / "c.tar.zip").exists()


def test_bundle_job_is_not_cancellable(env):
    client, home = env["client"], env["home"]
    job = _run(client, {"destination": str(home / "n.zip")})
    assert job["cancellable"] is False


def test_failed_write_is_a_bundle_failed_job(env, monkeypatch):
    from argos.server import support

    def refuse(*_args, **_kwargs):
        raise support.BundleError("No space left on device")

    monkeypatch.setattr(support, "create_bundle", refuse)
    job = _run(env["client"], {"destination": str(env["home"] / "full.zip")})
    assert job["state"] == "failed"
    assert job["error"] == {
        "code": "bundle_failed",
        "message": "Could not create the ZIP: No space left on device",
    }


def test_crash_reports_route(env):
    client = env["client"]
    body = client.get("/api/diagnostics/crash-reports", headers=AUTH).json()
    assert body["directory"] == str(env["logs"])
    names = [r["name"] for r in body["reports"]]
    assert names == ["crash-20261102T080000Z-4243.txt", "crash-20261101T210000Z-4242.txt"]
    first = body["reports"][1]
    assert first["t"] == "2026-11-01T21:00:00Z"
    assert first["summary"] == "ValueError: boom at <redacted-ip>"
    later = client.get(
        "/api/diagnostics/crash-reports", params={"since": "2026-11-02T00:00:00Z"}, headers=AUTH
    ).json()
    assert [r["name"] for r in later["reports"]] == ["crash-20261102T080000Z-4243.txt"]
    same = client.get(
        "/api/diagnostics/crash-reports",
        params={"since": "2026-11-02T08:00:00.000+00:00"},
        headers=AUTH,
    ).json()
    assert same["reports"] == []  # strictly after
    bad = client.get("/api/diagnostics/crash-reports", params={"since": "yesterday"}, headers=AUTH)
    assert bad.status_code == 400


def test_crash_reports_without_a_log_folder(client):
    body = client.get("/api/diagnostics/crash-reports", headers=AUTH).json()
    assert body == {"directory": None, "reports": []}
