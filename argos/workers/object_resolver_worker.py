"""Background bridge for the CDS object-name resolver."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.catalog.object_resolver import (
    ObjectResolutionError,
    resolve_nearby_objects,
    resolve_object,
)


class ObjectResolverWorker(QThread):
    """Resolve one object name without ever blocking the Qt event loop."""

    resolved = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, query: str, parent=None) -> None:
        super().__init__(parent)
        self._query = query

    def run(self) -> None:
        try:
            self.resolved.emit(resolve_object(self._query))
        except ObjectResolutionError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Object lookup failed unexpectedly. See the log for details.")


class NearbyObjectResolverWorker(QThread):
    """Resolve catalogue candidates around a Stellarium coordinate off the UI thread."""

    resolved = pyqtSignal(object)  # list[NearbyObject]
    failed = pyqtSignal(str)

    def __init__(
        self, ra_hours: float, dec_degrees: float, allow_network: bool, parent=None
    ) -> None:
        super().__init__(parent)
        self._ra_hours = ra_hours
        self._dec_degrees = dec_degrees
        self._allow_network = allow_network

    def run(self) -> None:
        try:
            self.resolved.emit(
                resolve_nearby_objects(
                    self._ra_hours * 15.0,
                    self._dec_degrees,
                    allow_network=self._allow_network,
                )
            )
        except ObjectResolutionError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Target-name lookup failed unexpectedly. See the log for details.")
