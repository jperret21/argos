"""Shared astrometry helpers — one code path for the live page and Open-FITS.

See ``docs/photometry_plan.md`` §4 (Workstream A). Both the live acquisition page
and the floating analysis window used to carry their own copies of "build the
ASTAP settings", "halve the green-plane scale to full-res", "build the grid
overlay" and "project catalog RA/Dec to green pixels" — with subtle divergences
(different hints, grid spacing applied on one side only, the ÷2 convention
duplicated). This module is the single, Qt-free, unit-tested home for all of it.

Conventions (``docs/photometry_plan.md`` §1):

- pixel coordinates are **green px** ``(H//2, W//2)`` everywhere;
- ``cfg_get`` is a ``callable(key, default) -> value`` (the page's ``self._cfg``),
  so this module never imports the UI ``Config``.
- ``mount_radec`` is ``(ra_hours, dec_deg)`` of the live pointing, or ``None``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from argos.core.imaging.metrics import ARCSEC_PER_GREEN_PX
from argos.core.imaging.platesolve import (
    FrameWCS,
    SolveResult,
    SolveSettings,
    WCSOverlay,
    angular_separation_deg,
    frame_wcs,
    wcs_grid,
)

CfgGet = Callable[[str, object], object]


def build_solve_settings(
    cfg_get: CfgGet,
    green_shape: tuple[int, int],
    *,
    live: bool,
    mount_radec: tuple[float, float] | None = None,
) -> SolveSettings:
    """Assemble :class:`SolveSettings` from config — the only place that does it.

    Live solves (``live=True``) with a mount hint use a bounded timeout and a
    configurable search radius, and **allow a blind retry** so a stale mount hint
    (common with the Seestar) doesn't permanently break auto-solving. The blind
    retry removes the hint and searches the whole sky, so the cadence is only
    affected when the hinted solve misses.
    """
    gh = int(green_shape[0])
    use_hint = bool(cfg_get("astrometry.use_scale_hint", True))
    ra_hint = mount_radec[0] if mount_radec is not None else None
    dec_hint = mount_radec[1] if mount_radec is not None else None

    if live and mount_radec is not None:
        radius = float(cfg_get("astrometry.live_search_radius_deg", 30.0))
    else:
        radius = float(cfg_get("astrometry.search_radius_deg", 30.0))
    timeout = float(cfg_get("astrometry.live_timeout_s", 25.0)) if live else 120.0

    return SolveSettings(
        astap_path=str(cfg_get("astrometry.astap_path", "")),
        database=str(cfg_get("astrometry.database", "")),
        search_radius_deg=radius,
        downsample=int(cfg_get("astrometry.downsample", 2)),
        fov_hint_deg=(gh * ARCSEC_PER_GREEN_PX / 3600.0) if use_hint else None,
        ra_hint_hours=ra_hint,
        dec_hint_deg=dec_hint,
        timeout_s=timeout,
        allow_blind_retry=True,
    )


def full_res_scale(result: SolveResult) -> float | None:
    """Full-res plate scale (″/px) from a solve.

    ASTAP solves the **green half-res** plane, so its reported scale is per green
    pixel; one full-res sensor pixel spans half that on sky. The ÷2 lives here,
    once, instead of being re-typed at every call site.
    """
    if result.scale_arcsec is None:
        return None
    return result.scale_arcsec / 2.0


def wcs_from_result(result: SolveResult, green_shape: tuple[int, int] | None) -> FrameWCS | None:
    """Build a :class:`FrameWCS` from a solve (CRPIX defaults to the green centre)."""
    return frame_wcs(result.fields, green_shape)


def field_geometry(
    wcs: FrameWCS | None, green_shape: tuple[int, int] | None
) -> tuple[float, float, float, float] | None:
    """``(centre RA°, centre Dec°, cone radius°, FOV arcmin)`` from the WCS.

    The cone radius is the centre→corner separation; the FOV diameter is twice
    that. Used to drive a VSX/VSP catalog cone search.
    """
    if wcs is None or green_shape is None:
        return None
    gh, gw = green_shape
    cx, cy = (gw - 1) / 2.0, (gh - 1) / 2.0
    ra_h, dec_d = wcs.pixel_to_radec(cx, cy)
    cra_h, cdec_d = wcs.pixel_to_radec(0.0, 0.0)
    radius_deg = angular_separation_deg(ra_h, dec_d, cra_h, cdec_d)
    return ra_h * 15.0, dec_d, radius_deg, radius_deg * 2.0 * 60.0


def project_points(
    wcs: FrameWCS | None,
    green_shape: tuple[int, int] | None,
    radec_deg: Iterable[tuple[float, float]],
    margin: float = 2.0,
) -> list[tuple[float, float] | None]:
    """Project ``(ra_deg, dec_deg)`` pairs to green px; ``None`` when off-frame.

    The output list is **parallel to the input** (one entry per pair) so callers
    can keep a marker/positions array aligned with their catalog list; an entry is
    ``None`` (and so not clickable / not measurable) when it falls outside the
    frame by more than ``margin`` green px.
    """
    out: list[tuple[float, float] | None] = []
    if wcs is None or green_shape is None:
        return out
    gh, gw = green_shape
    for ra_deg, dec_deg in radec_deg:
        x, y = wcs.world_to_pixel_deg(ra_deg, dec_deg)
        x, y = float(x), float(y)
        if -margin <= x <= gw + margin and -margin <= y <= gh + margin:
            out.append((x, y))
        else:
            out.append(None)
    return out


def overlay_for(
    wcs: FrameWCS | None,
    green_shape: tuple[int, int] | None,
    cfg_get: CfgGet,
    target_radec: tuple[float, float] | None = None,
) -> WCSOverlay | None:
    """Build the RA/Dec grid overlay, applying ``astrometry.grid_spacing_arcmin``.

    ``0`` (the default) keeps the adaptive 1/2/5 spacing; a positive value forces
    a finer fixed on-sky grid. ``target_radec`` is ``(ra_hours, dec_deg)`` of the
    intended target → a framing reticle.
    """
    if wcs is None or green_shape is None:
        return None
    arcmin = float(cfg_get("astrometry.grid_spacing_arcmin", 0) or 0)
    spacing = arcmin / 60.0 if arcmin > 0 else None
    return wcs_grid(wcs, green_shape, target_radec=target_radec, spacing_deg=spacing)
