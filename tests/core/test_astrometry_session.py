"""Tests for the shared astrometry helpers (Qt-free, no ASTAP)."""

from __future__ import annotations

from seercontrol.core.imaging.astrometry_session import (
    build_solve_settings,
    field_geometry,
    full_res_scale,
    overlay_for,
    project_points,
    wcs_from_result,
)
from seercontrol.core.imaging.platesolve import SolveResult, frame_wcs

# A clean aligned green-plane solution (mirror of tests/core/test_platesolve.py).
_SCALE_DEG = 7.48 / 3600.0
_FIELDS = {
    "CRVAL1": "83.6",
    "CRVAL2": "22.0",
    "CRPIX1": "513.0",
    "CRPIX2": "385.0",
    "CD1_1": f"{-_SCALE_DEG}",
    "CD1_2": "0.0",
    "CD2_1": "0.0",
    "CD2_2": f"{_SCALE_DEG}",
}
_SHAPE = (768, 1024)  # (h, w)


def _cfg(d: dict):
    """A ``cfg_get(key, default)`` backed by a plain dict."""
    return lambda key, default: d.get(key, default)


# --------------------------------------------------------------------------- #
# build_solve_settings                                                         #
# --------------------------------------------------------------------------- #


def test_build_solve_settings_live_small_radius_no_blind() -> None:
    s = build_solve_settings(
        _cfg({"astrometry.live_search_radius_deg": 4, "astrometry.live_timeout_s": 20}),
        (600, 800),
        live=True,
        mount_radec=(5.5, 22.0),
    )
    assert s.search_radius_deg == 4
    assert s.timeout_s == 20
    assert s.allow_blind_retry is True  # blind retry enabled so a stale mount
    # hint (common with the Seestar) doesn't permanently
    # break auto-solving.
    assert s.ra_hint_hours == 5.5 and s.dec_hint_deg == 22.0
    assert s.fov_hint_deg is not None  # scale hint on by default


def test_build_solve_settings_static_thorough() -> None:
    s = build_solve_settings(
        _cfg({"astrometry.search_radius_deg": 30}), (600, 800), live=False
    )
    assert s.search_radius_deg == 30
    assert s.timeout_s == 120.0
    assert s.allow_blind_retry is True
    assert s.ra_hint_hours is None and s.dec_hint_deg is None


def test_build_solve_settings_no_scale_hint() -> None:
    s = build_solve_settings(
        _cfg({"astrometry.use_scale_hint": False}), (600, 800), live=False
    )
    assert s.fov_hint_deg is None


def test_build_solve_settings_live_without_mount_uses_static_radius() -> None:
    # Live but no mount hint → fall back to the thorough radius (a small radius is
    # meaningless without a position to centre it on).
    s = build_solve_settings(
        _cfg({"astrometry.search_radius_deg": 30, "astrometry.live_search_radius_deg": 4}),
        (600, 800),
        live=True,
        mount_radec=None,
    )
    assert s.search_radius_deg == 30


# --------------------------------------------------------------------------- #
# full_res_scale / wcs_from_result                                            #
# --------------------------------------------------------------------------- #


def test_full_res_scale_halves_green_scale() -> None:
    assert abs(full_res_scale(SolveResult(True, scale_arcsec=7.48)) - 3.74) < 1e-9
    assert full_res_scale(SolveResult(True, scale_arcsec=None)) is None


def test_wcs_from_result_builds_wcs() -> None:
    assert wcs_from_result(SolveResult(True, fields=_FIELDS), _SHAPE) is not None
    assert wcs_from_result(SolveResult(False), _SHAPE) is None


# --------------------------------------------------------------------------- #
# field_geometry / project_points / overlay_for                               #
# --------------------------------------------------------------------------- #


def test_field_geometry_returns_centre_and_fov() -> None:
    geom = field_geometry(frame_wcs(_FIELDS, _SHAPE), _SHAPE)
    assert geom is not None
    ra_deg, dec_deg, radius_deg, fov_arcmin = geom
    assert abs(ra_deg - 83.6) < 0.1
    assert abs(dec_deg - 22.0) < 0.1
    assert radius_deg > 0 and fov_arcmin > 0


def test_field_geometry_none_without_wcs() -> None:
    assert field_geometry(None, _SHAPE) is None


def test_project_points_in_and_out_of_frame() -> None:
    wcs = frame_wcs(_FIELDS, _SHAPE)
    out = project_points(wcs, _SHAPE, [(83.6, 22.0), (180.0, -80.0)])
    assert len(out) == 2  # parallel to the input
    assert out[0] is not None  # field centre is inside the frame
    assert out[1] is None  # far-away point is off-frame


def test_project_points_empty_without_wcs() -> None:
    assert project_points(None, _SHAPE, [(83.6, 22.0)]) == []


def test_overlay_for_applies_spacing() -> None:
    wcs = frame_wcs(_FIELDS, _SHAPE)
    auto = overlay_for(wcs, _SHAPE, _cfg({"astrometry.grid_spacing_arcmin": 0}))
    fine = overlay_for(wcs, _SHAPE, _cfg({"astrometry.grid_spacing_arcmin": 6}))
    assert auto is not None and fine is not None
    assert len(fine.lines) >= len(auto.lines)


def test_overlay_for_none_without_wcs() -> None:
    assert overlay_for(None, _SHAPE, _cfg({})) is None
