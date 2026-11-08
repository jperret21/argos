"""Field catalogue, overlay layers and comparison candidates (rows A46, A47, A49).

Qt-free ports, in green-plane px internally and frame px on the wire:

- :class:`CatalogRequest` / :class:`CatalogResult` / :func:`run_request` are
  ``CatalogWorker`` (``catalog_worker.py:32-172``); :func:`build_request` is
  the request half of ``maybe_fetch_catalog`` (``acquisition_engine.py:
  1105-1173``).
- :func:`project_field` is ``_project_catalog`` / ``_project_targets``
  (``imaging_page.py:1497-1783``) with the helpers it calls (1801-2027):
  the Gaia / SIMBAD cross-match, marker de-duplication, object categories,
  generic identifiers and every tooltip text. It also returns the
  hit-test index of ``_on_star_clicked`` (804-978), so a click identifies
  exactly what Qt would.
- :func:`candidates` is the FieldBand table (PROPOSAL §7): the VSP
  comparison stars with ``b_minus_v`` and ``neighbours_in_aperture``.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from argos.core import catalog as core_catalog
from argos.core.catalog import CatalogError
from argos.core.catalog.offline import essential_catalogue_objects
from argos.core.catalog.photometry import separation_arcmin
from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.astrometry_session import field_geometry, project_points
from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms
from argos.server.field_solve import to_frame

logger = logging.getLogger(__name__)

CfgGet = Callable[[str, Any], Any]

#: Layers of ``FieldLayers.layers`` (A47), in the overlay bar's order.
LAYERS = (
    "stars",
    "variables",
    "galaxies",
    "nebulae_clusters",
    "exoplanets",
    "other_objects",
    "vsp",
    "selected",
)
#: A detected source this close to a catalogue position "is" that source
#: (``_is_detected_near``, ``imaging_page.py:1991-1997``), green px.
DETECTED_TOLERANCE_PX = 4.0
#: The candidate's own Gaia counterpart lies within at least this separation
#: (wider with the seeing: ``max(3″, FWHM/2)``) and within this G − V.
COUNTERPART_ARCSEC = 3.0
COUNTERPART_DELTA_MAG = 1.5
#: Any source this close to the candidate (green px = 1 frame px) is itself.
SELF_GREEN_PX = 0.5
#: A VSX entry this close to a comparison is the same star (``variable?``).
VSX_MATCH_ARCSEC = 3.0
#: A Gaia neighbour counts when at most this much fainter than the candidate.
NEIGHBOUR_DELTA_MAG = 3.0


# ---------------------------------------------------------------------------
# Request and fetch (catalog_worker.py:32-172; acquisition_engine.py:1105-1173)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogRequest:
    """A field query, derived from a solved frame's WCS (``catalog_worker.py:32-54``)."""

    ra_deg: float
    dec_deg: float
    radius_deg: float
    fov_arcmin: float
    mag_limit: float = 15.0
    max_results: int = 250
    include_suspected: bool = True
    want_comparisons: bool = True
    comparison_target_name: str | None = None
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
    """Outcome of a :class:`CatalogRequest` (``catalog_worker.py:57-79``)."""

    variables: list = field(default_factory=list)
    comparisons: list = field(default_factory=list)
    field_stars: list = field(default_factory=list)
    named_objects: list = field(default_factory=list)
    exoplanet_hosts: list = field(default_factory=list)
    field_star_limit: int = 0
    named_object_limit: int = 0
    #: The G limit the Gaia query asked (None: no Gaia query).
    field_star_mag_limit: float | None = None
    warnings: list[str] = field(default_factory=list)
    #: A source that failed and is only logged by Qt (Gaia, SIMBAD, NASA): the
    #: ``catalog`` record states it so an empty layer has its reason; the log
    #: lines stay Qt's.
    source_warnings: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def build_request(
    cfg: CfgGet, wcs: Any, green_shape: tuple[int, int] | None, source: TargetStar | None
) -> CatalogRequest | None:
    """The ``CatalogRequest`` of ``maybe_fetch_catalog`` (``acquisition_engine.py:1105-1173``)."""
    geom = field_geometry(wcs, green_shape)
    if geom is None:
        return None
    ra_deg, dec_deg, radius_deg, fov_arcmin = geom
    want_field_stars = bool(cfg("catalog.field_stars_enabled", True))
    want_named_objects = bool(cfg("catalog.named_objects_enabled", True))
    identity_budget = max(50, min(5000, int(cfg("catalog.identification_max_objects", 400))))
    if want_field_stars and want_named_objects:
        field_star_budget = max(25, round(identity_budget * 0.7))
        named_object_budget = max(25, identity_budget - field_star_budget)
    else:
        field_star_budget = identity_budget
        named_object_budget = identity_budget
    return CatalogRequest(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        radius_deg=radius_deg,
        fov_arcmin=fov_arcmin,
        mag_limit=float(cfg("catalog.mag_limit", 15.0)),
        max_results=int(cfg("catalog.max_results", 250)),
        include_suspected=bool(cfg("catalog.include_suspected", True)),
        comparison_target_name=source.display_name if source else None,
        comparison_ra_deg=source.ra_deg if source else None,
        comparison_dec_deg=source.dec_deg if source else None,
        want_field_stars=want_field_stars,
        field_star_mag_limit=float(cfg("catalog.field_stars_mag_limit", 18.0)),
        field_star_max_results=field_star_budget,
        want_named_objects=want_named_objects,
        named_object_max_results=named_object_budget,
        named_objects_allow_network=bool(cfg("catalog.named_objects_allow_network", True)),
        want_exoplanet_hosts=bool(cfg("catalog.exoplanet_hosts_enabled", True)),
        exoplanet_hosts_allow_network=bool(cfg("catalog.exoplanet_hosts_allow_network", True)),
    )


