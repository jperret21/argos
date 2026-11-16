"""AcquisitionEngine — camera ownership + capture/solve/photometry workers.

Extracted from the ImagingPage (WS5). A UI-thread ``QObject`` (never
``moveToThread`` it) that owns everything that *uses* the devices:

- the :class:`CameraService` ownership state machine (WS3) and its preview
  hooks;
- the LivePreview / Sequence / Autofocus workers;
- the :class:`AstrometryController` (live plate-solve lifecycle) and the
  VSX/VSP catalog cache;
- the persistent target set and the live photometry state (light curves,
  per-target CSVs, FITS saves).

The ImagingPage is a view: it forwards dock intents into these methods and
renders the typed signals (``frame_ready`` carries a frozen
:class:`LiveFrame`, ``photometry_point`` a :class:`PhotometryPoint`, …).
Capture parameters are read through injected providers
(:meth:`set_providers`) so the engine never touches a widget.

Coordination with the :class:`DeviceSession` happens through its
``camera_will_disconnect`` / ``focuser_will_disconnect`` hooks — the engine
stops using a device *before* the session drops the handle.
"""

from __future__ import annotations

import copy

import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

from argos import SOFTWARE_ID
from argos.core.catalog.photometry import ComparisonQuality, auto_comparison_stars
from argos.core.catalog.targets import (
    ROLE_CHECK,
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    TargetStar,
)
from argos.core.config import Config, observing_site
from argos.core.hardware import egain as camera_egain
from argos.core.imaging.astrometry_session import field_geometry
from argos.core.imaging.fits_writer import FITSWriter, FrameContext, filter_token
from argos.core.imaging.green import green_plane
from argos.core.imaging.metrics import detect_stars, frame_metrics, measure_star_at
from argos.core.imaging.platesolve import angular_separation_deg
from argos.core.imaging.sequencer import DARK_FILTER_NAME
from argos.core.imaging.sky_geometry import (
    SITE_FIT_MAX_RMS_DEG,
    SiteFit,
    angle_between_directions,
    horizontal_at,
)
from argos.core.photometry.airmass import (
    airmass_at,
    airmass_from_altitude,
    bjd_tdb,
    julian_date,
)
from argos.core.photometry.aperture import measure_aperture
from argos.core.photometry.lightcurve import (
    LcPoint,
    LightCurve,
    curve_key,
    curves_of_filter,
    run_curve_csv_name,
    series_label,
)
from argos.core.photometry.params import (
    DEFAULT_FWHM,
    PhotometryParams,
    frame_egain,
    frame_scintillation_inputs,
    measure_frame,
)
from argos.core.photometry.quality import comparison_quality_report, save_comparison_quality_report
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
from argos.core.session.device_session import DeviceSession
from argos.core.session.diagnostics import SessionDiagnostics
from argos.core.session.review import FROZEN_POINTING_S, flag_no_detection
from argos.core.session.types import LiveFrame, PhotometryPoint
from argos.workers.astrometry_controller import AstrometryController
from argos.workers.autofocus_worker import AutofocusWorker
from argos.workers.camera_service import CameraService, CameraState
from argos.workers.catalog_worker import CatalogRequest, CatalogWorker
from argos.workers.exposure_worker import LivePreviewWorker
from argos.workers.sequence_worker import SequenceWorker

logger = logging.getLogger(__name__)

_SOFTWARE = SOFTWARE_ID
#: S48: an anchor is seen when its aperture at the tracked position has this SNR
#: (S35's "seen" threshold); the lock holds when half the anchors are seen (S43).
_LOCK_MIN_SNR = 5.0
#: S56: with fewer anchors, ceil(n/2) is met by the very anchor that moved the
#: solution: the lock is unverified, its points flagged suspect, a re-solve due...
_LOCK_VERIFY_MIN_ANCHORS = 3
#: ...unless the frame is measured through a solution of this sub or the previous one
#: and the tracker moved no aperture of the set this much (green px) or more from where
#: that solution puts it. S56 as amended on 2026-11-16: between the largest motion of the
#: field between two subs that the converged tracker (S69) sees (4.2-7.5 px on XX Cyg
#: 2026-09-07, 5.1 px on 2026-08-29) and what a neighbour locked after a jump or a stale
#: rebuild (S52) moved them (22-36 px). It was 2 px, tuned on the lagging tracker.
_LOCK_FRESH_MAX_SHIFT_PX = 10.0
#: S54: 3 consecutive solutions refused by the anchor check that agree with each
#: other within this many green px (where each puts the newest one's frame centre)
#: are a re-pointing the mount did not report: the third is accepted. The owner's
#: runs' 3 consecutive good solves span at most 10.4 px (RR Lyr 2026-09-25: 4.3 px
#: of drift per sub), apart from the subs across a real jump (22.7 and 145 px).
_REPOINT_SOLVES = 3
_REPOINT_AGREE_PX = 20.0


def lock_unverified_text(n: int) -> str:
    """S56's Activity line (once per episode)."""
    return (
        f"Photometry: only {n} anchor star{'s' if n != 1 else ''} steer the apertures — the"
        " lock cannot be verified; points are flagged suspect while fewer than 3 anchor"
        " stars steer the apertures (except within 10 px of a solution of this sub or the"
        " previous one). Re-solving."
    )


def off_centre_text(n: int) -> str:
    """S69 (b)'s Activity line (once per episode)."""
    return (
        f"Photometry: {n} comparison/check star{'s' if n != 1 else ''} more than 1 px from"
        " the aperture centre — left out of the frame's ensemble, their points flagged"
        " suspect."
    )


def solutions_span_px(solutions, green_shape) -> float:
    """S54: the largest distance (green px) between where the solutions put the newest
    one's frame centre: how well consecutive solutions agree in position."""
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


def repoint_text(seen: int, anchors: int, span_px: float) -> str:
    """S54's Activity line when 3 refused solutions agree: a re-pointing is accepted."""
    return (
        f"Solve: {_REPOINT_SOLVES} consecutive solutions agree within {span_px:.1f} px on a"
        f" field where the anchor stars are not ({seen} of {anchors} seen) — accepted as a"
        " re-pointing the mount did not report"
    )


def _is_light_frame(frame_type: str) -> bool:
    """Shutter semantics for a CameraDock frame type — darks/bias expose with
    ``light=False`` so single shots are honest about what they captured."""
    return frame_type not in ("Dark Frame", "Bias Frame")


def _fits_utc(value) -> datetime | None:
    """A FITS ISO date-time keyword as an aware UTC datetime, else None.

    FITS dates are UTC; a value without a time part (old ``DATE-OBS`` with a
    separate ``TIME-OBS``) is refused rather than read as midnight.
    """
    text = str(value or "").strip()
    if "T" not in text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _gain_of(settings, default: int | None) -> int | None:
    """The integer gain setting a frame's settings or record carries, else ``default``."""
    gain = getattr(settings, "gain", None)
    if isinstance(gain, bool) or not isinstance(gain, (int, float)) or gain != gain:
        return default
    return int(gain)


def _new_preview_csv(
    folder: Path, obj: str, tag: str, now: datetime, taken=(), token: str = ""
) -> Path:
    """``<folder>/<object>_<YYYYMMDDTHHMMSSZ>_<filter>_<star>.csv``, a file not yet used.

    The start time and the filter token (S49) sit between object and star so
    that Review still finds the object's set (``<object>.json``, the longest
    stem prefix) and the star (the stem's AUID or name suffix). Two curves
    started in the same second take ``-2``, ``-3``… on the time.
    """
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    count = 1
    while True:
        mark = stamp if count == 1 else f"{stamp}-{count}"
        if token:
            mark = f"{mark}_{token}"
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{obj}_{mark}_{tag}")
        path = folder / f"{safe}.csv"
        if path not in taken and not path.exists():
            return path
        count += 1


def _late_date_avg(header) -> bool:
    """True for a frame written by Argos before 0.5.0, whose DATE-AVG may be late.

    Up to 0.4.x a sequence frame's clock stopped after the image download, so
    its DATE-AVG is late by half the download time (S36: +5.2 s median, 16.6 s
    at most on a 195-frame run); its DATE-OBS is the exposure start. Argos
    writes ``Argos v<version>`` in SOFTWARE (plain ``Argos`` by default).
    """
    text = str(header.get("SOFTWARE") or header.get("SWCREATE") or "").strip()
    match = re.fullmatch(r"Argos(?: v(\d+)\.(\d+)\S*)?", text)
    if match is None:
        return False
    if match.group(1) is None:
        return True
    return (int(match.group(1)), int(match.group(2))) < (0, 5)


def fits_exposure_mid(header) -> datetime | None:
    """Exposure midpoint (UTC) of a saved frame, from its header, or None.

    ``DATE-AVG`` when present, else ``DATE-OBS`` + ``EXPTIME``/2 (``EXPOSURE``
    accepted). ``DATE-OBS`` is the exposure start: Argos writes it so, and so
    does most capture software, but a third-party file may differ. A frame
    written by Argos before 0.5.0 is always dated by ``DATE-OBS`` +
    ``EXPTIME``/2 (see :func:`_late_date_avg`), as its live point was. Without
    a usable date and exposure the epoch is unknown (None), never guessed.
    """
    mid = None if _late_date_avg(header) else _fits_utc(header.get("DATE-AVG"))
    if mid is not None:
        return mid
    start = _fits_utc(header.get("DATE-OBS"))
    exposure = header.get("EXPTIME", header.get("EXPOSURE"))
    try:
        exposure_s = float(exposure)
    except (TypeError, ValueError):
        return None
    if start is None or not math.isfinite(exposure_s) or exposure_s < 0:
        return None
    return start + timedelta(seconds=exposure_s / 2.0)


def _raw_adu(data) -> np.ndarray:
    """An opened frame as the sensor's 16-bit ADU, or ``ValueError``.

    The live pipeline (photometry gain, saturation flags, solve) assumes raw
    camera counts. A plain ``uint16`` cast wraps what it cannot hold: a
    negative value (a dark-subtracted or calibrated frame) becomes about
    65535 and 70000 becomes 4464, so the sky and aperture sums are wrong
    while the frame still solves. Integer values in 0..65535 are accepted,
    whatever the stored type; anything else is refused.
    """
    arr = np.asarray(data)
    if arr.dtype.kind not in "uif":
        raise ValueError(f"unsupported pixel type {arr.dtype}")
    if arr.dtype.kind == "f" and not (
        np.isfinite(arr).all() and np.array_equal(arr, np.floor(arr))
    ):
        raise ValueError(
            "floating-point pixels (a calibrated or stacked frame?) are not raw "
            "16-bit camera counts — open the raw .fit frame instead"
        )
    low, high = arr.min(), arr.max()
    if low < 0 or high > 65535:
        raise ValueError(
            f"pixel values {low:g} to {high:g} do not fit raw 16-bit camera counts "
            "(0 to 65535) — open the raw .fit frame instead"
        )
    return np.ascontiguousarray(arr, dtype=np.uint16)


def _wheel_filter_name(wheel, requested: str, log_emit) -> str:
    """Filter the wheel actually sits on, for a Take-shot header.

    Same policy as ``SequenceWorker._read_back_filter``: without a wheel the
    form's name stands; an unreadable or still-turning wheel keeps it with a
    warning; a readable wheel that differs wins over the form. Runs off the
    UI thread (it is a device read).
    """
    if wheel is None:
        return requested
    try:
        actual = wheel.position_name()
    except Exception as exc:
        log_emit(
            "WARN", f"Filter read-back failed ({exc}) — FITS FILTER is the form's '{requested}'"
        )
        return requested
    if not actual or actual == "Moving…":
        log_emit("WARN", f"Filter wheel still moving — FITS FILTER is the form's '{requested}'")
        return requested
    if actual.lower() != requested.lower():
        log_emit(
            "WARN",
            f"The wheel is on '{actual}', not on the form's '{requested}' — "
            f"FITS FILTER records '{actual}'.",
        )
    return actual


