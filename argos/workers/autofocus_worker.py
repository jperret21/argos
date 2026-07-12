"""Autofocus worker — two-stage HFD V-curve sweep with verification.

``compute_hfd`` saturates in far defocus (its ROI is smaller than the donut),
so a single full-range sweep is a plateau with one dip — a parabola fitted to
it lands on noise (field-validated 2026-07-11: fit sent a focused scope from
1305 to 1055). Hence two stages:

    1. Coarse: ``num_steps`` evenly-spaced positions across ±``half_range``
       from the start. Only the *raw minimum* is trusted at this stage.
    2. Degenerate-sweep guard (P6): flat curve or edge minimum → restore the
       starting position and report, never move focus on a non-V sweep.
    3. Fine: ``refine_positions`` samples inside ±one coarse interval around
       the raw minimum — the zone where HFD is informative — and the parabola
       is fitted on those samples only (with the vertex-vs-raw guard).
    4. Verify: move to the best position, take one last exposure, and report
       the *measured* HFD there, not the fit's prediction.

Signals:
    step_done(step, total, position, hfd)  — after each measurement
    best_found(position, hfd)              — measured HFD at the final position
    error_occurred(message)
    finished()
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.imaging.debayer import compute_hfd
from argos.core.imaging.focus import fit_v_curve, refine_positions, sweep_is_degenerate

if TYPE_CHECKING:
    from argos.core.alpaca.camera import Camera
    from argos.core.alpaca.focuser import Focuser

logger = logging.getLogger(__name__)

_SETTLE_S = 1.0  # seconds to wait after focuser stops moving
_POLL_INTERVAL_MS = 300
_FINE_COUNT = 4  # fine-stage sample positions around the coarse minimum


class AutofocusWorker(QThread):
    """Run an HFD V-curve sweep in a background thread.

    Args:
        focuser:    Connected :class:`~argos.core.alpaca.focuser.Focuser`.
        camera:     Connected :class:`~argos.core.alpaca.camera.Camera`.
        exposure_s: Exposure time per sample frame (seconds).
        gain:       Camera gain for sample frames.
        half_range: Half-width of the focuser sweep (steps from start).
                    Default 2000 — reasonable for 160 mm refractor.
        num_steps:  Number of sample positions (odd number recommended so the
                    starting position is sampled). Default 9.
    """

    step_done = pyqtSignal(int, int, int, object)  # step, total, pos, hfd|None
    best_found = pyqtSignal(int, object)  # position, hfd|None
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        focuser: "Focuser",
        camera: "Camera",
        exposure_s: float = 5.0,
        gain: int = 80,
        half_range: int = 2000,
        num_steps: int = 9,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._focuser = focuser
        self._camera = camera
        self._exposure = exposure_s
        self._gain = gain
        self._half_range = half_range
        self._num_steps = max(3, num_steps)
        self._stop_flag = False

    def stop(self) -> None:
        self._stop_flag = True
        try:
            self._focuser.halt()
        except Exception:
            pass

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:
            logger.exception("Autofocus error")
            self.error_occurred.emit(str(exc))
        finally:
            self.finished.emit()

    def _run(self) -> None:
        start_pos = self._focuser.get_position()
        low = max(0, start_pos - self._half_range)
        high = min(self._focuser.max_step, start_pos + self._half_range)

        coarse = [int(p) for p in np.unique(np.linspace(low, high, self._num_steps, dtype=int))]
        spacing = coarse[1] - coarse[0] if len(coarse) > 1 else self._half_range
        # Fine positions depend on the coarse minimum, but their count doesn't —
        # announce a stable total: coarse + fine + the verification frame.
        total = len(coarse) + _FINE_COUNT + 1
        step_idx = 0

        # ── Stage 1: coarse sweep — locate the dip, trust only the raw minimum
        measurements = self._measure_positions(coarse, step_idx, total)
        step_idx += len(coarse)

        valid = [(p, h) for p, h in measurements if not np.isnan(h)]
        if self._stop_flag or len(valid) < 3:
            self._restore(start_pos)
            self.best_found.emit(start_pos, None)
            return

        # P6: never move the focus on a curve that isn't a V — a flat sweep
        # (clouds, wrong step size) or an edge minimum would send the focuser
        # to a parabola fitted on noise.
        reason = sweep_is_degenerate(tuple(sorted(valid)))
        if reason is not None:
            logger.warning("Autofocus rejected: %s — focus unchanged", reason)
            self._restore(start_pos)
            self.error_occurred.emit(f"Autofocus: {reason} — focus unchanged")
            self.best_found.emit(start_pos, None)
            return

        raw_min_pos, raw_min_hfd = min(valid, key=lambda t: t[1])

        # ── Stage 2: fine sweep around the raw minimum — the informative zone
        fine = refine_positions(raw_min_pos, spacing, low, high, count=_FINE_COUNT)
        fine_meas = self._measure_positions(fine, step_idx, total)
        step_idx += len(fine)
        if self._stop_flag:
            self._restore(start_pos)
            self.best_found.emit(start_pos, None)
            return

        # Fit on the V zone only: the fine samples plus the coarse minimum.
        # Far-defocus coarse samples are HFD-saturated and would bend the fit.
        window = fine_meas + [(raw_min_pos, raw_min_hfd)]
        result = fit_v_curve(window, raw_min_pos - spacing, raw_min_pos + spacing)
        best_pos = result.best_position
        logger.info(
            "AF best position: %d (HFD=%.1f, %s fit)",
            best_pos,
            result.best_hfd or -1,
            result.method,
        )

        # ── Stage 3: verify — measure at the final position, report reality
        self._focuser.move_to(best_pos)
        self._wait_for_focuser()
        verified = self._capture_hfd()
        self.step_done.emit(total, total, best_pos, verified)
        if verified is not None and result.best_hfd and verified > result.best_hfd * 2.0:
            logger.warning(
                "AF verification HFD %.1f much worse than fitted %.1f", verified, result.best_hfd
            )
        self.best_found.emit(best_pos, verified if verified is not None else result.best_hfd)

    def _measure_positions(
        self, positions: list[int], done: int, total: int
    ) -> list[tuple[int, float]]:
        """Measure HFD at each position; NaN marks a failed frame."""
        out: list[tuple[int, float]] = []
        for i, pos in enumerate(positions):
            if self._stop_flag:
                break
            self._focuser.move_to(int(pos))
            self._wait_for_focuser()
            if self._stop_flag:
                break
            hfd = self._capture_hfd()
            out.append((int(pos), hfd if hfd is not None else float("nan")))
            self.step_done.emit(done + i + 1, total, int(pos), hfd)
            logger.debug("AF step %d/%d  pos=%d  HFD=%s", done + i + 1, total, pos, hfd)
        return out

    def _restore(self, start_pos: int) -> None:
        """Move back to the sweep's starting position."""
        self._focuser.move_to(start_pos)
        self._wait_for_focuser()

    def _wait_for_focuser(self) -> None:
        """Poll until the focuser stops, then wait a settle period."""
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and not self._stop_flag:
            try:
                if not self._focuser.is_moving():
                    break
            except Exception:
                break
            self.msleep(_POLL_INTERVAL_MS)
        if not self._stop_flag:
            self.msleep(int(_SETTLE_S * 1000))

    def _capture_hfd(self) -> float | None:
        """Take one exposure and return its HFD (or None)."""
        try:
            self._camera.start_exposure(self._exposure)
        except Exception as exc:
            logger.warning("AF exposure start: %s", exc)
            return None

        # Wait for the exposure to complete
        deadline = time.monotonic() + self._exposure + 15.0
        while time.monotonic() < deadline and not self._stop_flag:
            self.msleep(_POLL_INTERVAL_MS)
            try:
                if self._camera.is_image_ready():
                    break
            except Exception:
                break

        if self._stop_flag:
            return None

        try:
            arr = self._camera.get_image_array()
        except Exception as exc:
            logger.warning("AF image download: %s", exc)
            return None

        return compute_hfd(arr)
