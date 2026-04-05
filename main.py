"""SeerControl — entry point.

Usage:
    python main.py
"""

import sys
import logging

from PyQt6.QtWidgets import QApplication

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SeerControl")
    app.setOrganizationName("SeerControl")

    # TODO: load config, instantiate MainWindow
    logger.info("SeerControl starting — Phase 1 skeleton")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
