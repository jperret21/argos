# PyInstaller spec for the macOS Argos.app bundle.
#
#   uv run --extra package pyinstaller packaging/argos.spec --noconfirm
#
# Produces dist/Argos.app. packaging/make_dmg.sh wraps it into a .dmg.
#
# The bundle is **unsigned**: Argos has no Apple Developer account, so
# Gatekeeper will refuse the first launch until the user right-clicks → Open
# (see README). Signing and notarisation are a 0.5 concern.
#
# ASTAP is deliberately NOT bundled — it is a separately licensed binary whose
# star databases run to gigabytes. The auto-detection in
# core/imaging/platesolve.py keeps finding a user-installed copy.

import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent

# Read the version out of argos/__init__.py rather than importing the package:
# the spec runs inside PyInstaller's analysis process, where importing the app
# would drag in Qt for nothing.
_init = (PROJECT_ROOT / "argos" / "__init__.py").read_text()
_match = re.search(r'__version__\s*=\s*"([^"]+)"', _init)
if not _match:
    raise SystemExit("cannot find __version__ in argos/__init__.py")
VERSION = _match.group(1)

# Assets referenced at runtime by path (the splash logo). Anything read with
# Path(__file__).parent must be listed here or it vanishes in the bundle.
datas = [
    (str(PROJECT_ROOT / "argos" / "ui" / "assets"), "argos/ui/assets"),
    (str(PROJECT_ROOT / "argos" / "resources" / "catalogues"), "argos/resources/catalogues"),
    (str(PROJECT_ROOT / "LICENSE"), "."),
]

# alpyca resolves device classes lazily, so PyInstaller's static analysis
# misses them.
hiddenimports = collect_submodules("alpaca")

# Qt modules Argos never touches. Dropping them keeps the bundle to a size
# people will actually download over a field hotspot.
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
    # Test/plotting stacks that ride in on scientific dependencies.
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
    # Our hooks take precedence over pyinstaller-hooks-contrib — see
    # packaging/hooks/hook-astropy.py for why astropy needs its own.
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
    upx=False,  # UPX breaks Qt frameworks on macOS
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # native arch; a universal2 build needs universal deps
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
    name="Argos",
)

app = BUNDLE(
    coll,
    name="Argos.app",
    icon=str(PROJECT_ROOT / "packaging" / "argos.icns"),
    bundle_identifier="org.argos.argos",
    version=VERSION,
    info_plist={
        "CFBundleName": "Argos",
        "CFBundleDisplayName": "Argos",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "GNU GPL v3 — free software, with no warranty",
        # Argos discovers the Seestar by UDP broadcast and talks to it over
        # HTTP; macOS 15+ prompts for local-network access without this.
        "NSLocalNetworkUsageDescription": (
            "Argos needs the local network to discover and control your Seestar telescope."
        ),
        "LSMinimumSystemVersion": "11.0",
    },
)
