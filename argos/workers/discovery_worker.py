"""QThread worker for Alpaca discovery (UDP broadcast + TCP fallbacks).

Runs the blocking layered scan (:func:`argos.core.alpaca.discovery.discover_all`)
in a background thread and emits signals when results are available or an
error occurs.

Usage:
    worker = DiscoveryWorker(port=32323, candidates=("192.168.1.42",))
    worker.devices_found.connect(self._on_devices_found)
    worker.error_occurred.connect(self._on_error)
    worker.finished.connect(worker.deleteLater)
    worker.start()
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.alpaca.discovery import discover_all

logger = logging.getLogger(__name__)


class DiscoveryWorker(QThread):
    """One-shot worker that performs the layered Alpaca discovery.

    Signals:
        devices_found: Emitted on success with a list of AlpacaDevice.
        error_occurred: Emitted if the scan raises an unexpected exception.
        finished: Emitted when the thread completes (success or error).
    """

    devices_found = pyqtSignal(list)  # list[AlpacaDevice]
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        port: int = 32323,
        candidates: tuple[str, ...] = (),
        timeout: float = 8.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._port = port
        self._candidates = candidates
        self._timeout = timeout

    def run(self) -> None:
        logger.debug(
            "DiscoveryWorker started (port=%d, candidates=%s, timeout=%.1fs)",
            self._port,
            self._candidates,
            self._timeout,
        )
        try:
            devices = discover_all(
                self._port, candidates=self._candidates, broadcast_timeout=self._timeout
            )
            self.devices_found.emit(devices)
        except Exception as exc:
            logger.error("Discovery failed: %s", exc)
            self.error_occurred.emit(str(exc))
