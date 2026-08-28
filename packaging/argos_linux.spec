# PyInstaller spec for the Linux folder bundle used by ``make_deb.sh``.
#
#   uv run --extra package pyinstaller packaging/argos_linux.spec --noconfirm
#   packaging/make_deb.sh
#
# Produces ``dist/Argos/``. The Debian wrapper installs that self-contained
# bundle in /usr/lib/argos and adds an ``argos`` launcher plus desktop entry.
# ASTAP and its star databases deliberately remain external.

import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent
_init = (PROJECT_ROOT / "argos" / "__init__.py").read_text()
_match = re.search(r'__version__\s*=\s*"([^"]+)"', _init)
if not _match:
    raise SystemExit("cannot find __version__ in argos/__init__.py")

datas = [
    (str(PROJECT_ROOT / "argos" / "ui" / "assets"), "argos/ui/assets"),
    (str(PROJECT_ROOT / "argos" / "resources" / "catalogues"), "argos/resources/catalogues"),
    (str(PROJECT_ROOT / "LICENSE"), "."),
]
hiddenimports = collect_submodules("alpaca")
excludes = [
    "PyQt6.QtBluetooth",
    "PyQt6.QtDBus",
    "PyQt6.QtDesigner",
    "PyQt6.QtHelp",
    "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtNetworkAuth",
    "PyQt6.QtNfc",
    "PyQt6.QtPositioning",
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtQuick3D",
    "PyQt6.QtQuickWidgets",
    "PyQt6.QtRemoteObjects",
    "PyQt6.QtSensors",
    "PyQt6.QtSerialPort",
    "PyQt6.QtSpatialAudio",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtTextToSpeech",
    "PyQt6.QtWebChannel",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebSockets",
    "matplotlib",
    "tkinter",
    "pytest",
    "IPython",
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(PROJECT_ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Argos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Argos")
