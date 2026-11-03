"""Live preview worker — continuous short exposures for camera feed.

Runs in a QThread. Loop:
  1. Set gain
  2. Start exposure
  3. Poll imageready every 100 ms
  4. Download imagearray
  5. Emit frame_ready(preview, full, start_dt, end_dt, FrameSettings)
  6. Repeat until stopped

Signals:
  frame_ready(preview, full, start, end, FrameSettings)  — arrays, UTC times, settings used
  status_updated(str)      — human-readable state string
  error_occurred(str)      — fatal error, worker stops
  finished()               — loop ended cleanly
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.imaging.debayer import downsample_cfa
from argos.core.alpaca.camera import Camera
from argos.core.alpaca.client import AlpacaError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameSettings:
    """The settings one frame was actually exposed with, emitted with it.

    ``update_settings`` arrives from the UI thread at any time, so whoever
    saves the frame must not re-read the form: the form may already hold the
    next frame's values (wrong EXPTIME/GAIN/IMAGETYP in the header).
    """

    #: Exposure (s) passed to ``start_exposure``.
    exposure_s: float
    #: Gain passed to ``set_gain``.
    gain: int
    #: Shutter semantics passed to ``start_exposure``.
    light: bool
    #: Opaque caller data applied with these settings (the engine's form snapshot).
    tag: object = None


class LivePreviewWorker(QThread):
    """Continuous live-preview acquisition loop.

    Args:
        camera: Connected Camera instance.
        exposure: Exposure time in seconds (default 1.0).
        gain: Camera gain value.
        light: True exposes light frames (shutter open); False exposes
            dark/bias frames — so single-shot darks are honest.
        tag: Opaque caller data emitted back with every frame exposed with
            these settings (see :class:`FrameSettings`).
    """

    frame_ready = pyqtSignal(
        object, object, object, object, object
    )  # (preview_arr, full_arr, start_dt, end_dt, FrameSettings)
    status_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        camera: Camera,
        exposure: float = 1.0,
        gain: int = 80,
        preview_scale: int = 4,
        light: bool = True,
        tag: object = None,
    ) -> None:
        super().__init__()
        self._camera = camera
        # (exposure, gain, light, tag) for the next frame. Replaced as one
        # tuple so the loop never mixes the old and the new settings, and
        # taken once per frame so the emitted FrameSettings are the ones used.
        self._settings: tuple[float, int, bool, object] = (exposure, gain, bool(light), tag)
        self._preview_scale = max(1, preview_scale)
        self._running = False

    def update_settings(
        self,
        exposure: float,
        gain: int,
        scale: int = 0,
        light: bool | None = None,
        tag: object = None,
    ) -> None:
        """Update exposure/gain/preview-scale for the next frame (thread-safe).

        Args:
            exposure: Exposure time in seconds. Ignored if < 0.001 s.
            gain:     Camera gain value.
            scale:    Preview decimation factor (1, 2, 4, 8). 0 = keep current.
            light:    Shutter semantics for the next frame (True = light,
                      False = dark/bias). None = keep current.
            tag:      Caller data emitted with the next frames. None = keep.
        """
        cur_exposure, _gain, cur_light, cur_tag = self._settings
        if exposure < 0.001:
            logger.warning(
                "Ignoring suspiciously low exposure value: %.4f s — keeping %.4f s",
                exposure,
                cur_exposure,
            )
            exposure = cur_exposure
        if scale > 0:
            self._preview_scale = max(1, scale)
        self._settings = (
            exposure,
            gain,
            cur_light if light is None else bool(light),
            cur_tag if tag is None else tag,
        )

    def stop(self) -> None:
        """Request the loop to stop after the current frame."""
        self._running = False
        try:
            self._camera.stop_exposure()
        except AlpacaError:
            pass

    def run(self) -> None:
        self._running = True
        exposure, gain, light, tag = self._settings
        logger.info("LivePreviewWorker started (%.2fs, gain=%d)", exposure, gain)

        while self._running:
            try:
                # One snapshot per frame: these exact values are applied to
                # the camera and emitted with the frame.
                exposure, gain, light, tag = self._settings

                # --- Set gain ------------------------------------------------
                try:
                    self._camera.set_gain(gain)
                except AlpacaError as exc:
                    logger.warning("Could not set gain: %s", exc)

                # --- Start exposure ------------------------------------------
                self.status_updated.emit(f"Exposing  {exposure:.1f}s…")
                exposure_start = datetime.now(timezone.utc)
                self._camera.start_exposure(exposure, light=light)

                # --- Wait for image ready ------------------------------------
                deadline = time.time() + exposure + 20.0
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

                # Create a reduced CFA preview without discarding three Bayer
                # colours. A raw stride would make a green-looking false RGB
                # image at half resolution.
                s = self._preview_scale
                preview_arr = downsample_cfa(full_arr, s) if s > 1 else full_arr
                logger.debug(
                    "Preview scale=%dx: full=%s preview=%s",
                    s,
                    full_arr.shape,
                    preview_arr.shape,
                )

                self.frame_ready.emit(
                    preview_arr,
                    full_arr,
                    exposure_start,
                    exposure_end,
                    FrameSettings(exposure, gain, light, tag),
                )
                self.status_updated.emit(
                    f"Live  {exposure:.1f}s  gain {gain}  "
                    f"preview {preview_arr.shape[1]}×{preview_arr.shape[0]}"
                    + (f"  (1/{s}²)" if s > 1 else "")
                )

            except AlpacaError as exc:
                logger.error("LivePreviewWorker error: %s", exc)
                self.error_occurred.emit(str(exc))
                self._running = False

        logger.info("LivePreviewWorker stopped")
        self.finished.emit()
