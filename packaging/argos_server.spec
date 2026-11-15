# PyInstaller spec for the headless ARGOS server: the Tauri desktop app's
# sidecar (web/src-tauri, `bundle.externalBin`).
#
#   python -m PyInstaller packaging/argos_server.spec --noconfirm \
#       --distpath <dist> --workpath <build>
#   cp <dist>/argos-server \
#       web/src-tauri/binaries/argos-server-$(rustc --print host-tuple)
#
# Build it from an environment with the runtime dependencies, the `server`
# extra and `pyinstaller` (the `package` extra). PyQt6 and pyqtgraph need not
# be installed: the server never imports Qt (tests/server/test_no_qt.py), they
# are excluded below, and the build fails if any Qt module is collected.
#
# One file, because externalBin is a single executable. The bootloader
# unpacks the bundle into $TMPDIR at each start, forwards SIGTERM / SIGINT to
# the Python process and removes the folder when it ends.
#
# Signing: the bootloader dlopens the unpacked libpython and extension
# modules, ad-hoc signed by PyInstaller. Under the hardened runtime, library
# validation refuses them ("different Team IDs"), so the Tauri bundle signs
# ad hoc without it (tauri.conf.json `hardenedRuntime: false`). Notarisation
# needs the hardened runtime: an open W8 item.
#
# ASTAP is not bundled (separately licensed, gigabytes of star databases): the
# server finds a user-installed copy, as the Qt app does (packaging/argos.spec).

import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent

# Files the server reads by path at runtime: the bundled offline catalogue
# (argos/core/catalog/offline.py). The Qt splash assets are not needed.
datas = [
    (str(PROJECT_ROOT / "argos" / "resources" / "catalogues"), "argos/resources/catalogues"),
    (str(PROJECT_ROOT / "LICENSE"), "."),
]

hiddenimports = (
    # alpyca resolves device classes lazily.
    collect_submodules("alpaca")
    # uvicorn picks its loop, HTTP and WebSocket implementations by name.
    + collect_submodules("uvicorn")
    # Every server module, including those only imported inside functions.
    + collect_submodules("argos.server")
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
    a.binaries,
    a.datas,
    [],
    name="argos-server",
    debug=False,
    bootloader_ignore_signals=False,  # forward SIGTERM / SIGINT to Python
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # native arch
    codesign_identity=None,
    entitlements_file=None,
)