def run_request(r: CatalogRequest, api: Any = core_catalog) -> CatalogResult:
    """``CatalogWorker.run`` (``catalog_worker.py:90-172``); *api* holds the query functions."""
    try:
        variables = api.vsx_cone_search(
            r.ra_deg,
            r.dec_deg,
            r.radius_deg,
            include_suspected=r.include_suspected,
            mag_limit=r.mag_limit,
            max_results=r.max_results,
        )
        comparisons: list = []
        warnings: list[str] = []
        source_warnings: list[str] = []
        if r.want_comparisons:
            try:
                comparisons = api.vsp_chart(
                    r.comparison_ra_deg if r.comparison_ra_deg is not None else r.ra_deg,
                    r.comparison_dec_deg if r.comparison_dec_deg is not None else r.dec_deg,
                    r.fov_arcmin,
                    maglimit=r.mag_limit,
                    target_name=r.comparison_target_name,
                )
            except CatalogError as exc:
                logger.warning("VSP fetch failed (keeping VSX result): %s", exc)
                warnings.append(f"VSP comparison sequence unavailable: {exc}")
        field_stars: list = []
        if r.want_field_stars:
            try:
                field_stars = api.gaia_cone_search(
                    r.ra_deg,
                    r.dec_deg,
                    r.radius_deg,
                    mag_limit=r.field_star_mag_limit,
                    max_results=r.field_star_max_results,
                )
            except CatalogError as exc:
                logger.warning("Gaia fetch failed (keeping AAVSO result): %s", exc)
                source_warnings.append(f"Gaia DR3 unavailable: {exc}")
        named_objects: list = []
        if r.want_named_objects:
            try:
                named_objects = api.simbad_field_objects(
                    r.ra_deg,
                    r.dec_deg,
                    r.radius_deg,
                    max_results=r.named_object_max_results,
                    allow_network=r.named_objects_allow_network,
                )
            except Exception as exc:
                logger.warning("SIMBAD field lookup failed (keeping other catalogues): %s", exc)
                source_warnings.append(f"SIMBAD unavailable: {exc}")
        exoplanet_hosts: list = []
        if r.want_exoplanet_hosts:
            try:
                exoplanet_hosts = api.exoplanet_hosts_in_cone(
                    r.ra_deg,
                    r.dec_deg,
                    r.radius_deg,
                    allow_network=r.exoplanet_hosts_allow_network,
                )
            except Exception as exc:
                logger.warning("NASA field lookup failed (keeping other catalogues): %s", exc)
                source_warnings.append(f"NASA Exoplanet Archive unavailable: {exc}")
        return CatalogResult(
            variables=list(variables),
            comparisons=list(comparisons),
            field_stars=list(field_stars),
            named_objects=list(named_objects),
            exoplanet_hosts=list(exoplanet_hosts),
            field_star_limit=r.field_star_max_results if r.want_field_stars else 0,
            field_star_mag_limit=r.field_star_mag_limit if r.want_field_stars else None,
            named_object_limit=r.named_object_max_results if r.want_named_objects else 0,
            warnings=warnings,
            source_warnings=source_warnings,
        )
    except CatalogError as exc:
        return CatalogResult(error=str(exc))
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Catalog query crashed")
        return CatalogResult(error=str(exc) or exc.__class__.__name__)


