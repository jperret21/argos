"""SeerControl — entry point.

Usage:
    python main.py
"""

import os
import sys
import logging
from pathlib import Path


def _fix_qt_plugin_path() -> None:
    """Set QT_QPA_PLATFORM_PLUGIN_PATH from the active venv if not already set.

    On macOS, Qt cannot auto-discover the cocoa platform plugin inside a uv
    venv. run.sh sets the path via the environment; this fallback handles direct
    invocation (uv run python main.py, IDE launchers, etc.).
    Must be called before any QApplication is created.
    """
    if sys.platform != "darwin":
        return
    if os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return  # already set by run.sh or caller

    try:
        import sysconfig
        site = Path(sysconfig.get_path("purelib"))
        plugin_path = site / "PyQt6" / "Qt6" / "plugins" / "platforms"
        if plugin_path.exists():
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugin_path)
    except Exception:
        pass  # best-effort — will surface as a Qt startup error if wrong


_fix_qt_plugin_path()

from PyQt6.QtWidgets import QApplication

from seercontrol.core.config import Config
from seercontrol.ui.main_window import MainWindow
from seercontrol.ui.theme import get_stylesheet


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    config = Config.load()
    _setup_logging(config.get("ui.log_level", "INFO"))

    logger = logging.getLogger(__name__)
    logger.info("SeerControl starting")

    app = QApplication(sys.argv)
    app.setApplicationName("SeerControl")
    app.setOrganizationName("SeerControl")
    app.setStyleSheet(get_stylesheet())

    window = MainWindow(config)
    window.show()

    logger.info("UI ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
