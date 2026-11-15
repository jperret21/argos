"""Re-run photometry over a session's saved frames (row A76 of ``web/spec/README.md`` §4.3).

A Qt-free port of the fixed ``PhotometryBatchWorker``
(``argos/workers/photometry_batch_worker.py``, release 0.5.0 with S12, S13,
S41, S43, S49, S58, S62 and S63), whose ``QThread`` cannot be imported here
(``tests/server/test_no_qt.py``). :class:`BatchRun` is the worker's ``run``
line for line: the signals become callbacks, the cancel flag the job's
event, and the S43/S58 re-solves go through the cancellable ASTAP runner
(:func:`argos.server.field_solve.solve_green`, which kills ASTAP on a cancel;
Qt's ``solve_array`` could not be interrupted). The measurement is the
unchanged core: ``measure_frame``, ``ApertureTracker``, ``TrackedWCS``,
``anchors_seen``, ``select_tracking_anchors``, ``estimate_systematic_floor``,
``airmass_at``, ``bjd_tdb``, ``LightCurve.to_csv``.

What the web adds around it (D2, Q-R1): the reference is a plate solve of a
session frame (or the live solution), the frames are the session's, and the
output is always a **new** folder inside the session, never overwritten.
"""

from __future__ import annotations

import logging
import math
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, ROLE_TARGET, TargetSet
from argos.core.config import observing_site
from argos.core.imaging.fits_writer import filter_token
from argos.core.imaging.green import green_plane
from argos.core.photometry.airmass import airmass_at, bjd_tdb, julian_date
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
    select_tracking_anchors,
)
from argos.core.photometry.uncertainty import apply_systematic_floor, estimate_systematic_floor
from argos.server.errors import ApiError
from argos.server.exports import plural
from argos.server.jobs import JobCancelled, JobContext
from argos.server.photometry import SessionDiagnostics

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: FITS file suffixes a re-run accepts (any case). Argos itself writes ``.fit``.
_FITS_SUFFIXES = (".fit", ".fits", ".fts")
#: IMAGETYP words that mark a calibration frame, never measured as a light.
_CALIBRATION_WORDS = ("dark", "flat", "bias", "offset", "zero")
#: S43: an anchor is seen when its aperture at the tracked position has this SNR.
_LOCK_MIN_SNR = 5.0
#: S58 (S56's rule in the re-run).
_LOCK_VERIFY_MIN_ANCHORS = 3
_LOCK_FRESH_MAX_SHIFT_PX = 2.0


# ---------------------------------------------------------------------------
# Frames and the output folder
# ---------------------------------------------------------------------------


def object_key(name: str | None) -> str:
    """An object name compared without case, spaces or underscores (S62)."""
    return "".join(c for c in str(name or "").lower() if c.isalnum())


@dataclass
class FrameSelection:
    """The frames a re-run measures, and what it left out."""

    paths: list[Path]
    calibration: int = 0
    other_object: int = 0
    #: S63: FITS of a session folder outside its lights/ (another program's), links
    #: to a frame already listed.
    outside_lights: int = 0
    duplicates: int = 0


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


def discover_light_frames(folder: Path, object_name: str | None = None) -> FrameSelection:
    """``discover_light_frames`` (0.5.0 with S62, S63): the light frames of the object.

    ``.fit``/``.fits``/``.fts`` files (any case) in the folder itself, or in its
    subfolders when it has none (a session root holds lights/). Frames whose
    ``IMAGETYP`` names a calibration type are left out, and (S62) frames whose
    ``OBJECT`` names another object than ``object_name``; a frame without
    either card is kept. In the subfolder search an Argos session folder's
    frames are its ``lights/`` only, and a link to a frame already listed is
    that frame (S63: Siril's ``process/`` holds links to the lights and
    registered copies). Ordered by ``DATE-OBS``, undated frames last, by name.
    """
    from astropy.io import fits

    folder = Path(folder)
    wanted = object_key(object_name)

    def fits_files(paths) -> list[Path]:
        return [p for p in paths if p.is_file() and p.suffix.lower() in _FITS_SUFFIXES]

    found = fits_files(sorted(folder.glob("*")))
    outside = 0
    if not found:
        below = fits_files(sorted(folder.rglob("*")))
        found = [p for p in below if _session_lights_only(p, folder)]
        outside = len(below) - len(found)
    candidates: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        real = path.resolve()
        if real not in seen:  # S63: a link to a frame already listed is that frame
            seen.add(real)
            candidates.append(path)
    duplicates = len(found) - len(candidates)
    dated: list[tuple[datetime, Path]] = []
    undated: list[Path] = []
    calibration = other = 0
    for path in candidates:
        try:
            header = fits.getheader(path)
        except Exception:  # unreadable: the run reports it as a skipped frame
            undated.append(path)
            continue
        imagetyp = str(header.get("IMAGETYP", "") or "").lower()
        if any(word in imagetyp for word in _CALIBRATION_WORDS):
            calibration += 1
            continue
        frame_object = object_key(header.get("OBJECT"))
        if wanted and frame_object and frame_object != wanted:
            other += 1
            continue
        try:
            start = datetime.fromisoformat(str(header.get("DATE-OBS") or "").replace("Z", "+00:00"))
        except ValueError:
            undated.append(path)
            continue
        if start.tzinfo is not None:  # FITS dates are UTC; compare naive UTC
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        dated.append((start, path))
    dated.sort(key=lambda item: (item[0], item[1].name))
    paths = [path for _start, path in dated] + sorted(undated, key=lambda p: p.name)
    return FrameSelection(paths, calibration, other, outside, duplicates)


