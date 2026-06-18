"""Live preview worker — continuous short exposures for camera feed.

Runs in a QThread. Loop:
  1. Set gain
  2. Start exposure
  3. Poll imageready every 100 ms
  4. Download imagearray
  5. Emit frame_ready(arr, start_dt, end_dt)
  6. Repeat until stopped

Signals:
  frame_ready(np.ndarray, datetime, datetime)  — (array, exposure_start_utc, exposure_end_utc)
  status_updated(str)      — human-readable state string
  error_occurred(str)      — fatal error, worker stops
  finished()               — loop ended cleanly
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.alpaca.camera import Camera
from argos.core.alpaca.client import AlpacaError

logger = logging.getLogger(__name__)


class LivePreviewWorker(QThread):
    """Continuous live-preview acquisition loop.

    Args:
        camera: Connected Camera instance.
        exposure: Exposure time in seconds (default 1.0).
        gain: Camera gain value.
    """

    frame_ready    = pyqtSignal(object, object, object, object)  # (preview_arr, full_arr, start_dt, end_dt)
    status_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished       = pyqtSignal()

    def __init__(
        self,
        camera: Camera,
        exposure: float = 1.0,
        gain: int = 80,
        preview_scale: int = 4,
    ) -> None:
        super().__init__()
        self._camera        = camera
        self._exposure      = exposure
        self._gain          = gain
        self._preview_scale = max(1, preview_scale)
        self._running       = False

    def update_settings(self, exposure: float, gain: int, scale: int = 0) -> None:
        """Update exposure/gain/preview-scale for the next frame (thread-safe).

        Args:
            exposure: Exposure time in seconds. Ignored if < 0.001 s.
            gain:     Camera gain value.
            scale:    Preview decimation factor (1, 2, 4, 8). 0 = keep current.
        """
        if exposure < 0.001:
            logger.warning("Ignoring suspiciously low exposure value: %.4f s — keeping %.4f s",
                           exposure, self._exposure)
        else:
            self._exposure = exposure
        self._gain = gain
        if scale > 0:
            self._preview_scale = max(1, scale)

    def stop(self) -> None:
        """Request the loop to stop after the current frame."""
        self._running = False
        try:
            self._camera.stop_exposure()
        except AlpacaError:
            pass

    def run(self) -> None:
        self._running = True
        logger.info("LivePreviewWorker started (%.2fs, gain=%d)", self._exposure, self._gain)

        while self._running:
            try:
                # --- Set gain ------------------------------------------------
                try:
                    self._camera.set_gain(self._gain)
                except AlpacaError as exc:
                    logger.warning("Could not set gain: %s", exc)

                # --- Start exposure ------------------------------------------
                self.status_updated.emit(f"Exposing  {self._exposure:.1f}s…")
                exposure_start = datetime.now(timezone.utc)
                self._camera.start_exposure(self._exposure)

                # --- Wait for image ready ------------------------------------
                deadline = time.time() + self._exposure + 20.0
                while not self._camera.is_image_ready():
                    if not self._running:
                        return
                    if time.time() > deadline:
                        raise AlpacaError(0, "Exposure timeout — no image after expected duration")
                    QThread.msleep(100)

                exposure_end = datetime.now(timezone.utc)

                if not self._running:
                    return

                # --- Download image ------------------------------------------
                self.status_updated.emit("Downloading…")
                full_arr = self._camera.get_image_array()

                # Create preview via stride decimation (zero-copy numpy view)
                s = self._preview_scale
                preview_arr = full_arr[::s, ::s] if s > 1 else full_arr
                logger.debug(
                    "Preview scale=%dx: full=%s preview=%s",
                    s, full_arr.shape, preview_arr.shape,
                )

                self.frame_ready.emit(preview_arr, full_arr, exposure_start, exposure_end)
                self.status_updated.emit(
                    f"Live  {self._exposure:.1f}s  gain {self._gain}  "
                    f"preview {preview_arr.shape[1]}×{preview_arr.shape[0]}"
                    + (f"  (1/{s}²)" if s > 1 else "")
                )

            except AlpacaError as exc:
                logger.error("LivePreviewWorker error: %s", exc)
                self.error_occurred.emit(str(exc))
                self._running = False

        logger.info("LivePreviewWorker stopped")
        self.finished.emit()
