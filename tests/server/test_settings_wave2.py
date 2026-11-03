"""Wave 2 Settings: exit criterion, live config sync, ASTAP, caches, place search.

Exit criterion of ``web/spec/README.md`` §7 W2: every key of
``web/spec/02-connection-and-settings.md`` appendix A is editable or
deliberately read-only (or deliberately omitted, with its reason), and
config changes sync live between two open clients. No test reaches the
network (the place search gets a fake HTTP getter) or the owner's files.
"""

from __future__ import annotations

import hashlib

import re
import threading
import time
from pathlib import Path

import pytest

from argos import __version__
from argos.server.config_meta import META, OMITTED
from argos.server.settings_helpers import USER_AGENT
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until, wait_for

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "web" / "spec" / "02-connection-and-settings.md"


# -- exit criterion: appendix A covered -------------------------------------------------


def _appendix_keys() -> list[str]:
    text = SPEC.read_text(encoding="utf-8")
    table = text.split("## A. Configuration keys", 1)[1]
    keys: list[str] = []
    for line in table.splitlines():
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1]
        names = re.findall(r"`([^`]+)`", cell)
        for name in names:
            # "observer.latitude / longitude / elevation" -> three keys
            parts = [p.strip() for p in name.split("/")]
            head = parts[0]
            keys.append(head)
            prefix = head.rsplit(".", 1)[0]
            keys += [f"{prefix}.{p}" for p in parts[1:] if p]
    return keys


def test_every_appendix_a_key_is_editable_read_only_or_deliberately_omitted():
    keys = _appendix_keys()
    assert len(keys) >= 80, "the appendix parser found too few keys"
    omitted = dict(OMITTED)
    uncovered = []
    for key in keys:
        if key in META or key in omitted:
            continue
        if key == "hardware.overrides" and any(k.startswith("hardware.overrides.") for k in META):
            continue  # the dict is exposed field by field
        uncovered.append(key)
    assert uncovered == []
    for key, meta in META.items():
        if meta.read_only:
            assert meta.read_only_reason, key
        else:
            assert meta.read_only_reason is None, key
    for key, reason in OMITTED:
        assert key not in META and reason, key


def test_read_only_keys_say_why(client):
    body = client.get("/api/config", headers=AUTH).json()
    meta = body["meta"]
    # Written for the observer (shown under the field): where to change it, no route or code.
    assert "Connection screen" in meta["hardware.profile"]["read_only_reason"]
    assert "/api/" not in meta["hardware.profile"]["read_only_reason"]
    assert meta["hardware.overrides.adc_bits"]["read_only"] is True
    assert "telescope profile" in meta["hardware.overrides.adc_bits"]["read_only_reason"]
    assert all("Q-" not in (m["read_only_reason"] or "") for m in meta.values())
    assert body["values"]["hardware.overrides.adc_bits"] is None
    assert meta["site.latitude"]["read_only_reason"] is None
    assert {o["key"] for o in body["omitted"]} == {k for k, _ in OMITTED}
    refused = client.patch("/api/config", json={"hardware.overrides.adc_bits": 14}, headers=AUTH)
    assert refused.status_code == 400
    assert refused.json()["error"]["fields"] == {
        "hardware.overrides.adc_bits": "is read-only. The ADC depth is the sensor's, set by the "
        "telescope profile."
    }


# -- live sync between two clients --------------------------------------------------------


def _drain_config(ws, until_revision: int, timeout: float = 10.0) -> dict:
    """Read config events until one reaches *until_revision*; return the newest."""
    newest: dict = {}
    deadline = time.monotonic() + timeout
    while not newest or newest["revision"] < until_revision:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(f"no config event reached revision {until_revision}")
        message = receive_json(ws, timeout=remaining)
        if message["type"] == "config" and message["revision"] >= newest.get("revision", -1):
            newest = message
    return newest


