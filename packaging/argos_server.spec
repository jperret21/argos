# PyInstaller spec for the headless ARGOS server: the Tauri desktop app's
# sidecar (web/src-tauri), frozen ONE-DIR (owner decision W8).
#
#   python -m PyInstaller packaging/argos_server.spec --noconfirm \
#       --distpath web/src-tauri/binaries --workpath <build>
#
# gives web/src-tauri/binaries/argos-server/ (the executable `argos-server`
# and `_internal/`), which tauri.conf.json copies into the bundles:
# `bundle.macOS.files` to ARGOS.app/Contents/Resources/argos-server/,
# `bundle.linux.deb.files` to /usr/lib/argos/argos-server/. Freeze it on the
# machine of each target (macOS arm64, Linux x86_64): the folder is native.
#
# Build it from an environment with the runtime dependencies, the `server`
# extra and `pyinstaller` (the `package` extra), without the `qt` extra:
# the server never imports Qt (tests/server/test_no_qt.py), Qt is excluded
# below, and the build fails if any Qt module is collected all the same.
#
# One-dir rather than one-file: the server starts in about 1 s instead of
# about 16 s (a one-file bootloader unpacks some 100 MB into $TMPDIR at each
# start), runs as a single process (no bootloader parent to forward
# signals) and leaves no _MEI folder behind after a SIGKILL.
#
# Signing: PyInstaller signs each collected binary ad hoc. Under the
# hardened runtime, library validation would refuse them ("different Team
# IDs"), so the Tauri bundle signs ad hoc without it (tauri.conf.json
# `hardenedRuntime: false`); there is no notarisation (owner decision W8).
#
# ASTAP is not bundled (separately licensed, gigabytes of star databases): the
# server finds a user-installed copy, as the Qt app does (packaging/argos.spec).

import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent

# Files the server reads by path at runtime: the bundled offline catalogue
# (argos/core/catalog/offline.py) and argos/core/session/review.py, which
# argos/server/review.py loads from its file (core_review: the package's
# __init__ imports PyQt6), so the frozen Review needs the source next to the
# archive. The Qt splash assets are not needed.
CORE_REVIEW = PROJECT_ROOT / "argos" / "core" / "session" / "review.py"
datas = [
    (str(PROJECT_ROOT / "argos" / "resources" / "catalogues"), "argos/resources/catalogues"),
    (str(CORE_REVIEW), "argos/core/session"),
    (str(PROJECT_ROOT / "LICENSE"), "."),
]

hiddenimports = (
    # alpyca resolves device classes lazily.
    collect_submodules("alpaca")
    # uvicorn picks its loop, HTTP and WebSocket implementations by name.
    + collect_submodules("uvicorn")
    # Every server module, including those only imported inside functions.
    + collect_submodules("argos.server")
    # What the path-loaded core review imports (not seen by the analysis).
    + ["argos.core.imaging.session_log", "argos.core.catalog.targets"]
    + ["argos.core.photometry.lightcurve"]
)

#: Top-level packages that must never reach the server bundle.
QT_PACKAGES = ("PyQt6", "PyQt5", "PySide6", "PySide2", "pyqtgraph", "sip", "shiboken6")

excludes = [
    *QT_PACKAGES,
    # The Qt app's own packages.
    "argos.ui",
    "argos.workers",
    # Test and plotting stacks that ride in on scientific dependencies.
    "matplotlib",
    "tkinter",
    "_tkinter",
    "pytest",
    "IPython",
]

a = Analysis(
    [str(PROJECT_ROOT / "argos" / "server" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    # packaging/hooks/hook-astropy.py shadows the contrib hook (see there).
    hookspath=[str(PROJECT_ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)


def _top_level(name):
    return re.split(r"[./\\]", name, maxsplit=1)[0]


_qt = sorted(
    {
        entry[0]
        for entry in (*a.pure, *a.binaries, *a.datas)
        if _top_level(entry[0]) in QT_PACKAGES or "Qt6" in entry[0]
    }
)
if _qt:
    raise SystemExit(f"Qt in the server bundle ({len(_qt)} entries), first: {_qt[:5]}")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="argos-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # native arch
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="argos-server",
)
