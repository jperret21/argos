"""Configuration over the API (rows A8-A10) against temporary config folders only.

No test here reads or writes ``~/.argos``: every client gets a fresh
temporary folder (``conftest.make_client``), and the store tests build their
own.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

import pytest

from argos.core import config as core_config
from argos.server import runtime
from argos.server.config_meta import KEYS, META
from argos.server.config_store import ConfigStore
from argos.server.errors import ApiError
from argos.server.settings import Settings
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until

META_FIELDS = {
    "type", "default", "nullable", "min", "max", "step", "options", "unit", "label", "help",
    "used_by", "category", "advanced", "read_only", "read_only_reason", "path_kind", "personal",
}  # fmt: skip
CATEGORIES = {
    "connection", "observer_site", "instrument", "plate_solving", "catalogues", "photometry",
    "data_storage", "privacy_diagnostics", "appearance", "observe",
}  # fmt: skip


def _config_file(client) -> Path:
    return Path(client.get("/api/config", headers=AUTH).json()["path"])


def test_get_config_has_values_and_meta_for_every_key(client):
    body = client.get("/api/config", headers=AUTH).json()
    assert set(body) == {"values", "meta", "omitted", "revision", "path"}  # omitted: wave 2
    assert set(body["values"]) == set(body["meta"]) == set(META)
    assert body["revision"] == 0
    assert not body["path"].startswith(str(Path.home() / ".argos"))
    for key, meta in body["meta"].items():
        assert set(meta) == META_FIELDS, key
        assert meta["category"] in CATEGORIES, key
        assert meta["label"] and meta["help"], key
        assert isinstance(meta["used_by"], list) and meta["used_by"], key
        if meta["options"] is not None:
            assert all(set(o) == {"value", "label"} for o in meta["options"]), key
    # A fresh folder: the values are the shipped defaults of argos/core/config.py.
    assert body["values"]["alpaca.port"] == 32323
    assert body["values"]["catalog.identification_max_objects"] == 400
    assert body["values"]["hardware.overrides.full_well_adu"] is None
    assert body["values"]["photometry.track_apertures"] is True  # missing from _DEFAULTS


def test_personal_keys_are_the_observer_and_the_site(client):
    """Wave 2 fix: these have no shipped default to reset to (0°, 0° is not a site)."""
    meta = client.get("/api/config", headers=AUTH).json()["meta"]
    personal = {k for k, m in meta.items() if m["personal"]}
    assert personal == {
        "observer.name", "observer.obscode",
        "site.name", "site.latitude", "site.longitude", "site.elevation",
    }  # fmt: skip


def test_no_observer_facing_text_names_an_api_route(client):
    meta = client.get("/api/config", headers=AUTH).json()["meta"]
    for key, m in meta.items():
        for text in (m["help"], m["label"], m["read_only_reason"] or ""):
            assert "/api/" not in text and "PUT " not in text and "PATCH" not in text, key
            # No config key and no JSON shape in the observer's words (the key has its own
            # line in the "About this setting" column).
            assert not any(k in text for k in META), (key, text)
            assert '{"' not in text, (key, text)


def test_meta_says_what_a_path_key_names(client):
    """Wave 2 integration: the FilePicker opens in the mode the server validates with."""
    meta = client.get("/api/config", headers=AUTH).json()["meta"]
    kinds = {k: m["path_kind"] for k, m in meta.items() if m["type"] == "path"}
    assert kinds["astrometry.astap_path"] == "exe"
    assert kinds["data_paths.object_catalogue_cache"] == "file"
    assert kinds["data_paths.exoplanet_cache"] == "file"
    assert kinds["sessions_path"] == "dir"
    assert kinds["astrometry.database_path"] == "dir"
    assert all(m["path_kind"] is None for m in meta.values() if m["type"] != "path")


def test_meta_defaults_match_the_core_defaults():
    """The meta table must not drift from argos/core/config.py:19-176."""
    for meta in KEYS:
        node = core_config._DEFAULTS
        for part in meta.key.split("."):
            node = node.get(part, KeyError) if isinstance(node, dict) else KeyError
        if node is not KeyError:
            assert meta.default == node, meta.key


def test_dead_and_internal_keys_are_not_exposed():
    for key in (
        "ui.language",
        "ui.window_state",
        "ui.window_geometry",
        "catalog.field_stars_max_results",
        "catalog.named_objects_max_results",
        "catalog.display_limit_version",
        "camera.adc_bits",
        "diagnostics.local_opt_in_v1",
        "observer.latitude",
    ):
        assert key not in META


def test_patch_commits_validated_values_and_announces_them(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        response = client.patch(
            "/api/config",
            json={"site.latitude": 48, "observer.obscode": " pjua ", "catalog.mag_limit": 14.5},
            headers=AUTH,
        )
        event = receive_until(events, lambda m: m["type"] == "config")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] == {
        "site.latitude": 48.0,
        "observer.obscode": "PJUA",
        "catalog.mag_limit": 14.5,
    }
    assert body["revision"] == 1 and body["warnings"] == []
    assert event["changed"] == body["changed"] and event["source"] == "api"
    assert event["values"] == body["values"] and event["revision"] == 1
    on_disk = json.loads(_config_file(client).read_text())
    assert on_disk["site"]["latitude"] == 48.0
    assert on_disk["observer"]["obscode"] == "PJUA"
    # The whole file is written, as config.py:221-229 (the Qt app can read it).
    assert on_disk["alpaca"] == {"host": "", "port": 32323}


def test_unchanged_values_are_not_written(client):
    response = client.patch("/api/config", json={"alpaca.port": 32323}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["changed"] == {} and response.json()["revision"] == 0
    assert not _config_file(client).exists()


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("alpaca.port", 80.0, "must be an integer"),
        ("alpaca.port", True, "must be an integer"),
        ("alpaca.port", 0, "must be at least 1"),
        ("site.latitude", "48.8", "must be a number"),
        ("site.latitude", 91, "must be at most 90°"),
        ("site.latitude", None, "must not be empty"),
        ("astrometry.use_scale_hint", 1, "must be true or false"),
        ("catalog.identification_max_objects", 300, "must be one of 100, 200, 400, 800, 1600"),
        ("ui.log_level", "debug", "must be one of 'DEBUG', 'INFO', 'WARNING', 'ERROR'"),
        ("observer.obscode", "PJ-UA", "contains characters that are not allowed"),
        ("sessions_path", "relative/sessions", "must be an absolute path"),
        ("alpaca.host", "192.168.1.42 ", None),  # stripped, valid
        ("alpaca.host", "bad host!", "must be an IP address or a host name"),
        (
            "hardware.profile",
            "s50",
            "is read-only. Changed on the Connection screen (Instrument card), which checks "
            "that no equipment is connected.",
        ),
        (
            "camera.full_well_adu",
            50000,
            "is read-only. Follows Saturation (full well) above, so the Qt app reads the same "
            "value.",
        ),
        (
            "photometry.default_band",
            "XX",
            "must be one of 'TG', 'TB', 'TR', 'V', 'B', 'U', "
            "'R', 'I', 'CV', 'CR', 'CBB', 'SU', 'SG', 'SR', 'SI', 'SZ', 'J', 'H', 'K'",
        ),
        ("no.such.key", 1, "unknown setting"),
        (
            "site.favorites",
            [{"name": "Home"}],
            "item 0 must have exactly name, latitude, longitude, elevation",
        ),
        ("camera.egain_table", {"80": -1}, "gain 80: e/ADU must be in (0, 100]"),
    ],
)
def test_patch_validation(client, key, value, message):
    response = client.patch("/api/config", json={key: value}, headers=AUTH)
    if message is None:
        assert response.status_code == 200
        return
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_argument"
    assert error["fields"] == {key: message}
    assert not _config_file(client).exists()  # nothing written


def test_one_invalid_key_rejects_the_whole_commit(client):
    response = client.patch(
        "/api/config", json={"site.name": "Home", "site.latitude": 120}, headers=AUTH
    )
    assert response.status_code == 400
    assert set(response.json()["error"]["fields"]) == {"site.latitude"}
    assert client.get("/api/config", headers=AUTH).json()["values"]["site.name"] == ""
    for body in ([], {}, "x"):
        assert client.patch("/api/config", json=body, headers=AUTH).status_code == 400


def test_path_warnings_and_refusals(client, tmp_path):
    missing = tmp_path / "new" / "sessions"
    response = client.patch("/api/config", json={"sessions_path": str(missing)}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["warnings"] == [
        {"key": "sessions_path", "message": "does not exist, it will be created"}
    ]
    a_file = tmp_path / "plain.txt"
    a_file.write_text("x")
    response = client.patch("/api/config", json={"sessions_path": str(a_file)}, headers=AUTH)
    assert response.json()["error"]["fields"] == {
        "sessions_path": "is a file; a folder is expected"
    }
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        if os.access(locked, os.W_OK):
            pytest.skip("running with permissions that ignore the mode bits")
        response = client.patch(
            "/api/config", json={"data_paths.gaia_cache_directory": str(locked)}, headers=AUTH
        )
        assert response.json()["error"]["fields"] == {
            "data_paths.gaia_cache_directory": "not writable"
        }
    finally:
        locked.chmod(0o700)
    # "~" is accepted and stored expanded.
    response = client.patch(
        "/api/config", json={"data_paths.sequence_presets_directory": "~/Argos/sequences"},
        headers=AUTH,
    )  # fmt: skip
    assert response.json()["values"]["data_paths.sequence_presets_directory"] == str(
        Path.home() / "Argos" / "sequences"
    )


def test_stellarium_host_off_loopback_warns(client):
    response = client.patch("/api/config", json={"stellarium.host": "0.0.0.0"}, headers=AUTH)
    assert response.json()["warnings"][0]["key"] == "stellarium.host"
    assert "reachable from the network" in response.json()["warnings"][0]["message"]


def test_override_is_mirrored_to_the_legacy_qt_key(client):
    response = client.patch(
        "/api/config", json={"hardware.overrides.full_well_adu": 58000}, headers=AUTH
    )
    assert response.json()["changed"] == {
        "hardware.overrides.full_well_adu": 58000,
        "camera.full_well_adu": 58000,
    }
    profile = client.get("/api/profiles", headers=AUTH).json()["profiles"][0]
    assert profile["full_well_adu"] == 58000 and profile["overrides"] == {"full_well_adu": 58000}
    # null = back to the profile's value, override removed from the file.
    response = client.patch(
        "/api/config", json={"hardware.overrides.full_well_adu": None}, headers=AUTH
    )
    assert response.json()["values"]["camera.full_well_adu"] == 60000
    on_disk = json.loads(_config_file(client).read_text())
    assert on_disk["hardware"]["overrides"] == {}


def test_diagnostics_choice_marks_the_explicit_opt_in(client):
    client.patch("/api/config", json={"diagnostics.enabled": True}, headers=AUTH)
    on_disk = json.loads(_config_file(client).read_text())
    assert on_disk["diagnostics"] == {"enabled": True, "local_opt_in_v1": True}


def test_writes_are_atomic_and_leave_no_temporary_file(client):
    errors: list = []

    def writer(i: int) -> None:
        response = client.patch("/api/config", json={"site.elevation": float(i + 1)}, headers=AUTH)
        if response.status_code != 200:
            errors.append(response.text)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors
    path = _config_file(client)
    json.loads(path.read_text())  # always a complete document
    assert [p.name for p in path.parent.iterdir()] == ["config.json"]
    assert client.get("/api/config", headers=AUTH).json()["revision"] == 20


def test_store_write_failure_keeps_the_old_file(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path)
    store.patch({"site.name": "Before"})
    original = (tmp_path / "config.json").read_text()

    def broken_dump(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", broken_dump)
    with pytest.raises(ApiError) as caught:
        store.patch({"site.name": "After"})
    assert caught.value.status == 500 and "disk full" in caught.value.message
    assert (tmp_path / "config.json").read_text() == original
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]
    assert store.get("site.name") == "Before"


def test_a_change_made_by_the_qt_app_is_read_not_overwritten(client):
    client.patch("/api/config", json={"site.name": "Home"}, headers=AUTH)
    path = _config_file(client)
    data = json.loads(path.read_text())
    data["observer"]["name"] = "Written by Qt"
    path.write_text(json.dumps(data, indent=2))
    os.utime(path, ns=(1, 1))  # a different stamp even within one mtime tick
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        client.patch("/api/config", json={"site.name": "Pic du Midi"}, headers=AUTH)
        seen: list = []
        receive_until(events, lambda m: m["type"] == "config" and m["source"] == "api", seen=seen)
    external = [m for m in seen if m["type"] == "config" and m["source"] == "file"]
    assert external and external[0]["changed"] == {"observer.name": "Written by Qt"}
    on_disk = json.loads(path.read_text())
    assert on_disk["observer"]["name"] == "Written by Qt"  # kept
    assert on_disk["site"]["name"] == "Pic du Midi"


def test_unreadable_file_is_kept_aside_before_the_first_write(tmp_path):
    (tmp_path / "config.json").write_text("{ not json")
    store = ConfigStore(tmp_path)
    assert store.load_error is not None
    assert store.values()["alpaca.port"] == 32323  # defaults in use
    store.patch({"site.name": "Home"})
    kept = [p for p in tmp_path.iterdir() if p.name.startswith("config.json.unreadable-")]
    assert len(kept) == 1 and kept[0].read_text() == "{ not json"
    assert json.loads((tmp_path / "config.json").read_text())["site"]["name"] == "Home"


def test_qt_migrations_apply_on_load(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "alpaca": {"profile": "field", "profiles": {"field": {"host": "10.0.0.1"}}},
                "diagnostics": {"enabled": True},
            }
        )
    )
    store = ConfigStore(tmp_path)
    assert store.values()["alpaca.host"] == "10.0.0.1"  # _migrate_alpaca_profiles
    assert store.values()["diagnostics.enabled"] is False  # opt-in policy migration


def test_in_memory_store_never_touches_a_file():
    store = ConfigStore(None)
    assert store.path is None
    store.patch({"site.name": "Home"})
    assert store.get("site.name") == "Home"
    from argos.server.hub import Hub

    assert Hub(settings=Settings(token="t")).config.path is None  # the default for tests


def test_data_paths_and_log_level_apply_when_the_server_owns_the_process(
    make_client, tmp_path, monkeypatch
):
    applied: list[tuple[str, Path]] = []
    for module, name in (
        (runtime.object_resolver, "configure_cache_path"),
        (runtime.exoplanets, "configure_cache_path"),
        (runtime.exoplanets, "configure_field_cache_directory"),
        (runtime.aavso, "configure_cache_directory"),
        (runtime.gaia, "configure_cache_directory"),
        (runtime.field_objects, "configure_cache_directory"),
        (runtime.sensor_reference, "configure_calibration_directory"),
        (runtime.imx585, "configure_calibration_directory"),
    ):
        label = f"{module.__name__.rsplit('.', 1)[1]}.{name}"
        monkeypatch.setattr(module, name, lambda path, label=label: applied.append((label, path)))
    root = logging.getLogger()
    monkeypatch.setattr(root, "level", root.level)  # restored after the test
    client = make_client(manage_process=True)
    assert len(applied) == 8  # at start-up, before the first request
    applied.clear()
    gaia_dir = tmp_path / "gaia"
    client.patch(
        "/api/config", json={"data_paths.gaia_cache_directory": str(gaia_dir)}, headers=AUTH
    )
    assert ("gaia.configure_cache_directory", gaia_dir) in applied
    client.patch("/api/config", json={"ui.log_level": "WARNING"}, headers=AUTH)
    assert root.level == logging.WARNING


def test_debug_lines_follow_the_log_level(client):
    hub = client.app.state.hub
    hub.log("debug", "hidden")
    client.patch("/api/config", json={"ui.log_level": "DEBUG"}, headers=AUTH)
    hub.log("debug", "shown")
    messages = [e["message"] for e in client.get("/api/logs", headers=AUTH).json()["entries"]]
    assert "shown" in messages and "hidden" not in messages
