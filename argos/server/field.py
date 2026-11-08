"""The live field: identification, catalogue, layers, tracking and star selection.

Rows A32-A33 (inputs), A43-A49 of ``web/spec/README.md`` §4.3. A Qt-free port
of what the Qt app split between ``AstrometryController``
(``astrometry_controller.py``), ``AcquisitionEngine`` (solve, catalogue,
tracker: ``acquisition_engine.py:1017-1240, 1542-1603``) and
``ImagingPage`` (overlays, click identification, invalidation:
``imaging_page.py:746-1300, 1393-1800, 2501-2563, 2667-2715``).

Threads (none is the event loop; none holds the hub lock across work):

- a **solve** thread per solve (manual: a ``field_solve`` job; automatic:
  a plain thread), running ASTAP through :func:`field_solve.solve_green`,
  killed on cancel;
- the **frame** thread: per new frame (latest wins) the geometry guard, the
  tracking transform (A48), the followed selection and the automatic
  identification policy;
- the **catalogue** thread: one fetch per field (A46);
- the **projection** thread: rebuilds the layers (A47) after a solve, a
  catalogue, a role or a display setting (bursts coalesce);
- an **identify** thread per point identification (A49), superseded by a
  newer click.

State is guarded by the hub lock and published with ``Hub._publish`` under
it, so events leave in the order of the changes.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from argos.core import catalog as core_catalog
from argos.core.catalog.photometry import separation_arcmin
from argos.core.catalog.point_identity import PointIdentityLookupError, identify_point_source
from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, ROLE_TARGET, TargetStar
from argos.core.imaging.astrometry_session import (
    build_solve_settings,
    field_geometry,
    full_res_scale,
    overlay_for,
    wcs_from_result,
)
from argos.core.imaging.debayer import VIEW_G, extract_plane
from argos.core.imaging.green import green_plane, green_shape
from argos.core.imaging.metrics import (
    TRACK_SNAP_SEARCH,
    arcsec_per_green_px,
    detect_stars,
    measure_star_at,
)
from argos.core.imaging.platesolve import angular_separation_deg, format_dec_dms, format_ra_hms
from argos.core.photometry.aperture import measure_aperture
from argos.core.photometry.tracking import TrackedWCS, select_tracking_anchors
from argos.server import field_catalog as fc
from argos.server.errors import ApiError
from argos.server.field_measure import FrameMeasurer
from argos.server.field_track import FieldTracker, vote_transform
from argos.server.field_solve import (
    SolveCancelled,
    frame_shape_of,
    frame_wcs_record,
    grid_record,
    solve_green,
    to_frame,
    to_green,
    wire_mirrored,
)
from argos.server.jobs import JobCancelled, JobContext
from argos.server.state import utc_iso
from argos.server.targets import pending_star, star_from_pending

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: Default hit tolerance (frame px) when the client sends none: Qt's 10 green px.
DEFAULT_TOL_PX = 20.0
#: Fallback tracking anchors detected on the solved frame (no target set).
MAX_DETECTED_ANCHORS = 6
#: Sources detected on the solved frame for the detected-only rules (Qt kept
#: the 120 brightest, ``metrics._MAX_STARS``: too few on a rich field, so
#: measurable comparisons read "not detected").
MAX_DETECTED_SOURCES = 2000
#: Brightest solved-frame sources that vote when a lost lock is re-acquired.
REACQUIRE_REFERENCE_STARS = 300
#: Keys that change what a catalogue fetch asks (debounced refetch, A9).
FETCH_KEYS = frozenset(
    {
        "catalog.mag_limit",
        "catalog.max_results",
        "catalog.include_suspected",
        "catalog.field_stars_enabled",
        "catalog.field_stars_mag_limit",
        "catalog.identification_max_objects",
        "catalog.named_objects_enabled",
        "catalog.named_objects_allow_network",
        "catalog.exoplanet_hosts_enabled",
        "catalog.exoplanet_hosts_allow_network",
    }
)
#: Keys that only change how the cached field is drawn (re-projection).
DISPLAY_KEYS = frozenset(
    {
        "catalog.display_mag_limit",
        "catalog.field_stars_detected_only",
        "catalog.show_essential_objects",
        "catalog.show_cached_exoplanets",
        "photometry.aperture_min_px",
        "photometry.aperture_fwhm_mult",
    }
)
_REFETCH_DEBOUNCE_S = 0.5
#: Logged once per loss of the tracking lock (Qt logged it on every frame,
#: ``acquisition_engine.py:1563-1564``).
LOST_TEXT = "Tracking: no anchor star found — overlays and apertures unguided"
FILE_SOLUTION_TEXT = (
    "This solution is for an opened file, not where the mount points: "
    "identify a camera frame first."
)

INVALIDATION_TEXT = {
    "slew": "GoTo — the field moved; identify it again.",
    "center": "Centring slew — the field moved; identify it again.",
    "mount_moved": (
        "Mount pointing changed outside ARGOS — stale astrometry overlays cleared. "
        "Plate-solve the current frame."
    ),
    "geometry": "Frame geometry changed — WCS overlays cleared (solve again).",
    "file_opened": "A FITS image was opened — identify its field.",
    "source_changed": "Frames now come from another source — identify the field again.",
}


@dataclass
class Frame:
    """The newest frame the field works on."""

    seq: int
    raw: np.ndarray
    origin: str
    hint: tuple[float, float] | None = None  # (ra_hours, dec_deg) from a FITS header


@dataclass
class Pilot:
    """The newest frame of the solved geometry with the tracked solution."""

    wcs: Any
    green_shape: tuple[int, int]
    raw: np.ndarray
    seq: int


def _origin_family(origin: str) -> str:
    return "file" if origin == "file" else "camera"


class FieldService:
    """Owns the field state and its events (``field``, ``catalog``, ``field_layers``,
    ``field_transform``, ``selection``)."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        #: Injectable for tests (no network in the suite).
        self.catalog_api: Any = core_catalog
        self.identify_point: Callable[..., Any] = identify_point_source

        self._state = "none"
        self._auto = False
        self._auto_source: str | None = None
        self._auto_before_sequence: bool | None = None
        self._solving: dict[str, Any] | None = None
        self._solve_cancel: threading.Event | None = None
        self._reason: str | None = None
        self._message: str | None = None
        self._generation = 0
        self._invalidations = 0
        self._revision = 0
        self._solution: dict[str, Any] | None = None
        self._wcs: Any = None
        self._green_shape: tuple[int, int] | None = None
        self._wcs_record: dict[str, Any] | None = None
        self._grid: dict[str, Any] | None = None
        self._reticle: dict[str, Any] | None = None
        self._last_attempt: dict[str, Any] | None = None
        self._attempt_mono = 0.0
        self._attempt_radec: tuple[float, float] | None = None
        self._ref_raw: np.ndarray | None = None
        self._ref_seq: int | None = None
        self._detected: list[tuple[float, float]] = []
        self._detected_anchors: list[tuple[float, float, float]] = []
        #: The state a cancelled or discarded attempt returns to.
        self._prior_state = "none"
        self._center_flag = False
        self._frame: Frame | None = None
        self._family: str | None = None

        # catalogue (A46)
        self._catalog_result: fc.CatalogResult | None = None
        self._catalog_centre: tuple[float, float] | None = None
        self._catalog_token = 0
        self._catalog_running = False
        self._catalog: dict[str, Any] = self._catalog_idle()
        self._point_identities: list = []
        self._refetch_timer: threading.Timer | None = None

        # layers (A47) and tracking (A48)
        self._projection: fc.Projection | None = None
        self._layers: dict[str, Any] = self._empty_layers()
        self._layers_revision = 0
        self._quality_cache: tuple[Any, dict[str, Any] | None] | None = None
        self._tracker: FieldTracker | None = None
        #: The set changed: rebuild the constellation from the current pose.
        self._tracker_stale = False
        #: A loss was logged (once per loss).
        self._loss_logged = False
        #: Solved-frame sources (green px, flux), brightest first: re-acquisition.
        self._ref_stars: list[tuple[float, float, float]] = []
        self._anchor_source: str | None = None
        self._transform: dict[str, Any] = self._identity_transform()

        # selection (A49)
        self._selection_seq = 0
        self._selection: dict[str, Any] = {"id": None, "selection": None}
        self._pending: dict[str, Any] | None = None
        self._follow: tuple[float, float] | None = None

        # threads
        self._closed = False
        self._frame_cond = threading.Condition()
        self._frame_pending: Frame | None = None
        self._frame_thread = threading.Thread(
            target=self._frame_loop, name="argos-field-frames", daemon=True
        )
        self._project_cond = threading.Condition()
        self._project_dirty = False
        self._project_thread = threading.Thread(
            target=self._project_loop, name="argos-field-project", daemon=True
        )
        self._threads_started = False
        #: Background work in flight (tests wait on :meth:`idle`).
        self._busy = 0
        self._busy_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_threads(self) -> None:
        if not self._threads_started:
            self._threads_started = True
            self._frame_thread.start()
            self._project_thread.start()

    def close(self) -> None:
        self._closed = True
        with self._hub._lock:
            cancel = self._solve_cancel
        if cancel is not None:
            cancel.set()
        if self._refetch_timer is not None:
            self._refetch_timer.cancel()
        with self._frame_cond:
            self._frame_cond.notify_all()
        with self._project_cond:
            self._project_cond.notify_all()

    def _work(self, delta: int) -> None:
        with self._busy_lock:
            self._busy += delta

    def idle(self) -> bool:
        """No background work queued or running (tests)."""
        with self._busy_lock:
            busy = self._busy
        with self._frame_cond:
            queued = self._frame_pending is not None
        with self._project_cond:
            dirty = self._project_dirty
        return busy == 0 and not queued and not dirty

    # ------------------------------------------------------------------
    # Records
    # ------------------------------------------------------------------

    @staticmethod
    def _catalog_idle() -> dict[str, Any]:
        return {
            "state": "idle",
            "generation": 0,
            "centre": None,
            "radius_deg": None,
            "counts": {
                "variables": 0,
                "comparisons": 0,
                "field_stars": 0,
                "named_objects": 0,
                "exoplanet_hosts": 0,
            },
            "limits": {"field_stars": 0, "named_objects": 0},
            "warnings": [],
            "error": None,
            "fetched_utc": None,
            "revision": 0,
        }

    def _empty_layers(self) -> dict[str, Any]:
        return {
            "generation": self._generation if hasattr(self, "_generation") else 0,
            "revision": 0,
            "available": False,
            "frame_shape": None,
            "display_mag_limit": 18.0,
            "aperture_r_px": None,
            "layers": {name: [] for name in fc.LAYERS},
            "counts": {name: 0 for name in fc.LAYERS},
            "candidates": [],
            "limits": None,
        }

    def _identity_transform(self) -> dict[str, Any]:
        return {
            "generation": self._generation if hasattr(self, "_generation") else 0,
            "frame_seq": None,
            "rot_deg": 0.0,
            "dx": 0.0,
            "dy": 0.0,
            "cx": 0.0,
            "cy": 0.0,
            "anchors": 0,
            "residual_px": None,
            "anchor_source": None,
            "lost_frames": 0,
            "tracking": None,
        }

    def record(self) -> dict[str, Any]:
        """The ``Field`` record (hub lock held or not: a consistent copy)."""
        with self._hub._lock:
            solving = dict(self._solving) if self._solving else None
            if solving is not None:
                solving.pop("cancel", None)
            return {
                "state": self._state,
                "auto": self._auto,
                "auto_source": self._auto_source,
                "solving": solving,
                "reason": self._reason,
                "message": self._message,
                "generation": self._generation,
                "solution": dict(self._solution) if self._solution else None,
                "wcs": self._wcs_record,
                "grid": self._grid,
                "target_reticle": self._reticle,
                "last_attempt": self._last_attempt,
                "center_available": self._center_available(),
                "revision": self._revision,
            }

    def catalog_record(self) -> dict[str, Any]:
        with self._hub._lock:
            return dict(self._catalog)

    def layers_record(self) -> dict[str, Any]:
        with self._hub._lock:
            return self._layers

    def transform_record(self) -> dict[str, Any]:
        with self._hub._lock:
            return dict(self._transform)

    def selection_record(self) -> dict[str, Any]:
        with self._hub._lock:
            return self._selection

    def snapshots(self, seq: int) -> list[tuple[str, int, dict[str, Any]]]:
        """Hub lock held: what a new ``/ws/events`` client receives."""
        return [
            ("field", seq, {"type": "field", **self.record()}),
            ("catalog", seq, {"type": "catalog", **self._catalog}),
            ("field_layers", seq, {"type": "field_layers", **self._layers}),
            ("field_transform", seq, {"type": "field_transform", **self._transform}),
            ("selection", seq, {"type": "selection", **self._selection}),
        ]

    def _publish_field(self) -> None:
        """Hub lock held."""
        self._revision += 1
        record = self.record()
        self._center_flag = record["center_available"]
        self._hub._publish("field", record)
        self._hub._sync_center_available(self._center_flag)

    def refresh_center(self) -> None:
        """Hub lock held: Centre availability follows the mount, the set and GoTo."""
        value = self._center_available()
        if value != self._center_flag:
            self._publish_field()
        else:
            self._hub._sync_center_available(value)

    def _publish_catalog(self, **changes: Any) -> None:
        """Hub lock held."""
        self._catalog = {
            **self._catalog,
            **changes,
            "revision": self._catalog["revision"] + 1,
        }
        self._hub._publish("catalog", dict(self._catalog))

    def _publish_selection(self, event: dict[str, Any]) -> dict[str, Any]:
        """Hub lock held."""
        self._selection = event
        self._hub._publish("selection", event)
        return event

    # ------------------------------------------------------------------
    # Accessors for other services
    # ------------------------------------------------------------------

    @property
    def solved(self) -> bool:
        return self._wcs is not None

    def _tracked_wcs(self):
        """``tracked_wcs`` (``acquisition_engine.py:1584-1593``). Lock held."""
        if self._wcs is None or self._tracker is None:
            return self._wcs
        return TrackedWCS(self._wcs, self._tracker)

    def comparisons(self) -> list:
        with self._hub._lock:
            result = self._catalog_result
            return list(result.comparisons) if result is not None and self._wcs else []

    def pilot(self) -> Pilot | None:
        """The newest full frame of the solved geometry, through the tracked solution."""
        with self._hub._lock:
            frame = self._frame
            if self._wcs is None or frame is None:
                return None
            if green_shape(frame.raw) != self._green_shape:
                return None
            return Pilot(self._tracked_wcs(), self._green_shape, frame.raw, frame.seq)

    def project_reference(self, ra_deg: float, dec_deg: float) -> tuple[float, float] | None:
        """A sky position in reference frame px, or None (unsolved / off frame)."""
        with self._hub._lock:
            wcs, gs = self._wcs, self._green_shape
        if wcs is None or gs is None:
            return None
        x, y = wcs.world_to_pixel_deg(ra_deg, dec_deg)
        x, y = float(x), float(y)
        margin = 2.0
        if not (-margin <= x <= gs[1] + margin and -margin <= y <= gs[0] + margin):
            return None
        return to_frame(x, y)

    def solved_centre(self) -> tuple[float, float]:
        """RA (h), Dec (°) of the current frame's centre through the tracked solution.

        Only a camera frame says where the mount points: a solution of an
        opened file (another night, another pointing) must never sync it.
        """
        with self._hub._lock:
            wcs, gs = self._tracked_wcs(), self._green_shape
            solution = self._solution
        if wcs is None or gs is None:
            raise ApiError(
                409, "not_solved", "Identify the field first: centring needs a plate solution."
            )
        if solution is not None and solution.get("frame_origin") == "file":
            raise ApiError(409, "file_solution", FILE_SOLUTION_TEXT)
        height, width = gs
        return wcs.pixel_to_radec((width - 1) / 2.0, (height - 1) / 2.0)

    def _center_available(self) -> bool:
        """Lock held: Centre target can run (A29 ``center_available``)."""
        if self._wcs is None or self._hub._slots["mount"].state != "connected":
            return False
        if self._solution is not None and self._solution.get("frame_origin") == "file":
            return False  # an opened file says nothing about where the mount points
        if self._hub._goto_target is not None:
            return True
        tset = self._hub.targets._set
        return bool(tset is not None and tset.by_role(ROLE_TARGET))

    def rebase_mount_reference(self, ra_hours: float, dec_deg: float) -> None:
        """After a Sync the mount reads new coordinates for the same field."""
        with self._hub._lock:
            if self._attempt_radec is not None:
                self._attempt_radec = (float(ra_hours), float(dec_deg))

    # ------------------------------------------------------------------
    # Frames (hub hooks)
    # ------------------------------------------------------------------

    def on_frame(
        self, seq: int, raw: np.ndarray, origin: str, hint: tuple[float, float] | None = None
    ) -> None:
        """A new frame was published (camera or file); latest wins on the frame thread."""
        if raw is None or getattr(raw, "ndim", 0) != 2 or self._closed:
            return
        frame = Frame(seq=seq, raw=raw, origin=origin, hint=hint)
        family = _origin_family(origin)
        dropped = False
        with self._hub._lock:
            self._frame = frame
            previous, self._family = self._family, family
            if previous is not None and previous != family and family == "camera":
                if self._wcs is not None or self._state == "solving":
                    self._invalidate_locked("source_changed")
                    dropped = True
        if dropped:
            self._announce_invalidation("source_changed")
        self._ensure_threads()
        with self._frame_cond:
            self._frame_pending = frame
            self._frame_cond.notify()

    def _frame_loop(self) -> None:
        while True:
            with self._frame_cond:
                while self._frame_pending is None and not self._closed:
                    self._frame_cond.wait()
                if self._closed:
                    return
                frame, self._frame_pending = self._frame_pending, None
                self._work(+1)
            try:
                self._process_frame(frame)
            except Exception:
                logger.exception("Field: frame %s failed", frame.seq)
            finally:
                self._work(-1)

    def _process_frame(self, frame: Frame) -> None:
        gs = green_shape(frame.raw)
        dropped = False
        with self._hub._lock:
            if self._wcs is not None and self._green_shape is not None and gs != self._green_shape:
                self._invalidate_locked("geometry")
                dropped = True
            solved = self._wcs is not None
        if dropped:
            self._announce_invalidation("geometry")
        if solved:
            self._track(frame)
        self._follow_selection(frame)
        self._maybe_auto_solve(frame)

    # ------------------------------------------------------------------
    # Identify field (A43) and automatic identification (A44)
    # ------------------------------------------------------------------

    def solve(self) -> dict[str, Any]:
        """``POST /api/field/solve``: a ``field_solve`` job on the newest frame."""
        with self._hub._lock:
            frame = self._frame
            if frame is None:
                raise ApiError(
                    409,
                    "no_frame",
                    "No frame to solve yet — take a frame or open a FITS image first.",
                )
            if self._solving is not None:
                raise ApiError(
                    409,
                    "busy",
                    "The field is already being identified.",
                    details={"owner": self._solving.get("job_id") or "auto"},
                )
            cancel = threading.Event()
            # Claimed before the job starts: a second request is 409 at once.
            claim = {
                "mode": "manual",
                "job_id": None,
                "frame_seq": frame.seq,
                "started_utc": utc_iso(),
            }
            self._solving = claim
            self._solve_cancel = cancel
            self._prior_state, self._state = self._state, "solving"

        def body(ctx: JobContext) -> dict[str, Any]:
            relay = threading.Thread(
                target=self._relay_cancel, args=(ctx, cancel), daemon=True, name="argos-solve-relay"
            )
            relay.start()
            try:
                return self._run_solve(frame, "manual", cancel, ctx, claim)
            finally:
                cancel.set()  # ends the relay (the solve is over either way)

        try:
            job = self._hub.jobs.start("field_solve", body, resource="field", stage="queued")
        except ApiError:
            with self._hub._lock:
                if self._solving is claim:
                    self._solving = None
                    self._solve_cancel = None
                    self._state = self._prior_state
            raise
        with self._hub._lock:
            if self._solving is claim:
                claim["job_id"] = job["id"]
                self._publish_field()
        return {"job_id": job["id"], "field": self.record()}

    @staticmethod
    def _relay_cancel(ctx: JobContext, cancel: threading.Event) -> None:
        """``DELETE /api/jobs/{id}`` sets the job's event: forward it to ASTAP."""
        while not cancel.is_set():
            if ctx.cancel_event.wait(0.05):
                cancel.set()
                return

    def cancel_solve(self) -> dict[str, Any]:
        """``DELETE /api/field/solve``: kill the running ASTAP (manual or automatic)."""
        with self._hub._lock:
            cancel = self._solve_cancel
            job_id = self._solving.get("job_id") if self._solving else None
        if cancel is not None:
            cancel.set()
        if job_id is not None:
            try:
                self._hub.jobs.cancel(job_id)
            except ApiError:
                pass
        return self.record()

    def set_auto(self, enabled: bool, *, source: str = "observer") -> dict[str, Any]:
        """``PUT /api/field/auto`` (``astrometry_controller.py:82-85``)."""
        with self._hub._lock:
            changed = self._auto != bool(enabled)
            self._auto = bool(enabled)
            self._auto_source = source if enabled else None
            if changed:
                self._publish_field()
            frame = self._frame
        if changed:
            self._hub.log(
                "info",
                (
                    "Automatic field identification on"
                    if enabled
                    else "Automatic field identification off"
                ),
                source="field",
                topic="field",
            )
            if enabled and frame is not None:
                self._ensure_threads()
                with self._frame_cond:
                    if self._frame_pending is None:
                        self._frame_pending = frame
                    self._frame_cond.notify()
        return self.record()

    def arm_for_sequence(self) -> None:
        """Q-O12: a sequence keeps the field identified, even without a solution."""
        with self._hub._lock:
            self._auto_before_sequence = self._auto
        if not self._auto:
            self.set_auto(True, source="sequence")
            self._hub.log(
                "info", "Sequence: auto-solve armed for the run.", source="field", topic="field"
            )

    def disarm_after_sequence(self) -> None:
        with self._hub._lock:
            before, self._auto_before_sequence = self._auto_before_sequence, None
        if before is False:
            self.set_auto(False)

    def _due(self, mount: tuple[float, float] | None) -> bool:
        """``_due`` (``astrometry_controller.py:135-154``). Lock held."""
        if self._wcs is None:
            return True
        if (time.monotonic() - self._attempt_mono) >= float(
            self._hub.config.get("astrometry.live_resolve_s", 20.0) or 20.0
        ):
            return True
        if mount is not None and self._attempt_radec is not None:
            sep = angular_separation_deg(mount[0], mount[1], *self._attempt_radec) * 60.0
            if sep >= float(self._hub.config.get("astrometry.live_resolve_arcmin", 2.0) or 2.0):
                return True
        return False

    def _maybe_auto_solve(self, frame: Frame) -> None:
        with self._hub._lock:
            if not self._auto or self._solving is not None or self._closed:
                return
            if self._frame is None or self._frame.seq != frame.seq:
                return  # a newer frame is queued: it decides
            mount = self._mount_radec()
            if not self._due(mount):
                return
            cancel = threading.Event()
            claim = {
                "mode": "auto",
                "job_id": None,
                "frame_seq": frame.seq,
                "started_utc": utc_iso(),
            }
            self._solving = claim
            self._solve_cancel = cancel
            self._prior_state, self._state = self._state, "solving"
            self._publish_field()
        self._work(+1)

        def run() -> None:
            try:
                self._run_solve(frame, "auto", cancel, None, claim)
            except (SolveCancelled, JobCancelled, ApiError):
                pass
            except Exception:
                logger.exception("Automatic field identification crashed")
            finally:
                self._work(-1)

        threading.Thread(target=run, name="argos-field-autosolve", daemon=True).start()

    def _mount_radec(self) -> tuple[float, float] | None:
        """Lock held: the connected mount's pointing (``_mount_radec``, 1017-1019)."""
        pointing = self._hub._pointing()
        return (pointing.ra_hours, pointing.dec_deg) if pointing is not None else None

    def _reticle_target(self) -> tuple[tuple[float, float], str] | None:
        """Lock held: the last GoTo target (Qt ``target_radec``), else the observation's."""
        goto = self._hub._goto_target
        if goto is not None:
            name = self._hub.observation.object_name or "GoTo target"
            return (goto[0], goto[1]), name
        target = self._hub.observation.target
        if target is not None:
            return (target["ra_hours"], target["dec_deg"]), target["name"]
        return None

    def _run_solve(
        self,
        frame: Frame,
        mode: str,
        cancel: threading.Event,
        ctx: JobContext | None,
        claim: dict[str, Any],
    ) -> dict[str, Any]:
        """One solve; an unexpected error ends the attempt instead of leaving it claimed."""
        try:
            return self._solve_frame(frame, mode, cancel, ctx, claim)
        except (JobCancelled, ApiError):
            raise
        except Exception as exc:
            logger.exception("Field identification failed")
            message = f"the solution could not be used ({type(exc).__name__}: {exc})"
            self._end_attempt(mode, "failed", message, claim)
            self._hub.log("error", f"Solve: {message}", source="field", topic="field")
            self._hub.set_activity(
                f"Field not identified: {message}", source="field", topic="field", log=False
            )
            raise ApiError(409, "not_solved", message) from exc

    def _solve_frame(
        self,
        frame: Frame,
        mode: str,
        cancel: threading.Event,
        ctx: JobContext | None,
        claim: dict[str, Any],
    ) -> dict[str, Any]:
        """One solve: ASTAP on the frame's green plane, then the result applied."""
        gs = green_shape(frame.raw)
        with self._hub._lock:
            invalidations = self._invalidations
            if frame.origin == "file":
                hint = frame.hint
                hint_source = "header" if hint is not None else None
                attempt_radec = None  # an opened file: the mount is no reference
            else:
                hint = self._mount_radec()
                hint_source = "mount" if hint is not None else None
                attempt_radec = hint
            self._attempt_mono = time.monotonic()
            self._attempt_radec = attempt_radec
            reticle = self._reticle_target()
        settings = build_solve_settings(
            self._hub.config.get, gs, live=(mode == "auto"), mount_radec=hint
        )
        if hint_source == "mount":
            text = f" (hint RA {hint[0]:.3f}h Dec {hint[1]:+.2f}°)"
        elif hint_source == "header":
            text = f" (hint from the FITS header: RA {hint[0]:.3f}h Dec {hint[1]:+.2f}°)"
        else:
            text = " (blind — no mount)"
        if mode == "manual":
            self._hub.log(
                "cmd", f"Plate-solving frame #{frame.seq}…{text}", source="field", topic="field"
            )
        self._hub.set_activity("Identifying field…", source="field", topic="field", log=False)

        def stage(name: str) -> None:
            if ctx is not None:
                ctx.progress(stage=name)

        green = extract_plane(frame.raw, VIEW_G)
        try:
            result = solve_green(green, settings, cancel, stage)
        except SolveCancelled:
            self._end_attempt(mode, "cancelled", "Field identification cancelled.", claim)
            self._hub.log("info", "Field identification cancelled.", source="field", topic="field")
            self._hub.set_activity(
                "Field identification cancelled", source="field", topic="field", log=False
            )
            raise JobCancelled() from None
        if not result.solved:
            message = result.message or "ASTAP could not solve the frame"
            self._end_attempt(mode, "failed", message, claim)
            level = "error" if mode == "manual" else "info"
            self._hub.log(level, f"Solve: {message}", source="field", topic="field")
            self._hub.set_activity(
                f"Field not identified: {message}", source="field", topic="field", log=False
            )
            raise ApiError(409, "not_solved", message)
        wcs = wcs_from_result(result, gs)
        if wcs is None:
            message = "could not build WCS from the solution"
            self._end_attempt(mode, "failed", message, claim)
            self._hub.log("error", f"Solve: {message}", source="field", topic="field")
            raise ApiError(409, "not_solved", message)
        # The solved frame's own sources: detected-only filters, anchors and
        # the re-acquisition of a lost lock (brightest first).
        stars = detect_stars(
            frame.raw, max_stars=MAX_DETECTED_SOURCES, radius=self._hub._star_radius()
        )
        detected = [(float(s.x), float(s.y)) for s in stars.stars]
        anchors_detected = [
            (float(s.x), float(s.y), float(s.flux)) for s in stars.stars if s.eccentricity < 0.6
        ]
        ref_stars = [(float(s.x), float(s.y), float(s.flux)) for s in stars.stars]
        ref_stars = sorted(ref_stars, key=lambda s: -s[2])[:REACQUIRE_REFERENCE_STARS]
        target_radec = reticle[0] if reticle is not None else None
        overlay = overlay_for(wcs, gs, self._hub.config.get, target_radec=target_radec)
        summary = self._summary(result, target_radec)
        with self._hub._lock:
            current = self._frame
            if self._invalidations != invalidations:
                stale = "Solve finished for a field that has moved since — discarded."
            elif current is not None and green_shape(current.raw) != gs:
                stale = "Solve finished for a different frame geometry — discarded."
            else:
                stale = None
            if stale is not None:
                if self._solving is claim:
                    self._solving = None
                    self._solve_cancel = None
                    if self._state == "solving":
                        self._state = self._prior_state
                self._last_attempt = {
                    "mode": mode,
                    "outcome": "cancelled",
                    "message": stale,
                    "t": utc_iso(),
                }
                self._publish_field()
        if stale is not None:
            self._hub.log("info", stale, source="field", topic="field")
            raise ApiError(409, "not_solved", stale)
        scale = full_res_scale(result)
        solution = {
            "ra_hours": float(result.ra_hours) if result.ra_hours is not None else None,
            "dec_deg": float(result.dec_deg) if result.dec_deg is not None else None,
            "scale_arcsec_px": float(scale) if scale is not None else None,
            "rotation_deg": float(result.rotation_deg) if result.rotation_deg is not None else None,
            # On the wire's y-down frame px, not ASTAP's FITS (y up) flag.
            "mirrored": wire_mirrored(wcs),
            "delta_target_arcmin": (
                angular_separation_deg(result.ra_hours, result.dec_deg, *target_radec) * 60.0
                if target_radec is not None and result.ra_hours is not None
                else None
            ),
            "target_name": reticle[1] if reticle is not None else None,
            "frame_seq": frame.seq,
            "frame_origin": frame.origin,
            "frame_shape": frame_shape_of(gs),
            "mode": mode,
            "solved_utc": utc_iso(),
            "hint": (
                {"ra_hours": hint[0], "dec_deg": hint[1], "source": hint_source}
                if hint is not None
                else None
            ),
            "summary": summary,
        }
        reticle_record = None
        target_xy = overlay.target if overlay is not None else None
        if (
            target_xy is not None
            and reticle is not None
            and all(math.isfinite(float(v)) for v in target_xy)
        ):
            # A target 90° or more from the field projects to NaN through TAN.
            tx, ty = to_frame(*target_xy)
            reticle_record = {
                "x": round(tx, 2),
                "y": round(ty, 2),
                "name": reticle[1],
                "ra_hours": reticle[0][0],
                "dec_deg": reticle[0][1],
            }
        with self._hub._lock:
            self._generation += 1
            self._state = "solved"
            self._reason = None
            self._message = None
            self._solving = None
            self._solve_cancel = None
            self._solution = solution
            self._wcs = wcs
            self._green_shape = gs
            self._wcs_record = frame_wcs_record(wcs, gs)
            self._grid = grid_record(overlay)
            self._reticle = reticle_record
            self._ref_raw = frame.raw
            self._ref_seq = frame.seq
            self._detected = detected
            self._detected_anchors = anchors_detected
            self._ref_stars = ref_stars
            self._tracker = None  # _on_reference_solved (1599-1602): a new reference
            self._tracker_stale = False
            self._loss_logged = False
            self._anchor_source = None
            self._transform = {**self._identity_transform(), "generation": self._generation}
            self._quality_cache = None
            self._last_attempt = {
                "mode": mode,
                "outcome": "solved",
                "message": summary,
                "t": utc_iso(),
            }
            self._publish_field()
            self._hub._publish("field_transform", dict(self._transform))
        self._hub.log("ok", summary, source="field", topic="field")
        self._hub.set_activity("Field identified", source="field", topic="field", log=False)
        self.maybe_fetch_catalog()
        self.schedule_projection()
        self._hub.targets.publish()  # positions on the new solution
        return solution

    def _end_attempt(
        self, mode: str, outcome: str, message: str, claim: dict[str, Any] | None = None
    ) -> None:
        """A failed or cancelled attempt: the last good solution is kept.

        Only the attempt that still owns the field ends it: an invalidation
        releases a running solve at once, and a newer one may run by then.
        """
        with self._hub._lock:
            if claim is not None and self._solving is not claim:
                if self._solving is None:  # released by an invalidation: just record it
                    self._last_attempt = {
                        "mode": mode,
                        "outcome": outcome,
                        "message": message,
                        "t": utc_iso(),
                    }
                    self._publish_field()
                return
            self._solving = None
            self._solve_cancel = None
            if self._state == "solving":
                # A failure keeps the last good solution (astrometry_controller.py:
                # 213-218); a cancel returns to where the field was.
                self._state = "failed" if outcome == "failed" else self._prior_state
            if outcome == "failed":
                self._message = message
            self._last_attempt = {
                "mode": mode,
                "outcome": outcome,
                "message": message,
                "t": utc_iso(),
            }
            self._publish_field()

    def _summary(self, result, target_radec) -> str:
        """``_summary`` (``astrometry_controller.py:226-238``)."""
        bits = [f"Solved — RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        scale = full_res_scale(result)
        if scale is not None:
            bits.append(f"{scale:.2f}″/px")
        if result.rotation_deg is not None:
            bits.append(f"rot {result.rotation_deg:.1f}°")
        if target_radec is not None:
            sep = angular_separation_deg(
                result.ra_hours, result.dec_deg, target_radec[0], target_radec[1]
            )
            bits.append(f"Δtarget {sep * 60.0:.1f}′")
        return "  ".join(bits)

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, reason: str) -> None:
        """Drop the solution and everything built on it (``_clear_astrometry``)."""
        with self._hub._lock:
            had = self._wcs is not None or self._state == "solving"
            self._invalidate_locked(reason)
        if had:
            self._announce_invalidation(reason)

    def _announce_invalidation(self, reason: str) -> None:
        self._hub.log("info", INVALIDATION_TEXT[reason], source="field", topic="field")
        self._hub.targets.publish()  # positions: off the solution

    def _invalidate_locked(self, reason: str) -> None:
        """Lock held. A running solve is cancelled and released: its field is gone."""
        if self._solve_cancel is not None:
            self._solve_cancel.set()
        self._solving = None
        self._solve_cancel = None
        self._invalidations += 1
        self._generation += 1
        self._state = "invalidated"
        self._prior_state = "invalidated"
        self._reason = reason
        self._message = INVALIDATION_TEXT[reason]
        self._solution = None
        self._wcs = None
        self._green_shape = None
        self._wcs_record = None
        self._grid = None
        self._reticle = None
        self._attempt_radec = None
        self._ref_raw = None
        self._ref_seq = None
        self._detected = []
        self._detected_anchors = []
        self._ref_stars = []
        self._tracker = None
        self._tracker_stale = False
        self._anchor_source = None
        self._quality_cache = None
        self._catalog_token += 1
        self._catalog_result = None
        self._catalog_centre = None
        self._catalog_running = False
        self._point_identities = []
        self._projection = None
        self._publish_field()
        self._publish_catalog(**{**self._catalog_idle(), "generation": self._generation})
        self._layers_revision += 1
        self._layers = {
            **self._empty_layers(),
            "generation": self._generation,
            "revision": self._layers_revision,
        }
        self._hub._publish("field_layers", self._layers)
        self._transform = {**self._identity_transform(), "generation": self._generation}
        self._hub._publish("field_transform", dict(self._transform))
        self._clear_selection_locked()

    def check_mount(self, ra_hours: float, dec_deg: float) -> None:
        """``mount_moved_since_solution`` (``astrometry_controller.py:156-174``)
        for every mount reading (``imaging_page.py:2667-2686``)."""
        with self._hub._lock:
            if self._wcs is None or self._attempt_radec is None:
                return
            sep = angular_separation_deg(ra_hours, dec_deg, *self._attempt_radec) * 60.0
            limit = float(self._hub.config.get("astrometry.live_resolve_arcmin", 2.0) or 2.0)
            if sep < limit:
                return
        self.invalidate("mount_moved")

    # ------------------------------------------------------------------
    # Catalogue (A46)
    # ------------------------------------------------------------------

    def maybe_fetch_catalog(self, *, force: bool = False) -> bool:
        """``maybe_fetch_catalog`` (``acquisition_engine.py:1105-1173``); True if started."""
        tset = self._hub.targets.target_set()
        targets = tset.by_role(ROLE_TARGET)
        with self._hub._lock:
            if self._wcs is None or self._catalog_running:
                return False
            geom = field_geometry(self._wcs, self._green_shape)
            if geom is None:
                return False
            ra_deg, dec_deg, radius_deg, _fov = geom
            result = self._catalog_result
            if not force and self._catalog_centre is not None and result is not None:
                has_any = (
                    result.variables
                    or result.comparisons
                    or result.field_stars
                    or result.named_objects
                    or result.exoplanet_hosts
                )
                moved = angular_separation_deg(
                    ra_deg / 15.0,
                    dec_deg,
                    self._catalog_centre[0] / 15.0,
                    self._catalog_centre[1],
                )
                if has_any and moved < radius_deg:
                    self._publish_catalog(generation=self._generation)
                    return False  # same field: reuse the cached catalogue
            request = fc.build_request(
                self._hub.config.get, self._wcs, self._green_shape, targets[0] if targets else None
            )
            if request is None:
                return False
            self._catalog_centre = (ra_deg, dec_deg)
            self._catalog_running = True
            self._catalog_token += 1
            token = self._catalog_token
            generation = self._generation
            self._publish_catalog(
                state="fetching",
                generation=generation,
                centre={"ra_hours": ra_deg / 15.0, "dec_deg": dec_deg},
                radius_deg=radius_deg,
                warnings=[],
                error=None,
            )
        self._work(+1)
        threading.Thread(
            target=self._fetch, args=(request, token), name="argos-field-catalog", daemon=True
        ).start()
        return True

    def _fetch(self, request: fc.CatalogRequest, token: int) -> None:
        try:
            result = fc.run_request(request, self.catalog_api)
            with self._hub._lock:
                if token != self._catalog_token:
                    return  # the field moved or a refetch replaced it
                self._catalog_running = False
                if not result.ok:
                    self._catalog_centre = None
                    self._publish_catalog(
                        state="error", error=result.error, warnings=[], fetched_utc=utc_iso()
                    )
                else:
                    self._catalog_result = result
                    self._quality_cache = None
                    self._publish_catalog(
                        state="ready",
                        counts={
                            "variables": len(result.variables),
                            "comparisons": len(result.comparisons),
                            "field_stars": len(result.field_stars),
                            "named_objects": len(result.named_objects),
                            "exoplanet_hosts": len(result.exoplanet_hosts),
                        },
                        limits={
                            "field_stars": result.field_star_limit,
                            "named_objects": result.named_object_limit,
                        },
                        warnings=list(result.warnings) + list(result.source_warnings),
                        error=None,
                        fetched_utc=utc_iso(),
                    )
            for level, text in fc.result_log_lines(result):
                self._hub.log(level, text, source="catalog", topic="field")  # type: ignore[arg-type]
            if result.ok:
                self.schedule_projection()
                if result.comparisons:
                    self._hub.targets.backfill_comparisons()
        except Exception:
            logger.exception("Field catalogue fetch failed")
            with self._hub._lock:
                if token == self._catalog_token:
                    self._catalog_running = False
                    self._publish_catalog(state="error", error="internal error")
        finally:
            self._work(-1)

    def refetch(self) -> dict[str, Any]:
        """``POST /api/field/catalog/refetch`` (``refetch_catalog``, 1086-1103)."""
        with self._hub._lock:
            if self._wcs is None:
                raise ApiError(
                    409,
                    "not_solved",
                    "Identify the field first: the catalogue is fetched around a plate solution.",
                )
            if self._catalog_running:
                raise ApiError(409, "busy", "The field catalogue is being fetched.")
            self._catalog_result = None
            self._catalog_centre = None
        self.maybe_fetch_catalog(force=True)
        return self.catalog_record()

    def on_config_changed(self, changed: dict[str, Any]) -> None:
        keys = set(changed)
        if keys & FETCH_KEYS:
            if self._refetch_timer is not None:
                self._refetch_timer.cancel()
            timer = threading.Timer(_REFETCH_DEBOUNCE_S, self._refetch_after_config)
            timer.daemon = True
            self._refetch_timer = timer
            timer.start()
        elif keys & DISPLAY_KEYS:
            self.schedule_projection()

    def _refetch_after_config(self) -> None:
        with self._hub._lock:
            if self._wcs is None or self._closed:
                return
            if self._catalog_running:
                self._catalog_token += 1  # its answer is for the old settings
                self._catalog_running = False
            self._catalog_result = None
            self._catalog_centre = None
        self.maybe_fetch_catalog(force=True)

    # ------------------------------------------------------------------
    # Layers (A47)
    # ------------------------------------------------------------------

    def on_targets_changed(self) -> None:
        """The set changed: re-anchor the tracker and re-project.

        Qt dropped the tracker (``_reset_tracker``, ``acquisition_engine.py:1301``)
        and restarted from the identity, which is wrong once the field has
        drifted: the new constellation starts from the current pose.
        """
        with self._hub._lock:
            if self._tracker is not None:
                self._tracker_stale = True
            self._hub._update_center_available()
        self.schedule_projection()

    def schedule_projection(self) -> None:
        if self._closed:
            return
        self._ensure_threads()
        with self._project_cond:
            self._project_dirty = True
            self._project_cond.notify()

    def _project_loop(self) -> None:
        while True:
            with self._project_cond:
                while not self._project_dirty and not self._closed:
                    self._project_cond.wait()
                if self._closed:
                    return
                self._project_dirty = False
                self._work(+1)
            try:
                self._project()
            except Exception:
                logger.exception("Field: projection failed")
            finally:
                self._work(-1)

    def _project(self) -> None:
        tset = self._hub.targets.target_set()
        with self._hub._lock:
            if self._wcs is None:
                return
            generation = self._generation
            ctx = fc.FieldContext(
                wcs=self._wcs,
                green_shape=self._green_shape,
                detected=list(self._detected),
                result=self._catalog_result or fc.CatalogResult(),
                point_identities=list(self._point_identities),
            )
            ref = (self._ref_raw, self._ref_seq)
            cached = self._quality_cache
        cfg = self._hub.config.get
        limit = float(cfg("catalog.display_mag_limit", 18.0) or 18.0)
        projection = fc.project_field(ctx, cfg, tset, display_mag_limit=limit)
        geometry = self._hub.targets.geometry()
        aperture = float(geometry["aperture_px"])
        target_bv = self._target_b_minus_v(tset, ctx.result)
        key = (generation, id(ctx.result), round(aperture, 2))
        quality = cached[1] if cached is not None and cached[0] == key else None
        measure = bool(ctx.result.comparisons) and ref[0] is not None and quality is None
        # The layers first; the candidates' measurement (pilot rule) follows.
        if not self._publish_layers(
            ctx, tset, projection, limit, aperture, quality, ref[1], target_bv, generation
        ):
            return
        if measure:
            quality = self._candidate_quality(ctx, ref[0], ref[1])
            with self._hub._lock:
                if generation != self._generation:
                    return
                self._quality_cache = (key, quality)
            self._publish_layers(
                ctx, tset, projection, limit, aperture, quality, ref[1], target_bv, generation
            )

    def _publish_layers(
        self, ctx, tset, projection, limit, aperture, quality, seq, target_bv, generation
    ) -> bool:
        cfg = self._hub.config.get
        fwhm_green = self._hub.targets.geometry().get("fwhm_px")
        scale_green = _green_scale_arcsec(ctx.wcs)
        counterpart = fc.COUNTERPART_ARCSEC
        if fwhm_green is not None and scale_green is not None:
            counterpart = max(counterpart, 0.5 * float(fwhm_green) * scale_green)
        rows = fc.candidates(
            ctx,
            tset,
            aperture_green_px=aperture,
            quality=quality,
            measured_seq=seq,
            target_b_minus_v=target_bv,
            counterpart_arcsec=counterpart,
        )
        # The rules the FieldBand flags with: the observer's (Settings ›
        # Photometry), never constants of the client.
        limits = {
            "comparison_max_separation_arcmin": float(
                cfg("photometry.comparison_max_separation_arcmin", 25.0)
            ),
            "comparison_max_delta_mag": float(cfg("photometry.comparison_max_delta_mag", 1.5)),
            "comparison_min_snr": float(cfg("photometry.comparison_min_snr", 10.0)),
            "gaia_depth_g": fc.gaia_depth(ctx.result),
        }
        with self._hub._lock:
            if generation != self._generation or self._wcs is None:
                return False  # the field changed while projecting
            self._projection = projection
            self._layers_revision += 1
            self._layers = {
                "generation": generation,
                "revision": self._layers_revision,
                "available": True,
                "frame_shape": frame_shape_of(ctx.green_shape),
                "display_mag_limit": limit,
                "aperture_r_px": 2.0 * aperture,
                "layers": projection.layers,
                "counts": projection.counts,
                "candidates": rows,
                "limits": limits,
            }
            self._hub._publish("field_layers", self._layers)
        return True

    @staticmethod
    def _target_b_minus_v(tset, result) -> float | None:
        targets = [s for s in tset.stars if s.role == ROLE_TARGET]
        if not targets:
            return None
        mags = targets[0].mags or {}
        if mags.get("B") is not None and mags.get("V") is not None:
            return round(float(mags["B"]) - float(mags["V"]), 4)
        return None

    def _candidate_quality(self, ctx, raw, seq) -> dict[str, Any]:
        """Peak, SNR and saturation of every VSP star on the solved frame (pilot rule)."""
        params = self._hub.targets.params(self._hub.targets.egain())
        fwhm = self._hub.targets.geometry()["fwhm_px"]
        r_ap = params.aperture_px(fwhm)
        r_in = max(params.annulus_in_px, r_ap + 1.0)
        r_out = max(params.annulus_out_px, r_in + 2.0)
        measurer = FrameMeasurer(raw)
        green = measurer.green
        out: dict[str, Any] = {}
        for star in ctx.result.comparisons:
            x, y = ctx.wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            x, y = float(x), float(y)
            if not (0 <= x < ctx.green_shape[1] and 0 <= y < ctx.green_shape[0]):
                continue
            centroid = measurer.measure_star_at(x, y, radius=max(2, int(round(r_ap))), search=3)
            if centroid is None or math.hypot(centroid.x - x, centroid.y - y) > 3.0:
                continue
            phot = measure_aperture(
                green,
                centroid.x,
                centroid.y,
                r_ap,
                r_in,
                r_out,
                egain=params.egain,
                read_noise_e=params.read_noise_e,
                sat_adu=params.sat_adu,
            )
            if phot is None:
                continue
            out[star.auid] = {
                "peak_adu": int(phot.peak_adu),
                "snr": round(float(phot.snr), 1),
                "saturated": bool(phot.saturated),
            }
        return out

    # ------------------------------------------------------------------
    # Tracking (A48)
    # ------------------------------------------------------------------

    def _track(self, frame: Frame) -> None:
        """``_wcs_for_frame`` (``acquisition_engine.py:1542-1567``) on every frame,
        with the web's tracker (:mod:`argos.server.field_track`)."""
        with self._hub._lock:
            wcs, gs, current = self._wcs, self._green_shape, self._tracker
            generation = self._generation
            if wcs is None or frame.seq == self._ref_seq:
                return
            rebuild = current is None or self._tracker_stale
            self._tracker_stale = False
            alignment = self._hub._mount_state.alignment
            anchors_detected = list(self._detected_anchors)
            ref_raw = self._ref_raw
            ref_stars = list(self._ref_stars)
            source = self._anchor_source
        green = green_plane(frame.raw)
        tracker = current
        if rebuild:
            if ref_raw is None:
                return
            pose = current.transform if current is not None else None
            tracker, source = self._build_tracker(
                green_plane(ref_raw), wcs, gs, anchors_detected, pose
            )
            if tracker is None:
                return
        # EQ: translation only, no spurious rotation (1557-1561).
        allow_rotation = alignment not in ("eq", "eq_gem")
        tracker.reacquired = False
        tracker.update(green, allow_rotation=allow_rotation)
        if tracker.anchors_used == 0 and ref_stars:
            self._reacquire(tracker, frame, ref_stars, green, allow_rotation)
        t = tracker.transform
        cx, cy = to_frame(t.cx, t.cy)
        health = tracker.health
        with self._hub._lock:
            if generation != self._generation or self._tracker is not current:
                return  # a new solution or an invalidation meanwhile
            self._tracker = tracker
            self._anchor_source = source
            announce = None
            if health == "lost" and not self._loss_logged:
                self._loss_logged = True
                announce = ("warning", LOST_TEXT)
            elif health != "lost" and self._loss_logged:
                self._loss_logged = False
                announce = (
                    "info",
                    f"Tracking: field found again ({tracker.anchors_used} anchors).",
                )
            self._transform = {
                "generation": generation,
                "frame_seq": frame.seq,
                "rot_deg": t.rotation_deg,
                "dx": 2.0 * t.tx,
                "dy": 2.0 * t.ty,
                "cx": cx,
                "cy": cy,
                "anchors": tracker.anchors_used,
                "residual_px": 2.0 * tracker.residual_px if tracker.anchors_used else None,
                "anchor_source": source,
                "lost_frames": tracker.frames_lost,
                "tracking": health,
            }
            self._hub._publish("field_transform", dict(self._transform))
        if announce is not None:
            self._hub.log(announce[0], announce[1], source="field", topic="field")

    def _reacquire(self, tracker, frame: Frame, ref_stars, green, allow_rotation: bool) -> None:
        """A lost lock: match the frame's stars to the solved frame's, then refit."""
        stars = detect_stars(frame.raw, radius=self._hub._star_radius())
        current = [(float(s.x), float(s.y), float(s.flux)) for s in stars.stars]
        found = vote_transform(ref_stars, current, tracker.transform, allow_rotation=allow_rotation)
        if found is None:
            return
        previous = tracker.transform
        tracker.transform = found[0]
        if tracker.update(green, allow_rotation=allow_rotation):
            tracker.reacquired = True
            logger.info("Tracking re-acquired on %d matched stars", found[1])
        else:
            tracker.transform = previous

    def _build_tracker(
        self, ref_green, wcs, gs, detected, pose
    ) -> tuple[FieldTracker | None, str | None]:
        """``_build_live_tracker`` (1569-1582), then the solved frame's own stars.

        Everything is chosen on the **solved** frame (``ref_green``), where the
        reference positions are true: the current frame has moved.
        """
        tset = self._hub.targets.target_set()
        params = self._hub.targets.params()
        h, w = gs
        search_r = max(8.0, 2.0 * params.aperture_px(None))
        margin = search_r + 2.0  # the centroid window fits in the frame (tracking.py:99-105)
        candidates = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        anchors = select_tracking_anchors(ref_green, wcs, candidates, params) if candidates else []
        xy: list[tuple[float, float]] = []
        for star in anchors:
            x, y = wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            if margin <= float(x) < w - margin and margin <= float(y) < h - margin:
                xy.append((float(x), float(y)))
        source = "target_set"
        if len(xy) < 2:
            # One anchor gives no rotation and no consistency test: bright,
            # unsaturated stars of the solved frame (protocol.md, Tracking).
            chosen = self._detected_anchor_xy(ref_green, detected, params, margin)
            if len(chosen) >= 2 or not xy:
                xy, source = chosen, "detected"
        if not xy:
            # Qt's last resort: every star of the set (a variable near minimum
            # is a poor centroid, 1576).
            for star in tset.stars:
                x, y = wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
                if margin <= float(x) < w - margin and margin <= float(y) < h - margin:
                    xy.append((float(x), float(y)))
            source = "target_set"
        if not xy:
            return None, None
        tracker = FieldTracker(
            xy,
            frame_center=(w / 2.0, h / 2.0),
            search_r=search_r,
            reference_green=ref_green,
            pose=pose,
        )
        return tracker, source

    @staticmethod
    def _detected_anchor_xy(ref_green, detected, params, margin) -> list[tuple[float, float]]:
        """Up to six bright stars of the solved frame, unsaturated and 20 px apart."""
        h, w = ref_green.shape
        usable = [
            (x, y, flux)
            for x, y, flux in detected
            if margin <= x < w - margin and margin <= y < h - margin
        ]
        usable.sort(key=lambda item: item[2], reverse=True)
        sat = float(params.sat_adu)
        chosen: list[tuple[float, float]] = []
        for x, y, _flux in usable:
            xi, yi = int(round(x)), int(round(y))
            # Saturation on the solved frame, where the star is (3x3 peak).
            if float(np.max(ref_green[yi - 1 : yi + 2, xi - 1 : xi + 2])) >= sat:
                continue
            if any(math.hypot(x - ox, y - oy) < 20.0 for ox, oy in chosen):
                continue
            chosen.append((x, y))
            if len(chosen) >= MAX_DETECTED_ANCHORS:
                break
        return chosen

    # ------------------------------------------------------------------
    # Selection (A49)
    # ------------------------------------------------------------------

    def _clear_selection_locked(self) -> None:
        self._pending = None
        self._follow = None
        if self._selection.get("id") is not None:
            self._selection_seq += 1  # a late identification answer is dropped
            self._publish_selection({"id": None, "selection": None})

    def clear_selection(self) -> dict[str, Any]:
        """``DELETE /api/field/select`` (``_on_card_cleared``, 2056-2061)."""
        with self._hub._lock:
            self._clear_selection_locked()
            return self._selection

    def pending_for(self, selection_id: int) -> dict[str, Any]:
        """The pending star of the current selection (``POST /api/targets``)."""
        with self._hub._lock:
            current = self._selection.get("id")
            pending = self._pending
        if current is None or current != selection_id or pending is None:
            raise ApiError(
                409,
                "not_found",
                "That star is no longer selected — click it again.",
            )
        return dict(pending)

    def variable_pending(self, index: int) -> dict[str, Any]:
        """``_on_variable_target_requested`` (``imaging_page.py:2252-2274``)."""
        with self._hub._lock:
            result = self._catalog_result
            variables = list(result.variables) if result is not None and self._wcs else []
        if not 0 <= index < len(variables):
            raise ApiError(404, "not_found", f"No variable #{index} in the field's catalogue")
        v = variables[index]
        return pending_star(v.ra_deg, v.dec_deg, auid=v.auid, name=v.name, source="vsx", mags={})

    def select(self, x: float, y: float, seq: int | None = None, tol_px: float | None = None):
        """``POST /api/field/select``: the click identification of ``_on_star_clicked``."""
        with self._hub._lock:
            frame = self._frame
            if frame is None:
                raise ApiError(409, "no_frame", "No frame to select a star on yet.")
            fh, fw = frame.raw.shape
            if not (0 <= x < fw and 0 <= y < fh):
                raise ApiError(400, "invalid_argument", "The point is outside the frame")
            self._selection_seq += 1
            sid = self._selection_seq
            wcs, tracked = self._wcs, self._tracked_wcs()
            tracker = self._tracker
            projection = self._projection
            scale = (
                2.0 * self._solution["scale_arcsec_px"]
                if self._solution and self._solution.get("scale_arcsec_px")
                else None
            )
        tol = max(2.0, float(tol_px or DEFAULT_TOL_PX) / 2.0)
        gx, gy = to_green(x, y)
        # Catalogue entries sit at reference positions: undo the tracking.
        rx, ry = tracker.transform.invert(gx, gy) if tracker is not None else (gx, gy)
        tset = self._hub.targets.target_set()
        saved = {s.key(): s.role for s in tset.stars}
        aperture = self._hub.targets.geometry()["aperture_px"]

        def card(kind, ref_point, title, rows, pending):
            # A catalogue position: reference px, moved by field_transform like markers.
            fx, fy = to_frame(*ref_point)
            key = TargetStar(role="target", **_star_args(pending)).key()
            rows = rows + [{"key": "Photometry aperture", "value": f"{aperture:.1f} green px"}]
            return {
                "id": sid,
                "seq": frame.seq,
                "kind": kind,
                "title": title,
                "rows": rows,
                "ring": {
                    "x": round(fx, 2),
                    "y": round(fy, 2),
                    "r_px": round(2.0 * aperture, 2),
                    "aperture": "photometry",
                    "space": "reference",
                },
                "pending_star": pending,
                "key": key,
                "role": saved.get(key),
                "roles_enabled": True,
                "roles_reason": None,
                "removable": key in saved,
                "identifying": False,
                "measurement": None,
            }

        if wcs is not None:
            target_entries = [
                (float(p[0]), float(p[1]), s) if p is not None else None
                for p, s in zip(
                    [
                        _project_one(wcs, self._green_shape_safe(), s.ra_deg, s.dec_deg)
                        for s in tset.stars
                    ],
                    tset.stars,
                )
            ]
            hits = [("target", target_entries)]
            if projection is not None:
                hits += [h for h in projection.hits if h[0] != "target"]
            for kind, entries in hits:
                i = fc.nearest(entries, rx, ry, tol)
                if i is None:
                    continue
                ex, ey, item = entries[i]
                built = _catalogue_card(kind, item, self._hub, tset)
                if built is None:
                    continue
                title, rows, pending = built
                selection = card(kind, (ex, ey), title, rows, pending)
                with self._hub._lock:
                    if sid != self._selection_seq:
                        return self._selection
                    self._pending = pending
                    self._follow = None
                    return self._publish_selection(
                        {"id": sid, "state": "resolved", "selection": selection, "message": None}
                    )

        meas = measure_star_at(frame.raw, gx, gy, self._hub._star_radius())
        if wcs is not None:
            px = meas.x if meas is not None else gx
            py = meas.y if meas is not None else gy
            ra_h, dec_d = tracked.pixel_to_radec(px, py)
            fx, fy = to_frame(px, py)
            selection = {
                "id": sid,
                "seq": frame.seq,
                "kind": "none",
                "title": "Identifying catalogue source…",
                "rows": [
                    {"key": "Point lookup", "value": "within 10″"},
                    {"key": "RA", "value": format_ra_hms(ra_h)},
                    {"key": "Dec", "value": format_dec_dms(dec_d)},
                    {"key": "Catalogues", "value": "Gaia astrometry · SIMBAD identity"},
                ],
                "ring": {
                    "x": round(fx, 2),
                    "y": round(fy, 2),
                    "r_px": round(2.0 * aperture, 2),
                    "aperture": "photometry",
                    "space": "frame",
                },
                "pending_star": None,
                "key": None,
                "role": None,
                "roles_enabled": False,
                "roles_reason": "identification in progress",
                "removable": False,
                "identifying": True,
                "measurement": _measurement(meas, tracked, scale),
            }
            with self._hub._lock:
                if sid != self._selection_seq:
                    return self._selection
                self._pending = None
                self._follow = None
                event = self._publish_selection(
                    {"id": sid, "state": "identifying", "selection": selection, "message": None}
                )
            self._work(+1)
            threading.Thread(
                target=self._identify,
                args=(sid, frame.seq, ra_h, dec_d, (px, py), meas, tracked, scale),
                name="argos-field-identify",
                daemon=True,
            ).start()
            return event

        if meas is None:
            with self._hub._lock:
                if sid != self._selection_seq:
                    return self._selection
                self._pending = None
                self._follow = None
                return self._publish_selection(
                    {
                        "id": sid,
                        "state": "no_match",
                        "selection": None,
                        "message": "No star-like signal at that point.",
                    }
                )
        selection = self._measured_card(sid, frame.seq, meas, None, scale, note=None)
        with self._hub._lock:
            if sid != self._selection_seq:
                return self._selection
            self._pending = None
            self._follow = (meas.x, meas.y)
            return self._publish_selection(
                {"id": sid, "state": "resolved", "selection": selection, "message": None}
            )

    def _green_shape_safe(self) -> tuple[int, int] | None:
        with self._hub._lock:
            return self._green_shape

    def _measured_card(self, sid, seq, meas, tracked, scale, note: str | None) -> dict[str, Any]:
        """``_present_field_card`` / ``_format_star_text`` (``imaging_page.py:1019-1045,
        1268-1295``)."""
        pending = None
        if tracked is not None:
            ra_h, dec_d = tracked.pixel_to_radec(meas.x, meas.y)
            pending = pending_star(
                ra_h * 15.0, dec_d, auid=None, name=None, source="manual", mags={}
            )
        fx, fy = to_frame(meas.x, meas.y)
        rows = [
            {
                "key": "Catalogue",
                "value": note
                or (
                    "No loaded catalogue marker. Gaia/SIMBAD point identification is available."
                    if tracked is not None
                    else "identify the field first"
                ),
            }
        ]
        rows += _measurement_rows(meas, tracked, scale, self._hub)
        key = TargetStar(role="target", **_star_args(pending)).key() if pending else None
        tset = self._hub.targets.target_set()
        saved = {s.key(): s.role for s in tset.stars}
        return {
            "id": sid,
            "seq": seq,
            "kind": "measured",
            "title": "Manual image measurement",
            "rows": rows,
            "ring": {
                "x": round(fx, 2),
                "y": round(fy, 2),
                "r_px": round(2.0 * meas.radius, 2),
                "aperture": "star",
                "space": "frame",
            },
            "pending_star": pending,
            "key": key,
            "role": saved.get(key) if key else None,
            "roles_enabled": pending is not None,
            "roles_reason": None if pending is not None else "identify the field first",
            "removable": bool(key and key in saved),
            "identifying": False,
            "measurement": _measurement(meas, tracked, scale),
        }

    def _identify(self, sid, seq, ra_h, dec_d, point, meas, tracked, scale) -> None:
        """``PointIdentityWorker`` and ``_on_point_identity_*`` (``imaging_page.py:1047-1197``)."""
        cfg = self._hub.config.get
        use_gaia = bool(cfg("catalog.field_stars_enabled", True))
        use_simbad = bool(cfg("catalog.named_objects_enabled", True))
        try:
            try:
                identity = self.identify_point(
                    ra_h * 15.0,
                    dec_d,
                    use_gaia=use_gaia,
                    use_simbad=use_simbad,
                    allow_gaia_network=use_gaia,
                    allow_simbad_network=use_simbad
                    and bool(cfg("catalog.named_objects_allow_network", True)),
                )
                error = None
            except PointIdentityLookupError as exc:
                identity, error = None, str(exc) or "Point identification failed."
            except Exception:
                logger.exception("Point identification failed")
                identity = None
                error = "Point identification failed unexpectedly. See the log for details."
            with self._hub._lock:
                if sid != self._selection_seq:
                    return  # superseded (P21)
            if error is not None:
                if meas is not None:
                    selection = self._measured_card(
                        sid, seq, meas, tracked, scale, note="Point catalogue lookup unavailable."
                    )
                    state, follow = "failed", (meas.x, meas.y)
                else:
                    selection = None
                    state, follow = "failed", None
                self._hub.log(
                    "warning", f"Point identification: {error}", source="field", topic="field"
                )
                with self._hub._lock:
                    if sid != self._selection_seq:
                        return
                    self._pending = selection["pending_star"] if selection else None
                    self._follow = follow
                    self._publish_selection(
                        {"id": sid, "state": state, "selection": selection, "message": error}
                    )
                return
            if identity is None:
                self._hub.log(
                    "info",
                    "Point identification: no catalogue match within 10″.",
                    source="field",
                    topic="field",
                )
                if meas is not None:
                    selection = self._measured_card(
                        sid,
                        seq,
                        meas,
                        tracked,
                        scale,
                        note="No Gaia or SIMBAD source matched within 10″.",
                    )
                    message = None
                else:
                    selection = None
                    message = (
                        "No measured stellar centroid or Gaia/SIMBAD identity was found within 10″."
                    )
                with self._hub._lock:
                    if sid != self._selection_seq:
                        return
                    self._pending = selection["pending_star"] if selection else None
                    self._follow = (meas.x, meas.y) if meas is not None else None
                    self._publish_selection(
                        {"id": sid, "state": "no_match", "selection": selection, "message": message}
                    )
                return
            with self._hub._lock:
                existing = next(
                    (
                        item
                        for item in self._point_identities
                        if separation_arcmin(
                            item.ra_deg, item.dec_deg, identity.ra_deg, identity.dec_deg
                        )
                        <= 1.0 / 60.0
                    ),
                    None,
                )
                if existing is None:
                    self._point_identities.append(identity)
                else:
                    identity = existing
                wcs, tracker = self._wcs, self._tracker
                gs = self._green_shape
            self.schedule_projection()
            ref = _project_one(wcs, gs, identity.ra_deg, identity.dec_deg) if wcs else None
            if ref is None:
                ref = tracker.transform.invert(*point) if tracker is not None else point
            title, rows, pending = _catalogue_card(
                "point_identity", identity, self._hub, self._hub.targets.target_set()
            )
            aperture = self._hub.targets.geometry()["aperture_px"]
            fx, fy = to_frame(*ref)
            key = TargetStar(role="target", **_star_args(pending)).key()
            saved = {s.key(): s.role for s in self._hub.targets.target_set().stars}
            selection = {
                "id": sid,
                "seq": seq,
                "kind": "point_identity",
                "title": title,
                "rows": rows
                + [{"key": "Photometry aperture", "value": f"{aperture:.1f} green px"}],
                "ring": {
                    "x": round(fx, 2),
                    "y": round(fy, 2),
                    "r_px": round(2.0 * aperture, 2),
                    "aperture": "photometry",
                    "space": "reference",
                },
                "pending_star": pending,
                "key": key,
                "role": saved.get(key),
                "roles_enabled": True,
                "roles_reason": None,
                "removable": key in saved,
                "identifying": False,
                "measurement": _measurement(meas, tracked, scale),
            }
            self._hub.log(
                "ok",
                f"Point identified: {identity.name} ({identity.source}, "
                f"offset {identity.separation_arcsec:.1f}″).",
                source="field",
                topic="field",
            )
            with self._hub._lock:
                if sid != self._selection_seq:
                    return
                self._pending = pending
                self._follow = None
                self._publish_selection(
                    {"id": sid, "state": "resolved", "selection": selection, "message": None}
                )
        finally:
            self._work(-1)

    def _follow_selection(self, frame: Frame) -> None:
        """``_remeasure_selection`` (``imaging_page.py:1241-1257``) for a measured star."""
        with self._hub._lock:
            follow = self._follow
            event = self._selection
            sid = event.get("id")
            selection = event.get("selection")
            if follow is None or selection is None or selection.get("kind") != "measured":
                return
            if selection.get("seq") == frame.seq:
                return
            tracked = self._tracked_wcs()
            scale = (
                2.0 * self._solution["scale_arcsec_px"]
                if self._solution and self._solution.get("scale_arcsec_px")
                else None
            )
        meas = measure_star_at(
            frame.raw, follow[0], follow[1], self._hub._star_radius(), search=TRACK_SNAP_SEARCH
        )
        if meas is None:
            return
        fx, fy = to_frame(meas.x, meas.y)
        updated = {
            **selection,
            "seq": frame.seq,
            "ring": {**selection["ring"], "x": round(fx, 2), "y": round(fy, 2)},
            "measurement": _measurement(meas, tracked, scale),
            "rows": [selection["rows"][0]] + _measurement_rows(meas, tracked, scale, self._hub),
        }
        with self._hub._lock:
            if self._selection.get("id") != sid or self._follow is None:
                return
            self._follow = (meas.x, meas.y)
            self._publish_selection(
                {"id": sid, "state": "tracking", "selection": updated, "message": None}
            )


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------