def result_log_lines(result: CatalogResult) -> list[tuple[str, str]]:
    """The log lines of ``_on_catalog`` (``acquisition_engine.py:1175-1223``), as data."""
    if not result.ok:
        return [("warning", f"Catalog: {result.error}")]
    lines = [("warning", f"Catalog: {w}") for w in result.warnings]
    if result.variables:
        lines.append(("ok", f"Catalog: {len(result.variables)} variable(s) in field"))
    if result.field_stars:
        lines.append(("ok", f"Catalog: {len(result.field_stars)} Gaia DR3 source(s) in field"))
        if result.field_star_limit and len(result.field_stars) >= result.field_star_limit:
            lines.append(
                (
                    "info",
                    "Catalog: Gaia identification budget reached; the displayed list is "
                    "not necessarily complete to the requested G limit.",
                )
            )
    if result.named_objects:
        lines.append(
            ("ok", f"Catalog: {len(result.named_objects)} named SIMBAD object(s) in field")
        )
        if result.named_object_limit and len(result.named_objects) >= result.named_object_limit:
            lines.append(
                (
                    "info",
                    "Catalog: SIMBAD identification budget reached; increase it in Settings "
                    "only when a more detailed field inventory is useful.",
                )
            )
    if result.exoplanet_hosts:
        lines.append(
            (
                "ok",
                f"Catalog: {len(result.exoplanet_hosts)} confirmed exoplanet host(s) in field",
            )
        )
    if result.comparisons:
        lines.append(
            (
                "ok",
                f"Catalog: {len(result.comparisons)} calibrated VSP comparison star(s) available",
            )
        )
    else:
        lines.append(
            (
                "warning",
                "Catalog: no calibrated VSP comparison stars returned for this field. "
                "Refresh the field catalogue or choose calibrated comparisons manually.",
            )
        )
    return lines


# ---------------------------------------------------------------------------
# Helpers and texts (imaging_page.py:1801-2027, 1199-1240)
# ---------------------------------------------------------------------------


def radec_text(ra_deg: float, dec_deg: float) -> str:
    return f"RA {format_ra_hms(ra_deg / 15.0)}  Dec {format_dec_dms(dec_deg)}"


def match_field_catalogue_names(field_stars, named_objects) -> tuple[set[int], list]:
    """``_match_field_catalogue_names`` (``imaging_page.py:1801-1836``): Gaia ↔ SIMBAD ≤ 3″."""
    names: list = [None] * len(field_stars)
    if not field_stars or not named_objects:
        return set(), names
    named_ra = np.deg2rad(np.asarray([item.ra_deg for item in named_objects]))
    named_dec = np.deg2rad(np.asarray([item.dec_deg for item in named_objects]))
    named_sin_dec = np.sin(named_dec)
    named_cos_dec = np.cos(named_dec)
    min_cosine = math.cos(math.radians(3.0 / 3600.0))
    matched: set[int] = set()
    block_size = 256
    for start in range(0, len(field_stars), block_size):
        stars = field_stars[start : start + block_size]
        ra = np.deg2rad(np.asarray([star.ra_deg for star in stars]))
        dec = np.deg2rad(np.asarray([star.dec_deg for star in stars]))
        cosines = np.sin(dec)[:, None] * named_sin_dec[None, :] + np.cos(dec)[
            :, None
        ] * named_cos_dec[None, :] * np.cos(ra[:, None] - named_ra[None, :])
        nearest = np.argmax(cosines, axis=1)
        for offset, index in enumerate(nearest):
            if cosines[offset, index] >= min_cosine:
                item_index = int(index)
                matched.add(item_index)
                names[start + offset] = named_objects[item_index]
    return matched, names


def deduplicate(points: list[dict], radius_px: float = 8.0) -> list[dict]:
    """``_deduplicate_marker_points`` (``imaging_page.py:1839-1856``); green px ``gx``/``gy``."""
    selected: list[dict] = []
    radius2 = float(radius_px) ** 2
    for point in points:
        if any(
            (point["gx"] - kept["gx"]) ** 2 + (point["gy"] - kept["gy"]) ** 2 <= radius2
            for kept in selected
        ):
            continue
        selected.append(point)
    return selected


def object_category(object_type: str) -> str:
    """``_object_category`` (``imaging_page.py:1868-1896``)."""
    value = (object_type or "").casefold()
    if any(token in value for token in ("gal", "qso", "agn")) or value in {
        "g",
        "gi",
        "gx",
        "gic",
    }:
        return "galaxy"
    if any(token in value for token in ("neb", "hii")) or value in {"pn", "pl", "nb", "snr"}:
        return "nebula"
    if any(token in value for token in ("cluster", "cl*")) or value in {
        "oc",
        "gc",
        "gb",
        "glc",
        "c+n",
    }:
        return "cluster"
    if "*" in value or "star" in value:
        return "star"
    return "other"


def is_generic_identifier(name: str) -> bool:
    """``_is_generic_catalogue_identifier`` (``imaging_page.py:1898-1917``)."""
    compact = " ".join((name or "").split()).casefold()
    return compact.startswith(
        (
            "gaia ",
            "2mass ",
            "ucac",
            "sdss ",
            "pan-starrs ",
            "ps1 ",
            "wise ",
            "allwise ",
            "lamost ",
            "ztf ",
            "asassn ",
            "ato ",
        )
    )


def gaia_body(star, identity=None) -> str:
    """``_field_catalogue_body`` (``imaging_page.py:1919-1938``), also its tooltip."""
    lines = []
    if identity is not None:
        lines.extend([f"Name  {identity.name}", f"Object type  {identity.object_type or '—'}"])
    lines.append(f"Gaia DR3 source  {star.source_id}")
    for label, value in (
        ("Gaia G", star.g_mag),
        ("Gaia BP", star.bp_mag),
        ("Gaia RP", star.rp_mag),
    ):
        if value is not None:
            lines.append(f"{label} magnitude  {value:.3f}")
    lines.append(radec_text(star.ra_deg, star.dec_deg))
    lines.append("Sources  Gaia DR3" + (" · SIMBAD" if identity is not None else ""))
    return "\n".join(lines)


