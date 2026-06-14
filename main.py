"""SeerControl — entry point.

Usage:
    python main.py
"""

import os
import sys
import logging
from pathlib import Path


def _fix_qt_plugin_path() -> None:
    """Fix Qt cocoa plugin loading on macOS uv venvs.

    Two problems to solve:
    1. QT_QPA_PLATFORM_PLUGIN_PATH is not set — Qt can't find the platforms dir.
    2. macOS quarantines freshly-downloaded dylibs — Qt can find the file but
       can't load it (SIP blocks quarantined dylibs).

    run.sh handles both via xattr + env var. This function is the fallback for
    direct invocations (uv run python main.py, IDE launchers).
    Must be called before any QApplication is created.
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

            # 2. Remove macOS quarantine from the entire PyQt6 tree (idempotent)
            qt6_root = site / "PyQt6"
            subprocess.run(
                ["xattr", "-dr", "com.apple.quarantine", str(qt6_root)],
                capture_output=True,
            )
    except Exception:
        pass  # best-effort


_fix_qt_plugin_path()

# E402: these imports run after _fix_qt_plugin_path() on purpose — the env var
# must be set before Qt is imported, and the config/theme stay grouped.
from PyQt6.QtWidgets import QApplication  # noqa: E402

from seercontrol.core.config import Config  # noqa: E402
from seercontrol.ui.theme import get_stylesheet  # noqa: E402


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_window(config: Config):
    """Return the top-level window (the 3-mode Shell)."""
    from seercontrol.ui.shell import Shell

    return Shell(config)


def main() -> None:
    config = Config.load()
    _setup_logging(config.get("ui.log_level", "INFO"))

    logger = logging.getLogger(__name__)
    logger.info("SeerControl starting")

    app = QApplication(sys.argv)
    app.setApplicationName("SeerControl")
    app.setOrganizationName("SeerControl")
    app.setStyleSheet(get_stylesheet())

    window = _build_window(config)
    window.show()

    logger.info("UI ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
