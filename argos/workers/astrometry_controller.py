"""AstrometryController — the live page's solve lifecycle + auto-solve policy.

See ``notes/photometry_plan.md`` §4 (Workstream A3). A ``QObject`` that lives on the
UI thread and owns a :class:`SolveWorker`. It centralises *when* and *how* the live
frame is plate-solved so the page doesn't grow ad-hoc solve state:

- at most one solve in flight (new requests are dropped while busy);
- **auto mode** re-solves only when it's worth it — there's no WCS yet, the mount
  moved more than ``astrometry.live_resolve_arcmin``, or ``astrometry.live_resolve_s``
  elapsed (between solves a tracked grid stays valid, so we don't thrash);
- **a failed solve keeps the last good WCS** — the grid never blanks on one miss;
- **a wrong solution is refused** (S50): a camera frame's solution whose plate
  scale is more than 1 % from the session's reference keeps the last good WCS,
  as a failed solve does. The reference is the first good solve, moved to the
  mean of any 3 consecutive solves that agree within 0.3 % (S55), so a wrong
  first solve cannot refuse every later good one; a solution that the
  photometry's previous anchors do not confirm is refused the same way (S54,
  :meth:`set_solution_check`);
- live solves use a small search radius + bounded timeout and **skip the slow
  whole-sky blind retry** (via :func:`build_solve_settings`), so the cadence can't
  stall the UI.

Signals:
    solved(FrameWCS, WCSOverlay, str): a fresh solution + grid overlay + summary.
    failed(str): the last solve attempt failed (the previous WCS, if any, is kept).
    state(str): short human status for the page ("Plate-solving…", "Idle", …).
    notice(str): a warning for the Activity log (S55: the scale reference moved).
"""

from __future__ import annotations

import logging
import math
import time

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from argos.core.imaging.astrometry_session import (
    build_solve_settings,
    full_res_scale,
    overlay_for,
    wcs_from_result,
)
from argos.core.imaging.debayer import VIEW_G, extract_plane
from argos.core.imaging.platesolve import angular_separation_deg
from argos.workers.solve_worker import SolveWorker

logger = logging.getLogger(__name__)

#: ``(ra_hours, dec_deg)`` of a pointing or target, or ``None``.
RaDec = tuple[float, float]

#: S50: a camera frame's solution whose plate scale differs from the session's
#: first good solve by more than this fraction is refused. The owner's 270
#: solves span 0.3 % around their night's first; the one wrong match was 3.4 % off.
SCALE_TOLERANCE = 0.01
#: S55: the reference moves to the mean of this many consecutive camera solves
#: when they agree with each other within ``SCALE_AGREEMENT`` (max/min - 1). The
#: owner's good solves span 0.3 % over a night.
SCALE_AGREE_SOLVES = 3
SCALE_AGREEMENT = 0.003


def green_scale_arcsec(wcs) -> float | None:
    """Arcseconds per green px of a solution (its CD matrix), or None."""
    try:
        a, b, c, d = (float(v) for v in wcs.cd)
    except (AttributeError, TypeError, ValueError):
        return None
    det = abs(a * d - b * c)
    return math.sqrt(det) * 3600.0 if det > 0 and math.isfinite(det) else None