def deep_sky_tooltip(item) -> str:
    """``_deep_sky_tooltip`` (``imaging_page.py:1945-1952``)."""
    magnitude = f"\nMagnitude  {item.magnitude:.1f}" if item.magnitude is not None else ""
    aliases = f"\nAlso  {', '.join(item.aliases[:2])}" if item.aliases else ""
    return (
        f"Argos Essential Catalogue\n{item.name}\n{item.object_type or 'Deep-sky object'}"
        f"{magnitude}{aliases}\n"
        f"RA {format_ra_hms(item.ra_degrees / 15.0)}  Dec {format_dec_dms(item.dec_degrees)}"
    )


def named_object_tooltip(item) -> str:
    """``_named_object_tooltip`` (``imaging_page.py:1955-1963``)."""
    magnitudes = "".join(
        f"\nSIMBAD {band} magnitude  {value:.3f}" for band, value in getattr(item, "mags", ())
    )
    return (
        f"SIMBAD identified object\n{item.name}\n{item.object_type or 'Object type unavailable'}\n"
        f"{magnitudes.lstrip()}\n"
        f"RA {format_ra_hms(item.ra_deg / 15.0)}  Dec {format_dec_dms(item.dec_deg)}"
    )


def point_identity_tooltip(identity) -> str:
    """``_point_identity_tooltip`` (``imaging_page.py:1966-1975``)."""
    magnitudes = "".join(f"\n{band} magnitude  {value:.3f}" for band, value in identity.mags)
    return (
        f"Point catalogue identification\n{identity.name}\n"
        f"{identity.object_type or 'Object type unavailable'}\n"
        f"Source  {identity.source}{magnitudes}\n"
        f"RA {format_ra_hms(identity.ra_deg / 15.0)}  "
        f"Dec {format_dec_dms(identity.dec_deg)}\n"
        f"WCS match offset  {identity.separation_arcsec:.1f}″"
    )


def exoplanet_tooltip(host) -> str:
    """``_exoplanet_tooltip`` (``imaging_page.py:1978-1989``)."""
    planets = ", ".join(host.planet_names)
    magnitudes = "".join(
        f"\n{band} magnitude  {value:.3f}" for band, value in getattr(host, "mags", ())
    )
    return (
        f"Prepared exoplanet host\n{host.host_name}\nCached planet(s)  {planets}\n"
        f"{magnitudes.lstrip()}\n"
        f"RA {format_ra_hms(host.ra_degrees / 15.0)}  "
        f"Dec {format_dec_dms(host.dec_degrees)}\n"
        "Source: local NASA Exoplanet Archive cache"
    )


def comparison_tooltip(comparison) -> str:
    """``_comparison_tooltip`` (``imaging_page.py:1999-2007``)."""
    mags = "  ".join(f"{band.band} {band.mag:.3f}" for band in comparison.bands) or "—"
    return (
        "VSP reference candidate\n"
        f"AUID {comparison.auid}\n"
        f"Catalogue magnitudes  {mags}\n"
        f"RA {format_ra_hms(comparison.ra_deg / 15.0)}  "
        f"Dec {format_dec_dms(comparison.dec_deg)}"
    )


def target_tooltip(star: TargetStar) -> str:
    """``_target_tooltip`` (``imaging_page.py:2010-2025``)."""
    role = {
        "target": "Photometry target",
        "comparison": "Selected reference star",
        "check": "Check star",
    }.get(star.role, star.role.capitalize())
    mags = "  ".join(f"{band} {mag:.3f}" for band, mag in star.mags.items()) or "—"
    return (
        f"{role}\n{star.display_name}\n"
        f"AUID {star.auid or '—'}\n"
        f"Catalogue magnitudes  {mags}\n"
        f"RA {format_ra_hms(star.ra_deg / 15.0)}  Dec {format_dec_dms(star.dec_deg)}"
    )


def variable_body(v) -> str:
    """``_variable_body`` (``imaging_page.py:1199-1215``)."""
    lines = []
    if v.var_type:
        lines.append(f"type {v.var_type}" + ("  (suspected)" if v.is_suspected else ""))
    rng = []
    if v.max_mag:
        rng.append(f"max {v.max_mag}")
    if v.min_mag and v.min_mag != "?":
        rng.append(f"min {v.min_mag}")
    if rng:
        lines.append("  ".join(rng))
    if v.period:
        lines.append(f"period {v.period:g} d")
    if v.auid:
        lines.append(f"AUID {v.auid}")
    lines.append(radec_text(v.ra_deg, v.dec_deg))
    return "\n".join(lines)


