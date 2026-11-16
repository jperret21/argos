"""PhotometryBatchWorker — re-run differential photometry over saved FITS (WS7).

The one genuinely-unique capability of the deleted Photometry Setup window:
measure a whole folder of already-saved subs against a target set, off the UI
thread. Uses the SAME measurement core as the live path
(:func:`argos.core.photometry.params.measure_frame` → ``measure_targets``), so
comps get their catalog magnitudes and the physics is identical; the only
intentional live/batch difference is the aperture FWHM: this worker measures the
field FWHM once, on the first readable frame, and holds it for the whole series.
Only when no stars are detected does it fall through to ``DEFAULT_FWHM`` — which
gives a *wider* aperture than the floor, not the floor itself.

Emits progress + a per-frame point stream and writes the canonical 9-column
CSVs (:meth:`LightCurve.to_csv`) so Analyze can reload the result. Cancellable
between frames.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, ROLE_TARGET, TargetSet
from argos.core.imaging.green import green_plane
from argos.core.photometry.airmass import airmass_at, bjd_tdb, julian_date
from argos.core.imaging.fits_writer import filter_token
from argos.core.photometry.lightcurve import (
    LcPoint,
    LightCurve,
    curve_key,
    run_curve_csv_name,
    series_label,
)
from argos.core.photometry.params import PhotometryParams, frame_egain, measure_frame
from argos.core.photometry.tracking import (
    ApertureTracker,
    TrackedWCS,
    anchors_seen,
    centring_offsets,
    off_centre,
    rotation_resolve_due,
    select_tracking_anchors,
)
from argos.core.photometry.uncertainty import apply_systematic_floor, estimate_systematic_floor
from argos.core.session.diagnostics import SessionDiagnostics
from argos.core.session.review import (
    SITE_CHECK_TOLERANCE_DEG,
    FrozenPointing,
    no_detection_flags,
    read_frame_pointing,
    site_offset_deg,
)
from argos.core.session.types import PhotometryPoint

logger = logging.getLogger(__name__)

#: FITS file suffixes a re-run accepts (any case). Argos itself writes ``.fit``.
_FITS_SUFFIXES = (".fit", ".fits", ".fts")
#: IMAGETYP words that mark a calibration frame, never measured as a light.
_CALIBRATION_WORDS = ("dark", "flat", "bias", "offset", "zero")
#: S43: an anchor is seen when its aperture at the tracked position has this SNR
#: (the S35 "seen" threshold); the lock holds when half the anchors are seen.
_LOCK_MIN_SNR = 5.0
#: S58 (S56's rule in the re-run): with fewer anchors ceil(n/2) is met by the very
#: anchor that moved the apertures, so the S43 check verifies nothing; such a frame
#: is verified only when measured through a solution of this frame or the previous
#: one and the tracker moved no aperture of the set this many green px or more from
#: where that solution puts it. Otherwise it is re-solved (with a solver) or flagged.
_LOCK_VERIFY_MIN_ANCHORS = 3
_LOCK_FRESH_MAX_SHIFT_PX = 2.0


def _object_key(name) -> str:
    """An object name compared without case, spaces or underscores (S62)."""
    return "".join(c for c in str(name or "").lower() if c.isalnum())


def _session_lights_only(path: Path, top: Path) -> bool:
    """S63: a FITS found below ``top`` is a frame of the run unless an Argos session
    folder (one holding ``session.json`` and ``lights/``) holds it outside ``lights/``.
    """
    for parent in path.parents:
        if (parent / "session.json").is_file():
            lights = parent / "lights"
            return not lights.is_dir() or lights in path.parents
        if parent == top:
            break
    return True


def discover_light_frames(folder: Path, object_name: str | None = None) -> list[Path]:
    """The light frames a batch re-run should measure under ``folder``.

    ``.fit``/``.fits``/``.fts`` files (any case) in the folder itself, or in
    its subfolders when it has none (a session root holds lights/, darks/,
    flats/, biases/). Frames whose ``IMAGETYP`` names a calibration type are
    left out; a frame without IMAGETYP is kept. With ``object_name`` (S62),
    frames whose ``OBJECT`` names another object are left out too (another
    field, measured against this target set); a frame without OBJECT is kept.
    In a subfolder search, an Argos session folder's frames are its ``lights/``
    only, and a link to a frame already listed is that frame (S63: Siril's
    ``process/`` beside the lights holds links to them and registered copies).
    Ordered by ``DATE-OBS``, frames without a readable date last, by name.
    """
    from astropy.io import fits

    folder = Path(folder)
    wanted = _object_key(object_name)

    def fits_files(paths) -> list[Path]:
        return [p for p in paths if p.is_file() and p.suffix.lower() in _FITS_SUFFIXES]

    found = fits_files(sorted(folder.glob("*"))) or [
        p for p in fits_files(sorted(folder.rglob("*"))) if _session_lights_only(p, folder)
    ]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        real = path.resolve()
        if real not in seen:  # S63: a link to a frame already listed is that frame
            seen.add(real)
            candidates.append(path)
    dated: list[tuple[datetime, Path]] = []
    undated: list[Path] = []
    for path in candidates:
        try:
            header = fits.getheader(path)
        except Exception:  # unreadable: the batch reports it as a skipped frame
            undated.append(path)
            continue
        imagetyp = str(header.get("IMAGETYP", "") or "").lower()
        if any(word in imagetyp for word in _CALIBRATION_WORDS):
            continue
        frame_object = _object_key(header.get("OBJECT"))
        if wanted and frame_object and frame_object != wanted:
            continue  # S62: another object's frame
        try:
            start = datetime.fromisoformat(str(header.get("DATE-OBS") or "").replace("Z", "+00:00"))
        except ValueError:
            undated.append(path)
            continue
        if start.tzinfo is not None:  # FITS dates are UTC; compare naive UTC
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        dated.append((start, path))
    dated.sort(key=lambda item: (item[0], item[1].name))
    return [path for _start, path in dated] + sorted(undated, key=lambda p: p.name)


def rerun_output_dir(frames_folder: Path, now: datetime) -> Path:
    """A new folder for one re-run's CSVs: never another run's files.

    ``<session root>/photometry_rerun_<UTC>`` when ``session.json`` sits in
    ``frames_folder`` or its parent (an Argos session or its lights/ folder),
    else ``<frames_folder>/photometry_rerun_<UTC>``.
    """
    folder = Path(frames_folder)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for root in (folder, folder.parent):
        if (root / "session.json").is_file():
            return root / f"photometry_rerun_{stamp}"
    return folder / f"photometry_rerun_{stamp}"


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
    #: ``camera.egain_table``: each frame's errors use its own gain (``frame_egain``);
    #: ``params.egain`` only for a frame that records none.
    egain_table: dict = field(default_factory=dict)
    #: Plate-solves a frame's green plane -> FrameWCS, or None (S43): called on a
    #: frame on which the tracker lost the field, to re-anchor the apertures.
    #: None (no ASTAP): the frames after a loss are flagged instead.
    solver: Callable[[np.ndarray], object] | None = None


@dataclass
class BatchResult:
    """Outcome of a batch run. ``error`` is empty on success.

    ``frames_done`` counts the frames measured; ``frames_skipped`` those that
    could not be read or dated. A ``cancelled`` run writes no CSV and its
    curves are partial (``ok`` still means "no error"). ``frames_resolved``
    counts the frames re-solved after the tracker lost the field (S43),
    ``frames_unanchored`` those measured without the field, ``frames_unverified``
    those whose lock rested on fewer than 3 anchors with no fresh solution (S58):
    their points are flagged suspect.
    """

    curves: dict[str, LightCurve] = field(default_factory=dict)
    frames_done: int = 0
    error: str = ""
    rotation_deg: float = 0.0  # accumulated field rotation vs the last solve
    shift_px: float = 0.0  # accumulated pointing drift vs the last solve
    frames_skipped: int = 0
    cancelled: bool = False
    out_dir: Path | None = None  # where the CSVs were written
    frames_resolved: int = 0
    frames_unanchored: int = 0
    #: S58: frames whose lock rested on 1-2 anchors with no solution of that frame or
    #: the one before within 2 px: their points are flagged suspect.
    frames_unverified: int = 0
    #: S69 (a): frames re-solved because the tracked rotation since the solution
    #: exceeded 2°.
    frames_rotation_solved: int = 0
    #: S69 (b): comparison and check star measurements more than 1 px from their
    #: aperture centre, left out of their frame's ensemble (their rows suspect).
    stars_off_centre: int = 0
    #: S69 (b): frames whose target got no point because every comparison was
    #: off-centre (no ensemble left).
    frames_no_target_point: int = 0
    #: S69 (a): re-solves for rotation that failed (no solution, or its apertures
    #: failed the lock check): the apertures followed the tracker.
    frames_rotation_unsolved: int = 0
    #: S67: frames with no detection (a target below SNR 3: its points; a target's zero
    #: point more than 1 mag from its median over the run: every point), flagged suspect.
    frames_no_detection: int = 0
    #: S66: frames whose airmass is their FITS header AIRMASS (the mount's), and frames
    #: whose header shows the Settings site more than 5° wrong (X3, a WARN).
    frames_header_airmass: int = 0
    frames_site_wrong: int = 0

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
        self._series_fwhm: float | None = None  # measured once, fixed all series (P7)
        # S43: the solve the apertures hang from (a re-solve replaces it), the
        # tracker's anchor stars, and whether the field is held since that solve.
        self._reference = request.wcs
        self._anchor_stars: list = []
        self._anchored = True
        self._frames_resolved = 0
        self._frames_unanchored = 0
        self._solver_failed_logged = False
        self._flagged: set[int] = set()  # id() of the points measured without the field
        # S58: the series index of the frame being measured and of the frame the
        # current reference was solved on (None: the request's solve, of no frame here).
        self._file_index = -1
        self._reference_index: int | None = None
        self._frames_unverified = 0
        self._frames_verify_solved = 0
        self._unverified_logged = False
        # S66: (file index, its header AIRMASS or None) once per frame; X1: frozen
        # header pointings; the site check's one WARN per run.
        self._frame_air: tuple[int, float | None] | None = None
        self._frozen = FrozenPointing()
        self._frozen_logged = False
        self._site_logged = False
        self._frames_header_airmass = 0
        self._frames_site_wrong = 0
        # S67: each measured frame's points, its targets' SNRs and zero points.
        self._frame_judging: list[tuple[int, str, list, list, list]] = []
        self._frames_no_detection = 0
        # S70: the frame's params (its own e-/ADU) for the tracker, lock and measure.
        self._params = request.params
        # S69 (a): re-solves for rotation, the rotation of the last failed attempt.
        self._frames_rotation_solved = 0
        self._rotation_attempted: float | None = None
        self._rotation_failed_logged = False
        self._frames_rotation_unsolved = 0
        # S69 (b): off-centre stars measured, and one WARN per run; frames whose target
        # got no point (every comparison off-centre).
        self._stars_off_centre = 0
        self._off_centre_logged = False
        self._frames_no_target_point = 0

    def cancel(self) -> None:
        """Ask the run to stop at the next frame boundary."""
        self._cancel = True

    def run(self) -> None:
        req = self._req
        curves: dict[str, LightCurve] = {}
        total = len(req.fits_paths)
        done = 0  # frames measured
        skipped = 0  # frames unreadable or without a usable DATE-OBS
        handled = 0  # progress: measured + skipped
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
                if self._process_frame(diag, fpath, done, curves):
                    done += 1
                else:
                    skipped += 1
                handled += 1
                self.progress.emit(handled, total)
            cancelled = self._cancel
            self._flag_no_detection(diag)  # S67, before the floors leave them out
            self._apply_systematic_floors(curves, self._flagged)
            if not cancelled:  # a partial run must not replace any file
                self._write_csvs(curves)
            result = BatchResult(
                curves=curves,
                frames_done=done,
                frames_skipped=skipped,
                cancelled=cancelled,
                out_dir=None if cancelled else req.out_dir,
                frames_resolved=self._frames_resolved,
                frames_unanchored=self._frames_unanchored,
                frames_unverified=self._frames_unverified,
                frames_rotation_solved=self._frames_rotation_solved,
                stars_off_centre=self._stars_off_centre,
                frames_no_target_point=self._frames_no_target_point,
                frames_rotation_unsolved=self._frames_rotation_unsolved,
                frames_no_detection=self._frames_no_detection,
                frames_header_airmass=self._frames_header_airmass,
                frames_site_wrong=self._frames_site_wrong,
            )
            multi_filter = len({lc.filter_name for lc in curves.values()}) > 1
            for key in sorted(self._check_keys):
                lc = curves.get(key)
                if lc is None:
                    continue
                mags = [
                    p.mag for p in lc.points if id(p) not in self._flagged and math.isfinite(p.mag)
                ]
                if len(mags) < 2:
                    continue
                mean = sum(mags) / len(mags)
                k_rms = (sum((m - mean) ** 2 for m in mags) / (len(mags) - 1)) ** 0.5
                star = lc.auid or lc.name
                # Per filter (S49); a one-filter re-run's record is unchanged.
                extra = {"filter": lc.filter_name} if multi_filter else {}
                label = f"{star} [{lc.filter_name}]" if multi_filter else star
                logger.info("Check star %s: RMS %.4f mag over %d frames", label, k_rms, len(mags))
                diag.record(
                    "event", what="check_rms", star=star, **extra, rms_mag=k_rms, n=len(mags)
                )
            if self._tracker is not None:
                result.rotation_deg = self._tracker.transform.rotation_deg
                result.shift_px = self._tracker.transform.shift_px
                if self._frames_unanchored or self._frames_resolved:
                    logger.warning(
                        "Batch tracking: the field was lost on %d frame(s): %d re-solved, "
                        "%d measured without it (points flagged suspect)",
                        self._frames_resolved + self._frames_unanchored,
                        self._frames_resolved,
                        self._frames_unanchored,
                    )
                elif not self._frames_unverified:
                    logger.info(
                        "Batch tracking: field rotated %.2f°, drifted %.1f px over %d frames",
                        result.rotation_deg,
                        result.shift_px,
                        done,
                    )
            if self._frames_rotation_solved:
                logger.info(
                    "Batch tracking: %d frame(s) re-solved after the field turned more than"
                    " 2° since the solution",
                    self._frames_rotation_solved,
                )
            if self._frames_rotation_unsolved:
                logger.warning(
                    "Batch tracking: the field turned more than 2° since the solution on"
                    " %d frame(s) that did not re-solve; their apertures followed the tracker",
                    self._frames_rotation_unsolved,
                )
            if self._stars_off_centre:
                logger.warning(
                    "Batch photometry: %d comparison/check measurement(s) more than 1 px"
                    " from their aperture centre were left out of their frame's ensemble"
                    " (their rows flagged suspect)",
                    self._stars_off_centre,
                )
            if self._frames_no_target_point:
                logger.warning(
                    "Batch photometry: %d frame(s) have no target point: every comparison"
                    " was more than 1 px from its aperture centre",
                    self._frames_no_target_point,
                )
            if self._frames_no_detection:
                logger.warning(
                    "Batch photometry: %d frame(s) show no detection (a target below SNR 3,"
                    " or a zero point more than 1 mag from the run's): their points are"
                    " flagged suspect and left out of sigma_syst",
                    self._frames_no_detection,
                )
            if self._frames_unverified or self._frames_verify_solved:
                logger.warning(
                    "Batch tracking: %d frame(s) steered by fewer than 3 anchor stars were"
                    " re-solved to verify their lock; %d had no verified lock (points"
                    " flagged suspect)",
                    self._frames_verify_solved,
                    self._frames_unverified,
                )
            diag.record(
                "event",
                what="batch_end",
                frames_done=done,
                rotation_deg=result.rotation_deg,
                shift_px=result.shift_px,
                frames_resolved=self._frames_resolved,
                frames_unanchored=self._frames_unanchored,
                frames_unverified=self._frames_unverified,
                frames_rotation_solved=self._frames_rotation_solved,
                stars_off_centre=self._stars_off_centre,
                frames_no_target_point=self._frames_no_target_point,
                frames_rotation_unsolved=self._frames_rotation_unsolved,
                frames_no_detection=self._frames_no_detection,
                frames_header_airmass=self._frames_header_airmass,
                frames_site_wrong=self._frames_site_wrong,
            )
            self.finished_batch.emit(result)
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Batch photometry crashed")
            diag.record("event", what="batch_crash", error=str(exc))
            self.finished_batch.emit(
                BatchResult(curves=curves, frames_done=done, frames_skipped=skipped, error=str(exc))
            )
        finally:
            diag.close()

    # ------------------------------------------------------------------

    def _process_frame(self, diag, fpath: Path, frame_no: int, curves) -> bool:
        """Measure one frame: tracker update, diagnostics records, points.

        Returns False, with no point, for a frame that cannot be read or has
        no usable DATE-OBS: an undated point would carry JD 0 to the AAVSO.
        """
        self._file_index += 1  # S58: "this frame or the previous one"
        arr, jd, egain = self._read_frame(fpath, self._req.egain_table)
        if arr is None:
            logger.warning("%s: unreadable — skipped", fpath.name)
            diag.record("event", what="frame_skipped", file=fpath.name, reason="unreadable")
            return False
        if jd is None:
            logger.warning("%s: no usable DATE-OBS — skipped (a point needs a time)", fpath.name)
            diag.record("event", what="frame_skipped", file=fpath.name, reason="no DATE-OBS")
            return False
        # S70: the frame's own e-/ADU in every SNR of the frame: the tracker's anchors,
        # the lock checks and the measurement (it was the measurement's only).
        params = self._req.params
        if egain is not None and egain != params.egain:
            params = replace(params, egain=egain)
        self._params = params
        green = green_plane(arr)
        wcs = self._wcs_for_frame(green, fpath.name)
        if self._series_fwhm is None:
            self._series_fwhm = self._measure_series_fwhm(arr, diag)
        diag.record("frame", frame=frame_no, file=fpath.name, jd_utc=jd, fwhm=self._series_fwhm)
        wcs, anchored = self._anchor(green, wcs, diag, frame_no, fpath.name)
        if anchored:
            wcs = self._resolve_rotation(green, wcs, diag, frame_no, fpath.name)
        offsets = self._centring(green, wcs)
        if anchored:
            wcs, anchored, offsets = self._verify(green, wcs, diag, frame_no, fpath.name, offsets)
        excluded = off_centre(offsets)
        if self._tracker is not None:
            diag.record(
                "tracking",
                frame=frame_no,
                anchors=self._tracker.anchors_used,
                anchors_rejected=self._tracker.anchors_rejected or None,
                residual_px=self._tracker.residual_px,
                rotation_deg=self._tracker.transform.rotation_deg,
                shift_px=self._tracker.transform.shift_px,
                frames_lost=self._tracker.frames_lost,
                anchored=anchored,
                off_centre=len(excluded) or None,
            )
        if excluded:
            self._stars_off_centre += len(excluded)
            if not self._off_centre_logged:
                self._off_centre_logged = True  # once per run; the recorder has each
                logger.warning(
                    "%s: %d comparison/check star(s) more than 1 px from their aperture"
                    " centre — left out of the frame's ensemble, their rows flagged suspect",
                    fpath.name,
                    len(excluded),
                )

        def on_star(s, phot, x, y):
            offset = offsets.get(s.key())
            diag.star(
                frame_no,
                s,
                phot,
                x,
                y,
                centroid_offset_px=offset if offset is not None and math.isfinite(offset) else None,
                off_centre=True if s.key() in excluded else None,
            )

        results = measure_frame(
            green,
            wcs,
            self._req.target_set,
            params,
            fwhm=self._series_fwhm,
            on_star=on_star,
            exclude=excluded,
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
        token = filter_token(self._read_filter(fpath))  # one curve per (star, filter): S49
        points = self._emit_points(
            results, jd, curves, flagged=not anchored, token=token, off_centre=excluded
        )
        self._judge_later(frame_no, fpath.name, results, points, excluded)
        return True

    def _judge_later(self, frame_no: int, fname: str, results, points, excluded) -> None:
        """Keep what S67's rule judges at the end of the run (the zero points' median
        is the run's), and count a target left without a point by S69 (b). ``points``:
        ``(role, identity, point)`` of the frame's points."""
        targets = [res for res in results if res.star.role == ROLE_TARGET]
        snrs = [
            (res.star.auid or res.star.display_name, res.phot.snr)
            for res in targets
            if res.phot is not None
        ]
        zps = [
            (res.star.auid or res.star.display_name, res.diff.zero_point)
            for res in targets
            if res.diff is not None
        ]
        self._frame_judging.append((frame_no, fname, points, snrs, zps))
        if excluded and any(
            not (res.diff is not None and res.diff.mag is not None)
            and not (res.relative is not None and res.relative.flux_ratio is not None)
            for res in targets
        ):
            self._frames_no_target_point += 1

    def _flag_no_detection(self, diag) -> None:
        """S67 (S35's rule, as Review applies it to a live run's recorder): a target's
        points on a frame where it was measured below SNR 3, and every point of a frame
        where a target's zero point is more than 1 mag from its median over the run,
        are flagged suspect (the AAVSO export leaves them out) and do not set the run's
        ``sigma_syst``. A faint target does not flag a second, bright one."""
        judged = no_detection_flags((snrs, zps) for *_head, snrs, zps in self._frame_judging)
        for (frame_no, fname, points, _snrs, _zps), (low, outlier) in zip(
            self._frame_judging, judged
        ):
            if not (low or outlier):
                continue
            self._frames_no_detection += 1
            for role, identity, point in points:
                if not (outlier or (role == ROLE_TARGET and identity in low)):
                    continue
                point.suspect = True
                point.no_detection = True
                self._flagged.add(id(point))
            diag.record(
                "event",
                frame=frame_no,
                what="no_detection",
                file=fname,
                low_snr=sorted(low) or None,
                zp_outlier=outlier or None,
            )

    def _lock_holds(self, green, wcs) -> bool:
        """The tracker found anchors and half of them show a star where it put them."""
        if self._tracker is None or not self._tracker.anchors_used or not self._anchor_stars:
            return False
        seen = anchors_seen(green, wcs, self._anchor_stars, self._params, min_snr=_LOCK_MIN_SNR)
        return seen >= max(1, math.ceil(len(self._anchor_stars) / 2))

    def _centring(self, green, wcs) -> dict[str, float]:
        """S69 (b): each comparison and check star's centroid offset from its aperture
        centre on this frame through ``wcs`` (stars seen at SNR >= 5 only)."""
        tset = self._req.target_set
        stars = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        return centring_offsets(
            green, wcs, stars, self._params, fwhm=self._series_fwhm, neighbours=list(tset.stars)
        )

    def _adopt(self, solution, green) -> TrackedWCS:
        """A frame's own solution becomes the reference: the tracker is rebuilt on it."""
        self._reference = solution
        self._reference_index = self._file_index
        self._rotation_attempted = None
        self._tracker = self._build_tracker(green)
        self._tracker.update(green)
        return TrackedWCS(self._reference, self._tracker)

    def _resolve_rotation(self, green, wcs, diag, frame_no: int, fname: str):
        """S69 (a): re-solve the frame once the tracked rotation since the solution
        exceeds 2° (``tracking.RESOLVE_ROTATION_DEG``).

        The rigid fit carries one solution's geometry across the field; the frame's
        own solution resets it. A solve that fails, or whose apertures fail the S43
        lock check, keeps the tracked solution, and the next attempt waits for 2° more
        rotation: a failing or slow solver costs one solve per 2°, never one per frame.
        """
        if self._tracker is None or self._req.solver is None:
            return wcs
        rotation = self._tracker.transform.rotation_deg
        if not rotation_resolve_due(rotation, self._rotation_attempted):
            return wcs
        solution = self._solve(green, fname, flags=False)
        if solution is not None:
            kept = (self._reference, self._reference_index, self._tracker, self._anchor_stars)
            tracked = self._adopt(solution, green)
            if self._lock_holds(green, tracked):
                self._frames_rotation_solved += 1
                diag.record(
                    "event", frame=frame_no, what="re_solved_rotation", rotation_deg=rotation
                )
                return tracked
            self._reference, self._reference_index, self._tracker, self._anchor_stars = kept
        self._rotation_attempted = rotation
        self._frames_rotation_unsolved += 1
        diag.record("event", frame=frame_no, what="rotation_not_re_solved", rotation_deg=rotation)
        if not self._rotation_failed_logged:
            self._rotation_failed_logged = True
            logger.warning(
                "%s: the field turned %.1f° since the solution and the frame did not re-solve;"
                " the apertures follow the tracker (next attempt after 2° more)",
                fname,
                rotation,
            )
        return wcs

    def _anchor(self, green, wcs, diag, frame_no: int, fname: str):
        """Check the tracker's lock; re-solve and re-anchor the frame when it is lost (S43).

        Returns ``(wcs, anchored)``. Once the field is lost, the points stay
        flagged until a solve re-anchors the apertures: a tracker that lost the
        field keeps a stale transform, and a window that finds a star again may
        have found another one.
        """
        if self._tracker is None:  # tracking off: the reference solve, as chosen
            return wcs, True
        if self._anchored and self._lock_holds(green, wcs):
            return wcs, True
        if self._anchored:
            self._anchored = False
            logger.warning(
                "%s: the field moved off the apertures (a pointing jump, or clouds)", fname
            )
            diag.record(
                "event", frame=frame_no, what="field_lost", anchors=self._tracker.anchors_used
            )
        solution = self._solve(green, fname)
        if solution is not None:
            tracked = self._adopt(solution, green)
            if self._lock_holds(green, tracked):
                self._anchored = True
                self._frames_resolved += 1
                logger.info("%s: re-solved, apertures re-anchored on the field", fname)
                diag.record("event", frame=frame_no, what="re_anchored")
                return tracked, True
            wcs = tracked
        self._frames_unanchored += 1
        diag.record(
            "event",
            frame=frame_no,
            what="unanchored",
            reason="no solver" if self._req.solver is None else "not re-solved",
        )
        return wcs, False

    def _fresh(self, tracked) -> bool:
        """S58: the frame is measured through a solution of this frame or the previous
        one, and the tracker moved no aperture of the set ``_LOCK_FRESH_MAX_SHIFT_PX``
        or more from where that solution puts it (the live path's S56 rule)."""
        if self._reference_index is None or self._file_index - self._reference_index > 1:
            return False
        shift = 0.0
        for star in self._req.target_set.stars:
            x0, y0 = self._reference.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            x1, y1 = tracked.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            d = math.hypot(float(x1) - float(x0), float(y1) - float(y0))
            if not math.isfinite(d):
                return False
            shift = max(shift, d)
        return shift < _LOCK_FRESH_MAX_SHIFT_PX

    def _centred_anchors(self, offsets: dict[str, float]) -> int:
        """S69 (b): the tracker's anchors less those more than 1 px off their aperture
        centre on this frame (an anchor too faint to test counts, as before) and the
        one its fit rejected (it verified nothing)."""
        bad = off_centre(offsets)
        rejected = self._tracker.rejected_anchor if self._tracker is not None else None
        return sum(
            1
            for index, star in enumerate(self._anchor_stars)
            if star.key() not in bad and index != rejected
        )

    def _verify(self, green, wcs, diag, frame_no: int, fname: str, offsets: dict[str, float]):
        """S58: S56's rule for a lock on fewer than 3 anchors, in the re-run.

        With 1 or 2 anchors the S43 check is met by the very anchor that moved the
        apertures: a neighbour or noise passes. Such a frame is verified only near
        a fresh solution (:meth:`_fresh`); otherwise it is re-solved now (the live
        path makes a re-solve due) and verified on its own solution, else its
        points are flagged suspect. S69 (b): the anchors counted are those centred
        within 1 px of their aperture (``offsets``), so a lock whose off-centre
        anchors leave fewer than 3 is treated the same way. Returns ``(wcs,
        verified, offsets)``, the offsets of the frame's final solution.
        """
        n = self._centred_anchors(offsets)
        if (
            self._tracker is None
            or not self._anchor_stars
            or n >= _LOCK_VERIFY_MIN_ANCHORS
            or self._fresh(wcs)
        ):
            self._unverified_logged = False
            return wcs, True, offsets
        solution = self._solve(green, fname)
        if solution is not None:
            tracked = self._adopt(solution, green)
            offsets = self._centring(green, tracked)
            n = self._centred_anchors(offsets)
            if self._lock_holds(green, tracked) and (
                n >= _LOCK_VERIFY_MIN_ANCHORS or self._fresh(tracked)
            ):
                self._frames_verify_solved += 1
                self._unverified_logged = False
                diag.record("event", frame=frame_no, what="lock_verified_by_solve", anchors=n)
                return tracked, True, offsets
            wcs = tracked
        self._frames_unverified += 1
        if not self._unverified_logged:
            self._unverified_logged = True  # once per episode
            logger.warning(
                "%s: only %d anchor star(s) steer the apertures — the lock cannot be"
                " verified; points are flagged suspect while fewer than 3 anchor stars steer"
                " the apertures (except within 2 px of a solution of this frame or the"
                " previous one)",
                fname,
                n,
            )
        diag.record("event", frame=frame_no, what="lock_unverified", anchors=n)
        return wcs, False, offsets

    def _solve(self, green, fname: str, *, flags: bool = True):
        """The frame's own solution from the request's solver, or None.

        ``flags``: a failure flags the frame's points (S43, S58), and the first such
        failure of the run says so; a re-solve for rotation (S69 a) flags nothing and
        has its own message."""
        if self._req.solver is None:
            return None
        try:
            solution = self._req.solver(green)
        except Exception as exc:  # a solver failure flags the frame, never ends the run
            logger.warning("%s: re-solve failed: %s", fname, exc)
            return None
        if solution is None and flags and not self._solver_failed_logged:
            self._solver_failed_logged = True
            logger.warning("%s: the frame did not solve — its points are flagged", fname)
        return solution

    def _measure_series_fwhm(self, raw, diag) -> float | None:
        """Field FWHM from the first readable frame — one aperture per series (P7).

        Time-series practice: a single radius for the whole run, sized from
        the measured seeing, instead of the aperture_min_px floor (saved subs
        carry no FWHM header). None when no stars are detected, which makes the
        aperture fall back to ``DEFAULT_FWHM`` — wider than the floor.
        """
        from argos.core.imaging.metrics import detect_stars

        try:
            fwhm = detect_stars(raw).mean_fwhm
        except Exception:  # pragma: no cover - defensive: bad first frame
            fwhm = None
        r_ap = self._req.params.aperture_px(fwhm)
        logger.info("Series FWHM %.2f px → aperture %.1f px", fwhm or -1, r_ap)
        diag.record("event", what="aperture", fwhm=fwhm, r_ap=r_ap)
        return fwhm

    def _wcs_for_frame(self, green, fname: str):
        """Reference WCS, rotation/drift-corrected by the tracker when it locks.

        The tracker is built lazily on the first frame (it needs the frame
        shape for its pivot) and keeps its last good transform on a frame with
        no usable anchor (clouds), so a later frame can re-acquire.
        """
        if not self._req.params.track_apertures:
            return self._req.wcs
        if self._tracker is None:
            self._tracker = self._build_tracker(green)
        self._tracker.update(green)
        if not self._tracker.anchors_used:
            logger.warning("%s: no anchor star found — apertures unguided", fname)
        return TrackedWCS(self._reference, self._tracker)

    def _build_tracker(self, green) -> ApertureTracker:
        """Anchor the tracker on the stable stars of the set (comps + checks).

        A target's *position* is as stable, but a variable near minimum makes a
        poor centroid — only fall back to targets when there is nothing else.
        """
        tset = self._req.target_set
        wcs = self._reference
        candidates = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        # S70: the anchors' SNR >= 10 with the frame's own e-/ADU (self._params).
        # S69: a candidate beside a brighter star of the set (targets included) is none.
        anchors = select_tracking_anchors(
            green, wcs, candidates, self._params, neighbours=list(tset.stars)
        )
        if not anchors:
            # Any star of the set seen where the solution places it (S35); with
            # none seen, the lock check fails and the frame is re-solved (S43).
            anchors = select_tracking_anchors(
                green, wcs, list(tset.stars), self._params, min_snr=_LOCK_MIN_SNR
            ) or list(tset.stars)
        self._anchor_stars = anchors
        xy = [wcs.world_to_pixel_deg(s.ra_deg, s.dec_deg) for s in anchors]
        h, w = green.shape
        search_r = max(8.0, 2.0 * self._req.params.aperture_px(None))
        return ApertureTracker(
            [(float(x), float(y)) for x, y in xy],
            frame_center=(w / 2.0, h / 2.0),
            search_r=search_r,
        )

    def _emit_points(
        self,
        results,
        jd: float | None,
        curves: dict[str, LightCurve],
        *,
        flagged: bool = False,
        token: str = "clear",
        off_centre: frozenset[str] = frozenset(),
    ) -> list[LcPoint]:
        """Convert one frame's measurements into curve points + point signals.

        ``results`` carry targets, check stars (P2) and leave-one-out
        comparison vetting curves; checks flow into their own curves/CSVs and
        their keys are remembered for the K-RMS summary (comps are not). Each
        (star, filter) has its own curve (S49): ``token`` is the frame's filter.
        ``off_centre`` (S69): stars measured more than 1 px from their centroid,
        whose own rows are flagged suspect like a frame measured without the field.
        Returns the points made, ``(role, identity, point)`` (S67 may flag them at the
        end of the run).
        """
        made: list[tuple[str, str, LcPoint]] = []
        for res in results:
            star_flagged = flagged or bool(off_centre and res.star.key() in off_centre)
            # Keep a point when *either* product exists. Requiring the flux
            # ratio discarded good differential magnitudes whenever every
            # comparison was flagged suspect (the ratio path rejects those,
            # the magnitude path does not).
            has_mag = res.diff is not None and res.diff.mag is not None
            has_ratio = res.relative is not None and res.relative.flux_ratio is not None
            if not (has_mag or has_ratio):
                continue
            key = curve_key(res.star, token)
            if res.star.role == ROLE_CHECK:
                self._check_keys.add(key)  # its K-RMS per filter
            bjd = self._bjd(jd, res.star)
            pt = LcPoint(
                jd_utc=jd,
                mag=res.diff.mag if res.diff and res.diff.mag is not None else float("nan"),
                mag_err=(
                    res.diff.mag_err if res.diff and res.diff.mag_err is not None else float("nan")
                ),
                bjd_tdb=bjd,
                airmass=self._airmass(jd, res.star),
                fwhm=self._series_fwhm,
                sky_adu=res.phot.sky_adu if res.phot else None,
                comps_used=res.diff.comps_used if res.diff else 0,
                relative_comps_used=res.relative.comps_used if res.relative else 0,
                saturated=bool(res.phot and res.phot.saturated),
                # S43: measured without the field (the tracker lost it, no re-solve);
                # S69: the star more than 1 px off its aperture centre; S71: the
                # comparison carrying the zero point disagrees with the others.
                suspect=bool(res.phot and res.phot.suspect)
                or star_flagged
                or bool(getattr(res.diff, "suspect", False)),
                formal_mag_err=(
                    res.diff.formal_mag_err or res.diff.mag_err
                    if res.diff and res.diff.mag_err is not None
                    else None
                ),
                relative_flux=res.relative.flux_ratio if res.relative else None,
                relative_flux_err=res.relative.flux_ratio_err if res.relative else None,
            )
            lc = curves.setdefault(
                key,
                LightCurve(
                    auid=res.star.auid or "",
                    name=res.star.display_name,
                    role=res.star.role,
                    filter_name=token,
                ),
            )
            lc.append(pt)
            made.append((res.star.role, res.star.auid or res.star.display_name, pt))
            if star_flagged:
                self._flagged.add(id(pt))
            multi = any(c.filter_name != token for c in curves.values())
            self.point.emit(
                PhotometryPoint(
                    key=key,
                    name=series_label(lc, multi),
                    jd=pt.jd_utc,
                    mag=pt.mag,
                    mag_err=pt.mag_err,
                    saturated=pt.saturated,
                    role=res.star.role,
                    relative_flux=pt.relative_flux,
                    relative_flux_err=pt.relative_flux_err,
                )
            )
        return made

    @staticmethod
    def _apply_systematic_floors(
        curves: dict[str, LightCurve], flagged: set[int] = frozenset()
    ) -> None:
        """Apply the shared star_var_script uncertainty model after a batch.

        Points measured without the field (``flagged``, S43) do not set the floor.
        """
        for curve in curves.values():
            floor = estimate_systematic_floor(
                [
                    (point.jd_utc, point.mag, point.formal_mag_err or point.mag_err)
                    for point in curve.points
                    if id(point) not in flagged
                    and math.isfinite(point.mag)
                    and math.isfinite(point.formal_mag_err or point.mag_err)
                ]
            )
            if floor is None:
                continue
            for point in curve.points:
                if not math.isfinite(point.mag):
                    continue
                formal = point.formal_mag_err if point.formal_mag_err is not None else point.mag_err
                point.mag_err = apply_systematic_floor(formal, floor)
                point.sigma_syst = floor.sigma_systematic

    def _bjd(self, jd: float | None, star) -> float | None:
        """BJD_TDB for a star at this frame's JD, or None without site/time."""
        lat, lon, elev = self._req.site
        if jd is None or lat is None or lon is None:
            return None
        return bjd_tdb(jd, star.ra_deg, star.dec_deg, float(lat), float(lon), float(elev))

    def _airmass(self, jd: float | None, star) -> float | None:
        """Per-star airmass at this frame's JD (P4), or None without site/time.

        S66: an Argos frame's header ``AIRMASS`` (the mount's, within 0.0004 of
        astropy whatever the Settings site) when it has one and its pointing is not
        frozen (:meth:`_frame_header_airmass`); otherwise :func:`airmass_at` for the
        Settings site, which the live path uses too, so the two never drift apart.
        """
        header = self._frame_header_airmass()
        if header is not None:
            return header
        lat, lon, _elev = self._req.site
        if jd is None or lat is None or lon is None:
            return None
        return airmass_at(jd, star.ra_deg, star.dec_deg, float(lat), float(lon))

    def _frame_header_airmass(self) -> float | None:
        """S66: the header ``AIRMASS`` of the frame being measured (read once per
        frame), or None: not written by Argos, no ``AIRMASS``, or a frozen pointing
        (X1: RA, DEC, ALTITUDE, AZIMUTH and AIRMASS those of a frame a minute or more
        before; its AIRMASS is a lost mount's last poll). The frame's site check (X3:
        the mount's direction more than 5° from the one computed for the Settings site
        in use) only warns, once per run: the airmass no longer depends on the site."""
        index = self._file_index
        if self._frame_air is not None and self._frame_air[0] == index:
            return self._frame_air[1]
        paths = self._req.fits_paths
        pointing = read_frame_pointing(paths[index]) if 0 <= index < len(paths) else None
        airmass = None
        if self._frozen.frozen(pointing):
            if not self._frozen_logged:
                self._frozen_logged = True
                logger.warning(
                    "Batch photometry: %s keeps the pointing of a frame a minute or more"
                    " before it (a lost mount's last poll): its airmass is computed for the"
                    " site in Settings",
                    paths[index].name,
                )
        elif pointing is not None and pointing.argos:
            airmass = pointing.airmass
            lat, lon, _elev = self._req.site
            offset = (
                site_offset_deg(pointing, float(lat), float(lon))
                if lat is not None and lon is not None
                else None
            )
            if offset is not None and offset > SITE_CHECK_TOLERANCE_DEG:
                self._frames_site_wrong += 1
                if not self._site_logged:
                    self._site_logged = True
                    logger.warning(
                        "Batch photometry: the site in Settings is not where the telescope"
                        " was (%s: the mount's direction is %.1f° from the one computed for"
                        " that site). Fix the site in Settings › Observer & site; the airmass"
                        " is each frame's FITS header AIRMASS, from the mount.",
                        paths[index].name,
                        offset,
                    )
        if airmass is not None:
            self._frames_header_airmass += 1
        self._frame_air = (index, airmass)
        return airmass

    @staticmethod
    def _read_frame(
        fpath: Path, egain_table=None
    ) -> tuple[np.ndarray | None, float | None, float | None]:
        """Read a FITS frame → (float32 array, exposure-midpoint JD or None, e-/ADU or None).

        DATE-OBS is the exposure *start*; half of EXPTIME is added (P5) so a
        30 s sub doesn't carry a 15 s systematic timing bias. Without EXPTIME
        the start JD is kept (and the bias with it — a WARN says so). The
        e-/ADU is the frame's own (:func:`frame_egain`), None when unknown.
        """
        from astropy.io import fits

        try:
            with fits.open(fpath) as hdul:
                data = hdul[0].data
                header = hdul[0].header
        except Exception:
            return None, None, None
        if data is None:
            return None, None, None
        arr = np.nan_to_num(np.asarray(data, dtype=np.float32))
        jd = None
        date_str = str(header.get("DATE-OBS", "") or "")
        if "T" in date_str:  # a date without a time is not an epoch (not midnight)
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if dt.tzinfo is not None:  # julian_date expects UTC fields
                    dt = dt.astimezone(timezone.utc)
                jd = julian_date(dt)
            except ValueError:
                jd = None
        if jd is not None:
            try:
                jd += float(header["EXPTIME"]) / 2.0 / 86400.0
            except (KeyError, TypeError, ValueError):
                logger.warning("%s: no EXPTIME — JD is exposure start, not midpoint", fpath.name)
        return arr, jd, frame_egain(header, egain_table)

    @staticmethod
    def _read_filter(fpath: Path) -> str:
        """The frame's ``FILTER`` card ("" when absent or unreadable), S49."""
        from astropy.io import fits

        try:
            return str(fits.getheader(fpath).get("FILTER", "") or "").strip()
        except Exception:
            return ""

    def _write_csvs(self, curves: dict[str, LightCurve]) -> None:
        """Write each curve as ``{role}_{object}_{filter}_{star}.csv`` beside ``targets.json``.

        The engine's naming (S49: one file per star and filter), so Review and
        "Open curve CSV…" recover each curve's role and star from the file
        name and the saved target set.
        """
        for lc in curves.values():
            tag = lc.auid or lc.name or "photometry"
            name = run_curve_csv_name(
                lc.role or "target", self._req.object_name, lc.filter_name or "clear", tag
            )
            try:
                lc.to_csv(self._req.out_dir / name)
            except OSError as exc:
                logger.warning("batch photometry.csv: %s", exc)
        if not curves:
            return
        try:
            self._req.target_set.save(self._req.out_dir / "targets.json")
        except OSError as exc:
            logger.warning("batch targets.json: %s", exc)
