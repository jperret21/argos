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

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot

from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar
from argos.core.config import Config
from argos.core.imaging.astrometry_session import field_geometry
from argos.core.imaging.fits_writer import FITSWriter, FrameContext
from argos.core.imaging.green import green_plane
from argos.core.imaging.platesolve import angular_separation_deg
from argos.core.photometry.airmass import airmass_from_altitude, bjd_tdb, julian_date
from argos.core.photometry.lightcurve import LcPoint, LightCurve
from argos.core.photometry.params import DEFAULT_FWHM, PhotometryParams, measure_frame
from argos.core.photometry.tracking import ApertureTracker, TrackedWCS
from argos.core.session.device_session import DeviceSession
from argos.core.session.diagnostics import SessionDiagnostics
from argos.core.session.types import LiveFrame, PhotometryPoint
from argos.workers.astrometry_controller import AstrometryController
from argos.workers.autofocus_worker import AutofocusWorker
from argos.workers.camera_service import CameraService, CameraState
from argos.workers.catalog_worker import CatalogRequest, CatalogWorker
from argos.workers.exposure_worker import LivePreviewWorker
from argos.workers.sequence_worker import SequenceWorker

logger = logging.getLogger(__name__)

_SOFTWARE = "Argos v0.2.0-redesign"


