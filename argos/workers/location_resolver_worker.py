"""Background worker for an explicit observing-site search."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.location_resolver import LocationResolutionError, search_locations


class LocationResolverWorker(QThread):
    """Query place and elevation services without blocking Settings."""

    resolved = pyqtSignal(object)  # list[LocationResult]
    failed = pyqtSignal(str)

    def __init__(self, query: str, parent=None) -> None:
        super().__init__(parent)
        self._query = query

    def run(self) -> None:
        try:
            self.resolved.emit(search_locations(self._query))
        except LocationResolutionError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Location search failed unexpectedly.")