class AcquisitionEngine(QObject):
    """Owns the capture workers and the solve/photometry session state."""

    # Camera ownership + capture visibility.
    camera_state_changed = pyqtSignal(object)  # CameraState
    device_state_changed = pyqtSignal(str, str, str)  # camera busy/connected
    frame_ready = pyqtSignal(object)  # LiveFrame
    sequence_running = pyqtSignal(bool)
    sequence_paused = pyqtSignal(bool)  # holding at a frame boundary
    sequence_progress = pyqtSignal(str, int, int, float)  # object, done, total, eta_s
    sequence_step = pyqtSignal(int, object)  # step index, FrameSpec
    frame_saved = pyqtSignal(str, object)  # path, FrameRecord | None
    autofocus_step = pyqtSignal(int, int, int, object)  # step, total, pos, hfd|None
    autofocus_best = pyqtSignal(int, object)  # best position, best hfd|None
    autofocus_state = pyqtSignal(bool)  # sweep running / stopped

    # Catalog / targets / photometry.
    catalog_ready = pyqtSignal(object)  # CatalogResult (cached — re-project now)
    targets_changed = pyqtSignal(object)  # TargetSet
    photometry_measuring = pyqtSignal()  # a measurement pass starts (temp sample)
    photometry_point = pyqtSignal(object)  # PhotometryPoint
    curves_changed = pyqtSignal()  # the curve STORE was replaced/cleared — re-render
    comparison_quality_updated = pyqtSignal(object)  # leave-one-out report
    apertures_tracked = pyqtSignal()  # live tracker refit — re-project markers

    # Logging / status relays.
    log_message = pyqtSignal(str, str)  # level, message
    action_changed = pyqtSignal(str)

    def __init__(
        self, config: Config, session: DeviceSession, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._session = session

        # Widget-free capture-parameter access, injected by the page.
        self._params = None  # Callable[[], CaptureParams]
        self._preview_scale = None  # Callable[[], int]

        # Single camera-ownership state machine (WS3): every "may I use the
        # camera?" decision goes through acquire/release on this service —
        # the workers keep their loops, the service owns WHO runs.
        self._camera_service = CameraService(self)
        self._camera_service.set_preview_hooks(self._start_preview, self._stop_preview)
        self._camera_service.state_changed.connect(self.camera_state_changed)
        self._camera_service.acquire_refused.connect(self._on_acquire_refused)
        self._camera_service.preempted.connect(self._on_preempted)

        self._preview: LivePreviewWorker | None = None
        self._autofocus: AutofocusWorker | None = None
        # A stopped sweep still driving the focuser back to its start.
        self._af_returning = False
        self._sequence: SequenceWorker | None = None
        self._seq_object = ""  # object name of the running sequence (for the strip)
        self._seq_has_lights = False  # the running plan shoots Light frames
        self._on_complete = "Nothing"  # end-of-sequence mount action (plan option)

        # Single-shot capture: number of upcoming preview frames to save.
        self._capture_pending = 0
        # Live loop: True while the user has explicitly started Live (a single
        # Take-shot also spins the preview worker, but only transiently).
        self._live_requested = False

        # Authoritative last frame for solve/photometry. ``decimated`` marks a
        # half-quality preview whose plate scale would poison a solve.
        self._last_raw: np.ndarray | None = None
        #: S56: the frame before it (a solution of this sub or the previous one is fresh).
        self._prev_raw: np.ndarray | None = None
        self._last_raw_decimated = False
        #: The last frame came from Open FITS (another night): no mount airmass (S34).
        self._last_raw_from_file = False
        #: e-/ADU of that opened frame (its own gain, see ``frame_egain``); None → live chain.
        self._file_egain: float | None = None
        #: That opened frame's exposure, airmass and site height (S74's scintillation).
        self._file_scintillation: dict = {}
        #: The exposure (s) of the frame in hand, live or sequence (S74).
        self._last_exposure_s: float | None = None
        #: The gain setting of the frame in hand, live or sequence: its e-/ADU (S83).
        self._last_gain: int | None = None
        self._green_shape: tuple[int, int] | None = None  # of the last processed frame
        self._last_metrics = None  # last displayed FrameMetrics (FITS QA uses the saved array)
        self._last_fwhm: float | None = None  # mean detected-star FWHM (green px)
        self._last_exposure_mid: datetime | None = None  # exposure midpoint (UTC)

        # Live plate-solve lifecycle + auto-solve policy (§6, shared pipeline).
        self._astrometry = AstrometryController(self._cfg, self)
        self._astrometry.failed.connect(self._on_solve_failed)
        self._astrometry.state.connect(self.action_changed)
        self._astrometry.solved.connect(self._on_reference_solved)
        self._astrometry.notice.connect(lambda text: self.log_message.emit("WARN", text))
        # S54: a new solution must show the previous anchors' stars where it puts them.
        self._astrometry.set_solution_check(self._solution_refusal)

        # §6 P1: live catalog (VSX/VSP) + persistent target set.
        self._catalog_worker: CatalogWorker | None = None
        self._variables: list = []
        self._comparisons: list = []
        self._comparison_quality_report: dict | None = None
        self._field_stars: list = []
        self._named_objects: list = []
        self._exoplanet_hosts: list = []
        self._catalog_centre: tuple[float, float] | None = None  # (ra_deg, dec_deg)
        self._target_set: TargetSet | None = None

        # §6 P4: live photometry preview state.
        self._lightcurves: dict[str, LightCurve] = {}  # key → per-target curve
        # Outside a run, the CSV each live curve was given when it started: a
        # new curve (object change, role change, restart) gets a new file and
        # never rewrites an earlier one.
        self._preview_csvs: dict[str, Path] = {}
        # S49: the filter of the frame in hand (sequence sub, live frame, opened
        # FITS) and the first filter measured since the store was cleared (its
        # vetting report keeps the name photometry_quality.json).
        self._last_filter = ""
        self._primary_filter: str | None = None
        self._measured_filter = "clear"  # the token of the frame being measured
        # Set when a frame's uncertainty floor changed earlier points: the
        # store is re-rendered once at the end of that frame, not per star.
        self._curves_dirty = False

        # P11 flight recorder for the live measurement path — created lazily
        # on the first measured frame, re-created when the object changes.
        self._diag: SessionDiagnostics | None = None
        self._diag_object: str | None = None
        #: The run folder the recorder writes in (None: the live one, S45).
        self._diag_root: Path | None = None
        self._diag_frame = 0

        # P7: one aperture radius per series — the FWHM is frozen on the first
        # measured frame and only re-sampled after a refocus or object change,
        # so the aperture size doesn't inject correlated variance into the curve.
        self._phot_fwhm: float | None = None

        # W1: live aperture tracker — rigid rotation/drift correction between
        # solves, so apertures and catalog markers stay on the stars during an
        # alt-az sequence. Rebuilt on a fresh solve or a target-set change.
        self._tracker: ApertureTracker | None = None
        self._tracker_anchor_stars: list = []  # the set's stars the tracker steers on (S48)
        # (raw solve, tracked solution frozen at a set change): what a tracker
        # rebuilt between two solves builds on (S52).
        self._rebase: tuple | None = None
        #: S56: the current unverified-lock episode was logged (once per episode: until
        #: a verified frame, a slew or invalidation, or a set change).
        self._unverified_logged = False
        #: S69 (a): the tracked rotation at which the last re-solve for rotation was
        #: made due (None: none since the solution); (b): the off-centre episode logged.
        self._rotation_attempted: float | None = None
        self._off_centre_logged = False
        #: S78: the mount's pointings (RA/Dec, altitude, azimuth) of the measured frames,
        #: and the site fitted to them: every star's airmass is computed for it. The last
        #: pointing added, since when it repeats (X1: frozen after 60 s), and whether the
        #: mount's last pointing is frozen.
        self._site_fit = SiteFit()
        self._mount_key: tuple | None = None
        self._mount_since: float | None = None
        self._mount_frozen = False
        #: S54: the consecutive solutions refused by the anchor check (their WCS).
        self._repoint_refused: list = []
        #: S59: the current solution is an opened FITS's (its anchors never vet a
        #: camera frame's solution).
        self._solution_from_file = False

        # Last sequence directory (for the photometry setup window).
        self._last_sequence_dir: Path | None = None
        self._active_run_root: Path | None = None

        # Stop using a device *before* the session drops its handle.
        session.camera_will_disconnect.connect(self._on_camera_will_disconnect)
        session.focuser_will_disconnect.connect(self.stop_autofocus)

    # ------------------------------------------------------------------
    # Wiring / properties
    # ------------------------------------------------------------------

    def set_providers(self, params, preview_scale) -> None:
        """Inject the capture-parameter providers (the CameraDock's ``params``
        and ``preview_scale`` callables) — the engine never reads widgets."""
        self._params = params
        self._preview_scale = preview_scale

    @property
    def camera_service(self) -> CameraService:
        """The ownership state machine (widgets may subscribe to state_changed)."""
        return self._camera_service

    @property
    def camera_state(self) -> CameraState:
        """Current camera owner — the value widgets base enable/disable on."""
        return self._camera_service.state

    @property
    def astrometry(self) -> AstrometryController:
        return self._astrometry

    @property
    def variables(self) -> list:
        """Cached VSX variables for the current field."""
        return self._variables

    @property
    def comparisons(self) -> list:
        """Cached VSP comparison stars for the current field."""
        return self._comparisons

    @property
    def comparison_quality_report(self) -> dict | None:
        """Latest in-memory leave-one-out diagnostic for the live ensemble."""
        return self._comparison_quality_report

    @property
    def field_stars(self) -> list:
        """Cached named Gaia DR3 sources for the current solved field."""
        return self._field_stars

    @property
    def named_objects(self) -> list:
        """Cached SIMBAD names/types for the current solved field."""
        return self._named_objects

    @property
    def exoplanet_hosts(self) -> list:
        """Cached NASA confirmed exoplanet hosts for the current solved field."""
        return self._exoplanet_hosts

    @property
    def lightcurves(self) -> dict[str, LightCurve]:
        return self._lightcurves

    def adopt_curves(self, curves: dict[str, LightCurve]) -> None:
        """Fold externally measured curves (the batch re-run) into THE store.

        Matching keys are replaced — a batch re-measurement of a star is
        canonical over its live preview points — and every display surface
        re-renders off the one dict via ``curves_changed``, so the dock and
        the window can never disagree again.
        """
        self._lightcurves.update(curves)
        for key in curves:
            self._preview_csvs.pop(key, None)  # a replaced curve never rewrites its file
        self.curves_changed.emit()

    def clear_lightcurves(self) -> None:
        """Drop the session's curve store (object change). CSVs stay on disk."""
        self._lightcurves.clear()
        self._preview_csvs.clear()
        self._primary_filter = None
        self._comparison_quality_report = None
        self.comparison_quality_updated.emit({})
        self.curves_changed.emit()

    @property
    def last_sequence_dir(self) -> Path | None:
        return self._last_sequence_dir

    @property
    def last_raw(self) -> np.ndarray | None:
        return self._last_raw

    @property
    def last_raw_decimated(self) -> bool:
        return self._last_raw_decimated

    def _cfg(self, key: str, default):
        value = self._config.get(key, default)
        return default if value is None else value

    @pyqtSlot(str)
    def _on_acquire_refused(self, reason: str) -> None:
        self.log_message.emit("WARN", reason)

    @pyqtSlot(str)
    def _on_preempted(self, note: str) -> None:
        self.log_message.emit("INFO", note)

    def camera_owner(self) -> str | None:
        """Name of the run that owns the camera right now, or ``None``.

        Live/single previews don't block parameter changes — the next loop
        iteration picks them up — so only the exclusive runs are named.
        """
        state = self._camera_service.state
        if state is CameraState.SEQUENCE:
            return "Sequence"
        if state is CameraState.AUTOFOCUS:
            return "Autofocus"
        return None

    # ------------------------------------------------------------------
    # Single shot + live loop
    # ------------------------------------------------------------------

    def take_shot(self) -> None:
        if not self._session.camera:
            self.log_message.emit("WARN", "Camera not connected.")
            return
        if not self._dark_shot_allowed(self._params()):
            return
        if self._camera_service.state is CameraState.LIVE:
            # The live loop already owns the camera — just tag its next frame
            # for saving; no ownership change.
            self._capture_pending = 1
            self.log_message.emit("CMD", "Take shot — saving next frame…")
            return
        if not self._camera_service.acquire(CameraState.SINGLE):
            return  # refused (sequence/autofocus owns the camera) — reason logged
        self._capture_pending = 1
        self.log_message.emit("CMD", "Take shot — saving next frame…")

    def _dark_shot_allowed(self, params) -> bool:
        """Refuse a Dark/Bias shot unless the wheel's opaque slot is selected.

        The Seestar has no shutter: ``light=False`` does not close anything,
        and the wheel's Dark slot is the only way to block the light (field
        bug 2026-07-11, the same rule as ``FrameSpec.wheel_filter``). Without
        that slot the frame is a light frame labelled IMAGETYP=Dark, and a
        master dark built from it corrupts every calibrated science frame.
        The check reads the Camera form's filter (the wheel is moved from
        there) and the slot the wheel last reported it settled on: the form
        shows the new filter as soon as it is picked, while the wheel still
        turns. The wheel is not moved automatically here.
        """
        if _is_light_frame(params.frame_type):
            return True
        if not self._wheel_can_block_light():
            self.log_message.emit(
                "WARN",
                f"{params.frame_type}: no filter wheel to block the light — the frame is "
                "only dark if the telescope is covered.",
            )
            return True
        if params.filter_name.strip().lower() != DARK_FILTER_NAME.lower():
            self.log_message.emit(
                "WARN",
                f"{params.frame_type} shot refused: the wheel is on '{params.filter_name}'. "
                f"Select Filter '{DARK_FILTER_NAME}' first (the Seestar has no shutter).",
            )
            return False
        problem = self._wheel_not_on_dark()
        if problem:
            self.log_message.emit("WARN", f"{params.frame_type} shot refused: {problem}")
            return False
        return True

    def _wheel_can_block_light(self) -> bool:
        """A wheel is connected and its profile has an opaque Dark slot."""
        has_dark_slot = DeviceSession.filter_position_for(DARK_FILTER_NAME) is not None
        return self._session.filterwheel is not None and has_dark_slot

    def _wheel_not_on_dark(self) -> str | None:
        """Why the wheel cannot be trusted to sit on its Dark slot, or ``None``."""
        session = self._session
        if session.filter_moving:
            return (
                f"the filter wheel is still turning. Wait until it has settled on "
                f"'{DARK_FILTER_NAME}' (the Seestar has no shutter)."
            )
        slot = session.filter_slot
        if slot is None:
            return (
                f"the filter wheel's position is unknown. Select Filter "
                f"'{DARK_FILTER_NAME}' again and wait for the wheel to settle."
            )
        if slot.strip().lower() != DARK_FILTER_NAME.lower():
            return f"the filter wheel reports '{slot}', not '{DARK_FILTER_NAME}'."
        return None

    def _wheel_moved_during(self, start_dt) -> bool:
        """The wheel turned, or is turning, since this exposure started.

        Moves made from the Camera form only (a sequence, which moves the
        wheel itself, owns the camera: no Take shot then).
        """
        session = self._session
        if session.filterwheel is None:
            return False
        if session.filter_moving:
            return True
        settled = session.filter_settled_at
        try:
            return settled is not None and start_dt is not None and settled > start_dt
        except TypeError:  # a naive start time: cannot compare, assume moved
            return True

    def start_live(self) -> None:
        if not self._session.camera:
            self.log_message.emit("WARN", "Camera not connected.")
            return
        if self._camera_service.state is CameraState.LIVE:
            return  # already live
        if not self._camera_service.acquire(CameraState.LIVE):
            return  # refused (sequence/autofocus owns the camera) — reason logged
        # Granted: from IDLE the service started the preview loop; from a
        # transient Take-shot loop the ownership was upgraded in place.
        self._live_requested = True
        self.log_message.emit("CMD", "Live preview started.")

    def stop_live(self) -> None:
        self._camera_service.release(CameraState.LIVE)
        self.log_message.emit("INFO", "Live preview stopped.")

    def _start_preview(self) -> None:
        if not self._session.camera:
            self.log_message.emit("WARN", "Camera not connected.")
            return
        params = self._params()
        self._preview = LivePreviewWorker(
            camera=self._session.camera,
            exposure=params.exposure_s,
            gain=params.gain,
            preview_scale=self._preview_scale(),
            light=_is_light_frame(params.frame_type),
            tag=params,
        )
        self._preview.frame_ready.connect(self._on_frame)
        self._preview.status_updated.connect(self.action_changed)
        self._preview.error_occurred.connect(self._on_preview_error)
        self._preview.finished.connect(self._on_preview_finished)
        self._preview.start()
        self.device_state_changed.emit("camera", "busy", "exposing")

    def _stop_preview(self) -> None:
        self._live_requested = False
        if self._preview and self._preview.isRunning():
            self._preview.stop()
            self._preview.wait(5000)
        self._preview = None
        if self._session.camera:
            self.device_state_changed.emit("camera", "connected", "")

    @pyqtSlot(str)
    def _on_preview_error(self, message: str) -> None:
        self.log_message.emit("ERROR", f"Preview: {message}")

    def _on_preview_finished(self) -> None:
        # The worker ended on its own (error) or after a stop — reconcile
        # ownership. Stale signals after a preemption find the state already
        # owned by sequence/autofocus and fall through to a no-op cleanup.
        state = self._camera_service.state
        if state in (CameraState.LIVE, CameraState.SINGLE):
            self._camera_service.release(state)
        else:
            self._stop_preview()

    @pyqtSlot(object, object, object, object, object)
    def _on_frame(self, preview_arr, full_arr, start_dt, end_dt, used=None) -> None:
        # Update worker settings for the next frame from the dock form. The
        # preview scale (Full/Half quality) only shapes the display pipeline —
        # saved FITS always use the full-resolution readout below. The form
        # snapshot rides along as the tag: ``used`` (a FrameSettings) is what
        # THIS frame was exposed with, which the form may no longer show.
        params = self._params()
        if self._preview:
            self._preview.update_settings(
                params.exposure_s,
                params.gain,
                scale=self._preview_scale(),
                light=_is_light_frame(params.frame_type),
                tag=params,
            )

        try:  # exposure-midpoint time → the light curve's true epoch
            self._last_exposure_mid = start_dt + (end_dt - start_dt) / 2
        except (TypeError, ValueError):
            self._last_exposure_mid = None
        self._last_exposure_s = getattr(used, "exposure_s", None) or params.exposure_s  # S74
        self._last_gain = _gain_of(used, params.gain)  # S83
        self._last_filter = self._live_filter(used, params)
        # Publish the (possibly decimated) preview; flag it so plate-solve /
        # photometry skip half-quality frames (their plate scale is wrong).
        self._last_raw_decimated = preview_arr.shape != full_arr.shape
        self._take_raw(preview_arr)
        self.frame_ready.emit(
            LiveFrame(
                preview=preview_arr,
                full=full_arr,
                start=start_dt,
                end=end_dt,
                decimated=self._last_raw_decimated,
            )
        )

        # Single-shot save: persist the requested number of FULL-RES frames.
        if self._capture_pending > 0:
            if self._wheel_moved_during(start_dt):
                # Exposed (partly) while the wheel turned: neither its filter
                # nor, for a dark, its darkness is known. The loop exposes
                # another frame, which is the one saved.
                self.log_message.emit(
                    "INFO",
                    "Take shot: the filter wheel moved during this exposure — "
                    "saving the next frame instead.",
                )
                return
            tag = used.tag if used is not None and used.tag is not None else params
            if not _is_light_frame(tag.frame_type) and self._wheel_can_block_light():
                problem = self._wheel_not_on_dark()
                if problem:
                    # The wheel left the Dark slot after the shot was accepted
                    # (moved by hand, or a refused move): never save a light
                    # frame as a dark.
                    self._capture_pending = 0
                    self.log_message.emit("WARN", f"{tag.frame_type} shot not saved: {problem}")
                    if not self._live_requested:
                        self._camera_service.release(CameraState.SINGLE)
                    return
            self._capture_pending -= 1
            self._save_fits_async(full_arr, start_dt, end_dt, used)
            if self._capture_pending == 0 and not self._live_requested:
                # Transient Take-shot loop done; Live keeps going (its release
                # would be a no-op here because LIVE owns the camera).
                self._camera_service.release(CameraState.SINGLE)

    def _live_filter(self, used, params) -> str:
        """The filter a live frame was exposed through (S49): the wheel's settled
        slot when a wheel reports one, else the form's filter for that frame."""
        session = self._session
        if session.filterwheel is not None and not session.filter_moving and session.filter_slot:
            return str(session.filter_slot)
        tag = used.tag if used is not None and getattr(used, "tag", None) is not None else params
        return str(getattr(tag, "filter_name", "") or "")

    def _on_camera_will_disconnect(self) -> None:
        """The session is about to drop the camera — stop using it first."""
        # Another camera or telescope may follow: its first good solve is the
        # new plate-scale reference (S50).
        self._astrometry.reset_scale_reference()
        state = self._camera_service.state
        if state in (CameraState.LIVE, CameraState.SINGLE):
            self._camera_service.release(state)  # stops the preview loop
        else:
            self._stop_preview()  # belt-and-braces for a leaked worker

    # ------------------------------------------------------------------
    # Advanced sequencer (Sequence tab → SequenceWorker)
    # ------------------------------------------------------------------

    def start_sequence(self, plan) -> bool:
        """Start the plan; returns False when refused (reason logged)."""
        if not self._session.camera:
            self.log_message.emit("WARN", "Connect the camera before running a sequence.")
            return False
        if self._sequence is not None:
            return False  # a sequence is already active (possibly paused for autofocus)
        # Acquire preempts a running live/single preview — the sequence owns
        # the camera from here on.
        if not self._camera_service.acquire(CameraState.SEQUENCE):
            return False  # refused (autofocus owns the camera) — reason logged

        self._seq_object = (plan.object_name or "").strip()
        self._active_run_root = None
        self.clear_lightcurves()
        self._sequence = SequenceWorker(
            camera=self._session.camera,
            telescope=self._session.telescope,
            filterwheel=self._session.filterwheel,
            plan=plan,
            frame_context_provider=self._sequence_frame_context,
            base_dir=Path(plan.base_dir) if plan.base_dir is not None else self._sessions_base(),
            parent=self,
        )
        self._sequence.step_started.connect(self.sequence_step)
        self._sequence.frame_image.connect(self._on_seq_frame_image)
        self._sequence.frame_saved.connect(self._on_seq_frame_saved)
        self._sequence.progress.connect(self._on_seq_progress)
        self._sequence.autofocus_due.connect(self._on_seq_autofocus_due)
        self._sequence.paused.connect(self.sequence_paused)
        self._sequence.error_occurred.connect(self._on_seq_error)
        self._sequence.finished.connect(self._on_seq_finished)
        self._on_complete = plan.on_complete
        self._seq_has_lights = any(
            s.enabled and s.count > 0 and s.frame_type == "Light" for s in plan.steps
        )

        self._sequence.start()
        self.sequence_running.emit(True)
        total = sum(s.count for s in plan.steps if s.enabled and s.count > 0) * max(1, plan.repeat)
        self.log_message.emit("CMD", f"Sequence started — {total} frame(s).")
        return True

    def sequence_has_light_frames(self) -> bool:
        """Whether the running sequence shoots Light frames (a field to identify)."""
        return self._sequence is not None and self._seq_has_lights

    def stop_sequence(self) -> None:
        if self._sequence and self._sequence.isRunning():
            self._sequence.stop()
            self.log_message.emit("INFO", "Stopping sequence…")

    def pause_sequence(self) -> None:
        """Hold at the next frame boundary (the current exposure completes)."""
        if self._sequence and self._sequence.isRunning():
            self._sequence.pause()
            self.log_message.emit("CMD", "Pausing after the current frame…")

    def resume_sequence_run(self) -> None:
        """Release a user pause (distinct from the AF resume handshake)."""
        if self._sequence and self._sequence.isRunning():
            self._sequence.resume()

    def _stop_sequence_worker(self) -> None:
        if self._sequence and self._sequence.isRunning():
            self._sequence.stop()
            self._sequence.wait(15000)
        self._sequence = None

    @pyqtSlot(int, int, float)
    def _on_seq_progress(self, done: int, total: int, eta_s: float) -> None:
        # Fan progress out to the Shell's persistent capture strip too.
        self.sequence_progress.emit(self._seq_object, done, total, eta_s)

    @pyqtSlot(str)
    def _on_seq_error(self, message: str) -> None:
        self.log_message.emit("ERROR", f"Sequence: {message}")

    def ingest_frame(self, full_arr) -> None:
        """Feed a saved full-res raw into the live pipeline (offline replay).

        The frame becomes the authoritative ``_last_raw`` — exactly like a
        sequence sub — so Solve, the catalog fetch, target selection and a
        batch re-run all work from a FITS opened without a telescope.
        """
        self._last_raw_decimated = False
        self._take_raw(full_arr)
        self.frame_ready.emit(
            LiveFrame(preview=full_arr, full=full_arr, start=None, end=None, decimated=False)
        )

    def _take_raw(self, arr) -> None:
        """A camera frame (or a sub) becomes ``_last_raw``; the one before is kept (S56).

        Back from an opened FITS, the tracker built on the file's field is dropped
        (S59): a camera solution was otherwise held to the file's anchors (S54).
        """
        if self._last_raw_from_file:
            self._reset_tracker()
        self._prev_raw = self._last_raw
        self._last_raw = arr
        self._last_raw_from_file = False

    def open_fits_frame(self, path) -> datetime | None:
        """Load a saved FITS into the live pipeline (Open FITS, offline replay).

        An opened file is another field and another night: the WCS and the
        field's catalogue cache are dropped (solve it again), the photometry
        epoch becomes the file's own exposure midpoint (see
        :func:`fits_exposure_mid`; None when the header has no usable date,
        and then no point is measured), and the last run's folder is
        forgotten so a point never lands in that run's CSVs.

        Returns the midpoint. Raises ``OSError``/``ValueError`` (the engine is
        untouched) when the file is not a single 2-D image of raw 16-bit
        data (see :func:`_raw_adu`).
        """
        from astropy.io import fits

        raw, header = fits.getdata(path, header=True)
        if raw is None or getattr(raw, "ndim", 0) != 2:
            raise ValueError("expected a single 2-D image HDU")
        # The display/measure pipeline speaks the sensor's raw dtype.
        frame = _raw_adu(raw)
        self.invalidate_astrometry()
        self._last_exposure_mid = fits_exposure_mid(header)
        self._file_egain = frame_egain(header, self._cfg("camera.egain_table", {}))
        self._last_gain = None  # S83: an opened frame's own e-/ADU, else the form's gain
        self._file_scintillation = frame_scintillation_inputs(header)  # S74
        self._last_filter = str(header.get("FILTER", "") or "").strip()
        self._active_run_root = None
        self.ingest_frame(frame)
        self._last_raw_from_file = True
        return self._last_exposure_mid

    @pyqtSlot(object)
    def _on_seq_frame_image(self, full_arr) -> None:
        self.ingest_frame(full_arr)  # sequence frames are always full-res

    def _on_seq_frame_saved(self, path: str, record) -> None:
        # Keep all science products beside the run that produced the FITS.
        self._last_sequence_dir = Path(path).parent
        run_root = self._last_sequence_dir.parent
        if run_root != self._active_run_root:
            self._active_run_root = run_root
            if self._diag is not None:
                self._diag.close()
            self._diag = None
            self._diag_object = None
            try:
                target_set = self.target_set()
                target_set.save(run_root / "targets.json")
                self._write_active_selection(target_set)
            except OSError as exc:
                self.log_message.emit("WARN", f"Save run targets: {exc}")
        if record is not None:
            self._last_filter = str(getattr(record, "filter_name", "") or "")  # S49
        if record is not None and getattr(record, "timestamp", None):
            try:
                start = datetime.fromisoformat(str(record.timestamp).replace("Z", "+00:00"))
                self._last_exposure_mid = start + timedelta(seconds=(record.exposure_s or 0) / 2.0)
            except (TypeError, ValueError):
                pass
            self._last_exposure_s = getattr(record, "exposure_s", None)  # S74
        if record is not None:
            self._last_gain = _gain_of(record, None)  # S83: the sub's, not the form's
        self.frame_saved.emit(path, record)  # the page logs the summary line
        # P5: one differential point per saved Light sub (uses the latest solve's WCS).
        # S44: never a Dark, Flat or Bias sub: its point was junk, and measuring it
        # moved the aperture tracker, which changed the Light points after it.
        if record is not None and getattr(record, "image_type", None) != "Light Frame":
            return
        if self._astrometry.wcs is not None and self.target_set().by_role(ROLE_TARGET):
            self._measure_photometry()

    def _on_seq_autofocus_due(self) -> None:
        """Run an autofocus pass mid-sequence, then resume the worker.

        SEQUENCE → AUTOFOCUS → SEQUENCE through the service: the sequence
        yields the camera for the sweep and gets it back when AF releases.
        """
        if not (self._session.focuser and self._session.camera):
            self._resume_sequence()
            return
        if not self._camera_service.begin_sequence_autofocus():
            self._resume_sequence()  # handshake refused — never block the run
            return
        self.log_message.emit("CMD", "Sequence: autofocus…")
        if self._start_autofocus_worker():
            self._autofocus.finished.connect(self._resume_sequence)
        else:
            # AF failed to start — hand the camera back and resume, never
            # leave the sequence blocked on the handshake.
            self._camera_service.release(CameraState.AUTOFOCUS)
            self._resume_sequence()

    def _resume_sequence(self) -> None:
        if self._sequence is not None:
            self._sequence.resume_after_autofocus()

    def _on_seq_finished(self, completed: bool) -> None:
        self._sequence = None
        # S45: the run's folder is closed. Every sub's point was measured before this
        # (frame_saved precedes finished), so a later live point goes to the live CSVs
        # and never rewrites this run's CSVs or photometry_quality.json.
        self._active_run_root = None
        # Hand the camera back (state_changed → "Idle" in the status bar). If
        # the sequence died while a mid-run autofocus held the camera, this
        # just cancels the pending resume — AF releases to IDLE on its own.
        self._camera_service.release(CameraState.SEQUENCE)
        # The worker moved the wheel directly; re-read it so the Camera form
        # (Take-shot metadata) shows the slot the wheel really sits on.
        self._session.refresh_filter()
        self.sequence_running.emit(False)
        self.log_message.emit(
            "OK" if completed else "INFO",
            "Sequence complete." if completed else "Sequence stopped.",
        )
        if completed:
            self._run_on_complete_action()

    def _run_on_complete_action(self) -> None:
        """End-of-sequence mount action — an explicit plan choice, logged.

        Runs only on FULL completion (never after a stop/error: the user is
        likely at the scope, and an unexpected park closes the Seestar arm).
        """
        action = self._on_complete
        if action == "Stop tracking":
            self.log_message.emit("CMD", "Sequence complete → stopping tracking (plan option).")
            self._session.set_tracking(False)
        elif action == "Park mount":
            self.log_message.emit("CMD", "Sequence complete → parking the mount (plan option).")
            self._session.park()

    def _sequence_frame_context(self, object_name: str, filter_name: str) -> FrameContext:
        """Build a FrameContext for the worker thread from cached state."""
        pos = self._session.last_position
        target = self._session.target_radec
        cam = self._session.camera
        site = observing_site(self._config) or (None, None, None)
        return FrameContext(
            ra=pos.ra if pos else None,
            dec=pos.dec if pos else None,
            altitude=pos.altitude if pos else None,
            azimuth=pos.azimuth if pos else None,
            target_ra=target[0] if target else None,
            target_dec=target[1] if target else None,
            object_name=object_name,
            filter_name=filter_name,
            observer=(self._config.get("observer.name") or "").strip(),
            site_lat=site[0],
            site_lon=site[1],
            site_elev=site[2],
            software=_SOFTWARE,
            ccd_temp=cam.get_ccd_temperature() if cam else None,
            egain_driver=cam.get_electrons_per_adu() if cam else None,
            egain_table=self._cfg("camera.egain_table", {}) or {},
            offset=cam.get_offset() if cam else None,
            readout_mode=cam.get_readout_mode_name() if cam else None,
        )

    def _sessions_base(self) -> Path:
        try:
            return self._config.sessions_path
        except AttributeError:
            return Path.home() / "Argos" / "sessions"

    def _diagnostics(self, tset) -> SessionDiagnostics:
        """The live flight recorder for the current object (P11).

        One jsonl per object next to the light-curve CSVs; a change of object
        closes the previous file and starts a fresh frame counter.
        """
        obj = tset.object_name or "Unknown"
        run_root = self._active_run_root
        if self._diag is None or self._diag_object != obj or self._diag_root != run_root:
            # A new object or a new run restarts the series; a run that ended only
            # moves the recorder out of its folder (S45).
            restart = (
                self._diag is None
                or self._diag_object != obj
                or (run_root is not None and run_root != self._diag_root)
            )
            if self._diag is not None:
                self._diag.close()
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in obj)
            root = (
                run_root / "diagnostics"
                if run_root is not None
                else self._sessions_base() / "targets"
            )
            self._diag = SessionDiagnostics(
                root / f"{safe or 'Unknown'}_live_diagnostics.jsonl",
                enabled=bool(self._cfg("diagnostics.enabled", False)),
            )
            self._diag_object = obj
            self._diag_root = run_root
            self._diag_frame = 0
            if restart:
                self._phot_fwhm = None  # new object → re-sample the series FWHM (P7)
        return self._diag

    # ------------------------------------------------------------------
    # Autofocus
    # ------------------------------------------------------------------

    def request_autofocus(self) -> None:
        """Toggle entry point (the Focus screen): start a sweep or stop it."""
        if self._camera_service.state is CameraState.AUTOFOCUS:
            self.stop_autofocus()
        else:
            self.start_autofocus()

    def start_autofocus(self) -> None:
        if not (self._session.focuser and self._session.camera):
            self.log_message.emit("WARN", "Autofocus needs focuser + camera connected")
            return
        if self._camera_service.state is CameraState.AUTOFOCUS:
            return  # already sweeping
        # Acquire preempts a running live/single preview (AF outranks LIVE)
        # and is refused while a sequence owns the camera.
        if not self._camera_service.acquire(CameraState.AUTOFOCUS):
            return  # reason logged via acquire_refused
        if not self._start_autofocus_worker():
            self._camera_service.release(CameraState.AUTOFOCUS)

    def _start_autofocus_worker(self) -> bool:
        """Create + start the AF sweep worker.

        The camera must already be owned as :attr:`CameraState.AUTOFOCUS`
        (via ``acquire`` or the sequence handshake). Returns False if a
        stale worker is still winding down.
        """
        if self._autofocus and self._autofocus.isRunning():
            return False
        params = self._params()
        self._autofocus = AutofocusWorker(
            focuser=self._session.focuser,
            camera=self._session.camera,
            exposure_s=min(params.exposure_s, 10.0),
            gain=params.gain,
            parent=self,
        )
        self._autofocus.step_done.connect(self.autofocus_step)
        self._autofocus.best_found.connect(self.autofocus_best)
        self._autofocus.error_occurred.connect(self._on_af_error)
        self._autofocus.finished.connect(self._on_af_finished)
        self.autofocus_state.emit(True)
        self._autofocus.start()
        self.log_message.emit("CMD", "Autofocus started…")
        return True

    @property
    def autofocus_running(self) -> bool:
        """True while an autofocus sweep worker is running."""
        return self._autofocus is not None and self._autofocus.isRunning()

    #: How long Stop AF blocks the UI for the worker to end (ms).
    _AF_STOP_WAIT_MS = 10_000

    def stop_autofocus(self) -> None:
        worker = self._autofocus
        if worker is not None and worker.isRunning():
            if self._af_returning:
                self.log_message.emit(
                    "INFO", "Autofocus stopping — the focuser is still returning to its start."
                )
                return
            worker.stop()
            if not worker.wait(self._AF_STOP_WAIT_MS):
                # The worker drives the focuser back to its start (bounded by
                # its own 30 s deadline) before it ends. Keep it, and its hold
                # on the camera, until then: _on_af_finished releases the
                # camera. Dropping it here let a new autofocus start a second
                # worker driving the same focuser.
                self._af_returning = True
                self.log_message.emit(
                    "INFO",
                    "Autofocus stopping — the focuser is still returning to its start; "
                    "the camera is released when it is back.",
                )
                return
        self._autofocus = None
        self.autofocus_state.emit(False)
        # Hand the camera back promptly (the worker's queued finished signal
        # would also release, but that lands on a later event-loop turn).
        self._camera_service.release(CameraState.AUTOFOCUS)

    @pyqtSlot(str)
    def _on_af_error(self, message: str) -> None:
        self.log_message.emit("ERROR", f"AF: {message}")

    def _on_af_finished(self) -> None:
        self._af_returning = False
        self.autofocus_state.emit(False)
        # The focus (and hence the PSF) may have changed — re-sample the
        # series aperture FWHM on the next measured frame (P7).
        self._phot_fwhm = None
        # Release through the service: back to SEQUENCE when this was the
        # mid-sequence handshake, else to IDLE. Double release (after a user
        # stop_autofocus already released) is a safe no-op.
        self._camera_service.release(CameraState.AUTOFOCUS)

    # ------------------------------------------------------------------
    # Plate solving the live frame (§6) — ASTAP with the mount as a hint
    # ------------------------------------------------------------------

    def _mount_radec(self) -> tuple[float, float] | None:
        pos = self._session.last_position
        return (pos.ra, pos.dec) if pos is not None else None

    def on_processed(self, green_shape, metrics, mean_fwhm) -> None:
        """Per-processed-frame bookkeeping + the auto-solve policy trigger.

        Called by the page after the display pipeline has run: ``green_shape``
        is the processed frame's green geometry (matches ``last_raw``).
        """
        self._green_shape = green_shape
        self._last_metrics = metrics
        self._last_fwhm = mean_fwhm
        # Auto-solve policy (no-op unless armed + due): re-solve the live frame
        # so the WCS grid tracks the sequence instead of going stale. Half-
        # quality previews are skipped — their plate scale would poison the solve.
        if self._last_raw is not None and green_shape is not None and not self._last_raw_decimated:
            self._astrometry.on_new_frame(
                self._last_raw,
                green_shape,
                self._mount_radec(),
                self._session.target_radec,
                gate_scale=not self._last_raw_from_file,  # S50: camera frames only
            )

    def solve_now(self) -> None:
        """Plate-solve the current live frame (the manual Solve button)."""
        if self._last_raw is None or self._green_shape is None:
            self.log_message.emit("WARN", "No frame to solve yet — start a preview first.")
            return
        if self._last_raw_decimated:
            self.log_message.emit(
                "WARN", "Preview is at half quality — set Preview to Full res to plate-solve."
            )
            return
        mount = self._mount_radec()
        if not self._astrometry.solve_now(
            self._last_raw,
            self._green_shape,
            mount,
            self._session.target_radec,
            gate_scale=not self._last_raw_from_file,  # S50: an opened FITS is not gated
        ):
            return  # a solve is already running
        hint = (
            f" (hint RA {mount[0]:.3f}h Dec {mount[1]:+.2f}°)" if mount else " (blind — no mount)"
        )
        self.log_message.emit("CMD", f"Plate-solving current frame…{hint}")

    @pyqtSlot(str)
    def _on_solve_failed(self, message: str) -> None:
        self.log_message.emit("ERROR", f"Solve: {message}")

    def measure_photometry_if_idle(self) -> None:
        """Per-solve photometry point — sequences measure per saved sub instead."""
        if self._camera_service.state not in (CameraState.SEQUENCE, CameraState.AUTOFOCUS):
            self._measure_photometry()

    def invalidate_astrometry(self) -> None:
        """Drop the WCS + the field's catalog cache — a slew changes the field.

        The catalog is re-fetched on the next solve; the page clears its own
        projections/overlays alongside this call.
        """
        self._astrometry.invalidate()
        self._variables = []
        self._comparisons = []
        self._field_stars = []
        self._named_objects = []
        self._exoplanet_hosts = []
        self._catalog_centre = None
        self._reset_tracker()
        self._unverified_logged = False  # S56: a slew or invalidation ends the episode

    # ------------------------------------------------------------------
    # Catalog (VSX/VSP once per field)
    # ------------------------------------------------------------------

    def refetch_catalog(self) -> None:
        """Drop the field's catalog cache and re-query with the current settings.

        Lighter than :meth:`invalidate_astrometry`: the WCS solution and the
        live tracker are left untouched because the field hasn't moved — only
        the catalog query parameters changed (e.g. the user lowered the
        magnitude limit in the Astrometry ▸ Catalog dialog). ``maybe_fetch_catalog``
        short-circuits while the cached field centre still matches, so we clear
        that centre and fetch again straight away when a solution already exists
        (a no-op when the field is unsolved — nothing to query around yet).
        """
        self._variables = []
        self._comparisons = []
        self._field_stars = []
        self._named_objects = []
        self._exoplanet_hosts = []
        self._catalog_centre = None
        self.maybe_fetch_catalog()

    def maybe_fetch_catalog(self) -> None:
        """Fetch VSX/VSP once per field (re-fetch only when the centre moves)."""
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            return
        geom = field_geometry(self._astrometry.wcs, self._green_shape)
        if geom is None:
            return
        ra_deg, dec_deg, radius_deg, fov_arcmin = geom
        if self._catalog_centre is not None and (
            self._variables
            or self._comparisons
            or self._field_stars
            or self._named_objects
            or self._exoplanet_hosts
        ):
            moved = angular_separation_deg(
                ra_deg / 15.0, dec_deg, self._catalog_centre[0] / 15.0, self._catalog_centre[1]
            )
            if moved < radius_deg:
                return  # same field → reuse the cached catalog
        self._catalog_centre = (ra_deg, dec_deg)
        # VSX must be queried at the solved field centre (all variables that
        # are actually on the detector). VSP, however, supplies a calibrated
        # *sequence for a scientific target*; querying the mount/field centre
        # instead loses that sequence whenever a goto is offset.
        targets = self.target_set().by_role(ROLE_TARGET)
        source = targets[0] if targets else None
        want_field_stars = bool(self._cfg("catalog.field_stars_enabled", True))
        want_named_objects = bool(self._cfg("catalog.named_objects_enabled", True))
        identity_budget = max(
            50, min(5000, int(self._cfg("catalog.identification_max_objects", 400)))
        )
        if want_field_stars and want_named_objects:
            # Gaia supplies the stellar backbone; SIMBAD enriches it with
            # physical types and conventional names.  Sharing one budget keeps
            # the observer's speed choice honest instead of spending it twice.
            field_star_budget = max(25, round(identity_budget * 0.7))
            named_object_budget = max(25, identity_budget - field_star_budget)
        else:
            field_star_budget = identity_budget
            named_object_budget = identity_budget
        req = CatalogRequest(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            fov_arcmin=fov_arcmin,
            mag_limit=float(self._cfg("catalog.mag_limit", 15.0)),
            max_results=int(self._cfg("catalog.max_results", 250)),
            include_suspected=bool(self._cfg("catalog.include_suspected", True)),
            comparison_target_name=source.display_name if source else None,
            comparison_ra_deg=source.ra_deg if source else None,
            comparison_dec_deg=source.dec_deg if source else None,
            want_field_stars=want_field_stars,
            field_star_mag_limit=float(self._cfg("catalog.field_stars_mag_limit", 18.0)),
            field_star_max_results=field_star_budget,
            want_named_objects=want_named_objects,
            named_object_max_results=named_object_budget,
            named_objects_allow_network=bool(
                self._cfg("catalog.named_objects_allow_network", True)
            ),
            want_exoplanet_hosts=bool(self._cfg("catalog.exoplanet_hosts_enabled", True)),
            exoplanet_hosts_allow_network=bool(
                self._cfg("catalog.exoplanet_hosts_allow_network", True)
            ),
        )
        self._catalog_worker = CatalogWorker(req, parent=self)
        self._catalog_worker.fetched.connect(self._on_catalog)
        self._catalog_worker.start()

    @pyqtSlot(object)
    def _on_catalog(self, result) -> None:
        if not result.ok:
            self.log_message.emit("WARN", f"Catalog: {result.error}")
            return
        self._variables = list(result.variables)
        self._comparisons = list(result.comparisons)
        self._field_stars = list(result.field_stars)
        self._named_objects = list(result.named_objects)
        self._exoplanet_hosts = list(result.exoplanet_hosts)
        self.catalog_ready.emit(result)  # the page re-projects onto the WCS
        for warning in result.warnings:
            self.log_message.emit("WARN", f"Catalog: {warning}")
        if self._variables:
            self.log_message.emit("OK", f"Catalog: {len(self._variables)} variable(s) in field")
        if self._field_stars:
            self.log_message.emit(
                "OK", f"Catalog: {len(self._field_stars)} Gaia DR3 source(s) in field"
            )
            if result.field_star_limit and len(self._field_stars) >= result.field_star_limit:
                self.log_message.emit(
                    "INFO",
                    "Catalog: Gaia identification budget reached; the displayed list is "
                    "not necessarily complete to the requested G limit.",
                )
        if self._named_objects:
            self.log_message.emit(
                "OK", f"Catalog: {len(self._named_objects)} named SIMBAD object(s) in field"
            )
            if result.named_object_limit and len(self._named_objects) >= result.named_object_limit:
                self.log_message.emit(
                    "INFO",
                    "Catalog: SIMBAD identification budget reached; increase it in Settings "
                    "only when a more detailed field inventory is useful.",
                )
        if self._exoplanet_hosts:
            self.log_message.emit(
                "OK", f"Catalog: {len(self._exoplanet_hosts)} confirmed exoplanet host(s) in field"
            )
        if self._comparisons:
            self.log_message.emit(
                "OK",
                f"Catalog: {len(self._comparisons)} calibrated VSP comparison star(s) available",
            )
        else:
            self.log_message.emit(
                "WARN",
                "Catalog: no calibrated VSP comparison stars returned for this field. "
                "Refresh the field catalogue or choose calibrated comparisons manually.",
            )
        # A target assigned before the VSP answer arrived got no auto-selected
        # comparisons (the set stayed comp-less and every differential measure
        # would say "no valid comparisons") — backfill now that the field's
        # comps are known. A manual/earlier ensemble is never clobbered.
        if self._comparisons:
            tset = self.target_set()
            targets = tset.by_role(ROLE_TARGET)
            if targets:
                self._auto_select_comparisons(tset, targets[0])
                if tset.by_role(ROLE_COMPARISON):
                    self._save_target_set(tset)
                    self._anchors_changed()
                    self.targets_changed.emit(tset)
            self._backfill_chart_ids(tset)
        if self._field_stars:
            self._backfill_proper_motions(self.target_set())

    def _backfill_proper_motions(self, tset: TargetSet) -> None:
        """S77: the set's VSX/VSP stars take the proper motion of their Gaia DR3 source.

        Every path that places an aperture then moves them to the frame's date
        (``TargetSet.at_jd``). The object's set is saved, and so is the running run's
        ``targets.json`` snapshot, as for the VSP chart (S68).
        """
        changed = tset.backfill_proper_motions(self._field_stars)
        if not changed:
            return
        self._save_target_set(tset)
        self.log_message.emit(
            "INFO",
            f"Catalog: proper motion from Gaia DR3 for {changed} star(s) of the set; their"
            " apertures are placed at each frame's date (S77).",
        )
        if self._active_run_root is None or self._sequence is None:
            return
        if not self._sequence.isRunning():
            return
        snapshot = self._active_run_root / "targets.json"
        try:
            run_set = TargetSet.load(snapshot) if snapshot.is_file() else None
            if run_set is not None and run_set.backfill_proper_motions(self._field_stars):
                run_set.save(snapshot)
        except OSError as exc:
            self.log_message.emit("WARN", f"Save run targets: {exc}")

    def _backfill_chart_ids(self, tset: TargetSet) -> None:
        """S68: comparisons kept from before 0.4.2 get the VSP chart of this answer.

        The object's set is saved, and so is the running run's ``targets.json``
        snapshot (taken on its first sub, maybe before this answer), so that the
        run's AAVSO report names the sequence in CHART.
        """
        if not tset.backfill_chart_ids(self._comparisons):
            return
        self._save_target_set(tset)
        if self._active_run_root is None or self._sequence is None:
            return
        if not self._sequence.isRunning():
            return
        snapshot = self._active_run_root / "targets.json"
        try:
            run_set = TargetSet.load(snapshot) if snapshot.is_file() else None
            if run_set is not None and run_set.backfill_chart_ids(self._comparisons):
                run_set.save(snapshot)
        except OSError as exc:
            self.log_message.emit("WARN", f"Save run targets: {exc}")

    # ------------------------------------------------------------------
    # Target set persistence (targets.json per object)
    # ------------------------------------------------------------------

    def crowding(self) -> tuple[dict, float]:
        """S79: the set's crowded comparison and check stars (``crowded_stars``) and the
        radius used, about 2 aperture radii (the series FWHM's aperture, else the
        default one) at the active profile's green-plane scale, in arcsec."""
        from argos.core.catalog.targets import CROWDING_APERTURE_RADII, crowded_stars
        from argos.core.imaging.metrics import arcsec_per_green_px

        params = PhotometryParams.from_config(self._cfg)
        fwhm = self._phot_fwhm or self._last_fwhm or None
        radius = CROWDING_APERTURE_RADII * params.aperture_px(fwhm) * arcsec_per_green_px()
        return crowded_stars(self.target_set(), radius), radius

    def _object_name(self) -> str:
        params = self._params() if self._params is not None else None
        name = (params.object_name if params else "") or "Unknown"
        return name.strip() or "Unknown"

    def _target_path(self, obj: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (obj or "Unknown"))
        return self._sessions_base() / "targets" / f"{safe or 'Unknown'}.json"

    def target_set(self) -> TargetSet:
        """The persistent target set for the current object name."""
        obj = self._object_name()
        if self._target_set is None or self._target_set.object_name != obj:
            self._target_set = TargetSet.load(self._target_path(obj))
            self._target_set.object_name = obj
        return self._target_set

    def _save_target_set(self, tset: TargetSet) -> None:
        try:
            tset.save(self._target_path(tset.object_name))
            self._write_active_selection(tset)
        except OSError as exc:
            self.log_message.emit("ERROR", f"Save targets: {exc}")

    def _write_active_selection(self, target_set: TargetSet) -> None:
        """Snapshot an in-run target-set edit without rewriting its history."""
        if (
            self._active_run_root is None
            or self._sequence is None
            or not self._sequence.isRunning()
        ):
            return
        target_set.save_selection_manifest(
            self._active_run_root / "photometry_selection.json", generated_by=_SOFTWARE
        )
        target_set.append_selection_history(
            self._active_run_root / "photometry_selection_history.jsonl", generated_by=_SOFTWARE
        )

    def on_object_changed(self) -> None:
        """The Object name changed — re-key and re-sync every dependent view.

        The target set is keyed by object name, so an edit silently swapped
        the set under the views (markers/tables kept showing the old stars
        while measurements ran on the new, usually empty, set). Reload under
        the new key and broadcast, and start the curve display fresh — the
        old object's curves live on in its CSVs.
        """
        tset = self.target_set()  # detects the key change and reloads
        self.clear_lightcurves()
        self._anchors_changed()
        self.targets_changed.emit(tset)

    def set_target_role(self, star: TargetStar) -> None:
        tset = self.target_set()
        tset.set_role(star)
        if star.role == ROLE_TARGET:
            self._auto_select_comparisons(tset, star)
        self._save_target_set(tset)
        self._anchors_changed()
        self.targets_changed.emit(tset)

    def propose_comparison_stars(self) -> int:
        """Complete the active target with the configured VSP ensemble size.

        Used when the observer changes the requested comparison count in the
        photometry panel. Existing manual choices are preserved; only missing
        calibrated VSP members are added.
        """
        tset = self.target_set()
        targets = tset.by_role(ROLE_TARGET)
        if not targets:
            return 0
        before = len(tset.by_role(ROLE_COMPARISON))
        self._auto_select_comparisons(tset, targets[0])
        added = len(tset.by_role(ROLE_COMPARISON)) - before
        if added:
            self._save_target_set(tset)
            self._anchors_changed()
            self.targets_changed.emit(tset)
        return added

    def reselect_comparison_stars(self) -> int:
        """Replace VSP suggestions with the best stars from the pilot frame.

        This is an explicit observer action.  Manual comparison choices stay
        intact; VSP suggestions, including ones made before pilot-quality
        ranking existed, are replaced as one coherent ensemble.
        """
        tset = self.target_set()
        targets = tset.by_role(ROLE_TARGET)
        if not targets or not self._comparisons:
            # No VSP stars to choose from (unsolved, catalogue not back, after a
            # GoTo): keep the ensemble rather than empty it (S32).
            return 0
        # Choose on a copy: when no VSP star passes the pilot gate (all too
        # far, too faint, off the frame), the ensemble is kept, not emptied.
        trial = copy.deepcopy(tset)
        trial.stars = [
            star
            for star in trial.stars
            if not (star.role == ROLE_COMPARISON and star.source in {"vsp", "vsp_auto"})
        ]
        added = self._auto_select_comparisons(trial, trial.by_role(ROLE_TARGET)[0])
        if not added:
            return 0
        tset.stars = trial.stars
        self._save_target_set(tset)
        self._anchors_changed()
        self.targets_changed.emit(tset)
        return added

    def _auto_select_comparisons(self, tset: TargetSet, target: TargetStar) -> int:
        """Fill an empty comparison set from the field's VSP stars (W2).

        Only when the set has none yet — a manual selection is never
        clobbered, and a second target reuses the same ensemble (it serves
        the whole field). Off-frame stars are excluded via the current WCS.
        """
        if not self._comparisons:
            return 0
        # Do not treat an arbitrary manually-clicked star as a calibrated
        # ensemble.  It has no AUID or catalogue magnitude, and therefore
        # cannot supply a differential zero point.  Preserve it for the user,
        # but complement it with the VSP proposal rather than leaving the
        # target scientifically unusable.
        band = str(self._cfg("photometry.default_band", "TG") or "TG")
        existing = tset.by_role(ROLE_COMPARISON)
        # S46: the target and the check star are never offered as comparisons.
        others = [s for s in tset.stars if s.role != ROLE_COMPARISON]
        calibrated = [
            s for s in existing if s.mags.get(band) is not None or s.mags.get("V") is not None
        ]
        wanted = max(0, int(self._cfg("photometry.auto_comparisons", 5)) - len(calibrated))
        if wanted <= 0:
            return 0
        target_inst_mag, quality = self._pilot_comparison_quality(target)
        min_snr = float(self._cfg("photometry.comparison_min_snr", 10.0))
        max_delta = float(self._cfg("photometry.comparison_max_delta_mag", 1.5))
        max_separation = float(self._cfg("photometry.comparison_max_separation_arcmin", 25.0))
        picks = auto_comparison_stars(
            target.ra_deg,
            target.dec_deg,
            self._comparisons,
            wcs=self._astrometry.wcs,
            green_shape=self._green_shape,
            count=wanted + len(existing) + len(others),
            candidate_quality=quality,
            target_inst_mag=target_inst_mag,
            min_snr=min_snr,
            max_delta_inst_mag=max_delta,
            max_separation_arcmin=max_separation,
        )

        # A manual click and its VSP record use different keys (position vs
        # AUID).  Keep a single physical star in the target set even in that
        # case, favouring the VSP record because it carries calibrated mags.
        def same_star(a: TargetStar, b: TargetStar) -> bool:
            if a.auid and b.auid and a.auid == b.auid:
                return True
            sep = angular_separation_deg(a.ra_deg / 15.0, a.dec_deg, b.ra_deg / 15.0, b.dec_deg)
            return sep < 1.0 / 3600.0

        def already_present(candidate: TargetStar) -> bool:
            # S46: set_role(candidate) replaced a check star of the same AUID.
            if any(same_star(star, candidate) for star in others):
                return True
            for saved in tuple(existing):
                if saved.auid and candidate.auid and saved.auid == candidate.auid:
                    return True
                if (
                    angular_separation_deg(
                        saved.ra_deg / 15.0,
                        saved.dec_deg,
                        candidate.ra_deg / 15.0,
                        candidate.dec_deg,
                    )
                    < 1.0 / 3600.0
                ):
                    if not saved.mags:
                        # Replace the uncalibrated manual identity with its
                        # authoritative VSP counterpart at the same position.
                        tset.remove(saved.key())
                        existing.remove(saved)
                        return False
                    return True
            return False

        picks = [p for p in picks if not already_present(p)][:wanted]
        for comp in picks:
            tset.set_role(comp)
        if picks:
            self.log_message.emit(
                "OK",
                f"Photometry: {len(picks)} pilot-qualified comparison(s) selected "
                f"for {target.display_name}",
            )
        if quality is not None and len(picks) < wanted:
            self.log_message.emit(
                "WARN",
                f"Photometry: only {len(picks)} of {wanted} requested comparisons pass "
                f"the pilot quality gate (SNR ≥ {min_snr:g}, Δmag ≤ {max_delta:g}, "
                f"distance ≤ {max_separation:g}′).",
            )
        return len(picks)

    def _pilot_comparison_quality(
        self, target: TargetStar
    ) -> tuple[float | None, dict[str, ComparisonQuality] | None]:
        """Measure target and VSP candidates on the solved pilot frame.

        The catalogue sees the whole sky but cannot know which calibrated star
        is measurable through the active filter.  A single full-resolution,
        solved image gives the relevant SNR, saturation and brightness match.
        """
        wcs = self._astrometry.wcs
        if wcs is None or self._last_raw is None or self._last_raw_decimated:
            return None, None
        green = green_plane(self._last_raw)
        params = PhotometryParams.from_config(self._cfg, egain=self._egain())
        fwhm = self._phot_fwhm or self._last_fwhm or DEFAULT_FWHM
        r_ap = params.aperture_px(fwhm)
        r_in = max(params.annulus_in_px, r_ap + 1.0)
        r_out = max(params.annulus_out_px, r_in + 2.0)

        def measure(ra_deg: float, dec_deg: float):
            x, y = wcs.world_to_pixel_deg(ra_deg, dec_deg)
            # A catalogue coordinate must land on a real local source before it
            # is allowed to enter the automatic comparison ensemble.  Aperture
            # flux alone can look plausible when a WCS marker is displaced onto
            # a neighbour or background structure; the centroid agreement is a
            # separate, stricter identity check.
            centroid = measure_star_at(
                self._last_raw,
                float(x),
                float(y),
                radius=max(2, int(round(r_ap))),
                search=3,
            )
            if centroid is None or math.hypot(centroid.x - float(x), centroid.y - float(y)) > 3.0:
                return None
            return measure_aperture(
                green,
                centroid.x,
                centroid.y,
                r_ap,
                r_in,
                r_out,
                egain=params.egain,
                read_noise_e=params.read_noise_e,
                sat_adu=params.sat_adu,
                black_adu=params.black_adu,
                plane_pixels=params.plane_pixels,
            )

        target_phot = measure(target.ra_deg, target.dec_deg)
        if target_phot is None or target_phot.inst_mag is None:
            return None, None
        quality: dict[str, ComparisonQuality] = {}
        for star in self._comparisons:
            phot = measure(star.ra_deg, star.dec_deg)
            if phot is not None:
                quality[star.auid] = ComparisonQuality(
                    snr=phot.snr,
                    inst_mag=phot.inst_mag,
                    saturated=phot.saturated,
                    suspect=phot.suspect,
                )
        return target_phot.inst_mag, quality

    def photometry_geometry(self) -> tuple[float, float, float]:
        """Return the active aperture and sky-annulus radii in green pixels.

        This is intentionally public for the capture UI: the ring shown around
        a selected source must describe the same FWHM-adaptive aperture used by
        :func:`measure_frame`, not the independent focus-inspection radius.
        """
        params = PhotometryParams.from_config(self._cfg, egain=self._egain())
        aperture = params.aperture_px(self._phot_fwhm or self._last_fwhm)
        inner = max(params.annulus_in_px, aperture + 1.0)
        outer = max(params.annulus_out_px, inner + 2.0)
        return aperture, inner, outer

    def remove_target(self, key: str) -> None:
        tset = self.target_set()
        tset.remove(key)
        self._save_target_set(tset)
        self._anchors_changed()
        self.targets_changed.emit(tset)

    # ------------------------------------------------------------------
    # Live photometry (§6 P4/P5)
    # ------------------------------------------------------------------

    def _egain(self) -> float:
        """e-/ADU for photometric errors (``hardware.egain.live``): the gain table, the
        observer's photon-transfer file, the profile's photon transfer (S73), the
        driver, the active sensor reference.

        At the gain the frame in hand was taken at (S83: a sequence sub's step, a live
        frame's settings), the Camera form's only before any frame. An opened frame
        keeps its own gain (``frame_egain``) when it records one.
        """
        if self._last_raw_from_file and self._file_egain is not None:
            return self._file_egain
        return camera_egain.live(
            self._last_gain if self._last_gain is not None else self._params().gain,
            table=self._cfg("camera.egain_table", {}) or {},
            driver=self._session.egain_driver,
        )

    def _with_frame_scintillation(self, params: PhotometryParams) -> PhotometryParams:
        """S74's inputs for the frame in hand: an opened frame's header (``EXPTIME``,
        ``AIRMASS``, ``SITEELEV``), else its exposure, the mount's airmass and the
        Settings site."""
        if self._last_raw_from_file:
            return params.with_frame(**self._file_scintillation)
        pos = self._session.last_position
        air = airmass_from_altitude(pos.altitude) if pos else None
        return params.with_frame(exposure_s=self._last_exposure_s, airmass=air)

    def _photometry_csv_path(self, star, token: str) -> Path:
        """One CSV per (star, filter) (S49): the filter token in the name."""
        obj = self.target_set().object_name or "Unknown"
        tag = star.auid or star.display_name
        if self._active_run_root is not None:
            role = getattr(star, "role", "target") or "target"
            return self._active_run_root / "photometry" / run_curve_csv_name(role, obj, token, tag)
        # No run yet (live preview, Open FITS): one file per curve, named after
        # the time it started, so measuring the object again (A → B → A, the
        # next evening) never overwrites the earlier points on disk.
        key = curve_key(star, token)
        path = self._preview_csvs.get(key)
        if path is None:
            path = _new_preview_csv(
                self._sessions_base() / "targets",
                obj,
                tag,
                _utcnow(),
                taken=set(self._preview_csvs.values()),
                token=token,
            )
            self._preview_csvs[key] = path
        return path

    def _wcs_for_frame(self, green, tset: TargetSet, params: PhotometryParams):
        """Reference WCS, rigid-corrected by the live tracker when enabled.

        Same recipe as the batch worker: the tracker is built lazily on the
        first measured frame, anchors on the set's stable stars, and keeps its
        last good transform when a frame has no usable anchor (clouds). Every
        refit is signalled so the page re-projects the catalog markers — the
        fix for the field bug where the variable-star markers froze at the
        solve position while the alt-az field rotated under them.
        """
        if not params.track_apertures:
            return self._astrometry.wcs
        wcs = self._base_wcs()
        if self._tracker is None or not self._tracker.anchor_count:
            # Also when built with no star seen (clouds, or the field had
            # moved): try again rather than until the next solve, which S35
            # makes due. The anchors are chosen on the solved frame (S56).
            self._tracker, self._tracker_anchor_stars = self._build_live_tracker(
                green, wcs, tset, params, chosen_on=self._anchor_frame(green)
            )
            if wcs is self._astrometry.wcs:
                self._rotation_attempted = None  # S69 (a): on the solution, a new count
        telescope = self._session.telescope
        # The alt-az tracker needs a rigid rotation + translation.  On an EQ
        # wedge there is no field rotation, so only retain measured drift;
        # centroid noise must not rotate a whole overlay about the sensor.
        allow_rotation = getattr(telescope, "alignment_mode", None) not in {"EQ", "EQ (GEM)"}
        self._tracker.update(green, allow_rotation=allow_rotation)
        self.apertures_tracked.emit()
        return TrackedWCS(wcs, self._tracker)

    def _field_lost(self, params: PhotometryParams) -> bool:
        """No star of the set where the tracked solution places it (S35).

        The field moved further than the tracker's search radius since the
        solve (a pointing jump, or a frame measured through an older solve),
        or clouds hide every anchor: apertures there would measure blank sky.
        """
        return (
            params.track_apertures and self._tracker is not None and not self._tracker.anchors_used
        )

    def _lock_lost(self, green, tracked, params: PhotometryParams) -> bool:
        """Fewer than half the anchors show a star where the tracked solution puts them (S48).

        The batch's S43 check, in the live and sequence paths: after a jump
        larger than the search radius a window may centroid a neighbour or
        noise, the tracker reports that anchor and moves every aperture by its
        offset, and S35 (no anchor at all) does not fire. Clouds that dim the
        anchors below SNR 5 fail it too. It does not catch a wrong plate
        solution: a new solution rebuilds the tracker from the stars seen where
        that solution puts them, so its anchors pass by construction (S50
        refuses the wrong scale instead).
        """
        stars = self._tracker_anchor_stars
        if not params.track_apertures or self._tracker is None or not stars:
            return False
        seen = anchors_seen(green, tracked, stars, params, min_snr=_LOCK_MIN_SNR)
        return seen < max(1, math.ceil(len(stars) / 2))

    def _centred_anchors(self, offsets: dict[str, float]) -> int:
        """S69 (b): the tracker's anchors less those more than 1 px off their aperture
        centre on this frame (an anchor too faint to test counts, as before) and the
        ones its fit rejected (they verified nothing; S80: every inconsistent one)."""
        bad = off_centre(offsets)
        rejected = self._tracker.rejected_anchors if self._tracker is not None else frozenset()
        return sum(
            1
            for index, star in enumerate(self._tracker_anchor_stars)
            if star.key() not in bad and index not in rejected
        )

    def _lock_unverified(
        self, params: PhotometryParams, tset: TargetSet, tracked, offsets=None
    ) -> bool:
        """The tracker steers on fewer than 3 anchors: the S48 check verifies nothing (S56).

        With n = 1 or 2 anchors, ceil(n/2) = 1 anchor must be seen, and the
        anchor whose centroid moved the solution is seen by construction: a
        neighbour taken for a comparison after a jump, or at a stale position
        after a set change (S52), passes. The frame keeps its points, flagged
        suspect, and a solve is due at once; a new solution rebuilds the tracker.

        Verified all the same (S56 as amended on 2026-11-15): a frame measured
        through a solution of this sub or the previous one on which the tracker
        moved no aperture of the set more than ``_LOCK_FRESH_MAX_SHIFT_PX`` from
        where that solution puts it (:meth:`_fresh_lock`).

        S69 (b): the anchors counted are those centred within 1 px of their aperture
        (``offsets``, :func:`centring_offsets`): off-centre anchors that leave fewer
        than 3 put the frame in this case.
        """
        if not (params.track_apertures and self._tracker is not None):
            return False
        if not self._tracker_anchor_stars:
            return False
        n = self._centred_anchors(offsets or {})
        if n >= _LOCK_VERIFY_MIN_ANCHORS:
            return False
        return not self._fresh_lock(tset, tracked)

    def _verified_on_previous_solution(self, params: PhotometryParams, offsets=None) -> bool:
        """A run's sub of 1 or 2 anchors verified through the previous sub's solution
        (S56 as amended on 2026-11-15, second set): its own solve is due now.

        Without it the next sub is two subs from that solution and unverified: with
        one solve per run the subs alternated verified and flagged (XX Cyg
        2026-08-29 050148Z: 12 of 22 flagged). Outside a run a live point follows
        each solve, of the newest frame or the one before: nothing more is due.
        """
        if not (params.track_apertures and self._tracker is not None):
            return False
        if not self._tracker_anchor_stars:
            return False
        if self._centred_anchors(offsets or {}) >= _LOCK_VERIFY_MIN_ANCHORS:  # S69 (b)
            return False
        if self._camera_service.state is not CameraState.SEQUENCE:
            return False
        solved = self._astrometry.solved_raw
        return solved is not None and solved is self._prev_raw and solved is not self._last_raw

    def _fresh_lock(self, tset: TargetSet, tracked) -> bool:
        """The frame is measured through a solution of this sub or the previous one,
        and the tracker moved the set's apertures less than 10 px from it (S56).

        The quantity: the largest distance, over the set's stars, between a star's
        position through the raw solution and through the tracked one this frame
        is measured with (a set-change rebase included). Between two subs the
        owner's fields move up to 7.5 px; a neighbour taken for an anchor moves them
        by the distance to that neighbour (22-36 px in the cases seen).
        """
        wcs = self._astrometry.wcs
        solved = self._astrometry.solved_raw
        if wcs is None or solved is None or self._last_raw is None:
            return False
        if solved is not self._last_raw and solved is not self._prev_raw:
            return False
        shift = 0.0
        for star in tset.stars:
            x0, y0 = wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            x1, y1 = tracked.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            d = math.hypot(float(x1) - float(x0), float(y1) - float(y0))
            if not math.isfinite(d):
                return False
            shift = max(shift, d)
        return shift < _LOCK_FRESH_MAX_SHIFT_PX

    def _solution_refusal(self, wcs, raw) -> str | None:
        """Why a camera frame's new solution is refused (S54), or None to accept it.

        A new solution rebuilds the tracker from the stars seen where it puts
        them, so a wrong match passes the S48 check by construction (XX Cyg
        2026-09-07 045156Z frame 1: 1 anchor of 6 seen, the next frame measured
        24 px off every star). Fewer than ceil(k/2) of the current tracker's k
        anchors showing a star (SNR >= 5, S35's threshold) where the new solution
        puts them on the frame it solved refuses it: the previous solution and
        its tracker stay. No tracker (the first solve, after a slew, Open FITS or
        a set change) means no check, and neither does a camera frame's solution while
        the reference is an opened FITS's (S59): a run's first sub is measured through
        the file's solution with anchors chosen on the file's frame (S56), which held
        the camera's correct solution to the file's field. Called by the controller
        (``_on_worker_solved``).

        3 consecutive refused solutions that agree with each other within
        ``_REPOINT_AGREE_PX`` (S54 as amended on 2026-11-15, as S55 moves the scale
        reference): the field moved without a reported slew (camera-only, another
        app), the third is accepted and logged.
        """
        stars = self._tracker_anchor_stars
        if self._tracker is None or not stars or raw is None:
            return None
        if self._solution_from_file and raw is not self._astrometry.solved_raw:
            return None  # S59: a file's anchors never vet a camera frame's solution
        params = PhotometryParams.from_config(self._cfg, egain=self._egain())
        if not params.track_apertures:
            return None
        green = green_plane(raw)
        seen = anchors_seen(green, wcs, stars, params, min_snr=_LOCK_MIN_SNR)
        needed = max(1, math.ceil(len(stars) / 2))
        if seen >= needed:
            self._repoint_refused = []
            return None
        self._repoint_refused = (self._repoint_refused + [wcs])[-_REPOINT_SOLVES:]
        if len(self._repoint_refused) == _REPOINT_SOLVES:
            span = solutions_span_px(self._repoint_refused, green.shape)
            if span <= _REPOINT_AGREE_PX:
                self._repoint_refused = []
                self.log_message.emit("WARN", repoint_text(seen, len(stars), span))
                return None
        return (
            f"only {seen} of the {len(stars)} anchor stars show a star where it places them"
            f" ({needed} needed: a wrong match, or the field is not there); the previous"
            " solution is kept"
        )

    def _resolve_now(self, green) -> None:
        """The field was lost: the next solve is due at once (S48).

        In a run the frame in hand is solved now (its solution serves the next
        sub). Outside a run only the next frame is due: a live point follows
        each solve, and solving the same frame again would only repeat it.
        """
        self._astrometry.make_due()
        if self._camera_service.state is CameraState.SEQUENCE and self._last_raw is not None:
            self._astrometry.on_new_frame(
                self._last_raw, green.shape, self._mount_radec(), self._session.target_radec
            )

    def _anchor_frame(self, green):
        """The frame the tracker's anchors are chosen on, with the solution exact there
        (S56 as amended on 2026-11-15, second set): the frame the current solution was
        solved on, through that raw solution, or None (unknown, or another geometry:
        the measured frame, as before).

        Chosen on the measured sub through a solution of an earlier one, only the
        stars that happened to show at the stale positions qualified after a jump:
        the lock check (S48, S56) then verified the very star that moved the
        apertures (real RR Lyr subs moved 500 px without a slew: 1 anchor, 2.16 px
        of tracker motion, the target 496 px off, flagged by a 0.16 px margin). On
        the solved frame all the anchors qualify, and the check counts those the
        measured sub shows (1 of 6 there: the lock is lost).
        """
        raw = self._astrometry.solved_raw
        wcs = self._astrometry.wcs
        if raw is None or wcs is None:
            return None
        solved = green if raw is self._last_raw else green_plane(raw)
        if solved.shape != green.shape:
            return None
        return solved, wcs

    @staticmethod
    def _build_live_tracker(
        green, wcs, tset: TargetSet, params: PhotometryParams, chosen_on=None
    ) -> tuple[ApertureTracker, list]:
        """The tracker of ``green`` on ``wcs`` (the raw solve or a set-change rebase,
        S52) and its anchor stars, chosen on ``chosen_on`` = (green plane, solution)
        when given: the solved frame, where its solution is exact (S56)."""
        pick_green, pick_wcs = chosen_on if chosen_on is not None else (green, wcs)
        candidates = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        # S69: a candidate beside a brighter star of the set (targets included) is none.
        anchors = select_tracking_anchors(
            pick_green, pick_wcs, candidates, params, neighbours=list(tset.stars)
        )
        if not anchors:
            # Comparisons too faint to steer: any star of the set will do, a
            # variable near minimum included — but only one seen where the
            # solution places it. Taking them all unseen let the tracker lock
            # on noise when the field had moved since the solve (S35).
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

    def tracked_wcs(self):
        """The reference WCS with the live rigid correction applied.

        What the page must project catalog markers / hit-tests through; falls
        back to the raw reference solve before the first tracked measurement.
        """
        wcs = self._base_wcs()
        if wcs is None or self._tracker is None:
            return wcs
        return TrackedWCS(wcs, self._tracker)

    def _base_wcs(self):
        """The solution a tracker is built on: the raw solve, or the tracked
        solution frozen at a set change since that solve (S52)."""
        wcs = self._astrometry.wcs
        if wcs is not None and self._rebase is not None and self._rebase[0] is wcs:
            return self._rebase[1]
        return wcs

    def _reset_tracker(self) -> None:
        """A new reference (a solve, a slew): the tracker starts from it."""
        self._tracker = None
        self._tracker_anchor_stars = []
        self._rebase = None
        self._repoint_refused = []  # S54: no anchors to refuse a solution against
        self._rotation_attempted = None  # S69 (a): a new solution, a new count

    def _anchors_changed(self) -> None:
        """The set's stars changed between two solves: rebuild the tracker (S52).

        The new tracker is built on the solution as tracked so far, frozen here,
        never on the raw solve. The field has drifted since that solve: a tracker
        rebuilt there kept only the stars that happened to show at the stale
        positions (a neighbour), passed the S48 check with 1 anchor of 1 and
        measured every aperture on blank sky until the next solve. In a run the
        next sub is solved at once.
        """
        wcs = self._astrometry.wcs
        if wcs is not None and self._tracker is not None and self._tracker.anchor_count:
            self._rebase = (wcs, TrackedWCS(self._base_wcs(), copy.copy(self._tracker)))
        self._tracker = None
        self._tracker_anchor_stars = []
        self._repoint_refused = []
        self._unverified_logged = False  # S56: a set change ends the episode
        if self._camera_service.state is CameraState.SEQUENCE:
            self._astrometry.make_due()

    @pyqtSlot(object, object, str)
    def _on_reference_solved(self, _wcs, _overlay, _summary: str) -> None:
        # A fresh solve *is* the new reference — accumulated rigid error and
        # the anchor geometry are stale relative to it.
        self._reset_tracker()
        solved = self._astrometry.solved_raw  # S59: an opened FITS's solution?
        self._solution_from_file = solved is not None and (
            self._last_raw_from_file and solved is self._last_raw
        )

    def _measure_photometry(self) -> None:
        """Aperture-measure the target set on the solved frame → light-curve point."""
        wcs = self._astrometry.wcs
        if wcs is None or self._last_raw is None or self._last_raw_decimated:
            return  # a decimated preview doesn't match the full-res WCS
        tset = self.target_set()
        if not tset.by_role(ROLE_TARGET):
            return
        if self._last_exposure_mid is None:
            # An opened FITS without DATE-OBS/EXPTIME: a point stamped "now"
            # would reach the curve, its CSV and the AAVSO export.
            self.log_message.emit(
                "WARN", "Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME)."
            )
            return
        selection = tset
        # S77: every star with a proper motion at the frame's date: the apertures, the
        # tracker's anchors and the lock and centring checks of this frame place it there.
        tset = tset.at_jd(julian_date(self._last_exposure_mid))
        # The recorder first: a new object (or run) resets the series FWHM, which
        # is then frozen on THIS frame. Freezing it before the reset gave the
        # first point its own aperture and the series the second frame's (S31).
        diag = self._diagnostics(tset)
        if self._phot_fwhm is None and self._last_fwhm:
            self._phot_fwhm = self._last_fwhm
        fwhm = self._phot_fwhm or DEFAULT_FWHM
        params = PhotometryParams.from_config(self._cfg, egain=self._egain())
        params = self._with_frame_scintillation(params)  # S74
        frame_no = self._diag_frame
        self._diag_frame += 1
        green = green_plane(self._last_raw)
        tracked = self._wcs_for_frame(green, tset, params)
        if self._field_lost(params):
            self.log_message.emit(
                "WARN",
                "Photometry skipped: no star of the set where the solution places it"
                " — the field moved since the solve, or clouds.",
            )
            diag.record("event", frame=frame_no, what="frame_skipped", reason="field_lost")
            self._resolve_now(green)
            return
        if self._lock_lost(green, tracked, params):
            self.log_message.emit(
                "WARN",
                "Photometry skipped: fewer than half the anchor stars show a star where the"
                " solution places them — the field moved since the solve, or clouds."
                " Re-solving.",
            )
            diag.record("event", frame=frame_no, what="frame_skipped", reason="lock_lost")
            self._resolve_now(green)
            return
        # S69 (b): each comparison and check star's centroid against its aperture.
        offsets = (
            centring_offsets(
                green,
                tracked,
                tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK),
                params,
                fwhm=fwhm,
                neighbours=list(tset.stars),
            )
            if tracked is not None
            else {}
        )
        excluded = off_centre(offsets)
        resolve = False
        unverified = self._lock_unverified(params, tset, tracked, offsets)
        if unverified:
            # S56: 1 or 2 anchors verify nothing (the anchor that moved the solution is
            # always seen) away from a fresh solution: flag the points, solve again now.
            # S69 (b): the anchors counted are those centred on their apertures.
            n = self._centred_anchors(offsets)
            if not self._unverified_logged:
                self._unverified_logged = True  # once per episode
                self.log_message.emit("WARN", lock_unverified_text(n))
            diag.record("event", frame=frame_no, what="lock_unverified", anchors=n)
            resolve = True
        else:
            self._unverified_logged = False  # a verified frame ends the episode
            # S56 (2026-11-15, second set): the sub in hand is solved too, so the
            # next sub is measured through the previous one's solution, never two
            # subs from it (one solve per run flagged every other sub).
            resolve = self._verified_on_previous_solution(params, offsets)
        rotation = tracked.rotation_deg if isinstance(tracked, TrackedWCS) else 0.0
        if rotation_resolve_due(rotation, self._rotation_attempted):
            # S69 (a): the field turned more than 2° since the solution: a solve is due
            # (once per 2° until one lands, so a failing solver never loops).
            self._rotation_attempted = rotation
            diag.record("event", frame=frame_no, what="rotation_resolve_due", rotation_deg=rotation)
            resolve = True
        if resolve:
            self._resolve_now(green)
        if excluded:
            diag.record("event", frame=frame_no, what="off_centre", stars=len(excluded))
            if not self._off_centre_logged:
                self._off_centre_logged = True  # once per episode
                self.log_message.emit("WARN", off_centre_text(len(excluded)))
        else:
            self._off_centre_logged = False

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
            green, tracked, tset, params, fwhm=fwhm, on_star=on_star, exclude=excluded
        )
        jd = julian_date(self._last_exposure_mid)
        token = filter_token(self._last_filter)  # one curve per (star, filter): S49
        if self._primary_filter is None:
            self._primary_filter = token
        self._measured_filter = token
        # The mount says where it points now: never the airmass of an opened
        # frame from another night (S34).
        pos = None if self._last_raw_from_file else self._session.last_position
        air = airmass_from_altitude(pos.altitude) if pos else None
        star_site = self._note_mount_pointing(pos)  # S78
        # Never the 0/0 default: without a site, the airmass is the mount's
        # (or none) and there is no BJD_TDB.
        lat, lon, elev = observing_site(self._config) or (None, None, 0.0)
        # S78 (amended): without a fitted site, a Settings site that does not reproduce the
        # mount's pointing gives no star its own airmass: each takes the mount's.
        own_airmass = star_site is not None or self._settings_site_reproduces(pos, lat, lon)
        diag.record(
            "frame",
            frame=frame_no,
            jd_utc=jd,
            airmass=air,
            fwhm=fwhm,
            egain=float(params.egain),  # S73: the e-/ADU and where it came from
            egain_source=params.egain_source,
        )
        self.photometry_measuring.emit()  # the page samples the CCD temp if open
        no_detection: list[str] = []  # S85: the targets measured below SNR 3
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
            # A point is worth keeping when *either* product exists. Requiring
            # the flux ratio used to discard perfectly good differential
            # magnitudes whenever every comparison was flagged suspect (the
            # ratio path rejects those, the magnitude path does not).
            has_mag = res.diff is not None and res.diff.mag is not None
            has_ratio = res.relative is not None and res.relative.flux_ratio is not None
            if not (has_mag or has_ratio):
                continue
            # S69 (b): an off-centre comparison or check star's own point is suspect.
            flagged = unverified or bool(excluded and res.star.key() in excluded)
            point = self._emit_live_point(
                res,
                jd,
                air,
                fwhm,
                (lat, lon, elev),
                token,
                flagged,
                airmass_site=star_site,
                own_airmass=own_airmass,
            )
            if point.no_detection:
                no_detection.append(res.star.auid or res.star.display_name)
        if no_detection:
            # S85: as a batch re-run records it (S67); Review reads the star records.
            diag.record("event", frame=frame_no, what="no_detection", low_snr=no_detection)
        if self._curves_dirty:
            # One whole-store re-render per frame, whatever the star count.
            self._curves_dirty = False
            self.curves_changed.emit()
        self._write_live_quality_report(selection)

    def _write_live_quality_report(self, target_set: TargetSet) -> None:
        """Persist non-destructive leave-one-out comparison diagnostics.

        The report deliberately never drops or substitutes a comparison during
        a run. It gives the observer a clear quality state and preserves the
        exact selection already recorded in ``photometry_selection.json``.
        The report is computed and shown in plain live preview too; it is
        written to disk only inside a run's folder. It vets the comparisons
        of the measured frame's filter only (S49): the run's first filter in
        ``photometry_quality.json``, another in ``photometry_quality_<filter>.json``;
        each file names its filter in a ``filter`` key (the token, S57).
        """
        token = self._measured_filter
        report = comparison_quality_report(
            target_set,
            curves_of_filter(self._lightcurves, token),
            min_points=int(self._cfg("photometry.comparison_validation_min_points", 10)),
            max_scatter_mag=float(
                self._cfg("photometry.comparison_validation_max_scatter_mag", 0.10)
            ),
            max_formal_error_mag=float(
                self._cfg("photometry.comparison_validation_max_formal_error_mag", 0.10)
            ),
        )
        self._comparison_quality_report = report
        self.comparison_quality_updated.emit(report)
        if self._active_run_root is None:
            return
        name = (
            "photometry_quality.json"
            if token == self._primary_filter
            else f"photometry_quality_{token}.json"
        )
        try:
            # S57: the file says which filter it vets (additive: readers ignore it).
            save_comparison_quality_report(self._active_run_root / name, report, filter_token=token)
        except OSError as exc:
            self.log_message.emit("WARN", f"Save photometry quality: {exc}")

    def _note_mount_pointing(self, pos) -> tuple[float, float] | None:
        """S78: add the mount's pointing to the site fit; the fitted site, or None.

        The mount reports altitude and azimuth from its own site and clock: the site
        that reproduces them over the run is the telescope's, whatever Settings says
        (X3). A pointing more than 6 hours after the last one starts a new fit (the
        telescope may have moved); a slewing mount's is not added, nor one that repeats
        the last (a lost mount's frozen poll, X1, which no site reproduces: it is frozen
        60 s after it began, as Review's ``FrozenPointing``)."""
        self._mount_frozen = False
        if pos is not None and not getattr(pos, "slewing", False):
            jd = julian_date(_utcnow())
            key = (pos.ra, pos.dec, pos.altitude, pos.azimuth)
            if key == self._mount_key and self._mount_since is not None:
                self._mount_frozen = (jd - self._mount_since) * 86_400.0 >= FROZEN_POINTING_S
                return self._site_fit.site()
            self._mount_key, self._mount_since = key, jd
            last = self._site_fit.last_jd
            if last is not None and jd - last > 0.25:
                self._site_fit = SiteFit()
            self._site_fit.add(jd, pos.ra, pos.dec, pos.altitude, pos.azimuth)
        return self._site_fit.site()

    def _settings_site_reproduces(self, pos, lat, lon) -> bool:
        """S78 (amended, Review's ``settings_site_reproduces`` on a live poll): whether
        the Settings site gives a star its own airmass without a fitted site. True when
        nothing can tell (no mount: an opened frame; a frozen pointing, whose airmass is
        stale, X1; no site), as before S78; else whether that site reproduces the
        mount's pointing within ``SITE_FIT_MAX_RMS_DEG``."""
        if pos is None or self._mount_frozen or lat is None or lon is None:
            return True
        try:
            alt, az = horizontal_at(julian_date(_utcnow()), pos.ra, pos.dec, float(lat), float(lon))
            offset = angle_between_directions(alt, az, pos.altitude, pos.azimuth)
        except (TypeError, ValueError):
            return True
        return offset <= SITE_FIT_MAX_RMS_DEG

    def _emit_live_point(
        self,
        res,
        jd: float,
        air,
        fwhm,
        site,
        token: str = "clear",
        unverified: bool = False,
        *,
        airmass_site: tuple[float, float] | None = None,
        own_airmass: bool = True,
    ) -> LcPoint:
        """Append one measured star to its (star, filter) curve + CSV and signal it.

        ``unverified``: the frame's lock rests on fewer than 3 anchors (S56), or the
        star is more than 1 px off its aperture centre (S69 b): the point is flagged
        suspect, as a batch re-run flags a frame measured without the field (S43).
        A target measured below SNR 3 holds no detection: its point is flagged suspect
        and ``no_detection`` (S85, S67's per-target rule) and sets no ``sigma_syst``.
        ``own_airmass`` False (S78, amended): the star takes the mount's airmass ``air``
        (the field centre's), the Settings site being wrong and no site fitted yet.
        Returns the point.
        """
        lat, lon, elev = site
        bjd = (
            bjd_tdb(jd, res.star.ra_deg, res.star.dec_deg, float(lat), float(lon), float(elev))
            if lat is not None and lon is not None
            else None
        )
        # Prefer the target's own altitude at the exposure midpoint over the
        # mount's last reported altitude, which is sampled at an arbitrary
        # instant. Fall back to the frame-level value when the site is unknown.
        # S78: each star's own, for the site fitted to the mount's pointing
        # (``airmass_site``) when there is one, else for the Settings site.
        a_lat, a_lon = airmass_site if airmass_site is not None else (lat, lon)
        if own_airmass and a_lat is not None and a_lon is not None:
            target_air = airmass_at(
                jd, res.star.ra_deg, res.star.dec_deg, float(a_lat), float(a_lon)
            )
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
            # S71: the comparison carrying the zero point disagrees with the others.
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
        # S85: S67's per-target rule when the point is measured, not only at Review.
        flag_no_detection(point, res.star.role, getattr(res.phot, "snr", None))
        key = curve_key(res.star, token)
        lc = self._lightcurves.get(key)
        if lc is None or lc.role != res.star.role:
            # A star whose role changed starts a new curve (S33): a comparison's
            # leave-one-out magnitudes and a check's are different quantities.
            if lc is not None:
                self._curves_dirty = True  # the old curve leaves the display
                self._preview_csvs.pop(key, None)  # ...and keeps its own file
            elif any(c.filter_name != token for c in self._lightcurves.values()):
                # A second filter: every series is relabelled with its filter.
                self._curves_dirty = True
            lc = LightCurve(
                auid=res.star.auid or "",
                name=res.star.display_name,
                role=res.star.role,
                filter_name=token,
            )
            self._lightcurves[key] = lc
        lc.append(point)
        floor_changed = self._apply_systematic_floor(lc)
        if floor_changed:
            # All prior values may have gained the shared systematic floor,
            # so replay the authoritative store rather than leaving stale bars
            # in the live panel: once, after the frame's last star
            # (_measure_photometry emits curves_changed).
            self._curves_dirty = True
        else:
            multi = any(c.filter_name != token for c in self._lightcurves.values())
            self.photometry_point.emit(
                PhotometryPoint(
                    key=key,
                    name=series_label(lc, multi),
                    jd=jd,
                    mag=point.mag,
                    mag_err=point.mag_err,
                    saturated=point.saturated,
                    role=res.star.role,
                    relative_flux=point.relative_flux,
                    relative_flux_err=point.relative_flux_err,
                )
            )
        try:
            lc.to_csv(self._photometry_csv_path(res.star, token))
        except OSError as exc:
            self.log_message.emit("WARN", f"photometry.csv: {exc}")
        return point

    def _apply_systematic_floor(self, curve: LightCurve) -> bool:
        """Apply the star_var_script-compatible run-level uncertainty floor."""
        manual = self._cfg("photometry.systematic_floor_mag", None)
        floor = estimate_systematic_floor(
            [
                (point.jd_utc, point.mag, point.formal_mag_err or point.mag_err)
                for point in curve.points
                if math.isfinite(point.mag)
                and math.isfinite(point.formal_mag_err or point.mag_err)
                and not point.no_detection  # S85: no star there (S67)
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

    # ------------------------------------------------------------------
    # FITS save
    # ------------------------------------------------------------------

    def _save_fits_async(
        self, arr: np.ndarray, start_dt: datetime, end_dt: datetime, used=None
    ) -> None:
        """Write a Take-shot frame off the UI thread.

        ``used`` is the worker's :class:`FrameSettings` for this frame: its
        exposure, gain and form snapshot (object, filter, frame type) are the
        ones the frame was exposed with. The current form is only a fallback.
        """
        params = self._params()
        if used is not None and used.tag is not None:
            params = used.tag
        exposure = used.exposure_s if used is not None else params.exposure_s
        gain = used.gain if used is not None else params.gain

        pos = self._session.last_position
        target = self._session.target_radec
        site = observing_site(self._config) or (None, None, None)
        ctx_kwargs = {
            "ra": pos.ra if pos else None,
            "dec": pos.dec if pos else None,
            "altitude": pos.altitude if pos else None,
            "azimuth": pos.azimuth if pos else None,
            "target_ra": target[0] if target else None,
            "target_dec": target[1] if target else None,
            "object_name": params.object_name,
            "observer": (self._config.get("observer.name") or "").strip(),
            "site_lat": site[0],
            "site_lon": site[1],
            "site_elev": site[2],
            "software": _SOFTWARE,
            "egain_table": self._cfg("camera.egain_table", {}) or {},
        }

        camera = self._session.camera
        wheel = self._session.filterwheel
        base = self._sessions_base()
        object_name = params.object_name
        form_filter = params.filter_name
        # Capture the engine's signal (long-lived) — never a page method.
        log_emit = self.log_message.emit

        frame_type = params.frame_type

        class _Task(QRunnable):
            def run(self) -> None:
                # Header truthfulness, as the sequence does: FILTER (and the
                # folder/file name) come from the wheel, not from the form,
                # which a sequence or any outside move leaves stale.
                filter_name = _wheel_filter_name(wheel, form_filter, log_emit)
                folder = FITSWriter.session_folder(
                    base, object_name, start_dt, frame_type, filter_name
                )
                frame_idx = 1
                while True:
                    filename = FITSWriter.build_filename(
                        object_name, frame_type, start_dt, exposure, filter_name, frame_idx, gain
                    )
                    path = folder / filename
                    if not path.exists():
                        break
                    frame_idx += 1

                ccd_temp = camera.get_ccd_temperature() if camera else None
                egain_d = camera.get_electrons_per_adu() if camera else None
                offset_v = camera.get_offset() if camera else None
                readout = camera.get_readout_mode_name() if camera else None

                ctx = FrameContext(
                    ccd_temp=ccd_temp,
                    egain_driver=egain_d,
                    offset=offset_v,
                    readout_mode=readout,
                    filter_name=filter_name,
                    **ctx_kwargs,
                )
                # QA headers measured on THIS array, as a sequence frame does
                # (the display's last metrics belong to another, maybe
                # decimated, frame). Best-effort: never block the save.
                try:
                    metrics = frame_metrics(arr)
                    field = detect_stars(arr)
                    ctx.hfd = metrics.hfd
                    ctx.star_count = metrics.star_count
                    ctx.sky_adu = metrics.sky_adu
                    ctx.fwhm = field.mean_fwhm
                    ctx.eccentricity = field.mean_eccentricity
                except Exception:  # pragma: no cover - metrics are best-effort
                    logger.warning("Frame metrics failed — saving without QA", exc_info=True)
                try:
                    FITSWriter.write(
                        arr=arr,
                        path=path,
                        exposure_start=start_dt,
                        exposure_end=end_dt,
                        exposure_time=exposure,
                        gain=gain,
                        image_type=frame_type,
                        context=ctx,
                        overwrite=False,
                    )
                    log_emit("OK", f"Saved {path.name}")
                except Exception as exc:
                    log_emit("ERROR", f"FITS save failed: {exc}")

        QThreadPool.globalInstance().start(_Task())

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    #: Total time budget for stopping all engine workers at shutdown. The old
    #: chained waits could block the UI thread ~35s worst case; now every
    #: worker gets its stop REQUEST first, then they wind down concurrently
    #: and we join within one global deadline.
    _SHUTDOWN_BUDGET_S = 5.0

    def shutdown(self) -> None:
        """Stop every engine-owned worker within a bounded budget.

        Call before ``session.shutdown()`` — the workers hold device
        references. Order: request every stop (non-blocking flags), then join
        each thread with whatever remains of the global budget; a worker that
        misses the deadline is logged and abandoned rather than blocking the
        UI thread forever. Safe to call twice.
        """
        # Phase 1 — request everything to stop; nothing blocks here.
        if self._sequence is not None:
            self._sequence.stop()
        if self._preview is not None:
            self._preview.stop()
        if self._autofocus is not None:
            self._autofocus.stop()

        # Phase 2 — join with one shared deadline.
        deadline = time.monotonic() + self._SHUTDOWN_BUDGET_S

        def _join(worker, label: str) -> None:
            if worker is None or not worker.isRunning():
                return
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if not worker.wait(remaining_ms):
                logger.warning(
                    "Shutdown: %s missed the %.0fs budget — abandoned",
                    label,
                    self._SHUTDOWN_BUDGET_S,
                )

        _join(self._sequence, "sequence worker")
        self._sequence = None
        _join(self._preview, "preview worker")
        self._preview = None
        self._live_requested = False
        _join(self._autofocus, "autofocus worker")
        self._autofocus = None
        remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
        self._astrometry.wait(remaining_ms)
        _join(self._catalog_worker, "catalog worker")
        self._catalog_worker = None

        if self._diag is not None:
            self._diag.close()
            self._diag = None
