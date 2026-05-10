"""Autofocus worker — runs the V-curve HFD scan in a QThread.

Signals:
    data_point(int, float)   — (position, hfd) for each scan sample
    progress(int, int)       — (current_step, total_steps)
    finished(int, float)     — (best_position, best_hfd) on success
    error_occurred(str)      — on hardware error
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.focuser import Focuser
from seercontrol.core.imaging.autofocus import AutofocusRoutine

logger = logging.getLogger(__name__)


class AutofocusWorker(QThread):
    """Runs AutofocusRoutine and emits results as Qt signals.

    Args:
        focuser:    Connected Focuser instance.
        camera:     Connected Camera instance.
        exposure:   Exposure time per sample (seconds).
        gain:       Camera gain.
        n_steps:    Number of scan positions.
        half_range: ± focuser steps around current position.
    """

    data_point     = pyqtSignal(int, float)   # (position, hfd)
    progress       = pyqtSignal(int, int)     # (current, total)
    finished       = pyqtSignal(int, float)   # (best_position, best_hfd)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        focuser: Focuser,
        camera: Camera,
        exposure: float = 3.0,
        gain: int = 80,
        n_steps: int = 9,
        half_range: int = 1000,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._routine = AutofocusRoutine(
            focuser=focuser,
            camera=camera,
            exposure=exposure,
            gain=gain,
            n_steps=n_steps,
            half_range=half_range,
        )
        self._n_steps = n_steps

    def abort(self) -> None:
        """Request an abort; current exposure finishes first."""
        self._routine.abort()

    def run(self) -> None:
        step = 0
        try:
            for point in self._routine.run():
                step += 1
                self.data_point.emit(point.position, point.hfd)
                self.progress.emit(step, self._n_steps)

            if not self._routine.aborted and self._routine.best_position is not None:
                self.finished.emit(
                    self._routine.best_position,
                    self._routine.best_hfd,
                )
            else:
                logger.info("Autofocus aborted or no valid points")

        except AlpacaError as exc:
            logger.error("AutofocusWorker error: %s", exc)
            self.error_occurred.emit(str(exc))
