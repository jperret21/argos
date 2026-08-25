"""Argos — entry point.

Usage:
    python main.py
"""

import os
import sys
import logging
from pathlib import Path

#: Marker written next to the PyQt6 tree once its quarantine sweep has run.
#: Named for the app so a stray file in site-packages is self-explanatory.
_QT_STAMP_NAME = ".argos-qt-prepared"


def _needs_quarantine_sweep(qt6_root: Path, stamp: Path) -> bool:
    """True when the PyQt6 tree may hold quarantine flags we haven't cleared.

    The sweep is skipped when the stamp exists and is at least as new as the
    PyQt6 directory — a reinstall (uv sync) bumps that mtime and invalidates it.
    """
    if not stamp.exists():
        return True
    try:
        return qt6_root.stat().st_mtime > stamp.stat().st_mtime
    except OSError:
        return True


def _fix_qt_plugin_path() -> None:
    """Fix Qt cocoa plugin loading on macOS uv venvs.

    Two problems to solve:
    1. QT_QPA_PLATFORM_PLUGIN_PATH is not set — Qt can't find the platforms dir.
    2. macOS quarantines freshly-downloaded dylibs — Qt can find the file but
       can't load it (SIP blocks quarantined dylibs).

    run.sh handles both via xattr + env var. This function is the fallback for
    direct invocations (uv run python main.py, IDE launchers).
    Must be called before any QApplication is created.

    The quarantine sweep walks ~2600 files and costs ~11 s, so it runs **once
    per PyQt6 install**, not once per launch — that sweep was the bulk of the
    startup time users saw. A stamp file records that it has been done; a
    reinstall bumps the directory mtime and the sweep runs again.
    """
    if sys.platform != "darwin":
        return

    try:
        import sysconfig
        import subprocess

        site = Path(sysconfig.get_path("purelib"))
        plugin_path = site / "PyQt6" / "Qt6" / "plugins" / "platforms"

        if plugin_path.exists():
            # 1. Set plugin path
            if not os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugin_path)

            # 2. Remove macOS quarantine from the entire PyQt6 tree, once.
            qt6_root = site / "PyQt6"
            stamp = site / _QT_STAMP_NAME
            if _needs_quarantine_sweep(qt6_root, stamp):
                result = subprocess.run(
                    ["xattr", "-dr", "com.apple.quarantine", str(qt6_root)],
                    capture_output=True,
                )
                # Only stamp a sweep that actually succeeded — otherwise a
                # transient failure would silently disable it forever.
                if result.returncode == 0:
                    stamp.touch()
    except Exception:
        pass  # best-effort


_fix_qt_plugin_path()

# E402: these imports run after _fix_qt_plugin_path() on purpose — the env var
# must be set before Qt is imported, and the config/theme stay grouped.
from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.core.config import Config  # noqa: E402
from argos.core.hardware import active as hardware  # noqa: E402
from argos.ui import theme  # noqa: E402
from argos.ui.palettes import PALETTES, EQUILUX  # noqa: E402


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_palette(config: Config) -> None:
    """Apply the palette stored in config (``ui.theme.preset``) before UI init."""
    preset_name: str = config.get("ui.theme.preset", EQUILUX.name)  # type: ignore[assignment]
    palette = PALETTES.get(preset_name, EQUILUX)
    theme.apply_palette(palette)


def _preload_heavy_modules() -> None:
    """Import the scientific stack up front, while the splash is visible.

    numpy, astropy, pyqtgraph and alpyca all arrive through this one import.
    Doing it explicitly is what lets the splash claim the stage is finished
    when it actually is, rather than reporting progress for work that has not
    started yet.
    """
    import argos.ui.shell  # noqa: F401


def _build_window(config: Config):
    """Return the top-level window (the 3-mode Shell)."""
    from argos.ui.shell import Shell

    return Shell(config)


def _make_splash():
    """The startup splash, or ``None`` when suppressed.

    ``ARGOS_NO_SPLASH=1`` skips it — useful when a startup crash would
    otherwise be hidden behind a frameless always-on-top window.
    """
    if os.environ.get("ARGOS_NO_SPLASH"):
        return None
    from argos.ui.splash import Splash

    splash = Splash()
    splash.show()
    return splash


def main() -> None:
    # The QApplication must exist before any widget, including the splash.
    app = QApplication(sys.argv)
    app.setApplicationName("Argos")
    app.setOrganizationName("Argos")

    config = Config.load()
    _setup_logging(config.get("ui.log_level", "INFO"))

    logger = logging.getLogger(__name__)
    logger.info("Argos starting")

    splash = _make_splash()

    def stage(key: str) -> None:
        if splash is not None:
            splash.stage(key)

    try:
        stage("config")

        stage("imports")
        _preload_heavy_modules()

        # Resolve which telescope we are driving before anything reads a spec.
        # Unlike the palette below, nothing binds this at import time —
        # consumers call hardware.profile() at the point of use — so the
        # ordering here is for tidy logs, not correctness.
        stage("profile")
        scope = hardware.load_from_config(config)
        logger.info("Driving %s", scope.describe())

        # Apply the saved palette *before* any widgets are constructed so that
        # all module-level constants are correct at widget construction time.
        # The splash deliberately does not read `theme`, so it is exempt.
        stage("theme")
        _load_palette(config)
        app.setStyleSheet(theme.get_stylesheet())

        stage("shell")
        window = _build_window(config)

        stage("layout")
        window.show()
    except BaseException as exc:
        # A splash left on screen after a crash hides the traceback behind a
        # frameless, always-on-top, undismissable window.
        if splash is not None:
            splash.fail(str(exc))
        raise

    if splash is not None:
        splash.finish(window)

    logger.info("UI ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
