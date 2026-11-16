"""Live differential photometry (rows A54-A58 of ``web/spec/README.md`` §4.3).

A Qt-free port of the live photometry half of ``AcquisitionEngine``
(``argos/core/session/acquisition_engine.py``, 0.5.0):

- **when**: one point per field solution outside a sequence
  (``measure_photometry_if_idle``, 1062-1065, called by
  ``_on_astrometry_solved``, ``imaging_page.py:1417``), on the newest frame
  of the solved geometry (Qt's ``_last_raw``); a sequence measures every
  saved sub (``_on_seq_frame_saved``, 772-797: :meth:`measure_saved_frame`);
- **what**: ``_measure_photometry`` (1604-1667) over the unchanged core
  ``measure_frame`` with the apertures placed by core's ``ApertureTracker``
  (``_wcs_for_frame`` / ``_build_live_tracker``, 1542-1582: an owner decision,
  the wave 4 ``FieldTracker`` keeps placing the overlays), the series FWHM
  (P7), ``_emit_live_point`` (1700-1765), the run-level floor
  (``_apply_systematic_floor``, 1767-1795), the CSVs (``_photometry_csv_path``,
  1531-1540) and the leave-one-out report (``_write_live_quality_report``,
  1669-1698), the flight recorder (``_diagnostics``, 887-913);
- **reset**: an object change clears the curves (``on_object_changed`` →
  ``clear_lightcurves``, 258-274, 1281-1293); a set change or a new solution
  drops the tracker (``_reset_tracker``, 1595-1602);
- **0.5.0 S48** (release branch): the lock check of each measured frame
  (fewer than ceil(n/2) anchors showing a star where the tracked solution puts
  them: no point, a re-solve due at once); **S49**: one curve and one CSV per
  (star, filter), the filter in the file name, the comparisons vetted per filter;
  **S54**: a new solution must show the tracker's anchors (:meth:`solution_refusal`,
  called by the field before it applies one), unless 3 consecutive refused ones
  agree (a re-pointing the mount did not report); **S56**: a lock on fewer than 3
  anchors is unverified, its points flagged suspect and a re-solve due at once,
  unless the frame is measured within 2 px of a solution of this sub or the
  previous one; the anchors are chosen on the solved frame (:func:`anchor_frame`)
  and a run's sub verified through the previous sub's solution is solved too (S56
  as amended on 2026-11-15, second set); **S57**: every vetting file names its filter.

One deliberate difference with the Qt 0.5.0 code: the series FWHM is frozen
on the **first** measured frame. Qt read it before ``_diagnostics`` reset it on
a new object, so its first point had its own aperture and the series used the
second frame's FWHM (``notes/release_0_5_0.md`` S31, fixed in the release
branch; the owner's CSVs show it: ``fwhm`` 2.16 on the first row, 2.12 on the
194 others).

Threads: measurements run on one photometry thread (FIFO), never on the event
loop. Lock order: the service lock, then the hub's; the target set's lock is
never held while this one is taken. The newest records are kept for a new
client's snapshots and read without the service lock.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from argos.core.catalog.targets import (
    ROLE_CHECK,
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    comparison_chart_id,
)
from argos.core.config import observing_site
from argos.core.imaging.fits_writer import FILTER_ABBREV
from argos.core.imaging.green import green_plane
from argos.core.imaging.metrics import detect_stars
from argos.core.photometry.airmass import (
    airmass_at,
    airmass_from_altitude,
    bjd_tdb,
    julian_date,
)
from argos.core.photometry.lightcurve import LcPoint, LightCurve
from argos.core.photometry.params import DEFAULT_FWHM, PhotometryParams, measure_frame
from argos.core.photometry.quality import comparison_quality_report, save_comparison_quality_report
from argos.core.photometry import tracking as _core_tracking
from argos.core.photometry.tracking import (
    ApertureTracker,
    TrackedWCS,
    anchors_seen,
    select_tracking_anchors,
)
from argos.core.photometry.uncertainty import apply_systematic_floor, estimate_systematic_floor
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: The Qt texts (``acquisition_engine.py:1612-1615``; S35 in the release branch).
NO_EPOCH_TEXT = "Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME)."
FIELD_LOST_TEXT = (
    "Photometry skipped: no star of the set where the solution places it"
    " — the field moved since the solve, or clouds."
)
#: S48 (release branch ``_measure_photometry``).
LOCK_LOST_TEXT = (
    "Photometry skipped: fewer than half the anchor stars show a star where the"
    " solution places them — the field moved since the solve, or clouds."
    " Re-solving."
)
#: S48: an anchor is seen at SNR 5 or more (S35's threshold); the lock holds when
#: ceil(n/2) of the n anchors are seen (S43's rule).
LOCK_MIN_SNR = 5.0
#: S56 (release ``_LOCK_VERIFY_MIN_ANCHORS``): with fewer anchors ceil(n/2) is met by
#: the very anchor that moved the solution: the lock is unverified...
LOCK_VERIFY_MIN_ANCHORS = 3
#: ...unless the frame is measured through a solution of this sub or the previous one
#: and the tracker moved no aperture of the set this many green px or more from where
#: that solution puts it (release ``_LOCK_FRESH_MAX_SHIFT_PX``, S56 as amended).
LOCK_FRESH_MAX_SHIFT_PX = 2.0
#: S56 (release ``lock_unverified_text``), once per episode: until a verified frame,
#: a slew or invalidation, or a set change.
LOCK_UNVERIFIED_TEXT = (
    "Photometry: only {n} anchor star{s} steer the apertures — the lock cannot be"
    " verified; points are flagged suspect while fewer than 3 anchor stars steer the"
    " apertures (except within 2 px of a solution of this sub or the previous one)."
    " Re-solving."
)
#: S69 (b) (release ``off_centre_text``), once per episode: until a frame with none.
OFF_CENTRE_TEXT = (
    "Photometry: {n} comparison/check star{s} more than 1 px from the aperture centre"
    " — left out of the frame's ensemble, their points flagged suspect."
)


def s69_core():
    """GUARD (S69, release/0.5.0): the core's ``tracking`` module when it has S69's
    centring check and rotation rule (``centring_offsets``, ``off_centre``,
    ``rotation_resolve_due``, ``TrackedWCS.rotation_deg``; ``measure_frame`` and
    ``measure_targets`` take ``exclude``) and the neighbour rule of the S69 review
    (``neighbour_distance``; ``select_tracking_anchors`` and ``centring_offsets`` take
    ``neighbours``, ``ApertureTracker.rejected_anchor``), else None: until the release
    core is merged the live path, the sequence path and the re-run (rerun.py) measure
    as before, S70 included (S70 is applied together with S69)."""
    names = ("centring_offsets", "off_centre", "rotation_resolve_due", "neighbour_distance")
    if all(hasattr(_core_tracking, name) for name in names):
        return _core_tracking
    return None


def set_neighbours(tset) -> dict:
    """S69 (GUARD: :func:`s69_core`): ``neighbours=`` the set's stars, targets included,
    for ``select_tracking_anchors`` and ``centring_offsets`` (a star beside a brighter
    one of the set is no anchor, and its centring centroid stays clear of it)."""
    return {"neighbours": list(tset.stars)} if s69_core() is not None else {}


def centred_anchors(anchor_stars, tracker, offsets) -> int:
    """S69 (b) (release ``_centred_anchors``): the tracker's anchors less those more than
    1 px off their aperture centre on this frame and the one its fit rejected (it
    verified nothing); without the centring check (GUARD), all of them."""
    core = s69_core()
    if core is None:
        return len(anchor_stars)
    bad = core.off_centre(offsets or {})
    rejected = getattr(tracker, "rejected_anchor", None)
    return sum(
        1 for index, star in enumerate(anchor_stars) if star.key() not in bad and index != rejected
    )


#: S54 as amended (release ``_REPOINT_SOLVES``, ``_REPOINT_AGREE_PX``): 3 consecutive
#: solutions refused by the anchor check that agree within 20 green px are a
#: re-pointing the mount did not report: the third is accepted.
REPOINT_SOLVES = 3
REPOINT_AGREE_PX = 20.0
REPOINT_TEXT = (
    "Solve: {k} consecutive solutions agree within {span:.1f} px on a field where the"
    " anchor stars are not ({seen} of {anchors} seen) — accepted as a re-pointing the"
    " mount did not report"
)


def solutions_span_px(solutions: list, green_shape: tuple[int, int]) -> float:
    """S54 (release ``solutions_span_px``): the largest distance (green px) between where
    the solutions put the newest one's frame centre."""
    h, w = green_shape
    ra_h, dec = solutions[-1].pixel_to_radec((w - 1) / 2.0, (h - 1) / 2.0)
    pts = [
        tuple(float(v) for v in s.world_to_pixel_deg(float(ra_h) * 15.0, float(dec)))
        for s in solutions
    ]
    return max(
        (math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(pts) for b in pts[i + 1 :]),
        default=0.0,
    )


