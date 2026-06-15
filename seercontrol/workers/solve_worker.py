"""SolveWorker — runs an ASTAP plate-solve off the UI thread (§6).

Solving spawns an external process that can take seconds; doing it on the UI
thread would freeze the app. This QThread runs :func:`solve_array` and reports
the result back via a signal.
"""

from __future__ import annotations

import logging

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from seercontrol.core.imaging.platesolve import SolveResult, SolveSettings, solve_array

logger = logging.getLogger(__name__)


class SolveWorker(QThread):
    """Plate-solve one green-plane array and emit the :class:`SolveResult`.

    Signals:
        solved(object): a SolveResult (check ``.solved``).
    """

    solved = pyqtSignal(object)

    def __init__(self, green: np.ndarray, settings: SolveSettings, parent=None) -> None:
        super().__init__(parent)
        self._green = green
        self._settings = settings

    def run(self) -> None:
        try:
            result = solve_array(self._green, self._settings)
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Plate-solve crashed")
            result = SolveResult(False, message=str(exc))
        self.solved.emit(result)