def variable_key(v) -> str:
    """The TargetStar key a VSX variable gets (``imaging_page.py:2245``)."""
    return f"auid:{v.auid}" if v.auid else f"pos:{v.ra_deg:.5f},{v.dec_deg:.5f}"


def comparison_mags(c) -> dict[str, float]:
    return {b.band: b.mag for b in c.bands}


def _band_mag(c, band: str) -> float | None:
    for b in c.bands:
        if b.band == band and b.mag is not None:
            return float(b.mag)
    return None


def b_minus_v(c) -> float | None:
    """VSP ``B − V`` of a comparison star, ``None`` unless both bands are given."""
    b, v = _band_mag(c, "B"), _band_mag(c, "V")
    if b is None or v is None:
        return None
    return round(b - v, 4)


# ---------------------------------------------------------------------------
# Projection (imaging_page.py:1497-1783)
# ---------------------------------------------------------------------------


@dataclass
class FieldContext:
    """What a projection needs: the reference solve and the field's catalogue."""

    wcs: Any  # FrameWCS (green px)
    green_shape: tuple[int, int]
    detected: list[tuple[float, float]]  # sources detected on the solved frame (green px)
    result: CatalogResult
    point_identities: list = field(default_factory=list)


@dataclass
class Projection:
    """``FieldLayers`` content plus the hit-test index (reference green px)."""

    layers: dict[str, list[dict]]
    counts: dict[str, int]
    hits: list[tuple[str, list]]  # (kind, [(gx, gy, item, extra) | None])
    deep_sky: list = field(default_factory=list)
    exoplanet_hosts: list = field(default_factory=list)


def _detected_near(detected, point, tolerance_px: float = DETECTED_TOLERANCE_PX) -> bool:
    """``_is_detected_near`` (``imaging_page.py:1991-1997``)."""
    if not detected:
        return True
    x, y = point
    return any(math.hypot(x - dx, y - dy) <= tolerance_px for dx, dy in detected)


def _marker(kind: str, ident: str, point, label: str, tooltip: str, ra_deg, dec_deg, **extra):
    fx, fy = to_frame(point[0], point[1])
    record = {
        "id": ident,
        "x": round(fx, 2),
        "y": round(fy, 2),
        "label": label,
        "tooltip": tooltip,
        "kind": kind,
        "key": None,
        "ra_hours": float(ra_deg) / 15.0,
        "dec_deg": float(dec_deg),
        "gx": point[0],
        "gy": point[1],
    }
    record.update(extra)
    return record


def _strip(markers: list[dict]) -> list[dict]:
    return [{k: v for k, v in m.items() if k not in ("gx", "gy")} for m in markers]