def _green_scale_arcsec(wcs) -> float | None:
    """Arcseconds per green px of a solution (its CD matrix)."""
    try:
        a, b, c, d = (float(v) for v in wcs.cd)
    except (AttributeError, TypeError, ValueError):
        return None
    det = abs(a * d - b * c)
    return math.sqrt(det) * 3600.0 if det > 0 and math.isfinite(det) else None


def _project_one(wcs, gs, ra_deg, dec_deg) -> tuple[float, float] | None:
    if wcs is None or gs is None:
        return None
    x, y = wcs.world_to_pixel_deg(ra_deg, dec_deg)
    x, y = float(x), float(y)
    if -2.0 <= x <= gs[1] + 2.0 and -2.0 <= y <= gs[0] + 2.0:
        return x, y
    return None


def _star_args(pending: dict[str, Any] | None) -> dict[str, Any]:
    if not pending:
        return {"ra_deg": 0.0, "dec_deg": 0.0}
    star = star_from_pending(pending, "target")
    return {
        "ra_deg": star.ra_deg,
        "dec_deg": star.dec_deg,
        "auid": star.auid,
        "name": star.name,
        "source": star.source,
        "mags": star.mags,
        "chart_id": star.chart_id,
    }


def _radec_rows(ra_deg: float, dec_deg: float) -> list[dict[str, str]]:
    return [
        {"key": "RA", "value": format_ra_hms(ra_deg / 15.0)},
        {"key": "Dec", "value": format_dec_dms(dec_deg)},
    ]