def rerun_output_dir(frames_folder: Path, now: datetime) -> Path:
    """``rerun_output_dir``: ``<session>/photometry_rerun_<UTC>``, never an existing folder.

    The session root is the folder holding ``session.json`` (``frames_folder``
    or its parent), else ``frames_folder`` itself. A folder of that second that
    exists already gets ``-2``, ``-3``… (the web can start two re-runs of two
    sessions in one second; Qt ran one at a time).
    """
    folder = Path(frames_folder)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = folder
    for candidate in (folder, folder.parent):
        if (candidate / "session.json").is_file():
            root = candidate
            break
    count = 1
    while True:
        name = f"photometry_rerun_{stamp}" if count == 1 else f"photometry_rerun_{stamp}-{count}"
        path = root / name
        if not path.exists():
            return path
        count += 1


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


@dataclass
class BatchRequest:
    """``BatchRequest``: inputs for one re-run."""

    fits_paths: list[Path]
    wcs: object  # the reference solve (green px)
    target_set: TargetSet
    params: PhotometryParams
    out_dir: Path
    object_name: str = "untitled"
    site: tuple[float | None, float | None, float] = (None, None, 0.0)  # lat, lon, elev
    diagnostics: bool = True
    egain_table: dict = field(default_factory=dict)
    solver: Callable[[np.ndarray], object] | None = None


@dataclass
class BatchResult:
    """``BatchResult``."""

    curves: dict[str, LightCurve] = field(default_factory=dict)
    frames_done: int = 0
    error: str = ""
    rotation_deg: float = 0.0
    shift_px: float = 0.0
    frames_skipped: int = 0
    cancelled: bool = False
    out_dir: Path | None = None
    frames_resolved: int = 0
    frames_unanchored: int = 0
    frames_unverified: int = 0
    #: Not in Qt's record (logged there): the check stars' RMS per curve key.
    check_rms: dict[str, tuple[float, int]] = field(default_factory=dict)
    series_fwhm: float | None = None

    @property
    def ok(self) -> bool:
        return not self.error


