"""QThread worker for Alpaca UDP discovery.

Runs the blocking UDP scan in a background thread and emits
signals when results are available or an error occurs.

Usage:
    worker = DiscoveryWorker(timeout=8.0)
    worker.devices_found.connect(self._on_devices_found)
    worker.error_occurred.connect(self._on_error)
    worker.finished.connect(worker.deleteLater)
    worker.start()
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.alpaca.discovery import AlpacaDevice, discover

logger = logging.getLogger(__name__)


class DiscoveryWorker(QThread):
    """One-shot worker that performs an Alpaca UDP broadcast scan.

    Signals:
        devices_found: Emitted on success with a list of AlpacaDevice.
        error_occurred: Emitted if the scan raises an unexpected exception.
        finished: Emitted when the thread completes (success or error).
    """

    devices_found = pyqtSignal(list)   # list[AlpacaDevice]
    error_occurred = pyqtSignal(str)

    def __init__(self, timeout: float = 8.0, parent=None) -> None:
        super().__init__(parent)
        self._timeout = timeout

    def run(self) -> None:
        logger.debug("DiscoveryWorker started (timeout=%.1fs)", self._timeout)
        try:
            devices = discover(timeout=self._timeout)
            self.devices_found.emit(devices)
        except Exception as exc:
            logger.error("Discovery failed: %s", exc)
            self.error_occurred.emit(str(exc))