STATUS_TEXT = {
    "no_target": "No target star: choose one on the image or in the Variables list.",
    "not_solved": "Waiting for a field solution: the next one measures a point.",
    "waiting": "Waiting for the next field solution.",
    "no_epoch": "Skipped frame #{seq}: it has no exposure time (DATE-OBS/EXPTIME).",
    "no_comparison": "Skipped frame #{seq}: the target set has no comparison star.",
    "no_point": "Skipped frame #{seq}: no star of the set could be measured.",
    "field_lost": (
        "Skipped frame #{seq}: no star of the set where the solution places it"
        " (the field moved since the solve, or clouds)."
    ),
    "lock_lost": (
        "Skipped frame #{seq}: fewer than half the anchor stars show a star where the"
        " solution places them (the field moved, or clouds); re-solving."
    ),
}


def anchor_frame(green, wcs, solved_raw: np.ndarray | None):
    """The frame the tracker's anchors are chosen on and the solution exact there, or
    None (release ``AcquisitionEngine._anchor_frame``, S56 as amended on 2026-11-15,
    second set): the frame ``wcs`` was solved on, of the measured frame's geometry.

    Chosen on the measured sub through a solution of an earlier one, only the stars
    that happened to show at the stale positions qualified after a jump, and the
    lock check (S48, S56) verified the very star that moved the apertures (real RR
    Lyr subs moved 500 px without a slew: 1 anchor, 2.16 px of tracker motion, the
    target 496 px off). On the solved frame every anchor qualifies, and the check
    counts those the measured sub shows (1 of 6 there: the lock is lost).
    """
    if solved_raw is None or wcs is None:
        return None
    solved = green_plane(solved_raw)
    if solved.shape != green.shape:
        return None
    return solved, wcs


def bundled_iers_only() -> None:
    """Never let astropy download IERS or leap-second tables (release S37).

    Core's ``bjd_tdb`` lets astropy fetch ``finals2000A.all`` and the leap
    seconds on first use; offline it then refuses its bundled table and every
    BJD_TDB is lost (2.3 s per frame refused, ~18 s on a hanging network). The
    bundled tables give the same BJD to the bit. Same settings as the mount's
    coordinate conversion (``telescope.py``) and the release branch's fix.
    """
    from astropy.utils import iers

    iers.conf.auto_download = False
    iers.conf.auto_max_age = None


def write_csv_atomic(curve: LightCurve, path: Path) -> None:
    """``LightCurve.to_csv`` written beside the file and renamed over it (release S38).

    A reader (Review, a spreadsheet) or a crash mid-write sees the previous file
    or the new one, never a truncated one. The same bytes as ``to_csv``.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        curve.to_csv(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _num(value: Any) -> float | None:
    """A finite float, else ``None`` (strict JSON: NaN and ±inf are not numbers)."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def point_record(
    point: LcPoint,
    frame_seq: int | None,
    t: str | None,
    zero_point: float | None = None,
    zp_rms: float | None = None,
) -> dict[str, Any]:
    """An ``LcPoint`` on the wire (every field of ``lightcurve.py:38-62``, unrounded).

    Plus the star's ensemble zero point and its rms on that frame (``DiffResult``,
    the flight recorder's ``ensemble`` record): not in the CSV, the night's
    extinction and transparency trend for the plot's ensemble facet.
    """
    return {
        "jd_utc": _num(point.jd_utc),
        "t": t,
        "bjd_tdb": _num(point.bjd_tdb),
        "mag": _num(point.mag),
        "mag_err": _num(point.mag_err),
        "formal_mag_err": _num(point.formal_mag_err),
        "sigma_syst": _num(point.sigma_syst),
        "airmass": _num(point.airmass),
        "fwhm": _num(point.fwhm),
        "sky_adu": _num(point.sky_adu),
        "comps_used": int(point.comps_used or 0),
        "relative_flux": _num(point.relative_flux),
        "relative_flux_err": _num(point.relative_flux_err),
        "relative_comps_used": int(point.relative_comps_used or 0),
        "saturated": bool(point.saturated),
        "suspect": bool(point.suspect),
        "frame_seq": frame_seq,
        "zero_point": _num(zero_point),
        "zp_rms": _num(zp_rms),
    }


def star_curve_key(star) -> str:
    """Qt's star key (``_emit_live_point``, 1740): the AUID, else the display name."""
    return star.auid or star.display_name


def filter_token(filter_name: str | None) -> str:
    """The filter as frame and curve file names spell it (release ``fits_writer.filter_token``,
    S49): the abbreviation (``FILTER_ABBREV``), ASCII letters, digits, ``_`` and ``-``,
    lower case; ``clear`` for none. Its parity with the core's is a guarded test."""
    import re
    import unicodedata

    name = str(filter_name or "").strip()
    name = FILTER_ABBREV.get(name, name)
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9_-]", "", ascii_name.replace(" ", "_")).lower() or "clear"


def curve_key(star, token: str) -> str:
    """One curve per (star, filter) (S49, release ``lightcurve.curve_key``):
    ``<AUID or name>@<filter token>``."""
    return f"{star_curve_key(star)}@{token}"


