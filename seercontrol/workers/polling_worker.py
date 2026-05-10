"""QThread worker for continuous mount status polling.

Reads position, tracking, and slewing state from the mount every
POLL_INTERVAL_MS milliseconds and emits a signal with fresh data.

The worker runs until stop() is called, then exits cleanly.

Usage:
    worker = MountPollingWorker(telescope)
    worker.position_updated.connect(self._on_position)
    worker.error_occurred.connect(self._on_poll_error)
    worker.start()
    # ...
    worker.stop()
    worker.wait()
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.telescope import MountPosition, Telescope

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 2000


class MountPollingWorker(QThread):
    """Continuously polls the mount and emits position updates.

    Signals:
        position_updated: Emitted every poll cycle with the latest MountPosition.
        error_occurred: Emitted when a poll fails. Polling continues after errors.
        connection_lost: Emitted when the device becomes unreachable.
    """

    position_updated = pyqtSignal(object)   # MountPosition
    error_occurred = pyqtSignal(str)
    connection_lost = pyqtSignal()

    def __init__(self, telescope: Telescope, parent=None) -> None:
        super().__init__(parent)
        self._telescope = telescope
        self._running = False
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3

    def run(self) -> None:
        self._running = True
        self._consecutive_errors = 0
        logger.info("MountPollingWorker started (interval=%dms)", POLL_INTERVAL_MS)

        while self._running:
            self._poll()
            self.msleep(POLL_INTERVAL_MS)

        logger.info("MountPollingWorker stopped")

    def stop(self) -> None:
        """Request the polling loop to stop. Call wait() after to join the thread."""
        self._running = False

    def _poll(self) -> None:
        try:
            position = self._telescope.get_position()
            self._consecutive_errors = 0
            self.position_updated.emit(position)

        except AlpacaError as exc:
            # Telescope.get_position wraps every backend error in the base
            # AlpacaError class, so we must catch the base type — catching
            # only AlpacaConnectionError / AlpacaTimeoutError would miss every
            # real-world failure and connection_lost would never fire.
            self._consecutive_errors += 1
            logger.warning(
                "Poll failed (%d/%d): %s",
                self._consecutive_errors,
                self._max_consecutive_errors,
                exc,
            )
            self.error_occurred.emit(str(exc))

            if self._consecutive_errors >= self._max_consecutive_errors:
                logger.error("Too many consecutive poll errors — declaring connection lost")
                self.connection_lost.emit()
                self._running = False

        except Exception as exc:
            logger.error("Unexpected error during poll: %s", exc)
            self.error_occurred.emit(str(exc))
