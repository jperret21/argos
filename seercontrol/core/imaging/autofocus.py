"""HFD-based autofocus routine — V-curve scan.

Algorithm:
  1. Coarse scan: take N_COARSE evenly-spaced positions over ±HALF_RANGE steps.
  2. For each position: move focuser, wait, expose, compute HFD.
  3. Find position with minimum HFD → best focus estimate.
  4. Move to best position.

The routine yields AutofocusPoint namedtuples so the caller can update the
V-curve chart in real time.

Usage (inside a QThread):
    af = AutofocusRoutine(focuser, camera, exposure=3.0, gain=80)
    for point in af.run():
        # point.position, point.hfd  — update chart
        if af.aborted:
            break
    best_pos = af.best_position
"""

from __future__ import annotations

import logging
import time
from typing import Iterator, NamedTuple

from PyQt6.QtCore import QThread

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.focuser import Focuser
from seercontrol.core.imaging.debayer import compute_hfd

logger = logging.getLogger(__name__)

# Default scan parameters
N_COARSE    = 9      # number of coarse scan points
HALF_RANGE  = 1000   # ± steps around starting position
MOVE_TIMEOUT = 30    # seconds to wait for a move to complete


class AutofocusPoint(NamedTuple):
    position: int
    hfd: float


class AutofocusRoutine:
    """Run a V-curve HFD scan and return the best focuser position.

    Args:
        focuser:  Connected Focuser instance.
        camera:   Connected Camera instance.
        exposure: Exposure time per sample in seconds.
        gain:     Camera gain.
        n_steps:  Number of scan positions.
        half_range: Half-width of the scan in focuser steps.
    """

    def __init__(
        self,
        focuser: Focuser,
        camera: Camera,
        exposure: float = 3.0,
        gain: int = 80,
        n_steps: int = N_COARSE,
        half_range: int = HALF_RANGE,
    ) -> None:
        self._focuser   = focuser
        self._camera    = camera
        self._exposure  = exposure
        self._gain      = gain
        self._n_steps   = n_steps
        self._half_range = half_range
        self.aborted    = False
        self.best_position: int | None = None
        self.best_hfd: float | None = None

    def run(self) -> Iterator[AutofocusPoint]:
        """Execute the scan; yields one AutofocusPoint per exposure.

        Raises:
            AlpacaError: Any hardware error causes abort.
        """
        start_pos = self._focuser.get_position()
        step = (self._half_range * 2) // max(self._n_steps - 1, 1)

        positions = [
            max(0, min(start_pos - self._half_range + i * step, self._focuser.max_step))
            for i in range(self._n_steps)
        ]

        points: list[AutofocusPoint] = []

        for pos in positions:
            if self.aborted:
                return

            self._move_and_wait(pos)

            if self.aborted:
                return

            arr = self._expose()

            if self.aborted:
                return

            hfd = compute_hfd(arr)
            if hfd is None:
                logger.warning("No star found at position %d — skipping", pos)
                continue

            point = AutofocusPoint(pos, hfd)
            points.append(point)
            logger.info("AF  pos=%d  HFD=%.1f", pos, hfd)
            yield point

        if not points:
            logger.warning("Autofocus: no valid points found, returning to start")
            self._move_and_wait(start_pos)
            return

        best = min(points, key=lambda p: p.hfd)
        self.best_position = best.position
        self.best_hfd = best.hfd

        logger.info("AF best position=%d  HFD=%.1f  → moving", best.position, best.hfd)
        self._move_and_wait(best.position)

    def abort(self) -> None:
        """Signal the scan to stop after the current step."""
        self.aborted = True
        try:
            self._focuser.halt()
        except AlpacaError:
            pass

    # ------------------------------------------------------------------

    def _move_and_wait(self, position: int) -> None:
        self._focuser.move_to(position)
        deadline = time.time() + MOVE_TIMEOUT
        while self._focuser.is_moving():
            if self.aborted or time.time() > deadline:
                return
            QThread.msleep(200)

    def _expose(self) -> "np.ndarray":  # noqa: F821
        try:
            self._camera.set_gain(self._gain)
        except AlpacaError as exc:
            logger.warning("Could not set gain: %s", exc)

        self._camera.start_exposure(self._exposure)
        deadline = time.time() + self._exposure + 20.0
        while not self._camera.is_image_ready():
            if self.aborted:
                return None
            if time.time() > deadline:
                raise AlpacaError(0, "Autofocus exposure timeout")
            QThread.msleep(200)

        return self._camera.get_image_array()