def test_two_clients_patching_at_once_converge(client):
    with (
        client.websocket_connect(f"/ws/events?token={TOKEN}") as a,
        client.websocket_connect(f"/ws/events?token={TOKEN}") as b,
    ):
        receive_until(a, lambda m: m["type"] == "status")
        receive_until(b, lambda m: m["type"] == "status")
        results: dict[str, list[int]] = {"a": [], "b": []}

        def writer(tag: str, key: str, values: list) -> None:
            for value in values:
                response = client.patch("/api/config", json={key: value}, headers=AUTH)
                assert response.status_code == 200, response.text
                results[tag].append(response.json()["revision"])

        names = [f"Observer {i}" for i in range(15)]
        sites = [f"Site {i}" for i in range(15)]
        threads = [
            threading.Thread(target=writer, args=("a", "observer.name", names)),
            threading.Thread(target=writer, args=("b", "site.name", sites)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
        final = client.get("/api/config", headers=AUTH).json()
        assert final["revision"] == 30  # every commit counted once, none lost
        assert sorted(results["a"] + results["b"]) == list(range(1, 31))
        newest_a = _drain_config(a, final["revision"])
        newest_b = _drain_config(b, final["revision"])
    for newest in (newest_a, newest_b):
        assert newest["values"] == final["values"]
        assert newest["source"] == "api"
    assert final["values"]["observer.name"] == "Observer 14"
    assert final["values"]["site.name"] == "Site 14"


def test_same_key_from_two_clients_ends_with_the_later_commit_everywhere(client):
    with (
        client.websocket_connect(f"/ws/events?token={TOKEN}") as a,
        client.websocket_connect(f"/ws/events?token={TOKEN}") as b,
    ):
        client.patch("/api/config", json={"observer.obscode": "AAA"}, headers=AUTH)
        last = client.patch("/api/config", json={"observer.obscode": "bbb"}, headers=AUTH).json()
        assert last["values"]["observer.obscode"] == "BBB"  # upper-cased
        for ws in (a, b):
            newest = _drain_config(ws, last["revision"])
            assert newest["values"]["observer.obscode"] == "BBB"
            assert newest["changed"] == {"observer.obscode": "BBB"}


def test_two_servers_on_one_config_folder_converge(make_client, tmp_path):
    """The web UI beside another writer of the same file (the Qt app, or a second server)."""
    shared = tmp_path / "shared-config"
    first = make_client(config_dir=shared)
    second = make_client(config_dir=shared)
    with second.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        receive_until(ws, lambda m: m["type"] == "status")
        first.patch("/api/config", json={"site.name": "Haute-Provence"}, headers=AUTH)
        time.sleep(0.01)
        # The second server notices the file changed on its next read, and says so.
        assert second.get("/api/config", headers=AUTH).json()["values"]["site.name"] == (
            "Haute-Provence"
        )
        event = receive_until(ws, lambda m: m["type"] == "config")
        assert event["source"] == "file" and event["changed"] == {"site.name": "Haute-Provence"}
        # A commit on the second server never overwrites the first one's change.
        second.patch("/api/config", json={"observer.name": "J. Observer"}, headers=AUTH)
    values = first.get("/api/config", headers=AUTH).json()["values"]
    assert values["site.name"] == "Haute-Provence" and values["observer.name"] == "J. Observer"


# -- ASTAP detection (A81) -------------------------------------------------------------------


def test_astap_detection(client, tmp_path):
    exe = tmp_path / "astap_cli"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    db = tmp_path / "d50"
    db.mkdir()
    (db / "d50_0101.1476").write_bytes(b"")
    body = client.get(
        "/api/astrometry/astap", params={"path": str(exe), "database_path": str(db)}, headers=AUTH
    ).json()
    assert body["astap"] == str(exe) and body["configured_found"] is True
    assert body["database_dir"] == str(db) and body["database_source"] == "configured"
    assert body["database_found"] is True
    assert body["database_args"] == ["-d", str(db)]
    assert body["database_ignored"] is False
    assert body["message"].startswith(f"ASTAP detected: {exe}")
    # A set and a folder: the set is ignored (Q-C9).
    both = client.get(
        "/api/astrometry/astap",
        params={"path": str(exe), "database_path": str(db), "database": "D50"},
        headers=AUTH,
    ).json()
    assert both["database_ignored"] is True and "ignored while a folder is set" in both["message"]
    # An empty folder is "not found".
    empty = tmp_path / "empty"
    empty.mkdir()
    none = client.get(
        "/api/astrometry/astap",
        params={"path": str(exe), "database_path": str(empty)},
        headers=AUTH,
    ).json()
    assert none["database_found"] is False and "Star database not found in" in none["message"]
    # A path that is not a file falls back to auto-detection (PATH, common places).
    missing = client.get(
        "/api/astrometry/astap", params={"path": str(tmp_path / "nope")}, headers=AUTH
    ).json()
    assert missing["configured_found"] is False and "is not a file" in missing["message"]


def test_astap_defaults_to_the_config(client, tmp_path):
    exe = tmp_path / "astap"
    exe.write_text("")
    client.patch("/api/config", json={"astrometry.astap_path": str(exe)}, headers=AUTH)
    body = client.get("/api/astrometry/astap", headers=AUTH).json()
    assert body["configured"] == str(exe) and body["astap"] == str(exe)


# -- caches (A83) and the essential catalogue (A84) --------------------------------------------


def _digest(i: int, width: int) -> str:
    """A cache file name as the core writes it (hex digest, gaia.py:57-58)."""
    return hashlib.sha256(str(i).encode()).hexdigest()[:width]


def test_cache_clear_keeps_files_argos_did_not_write(client, tmp_path):
    """Technical review: a cache pointed at a general folder must not lose its JSON files."""
    documents = tmp_path / "Documents"
    (documents / "project" / "sub").mkdir(parents=True)
    (documents / "notes.json").write_text("{}")
    (documents / "project" / "package.json").write_text("{}")
    (documents / "project" / "sub" / "tsconfig.json").write_text("{}")
    (documents / "simbad").mkdir()
    (documents / "simbad" / f"{_digest(3, 64)}.json").write_text("{}")
    (documents / "simbad" / "mine.json").write_text("{}")
    for key in ("data_paths.field_catalogue_cache_directory", "data_paths.aavso_cache_directory"):
        assert (
            client.patch("/api/config", json={key: str(documents)}, headers=AUTH).status_code == 200
        )
    caches = {c["kind"]: c for c in client.get("/api/caches", headers=AUTH).json()["caches"]}
    assert caches["field_catalogue"]["files"] == 1 and caches["aavso"]["files"] == 0
    assert client.delete("/api/caches/aavso", headers=AUTH).json()["removed"] == 0
    assert client.delete("/api/caches/field_catalogue", headers=AUTH).json()["removed"] == 1
    for kept in ("notes.json", "project/package.json", "project/sub/tsconfig.json",
                 "simbad/mine.json"):  # fmt: skip
        assert (documents / kept).exists(), kept
    assert not (documents / "simbad" / f"{_digest(3, 64)}.json").exists()


def test_cache_listing_and_clearing(client, tmp_path):
    base = tmp_path / "cache"
    paths = {
        "data_paths.object_catalogue_cache": base / "object_resolver.json",
        "data_paths.exoplanet_cache": base / "exoplanets.json",
        "data_paths.aavso_cache_directory": base / "catalog",
        "data_paths.gaia_cache_directory": base / "gaia",
        "data_paths.field_catalogue_cache_directory": base / "field_catalogue",
    }
    client.patch("/api/config", json={k: str(v) for k, v in paths.items()}, headers=AUTH)
    base.mkdir()
    paths["data_paths.object_catalogue_cache"].write_text("{}")
    (base / "gaia").mkdir()
    for i in range(3):
        (base / "gaia" / f"{_digest(i, 64)}.csv").write_text("g\n1\n")
    (base / "gaia" / "keep.txt").write_text("not a cache file")
    (base / "gaia" / "notes.csv").write_text("not written by the cache")
    keep_outside = tmp_path / "precious.csv"
    keep_outside.write_text("precious")
    (base / "gaia" / f"{_digest(9, 64)}.csv").symlink_to(keep_outside)
    (base / "field_catalogue" / "simbad").mkdir(parents=True)
    (base / "field_catalogue" / "simbad" / f"{_digest(1, 64)}.json").write_text("{}")
    (base / "field_catalogue" / "nasa").mkdir()
    (base / "field_catalogue" / "nasa" / f"{_digest(2, 64)}.json").write_text("{}")
    (base / "field_catalogue" / "project.json").write_text("{}")  # not the cache's

    caches = {c["kind"]: c for c in client.get("/api/caches", headers=AUTH).json()["caches"]}
    assert list(caches) == ["object", "exoplanet", "aavso", "gaia", "field_catalogue"]
    assert caches["object"]["files"] == 1 and caches["object"]["path_kind"] == "file"
    assert caches["exoplanet"]["exists"] is False and caches["exoplanet"]["files"] == 0
    assert caches["gaia"]["files"] == 3 and caches["gaia"]["bytes"] == 3 * 4
    assert caches["field_catalogue"]["files"] == 2
    assert caches["gaia"]["label"] == "Gaia DR3 field-star cache"
    assert caches["gaia"]["key"] == "data_paths.gaia_cache_directory"

    with client.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        cleared = client.delete("/api/caches/gaia", headers=AUTH).json()
        line = receive_until(ws, lambda m: m["type"] == "log" and "Cleared" in m["message"])
    assert cleared["removed"] == 3 and cleared["cache"]["files"] == 0
    assert line["message"] == "Cleared the Gaia DR3 field-star cache (3 files)."
    assert (base / "gaia" / "keep.txt").exists()
    assert (base / "gaia" / "notes.csv").exists()  # only the names the cache writes
    assert keep_outside.read_text() == "precious"  # a link is never followed
    assert client.delete("/api/caches/field_catalogue", headers=AUTH).json()["removed"] == 2
    assert (base / "field_catalogue" / "project.json").exists()
    assert client.delete("/api/caches/object", headers=AUTH).json()["removed"] == 1
    unknown = client.delete("/api/caches/everything", headers=AUTH)
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "not_found"


def test_essential_catalogue(client):
    body = client.get("/api/catalogues/essential", headers=AUTH).json()
    assert set(body) == {"name", "version", "source", "source_url", "object_count"}
    assert body["object_count"] > 0 and body["name"]


# -- place search (A82) -------------------------------------------------------------------------


class FakeGeo:
    def __init__(self, matches, elevation=650.0, fail_search=False, block: threading.Event = None):
        self.matches = matches
        self.elevation = elevation
        self.fail_search = fail_search
        self.block = block
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url, params, headers, timeout):
        self.calls.append((url, params, headers))
        if self.block is not None:
            self.block.wait(10)
        if "nominatim" in url:
            if self.fail_search:
                raise OSError("network is unreachable")
            return self.matches
        if self.elevation is None:
            raise OSError("elevation service down")
        return {"elevation": [self.elevation]}


def _search(client, query: str) -> dict:
    response = client.post("/api/site/search", json={"query": query}, headers=AUTH)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    return wait_for(
        lambda: (j := client.get(f"/api/jobs/{job_id}", headers=AUTH).json())["state"]
        in ("done", "failed", "cancelled")
        and j
    )


def test_place_search_returns_places_with_elevations(client):
    fake = FakeGeo(
        [
            {"lat": "43.9319", "lon": "5.7131", "display_name": "Observatoire de Haute-Provence"},
            {"lat": "bad", "lon": "1"},  # skipped
            {"lat": "95", "lon": "0", "display_name": "off the globe"},  # skipped
        ]
    )
    client.app.state.hub.place_http_get = fake
    job = _search(client, "  Saint-Michel-l'Observatoire  ")
    assert job["state"] == "done", job
    assert job["kind"] == "site_search"
    assert job["result"] == {
        "query": "Saint-Michel-l'Observatoire",
        "places": [
            {
                "label": "Observatoire de Haute-Provence",
                "latitude": 43.9319,
                "longitude": 5.7131,
                "elevation_m": 650.0,
            }
        ],
    }
    url, params, headers = fake.calls[0]
    assert "nominatim.openstreetmap.org" in url and params["limit"] == 5
    assert headers["User-Agent"] == USER_AGENT
    assert f"Argos/{__version__}" in USER_AGENT
    # The place search writes nothing: the client PATCHes site.* when one is chosen.
    assert client.get("/api/config", headers=AUTH).json()["revision"] == 0


def test_elevation_failure_keeps_the_place(client):
    client.app.state.hub.place_http_get = FakeGeo([{"lat": "1", "lon": "2"}], elevation=None)
    job = _search(client, "somewhere")
    assert job["result"]["places"][0]["elevation_m"] is None


def test_place_search_errors(client):
    hub = client.app.state.hub
    empty = client.post("/api/site/search", json={"query": "   "}, headers=AUTH)
    assert empty.status_code == 400
    assert empty.json()["error"]["message"] == "Enter a city, country, or address first."
    hub.place_http_get = FakeGeo([])
    job = _search(client, "Nowhere")
    assert job["state"] == "failed"
    assert job["error"] == {"code": "not_found", "message": "No place found for ‘Nowhere’."}
    hub.place_http_get = FakeGeo([{"lat": "x", "lon": "y"}])
    job = _search(client, "Garbage")
    assert job["error"]["code"] == "not_found" and "usable" in job["error"]["message"]
    hub.place_http_get = FakeGeo([], fail_search=True)
    job = _search(client, "Offline")
    assert job["error"] == {
        "code": "lookup_failed",
        "message": "Location search is unavailable. Check your internet connection.",
    }


def test_place_search_cancels_during_a_request(client):
    gate = threading.Event()
    client.app.state.hub.place_http_get = FakeGeo([{"lat": "1", "lon": "2"}], block=gate)
    response = client.post("/api/site/search", json={"query": "slow"}, headers=AUTH)
    job_id = response.json()["job_id"]
    busy = client.post("/api/site/search", json={"query": "again"}, headers=AUTH)
    assert busy.status_code == 409 and busy.json()["error"]["owner"] == job_id
    started = time.monotonic()
    client.delete(f"/api/jobs/{job_id}", headers=AUTH)
    job = wait_for(
        lambda: (j := client.get(f"/api/jobs/{job_id}", headers=AUTH).json())["state"]
        == "cancelled"
        and j
    )
    assert time.monotonic() - started < 2.0
    assert job["result"] is None
    gate.set()
