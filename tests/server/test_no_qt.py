"""argos.server must never import Qt, even transitively.

Run in a fresh interpreter: the test process itself may already have PyQt6
loaded by other suites, and only a clean ``sys.modules`` proves anything.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_PROBE = textwrap.dedent("""
    import importlib, pkgutil, sys, warnings

    BLOCKED = ("PyQt6", "PyQt5", "PySide6", "PySide2", "pyqtgraph", "sip")

    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ImportError(f"Qt import blocked: {name}")
            return None

    sys.meta_path.insert(0, Blocker())
    for name in list(sys.modules):
        if name.split(".")[0] in BLOCKED:
            del sys.modules[name]

    import argos.server
    modules = ["argos.server"]
    for info in pkgutil.walk_packages(argos.server.__path__, "argos.server."):
        importlib.import_module(info.name)
        modules.append(info.name)

    # Exercise the app end to end, not just the imports.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from starlette.testclient import TestClient
    from argos.server.app import create_app
    from argos.server.settings import Settings, SimOptions

    auth = {"Authorization": "Bearer t"}
    app = create_app(Settings(token="t", sim=SimOptions(width=32, height=24, n_stars=5)))
    with TestClient(app, base_url="http://127.0.0.1:8742") as client:
        assert client.get("/api/health").json()["ok"] is True
        assert client.post("/api/connection", json={"mode": "simulator"}, headers=auth).is_success
        assert client.post(
            "/api/camera/capture", json={"exposure_s": 0.01, "gain": 80}, headers=auth
        ).is_success

    leaked = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
    assert not leaked, leaked
    print("OK", len(modules), "modules")
    """)


def test_argos_server_imports_without_qt():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.startswith("OK")
    # Every module of the package was imported, the Alpaca adapter included.
    assert int(result.stdout.split()[1]) >= 14
