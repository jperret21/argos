"""SeerControl — entry point.

Usage:
    python main.py
"""

import sys
import logging

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