def project_field(
    ctx: FieldContext, cfg: CfgGet, tset: TargetSet, *, display_mag_limit: float
) -> Projection:
    """The overlay layers of one field and its hit-test index (reference solve)."""
    wcs, gs, result = ctx.wcs, ctx.green_shape, ctx.result
    variables = result.variables
    field_stars = result.field_stars
    named_objects = result.named_objects
    comparisons = result.comparisons
    geometry = field_geometry(wcs, gs)
    centre = geometry[:2] if geometry is not None else None
    saved = {s.key(): s.role for s in tset.stars}

    var_green = project_points(wcs, gs, ((v.ra_deg, v.dec_deg) for v in variables))
    var_pts = []
    for index, (p, v) in enumerate(zip(var_green, variables)):
        if not p:
            continue
        key = variable_key(v)
        mag_text = " – ".join(m for m in (v.max_mag, v.min_mag) if m)
        var_pts.append(
            _marker(
                "variable",
                f"variable:{index}",
                p,
                v.name,
                f"Variable star\n{v.name}\n{variable_body(v)}",
                v.ra_deg,
                v.dec_deg,
                key=key,
                suspected=bool(v.is_suspected),
                index=index,
                name=v.name,
                var_type=v.var_type,
                mag_text=mag_text,
                max_mag=v.max_mag,
                min_mag=v.min_mag,
                brightest_mag=v.brightest_mag,
                period_d=v.period,
                auid=v.auid,
                sep_arcmin=(
                    separation_arcmin(centre[0], centre[1], v.ra_deg, v.dec_deg)
                    if centre is not None
                    else None
                ),
                role=saved.get(key),
            )
        )

    matched_named, gaia_names = match_field_catalogue_names(field_stars, named_objects)
    raw_gaia_green = project_points(wcs, gs, ((s.ra_deg, s.dec_deg) for s in field_stars))
    detected_only = bool(cfg("catalog.field_stars_detected_only", False))
    gaia_green = [
        (
            point
            if point is not None
            and (star.g_mag is None or float(star.g_mag) <= display_mag_limit)
            and (not detected_only or _detected_near(ctx.detected, point))
            else None
        )
        for point, star in zip(raw_gaia_green, field_stars)
    ]
    stars_pts = []
    for index, (point, star, identity) in enumerate(zip(gaia_green, field_stars, gaia_names)):
        if not point:
            continue
        label = (
            identity.name
            if identity is not None and not is_generic_identifier(identity.name)
            else ""
        )
        stars_pts.append(
            _marker(
                "gaia",
                f"gaia:{index}",
                point,
                label,
                gaia_body(star, identity),
                star.ra_deg,
                star.dec_deg,
                key=f"pos:{star.ra_deg:.5f},{star.dec_deg:.5f}",
                g_mag=star.g_mag,
                bp_mag=star.bp_mag,
                rp_mag=star.rp_mag,
                source_id=star.source_id,
                name=identity.name if identity is not None else None,
                detected=_detected_near(ctx.detected, point),
            )
        )

    raw_named_green = project_points(wcs, gs, ((i.ra_deg, i.dec_deg) for i in named_objects))
    named_green = [
        point if index not in matched_named else None for index, point in enumerate(raw_named_green)
    ]
    by_type: dict[str, list[dict]] = {"star": [], "galaxy": [], "nebula_cluster": [], "other": []}

    def file_by_category(object_type: str, marker: dict) -> None:
        category = object_category(object_type)
        if category == "star":
            by_type["star"].append(marker)
        elif category == "galaxy":
            by_type["galaxy"].append(marker)
        elif category in {"nebula", "cluster"}:
            by_type["nebula_cluster"].append(marker)
        else:
            by_type["other"].append(marker)

    for index, (point, item) in enumerate(zip(named_green, named_objects)):
        if point is None:
            continue
        marker = _marker(
            "simbad",
            f"simbad:{index}",
            point,
            item.name,
            named_object_tooltip(item),
            item.ra_deg,
            item.dec_deg,
            key=f"pos:{item.ra_deg:.5f},{item.dec_deg:.5f}",
            name=item.name,
            object_type=item.object_type,
        )
        file_by_category(item.object_type, marker)
    stars_pts.extend(by_type["star"])
    by_type["star"] = []

    identity_green = project_points(wcs, gs, ((i.ra_deg, i.dec_deg) for i in ctx.point_identities))
    for index, (point, identity) in enumerate(zip(identity_green, ctx.point_identities)):
        if point is None:
            continue
        marker = _marker(
            "point_identity",
            f"point:{index}",
            point,
            identity.name,
            point_identity_tooltip(identity),
            identity.ra_deg,
            identity.dec_deg,
            key=f"pos:{identity.ra_deg:.5f},{identity.dec_deg:.5f}",
            name=identity.name,
            object_type=identity.object_type,
        )
        if object_category(identity.object_type) == "star":
            stars_pts.append(marker)
        else:
            file_by_category(identity.object_type, marker)
    stars_pts = deduplicate(stars_pts)

    deep_sky: list = []
    hosts = list(result.exoplanet_hosts)
    if geometry is not None:
        ra_deg, dec_deg, radius_deg, _fov = geometry
        if bool(cfg("catalog.show_essential_objects", True)):
            deep_sky = [
                item
                for item in essential_catalogue_objects()
                if separation_arcmin(ra_deg, dec_deg, item.ra_degrees, item.dec_degrees)
                <= radius_deg * 60.0
            ]
        if not hosts and bool(cfg("catalog.show_cached_exoplanets", True)):
            hosts = core_catalog.cached_exoplanet_hosts_in_cone(ra_deg, dec_deg, radius_deg)
    deep_green = project_points(wcs, gs, ((i.ra_degrees, i.dec_degrees) for i in deep_sky))
    essential: dict[str, list[dict]] = {"galaxy": [], "nebula_cluster": [], "other": []}
    for index, (point, item) in enumerate(zip(deep_green, deep_sky)):
        if point is None:
            continue
        marker = _marker(
            "deep_sky",
            f"deep_sky:{index}",
            point,
            item.name,
            deep_sky_tooltip(item),
            item.ra_degrees,
            item.dec_degrees,
            key=f"pos:{item.ra_degrees:.5f},{item.dec_degrees:.5f}",
            name=item.name,
            object_type=item.object_type,
        )
        category = object_category(item.object_type)
        if category == "galaxy":
            essential["galaxy"].append(marker)
        elif category in {"nebula", "cluster"}:
            essential["nebula_cluster"].append(marker)
        else:
            essential["other"].append(marker)
    galaxies = deduplicate(by_type["galaxy"] + essential["galaxy"])
    nebulae = deduplicate(by_type["nebula_cluster"] + essential["nebula_cluster"])
    others = deduplicate(by_type["other"] + essential["other"])

    host_green = project_points(wcs, gs, ((h.ra_degrees, h.dec_degrees) for h in hosts))
    exo_pts = [
        _marker(
            "exoplanet",
            f"exoplanet:{index}",
            point,
            host.host_name,
            exoplanet_tooltip(host),
            host.ra_degrees,
            host.dec_degrees,
            key=f"pos:{host.ra_degrees:.5f},{host.dec_degrees:.5f}",
            name=host.host_name,
            planets=list(host.planet_names),
        )
        for index, (point, host) in enumerate(zip(host_green, hosts))
        if point
    ]

    comp_green = project_points(wcs, gs, ((c.ra_deg, c.dec_deg) for c in comparisons))
    vsp_pts = [
        _marker(
            "vsp",
            f"vsp:{index}",
            p,
            "",
            comparison_tooltip(c),
            c.ra_deg,
            c.dec_deg,
            key=f"auid:{c.auid}" if c.auid else f"pos:{c.ra_deg:.5f},{c.dec_deg:.5f}",
            auid=c.auid,
            chart_label=c.label,
            role=saved.get(f"auid:{c.auid}" if c.auid else ""),
            detected=True,
        )
        for index, (p, c) in enumerate(zip(comp_green, comparisons))
        if p and _detected_near(ctx.detected, p)
    ]

    target_green = project_points(wcs, gs, ((s.ra_deg, s.dec_deg) for s in tset.stars))
    selected = [
        _marker(
            "target",
            f"target:{s.key()}",
            p,
            s.display_name,
            target_tooltip(s),
            s.ra_deg,
            s.dec_deg,
            key=s.key(),
            role=s.role,
            auid=s.auid,
        )
        for p, s in zip(target_green, tset.stars)
        if p is not None
    ]

    layers = {
        "stars": stars_pts,
        "variables": var_pts,
        "galaxies": galaxies,
        "nebulae_clusters": nebulae,
        "exoplanets": exo_pts,
        "other_objects": others,
        "vsp": vsp_pts,
        "selected": selected,
    }
    counts = {name: len(markers) for name, markers in layers.items()}

    # Hit-test order of _on_star_clicked (imaging_page.py:804-978); hidden
    # layers still identify (Q-O18), the Gaia list honours the display filter.
    def entries(points, items):
        return [(p[0], p[1], item) if p is not None else None for p, item in zip(points, items)]

    gaia_entries = [
        (p[0], p[1], (star, identity)) if p is not None else None
        for p, star, identity in zip(gaia_green, field_stars, gaia_names)
    ]
    hits = [
        ("target", entries(target_green, tset.stars)),
        ("variable", entries(var_green, variables)),
        ("vsp", entries(comp_green, comparisons)),
        ("simbad", entries(named_green, named_objects)),
        ("deep_sky", entries(deep_green, deep_sky)),
        ("exoplanet", entries(host_green, hosts)),
        ("gaia", gaia_entries),
        ("point_identity", entries(identity_green, ctx.point_identities)),
    ]
    return Projection(
        layers={name: _strip(markers) for name, markers in layers.items()},
        counts=counts,
        hits=hits,
        deep_sky=deep_sky,
        exoplanet_hosts=hosts,
    )