def _is_light_frame(frame_type: str) -> bool:
    """Shutter semantics for a CameraDock frame type — darks/bias expose with
    ``light=False`` so single shots are honest about what they captured."""
    return frame_type not in ("Dark Frame", "Bias Frame")


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
        self._sequence: SequenceWorker | None = None
        self._seq_object = ""  # object name of the running sequence (for the strip)
        self._on_complete = "Nothing"  # end-of-sequence mount action (plan option)

        # Single-shot capture: number of upcoming preview frames to save.
        self._capture_pending = 0
        # Live loop: True while the user has explicitly started Live (a single
        # Take-shot also spins the preview worker, but only transiently).
        self._live_requested = False

        # Authoritative last frame for solve/photometry. ``decimated`` marks a
        # half-quality preview whose plate scale would poison a solve.
        self._last_raw: np.ndarray | None = None
        self._last_raw_decimated = False
        self._green_shape: tuple[int, int] | None = None  # of the last processed frame
        self._last_metrics = None  # last FrameMetrics, for FITS QA headers
        self._last_fwhm: float | None = None  # mean detected-star FWHM (green px)
        self._last_exposure_mid: datetime | None = None  # exposure midpoint (UTC)

        # Live plate-solve lifecycle + auto-solve policy (§6, shared pipeline).
        self._astrometry = AstrometryController(self._cfg, self)
        self._astrometry.failed.connect(self._on_solve_failed)
        self._astrometry.state.connect(self.action_changed)
        self._astrometry.solved.connect(self._on_reference_solved)

        # §6 P1: live catalog (VSX/VSP) + persistent target set.
        self._catalog_worker: CatalogWorker | None = None
        self._variables: list = []
        self._comparisons: list = []
        self._catalog_centre: tuple[float, float] | None = None  # (ra_deg, dec_deg)
        self._target_set: TargetSet | None = None

        # §6 P4: live photometry preview state.
        self._lightcurves: dict[str, LightCurve] = {}  # key → per-target curve

        # P11 flight recorder for the live measurement path — created lazily
        # on the first measured frame, re-created when the object changes.
        self._diag: SessionDiagnostics | None = None
        self._diag_object: str | None = None
        self._diag_frame = 0

        # P7: one aperture radius per series — the FWHM is frozen on the first
        # measured frame and only re-sampled after a refocus or object change,
        # so the aperture size doesn't inject correlated variance into the curve.
        self._phot_fwhm: float | None = None

        # W1: live aperture tracker — rigid rotation/drift correction between
        # solves, so apertures and catalog markers stay on the stars during an
        # alt-az sequence. Rebuilt on a fresh solve or a target-set change.
        self._tracker: ApertureTracker | None = None

        # Last sequence directory (for the photometry setup window).
        self._last_sequence_dir: Path | None = None

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
    def lightcurves(self) -> dict[str, LightCurve]:
        return self._lightcurves

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

    @pyqtSlot(object, object, object, object)
    def _on_frame(self, preview_arr, full_arr, start_dt, end_dt) -> None:
        # Update worker settings for the next frame from the dock form. The
        # preview scale (Full/Half quality) only shapes the display pipeline —
        # saved FITS always use the full-resolution readout below.
        params = self._params()
        if self._preview:
            self._preview.update_settings(
                params.exposure_s,
                params.gain,
                scale=self._preview_scale(),
                light=_is_light_frame(params.frame_type),
            )

        try:  # exposure-midpoint time → the light curve's true epoch
            self._last_exposure_mid = start_dt + (end_dt - start_dt) / 2
        except (TypeError, ValueError):
            self._last_exposure_mid = None
        # Publish the (possibly decimated) preview; flag it so plate-solve /
        # photometry skip half-quality frames (their plate scale is wrong).
        self._last_raw_decimated = preview_arr.shape != full_arr.shape
        self._last_raw = preview_arr
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
            self._capture_pending -= 1
            self._save_fits_async(full_arr, start_dt, end_dt)
            if self._capture_pending == 0 and not self._live_requested:
                # Transient Take-shot loop done; Live keeps going (its release
                # would be a no-op here because LIVE owns the camera).
                self._camera_service.release(CameraState.SINGLE)

    def _on_camera_will_disconnect(self) -> None:
        """The session is about to drop the camera — stop using it first."""
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
        self._sequence = SequenceWorker(
            camera=self._session.camera,
            telescope=self._session.telescope,
            filterwheel=self._session.filterwheel,
            plan=plan,
            frame_context_provider=self._sequence_frame_context,
            base_dir=self._sessions_base(),
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

        self._sequence.start()
        self.sequence_running.emit(True)
        total = sum(s.count for s in plan.steps if s.enabled and s.count > 0) * max(1, plan.repeat)
        self.log_message.emit("CMD", f"Sequence started — {total} frame(s).")
        return True

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

    @pyqtSlot(object)
    def _on_seq_frame_image(self, full_arr) -> None:
        self._last_raw_decimated = False  # sequence frames are always full-res
        self._last_raw = full_arr
        self.frame_ready.emit(
            LiveFrame(preview=full_arr, full=full_arr, start=None, end=None, decimated=False)
        )

    def _on_seq_frame_saved(self, path: str, record) -> None:
        # Track the last sequence directory for the photometry setup window.
        self._last_sequence_dir = Path(path).parent
        if record is not None and getattr(record, "timestamp", None):
            try:
                start = datetime.fromisoformat(str(record.timestamp).replace("Z", "+00:00"))
                self._last_exposure_mid = start + timedelta(seconds=(record.exposure_s or 0) / 2.0)
            except (TypeError, ValueError):
                pass
        self.frame_saved.emit(path, record)  # the page logs the summary line
        # P5: one differential point per saved sub (uses the latest solve's WCS).
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
        # Hand the camera back (state_changed → "Idle" in the status bar). If
        # the sequence died while a mid-run autofocus held the camera, this
        # just cancels the pending resume — AF releases to IDLE on its own.
        self._camera_service.release(CameraState.SEQUENCE)
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
            site_lat=self._config.get("site.latitude"),
            site_lon=self._config.get("site.longitude"),
            site_elev=self._config.get("site.elevation"),
            software=_SOFTWARE,
            ccd_temp=cam.get_ccd_temperature() if cam else None,
            egain_driver=cam.get_electrons_per_adu() if cam else None,
            offset=cam.get_offset() if cam else None,
            readout_mode=cam.get_readout_mode_name() if cam else None,
        )

    def _sessions_base(self) -> Path:
        try:
            return self._config.sessions_path.parent
        except AttributeError:
            return Path.home() / "Argos"

    def _diagnostics(self, tset) -> SessionDiagnostics:
        """The live flight recorder for the current object (P11).

        One jsonl per object next to the light-curve CSVs; a change of object
        closes the previous file and starts a fresh frame counter.
        """
        obj = tset.object_name or "untitled"
        if self._diag is None or self._diag_object != obj:
            if self._diag is not None:
                self._diag.close()
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in obj)
            self._diag = SessionDiagnostics(
                self._sessions_base() / "targets" / f"{safe or 'untitled'}_live_diagnostics.jsonl",
                enabled=bool(self._cfg("diagnostics.enabled", True)),
            )
            self._diag_object = obj
            self._diag_frame = 0
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

    def stop_autofocus(self) -> None:
        if self._autofocus and self._autofocus.isRunning():
            self._autofocus.stop()
            self._autofocus.wait(10_000)
        self._autofocus = None
        self.autofocus_state.emit(False)
        # Hand the camera back promptly (the worker's queued finished signal
        # would also release, but that lands on a later event-loop turn).
        self._camera_service.release(CameraState.AUTOFOCUS)

    @pyqtSlot(str)
    def _on_af_error(self, message: str) -> None:
        self.log_message.emit("ERROR", f"AF: {message}")

    def _on_af_finished(self) -> None:
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
                self._last_raw, green_shape, self._mount_radec(), self._session.target_radec
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
            self._last_raw, self._green_shape, mount, self._session.target_radec
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
        self._catalog_centre = None
        self._reset_tracker()

    # ------------------------------------------------------------------
    # Catalog (VSX/VSP once per field)
    # ------------------------------------------------------------------

    def maybe_fetch_catalog(self) -> None:
        """Fetch VSX/VSP once per field (re-fetch only when the centre moves)."""
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            return
        geom = field_geometry(self._astrometry.wcs, self._green_shape)
        if geom is None:
            return
        ra_deg, dec_deg, radius_deg, fov_arcmin = geom
        if self._catalog_centre is not None and (self._variables or self._comparisons):
            moved = angular_separation_deg(
                ra_deg / 15.0, dec_deg, self._catalog_centre[0] / 15.0, self._catalog_centre[1]
            )
            if moved < radius_deg:
                return  # same field → reuse the cached catalog
        self._catalog_centre = (ra_deg, dec_deg)
        req = CatalogRequest(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            fov_arcmin=fov_arcmin,
            mag_limit=float(self._cfg("catalog.mag_limit", 15.0)),
            max_results=int(self._cfg("catalog.max_results", 250)),
            include_suspected=bool(self._cfg("catalog.include_suspected", True)),
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
        self.catalog_ready.emit(result)  # the page re-projects onto the WCS
        if self._variables:
            self.log_message.emit("OK", f"Catalog: {len(self._variables)} variable(s) in field")

    # ------------------------------------------------------------------
    # Target set persistence (targets.json per object)
    # ------------------------------------------------------------------

    def _object_name(self) -> str:
        params = self._params() if self._params is not None else None
        name = (params.object_name if params else "") or "untitled"
        return name.strip() or "untitled"

    def _target_path(self, obj: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (obj or "untitled"))
        return self._sessions_base() / "targets" / f"{safe or 'untitled'}.json"

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
        except OSError as exc:
            self.log_message.emit("ERROR", f"Save targets: {exc}")

    def set_target_role(self, star: TargetStar) -> None:
        tset = self.target_set()
        tset.set_role(star)
        self._save_target_set(tset)
        self._reset_tracker()  # the anchor constellation changed
        self.targets_changed.emit(tset)

    def remove_target(self, key: str) -> None:
        tset = self.target_set()
        tset.remove(key)
        self._save_target_set(tset)
        self._reset_tracker()  # the anchor constellation changed
        self.targets_changed.emit(tset)

    # ------------------------------------------------------------------
    # Live photometry (§6 P4/P5)
    # ------------------------------------------------------------------

    def _egain(self) -> float:
        """e-/ADU for the photometric error: config egain_table[gain] → driver → 1."""
        table = self._cfg("camera.egain_table", {}) or {}
        gain = str(self._params().gain)
        if isinstance(table, dict) and gain in table:
            try:
                return float(table[gain])
            except (TypeError, ValueError):
                pass
        value = self._session.egain_driver()
        if value:
            return float(value)
        return 1.0

    def _photometry_csv_path(self, star) -> Path:
        obj = self.target_set().object_name or "untitled"
        tag = star.auid or star.display_name
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{obj}_{tag}")
        return self._sessions_base() / "targets" / f"{safe or 'photometry'}.csv"

    def _wcs_for_frame(self, green, tset: TargetSet, params: PhotometryParams):
        """Reference WCS, rigid-corrected by the live tracker when enabled.

        Same recipe as the batch worker: the tracker is built lazily on the
        first measured frame, anchors on the set's stable stars, and keeps its
        last good transform when a frame has no usable anchor (clouds). Every
        refit is signalled so the page re-projects the catalog markers — the
        fix for the field bug where the variable-star diamonds froze at the
        solve position while the alt-az field rotated under them.
        """
        wcs = self._astrometry.wcs
        if not params.track_apertures:
            return wcs
        if self._tracker is None:
            self._tracker = self._build_live_tracker(green.shape, wcs, tset, params)
        self._tracker.update(green)
        if not self._tracker.anchors_used:
            self.log_message.emit("WARN", "Photometry: no anchor star found — apertures unguided")
        self.apertures_tracked.emit()
        return TrackedWCS(wcs, self._tracker)

    @staticmethod
    def _build_live_tracker(
        shape: tuple[int, int], wcs, tset: TargetSet, params: PhotometryParams
    ) -> ApertureTracker:
        anchors = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        if not anchors:  # a variable near minimum is a poor centroid
            anchors = list(tset.stars)
        xy = [wcs.world_to_pixel_deg(s.ra_deg, s.dec_deg) for s in anchors]
        h, w = shape
        return ApertureTracker(
            [(float(x), float(y)) for x, y in xy],
            frame_center=(w / 2.0, h / 2.0),
            search_r=max(8.0, 2.0 * params.aperture_px(None)),
        )

    def tracked_wcs(self):
        """The reference WCS with the live rigid correction applied.

        What the page must project catalog markers / hit-tests through; falls
        back to the raw reference solve before the first tracked measurement.
        """
        wcs = self._astrometry.wcs
        if wcs is None or self._tracker is None:
            return wcs
        return TrackedWCS(wcs, self._tracker)

    def _reset_tracker(self) -> None:
        self._tracker = None

    @pyqtSlot(object, object, str)
    def _on_reference_solved(self, _wcs, _overlay, _summary: str) -> None:
        # A fresh solve *is* the new reference — accumulated rigid error and
        # the anchor geometry are stale relative to it.
        self._reset_tracker()

    def _measure_photometry(self) -> None:
        """Aperture-measure the target set on the solved frame → light-curve point."""
        wcs = self._astrometry.wcs
        if wcs is None or self._last_raw is None or self._last_raw_decimated:
            return  # a decimated preview doesn't match the full-res WCS
        tset = self.target_set()
        if not tset.by_role(ROLE_TARGET):
            return
        if self._phot_fwhm is None and self._last_fwhm:
            self._phot_fwhm = self._last_fwhm
        fwhm = self._phot_fwhm or DEFAULT_FWHM
        params = PhotometryParams.from_config(self._cfg, egain=self._egain())
        diag = self._diagnostics(tset)
        frame_no = self._diag_frame
        self._diag_frame += 1
        green = green_plane(self._last_raw)
        results = measure_frame(
            green,
            self._wcs_for_frame(green, tset, params),
            tset,
            params,
            fwhm=fwhm,
            on_star=lambda s, phot, x, y: diag.star(frame_no, s, phot, x, y),
        )
        jd = julian_date(self._last_exposure_mid or datetime.now(timezone.utc))
        pos = self._session.last_position
        air = airmass_from_altitude(pos.altitude) if pos else None
        lat, lon = self._cfg("site.latitude", None), self._cfg("site.longitude", None)
        elev = self._cfg("site.elevation", 0.0) or 0.0
        diag.record("frame", frame=frame_no, jd_utc=jd, airmass=air, fwhm=fwhm)
        self.photometry_measuring.emit()  # the page samples the CCD temp if open
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
            if res.diff is None or res.diff.mag is None:
                continue
            self._emit_live_point(res, jd, air, fwhm, (lat, lon, elev))

    def _emit_live_point(self, res, jd: float, air, fwhm, site) -> None:
        """Append one measured star to its live curve + CSV and signal it."""
        lat, lon, elev = site
        bjd = (
            bjd_tdb(jd, res.star.ra_deg, res.star.dec_deg, float(lat), float(lon), float(elev))
            if lat is not None and lon is not None
            else None
        )
        point = LcPoint(
            jd_utc=jd,
            mag=res.diff.mag,
            mag_err=res.diff.mag_err or 0.0,
            bjd_tdb=bjd,
            airmass=air,
            fwhm=fwhm,
            sky_adu=res.phot.sky_adu if res.phot else None,
            comps_used=res.diff.comps_used,
            saturated=bool(res.phot and res.phot.saturated),
        )
        key = res.star.auid or res.star.display_name
        lc = self._lightcurves.setdefault(
            key, LightCurve(auid=res.star.auid or "", name=res.star.display_name)
        )
        lc.append(point)
        self.photometry_point.emit(
            PhotometryPoint(
                key=key,
                name=res.star.display_name,
                jd=jd,
                mag=res.diff.mag,
                mag_err=res.diff.mag_err or 0.0,
                saturated=point.saturated,
            )
        )
        try:
            lc.to_csv(self._photometry_csv_path(res.star))
        except OSError as exc:
            self.log_message.emit("WARN", f"photometry.csv: {exc}")

    # ------------------------------------------------------------------
    # FITS save
    # ------------------------------------------------------------------

    def _save_fits_async(self, arr: np.ndarray, start_dt: datetime, end_dt: datetime) -> None:
        params = self._params()
        frame_idx = 1

        pos = self._session.last_position
        target = self._session.target_radec
        ctx_kwargs = {
            "ra": pos.ra if pos else None,
            "dec": pos.dec if pos else None,
            "altitude": pos.altitude if pos else None,
            "azimuth": pos.azimuth if pos else None,
            "target_ra": target[0] if target else None,
            "target_dec": target[1] if target else None,
            "object_name": params.object_name,
            "filter_name": params.filter_name,
            "observer": (self._config.get("observer.name") or "").strip(),
            "site_lat": self._config.get("site.latitude"),
            "site_lon": self._config.get("site.longitude"),
            "site_elev": self._config.get("site.elevation"),
            "software": _SOFTWARE,
            "hfd": self._last_metrics.hfd if self._last_metrics else None,
            "star_count": self._last_metrics.star_count if self._last_metrics else None,
            "sky_adu": self._last_metrics.sky_adu if self._last_metrics else None,
        }

        camera = self._session.camera
        base = self._sessions_base()
        folder = FITSWriter.session_folder(
            base,
            params.object_name,
            start_dt,
            params.frame_type,
            params.filter_name,
        )
        filename = FITSWriter.build_filename(
            params.object_name,
            params.frame_type,
            start_dt,
            params.exposure_s,
            params.filter_name,
            frame_idx,
        )
        path = folder / filename
        # Capture the engine's signal (long-lived) — never a page method.
        log_emit = self.log_message.emit

        gain = params.gain
        exposure = params.exposure_s
        frame_type = params.frame_type

        class _Task(QRunnable):
            def run(self) -> None:
                ccd_temp = camera.get_ccd_temperature() if camera else None
                egain_d = camera.get_electrons_per_adu() if camera else None
                offset_v = camera.get_offset() if camera else None
                readout = camera.get_readout_mode_name() if camera else None

                ctx = FrameContext(
                    ccd_temp=ccd_temp,
                    egain_driver=egain_d,
                    offset=offset_v,
                    readout_mode=readout,
                    **ctx_kwargs,
                )
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
