"""The desktop app's packaging stays in step with the tree (W8).

- One version source: ``argos/__init__.py`` ``__version__``. The Tauri shell
  (``web/src-tauri/Cargo.toml``, which ``tauri.conf.json`` follows by setting
  no version of its own) must say the same; ``build.rs`` refuses a mismatch at
  build time, this test catches it in the Python suite (CI builds no Rust).
- The one-dir sidecar goes where ``sidecar.rs`` looks for it.
- The .deb's desktop entry keeps the categories and keywords of
  ``packaging/argos.desktop``.
- PyQt6 and pyqtgraph are not runtime dependencies (the ``qt`` extra).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import argos

ROOT = Path(__file__).resolve().parents[2]
SHELL = ROOT / "web" / "src-tauri"


def _desktop_entry(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def test_shell_version_is_the_application_version() -> None:
    cargo = tomllib.loads((SHELL / "Cargo.toml").read_text(encoding="utf-8"))
    assert cargo["package"]["version"] == argos.__version__
    lock = (SHELL / "Cargo.lock").read_text(encoding="utf-8")
    locked = re.search(r'name = "argos-desktop"\nversion = "([^"]+)"', lock)
    assert locked and locked.group(1) == argos.__version__
    conf = json.loads((SHELL / "tauri.conf.json").read_text(encoding="utf-8"))
    assert "version" not in conf, "tauri.conf.json must follow Cargo.toml"


def test_sidecar_is_bundled_one_dir_where_the_shell_looks() -> None:
    conf = json.loads((SHELL / "tauri.conf.json").read_text(encoding="utf-8"))
    bundle = conf["bundle"]
    assert "externalBin" not in bundle, "one-dir, not a one-file externalBin"
    assert bundle["macOS"]["files"] == {"Resources/argos-server": "binaries/argos-server"}
    deb = bundle["linux"]["deb"]["files"]
    assert deb["/usr/lib/argos/argos-server"] == "binaries/argos-server"
    assert (SHELL / deb["/usr/share/doc/argos/copyright"]).resolve() == ROOT / "LICENSE"
    sidecar = (SHELL / "src" / "sidecar.rs").read_text(encoding="utf-8")
    assert '"../Resources"' in sidecar and '"../lib/argos"' in sidecar
    spec = (ROOT / "packaging" / "argos_server.spec").read_text(encoding="utf-8")
    assert "COLLECT(" in spec and 'name="argos-server"' in spec


def test_deb_desktop_entry_keeps_the_categories() -> None:
    conf = json.loads((SHELL / "tauri.conf.json").read_text(encoding="utf-8"))
    template = (SHELL / conf["bundle"]["linux"]["deb"]["desktopTemplate"]).resolve()
    tauri_entry = _desktop_entry(template)
    qt_entry = _desktop_entry(ROOT / "packaging" / "argos.desktop")
    for key in ("Type", "Comment", "Terminal", "Categories", "Keywords"):
        assert tauri_entry[key] == qt_entry[key], key
    assert tauri_entry["Exec"] == "{{exec}}" and tauri_entry["Icon"] == "{{icon}}"


def test_qt_is_an_extra_not_a_runtime_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names = {
        re.split(r"[<>=!~ \[;]", dep, maxsplit=1)[0].lower() for dep in project["dependencies"]
    }
    assert not names & {"pyqt6", "pyqt6-qt6", "pyqtgraph"}
    extras = {
        extra: {re.split(r"[<>=!~ \[;]", dep, maxsplit=1)[0].lower() for dep in deps}
        for extra, deps in project["optional-dependencies"].items()
    }
    assert extras["qt"] == {"pyqt6", "pyqt6-qt6", "pyqtgraph", "pytest-qt"}
    # "--extra dev --extra server" runs tests/server with no Qt (pytest-qt would refuse).
    for extra in ("dev", "server", "package"):
        assert not extras[extra] & extras["qt"], extra


def test_project_version_is_the_application_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == argos.__version__


def test_sidecar_ships_the_files_the_server_loads_by_path() -> None:
    # argos/server/review.py loads argos/core/session/review.py from its file (its package
    # imports PyQt6); without the source in the bundle, Review fails in the desktop app.
    review = (ROOT / "argos" / "server" / "review.py").read_text(encoding="utf-8")
    assert '"core" / "session" / "review.py"' in review
    spec = (ROOT / "packaging" / "argos_server.spec").read_text(encoding="utf-8")
    assert '"argos" / "core" / "session" / "review.py"' in spec
    assert '(str(CORE_REVIEW), "argos/core/session")' in spec
    imports = re.findall(
        r"^from (argos\.[\w.]+) import",
        (ROOT / "argos" / "core" / "session" / "review.py").read_text(encoding="utf-8"),
        re.M,
    )
    for module in imports:
        assert f'"{module}"' in spec, module


def test_self_check_loads_the_modules_read_by_path(capsys) -> None:
    # The release workflow runs `argos-server --self-check` on the frozen sidecar
    # (packaging/smoke_sidecar.py): it must load argos/core/session/review.py by its path.
    from argos.server.__main__ import main

    assert main(["--self-check"]) == 0
    out = capsys.readouterr().out
    assert str(Path("argos") / "core" / "session" / "review.py") in out
    assert out.rstrip().endswith("self-check: ok")
    smoke = (ROOT / "packaging" / "smoke_sidecar.py").read_text(encoding="utf-8")
    assert '"--self-check"' in smoke
