"""Tests for ASTAP plate-solving glue — parsing + command, no ASTAP needed."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from seercontrol.core.imaging import platesolve
from seercontrol.core.imaging.platesolve import (
    SolveSettings,
    _build_command,
    angular_separation_deg,
    find_astap,
    format_dec_dms,
    format_ra_hms,
    frame_wcs,
    parse_astap_ini,
    solve_array,
    wcs_grid,
)

# A clean aligned green-plane solution: ~7.48″/px (≈0.002078°), N up, E left.
_SCALE_DEG = 7.48 / 3600.0
_WCS_FIELDS = {
    "CRVAL1": "83.6",  # RA  deg (≈ 5.5733 h)
    "CRVAL2": "22.0",  # Dec deg
    "CRPIX1": "513.0",  # 1-based reference pixel
    "CRPIX2": "385.0",
    "CD1_1": f"{-_SCALE_DEG}",
    "CD1_2": "0.0",
    "CD2_1": "0.0",
    "CD2_2": f"{_SCALE_DEG}",
}
_GREEN_SHAPE = (768, 1024)  # (h, w)

_SOLVED_INI = """
PLTSOLVD=T
CRVAL1=83.633
CRVAL2=22.0145
CD1_1=-0.000277
CD1_2=0.0
CD2_1=0.0
CD2_2=0.000277
CROTA2=0.5
"""

_FAILED_INI = """
PLTSOLVD=F
ERROR=No solution found
"""


def test_parse_solved_ini() -> None:
    r = parse_astap_ini(_SOLVED_INI)
    assert r.solved
    assert abs(r.ra_hours - 5.5755) < 0.01
    assert abs(r.dec_deg - 22.0145) < 0.01
    assert r.scale_arcsec is not None and abs(r.scale_arcsec - 0.997) < 0.05
    assert r.rotation_deg is not None
    assert r.mirrored is False  # negative CD determinant


def test_parse_failed_ini() -> None:
    r = parse_astap_ini(_FAILED_INI)
    assert not r.solved
    assert "No solution" in r.message


def test_build_command_hinted() -> None:
    s = SolveSettings(
        search_radius_deg=15,
        downsample=2,
        fov_hint_deg=0.8,
        ra_hint_hours=5.5,
        dec_hint_deg=22.0,
        database="V17",
    )
    cmd = _build_command("astap", Path("/tmp/x.fits"), s)
    assert cmd[0] == "astap" and "-wcs" in cmd
    assert "-r" in cmd and "15" in cmd
    assert "-z" in cmd and "2" in cmd
    assert "-fov" in cmd
    assert "-ra" in cmd and "-spd" in cmd  # dec+90 hint
    assert "-d" in cmd and "V17" in cmd


def test_build_command_blind_uses_full_sky() -> None:
    cmd = _build_command("astap", Path("/tmp/x.fits"), SolveSettings(search_radius_deg=0))
    assert "180" in cmd  # blind → whole-sky radius


def test_find_astap_explicit_path(tmp_path) -> None:
    fake = tmp_path / "astap_cli"
    fake.write_text("#!/bin/sh\n")
    assert find_astap(str(fake)) == str(fake)


def test_solve_array_reports_missing_astap(monkeypatch) -> None:
    monkeypatch.setattr(platesolve, "find_astap", lambda _p: None)
    r = solve_array(np.zeros((16, 16), np.uint16), SolveSettings())
    assert not r.solved
    assert "not found" in r.message.lower()


def test_solve_array_rejects_non_2d(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "astap"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(platesolve, "find_astap", lambda _p: str(fake))
    r = solve_array(np.zeros((4, 4, 3), np.uint16), SolveSettings())
    assert not r.solved
    assert "2-D" in r.message or "2-d" in r.message.lower()


# --------------------------------------------------------------------------- #
# WCS model (§6)                                                               #
# --------------------------------------------------------------------------- #


def test_frame_wcs_centre_maps_to_crval() -> None:
    wcs = frame_wcs(_WCS_FIELDS, _GREEN_SHAPE)
    assert wcs is not None
    # CRPIX is 1-based; the 0-based reference pixel is (512, 384).
    ra_h, dec_d = wcs.pixel_to_radec(512.0, 384.0)
    assert abs(ra_h - 83.6 / 15.0) < 1e-3
    assert abs(dec_d - 22.0) < 1e-4


def test_frame_wcs_round_trip() -> None:
    wcs = frame_wcs(_WCS_FIELDS, _GREEN_SHAPE)
    assert wcs is not None
    ra_h, dec_d = wcs.pixel_to_radec(700.0, 300.0)
    x, y = wcs.radec_to_pixel(ra_h, dec_d)
    assert abs(x - 700.0) < 1e-3
    assert abs(y - 300.0) < 1e-3


def test_frame_wcs_orientation_east_left_north_up() -> None:
    wcs = frame_wcs(_WCS_FIELDS, _GREEN_SHAPE)
    assert wcs is not None
    ra0, dec0 = wcs.pixel_to_radec(512.0, 384.0)
    ra_right, _ = wcs.pixel_to_radec(612.0, 384.0)  # +x → RA decreases (E left)
    _, dec_up = wcs.pixel_to_radec(512.0, 484.0)  # +y → Dec increases (N up)
    assert ra_right < ra0
    assert dec_up > dec0


def test_frame_wcs_crpix_fallback_to_centre() -> None:
    fields = {k: v for k, v in _WCS_FIELDS.items() if not k.startswith("CRPIX")}
    wcs = frame_wcs(fields, _GREEN_SHAPE)
    assert wcs is not None
    gh, gw = _GREEN_SHAPE
    # Centre of the frame should land on CRVAL when CRPIX defaults to the middle.
    ra_h, dec_d = wcs.pixel_to_radec((gw - 1) / 2.0, (gh - 1) / 2.0)
    assert abs(ra_h - 83.6 / 15.0) < 1e-3
    assert abs(dec_d - 22.0) < 1e-3


def test_frame_wcs_returns_none_without_keys() -> None:
    assert frame_wcs({}) is None
    assert frame_wcs({"CRVAL1": "83.6"}) is None  # missing CRVAL2
    # CRVAL present but no CD and no CDELT → cannot build.
    assert frame_wcs({"CRVAL1": "83.6", "CRVAL2": "22.0"}, _GREEN_SHAPE) is None


def test_frame_wcs_from_cdelt_crota() -> None:
    fields = {
        "CRVAL1": "83.6",
        "CRVAL2": "22.0",
        "CRPIX1": "513.0",
        "CRPIX2": "385.0",
        "CDELT1": f"{-_SCALE_DEG}",
        "CDELT2": f"{_SCALE_DEG}",
        "CROTA2": "0.0",
    }
    wcs = frame_wcs(fields, _GREEN_SHAPE)
    assert wcs is not None
    ra_h, dec_d = wcs.pixel_to_radec(512.0, 384.0)
    assert abs(ra_h - 83.6 / 15.0) < 1e-3
    assert abs(dec_d - 22.0) < 1e-4


def test_wcs_grid_has_lines_and_centre() -> None:
    wcs = frame_wcs(_WCS_FIELDS, _GREEN_SHAPE)
    overlay = wcs_grid(wcs, _GREEN_SHAPE)
    assert overlay.lines  # at least one RA and one Dec line cross the frame
    assert overlay.center is not None
    cx, cy = overlay.center
    assert abs(cx - 512.0) < 1.0 and abs(cy - 384.0) < 1.0  # centre ≈ CRPIX-1
    assert "RA" in overlay.center_label and "Dec" in overlay.center_label
    assert overlay.target is None


def test_wcs_grid_target_reticle() -> None:
    wcs = frame_wcs(_WCS_FIELDS, _GREEN_SHAPE)
    # A target a touch off-centre should project to a pixel near, but not at, the centre.
    overlay = wcs_grid(wcs, _GREEN_SHAPE, target_radec=(83.7 / 15.0, 22.05))
    assert overlay.target is not None
    tx, ty = overlay.target
    assert 0 <= tx <= _GREEN_SHAPE[1] and 0 <= ty <= _GREEN_SHAPE[0]
    assert (tx, ty) != overlay.center


# --------------------------------------------------------------------------- #
# Formatting + spherical helpers (§6)                                          #
# --------------------------------------------------------------------------- #


def test_format_ra_hms() -> None:
    assert format_ra_hms(5.5733).startswith("05h")
    assert format_ra_hms(0.0) == "00h00m00.0s"
    assert format_ra_hms(24.0) == "00h00m00.0s"  # wraps


def test_format_dec_dms() -> None:
    assert format_dec_dms(22.0) == "+22°00'00.0\""
    assert format_dec_dms(-5.5).startswith("-05°30'")


def test_angular_separation_deg() -> None:
    assert angular_separation_deg(5.0, 22.0, 5.0, 22.0) == 0.0
    assert abs(angular_separation_deg(0.0, 0.0, 0.0, 1.0) - 1.0) < 1e-6
    # 1 minute of RA at the equator ≈ 15 arcmin = 0.25°.
    assert abs(angular_separation_deg(0.0, 0.0, 1.0 / 60.0, 0.0) - 0.25) < 1e-3