class AstrometryController(QObject):
    """Owns the live plate-solve lifecycle + auto-solve policy."""

    solved = pyqtSignal(object, object, str)  # FrameWCS, WCSOverlay, summary
    failed = pyqtSignal(str)
    state = pyqtSignal(str)
    notice = pyqtSignal(str)

    def __init__(self, cfg_get, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg_get
        self._worker: SolveWorker | None = None
        self._auto = False
        self._wcs = None  # platesolve.FrameWCS (last good solution)
        self._green_shape: tuple[int, int] | None = None
        self._last_solve_monotonic = 0.0
        self._last_solve_radec: RaDec | None = None  # mount pointing at the last attempt
        self._pending_target: RaDec | None = None  # target for the in-flight solve's overlay
        #: S50: the in-flight solve is of a camera frame (an opened FITS is not gated).
        self._pending_gate = True
        #: S50: the first good solve's scale (″/green px) and frame geometry.
        self._scale_ref: float | None = None
        self._scale_ref_shape: tuple[int, int] | None = None
        #: S55: the scales of the last camera solves of that geometry (refused ones too).
        self._scale_recent: list[float] = []
        #: S54: ``check(wcs, raw) -> reason | None`` vets a camera frame's new solution.
        self._solution_check = None
        #: S54: the raw frame of the in-flight solve (what its solution describes).
        self._pending_raw: np.ndarray | None = None
        #: S56: the raw frame the current WCS was solved on (None: unknown or dropped).
        self._solved_raw: np.ndarray | None = None
        #: S48: the photometry lost the field: the next frame is due at once.
        self._resolve_due = False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def wcs(self):
        """The last good :class:`FrameWCS`, or ``None``."""
        return self._wcs

    @property
    def solved_raw(self) -> np.ndarray | None:
        """The raw frame the current WCS was solved on (S56: the engine tells a
        solution of this sub or the previous one by identity), or ``None``."""
        return self._solved_raw if self._wcs is not None else None

    @property
    def green_shape(self) -> tuple[int, int] | None:
        """Green shape of the frame the WCS was solved against — its pixel
        coordinates are only valid for frames of this geometry."""
        return self._green_shape

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def set_auto(self, enabled: bool) -> None:
        """Arm/disarm per-frame auto-solving (an in-flight solve still finishes)."""
        self._auto = bool(enabled)
        self.state.emit("Auto-solve on" if self._auto else "Auto-solve off")

    @property
    def auto(self) -> bool:
        return self._auto

    @property
    def scale_reference(self) -> float | None:
        """The session's plate-scale reference (″ per green px): S50's first good
        solve, moved by three agreeing solves (S55)."""
        return self._scale_ref

    def reset_scale_reference(self) -> None:
        """Another camera or telescope: the next good solve is the new reference (S50)."""
        self._scale_ref = None
        self._scale_ref_shape = None
        self._scale_recent = []

    def set_solution_check(self, check) -> None:
        """S54: ``check(wcs, raw)`` returns why a camera frame's new solution is
        refused (the previous anchors show no star where it puts them), or None."""
        self._solution_check = check

    def make_due(self) -> None:
        """The photometry lost the field (S48): the next frame is solved at once."""
        self._resolve_due = True

    def invalidate(self) -> None:
        """Drop the current WCS — a slew/goto makes the previous solution stale.

        The next frame is then immediately "due" (no WCS), so auto mode re-solves
        on the new pointing instead of drawing a grid that no longer matches.
        """
        self._wcs = None
        self._solved_raw = None
        self._last_solve_radec = None
        self.state.emit("WCS cleared (slew)")

    # ------------------------------------------------------------------
    # Solve triggers
    # ------------------------------------------------------------------

    def solve_now(
        self,
        raw: np.ndarray,
        green_shape: tuple[int, int],
        mount_radec: RaDec | None = None,
        target_radec: RaDec | None = None,
        *,
        gate_scale: bool = True,
    ) -> bool:
        """Force a solve (the manual button) — thorough settings, with blind retry.

        ``gate_scale`` False for an opened FITS (another instrument may have
        another scale): its solution neither sets nor is held to the camera's
        reference (S50). Returns ``False`` if a solve is already running.
        """
        if self.is_busy():
            return False
        self._start(raw, green_shape, mount_radec, target_radec, live=False, gate=gate_scale)
        return True

    def on_new_frame(
        self,
        raw: np.ndarray,
        green_shape: tuple[int, int],
        mount_radec: RaDec | None = None,
        target_radec: RaDec | None = None,
        *,
        gate_scale: bool = True,
    ) -> None:
        """Auto-solve hook — called per processed frame. No-op unless armed + due."""
        if not self._auto or self.is_busy() or raw is None:
            return
        if not self._due(mount_radec):
            return
        self._start(raw, green_shape, mount_radec, target_radec, live=True, gate=gate_scale)

    def _due(self, mount_radec: RaDec | None) -> bool:
        if self._wcs is None or self._resolve_due:
            return True
        if (time.monotonic() - self._last_solve_monotonic) >= float(
            self._cfg("astrometry.live_resolve_s", 20.0)
        ):
            return True
        if mount_radec is not None and self._last_solve_radec is not None:
            sep_arcmin = (
                angular_separation_deg(
                    mount_radec[0],
                    mount_radec[1],
                    self._last_solve_radec[0],
                    self._last_solve_radec[1],
                )
                * 60.0
            )
            if sep_arcmin >= float(self._cfg("astrometry.live_resolve_arcmin", 2.0)):
                return True
        return False

    def mount_moved_since_solution(self, mount_radec: RaDec | None) -> bool:
        """Whether the reported mount position makes the current WCS unsafe.

        ``DeviceSession.slewed`` covers GoTo commands issued by Argos itself,
        but an observer may slew from Stellarium or the telescope's native app.
        In that case retaining the former field's WCS is worse than showing no
        overlay: a target aperture can be drawn on empty sky.  Reuse the same
        movement threshold that arms an automatic re-solve.
        """
        if self._wcs is None or mount_radec is None or self._last_solve_radec is None:
            return False
        sep_arcmin = (
            angular_separation_deg(
                mount_radec[0], mount_radec[1], self._last_solve_radec[0], self._last_solve_radec[1]
            )
            * 60.0
        )
        return sep_arcmin >= float(self._cfg("astrometry.live_resolve_arcmin", 2.0))

    def _start(
        self,
        raw: np.ndarray,
        green_shape: tuple[int, int],
        mount_radec: RaDec | None,
        target_radec: RaDec | None,
        *,
        live: bool,
        gate: bool = True,
    ) -> None:
        green = extract_plane(raw, VIEW_G)
        settings = build_solve_settings(self._cfg, green_shape, live=live, mount_radec=mount_radec)
        self._green_shape = green_shape
        self._pending_target = target_radec
        self._pending_gate = gate
        self._pending_raw = raw
        self._resolve_due = False
        self._last_solve_monotonic = time.monotonic()
        self._last_solve_radec = mount_radec
        self.state.emit("Plate-solving…")
        worker = SolveWorker(green, settings, parent=self)
        worker.solved.connect(self._on_worker_solved)
        # Reap the QThread once it finishes — without this every solve leaks a
        # parented SolveWorker (plus its frame copy) for the page's lifetime.
        worker.finished.connect(lambda w=worker: self._reap_worker(w))
        self._worker = worker
        worker.start()

    def _reap_worker(self, worker: SolveWorker) -> None:
        """Release a finished SolveWorker (its ``solved`` result, if any, was
        already delivered — ``finished`` is emitted after ``run()`` returns)."""
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _on_worker_solved(self, result) -> None:
        self.state.emit("Idle")
        raw, self._pending_raw = self._pending_raw, None
        if not result.solved:
            # Keep the previous WCS — a single miss must not blank the grid.
            self.failed.emit(result.message)
            if self._wcs is not None:
                self.state.emit("Solve failed — keeping last WCS")
            return
        wcs = wcs_from_result(result, self._green_shape)
        if wcs is None:
            self.failed.emit("could not build WCS from the solution")
            return
        refusal = self._scale_refusal(wcs)
        if refusal is None and self._pending_gate and self._solution_check is not None:
            # S54: a new solution on which fewer than half the previous tracker's
            # anchors show a star where it puts them (XX Cyg 2026-09-07 045156Z
            # frame 1: 1 of 6) is a wrong match, or the field is not there.
            refusal = self._solution_check(wcs, raw)
        if refusal is not None:
            # S50, S54: a wrong match (XX Cyg 2026-09-07, 3.4 % off) is worse than
            # no new solution: keep the last good WCS, as a failed solve does.
            logger.warning("Solution refused: %s", refusal)
            self.failed.emit(f"solution refused — {refusal}")
            if self._wcs is not None:
                self.state.emit("Solution refused — keeping last WCS")
            return
        self._wcs = wcs
        self._solved_raw = raw
        overlay = overlay_for(wcs, self._green_shape, self._cfg, target_radec=self._pending_target)
        self.solved.emit(wcs, overlay, self._summary(result))

    def _scale_refusal(self, wcs) -> str | None:
        """Why a camera frame's solution is refused (S50), or None to accept it.

        The reference is the session's first good solve (the profile's nominal
        scale is 1.8 % above every measured one), restarted by another frame
        geometry or :meth:`reset_scale_reference`. It moves to the mean of the
        last 3 camera solves (refused ones included) when they agree within
        0.3 % (S55): a wrong first solve no longer refuses every later good one.
        An opened FITS is not gated.
        """
        if not self._pending_gate:
            return None
        scale = green_scale_arcsec(wcs)
        if scale is None:
            return None
        if self._scale_ref is None or self._scale_ref_shape != self._green_shape:
            self._scale_ref = scale
            self._scale_ref_shape = self._green_shape
            self._scale_recent = [scale]
            return None
        self._scale_recent = (self._scale_recent + [scale])[-SCALE_AGREE_SOLVES:]
        recent = self._scale_recent
        if len(recent) == SCALE_AGREE_SOLVES and max(recent) <= min(recent) * (
            1.0 + SCALE_AGREEMENT
        ):
            moved = sum(recent) / len(recent)
            if abs(moved / self._scale_ref - 1.0) > SCALE_TOLERANCE:
                text = (
                    f"Solve: the plate-scale reference moves from {self._scale_ref / 2.0:.3f}″/px"
                    f" to {moved / 2.0:.3f}″/px — {len(recent)} solves agree; the earlier"
                    " reference was a wrong match"
                )
                logger.warning(text)
                self.notice.emit(text)
            self._scale_ref = moved
        deviation = scale / self._scale_ref - 1.0
        if abs(deviation) <= SCALE_TOLERANCE:
            return None
        # Reported per full-res px, as the solve summary is.
        return (
            f"plate scale {scale / 2.0:.3f}″/px is {abs(deviation) * 100.0:.1f} % "
            f"{'below' if deviation < 0 else 'above'} this session's {self._scale_ref / 2.0:.3f}″/px "
            "(a wrong match); the previous solution is kept"
        )

    def _summary(self, result) -> str:
        bits = [f"Solved — RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        scale = full_res_scale(result)
        if scale is not None:
            bits.append(f"{scale:.2f}″/px")
        if result.rotation_deg is not None:
            bits.append(f"rot {result.rotation_deg:.1f}°")
        if self._pending_target is not None:
            sep = angular_separation_deg(
                result.ra_hours, result.dec_deg, self._pending_target[0], self._pending_target[1]
            )
            bits.append(f"Δtarget {sep * 60.0:.1f}′")
        return "  ".join(bits)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def wait(self, ms: int = 2000) -> None:
        """Block until an in-flight solve finishes (called on page shutdown)."""
        if self.is_busy():
            self._worker.wait(ms)