def _mags_value(pairs) -> str | None:
    text = "  ".join(f"{band} {float(mag):.3f}" for band, mag in pairs if mag is not None)
    return text or None


def _catalogue_card(kind: str, item, hub, tset) -> tuple[str, list, dict] | None:
    """Titles, rows and pending stars of ``_on_star_clicked`` (``imaging_page.py:804-978``)
    with the bodies of 1199-1240, 1919-1989."""
    rows: list[dict[str, Any]] = []
    if kind == "target":
        s = item
        rows.append({"key": "Role", "value": s.role})
        rows.append({"key": "Source", "value": s.source})
        mags = _mags_value(s.mags.items())
        if mags:
            rows.append({"key": "Magnitudes", "value": mags})
        rows += _radec_rows(s.ra_deg, s.dec_deg)
        pending = pending_star(
            s.ra_deg, s.dec_deg, auid=s.auid, name=s.name, source=s.source, mags=dict(s.mags)
        )
        return f"Target · {s.display_name}", rows, pending
    if kind == "variable":
        v = item
        if v.var_type:
            rows.append(
                {"key": "Type", "value": v.var_type + ("  (suspected)" if v.is_suspected else "")}
            )
        if v.max_mag:
            rows.append({"key": "Max", "value": v.max_mag})
        if v.min_mag and v.min_mag != "?":
            rows.append({"key": "Min", "value": v.min_mag})
        if v.period:
            rows.append({"key": "Period", "value": f"{v.period:g} d"})
        if v.auid:
            rows.append({"key": "AUID", "value": v.auid})
        rows += _radec_rows(v.ra_deg, v.dec_deg)
        pending = pending_star(v.ra_deg, v.dec_deg, auid=v.auid, name=v.name, source="vsx")
        return f"Variable · {v.name}", rows, pending
    if kind == "vsp":
        c = item
        rows.append({"key": "AAVSO VSP reference", "value": c.auid})
        with hub._lock:
            result = hub.field._catalog_result
            gaia = list(result.field_stars) if result is not None else []
        match = next(
            (
                s
                for s in gaia
                if separation_arcmin(c.ra_deg, c.dec_deg, s.ra_deg, s.dec_deg) <= 0.05
            ),
            None,
        )
        if match is not None:
            rows.append({"key": "Gaia DR3 source", "value": str(match.source_id)})
        mags = _mags_value((b.band, b.mag) for b in c.bands)
        if mags:
            rows.append({"key": "Magnitudes", "value": mags})
        bv = fc.b_minus_v(c)
        if bv is not None:
            rows.append({"key": "B−V", "value": f"{bv:.3f}"})
        if c.label:
            rows.append(
                {"key": "VSP chart code", "value": f"{c.label}  (magnitude code, not a name)"}
            )
        rows += _radec_rows(c.ra_deg, c.dec_deg)
        pending = pending_star(
            c.ra_deg,
            c.dec_deg,
            auid=c.auid,
            name=c.auid,
            source="vsp",
            mags=fc.comparison_mags(c),
            chart_id=c.chart_id,
        )
        return f"VSP reference · {c.auid}", rows, pending
    if kind == "simbad":
        rows.append({"key": "Source", "value": "SIMBAD"})
        rows.append({"key": "Object type", "value": item.object_type or "unavailable"})
        rows += [
            {"key": f"SIMBAD {band} magnitude", "value": f"{value:.3f}"}
            for band, value in getattr(item, "mags", ())
        ]
        rows += _radec_rows(item.ra_deg, item.dec_deg)
        pending = pending_star(
            item.ra_deg,
            item.dec_deg,
            auid=None,
            name=item.name,
            source="simbad",
            mags=dict(getattr(item, "mags", ())),
        )
        return f"Identified object · {item.name}", rows, pending
    if kind == "deep_sky":
        rows.append({"key": "Catalogue", "value": "Argos Essential Catalogue"})
        rows.append({"key": "Object type", "value": item.object_type or "Deep-sky object"})
        if item.magnitude is not None:
            rows.append({"key": "Magnitude", "value": f"{item.magnitude:.1f}"})
        if item.aliases:
            rows.append({"key": "Also", "value": ", ".join(item.aliases[:2])})
        rows += _radec_rows(item.ra_degrees, item.dec_degrees)
        pending = pending_star(
            item.ra_degrees,
            item.dec_degrees,
            auid=None,
            name=item.name,
            source="argos_essential",
            mags={"V": item.magnitude} if item.magnitude is not None else {},
        )
        return f"Deep-sky object · {item.name}", rows, pending
    if kind == "exoplanet":
        rows.append({"key": "Cached planet(s)", "value": ", ".join(item.planet_names)})
        rows += [
            {"key": f"{band} magnitude", "value": f"{value:.3f}"}
            for band, value in getattr(item, "mags", ())
        ]
        rows += _radec_rows(item.ra_degrees, item.dec_degrees)
        rows.append({"key": "Source", "value": "local NASA Exoplanet Archive cache"})
        pending = pending_star(
            item.ra_degrees,
            item.dec_degrees,
            auid=None,
            name=item.host_name,
            source="nasa_exoplanet_cache",
            mags=dict(getattr(item, "mags", ())),
        )
        return f"Exoplanet host · {item.host_name}", rows, pending
    if kind == "gaia":
        star, identity = item
        if identity is not None:
            rows.append({"key": "Name", "value": identity.name})
            rows.append({"key": "Object type", "value": identity.object_type or "—"})
        rows.append({"key": "Gaia DR3 source", "value": str(star.source_id)})
        for label, value in (
            ("Gaia G magnitude", star.g_mag),
            ("Gaia BP magnitude", star.bp_mag),
            ("Gaia RP magnitude", star.rp_mag),
        ):
            if value is not None:
                rows.append({"key": label, "value": f"{value:.3f}"})
        rows += _radec_rows(star.ra_deg, star.dec_deg)
        rows.append(
            {"key": "Sources", "value": "Gaia DR3" + (" · SIMBAD" if identity is not None else "")}
        )
        mags = {
            band: value
            for band, value in (("G", star.g_mag), ("BP", star.bp_mag), ("RP", star.rp_mag))
            if value is not None
        }
        pending = pending_star(
            star.ra_deg,
            star.dec_deg,
            auid=None,
            name=identity.name if identity is not None else star.display_name,
            source="gaia_dr3+simbad" if identity is not None else "gaia_dr3",
            mags=mags,
        )
        title = (
            f"Identified star · {identity.name}"
            if identity is not None
            else f"Gaia DR3 · {star.source_id}"
        )
        return title, rows, pending
    if kind == "point_identity":
        identity = item
        category = fc.object_category(identity.object_type)
        rows.append({"key": "Source", "value": identity.source})
        rows.append({"key": "Object type", "value": identity.object_type or "—"})
        if identity.gaia_source_id:
            rows.append({"key": "Gaia DR3 source", "value": str(identity.gaia_source_id)})
        rows += [
            {"key": f"{band} magnitude", "value": f"{value:.3f}"} for band, value in identity.mags
        ]
        rows += _radec_rows(identity.ra_deg, identity.dec_deg)
        rows.append({"key": "WCS match offset", "value": f"{identity.separation_arcsec:.1f}″"})
        pending = pending_star(
            identity.ra_deg,
            identity.dec_deg,
            auid=None,
            name=identity.name,
            source="point_catalogue",
            mags=dict(identity.mags),
        )
        kind_word = "star" if category == "star" else "object"
        return f"Identified {kind_word} · {identity.name}", rows, pending
    return None