def nearest(entries, gx: float, gy: float, tol: float) -> int | None:
    """``_nearest`` (``imaging_page.py:980-994``) with the client's tolerance."""
    best_i, best_d = None, tol
    for i, entry in enumerate(entries):
        if entry is None:
            continue
        d = math.hypot(entry[0] - gx, entry[1] - gy)
        if d <= best_d:
            best_i, best_d = i, d
    return best_i


# ---------------------------------------------------------------------------
# Comparison candidates (PROPOSAL §7)
# ---------------------------------------------------------------------------


def gaia_depth(result: "CatalogResult") -> float | None:
    """The G magnitude the held Gaia list is complete to, or None.

    The query asks the brightest sources to ``field_star_mag_limit`` within
    the identification budget: when the budget truncated it, the list is
    only complete to its faintest source.
    """
    stars = result.field_stars
    if not stars or result.field_star_mag_limit is None:
        return None
    if result.field_star_limit and len(stars) >= result.field_star_limit:
        mags = [float(s.g_mag) for s in stars if s.g_mag is not None]
        return max(mags) if mags else None
    return float(result.field_star_mag_limit)


def neighbours_in_aperture(
    comparison,
    comp_green: tuple[float, float],
    field_stars: list,
    gaia_green: list[tuple[float, float] | None],
    aperture_green_px: float,
    *,
    depth_g: float | None = None,
    counterpart_arcsec: float = COUNTERPART_ARCSEC,
) -> int | None:
    """Gaia sources inside the candidate's photometry aperture (blend risk).

    The candidate's own counterpart is the nearest Gaia source within
    *counterpart_arcsec* whose G is within :data:`COUNTERPART_DELTA_MAG` of
    the VSP V (any source within 1 frame px is the candidate itself); every
    other source whose reference position lies within *aperture_green_px*
    of the candidate's and that is at most :data:`NEIGHBOUR_DELTA_MAG`
    fainter (``G ≤ m + 3``, ``m`` = the counterpart's G, else the VSP V)
    counts. ``None`` when the count cannot be stated: no Gaia sources, no
    magnitude, or a held list not complete to ``m + 3`` (*depth_g*).
    """
    if not field_stars or depth_g is None:
        return None
    v_mag = _band_mag(comparison, "V")
    own = None
    best = counterpart_arcsec
    for index, star in enumerate(field_stars):
        sep = separation_arcmin(comparison.ra_deg, comparison.dec_deg, star.ra_deg, star.dec_deg)
        if sep * 60.0 > best:
            continue
        if v_mag is not None and star.g_mag is not None:
            if abs(float(star.g_mag) - float(v_mag)) >= COUNTERPART_DELTA_MAG:
                continue
        own, best = index, sep * 60.0
    reference = field_stars[own].g_mag if own is not None else None
    if reference is None:
        reference = v_mag
    if reference is None or float(reference) + NEIGHBOUR_DELTA_MAG > float(depth_g):
        return None  # the held list cannot say what is at m + 3
    count = 0
    for index, (star, point) in enumerate(zip(field_stars, gaia_green)):
        if index == own or point is None:
            continue
        d = math.hypot(point[0] - comp_green[0], point[1] - comp_green[1])
        if d > aperture_green_px or d <= SELF_GREEN_PX:
            continue
        if star.g_mag is not None and float(star.g_mag) > float(reference) + NEIGHBOUR_DELTA_MAG:
            continue
        count += 1
    return count