class BatchRun:
    """``PhotometryBatchWorker.run`` without Qt: call :meth:`run` on a worker thread.

    ``progress(done, total, name)`` replaces the ``progress`` signal (``name``:
    the frame just handled); ``cancel`` is checked at every frame boundary.
    """

    def __init__(
        self,
        request: BatchRequest,
        *,
        cancel: threading.Event | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        self._req = request
        self._cancel_event = cancel or threading.Event()
        self._progress_cb = progress
        self._tracker: ApertureTracker | None = None
        self._check_keys: set[str] = set()
        self._series_fwhm: float | None = None
        self._reference = request.wcs
        self._anchor_stars: list = []
        self._anchored = True
        self._frames_resolved = 0
        self._frames_unanchored = 0
        self._solver_failed_logged = False
        self._flagged: set[int] = set()
        self._file_index = -1
        self._reference_index: int | None = None
        self._frames_unverified = 0
        self._frames_verify_solved = 0
        self._unverified_logged = False

    @property
    def _cancel(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> BatchResult:
        req = self._req
        curves: dict[str, LightCurve] = {}
        total = len(req.fits_paths)
        done = 0
        skipped = 0
        handled = 0
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
                if self._progress_cb is not None:
                    self._progress_cb(handled, total, fpath.name)
            cancelled = self._cancel
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
                series_fwhm=self._series_fwhm,
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
                extra = {"filter": lc.filter_name} if multi_filter else {}
                label = f"{star} [{lc.filter_name}]" if multi_filter else star
                logger.info("Check star %s: RMS %.4f mag over %d frames", label, k_rms, len(mags))
                diag.record(
                    "event", what="check_rms", star=star, **extra, rms_mag=k_rms, n=len(mags)
                )
                result.check_rms[key] = (k_rms, len(mags))
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
            )
            return result
        except JobCancelled:
            raise  # a cancel inside a re-solve (ASTAP killed): the job ends cancelled
        except Exception as exc:
            logger.exception("Batch photometry crashed")
            diag.record("event", what="batch_crash", error=str(exc))
            return BatchResult(
                curves=curves, frames_done=done, frames_skipped=skipped, error=str(exc)
            )
        finally:
            diag.close()

    # ------------------------------------------------------------------

    def _process_frame(self, diag, fpath: Path, frame_no: int, curves) -> bool:
        self._file_index += 1
        arr, jd, egain, filter_name = self._read_frame(fpath, self._req.egain_table)
        if arr is None:
            logger.warning("%s: unreadable — skipped", fpath.name)
            diag.record("event", what="frame_skipped", file=fpath.name, reason="unreadable")
            return False
        if jd is None:
            logger.warning("%s: no usable DATE-OBS — skipped (a point needs a time)", fpath.name)
            diag.record("event", what="frame_skipped", file=fpath.name, reason="no DATE-OBS")
            return False
        green = green_plane(arr)
        wcs = self._wcs_for_frame(green, fpath.name)
        if self._series_fwhm is None:
            self._series_fwhm = self._measure_series_fwhm(arr, diag)
        diag.record("frame", frame=frame_no, file=fpath.name, jd_utc=jd, fwhm=self._series_fwhm)
        wcs, anchored = self._anchor(green, wcs, diag, frame_no, fpath.name)
        if anchored:
            wcs, anchored = self._verify(green, wcs, diag, frame_no, fpath.name)
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
            )
        params = self._req.params
        if egain is not None and egain != params.egain:
            params = replace(params, egain=egain)
        results = measure_frame(
            green,
            wcs,
            self._req.target_set,
            params,
            fwhm=self._series_fwhm,
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
        token = filter_token(filter_name)  # one curve per (star, filter): S49
        self._emit_points(results, jd, curves, flagged=not anchored, token=token)
        return True

    def _lock_holds(self, green, wcs) -> bool:
        if self._tracker is None or not self._tracker.anchors_used or not self._anchor_stars:
            return False
        seen = anchors_seen(green, wcs, self._anchor_stars, self._req.params, min_snr=_LOCK_MIN_SNR)
        return seen >= max(1, math.ceil(len(self._anchor_stars) / 2))

    def _anchor(self, green, wcs, diag, frame_no: int, fname: str):
        """S43: check the lock; re-solve and re-anchor the frame when it is lost."""
        if self._tracker is None:
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
            self._reference = solution
            self._reference_index = self._file_index
            self._tracker = self._build_tracker(green)
            self._tracker.update(green)
            tracked = TrackedWCS(self._reference, self._tracker)
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
        """S58: a solution of this frame or the previous one, no aperture moved >= 2 px."""
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

    def _verify(self, green, wcs, diag, frame_no: int, fname: str):
        """S58: S56's rule for a lock on fewer than 3 anchors."""
        n = len(self._anchor_stars)
        if self._tracker is None or not 0 < n < _LOCK_VERIFY_MIN_ANCHORS or self._fresh(wcs):
            self._unverified_logged = False
            return wcs, True
        solution = self._solve(green, fname)
        if solution is not None:
            self._reference = solution
            self._reference_index = self._file_index
            self._tracker = self._build_tracker(green)
            self._tracker.update(green)
            tracked = TrackedWCS(self._reference, self._tracker)
            n = len(self._anchor_stars)
            if self._lock_holds(green, tracked) and (
                n >= _LOCK_VERIFY_MIN_ANCHORS or self._fresh(tracked)
            ):
                self._frames_verify_solved += 1
                self._unverified_logged = False
                diag.record("event", frame=frame_no, what="lock_verified_by_solve", anchors=n)
                return tracked, True
            wcs = tracked
        self._frames_unverified += 1
        if not self._unverified_logged:
            self._unverified_logged = True
            logger.warning(
                "%s: only %d anchor star(s) steer the apertures — the lock cannot be"
                " verified; points are flagged suspect while fewer than 3 anchor stars steer"
                " the apertures (except within 2 px of a solution of this frame or the"
                " previous one)",
                fname,
                n,
            )
        diag.record("event", frame=frame_no, what="lock_unverified", anchors=n)
        return wcs, False

    def _solve(self, green, fname: str):
        if self._req.solver is None:
            return None
        try:
            solution = self._req.solver(green)
        except JobCancelled:
            raise
        except Exception as exc:  # a solver failure flags the frame, never ends the run
            logger.warning("%s: re-solve failed: %s", fname, exc)
            return None
        if solution is None and not self._solver_failed_logged:
            self._solver_failed_logged = True
            logger.warning("%s: the frame did not solve — its points are flagged", fname)
        return solution

    def _measure_series_fwhm(self, raw, diag) -> float | None:
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
        if not self._req.params.track_apertures:
            return self._req.wcs
        if self._tracker is None:
            self._tracker = self._build_tracker(green)
        self._tracker.update(green)
        if not self._tracker.anchors_used:
            logger.warning("%s: no anchor star found — apertures unguided", fname)
        return TrackedWCS(self._reference, self._tracker)

    def _build_tracker(self, green) -> ApertureTracker:
        tset = self._req.target_set
        wcs = self._reference
        candidates = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        anchors = select_tracking_anchors(green, wcs, candidates, self._req.params)
        if not anchors:
            anchors = select_tracking_anchors(
                green, wcs, list(tset.stars), self._req.params, min_snr=_LOCK_MIN_SNR
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
    ) -> None:
        for res in results:
            has_mag = res.diff is not None and res.diff.mag is not None
            has_ratio = res.relative is not None and res.relative.flux_ratio is not None
            if not (has_mag or has_ratio):
                continue
            key = curve_key(res.star, token)
            if res.star.role == ROLE_CHECK:
                self._check_keys.add(key)
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
                suspect=bool(res.phot and res.phot.suspect) or flagged,
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
            if flagged:
                self._flagged.add(id(pt))
            # Qt's point signal fed a live plot; the web reads the written CSVs.
            series_label(lc, any(c.filter_name != token for c in curves.values()))

    @staticmethod
    def _apply_systematic_floors(
        curves: dict[str, LightCurve], flagged: set[int] = frozenset()
    ) -> None:
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
        lat, lon, elev = self._req.site
        if jd is None or lat is None or lon is None:
            return None
        return bjd_tdb(jd, star.ra_deg, star.dec_deg, float(lat), float(lon), float(elev))

    def _airmass(self, jd: float | None, star) -> float | None:
        lat, lon, _elev = self._req.site
        if jd is None or lat is None or lon is None:
            return None
        return airmass_at(jd, star.ra_deg, star.dec_deg, float(lat), float(lon))

    @staticmethod
    def _read_frame(fpath: Path, egain_table=None):
        """``_read_frame`` + ``_read_filter`` in one open: (array, mid JD, e-/ADU, FILTER).

        Qt opened the file twice (pixels, then the FILTER card); the values are
        the same.
        """
        from astropy.io import fits

        from argos.server.fits_source import _check_size

        try:
            with fits.open(fpath) as hdul:
                header = hdul[0].header
                filter_name = str(header.get("FILTER", "") or "").strip()
                _check_size(header)  # an oversized file is unreadable, as a corrupt one
                data = hdul[0].data
        except Exception:
            return None, None, None, ""
        if data is None:
            return None, None, None, filter_name
        arr = np.nan_to_num(np.asarray(data, dtype=np.float32))
        jd = None
        date_str = str(header.get("DATE-OBS", "") or "")
        if "T" in date_str:  # a date without a time is not an epoch (not midnight)
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                jd = julian_date(dt)
            except ValueError:
                jd = None
        if jd is not None:
            try:
                jd += float(header["EXPTIME"]) / 2.0 / 86400.0
            except (KeyError, TypeError, ValueError):
                logger.warning("%s: no EXPTIME — JD is exposure start, not midpoint", fpath.name)
        return arr, jd, frame_egain(header, egain_table), filter_name

    def _write_csvs(self, curves: dict[str, LightCurve]) -> None:
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


# ---------------------------------------------------------------------------
# The service (A76)
# ---------------------------------------------------------------------------


def _engine_egain(hub: "Hub") -> float:
    """``imaging_page._engine_egain``: Settings' table at the Camera gain, else the sensor's."""
    from argos.core.hardware import active as hardware
    from argos.core.imaging import sensor_models

    with hub._lock:
        gain = int(hub._capture_settings.gain)
    table = hub.config.get("camera.egain_table", {}) or {}
    if isinstance(table, dict) and str(gain) in table:
        try:
            return float(table[str(gain)])
        except (TypeError, ValueError):
            pass
    return sensor_models.lookup_egain(hardware.profile().sensor, gain)


def _frame_solver(
    cfg_get, centre: tuple[float, float] | None, cancel: threading.Event, on_stage=None
) -> Callable[[np.ndarray], object]:
    """``batch_frame_solver`` through the cancellable ASTAP runner (S43/S58 re-solves)."""
    from argos.core.imaging.astrometry_session import build_solve_settings, wcs_from_result
    from argos.server.field_solve import SolveCancelled, solve_green

    def solve(green):
        plane = np.asarray(green)
        settings = build_solve_settings(cfg_get, plane.shape, live=True, mount_radec=centre)
        settings.allow_blind_retry = False
        if on_stage is not None:
            on_stage("re-solving")
        try:
            result = solve_green(np.clip(plane, 0, 65535).astype(np.uint16), settings, cancel)
        except SolveCancelled as exc:
            raise JobCancelled() from exc
        finally:
            if on_stage is not None:
                on_stage("measuring")
        return wcs_from_result(result, plane.shape) if result.solved else None

    return solve


def _wcs_centre(wcs) -> tuple[float, float] | None:
    crval = (getattr(wcs, "crval1", None), getattr(wcs, "crval2", None))
    return (crval[0] / 15.0 % 24.0, crval[1]) if None not in crval else None


class RerunService:
    """``POST /api/review/rerun`` (A76) and its plan."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._lock = threading.Lock()
        self._selections: dict[tuple[str, str], tuple[int, FrameSelection]] = {}

    # -- inputs ----------------------------------------------------------------

    def _resolve(self, body: dict[str, Any]):
        roots = self._hub.fs_roots
        session, _root = roots.resolve(body.get("session") or "", what="session folder")
        if session.is_file() and session.name == "session.json":
            session = session.parent
        if session.is_file():  # as A68: a file is not a session
            raise ApiError(400, "invalid_argument", f"{session.name} is not a session folder")
        if not session.is_dir():
            raise ApiError(404, "not_found", f"No folder {session}")
        frames_raw = body.get("frames")
        if frames_raw:
            frames_dir, _ = roots.resolve(frames_raw, what="frames folder")
            if not frames_dir.is_dir():
                raise ApiError(404, "not_found", f"No folder {frames_dir}")
        else:
            frames_dir = session
        mode = body.get("targets") or "session"
        if mode == "live":
            tset = self._hub.targets.snapshot()
        else:
            path = session / "targets.json"
            tset = TargetSet.load(path) if path.is_file() else TargetSet()
        reference = body.get("reference") or "solve"
        ref_frame = None
        if body.get("reference_frame"):
            ref_frame, _ = roots.resolve(body["reference_frame"], what="reference frame")
            if ref_frame.suffix.lower() not in _FITS_SUFFIXES:
                raise ApiError(
                    400, "invalid_argument", f"{ref_frame.name} is not a FITS frame (.fit/.fits)"
                )
            if not ref_frame.is_file():
                raise ApiError(404, "not_found", f"No file {ref_frame}")
        return session, frames_dir, mode, tset, reference, ref_frame

    def _discover(self, frames_dir: Path, object_name: str | None) -> FrameSelection:
        """:func:`discover_light_frames`, cached while no FITS file below changes.

        The scan reads one header per frame (about 4 ms each): the dialog's plan and
        the start then cost one scan, not one per call (W7 technical review: 23 s for
        6000 frames, past the client's timeout).
        """
        import os

        files = []
        for dirpath, _dirs, names in os.walk(frames_dir):
            for name in names:
                if Path(name).suffix.lower() in _FITS_SUFFIXES:
                    try:
                        st = os.stat(os.path.join(dirpath, name))
                    except OSError:
                        continue
                    files.append((dirpath, name, st.st_mtime_ns, st.st_size))
        key = (str(frames_dir), object_key(object_name))
        stamp = hash(tuple(sorted(files)))
        with self._lock:
            held = self._selections.get(key)
        if held is not None and held[0] == stamp:
            return held[1]
        selection = discover_light_frames(frames_dir, object_name)
        with self._lock:
            self._selections[key] = (stamp, selection)
            while len(self._selections) > 4:
                self._selections.pop(next(iter(self._selections)))
        return selection

    @staticmethod
    def _output_root(session: Path, frames_dir: Path) -> Path:
        """The re-run folder goes inside the session (protocol A76), the frames' folder
        only when ``session`` is not one (no ``session.json``)."""
        return session if (session / "session.json").is_file() else frames_dir

    def _live_solution(self):
        field_service = getattr(self._hub, "field", None)
        return field_service.reference_solution() if field_service is not None else None

    def _astap(self) -> bool:
        from argos.core.imaging.platesolve import find_astap

        return find_astap(str(self._hub.config.get("astrometry.astap_path", "") or "")) is not None

    def _refusal(self, tset, selection, reference, frames_dir) -> dict[str, str] | None:
        if not selection.paths:
            return {
                "code": "no_frames",
                "message": f"No light frames (.fit/.fits/.fts) of"
                f" {tset.object_name or 'the target'} in {frames_dir}",
            }
        if not tset.by_role(ROLE_TARGET):
            return {"code": "no_targets", "message": "Assign at least one target star first."}
        if not tset.by_role(ROLE_COMPARISON):
            return {
                "code": "no_comparisons",
                "message": "The target set has no comparison stars, so differential photometry"
                " cannot produce magnitudes.",
            }
        if reference == "live" and self._live_solution() is None:
            return {
                "code": "not_solved",
                "message": "Plate-solve the live frame before a batch re-run.",
            }
        if reference == "solve" and not self._astap():
            return {
                "code": "astap_missing",
                "message": "ASTAP not found — set its path in Settings › Plate solving",
            }
        return None

    def _params(self) -> PhotometryParams:
        return PhotometryParams.from_config(self._hub.config.get, egain=_engine_egain(self._hub))

    def plan(self, body: dict[str, Any]) -> dict[str, Any]:
        """``POST /api/review/rerun/plan``: what a start now would do; never writes."""
        session, frames_dir, mode, tset, reference, ref_frame = self._resolve(body)
        selection = self._discover(frames_dir, tset.object_name)
        params = self._params()
        first = ref_frame or (selection.paths[0] if selection.paths else None)
        return {
            "session": str(session),
            "frames_dir": str(frames_dir),
            "frames": len(selection.paths),
            "frame_names": {
                "first": selection.paths[0].name if selection.paths else None,
                "last": selection.paths[-1].name if selection.paths else None,
            },
            "left_out": {
                "calibration": selection.calibration,
                "other_object": selection.other_object,
                "outside_lights": selection.outside_lights,
                "duplicates": selection.duplicates,
            },
            "stars": {
                "object": tset.object_name or "",
                "target": len(tset.by_role(ROLE_TARGET)),
                "comparison": len(tset.by_role(ROLE_COMPARISON)),
                "check": len(tset.by_role(ROLE_CHECK)),
            },
            "targets": mode,
            "reference": {
                "mode": reference,
                "frame": first.name if (reference == "solve" and first is not None) else None,
                "live_available": self._live_solution() is not None,
                "astap": self._astap(),
            },
            "params": {
                "aperture_fwhm_mult": params.aperture_fwhm_mult,
                "aperture_min_px": params.aperture_min_px,
                "annulus_in_px": params.annulus_in_px,
                "annulus_out_px": params.annulus_out_px,
                "egain": params.egain,
                "read_noise_e": params.read_noise_e,
                "sat_adu": params.sat_adu,
                "band": params.band,
                "min_comps": params.min_comps,
                "track_apertures": params.track_apertures,
            },
            "site_set": observing_site(self._hub.config) is not None,
            "out_dir": str(
                rerun_output_dir(self._output_root(session, frames_dir), datetime.now(timezone.utc))
            ),
            "refusal": self._refusal(tset, selection, reference, frames_dir),
        }

    # -- the job ---------------------------------------------------------------

    def start(self, body: dict[str, Any]) -> dict[str, Any]:
        """``POST /api/review/rerun`` (A76): refusals at once, then the ``rerun`` job."""
        hub = self._hub
        session, frames_dir, mode, tset, reference, ref_frame = self._resolve(body)
        selection = self._discover(frames_dir, tset.object_name)
        refusal = self._refusal(tset, selection, reference, frames_dir)
        if refusal is not None:
            raise ApiError(409, refusal["code"], refusal["message"])
        cfg_get = hub.config.get
        params = self._params()
        site = observing_site(hub.config) or (None, None, 0.0)
        diagnostics = body.get("diagnostics")
        if diagnostics is None:
            diagnostics = bool(cfg_get("diagnostics.enabled", False))
        egain_table = cfg_get("camera.egain_table", {}) or {}
        live = self._live_solution() if reference == "live" else None
        ref_path = ref_frame or selection.paths[0]
        paths = list(selection.paths)
        object_name = tset.object_name or "untitled"
        out_root = self._output_root(session, frames_dir)

        def body_fn(ctx: JobContext) -> dict[str, Any]:
            if live is not None:
                wcs, ref_name = live[0], None
            else:
                ctx.progress(0, len(paths), stage="solving the reference", message=ref_path.name)
                wcs = self._solve_reference(ref_path, ctx)
                ref_name = ref_path.name
            out_dir = rerun_output_dir(out_root, datetime.now(timezone.utc))

            def progress(done: int, total: int, name: str) -> None:
                ctx.progress(done, total, message=name)

            def stage(text: str) -> None:
                ctx.progress(None, stage=text)

            request = BatchRequest(
                fits_paths=paths,
                wcs=wcs,
                target_set=tset,
                params=params,
                out_dir=out_dir,
                object_name=object_name,
                site=site,
                diagnostics=bool(diagnostics),
                egain_table=egain_table,
                solver=_frame_solver(cfg_get, _wcs_centre(wcs), ctx.cancel_event, stage),
            )
            ctx.progress(0, len(paths), stage="measuring", message=None)
            run = BatchRun(request, cancel=ctx.cancel_event, progress=progress)
            try:
                result = run.run()
            except JobCancelled:
                result = BatchResult(cancelled=True)
            if result.cancelled:
                self._discard(out_dir)
                # The flight recorder stays (``_discard``): say so, and end on these words
                # rather than the last frame's name (the job strip shows the message).
                kept = out_dir.is_dir()
                said = (
                    f"cancelled after {ctx_done(ctx)}/{plural(len(paths), 'frame')}: no curve saved"
                    + (f"; the per-frame notes are kept in {out_dir.name}/" if kept else "")
                )
                ctx.progress(None, message=said[0].upper() + said[1:])
                hub.log("warning", f"Batch photometry {said}.", source="review", topic="photometry")
                raise JobCancelled()
            if not result.ok:
                self._discard(out_dir)
                hub.log(
                    "error", f"Batch failed: {result.error}", source="review", topic="photometry"
                )
                raise ApiError(500, "rerun_failed", result.error)
            notes = self._notes(result, len(paths), out_dir, bool(diagnostics))
            for level, text in notes:
                hub.log(level, text, source="review", topic="photometry")
            return self._result(
                result, paths, selection, out_dir, wcs, reference, ref_name, notes, object_name
            )

        def ctx_done(ctx: JobContext) -> int:
            try:
                return int(hub.jobs.get(ctx.id)["done"])
            except ApiError:
                return 0

        return hub.jobs.start(
            "rerun",
            body_fn,
            resource=str(session),
            cancellable=True,
            total=len(paths),
            stage="queued",
        )

    def _solve_reference(self, path: Path, ctx: JobContext):
        """Plate-solve the reference frame (``build_solve_settings(live=False)``, as A74)."""
        from astropy.io import fits

        from argos.core.imaging.astrometry_session import build_solve_settings, wcs_from_result
        from argos.server.field_solve import SolveCancelled, header_hint, solve_green

        from argos.server.fits_source import FitsReadError, _check_size

        try:
            with fits.open(path) as hdul:
                header = hdul[0].header
                _check_size(header)  # before the pixels are read (W7 technical review)
                data = hdul[0].data
                arr = np.nan_to_num(np.asarray(data, dtype=np.float32))
        except FitsReadError as exc:
            raise ApiError(400, "invalid_fits", f"{path.name}: {exc}") from exc
        except Exception as exc:
            raise ApiError(400, "invalid_fits", f"Could not read {path.name}: {exc}") from exc
        green = green_plane(arr)
        settings = build_solve_settings(
            self._hub.config.get, green.shape, live=False, mount_radec=header_hint(header)
        )
        try:
            result = solve_green(
                np.clip(green, 0, 65535).astype(np.uint16),
                settings,
                ctx.cancel_event,
                lambda text: ctx.progress(None, message=f"{path.name}: {text}"),
            )
        except SolveCancelled as exc:
            ctx.progress(
                None, message="Cancelled while identifying the reference frame: no curve saved"
            )
            raise JobCancelled() from exc
        wcs = wcs_from_result(result, green.shape) if result.solved else None
        if wcs is None:
            raise ApiError(
                422,
                "not_solved",
                f"The reference frame {path.name} did not solve: {result.message or 'no solution'}",
            )
        return wcs

    @staticmethod
    def _discard(out_dir: Path) -> None:
        """A cancelled or failed run leaves nothing but its flight recorder."""
        if not out_dir.is_dir():
            return
        if not any(p.name.endswith("_diagnostics.jsonl") for p in out_dir.iterdir()):
            shutil.rmtree(out_dir, ignore_errors=True)

    @staticmethod
    def _notes(result: BatchResult, total: int, out_dir: Path, diagnostics: bool):
        """``imaging_page._on_batch_done``'s log lines, the counts' plurals spelled out."""
        notes: list[tuple[str, str]] = []
        if result.frames_skipped:
            notes.append(
                (
                    "warning",
                    f"Batch photometry: {plural(result.frames_skipped, 'frame')} skipped "
                    "(unreadable, or no DATE-OBS to date a point).",
                )
            )
        if not result.curves:
            extra = f" — see the per-frame notes in {out_dir}" if diagnostics else ""
            notes.append(("warning", f"Batch photometry: no points measured{extra}."))
            return notes
        roles: dict[str, int] = {}
        for curve in result.curves.values():
            roles[curve.role] = roles.get(curve.role, 0) + 1
        counts = ", ".join(
            f"{roles[role]} {role}" for role in ("target", "check", "comparison") if roles.get(role)
        )
        notes.append(
            (
                "ok",
                f"Batch photometry: {plural(result.frames_done, 'frame')} measured; curves: {counts}"
                f" → {out_dir}.",
            )
        )
        if result.frames_resolved:
            notes.append(
                (
                    "info",
                    f"Batch photometry: the field jumped on {plural(result.frames_resolved, 'frame')}; "
                    "each was re-solved and the apertures re-anchored on it.",
                )
            )
        if result.frames_unanchored:
            notes.append(
                (
                    "warning",
                    f"Batch photometry: {plural(result.frames_unanchored, 'frame')} measured where the "
                    "field was lost (a pointing jump or clouds) and not re-solved: their points "
                    "are flagged suspect and left out of the AAVSO export.",
                )
            )
        if result.frames_unverified:
            notes.append(
                (
                    "warning",
                    f"Batch photometry: {plural(result.frames_unverified, 'frame')} steered by fewer than"
                    " 3 anchor stars had no verified lock (no solution of that frame or the one"
                    " before within 2 px): their points are flagged suspect and left out of the"
                    " AAVSO export.",
                )
            )
        lost = result.frames_resolved or result.frames_unanchored or result.frames_unverified
        if not lost and (abs(result.rotation_deg) > 0.05 or result.shift_px > 1.0):
            notes.append(
                (
                    "info",
                    f"Apertures tracked the field: {result.rotation_deg:+.2f}° rotation, "
                    f"{result.shift_px:.1f} px drift vs the reference solve.",
                )
            )
        return notes

    def _result(self, result, paths, selection, out_dir, wcs, mode, ref_name, notes, object_name):
        curves = []
        target_file = None
        for key, lc in result.curves.items():
            tag = lc.auid or lc.name or "photometry"
            name = run_curve_csv_name(
                lc.role or "target", object_name, lc.filter_name or "clear", tag
            )
            if target_file is None and lc.role == ROLE_TARGET:
                target_file = name
            curves.append(
                {
                    "key": key,
                    "role": lc.role,
                    "name": lc.name,
                    "auid": lc.auid or None,
                    "filter": lc.filter_name,
                    "points": len(lc.points),
                    "file": name,
                }
            )
        centre = _wcs_centre(wcs)
        scale = None
        cd = getattr(wcs, "cd", None)
        if isinstance(cd, tuple) and len(cd) == 4:
            # per green px -> per frame px (a green px spans two sensor px)
            scale = math.sqrt(abs(cd[0] * cd[3] - cd[1] * cd[2])) * 3600.0 / 2.0
        first_csv = target_file or (curves[0]["file"] if curves else None)
        return {
            "out_dir": str(out_dir),
            "folder": out_dir.name,
            "source": ({"kind": "import", "path": str(out_dir / first_csv)} if first_csv else None),
            "frames_total": len(paths),
            "frames_done": result.frames_done,
            "frames_skipped": result.frames_skipped,
            "frames_resolved": result.frames_resolved,
            "frames_unanchored": result.frames_unanchored,
            "frames_unverified": result.frames_unverified,
            "left_out": {
                "calibration": selection.calibration,
                "other_object": selection.other_object,
                "outside_lights": selection.outside_lights,
                "duplicates": selection.duplicates,
            },
            "rotation_deg": result.rotation_deg,
            "shift_px": result.shift_px,
            "series_fwhm_px": result.series_fwhm,
            "aperture_px": self._params().aperture_px(result.series_fwhm),
            "reference": {
                "mode": mode,
                "frame": ref_name,
                "ra_hours": centre[0] if centre else None,
                "dec_deg": centre[1] if centre else None,
                "scale_arcsec_px": scale,
            },
            "curves": curves,
            "check_rms": [
                {
                    "key": key,
                    "filter": result.curves[key].filter_name,
                    "rms_mag": rms,
                    "n": n,
                }
                for key, (rms, n) in sorted(result.check_rms.items())
            ],
            "notes": [text for _level, text in notes],
        }


__all__ = [
    "BatchRequest",
    "BatchResult",
    "BatchRun",
    "FrameSelection",
    "RerunService",
    "discover_light_frames",
    "object_key",
    "rerun_output_dir",
]
