"""Background bridge for the CDS object-name resolver."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.catalog.object_resolver import ObjectResolutionError, resolve_object


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
