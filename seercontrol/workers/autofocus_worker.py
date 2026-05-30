"""Autofocus worker — HFD V-curve sweep and parabola fit.

Algorithm:
    1. Record starting position.
    2. Move to (start − half_range), then step through ``num_steps`` evenly-
       spaced positions up to (start + half_range).
    3. At each position, wait for the focuser to stop, take one exposure,
       compute HFD from the green channel.
    4. When all steps are done, fit a 2nd-order polynomial to the
       (position, HFD) data and move to the vertex (minimum HFD).
    5. If the fit is unreliable (concave-up parabola opening downward, or
       vertex outside the scanned range) fall back to the raw minimum.

Signals:
    step_done(step, total, position, hfd)  — after each measurement
    best_found(position, hfd)              — when the best position is known
    error_occurred(message)
    finished()
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from seercontrol.core.imaging.debayer import compute_hfd

if TYPE_CHECKING:
    from seercontrol.core.alpaca.camera import Camera
    from seercontrol.core.alpaca.focuser import Focuser

logger = logging.getLogger(__name__)

_SETTLE_S    = 1.0   # seconds to wait after focuser stops moving
_POLL_INTERVAL_MS = 300


class AutofocusWorker(QThread):
    """Run an HFD V-curve sweep in a background thread.

    Args:
        focuser:    Connected :class:`~seercontrol.core.alpaca.focuser.Focuser`.
        camera:     Connected :class:`~seercontrol.core.alpaca.camera.Camera`.
        exposure_s: Exposure time per sample frame (seconds).
        gain:       Camera gain for sample frames.
        half_range: Half-width of the focuser sweep (steps from start).
                    Default 2000 — reasonable for 160 mm refractor.
        num_steps:  Number of sample positions (odd number recommended so the
                    starting position is sampled). Default 9.
    """

    step_done      = pyqtSignal(int, int, int, object)   # step, total, pos, hfd|None
    best_found     = pyqtSignal(int, object)             # position, hfd|None
    error_occurred = pyqtSignal(str)
    finished       = pyqtSignal()

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
        self._focuser    = focuser
        self._camera     = camera
        self._exposure   = exposure_s
        self._gain       = gain
        self._half_range = half_range
        self._num_steps  = max(3, num_steps)
        self._stop_flag  = False

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
        low  = max(0, start_pos - self._half_range)
        high = min(self._focuser.max_step, start_pos + self._half_range)

        positions = np.linspace(low, high, self._num_steps, dtype=int)
        positions = np.unique(positions)

        measurements: list[tuple[int, float]] = []

        for step_idx, pos in enumerate(positions):
            if self._stop_flag:
                break

            self._focuser.move_to(int(pos))
            self._wait_for_focuser()

            if self._stop_flag:
                break

            hfd = self._capture_hfd()
            measurements.append((int(pos), hfd if hfd is not None else float("nan")))
            self.step_done.emit(step_idx + 1, len(positions), int(pos), hfd)
            logger.debug("AF step %d/%d  pos=%d  HFD=%s", step_idx + 1, len(positions), pos, hfd)

        if self._stop_flag or len(measurements) < 3:
            # Return to start and give up
            self._focuser.move_to(start_pos)
            self._wait_for_focuser()
            self.best_found.emit(start_pos, None)
            return

        best_pos, best_hfd = self._find_best(measurements, low, high)
        logger.info("AF best position: %d (HFD=%.1f)", best_pos, best_hfd or -1)

        self._focuser.move_to(best_pos)
        self._wait_for_focuser()
        self.best_found.emit(best_pos, best_hfd)

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

    @staticmethod
    def _find_best(
        measurements: list[tuple[int, float]],
        low: int,
        high: int,
    ) -> tuple[int, float | None]:
        """Return (best_position, best_hfd) from a list of (pos, hfd) pairs.

        Tries a parabola fit first; falls back to the raw minimum if the fit
        is degenerate.
        """
        # Filter NaN
        valid = [(p, h) for p, h in measurements if not np.isnan(h)]
        if len(valid) < 3:
            if valid:
                best_raw = min(valid, key=lambda x: x[1])
                return int(best_raw[0]), float(best_raw[1])
            return int(measurements[len(measurements) // 2][0]), None

        pos_arr = np.array([p for p, _ in valid], dtype=float)
        hfd_arr = np.array([h for _, h in valid], dtype=float)

        best_raw = valid[int(np.argmin(hfd_arr))]

        # Parabola fit — only use if the parabola opens upward (a > 0) and the
        # vertex falls within the scanned range.
        try:
            coeffs = np.polyfit(pos_arr, hfd_arr, 2)
            a, b, _ = coeffs
            if a > 0:
                vertex = -b / (2.0 * a)
                if low <= vertex <= high:
                    poly = np.poly1d(coeffs)
                    fitted_hfd = float(poly(vertex))
                    return int(round(vertex)), round(fitted_hfd, 1)
        except Exception as exc:
            logger.debug("Parabola fit failed: %s", exc)

        return int(best_raw[0]), float(best_raw[1])
