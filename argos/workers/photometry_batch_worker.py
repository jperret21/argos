"""PhotometryBatchWorker — re-run differential photometry over saved FITS (WS7).

The one genuinely-unique capability of the deleted Photometry Setup window:
measure a whole folder of already-saved subs against a target set, off the UI
thread. Uses the SAME measurement core as the live path
(:func:`argos.core.photometry.params.measure_frame` → ``measure_targets``), so
comps get their catalog magnitudes and the physics is identical; the only
intentional live/batch difference is the aperture FWHM (a saved sub carries no
measured FWHM, so the aperture floors to ``aperture_min_px``).

Emits progress + a per-frame point stream and writes the canonical 9-column
CSVs (:meth:`LightCurve.to_csv`) so Analyze can reload the result. Cancellable
between frames.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.catalog.targets import TargetSet
from argos.core.imaging.green import green_plane
from argos.core.photometry.airmass import bjd_tdb, julian_date
from argos.core.photometry.lightcurve import LcPoint, LightCurve
from argos.core.photometry.params import PhotometryParams, measure_frame
from argos.core.session.types import PhotometryPoint

logger = logging.getLogger(__name__)


@dataclass
class BatchRequest:
    """Inputs for one batch re-run."""

    fits_paths: list[Path]
    wcs: object  # a solved FrameWCS shared by every frame (the reference solve)
    target_set: TargetSet
    params: PhotometryParams
    out_dir: Path  # where the per-target 9-column CSVs are written
    object_name: str = "untitled"
    site: tuple[float | None, float | None, float] = (None, None, 0.0)  # lat, lon, elev


@dataclass
class BatchResult:
    """Outcome of a batch run. ``error`` is empty on success."""

    curves: dict[str, LightCurve] = field(default_factory=dict)
    frames_done: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


class PhotometryBatchWorker(QThread):
    """Measure a list of saved FITS against a target set, off the UI thread.

    Signals:
        progress(int, int): frames done, total.
        point(object): a :class:`PhotometryPoint` per measured target/frame.
        finished_batch(object): a :class:`BatchResult` (check ``.ok``).
    """

    progress = pyqtSignal(int, int)
    point = pyqtSignal(object)
    finished_batch = pyqtSignal(object)

    def __init__(self, request: BatchRequest, parent=None) -> None:
        super().__init__(parent)
        self._req = request
        self._cancel = False

    def cancel(self) -> None:
        """Ask the run to stop at the next frame boundary."""
        self._cancel = True

    def run(self) -> None:
        req = self._req
        lat, lon, elev = req.site
        curves: dict[str, LightCurve] = {}
        total = len(req.fits_paths)
        done = 0
        try:
            for fpath in req.fits_paths:
                if self._cancel:
                    break
                arr, jd = self._read_frame(fpath)
                if arr is None:
                    done += 1
                    self.progress.emit(done, total)
                    continue
                green = green_plane(arr)
                results = measure_frame(green, req.wcs, req.target_set, req.params)
                for res in results:
                    if res.diff is None or res.diff.mag is None:
                        continue
                    bjd = (
                        bjd_tdb(
                            jd,
                            res.star.ra_deg,
                            res.star.dec_deg,
                            float(lat),
                            float(lon),
                            float(elev),
                        )
                        if jd is not None and lat is not None and lon is not None
                        else None
                    )
                    pt = LcPoint(
                        jd_utc=jd or 0.0,
                        mag=res.diff.mag,
                        mag_err=res.diff.mag_err or 0.0,
                        bjd_tdb=bjd,
                        airmass=None,
                        fwhm=None,
                        sky_adu=res.phot.sky_adu if res.phot else None,
                        comps_used=res.diff.comps_used,
                        saturated=bool(res.phot and res.phot.saturated),
                    )
                    key = res.star.auid or res.star.display_name
                    lc = curves.setdefault(
                        key, LightCurve(auid=res.star.auid or "", name=res.star.display_name)
                    )
                    lc.append(pt)
                    self.point.emit(
                        PhotometryPoint(
                            key=key,
                            name=res.star.display_name,
                            jd=pt.jd_utc,
                            mag=pt.mag,
                            mag_err=pt.mag_err,
                            saturated=pt.saturated,
                        )
                    )
                done += 1
                self.progress.emit(done, total)
            self._write_csvs(curves)
            self.finished_batch.emit(BatchResult(curves=curves, frames_done=done))
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Batch photometry crashed")
            self.finished_batch.emit(BatchResult(curves=curves, frames_done=done, error=str(exc)))

    # ------------------------------------------------------------------

    @staticmethod
    def _read_frame(fpath: Path) -> tuple[np.ndarray | None, float | None]:
        """Read a FITS frame → (float32 array, exposure-midpoint JD or None)."""
        from astropy.io import fits

        try:
            with fits.open(fpath) as hdul:
                data = hdul[0].data
                header = hdul[0].header
        except Exception:
            return None, None
        if data is None:
            return None, None
        arr = np.nan_to_num(np.asarray(data, dtype=np.float32))
        jd = None
        date_str = str(header.get("DATE-OBS", "") or "")
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                jd = julian_date(dt)
            except ValueError:
                jd = None
        return arr, jd

    def _write_csvs(self, curves: dict[str, LightCurve]) -> None:
        """Write each curve as the canonical 9-column CSV keyed by object+star."""
        for lc in curves.values():
            tag = lc.auid or lc.name or "photometry"
            safe = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in f"{self._req.object_name}_{tag}"
            )
            try:
                lc.to_csv(self._req.out_dir / f"{safe or 'photometry'}.csv")
            except OSError as exc:
                logger.warning("batch photometry.csv: %s", exc)