def _measurement(meas, tracked, scale_green: float | None) -> dict[str, Any] | None:
    if meas is None:
        return None
    scale = scale_green or arcsec_per_green_px()
    fx, fy = to_frame(meas.x, meas.y)
    ra = dec = None
    if tracked is not None:
        ra, dec = tracked.pixel_to_radec(meas.x, meas.y)
    return {
        "x": round(fx, 2),
        "y": round(fy, 2),
        "fwhm_px": 2.0 * meas.fwhm if meas.fwhm is not None else None,
        "hfd_px": 2.0 * meas.hfd if meas.hfd is not None else None,
        "fwhm_arcsec": meas.fwhm * scale if meas.fwhm is not None else None,
        "hfd_arcsec": meas.hfd * scale if meas.hfd is not None else None,
        "eccentricity": meas.eccentricity,
        "snr": float(meas.snr),
        "peak_adu": int(meas.peak_adu),
        "sky_adu": float(meas.sky_adu),
        "ra_hours": ra,
        "dec_deg": dec,
    }


def _measurement_rows(meas, tracked, scale_green, hub) -> list[dict[str, str]]:
    """``_format_star_text`` (``imaging_page.py:1268-1295``) as rows."""
    scale = scale_green or arcsec_per_green_px()
    rows = []
    if meas.fwhm is not None:
        rows.append({"key": "FWHM", "value": f"{meas.fwhm * scale:.1f}″"})
    if meas.hfd is not None:
        rows.append({"key": "HFD", "value": f"{meas.hfd * scale:.1f}″"})
    if meas.eccentricity is not None:
        rows.append({"key": "Eccentricity", "value": f"{meas.eccentricity:.2f}"})
    rows.append({"key": "SNR", "value": f"{meas.snr:.0f}"})
    rows.append({"key": "Peak", "value": f"{meas.peak_adu} ADU"})
    if tracked is not None:
        ra_h, dec_d = tracked.pixel_to_radec(meas.x, meas.y)
        rows.append({"key": "RA", "value": format_ra_hms(ra_h)})
        rows.append({"key": "Dec", "value": format_dec_dms(dec_d)})
    else:
        pointing = hub._pointing()
        if pointing is not None:
            rows.append(
                {
                    "key": "Field",
                    "value": f"RA {pointing.ra_hours:.3f}h  Dec {pointing.dec_deg:+.2f}°",
                }
            )
    return rows


__all__ = ["FieldService"]
