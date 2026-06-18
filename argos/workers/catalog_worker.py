"""CatalogWorker — fetch VSX/VSP catalog objects off the UI thread.

A catalog query is an HTTP round-trip that can take seconds; on the UI thread it
would freeze the app. This QThread runs the queries and emits the bundled result
back via a signal, mirroring :mod:`argos.workers.solve_worker`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.catalog import (
    CatalogError,
    ComparisonStar,
    VariableStar,
    vsp_chart,
    vsx_cone_search,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogRequest:
    """A field query, derived from a solved frame's WCS."""

    ra_deg: float
    dec_deg: float
    radius_deg: float  # cone radius for VSX (half the frame diagonal)
    fov_arcmin: float  # chart field of view for VSP
    mag_limit: float = 15.0
    max_results: int = 250
    include_suspected: bool = True
    want_comparisons: bool = True


@dataclass
class CatalogResult:
    """Outcome of a :class:`CatalogRequest`. ``error`` is empty on success."""

    variables: list[VariableStar] = field(default_factory=list)
    comparisons: list[ComparisonStar] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


class CatalogWorker(QThread):
    """Run a VSX (+VSP) field query and emit the :class:`CatalogResult`.

    Signals:
        fetched(object): a CatalogResult (check ``.ok``).
    """

    fetched = pyqtSignal(object)

    def __init__(self, request: CatalogRequest, parent=None) -> None:
        super().__init__(parent)
        self._req = request

    def run(self) -> None:
        r = self._req
        try:
            variables = vsx_cone_search(
                r.ra_deg,
                r.dec_deg,
                r.radius_deg,
                include_suspected=r.include_suspected,
                mag_limit=r.mag_limit,
                max_results=r.max_results,
            )
            comparisons: list[ComparisonStar] = []
            if r.want_comparisons:
                try:
                    comparisons = vsp_chart(r.ra_deg, r.dec_deg, r.fov_arcmin, maglimit=r.mag_limit)
                except CatalogError as exc:
                    # Comparison stars are a bonus; a VSP miss shouldn't sink the
                    # whole result when we already have the variables.
                    logger.warning("VSP fetch failed (keeping VSX result): %s", exc)
            result = CatalogResult(variables=variables, comparisons=comparisons)
        except CatalogError as exc:
            result = CatalogResult(error=str(exc))
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Catalog query crashed")
            result = CatalogResult(error=str(exc))
        self.fetched.emit(result)
