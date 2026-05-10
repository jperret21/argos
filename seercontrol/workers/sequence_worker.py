"""Sequence worker — executes a full acquisition sequence in a QThread.

For each frame:
  1. Set gain
  2. Start exposure
  3. Poll imageready
  4. Download array
  5. Save FITS (in a QRunnable to not block the acquisition loop)
  6. Emit progress

Signals:
    progress(int, int)      — (frames_done, total_frames)
    frame_saved(str)        — absolute path of the saved FITS file
    status_updated(str)     — human-readable state string
    error_occurred(str)     — fatal error, sequence stops
    finished(int)           — total frames successfully saved
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QRunnable, QThread, QThreadPool, pyqtSignal

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.imaging.fits_writer import FITSWriter
from seercontrol.core.imaging.sequencer import SequenceConfig

logger = logging.getLogger(__name__)


class SequenceWorker(QThread):
    """Runs a SequenceConfig acquisition loop.

    Args:
        camera:    Connected Camera instance.
        config:    Sequence configuration (frame type, count, exposure…).
        telescope: Optional connected Telescope instance for FITS pointing headers.
        observer:  Observer name from config.
        site_lat:  Observer latitude.
        site_lon:  Observer longitude.
        site_elev: Observer elevation in metres.
    """

    progress       = pyqtSignal(int, int)   # (done, total)
    frame_saved    = pyqtSignal(str)        # absolute FITS path
    status_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished       = pyqtSignal(int)        # total saved

    def __init__(
        self,
        camera: Camera,
        config: SequenceConfig,
        telescope=None,
        observer: str = "",
        site_lat: float | None = None,
        site_lon: float | None = None,
        site_elev: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._camera    = camera
        self._config    = config
        self._telescope = telescope
        self._observer  = observer
        self._site_lat  = site_lat
        self._site_lon  = site_lon
        self._site_elev = site_elev
        self._running   = False
        self._pool      = QThreadPool.globalInstance()

    def stop(self) -> None:
        """Request the sequence to stop after the current frame."""
        self._running = False
        try:
            self._camera.stop_exposure()
        except AlpacaError:
            pass

    def run(self) -> None:
        self._running = True
        cfg = self._config
        session_start = datetime.now(timezone.utc)
        folder = cfg.frame_folder(session_start)
        folder.mkdir(parents=True, exist_ok=True)

        logger.info(
            "SequenceWorker started: %d × %s  %.1fs  gain=%d  → %s",
            cfg.count, cfg.frame_type.label, cfg.actual_exposure, cfg.gain, folder,
        )

        saved = 0
        for frame_idx in range(1, cfg.count + 1):
            if not self._running:
                break

            self.status_updated.emit(
                f"Frame {frame_idx}/{cfg.count}  {cfg.actual_exposure:.1f}s  gain {cfg.gain}"
            )

            try:
                start_dt, end_dt, arr = self._acquire()
            except AlpacaError as exc:
                logger.error("SequenceWorker acquisition error: %s", exc)
                self.error_occurred.emit(str(exc))
                self._running = False
                break

            if not self._running:
                break

            filename = cfg.build_filename(frame_idx, start_dt)
            path = folder / filename

            # Read pointing from telescope (best-effort)
            ra = dec = alt = az = None
            if self._telescope:
                try:
                    pos = self._telescope.get_position()
                    ra, dec = pos.ra, pos.dec
                    alt, az = pos.altitude, pos.azimuth
                except Exception:
                    pass

            self._save_async(arr, path, start_dt, end_dt, ra, dec, alt, az)
            saved += 1
            self.frame_saved.emit(str(path))
            self.progress.emit(frame_idx, cfg.count)

        self.status_updated.emit(f"Done  {saved}/{cfg.count} frames saved")
        logger.info("SequenceWorker finished: %d frames saved", saved)
        self.finished.emit(saved)

    # ------------------------------------------------------------------

    def _acquire(self):
        cfg = self._config
        try:
            self._camera.set_gain(cfg.gain)
        except AlpacaError as exc:
            logger.warning("Could not set gain: %s", exc)

        start_dt = datetime.now(timezone.utc)
        self._camera.start_exposure(cfg.actual_exposure)

        deadline = time.time() + cfg.actual_exposure + 20.0
        while not self._camera.is_image_ready():
            if not self._running:
                raise AlpacaError(0, "Sequence stopped by user")
            if time.time() > deadline:
                raise AlpacaError(0, "Exposure timeout")
            QThread.msleep(100)

        end_dt = datetime.now(timezone.utc)
        arr = self._camera.get_image_array()
        return start_dt, end_dt, arr

    def _save_async(self, arr, path: Path, start_dt, end_dt, ra, dec, alt, az) -> None:
        cfg = self._config

        observer    = self._observer
        site_lat    = self._site_lat
        site_lon    = self._site_lon
        site_elev   = self._site_elev

        class _SaveTask(QRunnable):
            def run(self) -> None:
                try:
                    FITSWriter.write(
                        arr=arr,
                        path=path,
                        exposure_start=start_dt,
                        exposure_end=end_dt,
                        exposure_time=cfg.actual_exposure,
                        gain=cfg.gain,
                        image_type=cfg.frame_type.fits_value,
                        ra=ra,
                        dec=dec,
                        altitude=alt,
                        azimuth=az,
                        object_name=cfg.object_name,
                        filter_name=cfg.filter_name if cfg.frame_type.needs_filter else "NoFilter",
                        observer=observer,
                        site_lat=site_lat,
                        site_lon=site_lon,
                        site_elev=site_elev,
                    )
                except Exception as exc:
                    logger.error("FITS save failed for %s: %s", path.name, exc)

        self._pool.start(_SaveTask())
