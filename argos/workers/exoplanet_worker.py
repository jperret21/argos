"""Background bridge for NASA Exoplanet Archive lookups."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.catalog.exoplanets import ExoplanetLookupError, lookup_exoplanet


class ExoplanetLookupWorker(QThread):
    """Retrieve one exoplanet ephemeris without blocking the Qt event loop."""

    resolved = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, query: str, parent=None) -> None:
        super().__init__(parent)
        self._query = query

    def run(self) -> None:
        try:
            self.resolved.emit(lookup_exoplanet(self._query))
        except ExoplanetLookupError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Planet lookup failed unexpectedly. See the local log for details.")
