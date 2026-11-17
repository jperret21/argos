"""Read-only folder listing for the in-app picker (row A11): limits, links, filters.

Every test runs with HOME and every ARGOS data folder inside a temporary
tree; "outside" is a sibling folder of that tree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.server.conftest import AUTH

DATA_KEYS = {
    "sessions_path": "data/sessions",
    "data_paths.sequence_presets_directory": "data/sequences",
    "data_paths.camera_calibration_directory": "data/calibrations",
    "data_paths.object_catalogue_cache": "data/cache/object_resolver.json",
    "data_paths.exoplanet_cache": "data/cache/exoplanets.json",
    "data_paths.aavso_cache_directory": "data/cache/catalog",
    "data_paths.gaia_cache_directory": "data/cache/gaia",
    "data_paths.field_catalogue_cache_directory": "data/cache/field_catalogue",
}


def isolate(client, monkeypatch, base: Path) -> dict[str, Path]:
    """HOME = base/home; every data path under base/home/data (no real folder touched)."""
    home = base / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    paths = {key: home / rel for key, rel in DATA_KEYS.items()}
    response = client.patch("/api/config", json={k: str(v) for k, v in paths.items()}, headers=AUTH)
    assert response.status_code == 200, response.text
    return {"home": home, **paths}


@pytest.fixture
def tree(client, monkeypatch, tmp_path):
    paths = isolate(client, monkeypatch, tmp_path)
    home = paths["home"]
    sessions = paths["sessions_path"]
    (sessions / "20260925T200453Z_RR_Lyr" / "lights").mkdir(parents=True)
    for i in range(3):
        (sessions / "20260925T200453Z_RR_Lyr" / "lights" / f"f{i}.FITS").write_bytes(b"x")
    (sessions / "20260925T200453Z_RR_Lyr" / "lights" / "notes.txt").write_text("n")
    (sessions / "20260925T200453Z_RR_Lyr" / "session.json").write_text("{}")
    (home / "Desktop").mkdir()
    (home / ".hidden").mkdir()
    (home / "b.fit").write_bytes(b"12345")
    (home / "a.json").write_text("{}")
    outside = tmp_path / "outside"
    (outside / "secret").mkdir(parents=True)
    (outside / "secret.fits").write_bytes(b"s")
    return {**paths, "outside": outside}


def _list(client, **params):
    return client.get("/api/fs/list", params=params, headers=AUTH)


def test_default_is_the_sessions_folder(client, tree):
    body = _list(client).json()
    assert body["path"] == str(Path(os.path.realpath(tree["sessions_path"])))
    assert [e["name"] for e in body["entries"]] == ["20260925T200453Z_RR_Lyr"]
    entry = body["entries"][0]
    assert entry["kind"] == "dir" and entry["size"] is None and entry["fits_count"] is None
    assert body["truncated"] is False
    places = {p["id"]: p for p in body["places"]}
    assert {"home", "desktop", "sessions", "presets", "calibrations"} <= set(places)
    assert places["home"]["path"] == str(tree["home"])
    assert places["sessions"]["exists"] is True


def test_folders_first_hidden_left_out_and_filters(client, tree):
    home = str(tree["home"])
    names = [e["name"] for e in _list(client, path=home).json()["entries"]]
    assert names == ["data", "Desktop", "a.json", "b.fit"]  # folders first, case-insensitive
    assert ".hidden" in [
        e["name"] for e in _list(client, path=home, hidden="true").json()["entries"]
    ]
    dirs = _list(client, path=home, kind="dir").json()["entries"]
    assert {e["kind"] for e in dirs} == {"dir"}
    fits = _list(client, path=home, kind="file", ext=".fits,.FIT,fts").json()["entries"]
    assert [e["name"] for e in fits] == ["data", "Desktop", "b.fit"]
    b = next(e for e in fits if e["name"] == "b.fit")
    assert b["size"] == 5 and b["mtime"].endswith("Z") and b["symlink"] is False


def test_fits_counts_one_level(client, tree):
    session = tree["sessions_path"] / "20260925T200453Z_RR_Lyr"
    body = _list(client, path=str(session), counts="fits").json()
    lights = next(e for e in body["entries"] if e["name"] == "lights")
    assert lights["fits_count"] == 3  # the .txt is not counted
    assert body["parent"] == str(Path(os.path.realpath(tree["sessions_path"])))


def test_outside_the_roots_is_forbidden(client, tree):
    for path in (str(tree["outside"]), "/", "/etc", str(tree["home"] / ".." / "outside")):
        response = _list(client, path=path)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "forbidden_path"


def test_parent_stops_at_the_top_of_a_root(client, tree):
    body = _list(client, path=str(tree["home"])).json()
    assert body["parent"] is None
    assert body["root"] == str(tree["home"])


def test_bad_paths(client, tree):
    relative = _list(client, path="data/sessions")
    assert relative.status_code == 400 and relative.json()["error"]["code"] == "invalid_argument"
    missing = _list(client, path=str(tree["home"] / "nope"))
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    a_file = _list(client, path=str(tree["home"] / "a.json"), kind="dir")
    assert a_file.status_code == 400 and "not a folder" in a_file.json()["error"]["message"]
    bad_kind = _list(client, path=str(tree["home"]), kind="everything")
    assert bad_kind.status_code == 400


def test_a_nul_byte_is_a_400_not_a_500(client, tree):
    """Technical review: os.path.realpath raised ValueError, answered 500 internal_error."""
    response = _list(client, path=f"{tree['home']}\x00/x")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_argument"
    bundle = client.post(
        "/api/support-bundle", json={"destination": f"{tree['home']}/a\x00b.zip"}, headers=AUTH
    )
    assert bundle.status_code == 400, bundle.text
    assert bundle.json()["error"]["code"] == "invalid_argument"


@pytest.mark.skipif(sys.platform != "darwin", reason="a case-insensitive APFS volume")
def test_a_root_typed_in_another_case_is_listed(client, tree):
    """macOS: realpath keeps the typed case; the folder is respelled from the disk."""
    home = tree["home"]
    upper = str(home.parent / home.name.upper())
    if not os.path.isdir(upper):
        pytest.skip("this volume is case-sensitive")
    body = _list(client, path=upper)
    assert body.status_code == 200, body.text
    assert body.json()["path"] == str(home)
    # Respelling never widens the roots: the sibling folder stays forbidden in any case.
    outside = str(tree["outside"].parent / tree["outside"].name.upper())
    assert _list(client, path=outside).status_code == 403


def test_true_case_keeps_meaning(tmp_path):
    from argos.server.fs import _true_case

    (tmp_path / "Data" / "Sub").mkdir(parents=True)
    assert _true_case(tmp_path / "Data" / "Sub") == tmp_path / "Data" / "Sub"
    # A missing tail stays as typed (a file still to be written).
    assert _true_case(tmp_path / "Data" / "new.zip") == tmp_path / "Data" / "new.zip"
    respelled = _true_case(tmp_path / "data" / "sub")
    if os.path.isdir(tmp_path / "data"):  # case-insensitive volume
        assert respelled == tmp_path / "Data" / "Sub"
    else:  # case-sensitive: "data" is another (missing) folder, never respelled
        assert respelled == tmp_path / "data" / "sub"


def test_tilde_is_expanded(client, tree):
    body = _list(client, path="~").json()
    assert body["path"] == str(tree["home"])


def test_symlinks_cannot_escape(client, tree):
    home, outside = tree["home"], tree["outside"]
    (home / "escape_dir").symlink_to(outside / "secret", target_is_directory=True)
    (home / "escape_file.fits").symlink_to(outside / "secret.fits")
    (home / "broken").symlink_to(home / "does-not-exist")
    (home / "inside_link").symlink_to(tree["sessions_path"], target_is_directory=True)
    names = {e["name"]: e for e in _list(client, path=str(home)).json()["entries"]}
    assert "escape_dir" not in names and "escape_file.fits" not in names
    assert "broken" not in names
    assert names["inside_link"]["symlink"] is True and names["inside_link"]["kind"] == "dir"
    # Asking for the link itself resolves it first: outside, refused.
    response = _list(client, path=str(home / "escape_dir"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_path"
    # A link that stays inside resolves to the real folder.
    inside = _list(client, path=str(home / "inside_link")).json()
    assert inside["path"] == str(Path(os.path.realpath(tree["sessions_path"])))


def test_a_data_folder_on_another_disk_stays_browsable(client, monkeypatch, tmp_path, tree):
    """sessions_path outside home (an external disk) is itself a root."""
    external = tmp_path / "Volumes" / "Data" / "sessions"
    (external / "night").mkdir(parents=True)
    client.patch("/api/config", json={"sessions_path": str(external)}, headers=AUTH)
    body = _list(client, path=str(external)).json()
    assert [e["name"] for e in body["entries"]] == ["night"]
    assert body["parent"] is None  # its folder above is not a root
    assert _list(client, path=str(external.parent)).status_code == 403


def test_unreadable_folder_is_forbidden(client, tree):
    locked = tree["home"] / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        if os.access(locked, os.R_OK):
            pytest.skip("running with privileges that ignore permissions")
        response = _list(client, path=str(locked))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden_path"
    finally:
        locked.chmod(0o755)


def test_listing_needs_the_token(client, tree):
    assert client.get("/api/fs/list").status_code == 401


def test_nothing_is_written(client, tree):
    before = sorted(str(p) for p in tree["home"].rglob("*"))
    _list(client, path=str(tree["home"]), counts="fits")
    _list(client)
    assert sorted(str(p) for p in tree["home"].rglob("*")) == before


def test_a_typed_file_path_lists_its_folder_with_the_file_selected(client, tree):
    """Wave 4 follow-up: the FilePicker answered 400 to a typed file path."""
    home = Path(os.path.realpath(tree["home"]))
    body = _list(client, path=str(tree["home"] / "a.json"), kind="file", ext=".json").json()
    assert body["path"] == str(home) and body["selected"] == "a.json"
    assert "a.json" in [e["name"] for e in body["entries"]]
    assert _list(client, path=str(tree["home"] / "a.json")).json()["selected"] == "a.json"
    wrong = _list(client, path=str(tree["home"] / "a.json"), kind="file", ext=".fits,.fit")
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "invalid_argument"
    assert wrong.json()["error"]["message"] == "a.json is not a .fits/.fit file"
    assert _list(client, path=str(tree["home"])).json()["selected"] is None
