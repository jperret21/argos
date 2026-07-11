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

from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, TargetSet
from argos.core.imaging.green import green_plane
from argos.core.photometry.airmass import bjd_tdb, julian_date
from argos.core.photometry.lightcurve import LcPoint, LightCurve
from argos.core.photometry.params import PhotometryParams, measure_frame
from argos.core.photometry.tracking import ApertureTracker, TrackedWCS
from argos.core.session.diagnostics import SessionDiagnostics
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
    diagnostics: bool = True  # flight recorder (diagnostics.jsonl in out_dir, P11)


@dataclass
class BatchResult:
    """Outcome of a batch run. ``error`` is empty on success."""

    curves: dict[str, LightCurve] = field(default_factory=dict)
    frames_done: int = 0
    error: str = ""
    rotation_deg: float = 0.0  # accumulated field rotation vs the reference solve
    shift_px: float = 0.0  # accumulated pointing drift vs the reference solve

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
        self._tracker: ApertureTracker | None = None
        self._check_keys: set[str] = set()  # curve keys that are check stars (P2)

    def cancel(self) -> None:
        """Ask the run to stop at the next frame boundary."""
        self._cancel = True

    def run(self) -> None:
        req = self._req
        curves: dict[str, LightCurve] = {}
        total = len(req.fits_paths)
        done = 0
        safe_obj = "".join(c if c.isalnum() or c in "-_" else "_" for c in req.object_name)
        diag = SessionDiagnostics(
            req.out_dir / f"{safe_obj or 'batch'}_diagnostics.jsonl",
            enabled=req.diagnostics,
        )
        try:
            diag.record(
                "event",
                what="batch_start",
                object=req.object_name,
                n_frames=total,
                track_apertures=req.params.track_apertures,
                band=req.params.band,
            )
            for fpath in req.fits_paths:
                if self._cancel:
                    break
                self._process_frame(diag, fpath, done, curves)
                done += 1
                self.progress.emit(done, total)
            self._write_csvs(curves)
            result = BatchResult(curves=curves, frames_done=done)
            for key in sorted(self._check_keys):
                lc = curves.get(key)
                if lc is None or len(lc.points) < 2:
                    continue
                mags = [p.mag for p in lc.points]
                mean = sum(mags) / len(mags)
                k_rms = (sum((m - mean) ** 2 for m in mags) / (len(mags) - 1)) ** 0.5
                logger.info("Check star %s: RMS %.4f mag over %d frames", key, k_rms, len(mags))
                diag.record("event", what="check_rms", star=key, rms_mag=k_rms, n=len(mags))
            if self._tracker is not None:
                result.rotation_deg = self._tracker.transform.rotation_deg
                result.shift_px = self._tracker.transform.shift_px
                logger.info(
                    "Batch tracking: field rotated %.2f°, drifted %.1f px over %d frames",
                    result.rotation_deg,
                    result.shift_px,
                    done,
                )
            diag.record(
                "event",
                what="batch_end",
                frames_done=done,
                rotation_deg=result.rotation_deg,
                shift_px=result.shift_px,
            )
            self.finished_batch.emit(result)
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Batch photometry crashed")
            diag.record("event", what="batch_crash", error=str(exc))
            self.finished_batch.emit(BatchResult(curves=curves, frames_done=done, error=str(exc)))
        finally:
            diag.close()

    # ------------------------------------------------------------------

    def _process_frame(self, diag, fpath: Path, frame_no: int, curves) -> None:
        """Measure one frame: tracker update, diagnostics records, points."""
        arr, jd = self._read_frame(fpath)
        if arr is None:
            return
        green = green_plane(arr)
        wcs = self._wcs_for_frame(green, fpath.name)
        diag.record("frame", frame=frame_no, file=fpath.name, jd_utc=jd)
        if self._tracker is not None:
            diag.record(
                "tracking",
                frame=frame_no,
                anchors=self._tracker.anchors_used,
                rotation_deg=self._tracker.transform.rotation_deg,
                shift_px=self._tracker.transform.shift_px,
                frames_lost=self._tracker.frames_lost,
            )
        results = measure_frame(
            green,
            wcs,
            self._req.target_set,
            self._req.params,
            on_star=lambda s, phot, x, y: diag.star(frame_no, s, phot, x, y),
        )
        for res in results:
            if res.diff is not None:
                diag.record(
                    "ensemble",
                    frame=frame_no,
                    target=res.star.auid or res.star.display_name,
                    zp=res.diff.zero_point,
                    zp_rms=res.diff.zp_rms,
                    comps_used=res.diff.comps_used,
                    note=res.diff.note or None,
                )
        self._emit_points(results, jd, curves)

    def _wcs_for_frame(self, green, fname: str):
        """Reference WCS, rotation/drift-corrected by the tracker when it locks.

        The tracker is built lazily on the first frame (it needs the frame
        shape for its pivot) and keeps its last good transform on a frame with
        no usable anchor (clouds), so a later frame can re-acquire.
        """
        if not self._req.params.track_apertures:
            return self._req.wcs
        if self._tracker is None:
            self._tracker = self._build_tracker(green.shape)
        self._tracker.update(green)
        if not self._tracker.anchors_used:
            logger.warning("%s: no anchor star found — apertures unguided", fname)
        return TrackedWCS(self._req.wcs, self._tracker)

    def _build_tracker(self, shape: tuple[int, int]) -> ApertureTracker:
        """Anchor the tracker on the stable stars of the set (comps + checks).

        A target's *position* is as stable, but a variable near minimum makes a
        poor centroid — only fall back to targets when there is nothing else.
        """
        tset = self._req.target_set
        anchors = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        if not anchors:
            anchors = list(tset.stars)
        xy = [self._req.wcs.world_to_pixel_deg(s.ra_deg, s.dec_deg) for s in anchors]
        h, w = shape
        search_r = max(8.0, 2.0 * self._req.params.aperture_px(None))
        return ApertureTracker(
            [(float(x), float(y)) for x, y in xy],
            frame_center=(w / 2.0, h / 2.0),
            search_r=search_r,
        )

    def _emit_points(self, results, jd: float | None, curves: dict[str, LightCurve]) -> None:
        """Convert one frame's measurements into curve points + point signals.

        ``results`` carry targets and check stars (P2); checks flow into their
        own curves/CSVs and their keys are remembered for the K-RMS summary.
        """
        for res in results:
            if res.diff is None or res.diff.mag is None:
                continue
            if res.star.role == ROLE_CHECK:
                self._check_keys.add(res.star.auid or res.star.display_name)
            bjd = self._bjd(jd, res.star)
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

    def _bjd(self, jd: float | None, star) -> float | None:
        """BJD_TDB for a star at this frame's JD, or None without site/time."""
        lat, lon, elev = self._req.site
        if jd is None or lat is None or lon is None:
            return None
        return bjd_tdb(jd, star.ra_deg, star.dec_deg, float(lat), float(lon), float(elev))

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
