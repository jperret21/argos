"""Tests for the AstrometryController auto-solve policy (no ASTAP, no solving).

These exercise the pure decision logic (``_due``) + state (``set_auto`` /
``invalidate``). A ``QApplication`` is required because the controller is a
``QObject``; no event loop is run and no solve is started.
"""

from __future__ import annotations

import time

import pytest
from PyQt6.QtWidgets import QApplication

from argos.workers.astrometry_controller import AstrometryController


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _cfg(d: dict):
    return lambda key, default: d.get(key, default)


def test_due_when_no_wcs(qapp) -> None:
    c = AstrometryController(_cfg({}))
    assert c._due(None) is True  # no WCS yet → always due


def test_not_due_within_cadence(qapp) -> None:
    c = AstrometryController(_cfg({"astrometry.live_resolve_s": 100}))
    c._wcs = object()
    c._last_solve_monotonic = time.monotonic()
    c._last_solve_radec = (5.0, 22.0)
    assert c._due((5.0, 22.0)) is False  # fresh + same pointing → not due


def test_due_after_cadence(qapp) -> None:
    c = AstrometryController(_cfg({"astrometry.live_resolve_s": 0.0}))
    c._wcs = object()
    c._last_solve_monotonic = time.monotonic() - 5.0
    assert c._due(None) is True  # cadence elapsed


def test_due_on_mount_move(qapp) -> None:
    c = AstrometryController(
        _cfg({"astrometry.live_resolve_s": 1e6, "astrometry.live_resolve_arcmin": 2.0})
    )
    c._wcs = object()
    c._last_solve_monotonic = time.monotonic()
    c._last_solve_radec = (5.0, 22.0)
    assert c._due((5.0, 22.2)) is True  # 0.2° ≈ 12′ move > 2′ threshold


def test_mount_move_marks_an_existing_wcs_unsafe(qapp) -> None:
    """External telescope slews must not leave target apertures on old pixels."""
    c = AstrometryController(_cfg({"astrometry.live_resolve_arcmin": 2.0}))
    c._wcs = object()
    c._last_solve_radec = (5.0, 22.0)
    assert not c.mount_moved_since_solution((5.0, 22.01))
    assert c.mount_moved_since_solution((5.0, 22.2))


def test_invalidate_clears_wcs(qapp) -> None:
    c = AstrometryController(_cfg({}))
    c._wcs = object()
    c.invalidate()
    assert c.wcs is None


def test_set_auto_toggles(qapp) -> None:
    c = AstrometryController(_cfg({}))
    assert c.auto is False
    c.set_auto(True)
    assert c.auto is True


def test_on_new_frame_noop_when_not_armed(qapp) -> None:
    # Not armed → never touches the (None) raw frame, so no crash.
    c = AstrometryController(_cfg({}))
    c.on_new_frame(None, (10, 10))  # auto off → returns immediately


# ── S50: a solution off the session's plate scale is refused ────────────────


def _result(scale_arcsec_green: float, ra_deg: float = 301.2):
    """A solved ASTAP result whose CD matrix has this scale (″ per green px)."""
    from argos.core.imaging.platesolve import SolveResult

    cd = scale_arcsec_green / 3600.0
    return SolveResult(
        solved=True,
        ra_hours=ra_deg / 15.0,
        dec_deg=58.8,
        scale_arcsec=scale_arcsec_green,
        rotation_deg=0.0,
        fields={
            "CRVAL1": ra_deg,
            "CRVAL2": 58.8,
            "CD1_1": cd,
            "CD1_2": 0.0,
            "CD2_1": 0.0,
            "CD2_2": cd,
        },
    )


def test_a_solution_off_the_session_scale_is_refused_s50(qapp) -> None:
    """XX Cyg 2026-09-07 045156Z frame 2 solved at 7.093″ per green px, every
    other solve of the night at 7.341-7.343: before S50 it replaced the good
    solution and the next frame was measured 21-26 px off every star."""
    c = AstrometryController(_cfg({}))
    solved, failed = [], []
    c.solved.connect(lambda wcs, _o, _s: solved.append(wcs))
    c.failed.connect(failed.append)
    c._green_shape = (1920, 1080)
    c._on_worker_solved(_result(7.342))  # the first good solve: the reference
    first = c.wcs
    assert len(solved) == 1 and first is not None
    c._on_worker_solved(_result(7.093, ra_deg=301.3))  # 3.4 % off: a wrong match
    assert c.wcs is first  # the good solution is kept
    assert len(solved) == 1
    assert failed and "refused" in failed[-1] and "3.4 %" in failed[-1]
    c._on_worker_solved(_result(7.329))  # 0.18 % off: the RR Lyr run's spread
    assert len(solved) == 2 and c.wcs is not first


def test_the_scale_reference_restarts_with_the_camera_or_geometry_s50(qapp) -> None:
    c = AstrometryController(_cfg({}))
    c._green_shape = (1920, 1080)
    c._on_worker_solved(_result(7.342))
    c.reset_scale_reference()  # another camera: a new reference
    c._on_worker_solved(_result(5.84))
    assert abs(c.scale_reference - 5.84) < 1e-9
    c._green_shape = (300, 400)  # another readout geometry: a new reference
    c._on_worker_solved(_result(7.342))
    assert abs(c.scale_reference - 7.342) < 1e-9


def test_an_opened_frame_is_not_held_to_the_camera_scale_s50(qapp) -> None:
    """A FITS from another instrument solves at its own scale; it neither sets
    nor is held to the camera's reference."""
    c = AstrometryController(_cfg({}))
    c._green_shape = (1920, 1080)
    c._on_worker_solved(_result(7.342))
    c._pending_gate = False  # what solve_now(..., gate_scale=False) records
    c._on_worker_solved(_result(5.0))
    assert c.wcs is not None and abs(c.scale_reference - 7.342) < 1e-9


def test_a_lost_lock_makes_a_solve_due_at_once_s48(qapp) -> None:
    c = AstrometryController(_cfg({"astrometry.live_resolve_s": 1e6}))
    c._wcs = object()
    c._last_solve_monotonic = time.monotonic()
    c._last_solve_radec = (5.0, 22.0)
    assert c._due((5.0, 22.0)) is False
    c.make_due()
    assert c._due((5.0, 22.0)) is True