def safe_name(text: str) -> str:
    """``_photometry_csv_path`` / ``_diagnostics`` file-name rule (1531-1540, 897)."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_preview_csv(
    folder: Path, obj: str, tag: str, now: datetime, taken=(), token: str = ""
) -> Path:
    """``_new_preview_csv`` (S40, S49):
    ``<folder>/<object>_<YYYYMMDDTHHMMSSZ>_<filter>_<star>.csv``, a file not yet
    used; ``-2``, ``-3``… on the time for curves started in the same second.
    Review still finds ``<object>.json`` and the star."""
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    count = 1
    while True:
        mark = stamp if count == 1 else f"{stamp}-{count}"
        if token:
            mark = f"{mark}_{token}"
        path = folder / f"{safe_name(f'{obj}_{mark}_{tag}')}.csv"
        if path not in taken and not path.exists():
            return path
        count += 1


class SessionDiagnostics:
    """The live flight recorder (``argos/core/session/diagnostics.py``, P11).

    A line-for-line port: the core module sits in the ``argos.core.session``
    package, whose ``__init__`` imports the Qt ``DeviceSession`` (the server
    never imports Qt, ``tests/server/test_no_qt.py``). One JSON object per line;
    a write error disables it with one warning; a no-op when disabled.
    """

    _NDIGITS = 4

    def __init__(self, path: Path | str, enabled: bool = True) -> None:
        self._path = Path(path)
        self._enabled = bool(enabled)
        self._fh = None

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def _clean(cls, value: Any) -> Any:
        if isinstance(value, float):
            return round(value, cls._NDIGITS)
        if isinstance(value, dict):
            return {k: cls._clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._clean(v) for v in value]
        return value

    def record(self, kind: str, frame: int | None = None, **fields: Any) -> None:
        if not self._enabled:
            return
        doc: dict[str, Any] = {
            "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": kind,
        }
        if frame is not None:
            doc["frame"] = int(frame)
        doc.update({k: self._clean(v) for k, v in fields.items() if v is not None})
        try:
            if self._fh is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = open(self._path, "a", encoding="utf-8")
            self._fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
            self._fh.flush()
        except OSError as exc:
            logger.warning("Diagnostics disabled (write failed): %s", exc)
            self._enabled = False
            self.close()

    def star(self, frame: int, star, phot, x: float, y: float, **extra: Any) -> None:
        """``extra``: more fields (S69's ``centroid_offset_px`` and ``off_centre``)."""
        self.record(
            "star",
            frame=frame,
            auid=star.auid or None,
            name=star.display_name,
            role=star.role,
            x=float(x),
            y=float(y),
            flux_adu=phot.flux_adu if phot else None,
            sky_adu=phot.sky_adu if phot else None,
            peak_adu=phot.peak_adu if phot else None,
            snr=phot.snr if phot else None,
            inst_mag=phot.inst_mag if phot else None,
            inst_mag_err=phot.inst_mag_err if phot else None,
            saturated=bool(phot.saturated) if phot else None,
            suspect=bool(getattr(phot, "suspect", False)) or None if phot else None,
            measured=phot is not None,
            **extra,
        )

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


@dataclass
class MeasureRequest:
    """One frame to measure through one solution."""

    frame_seq: int
    raw: np.ndarray
    wcs: Any  # the reference solve (green px)
    epoch: datetime | None  # exposure midpoint (UTC)
    generation: int  # the field generation of the solution
    fwhm: float | None = None  # the frame's mean FWHM when known (green px)
    run_root: Path | None = None  # a sequence's run folder (wave 6)
    origin: str = "live"  # the frame's origin; "file" = Open FITS (another night)
    reset_tracker: bool = False  # a new solution: rebuild the tracker first
    egain: float | None = None  # an opened frame's own e-/ADU (frame_egain, S41)
    #: The frame's filter (S49): a sub's read-back FILTER, an opened file's FILTER
    #: card, a live frame's Camera form; None: the wheel's settled slot, else the form.
    filter_name: str | None = None
    #: S56: the seq of the frame ``wcs`` was solved on (None: unknown). A solution
    #: of this frame or the previous one (seq - 1) is fresh.
    solved_seq: int | None = None
    #: S56 (2026-11-15, second set): the raw frame ``wcs`` was solved on (None:
    #: unknown): the tracker's anchors are chosen there, where the solution is exact.
    solved_raw: np.ndarray | None = None


class PhotometryService:
    """The live curves, their points and the leave-one-out report."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._lock = threading.RLock()
        self._curves: dict[str, LightCurve] = {}
        #: Per curve: the star's set key, its catalogue magnitudes and, per point,
        #: (frame seq, ISO midpoint).
        self._meta: dict[str, dict[str, Any]] = {}
        self._csv: dict[str, Path] = {}
        #: Outside a run, the CSV each curve was given when it started (S40).
        self._preview_csv: dict[str, Path] = {}
        self._revision = 0
        self._seq = 0
        self._frames = 0
        self._points = 0
        self._object: str | None = None
        #: P7: the series FWHM (green px), frozen on the first measured frame.
        self._phot_fwhm: float | None = None
        self._tracker: ApertureTracker | None = None
        self._tracker_anchors = 0  # anchor stars the tracker was built with
        self._tracker_anchor_stars: list = []  # ...and which (the S48 lock check)
        #: The solution the tracker was built on (the request's raw WCS, and that
        #: WCS or the tracked solution frozen at a set change), then that freeze (S52).
        self._tracker_base: tuple[Any, Any] | None = None
        self._rebase: tuple[Any, Any] | None = None
        #: S54: the field generation of the solution the tracker was built for.
        self._tracker_generation: int | None = None
        #: S56: the current unverified-lock episode was logged (once per episode: until
        #: a verified frame, a slew or invalidation, or a set change).
        self._unverified_logged = False
        #: S69 (a): the tracked rotation at which the last re-solve for rotation was made
        #: due (None: none since the solution); (b): the off-centre episode logged.
        self._rotation_attempted: float | None = None
        self._off_centre_logged = False
        #: S54: the consecutive solutions refused by the anchor check (their WCS).
        self._repoint_refused: list[Any] = []
        #: S48: the last lock check ({frame_seq, anchors, seen, needed, held}), or None.
        self._lock_state: dict[str, Any] | None = None
        #: S49: the first filter measured since the curves were cleared (its vetting
        #: report keeps the name ``photometry_quality.json``).
        self._primary_filter: str | None = None
        self._diag: SessionDiagnostics | None = None
        self._diag_object: str | None = None
        self._diag_root: Path | None = None  # the run folder of the recorder (wave 6a)
        self._diag_frame = 0
        self._last: dict[str, Any] | None = None
        self._outcome: tuple[str, str | None, int | None] | None = None  # state, reason, seq
        self._measured_keys: frozenset[str] = frozenset()  # the set the outcome is about
        self._quality_report: dict[str, Any] | None = None
        self._quality_filter: str | None = None  # the filter the report vets (S49)
        self._quality_revision = 0
        self._quality_record: dict[str, Any] = {
            "revision": 0,
            "frame_seq": None,
            "filter": None,
            "report": None,
        }
        self._status: dict[str, Any] = self._status_record()
        # the photometry thread
        self._queue: deque[MeasureRequest] = deque()
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._busy = 0

    # ------------------------------------------------------------------
    # Lifecycle and the photometry thread
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._queue.clear()
            self._cond.notify_all()
        with self._lock:
            if self._diag is not None:
                self._diag.close()
                self._diag = None

    def idle(self) -> bool:
        """Nothing queued or measuring (tests)."""
        with self._cond:
            return not self._queue and self._busy == 0

    def submit(self, request: MeasureRequest) -> None:
        with self._cond:
            if self._closed:
                return
            self._queue.append(request)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, name="argos-photometry", daemon=True
                )
                self._thread.start()
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                request = self._queue.popleft()
                self._busy += 1
            try:
                self.measure(request)
            except Exception:
                logger.exception("Photometry: frame %s failed", request.frame_seq)
            finally:
                with self._cond:
                    self._busy -= 1

    # ------------------------------------------------------------------
    # Hooks (field, targets, observation)
    # ------------------------------------------------------------------

    def on_solved(self, request: MeasureRequest) -> None:
        """A new solution was applied: ``measure_photometry_if_idle`` (1062-1065)."""
        with self._hub._lock:
            owner = self._hub._camera_state.owner
        # A sequence measures every saved sub instead; a fresh solution is still a new
        # reference for its tracker (_on_reference_solved). A run's sub is never measured
        # again here: its solve may finish after the run ended (wave 6b integration: the
        # run's last sub got a second point under no filter, a one-point curve and CSV).
        with self._lock:
            self._repoint_refused = []  # S54: a solution was accepted
        if owner in ("sequence", "autofocus") or request.origin == "sequence":
            with self._lock:
                self._tracker = None
                self._rebase = None
            return
        self.submit(replace(request, reset_tracker=True))

    def on_field_invalidated(self) -> None:
        """The solution was dropped (a slew, another source or geometry): the tracker
        and its anchors go with it (release ``invalidate_astrometry`` →
        ``_reset_tracker``), so the next field's first solution is not held to the
        previous field's anchors (S54)."""
        with self._lock:
            self._tracker = None
            self._tracker_anchor_stars = []
            self._tracker_anchors = 0
            self._rebase = None
            self._tracker_generation = None
            self._unverified_logged = False  # S56: a slew or invalidation ends the episode
            self._repoint_refused = []

    def solution_refusal(self, raw: np.ndarray, wcs: Any, generation: int) -> str | None:
        """Why a camera frame's new solution is refused (S54), or None to accept it.

        Release ``AcquisitionEngine._solution_refusal``: a new solution rebuilds
        the tracker from the stars seen where it puts them, so a wrong match passes
        the S48 check by construction (XX Cyg 2026-09-07 045156Z frame 1: 1 anchor
        of 6 seen, the next frame measured 24 px off every star). Fewer than
        ceil(k/2) of the current tracker's k anchors showing a star (SNR >= 5)
        where the new solution puts them on the frame it solved refuses it. Only a
        tracker built for the field's current solution (``generation``) counts:
        none after a slew, an opened file or a set change. Called by the field's
        solve thread, never with the hub lock held.

        3 consecutive refused solutions that agree within ``REPOINT_AGREE_PX`` (S54
        as amended on 2026-11-15, as S55 moves the scale reference): the field
        moved without a reported slew, the third is accepted and logged.
        """
        with self._lock:
            if self._tracker is None or self._tracker_generation != generation:
                return None
            stars = list(self._tracker_anchor_stars)
        if not stars or raw is None:
            return None
        params = PhotometryParams.from_config(self._hub.config.get, egain=self._hub.targets.egain())
        if not params.track_apertures:
            return None
        green = green_plane(raw)
        seen = anchors_seen(green, wcs, stars, params, min_snr=LOCK_MIN_SNR)
        needed = max(1, math.ceil(len(stars) / 2))
        with self._lock:
            if seen >= needed:
                self._repoint_refused = []
                return None
            self._repoint_refused = (self._repoint_refused + [wcs])[-REPOINT_SOLVES:]
            streak = list(self._repoint_refused)
        if len(streak) == REPOINT_SOLVES:
            span = solutions_span_px(streak, green.shape)
            if span <= REPOINT_AGREE_PX:
                with self._lock:
                    self._repoint_refused = []
                text = REPOINT_TEXT.format(
                    k=REPOINT_SOLVES, span=span, seen=seen, anchors=len(stars)
                )
                self._hub.log("warning", text, source="field", topic="field")
                return None
        return (
            f"only {seen} of the {len(stars)} anchor stars show a star where it places them"
            f" ({needed} needed: a wrong match, or the field is not there); the previous"
            " solution is kept"
        )

    def measure_saved_frame(self, request: MeasureRequest) -> None:
        """A sequence's saved sub (``_on_seq_frame_saved``, 793-797; wave 6)."""
        self.submit(request)

    def on_targets_changed(self) -> None:
        """A set change drops the tracker (release ``_anchors_changed``, S52).

        The next tracker is built on the solution as tracked so far, frozen
        here, never on the raw solution: the field has drifted since that
        solve, and a tracker rebuilt there kept only a neighbour seen at a stale
        position, passed the S48 check with 1 anchor of 1 and measured every
        aperture on blank sky until the next solve (the science review's replay
        of RR Lyr 0-79). In a run the next sub is solved at once.

        When the set's stars changed, the status waits for the next measurement:
        the last one was of the previous set (its points, its frame).
        """
        keys = frozenset(s.key() for s in self._hub.targets.snapshot().stars)
        with self._hub._lock:
            in_run = self._hub._camera_state.owner == "sequence"
        with self._lock:
            tracker, base = self._tracker, self._tracker_base
            if tracker is not None and self._tracker_anchors and base is not None:
                self._rebase = (base[0], TrackedWCS(base[1], copy.copy(tracker)))
            self._tracker = None
            self._tracker_anchor_stars = []  # release _anchors_changed (S54: no check)
            self._repoint_refused = []
            self._unverified_logged = False  # S56: a set change ends the episode
            if keys != self._measured_keys:
                self._outcome = None
        field = getattr(self._hub, "field", None)
        if in_run and field is not None and hasattr(field, "resolve_due"):
            field.resolve_due(-1)  # the next frame, not the one in hand
        self.refresh_status()

    def on_object_changed(self, object_name: str) -> None:
        """``on_object_changed`` (1281-1293): fresh curves for the new object."""
        with self._lock:
            if object_name != self._object:
                previous, self._object = self._object, object_name
                self._tracker = None
                if previous is not None or self._curves:
                    self._reset_locked("object_changed")
        self.refresh_status()

    def clear(self, reason: str = "cleared") -> None:
        """``clear_lightcurves`` (258-274); also a sequence start (650-692, wave 6)."""
        with self._lock:
            self._reset_locked(reason)
        self.refresh_status()

    def begin_run(self) -> None:
        """Wave 6a: a sequence starts (``start_sequence``: ``clear_lightcurves``; at its
        first save ``_on_seq_frame_saved`` closes the recorder, so the series FWHM
        and the frame counter restart with the run)."""
        with self._lock:
            self._close_diagnostics()
            self._reset_locked("sequence_started")
        self.refresh_status()

    def reset_series_fwhm(self) -> None:
        """An autofocus ended (Qt ``_on_af_finished``): re-sample the series FWHM (P7)."""
        with self._lock:
            self._phot_fwhm = None

    def _close_diagnostics(self) -> None:
        """Lock held."""
        if self._diag is not None:
            self._diag.close()
        self._diag = None
        self._diag_object = None
        self._phot_fwhm = None

    def _reset_locked(self, reason: str) -> None:
        self._curves.clear()
        self._meta.clear()
        self._csv.clear()
        self._preview_csv.clear()
        self._primary_filter = None
        self._quality_filter = None
        self._lock_state = None
        self._frames = 0
        self._points = 0
        self._last = None
        self._outcome = None
        self._quality_report = None
        self._publish_reset(reason)
        self._publish_quality(None)

    def _publish_reset(self, reason: str) -> None:
        """Lock held: a new revision; clients re-read ``GET /api/photometry/live``."""
        self._revision += 1
        self._seq += 1
        reset = {
            "type": "photometry_reset",
            "seq": self._seq,
            "revision": self._revision,
            "reason": reason,
        }
        self._hub.bus.publish("photometry_reset", None, reset)

    # ------------------------------------------------------------------
    # Records
    # ------------------------------------------------------------------

    def series_fwhm(self) -> float | None:
        """The frozen series FWHM (green px), read without the lock."""
        return self._phot_fwhm

    def snapshots(self, seq: int) -> list[tuple[str, int, dict[str, Any]]]:
        """Hub lock held: what a new ``/ws/events`` client receives."""
        return [
            ("photometry", seq, {"type": "photometry", **self._status}),
            ("comparison_quality", seq, {"type": "comparison_quality", **self._quality_record}),
        ]

    def _status_record(self) -> dict[str, Any]:
        """Lock held (or init): the ``photometry`` status for the current state."""
        try:
            tset = self._hub.targets.target_set()
            has_target = bool(tset.by_role(ROLE_TARGET))
        except Exception:  # during start-up
            has_target = False
        solved = bool(getattr(self._hub, "field", None) and self._hub.field.solved)
        if not has_target:
            state, reason = "off", "no_target"
        elif not solved:
            state, reason = "waiting", "not_solved"
        elif self._outcome is None:
            state, reason = "waiting", None
        else:
            state, reason = self._outcome[0], self._outcome[1]
        if state == "off":
            message = STATUS_TEXT["no_target"]
        elif state == "waiting":
            message = STATUS_TEXT["not_solved" if reason else "waiting"]
        elif state == "measured":
            last = self._last or {}
            message = f"{last.get('points', 0)} point(s) on frame #{last.get('frame_seq')}"
        else:
            message = STATUS_TEXT[reason or "no_point"].format(seq=self._outcome[2])
        return {
            "state": state,
            "reason": reason,
            "message": message,
            "frames": self._frames,
            "points": self._points,
            "last": dict(self._last) if self._last is not None else None,
            # S48: the last lock check (null: tracking off, or not measured yet).
            "lock": dict(self._lock_state) if self._lock_state is not None else None,
            "revision": self._revision,
        }

    def refresh_status(self) -> None:
        """Re-derive and publish the status when it changed (set, field, outcome)."""
        with self._lock:
            record = self._status_record()
            if record == self._status:
                return
            self._status = record
            with self._hub._lock:
                self._hub._publish("photometry", record)

    def _publish_quality(self, frame_seq: int | None) -> None:
        """Lock held: the ``comparison_quality`` snapshot."""
        self._quality_revision += 1
        record = {
            "revision": self._quality_revision,
            "frame_seq": frame_seq,
            "filter": self._quality_filter,  # the filter whose comparisons it vets (S49)
            "report": self._wire_report(self._quality_report),
        }
        self._quality_record = record
        with self._hub._lock:
            self._hub._publish("comparison_quality", record)

    def _wire_report(self, report: dict[str, Any] | None) -> dict[str, Any] | None:
        """Lock held: the core report plus each comparison's keys and newest point."""
        if report is None:
            return None
        entries = []
        token = self._quality_filter or "clear"
        for entry in report.get("comparison_stars", []):
            key = f"{entry.get('auid') or entry.get('name')}@{token}"  # its curve (S49)
            meta = self._meta.get(key, {})
            curve = self._curves.get(key)
            last = None
            if curve is not None and curve.points:
                p = curve.points[-1]
                last = {
                    "mag": _num(p.mag),
                    "mag_err": _num(p.mag_err),
                    "comps_used": int(p.comps_used or 0),
                    "jd_utc": _num(p.jd_utc),
                }
            entries.append({**entry, "key": key, "star_key": meta.get("star_key"), "last": last})
        return {**report, "comparison_stars": entries}

    def live_record(self) -> dict[str, Any]:
        """``GET /api/photometry/live`` (A54)."""
        cfg = self._hub.config.get
        tset = self._hub.targets.snapshot()
        geometry = self._hub.targets.geometry()
        sequence = getattr(self._hub, "sequence", None)
        root = sequence.run_root() if sequence is not None else None
        run_root = str(root) if root is not None else None
        sequence_running = bool(sequence is not None and sequence.active)
        with self._lock:
            set_keys = {star_curve_key(s): s.key() for s in tset.stars}
            curves = []
            for key, curve in self._curves.items():
                meta = self._meta.get(key, {})
                token = meta.get("filter") or key.rpartition("@")[2]
                extra = meta.get("points", [])
                mags = dict(meta.get("mags") or {})
                floor = next(
                    (p.sigma_syst for p in reversed(curve.points) if p.sigma_syst is not None),
                    None,
                )
                curves.append(
                    {
                        "key": key,
                        "star_key": set_keys.get(key.rpartition("@")[0]),  # null: left the set
                        "filter": token,  # S49: one curve per (star, filter)
                        "role": curve.role,
                        "name": curve.name,
                        "auid": curve.auid or None,
                        "mags": mags,
                        "catalogue_v": _num(mags.get("V")),
                        "sigma_syst": _num(floor),
                        "csv": str(self._csv[key]) if key in self._csv else None,
                        "points": [
                            point_record(p, *(extra[i] if i < len(extra) else (None, None)))
                            for i, p in enumerate(curve.points)
                        ],
                    }
                )
            record = {
                "object_name": tset.object_name or "Unknown",
                "run_root": run_root,
                "sequence_running": sequence_running,
                "band": str(cfg("photometry.default_band", "TG") or "TG"),
                "obscode": str(cfg("observer.obscode", "") or ""),
                "chart_id": comparison_chart_id(tset.by_role(ROLE_COMPARISON)),
                "site_set": observing_site(self._hub.config) is not None,
                "geometry": {**geometry, "series_fwhm_px": self._phot_fwhm},
                "curves": curves,
                "quality": self._quality_record["report"],
                "status": dict(self._status),
                "revision": self._revision,
                "seq": self._seq,
            }
        return record

    # ------------------------------------------------------------------
    # The measurement (acquisition_engine.py:1604-1667)
    # ------------------------------------------------------------------

    def _cfg(self, key: str, default: Any) -> Any:
        value = self._hub.config.get(key, default)
        return default if value is None else value

    def _sessions_base(self) -> Path:
        return self._hub._sessions_root()

    def _diagnostics(self, tset: TargetSet, run_root: Path | None) -> SessionDiagnostics:
        """``_diagnostics`` (887-913). Lock held."""
        obj = tset.object_name or "Unknown"
        if self._diag is None or self._diag_object != obj or self._diag_root != run_root:
            # A new object, or a new run folder (Qt: _on_seq_frame_saved at the run's
            # first save), restarts the series; a run that ended only moves the
            # recorder out of its folder (wave 6a).
            restart = (
                self._diag is None
                or self._diag_object != obj
                or (run_root is not None and run_root != self._diag_root)
            )
            if self._diag is not None:
                self._diag.close()
            root = run_root / "diagnostics" if run_root is not None else self._sessions_base()
            if run_root is None:
                root = root / "targets"
            self._diag = SessionDiagnostics(
                root / f"{safe_name(obj) or 'Unknown'}_live_diagnostics.jsonl",
                enabled=bool(self._cfg("diagnostics.enabled", False)),
            )
            self._diag_object = obj
            self._diag_root = run_root
            self._diag_frame = 0
            if restart:
                self._phot_fwhm = None  # new object → re-sample the series FWHM (P7)
        return self._diag

    def _csv_path(self, tset: TargetSet, star, run_root: Path | None, key: str, token: str) -> Path:
        """``_photometry_csv_path``: a run's ``photometry/{role}_{object}_{filter}_{star}.csv``
        (release S49: one file per star and filter); outside a run, the curve's own
        file, named after its start (S40) and filter."""
        obj = tset.object_name or "Unknown"
        tag = star.auid or star.display_name
        if run_root is not None:
            safe = safe_name(f"{obj}_{token}_{tag}")
            role = getattr(star, "role", "target") or "target"
            return run_root / "photometry" / f"{role}_{safe or 'photometry'}.csv"
        path = self._preview_csv.get(key)
        if path is None:
            path = new_preview_csv(
                self._sessions_base() / "targets",
                obj,
                tag,
                _utcnow(),
                taken=set(self._preview_csv.values()),
                token=token,
            )
            self._preview_csv[key] = path
        return path

    def _frame_fwhm(self, request: MeasureRequest) -> float | None:
        """The measured frame's mean FWHM (green px): Qt's ``_last_fwhm``.

        ``detect_stars`` with ``imaging.star_radius_px``, as the frame metrics
        (and the Qt display pipeline, ``preview_processor.py:58-75``) measure it.
        """
        if request.fwhm is not None:
            return request.fwhm
        known = self._hub.targets.fwhm_for(request.frame_seq)
        if known is not None:
            return known[0]
        try:
            return detect_stars(request.raw, radius=self._hub._star_radius()).mean_fwhm
        except Exception:
            logger.warning("Photometry: FWHM of frame %s failed", request.frame_seq, exc_info=True)
            return None

    def _allow_rotation(self) -> bool:
        """An EQ mount has no field rotation (``_wcs_for_frame``, 1557-1560)."""
        with self._hub._lock:
            alignment = self._hub._mount_state.alignment
        return alignment not in ("eq", "eq_gem")

    def _wcs_for_frame(
        self,
        green,
        tset: TargetSet,
        params: PhotometryParams,
        wcs,
        generation: int | None = None,
        solved_raw: np.ndarray | None = None,
    ):
        """``_wcs_for_frame`` (1542-1567, with the release branch's S35 and S52). Lock held.
        ``generation``: the field generation of ``wcs`` (S54 checks only a tracker
        built for the current solution). ``solved_raw``: the frame ``wcs`` was solved
        on, where the anchors are chosen (S56 as amended, :func:`anchor_frame`)."""
        if not params.track_apertures:
            return wcs
        # After a set change, the tracked solution frozen then (S52).
        rebase = self._rebase
        base = rebase[1] if rebase is not None and rebase[0] is wcs else wcs
        if self._tracker is None or not self._tracker_anchors:
            # Also when built with no star seen (clouds, or the field had moved):
            # try again rather than until the next solution, which S35 makes due.
            # The anchors are chosen on the solved frame (S56, second set).
            self._tracker, self._tracker_anchor_stars = self._build_live_tracker(
                green, base, tset, params, chosen_on=anchor_frame(green, wcs, solved_raw)
            )
            self._tracker_anchors = len(self._tracker_anchor_stars)
            self._tracker_base = (wcs, base)
            self._tracker_generation = generation
            if base is wcs:
                self._rotation_attempted = None  # S69 (a): on the solution, a new count
        self._tracker.update(green, allow_rotation=self._allow_rotation())
        return TrackedWCS(base, self._tracker)

    def _field_lost(self, params: PhotometryParams) -> bool:
        """No star of the set where the tracked solution places it (S35). Lock held.

        The field moved further than the tracker's search radius since the
        solution, or clouds hide every anchor: apertures there measure blank sky.
        """
        return (
            params.track_apertures and self._tracker is not None and not self._tracker.anchors_used
        )

    @staticmethod
    def _build_live_tracker(green, wcs, tset: TargetSet, params: PhotometryParams, chosen_on=None):
        """``_build_live_tracker`` (1569-1582, with the release branch's S35 and S56).

        Returns the tracker and its anchor stars. Without a comparison bright
        enough to steer, any star of the set seen where the solution places it
        (SNR ≥ 5); never the set's stars unseen, whose noise centroids passed
        for anchors when the field had moved since the solve. The anchors are
        chosen on ``chosen_on`` = (green plane, solution) when given: the frame
        the solution was solved on, where it is exact (S56 as amended on
        2026-11-15); the tracker is placed on ``wcs`` (the solve or its S52 rebase).
        """
        pick_green, pick_wcs = chosen_on if chosen_on is not None else (green, wcs)
        candidates = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        anchors = select_tracking_anchors(
            pick_green, pick_wcs, candidates, params, **set_neighbours(tset)
        )
        if not anchors:
            anchors = select_tracking_anchors(
                pick_green, pick_wcs, list(tset.stars), params, min_snr=5.0
            )
        xy = [wcs.world_to_pixel_deg(s.ra_deg, s.dec_deg) for s in anchors]
        h, w = green.shape
        tracker = ApertureTracker(
            [(float(x), float(y)) for x, y in xy],
            frame_center=(w / 2.0, h / 2.0),
            search_r=max(8.0, 2.0 * params.aperture_px(None)),
        )
        return tracker, list(anchors)

    def _check_lock(self, green, tracked, params: PhotometryParams, frame_seq: int) -> bool:
        """The S48 lock check (release ``_lock_lost``): True when the lock holds.
        Called with the service lock held.

        After a jump larger than the search radius a tracker window may
        centroid a neighbour or noise: the tracker reports that anchor and moves
        every aperture by its offset, and S35 (no anchor at all) does not fire.
        Half the anchors (rounded up) must show a star of SNR ≥ 5 where the
        tracked solution puts them. Clouds that dim the anchors below SNR 5 fail
        it too. It does not catch a wrong plate solution: a new solution rebuilds
        the tracker from the stars seen where it puts them (S50 refuses the wrong
        scale instead).
        """
        stars = self._tracker_anchor_stars
        if not params.track_apertures or self._tracker is None or not stars:
            self._lock_state = None
            return True
        seen = anchors_seen(green, tracked, stars, params, min_snr=LOCK_MIN_SNR)
        needed = max(1, math.ceil(len(stars) / 2))
        self._lock_state = {
            "frame_seq": frame_seq,
            "anchors": len(stars),
            "seen": int(seen),
            "needed": needed,
            "held": seen >= needed,
            # S56: 1 or 2 anchors verify nothing (the anchor that moved the solution).
            "verified": seen >= needed and len(stars) >= LOCK_VERIFY_MIN_ANCHORS,
        }
        return seen >= needed

    def _centred_anchors(self, offsets: dict[str, float] | None) -> int:
        """S69 (b) (release ``_centred_anchors``): :func:`centred_anchors`."""
        return centred_anchors(self._tracker_anchor_stars, self._tracker, offsets)

    def _lock_unverified(
        self,
        params: PhotometryParams,
        tset: TargetSet,
        tracked,
        request: MeasureRequest,
        offsets: dict[str, float] | None = None,
    ) -> bool:
        """The tracker steers on fewer than 3 anchors (S56, release ``_lock_unverified``).

        With n = 1 or 2, ceil(n/2) = 1 anchor must be seen and the anchor whose
        centroid moved the solution is seen by construction. Verified all the same
        (S56 as amended on 2026-11-15) near a fresh solution (:meth:`_fresh_lock`).
        S69 (b): the anchors counted are those centred within 1 px of their aperture.
        Lock held.
        """
        if not (params.track_apertures and self._tracker is not None):
            return False
        if not self._tracker_anchor_stars:
            return False
        if self._centred_anchors(offsets) >= LOCK_VERIFY_MIN_ANCHORS:
            return False
        return not self._fresh_lock(tset, tracked, request)

    def _verified_on_previous_solution(
        self,
        params: PhotometryParams,
        request: MeasureRequest,
        offsets: dict[str, float] | None = None,
    ) -> bool:
        """A run's sub of 1 or 2 anchors verified through the previous sub's solution
        (release ``_verified_on_previous_solution``, S56 as amended on 2026-11-15,
        second set): its own solve is due now, so the next sub is never two subs
        from a solution (one solve per run flagged every other sub of XX Cyg
        2026-08-29 050148Z: 12 of 22). Outside a run a live point follows each solve:
        nothing more is due. S69 (b): the anchors counted are those centred. Lock held."""
        if not (params.track_apertures and self._tracker is not None):
            return False
        if not self._tracker_anchor_stars or request.origin != "sequence":
            return False
        if self._centred_anchors(offsets) >= LOCK_VERIFY_MIN_ANCHORS:
            return False
        return request.solved_seq is not None and request.frame_seq - request.solved_seq == 1

    @staticmethod
    def _fresh_lock(tset: TargetSet, tracked, request: MeasureRequest) -> bool:
        """The frame is measured through a solution of this sub or the previous one
        (``solved_seq`` = ``frame_seq`` or ``frame_seq - 1``), and the tracker moved no
        aperture of the set ``LOCK_FRESH_MAX_SHIFT_PX`` or more from where that
        solution puts it (release ``_fresh_lock``): the largest distance, over the
        set's stars, between the raw and the tracked solution's positions."""
        if request.solved_seq is None or not 0 <= request.frame_seq - request.solved_seq <= 1:
            return False
        shift = 0.0
        for star in tset.stars:
            x0, y0 = request.wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            x1, y1 = tracked.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            d = math.hypot(float(x1) - float(x0), float(y1) - float(y0))
            if not math.isfinite(d):
                return False
            shift = max(shift, d)
        return shift < LOCK_FRESH_MAX_SHIFT_PX

    def _frame_filter(self, request: MeasureRequest) -> str:
        """The measured frame's filter name (S49).

        A sequence sub's read-back FILTER and an opened file's FILTER card as
        they are; a live frame (release ``_live_filter``): the wheel's settled
        slot when it reports one, else the frame's Camera form filter.
        """
        if request.origin in ("sequence", "file"):
            return request.filter_name or ""
        wheel = getattr(self._hub, "wheel", None)
        if wheel is not None and wheel.connected and not wheel.moving and wheel.slot:
            return str(wheel.slot)
        if request.filter_name is not None:
            return request.filter_name
        with self._hub._lock:
            settings = getattr(self._hub, "_capture_settings", None)
            return str(getattr(settings, "filter", "") or "")

    def measure(self, request: MeasureRequest) -> int:
        """``_measure_photometry`` (1604-1667) on one frame; returns the points kept."""
        tset = self._hub.targets.snapshot()
        with self._lock:
            if request.reset_tracker:
                self._tracker = None  # _on_reference_solved (1599-1602)
                self._rebase = None
            if tset.object_name != self._object:
                # The observation changed under a queued frame: never mix objects.
                if self._object is not None or self._curves:
                    self._reset_locked("object_changed")
                self._object = tset.object_name
                self._tracker = None
        if not tset.by_role(ROLE_TARGET):
            self.refresh_status()
            return 0
        if request.epoch is None:
            # An opened FITS without DATE-OBS/EXPTIME: a point stamped "now"
            # would reach the curve, its CSV and the AAVSO export (S4).
            self._hub.log("warning", NO_EPOCH_TEXT, source="photometry", topic="photometry")
            with self._lock:
                self._outcome = ("skipped", "no_epoch", request.frame_seq)
            self.refresh_status()
            return 0
        frame_fwhm = self._frame_fwhm(request)
        token = filter_token(self._frame_filter(request))  # one curve per (star, filter): S49
        # An opened frame's errors use its own e-/ADU (S41), else the live chain.
        egain = request.egain if request.egain is not None else self._hub.targets.egain()
        params = PhotometryParams.from_config(self._hub.config.get, egain=egain)
        green = green_plane(request.raw)
        jd = julian_date(request.epoch)
        t_iso = utc_iso(request.epoch)
        # The mount says where it points now: never the airmass of an opened
        # frame from another night (S34, fixed for 0.5.0).
        pointing = None if request.origin == "file" else self._hub._pointing()
        air = airmass_from_altitude(pointing.alt_deg) if pointing is not None else None
        # Never the 0/0 default: without a site, the airmass is the mount's
        # (or none) and there is no BJD_TDB (X2).
        lat, lon, elev = observing_site(self._hub.config) or (None, None, 0.0)
        with self._lock:
            # The recorder first: a new object resets the series FWHM, which is
            # then frozen on THIS frame (P7; S31: Qt froze it before the reset).
            diag = self._diagnostics(tset, request.run_root)
            if self._phot_fwhm is None and frame_fwhm:
                self._phot_fwhm = frame_fwhm
            fwhm = self._phot_fwhm or DEFAULT_FWHM
            frame_no = self._diag_frame
            self._diag_frame += 1
            tracked = self._wcs_for_frame(
                green, tset, params, request.wcs, request.generation, request.solved_raw
            )
            lost = None
            if self._field_lost(params):
                # No point on blank sky (S35); the service lock, then the hub's.
                self._lock_state = None
                lost = ("field_lost", FIELD_LOST_TEXT)
            elif not self._check_lock(green, tracked, params, request.frame_seq):
                lost = ("lock_lost", LOCK_LOST_TEXT)  # S48
            if lost is not None:
                diag.record("event", frame=frame_no, what="frame_skipped", reason=lost[0])
                self._outcome = ("skipped", lost[0], request.frame_seq)
                self._hub.log("warning", lost[1], source="photometry", topic="photometry")
                self.refresh_status()
                # S48: a re-solve due at once; in a run the sub in hand is solved now.
                field = getattr(self._hub, "field", None)
                if field is not None and hasattr(field, "resolve_due"):
                    field.resolve_due(request.frame_seq, now=request.origin == "sequence")
                return 0
            # S69 (b) (GUARD: the release core): each comparison and check star's
            # centroid against its aperture (release ``_measure_photometry``).
            core = s69_core()
            offsets: dict[str, float] = {}
            if core is not None and tracked is not None:
                offsets = core.centring_offsets(
                    green,
                    tracked,
                    tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK),
                    params,
                    fwhm=fwhm,
                    neighbours=list(tset.stars),
                )
            excluded = core.off_centre(offsets) if core is not None else frozenset()
            due: bool | None = None  # S48/S56/S69: a solve due now (True: in hand too)
            unverified = self._lock_unverified(params, tset, tracked, request, offsets)
            if self._lock_state is not None:
                self._lock_state["verified"] = not unverified  # S56 as amended
            if unverified:
                # S56: points flagged suspect and a solve due at once, away from a fresh
                # solution (release ``_measure_photometry``). S69 (b): the anchors
                # counted are those centred on their apertures.
                n = self._centred_anchors(offsets)
                diag.record("event", frame=frame_no, what="lock_unverified", anchors=n)
                if not self._unverified_logged:
                    self._unverified_logged = True  # once per episode
                    self._hub.log(
                        "warning",
                        LOCK_UNVERIFIED_TEXT.format(n=n, s="s" if n != 1 else ""),
                        source="photometry",
                        topic="photometry",
                    )
                due = request.origin == "sequence"
            else:
                self._unverified_logged = False  # a verified frame ends the episode
                if self._verified_on_previous_solution(params, request, offsets):
                    # S56 (2026-11-15, second set): the sub in hand is solved too, so
                    # the next sub is measured through the previous one's solution.
                    due = True
            rotation = (
                tracked.rotation_deg
                if core is not None and isinstance(tracked, TrackedWCS)
                else 0.0
            )
            if core is not None and core.rotation_resolve_due(rotation, self._rotation_attempted):
                # S69 (a): the field turned more than 2° since the solution: a solve is
                # due (once per 2° until one lands, so a failing solver never loops).
                self._rotation_attempted = rotation
                diag.record(
                    "event", frame=frame_no, what="rotation_resolve_due", rotation_deg=rotation
                )
                if due is None:
                    due = request.origin == "sequence"
            if due is not None:
                field = getattr(self._hub, "field", None)
                if field is not None and hasattr(field, "resolve_due"):
                    field.resolve_due(request.frame_seq, now=due)
            if excluded:
                diag.record("event", frame=frame_no, what="off_centre", stars=len(excluded))
                if not self._off_centre_logged:
                    self._off_centre_logged = True  # once per episode
                    n_off = len(excluded)
                    self._hub.log(
                        "warning",
                        OFF_CENTRE_TEXT.format(n=n_off, s="s" if n_off != 1 else ""),
                        source="photometry",
                        topic="photometry",
                    )
            else:
                self._off_centre_logged = False
            if self._primary_filter is None:
                self._primary_filter = token
            bundled_iers_only()  # BJD_TDB offline (S37)

            def on_star(s, phot, x, y):
                if core is None:
                    diag.star(frame_no, s, phot, x, y)
                    return
                offset = offsets.get(s.key())
                diag.star(
                    frame_no,
                    s,
                    phot,
                    x,
                    y,
                    centroid_offset_px=(
                        offset if offset is not None and math.isfinite(offset) else None
                    ),
                    off_centre=True if s.key() in excluded else None,
                )

            exclude = {"exclude": excluded} if core is not None else {}
            results = measure_frame(
                green, tracked, tset, params, fwhm=fwhm, on_star=on_star, **exclude
            )
            tracker = self._tracker if params.track_apertures else None
            diag.record("frame", frame=frame_no, jd_utc=jd, airmass=air, fwhm=fwhm)
            kept = 0
            target_point: dict[str, Any] | None = None
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
                # A point is worth keeping when either product exists (S18).
                has_mag = res.diff is not None and res.diff.mag is not None
                has_ratio = res.relative is not None and res.relative.flux_ratio is not None
                if not (has_mag or has_ratio):
                    continue
                # S69 (b): an off-centre comparison or check star's own point is suspect.
                flagged = unverified or bool(excluded and res.star.key() in excluded)
                point = self._emit_live_point(
                    tset, res, jd, air, fwhm, (lat, lon, elev), request, t_iso, token, flagged
                )
                kept += 1
                if res.star.role == ROLE_TARGET and target_point is None:
                    target_point = {
                        "key": curve_key(res.star, token),
                        "mag": _num(point.mag),
                        "mag_err": _num(point.mag_err),
                        "bjd_tdb": _num(point.bjd_tdb),
                    }
            self._write_live_quality_report(tset, request, token)
            self._frames += 1
            self._points += kept
            r_ap = params.aperture_px(fwhm)
            self._last = {
                "frame_seq": request.frame_seq,
                "t": t_iso,
                "jd_utc": jd,
                "bjd_tdb": target_point["bjd_tdb"] if target_point is not None else None,
                "points": kept,
                "target": target_point,
                "filter": token,
                "aperture_px": r_ap,
                "fwhm_px": fwhm,
                "anchors": tracker.anchors_used if tracker is not None else None,
                "tracking": (
                    {
                        "rot_deg": tracker.transform.rotation_deg,
                        "dx": tracker.transform.tx,
                        "dy": tracker.transform.ty,
                        "residual_px": tracker.residual_px,
                    }
                    if tracker is not None
                    else None
                ),
            }
            self._measured_keys = frozenset(s.key() for s in tset.stars)
            if kept:
                self._outcome = ("measured", None, request.frame_seq)
            elif not tset.by_role(ROLE_COMPARISON):
                self._outcome = ("skipped", "no_comparison", request.frame_seq)
            else:
                self._outcome = ("skipped", "no_point", request.frame_seq)
        self.refresh_status()
        return kept

    def _emit_live_point(
        self,
        tset,
        res,
        jd,
        air,
        fwhm,
        site,
        request,
        t_iso,
        token: str = "clear",
        unverified: bool = False,
    ) -> LcPoint:
        """``_emit_live_point`` (1700-1765): the point, its (star, filter) curve (S49),
        its CSV, its event. ``unverified``: the frame's lock rests on fewer than 3
        anchors, the point is flagged ``suspect`` (S56)."""
        lat, lon, elev = site
        bjd = (
            bjd_tdb(jd, res.star.ra_deg, res.star.dec_deg, float(lat), float(lon), float(elev))
            if lat is not None and lon is not None
            else None
        )
        # The target's own altitude at the midpoint, not the mount's (1712-1719).
        if lat is not None and lon is not None:
            target_air = airmass_at(jd, res.star.ra_deg, res.star.dec_deg, float(lat), float(lon))
            if target_air is not None:
                air = target_air
        point = LcPoint(
            jd_utc=jd,
            mag=res.diff.mag if res.diff and res.diff.mag is not None else float("nan"),
            mag_err=res.diff.mag_err if res.diff and res.diff.mag_err is not None else float("nan"),
            bjd_tdb=bjd,
            airmass=air,
            fwhm=fwhm,
            sky_adu=res.phot.sky_adu if res.phot else None,
            comps_used=res.diff.comps_used if res.diff else 0,
            relative_comps_used=res.relative.comps_used if res.relative else 0,
            saturated=bool(res.phot and res.phot.saturated),
            # S71: the comparison carrying the zero point disagrees with the others
            # (release DiffResult.suspect, read with getattr: GUARD).
            suspect=bool(res.phot and res.phot.suspect)
            or unverified
            or bool(getattr(res.diff, "suspect", False)),
            formal_mag_err=(
                res.diff.formal_mag_err or res.diff.mag_err
                if res.diff and res.diff.mag_err is not None
                else None
            ),
            relative_flux=res.relative.flux_ratio if res.relative else None,
            relative_flux_err=res.relative.flux_ratio_err if res.relative else None,
        )
        key = curve_key(res.star, token)
        lc = self._curves.get(key)
        if lc is None or lc.role != res.star.role:
            # A star whose role changed starts a new curve (S33, fixed for 0.5.0:
            # Qt appended a check's points to its leave-one-out comparison curve).
            if lc is not None:
                self._meta.pop(key, None)
                self._preview_csv.pop(key, None)  # the old curve keeps its own file (S40)
                self._publish_reset("role_changed")
            lc = LightCurve(
                auid=res.star.auid or "", name=res.star.display_name, role=res.star.role
            )
            self._curves[key] = lc
        meta = self._meta.setdefault(key, {"points": []})
        meta["star_key"] = res.star.key()
        meta["mags"] = dict(res.star.mags)
        meta["filter"] = token
        lc.append(point)
        zp = res.diff.zero_point if res.diff is not None else None
        zp_rms = res.diff.zp_rms if res.diff is not None else None
        meta["points"].append((request.frame_seq, t_iso, zp, zp_rms))
        self._apply_systematic_floor(lc)
        path = self._csv_path(tset, res.star, request.run_root, key, token)
        self._csv[key] = path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_csv_atomic(lc, path)
        except OSError as exc:
            self._hub.log(
                "warning", f"photometry.csv: {exc}", source="photometry", topic="photometry"
            )
        self._seq += 1
        floor = point.sigma_syst
        event = {
            "type": "photometry_point",
            "seq": self._seq,
            "revision": self._revision,
            "frame_seq": request.frame_seq,
            "key": key,
            "star_key": res.star.key(),
            "filter": token,  # S49: the curve's filter token
            "role": lc.role,
            "name": lc.name,
            "auid": lc.auid or None,
            "index": len(lc.points) - 1,
            "point": point_record(point, request.frame_seq, t_iso, zp, zp_rms),
            # The run-level floor: every earlier error bar is hypot(formal, it),
            # recomputed by the client (S19), never resent as a column.
            "sigma_syst": _num(floor),
        }
        self._hub.bus.publish("photometry_point", None, event)
        return point

    def _apply_systematic_floor(self, curve: LightCurve) -> bool:
        """``_apply_systematic_floor`` (1767-1795)."""
        manual = self._cfg("photometry.systematic_floor_mag", None)
        floor = estimate_systematic_floor(
            [
                (point.jd_utc, point.mag, point.formal_mag_err or point.mag_err)
                for point in curve.points
                if math.isfinite(point.mag) and math.isfinite(point.formal_mag_err or point.mag_err)
            ],
            manual_floor=manual,
        )
        if floor is None:
            return False
        changed = False
        for point in curve.points:
            if not math.isfinite(point.mag):
                continue
            formal = point.formal_mag_err if point.formal_mag_err is not None else point.mag_err
            final = apply_systematic_floor(formal, floor)
            if point.mag_err != final or point.sigma_syst != floor.sigma_systematic:
                point.mag_err = final
                point.sigma_syst = floor.sigma_systematic
                changed = True
        return changed

    def _write_live_quality_report(
        self, tset: TargetSet, request: MeasureRequest, token: str = "clear"
    ) -> None:
        """``_write_live_quality_report`` (1669-1698): every frame (S17), the comparisons
        of the measured frame's filter only (S49): the run's first filter in
        ``photometry_quality.json``, another in ``photometry_quality_<filter>.json``,
        each naming its filter in a ``filter`` key (S57). Lock held."""
        by_star = {
            key.rpartition("@")[0]: curve
            for key, curve in self._curves.items()
            if self._meta.get(key, {}).get("filter") == token
        }
        report = comparison_quality_report(
            tset,
            by_star,
            min_points=int(self._cfg("photometry.comparison_validation_min_points", 10)),
            max_scatter_mag=float(
                self._cfg("photometry.comparison_validation_max_scatter_mag", 0.10)
            ),
            max_formal_error_mag=float(
                self._cfg("photometry.comparison_validation_max_formal_error_mag", 0.10)
            ),
        )
        self._quality_report = report
        self._quality_filter = token
        self._publish_quality(request.frame_seq)
        if request.run_root is None:
            return
        name = (
            "photometry_quality.json"
            if token == self._primary_filter
            else f"photometry_quality_{token}.json"
        )
        try:
            # S57: the file says which filter it vets (additive; written here, so the
            # server needs no core change: release save_comparison_quality_report's
            # filter_token writes the same key, last).
            save_comparison_quality_report(request.run_root / name, {**report, "filter": token})
        except OSError as exc:
            self._hub.log(
                "warning",
                f"Save photometry quality: {exc}",
                source="photometry",
                topic="photometry",
            )


__all__ = [
    "MeasureRequest",
    "PhotometryService",
    "curve_key",
    "filter_token",
    "point_record",
    "star_curve_key",
]
