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
    GaiaStar,
    CachedExoplanetHost,
    NamedFieldObject,
    VariableStar,
    exoplanet_hosts_in_cone,
    gaia_cone_search,
    simbad_field_objects,
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
    comparison_target_name: str | None = None  # VSP sequence identity, if selected
    comparison_ra_deg: float | None = None
    comparison_dec_deg: float | None = None
    want_field_stars: bool = True
    field_star_mag_limit: float = 18.0
    field_star_max_results: int = 2000
    want_named_objects: bool = True
    named_object_max_results: int = 500
    named_objects_allow_network: bool = True
    want_exoplanet_hosts: bool = True
    exoplanet_hosts_allow_network: bool = True


@dataclass
class CatalogResult:
    """Outcome of a :class:`CatalogRequest`. ``error`` is empty on success."""

    variables: list[VariableStar] = field(default_factory=list)
    comparisons: list[ComparisonStar] = field(default_factory=list)
    field_stars: list[GaiaStar] = field(default_factory=list)
    named_objects: list[NamedFieldObject] = field(default_factory=list)
    exoplanet_hosts: list[CachedExoplanetHost] = field(default_factory=list)
    field_star_limit: int = 0
    named_object_limit: int = 0
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
                    comparisons = vsp_chart(
                        r.comparison_ra_deg if r.comparison_ra_deg is not None else r.ra_deg,
                        r.comparison_dec_deg if r.comparison_dec_deg is not None else r.dec_deg,
                        r.fov_arcmin,
                        maglimit=r.mag_limit,
                        target_name=r.comparison_target_name,
                    )
                except CatalogError as exc:
                    # Comparison stars are a bonus; a VSP miss shouldn't sink the
                    # whole result when we already have the variables.
                    logger.warning("VSP fetch failed (keeping VSX result): %s", exc)
            field_stars: list[GaiaStar] = []
            if r.want_field_stars:
                try:
                    field_stars = gaia_cone_search(
                        r.ra_deg,
                        r.dec_deg,
                        r.radius_deg,
                        mag_limit=r.field_star_mag_limit,
                        max_results=r.field_star_max_results,
                    )
                except CatalogError as exc:
                    # Field labels are optional context; VSP/VSX must remain
                    # usable when an observer works offline without a Gaia cache.
                    logger.warning("Gaia fetch failed (keeping AAVSO result): %s", exc)
            named_objects: list[NamedFieldObject] = []
            if r.want_named_objects:
                try:
                    named_objects = simbad_field_objects(
                        r.ra_deg,
                        r.dec_deg,
                        r.radius_deg,
                        max_results=r.named_object_max_results,
                        allow_network=r.named_objects_allow_network,
                    )
                except Exception as exc:
                    logger.warning("SIMBAD field lookup failed (keeping other catalogues): %s", exc)
            exoplanet_hosts: list[CachedExoplanetHost] = []
            if r.want_exoplanet_hosts:
                try:
                    exoplanet_hosts = exoplanet_hosts_in_cone(
                        r.ra_deg,
                        r.dec_deg,
                        r.radius_deg,
                        allow_network=r.exoplanet_hosts_allow_network,
                    )
                except Exception as exc:
                    logger.warning("NASA field lookup failed (keeping other catalogues): %s", exc)
            result = CatalogResult(
                variables=variables,
                comparisons=comparisons,
                field_stars=field_stars,
                named_objects=named_objects,
                exoplanet_hosts=exoplanet_hosts,
                field_star_limit=r.field_star_max_results if r.want_field_stars else 0,
                named_object_limit=r.named_object_max_results if r.want_named_objects else 0,
            )
        except CatalogError as exc:
            result = CatalogResult(error=str(exc))
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Catalog query crashed")
            result = CatalogResult(error=str(exc))
        self.fetched.emit(result)