def vsx_match(comparison, variables: list) -> dict[str, Any] | None:
    """The VSX entry at the comparison's position (a known or suspected variable)."""
    best, best_sep = None, VSX_MATCH_ARCSEC
    for star in variables:
        sep = separation_arcmin(comparison.ra_deg, comparison.dec_deg, star.ra_deg, star.dec_deg)
        if sep * 60.0 <= best_sep:
            best, best_sep = star, sep * 60.0
    if best is None:
        return None
    return {
        "name": best.name,
        "var_type": best.var_type,
        "suspected": bool(best.is_suspected),
        "max_mag": best.max_mag,
        "min_mag": best.min_mag,
        "sep_arcsec": round(best_sep, 2),
    }


def candidates(
    ctx: FieldContext,
    tset: TargetSet,
    *,
    aperture_green_px: float,
    quality: dict[str, Any] | None,
    measured_seq: int | None,
    target_b_minus_v: float | None,
    counterpart_arcsec: float = COUNTERPART_ARCSEC,
) -> list[dict]:
    """The FieldBand rows: VSP comparison stars inside the frame (PROPOSAL §7)."""
    wcs, gs, result = ctx.wcs, ctx.green_shape, ctx.result
    depth_g = gaia_depth(result)
    comps = result.comparisons
    comp_green = project_points(wcs, gs, ((c.ra_deg, c.dec_deg) for c in comps))
    gaia_green = project_points(wcs, gs, ((s.ra_deg, s.dec_deg) for s in result.field_stars))
    targets = [s for s in tset.stars if s.role == "target"]
    if targets:
        origin = (targets[0].ra_deg, targets[0].dec_deg)
    else:
        geometry = field_geometry(wcs, gs)
        origin = (geometry[0], geometry[1]) if geometry is not None else None
    saved = {s.key(): s.role for s in tset.stars}
    rows = []
    for c, point in zip(comps, comp_green):
        if point is None:
            continue
        fx, fy = to_frame(*point)
        key = f"auid:{c.auid}" if c.auid else f"pos:{c.ra_deg:.5f},{c.dec_deg:.5f}"
        bv = b_minus_v(c)
        q = quality.get(c.auid) if quality else None
        rows.append(
            {
                "auid": c.auid,
                "label": c.label,
                "chart_id": c.chart_id,
                "x": round(fx, 2),
                "y": round(fy, 2),
                "ra_hours": c.ra_deg / 15.0,
                "dec_deg": c.dec_deg,
                "key": key,
                "v_mag": _band_mag(c, "V"),
                "b_mag": _band_mag(c, "B"),
                "b_minus_v": bv,
                "delta_b_minus_v": (
                    round(bv - target_b_minus_v, 4)
                    if bv is not None and target_b_minus_v is not None
                    else None
                ),
                "sep_arcmin": (
                    separation_arcmin(origin[0], origin[1], c.ra_deg, c.dec_deg)
                    if origin is not None
                    else None
                ),
                "peak_adu": q.get("peak_adu") if q else None,
                "snr": q.get("snr") if q else None,
                "saturated": q.get("saturated") if q else None,
                "neighbours_in_aperture": neighbours_in_aperture(
                    c,
                    point,
                    result.field_stars,
                    gaia_green,
                    aperture_green_px,
                    depth_g=depth_g,
                    counterpart_arcsec=counterpart_arcsec,
                ),
                "vsx": vsx_match(c, result.variables),
                "detected": _detected_near(ctx.detected, point),
                "role": saved.get(key),
                "measured_seq": measured_seq if q else None,
                "pending_star": {
                    "ra_deg": c.ra_deg,
                    "dec_deg": c.dec_deg,
                    "ra_hours": c.ra_deg / 15.0,
                    "auid": c.auid,
                    "name": c.auid,
                    "source": "vsp",
                    "mags": comparison_mags(c),
                    "chart_id": c.chart_id,
                },
            }
        )
    return rows
