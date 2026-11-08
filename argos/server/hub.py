"""The hub: device ownership, state machine, worker threads and event emission.

The HTTP layer is thin: every route calls one :class:`Hub` method from
FastAPI's threadpool. The hub keeps the contract records and is the only
writer of them.

Devices (API 2, rows A13-A15). Four device slots — mount, camera, filter
wheel, focuser — each with its own state (``disconnected``, ``connecting``,
``connected``, ``error``; ``busy`` is derived from the camera and mount
records), its own handle and its own *generation*. This is a Qt-free port of
``DeviceSession`` (``argos/core/session/device_session.py:230-501``) with the
problems of 02 §1.2-1.3 fixed: connects run in worker threads (the Qt app
ran them on the UI thread, freezing it for up to ~40 s on a dead address),
connect-all skips connected devices (the Qt app started a second mount
poller), and error texts are kept whole (Qt cut them to 48 characters). The
v1 ``ConnectionState`` is derived from the camera and mount slots, so the
v1 routes keep working on top of the per-device model.

Threads:

- the **request threads** (FastAPI's pool) run commands and device connects;
  a slow Alpaca call blocks only its own request;
- one **exposure job** thread at a time runs a single capture or a live loop;
- one **mount poller** thread reads the mount every ``poll_interval_s``
  (0.25 s for the simulator — the contract's 4 Hz ceiling) and publishes it;
  after ``mount_lost_after`` consecutive failures it hands over to a
  **mount retry** thread (``device_session.py:155-160, 299-333, 557-567``);
- the **network monitor** and **job** threads (``network.py``, ``jobs.py``);
- the **Stellarium bridge** thread, with its own event loop
  (``stellarium.py``, row A19); a GoTo it receives is run on a short-lived
  thread, never on the bridge's loop.

Locking: ``_lock`` guards the records and is never held across device I/O,
a thread join or a configuration write. Every state change happens under it
together with the publication of its event and a fresh sequence number, so
events leave in the order the changes happened. Lock order, outermost
first: ``_profile_guard`` → the config store's lock → ``_lock`` → the
site check's own lock (``site_check.py``, wave 2), which never calls out
while held; the hub never waits for the store while holding ``_lock``.

Wave 2 (Settings) adds services that are no device: the read-only file
listing (``fs.py``), the session list (``sessions.py``), the support bundle
and crash reports (``support.py``), the Settings helpers
(``settings_helpers.py``: ASTAP, caches, place search) and the site check
(``site_check.py``), fed by the mount poller.

Wave 3 (Observe: acquisition) drives the devices: capture settings and the
Take shot with its FITS save (``capture.py``, on the **save** thread), the
filter wheel (``wheel.py``, a thread per move), the focuser (``focuser.py``,
its **poll** thread), autofocus (``autofocus.py``, its own thread), the jog
dead-man (``jog.py``, a **watcher** thread), the observation identity and
catalogue lookups (``observation.py``) and the **metrics** thread with the
conditions rows (``conditions.py``). Every one keeps its records under
``_lock`` and never holds it across device I/O.

A command or connect that was already talking to a device when the observer
disconnected it must not write its answer into the state afterwards: every
connect and teardown bumps that slot's ``generation``, and a result read
under an older generation is discarded.
"""

from __future__ import annotations

import dataclasses
import logging
import secrets
import shutil
import socket
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from collections import deque
from concurrent.futures import ThreadPoolExecutor

from argos.core.config import observing_site
from argos.core.hardware import active, catalog
from argos.core.imaging.sky_geometry import compute_airmass
from argos.core.photometry.airmass import airmass_at, julian_date
from argos.server import API_VERSION
from argos.server import profiles as profile_records
from argos.server import runtime
from argos.server import settings_helpers, support
from argos.server.autofocus import (
    MAX_DEFAULT_EXPOSURE_S,
    AutofocusParams,
    AutofocusRun,
    idle_record,
)
from argos.server.capture import (
    FALLBACK_EXPOSURE_MAX_S,
    FALLBACK_GAIN_MAX,
    FRAME_TYPES,
    CaptureSettings,
    FrameSettings,
    Pointing,
    SaveJob,
    SaveRequest,
    image_type,
    is_dark_slot,
    is_light_frame,
    save_frame,
)
from argos.server.conditions import ConditionsLog, MetricsJob, MetricsWorker
from argos.server.config_meta import DATA_PATH_KEYS
from argos.server.config_store import ConfigStore
from argos.server.devices.base import (
    CameraDevice,
    CameraLimits,
    DeviceError,
    ExposureCancelled,
    MountDevice,
    MountParked,
    MountReading,
)
from argos.server.devices.sim_aux import SimOptics
from argos.server.discovery import DEFAULT_LAYERS, DiscoveryLayers, run_discovery
from argos.server.errors import ApiError
from argos.server.events import EventBus
from argos.server.fits_source import FITS_SUFFIXES, FitsReadError, load_raw_fits_frame
from argos.server.focuser import FocuserService
from argos.server.frames import FrameSource, encode_frame
from argos.server.fs import AllowedRoots, list_folder, parse_exts
from argos.server.jobs import JobCancelled, JobContext, JobManager
from argos.server.jog import JogService
from argos.server.logbook import LOG_HISTORY, LogBook
from argos.server.network import NetworkMonitor
from argos.server.observation import ObservationService
from argos.server.sessions import SessionIndex, is_session
from argos.server.settings import Settings, SimOptions
from argos.server.site_check import SITE_KEYS, SiteCheck
from argos.server.stellarium import StellariumBridge
from argos.server.state import (
    CAMERA_BUSY,
    CameraState,
    ConnectionState,
    MountState,
    Target,
    utc_iso,
)
from argos.server.wheel import FilterWheelService

logger = logging.getLogger(__name__)

#: How long ``stop`` waits for an exposure job to wind down before answering.
_STOP_JOIN_S = 2.0
#: How long disconnect/shutdown wait for a worker thread.
_SHUTDOWN_JOIN_S = 5.0
#: How long a request waits for a connect already running for the same device.
_CONNECT_WAIT_S = 60.0
#: Camera sensor temperature poll while connected (A21).
_CAMERA_TEMPERATURE_S = 10.0
#: A single Take shot re-exposes at most this many times when its frames
#: cannot be saved (the wheel moved during them), then gives up with a WARN.
_SINGLE_ATTEMPTS = 5
#: ``GET /api/camera/saved`` keeps the last saves.
_SAVES_KEPT = 200
#: The mount clock is too far off for GoTo / Sync / Center (telescope.py:283-294).
_CLOCK_LIMIT_S = 60.0

__all__ = ["Hub", "LOG_HISTORY", "DEVICE_IDS"]

LogLevel = Literal["debug", "cmd", "info", "ok", "warning", "error"]
_PY_LEVELS = {
    "debug": logging.DEBUG,
    "cmd": logging.INFO,
    "info": logging.INFO,
    "ok": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

DEVICE_IDS = ("mount", "camera", "filterwheel", "focuser")
LABELS = {"mount": "Mount", "camera": "Camera", "filterwheel": "Filter wheel", "focuser": "Focuser"}
#: device_session.py:252-256 — the mount first: its connect syncs the mount
#: clock, which every later GoTo depends on.
CONNECT_ORDER = ("mount", "camera", "filterwheel", "focuser")
#: device_session.py:258-263 — the camera first, so its exposure stops first.
DISCONNECT_ORDER = ("camera", "mount", "filterwheel", "focuser")
SIMULATOR_NAME = "ARGOS Simulator (Seestar S50)"
#: ``info`` of a device that a Connect all has claimed but not opened yet.
QUEUED = "queued"
PROFILE_LOCKED = (
    "Disconnect the equipment before changing the telescope: it sets plate scale, "
    "sensor geometry and FITS metadata."
)


@dataclass(frozen=True)
class Link:
    """Where devices are connected: the simulator, or one Alpaca server."""

    mode: Literal["simulator", "alpaca"]
    host: str | None = None
    port: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "host": self.host, "port": self.port}

    @property
    def where(self) -> str:
        return "simulator" if self.mode == "simulator" else f"{self.host}:{self.port}"


class _Slot:
    """One device's connection state (hub lock held for every access)."""

    def __init__(self, device_id: str) -> None:
        self.id = device_id
        self.state = "disconnected"
        self.name: str | None = None
        self.info: str | None = None
        self.error: str | None = None
        self.retrying = False
        self.warnings: tuple[str, ...] = ()
        self.link: Link | None = None
        self.since = utc_iso()
        self.handle: Any = None
        self.generation = 0
        #: Set when the running connect attempt ends (waiters on it wake up).
        self.settled: threading.Event | None = None
        #: Set to stop the mount's auto-retry thread.
        self.retry_stop: threading.Event | None = None

    def reset(self) -> None:
        if self.state != "disconnected":
            self.since = utc_iso()
        self.state = "disconnected"
        self.name = self.info = self.error = None
        self.retrying = False
        self.warnings = ()
        self.link = None


def _error_text(exc: BaseException, label: str) -> str:
    """The driver's text without the adapter's ``"<Device>: "`` prefix."""
    text = str(exc).strip() or exc.__class__.__name__
    prefix = f"{label}: "
    return text[len(prefix) :] if text.startswith(prefix) else text


class Hub:
    """Owns the devices and the contract state; thread-safe."""

    def __init__(
        self,
        bus: EventBus | None = None,
        sim: SimOptions | None = None,
        *,
        config: ConfigStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.bus = bus or EventBus()
        #: Identifies this server process (``/api/health``, ``status``, ``GET /api/logs``):
        #: log ``seq`` numbers start again at 1 in a new process, so a client that
        #: sees another id knows its lines come from a restarted server.
        self.boot_id = secrets.token_hex(8)
        self._settings = settings or Settings(token="unused", sim=sim or SimOptions())
        self._sim = sim or self._settings.sim
        self._lock = threading.RLock()
        self._profile_guard = threading.Lock()
        self._seq = 0  # event sequence (ordering of snapshots)
        self._frame_seq = 0  # frame sequence (contract "seq")

        self._slots: dict[str, _Slot] = {dev: _Slot(dev) for dev in DEVICE_IDS}
        # Bumped by disconnect_all: a connect-all in progress stops before its next device.
        self._release_epoch = 0
        self._camera_state = CameraState()
        self._mount_state = MountState()
        self._last_devices: dict[str, Any] | None = None
        self._activity: dict[str, Any] | None = None

        self._job: threading.Thread | None = None
        self._job_cancel: threading.Event | None = None
        self._poller: threading.Thread | None = None
        self._poller_stop: threading.Event | None = None
        self._mount_failing = False
        #: Exposure and gain the running live view uses from its next frame on.
        self._live_settings: tuple[float, int] | None = None

        self.logbook = LogBook()
        #: Numbering and handing a log line to the bus happen under one lock, so
        #: lines leave in ``seq`` order even when threads log at the same time.
        self._log_lock = threading.Lock()
        #: Set by ``mount_stop`` so the end of that slew reads "Slew stopped".
        self._slew_stop_requested = False
        self.stellarium = StellariumBridge(self._on_stellarium_goto, self._publish_stellarium)
        self._last_goto: dict[str, Any] | None = None
        self.config = config or ConfigStore(self._settings.config_dir)
        self.jobs = JobManager(self.publish_event)
        self.network = NetworkMonitor(
            self._alpaca_address,
            self._publish_network,
            interval_s=self._settings.network_interval_s,
            timeout_s=self._settings.network_probe_timeout_s,
        )
        #: The layered discovery's network operations (tests replace them).
        self.discovery_layers: DiscoveryLayers = DEFAULT_LAYERS
        #: The place search's HTTP getter (tests replace it; row A82).
        self.place_http_get: settings_helpers.HttpGet = settings_helpers.requests_get
        #: Folders the file listing and the support bundle may touch (row A11).
        self.fs_roots = AllowedRoots(
            self.config.get, extra=lambda: (self.config.directory, self._settings.log_dir)
        )
        self.sessions = SessionIndex()
        #: Files a finished job serves on ``GET /api/jobs/{id}/download``.
        self._downloads: dict[str, tuple[Path, str]] = {}
        self._download_dir: Path | None = None
        self._downloads_lock = threading.Lock()
        #: Settings site against the mount (PROPOSAL §7; protocol.md "Site check").
        self.site_check = SiteCheck(
            self.config.get,
            self._announce_site_check,
            self._site_check_log,
            period_s=self._settings.site_check_period_s,
            settle_s=self._settings.site_check_settle_s,
        )
        # -- wave 3 (Observe: acquisition) -------------------------------------
        self._capture_settings = CaptureSettings()
        self._camera_state = dataclasses.replace(
            self._camera_state, settings=self._capture_settings.to_dict()
        )
        #: The pending Take shot (``_capture_pending`` of the Qt engine).
        self._save: SaveRequest | None = None
        #: Logged once per pending save: why a frame was not the one saved.
        self._save_notes: set[str] = set()
        self._camera_limits: CameraLimits | None = None
        self._camera_temp_stop: threading.Event | None = None
        #: The newest mount reading of the current connection (X1), else None.
        self._last_reading: MountReading | None = None
        #: The last GoTo target of this process (the Qt ``target_radec``, kept
        #: across park and reconnects; FITS TARGRA / TARGDEC).
        self._goto_target: tuple[float, float] | None = None
        self._sim_optics = SimOptics(best_focus=self._sim.focus_best)
        self.wheel = FilterWheelService(self)
        self.wheel.on_settled = self._on_wheel_settled
        self.focuser = FocuserService(self)
        self.focuser.on_halt_during_autofocus = self._halt_autofocus
        self.jog = JogService(self, deadman_s=self._settings.jog_deadman_s)
        self.observation = ObservationService(self)
        self.conditions = ConditionsLog()
        self.conditions.boot_id = self.boot_id
        self.metrics = MetricsWorker(self._on_metrics)
        self._saver = ThreadPoolExecutor(max_workers=1, thread_name_prefix="argos-save")
        self._saves: deque[dict[str, Any]] = deque(maxlen=_SAVES_KEPT)
        self._save_seq = 0
        #: Take-shot frames handed to the save thread and not yet written.
        self._saves_in_flight = 0
        #: Offset / binning sent to the driver: in progress (count) and when the
        #: last one ended. A frame exposed across such a change is never saved:
        #: FITS OFFSET is read from the camera at save time (S2 review).
        self._readout_changing = 0
        self._readout_changed_at: datetime | None = None
        self._autofocus: AutofocusRun | None = None
        self._af_record: dict[str, Any] = idle_record()
        self._af_runs = 0

        self.config.add_listener(self._on_config_changed)
        if self.config.load_error:
            self.log(
                "error", f"Configuration unreadable, defaults in use: {self.config.load_error}"
            )
        if self._settings.manage_process:
            runtime.apply_log_level(self.config.get("ui.log_level", "INFO"))
            runtime.apply_data_paths(self.config.get)
        self._apply_profile_from_config(announce=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background services (the event loop is attached)."""
        if self._settings.network_interval_s > 0:
            self.network.start()

    def shutdown(self) -> None:
        """Release everything at server exit."""
        self.jobs.shutdown()
        self.network.stop()
        self.stellarium.stop(announce=False)
        run = self._autofocus
        if run is not None:
            run.stop()  # return the focuser to its start, bounded by the join below
            run.thread.join(_SHUTDOWN_JOIN_S)
        for dev in DISCONNECT_ORDER:
            self._disconnect_device(dev, quiet=True)
        self.jog.close()
        self.metrics.close()
        self._saver.shutdown(wait=True)  # a FITS being written is finished, never cut
        with self._lock:
            self._publish_status()
        with self._downloads_lock:
            folder, self._download_dir = self._download_dir, None
            self._downloads.clear()
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        self.log("info", "Server shutting down — devices released", topic="app")

    # ------------------------------------------------------------------
    # Snapshots and events
    # ------------------------------------------------------------------

    def _device_record(self, slot: _Slot) -> dict[str, Any]:
        state, info = slot.state, slot.info
        if state == "connected":
            if slot.id == "camera" and self._camera_state.state in CAMERA_BUSY:
                state, info = "busy", self._camera_state.state
            elif slot.id == "mount" and self._mount_state.state == "slewing":
                state, info = "busy", "slewing"
        return {
            "state": state,
            "name": slot.name,
            "info": info,
            "error": slot.error,
            "retrying": slot.retrying,
            "warnings": list(slot.warnings),
            "link": slot.link.to_dict() if slot.link is not None else None,
            "since": slot.since,
        }

    def _devices_payload(self) -> dict[str, Any]:
        return {dev: self._device_record(slot) for dev, slot in self._slots.items()}

    def _connection(self) -> ConnectionState:
        """The v1 record, derived from the camera and mount slots."""
        camera, mount = self._slots["camera"], self._slots["mount"]
        states = (camera.state, mount.state)
        if "connecting" in states:
            state = "connecting"
        elif "connected" in states:
            state = "connected"
        elif "error" in states:
            state = "error"
        else:
            return ConnectionState()
        if state == "error":
            failed = camera if camera.state == "error" else mount
            mode = failed.link.mode if failed.link else None
            return ConnectionState(state="error", mode=mode, message=failed.error)
        live = [s for s in (mount, camera) if s.state == state]
        link = live[0].link
        mode = link.mode if link else None
        name = None
        if state == "connected":
            name = SIMULATOR_NAME if mode == "simulator" else live[0].name
        return ConnectionState(state=state, mode=mode, device_name=name, message=None)

    def _status_payload(self) -> dict[str, Any]:
        return {
            "boot_id": self.boot_id,
            "connection": self._connection().to_dict(),
            "camera": self._camera_state.to_dict(),
            "mount": self._mount_state.to_dict(),
            "devices": self._devices_payload(),
            "profile": profile_records.summary(active.profile()),
            "site_check": self.site_check.record(),
            # wave 3: so a client opened later has every record at once
            "filterwheel": self.wheel.record(),
            "focuser": self.focuser.record(),
            "autofocus": self._autofocus_record(),
            "observation": self.observation.record(),
        }

    def status(self) -> dict[str, Any]:
        """``GET /api/status`` body."""
        with self._lock:
            return self._status_payload()

    def status_event(self) -> tuple[int, dict[str, Any]]:
        """The current ``status`` event with its sequence number (for a new client)."""
        with self._lock:
            return self._seq, {"type": "status", **self._status_payload()}

    def initial_snapshots(self) -> list[tuple[str, int, dict[str, Any]]]:
        """Snapshots a new ``/ws/events`` client gets right after ``status``."""
        with self._lock:
            seq = self._seq
            snapshots = [("network", seq, {"type": "network", **self.network.snapshot()})]
            snapshots.append(
                ("stellarium", seq, {"type": "stellarium", **self._stellarium_state()})
            )
            if self._activity is not None:
                snapshots.append(("activity", seq, {"type": "activity", **self._activity}))
            return snapshots

    def devices(self) -> dict[str, Any]:
        with self._lock:
            return self._devices_payload()

    def _publish(self, kind: str, payload: dict[str, Any]) -> None:
        """Publish a snapshot event (lock held, so the sequence follows the changes)."""
        self._seq += 1
        self.bus.publish(kind, self._seq, {"type": kind, **payload})

    def publish_event(self, kind: str, payload: dict[str, Any]) -> None:
        """Publish a ready-made event under a bus *kind* (jobs use ``job:<id>``)."""
        with self._lock:
            self._seq += 1
            self.bus.publish(kind, self._seq, payload)

    def _publish_status(self) -> None:
        """``devices`` (when it changed) then ``status``; lock held."""
        devices = self._devices_payload()
        if devices != self._last_devices:
            self._last_devices = devices
            self._publish("devices", {"devices": devices})
        self._publish("status", self._status_payload())

    def _publish_network(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._publish("network", state)

    def _set_camera(self, **changes: Any) -> CameraState:
        with self._lock:
            new = dataclasses.replace(self._camera_state, **changes)
            if new != self._camera_state:
                self._camera_state = new
                self._publish("camera", {"camera": new.to_dict()})
                self._publish_status()
            return new

    def _apply_mount(self, new: MountState, telemetry: bool) -> MountState:
        """Store a mount state: ``status`` on a transition, ``mount`` if *telemetry*."""
        with self._lock:
            changed = new.discrete() != self._mount_state.discrete()
            slew_ended = self._mount_state.state == "slewing" and new.state != "slewing"
            self._mount_state = new
            if changed:
                self._publish_status()
            if telemetry:
                self._publish("mount", {"mount": new.to_dict()})
                if self._slots["mount"].state == "connected":
                    self.stellarium.set_position(new.ra_hours, new.dec_deg, new.state == "slewing")
            if slew_ended:
                stopped, self._slew_stop_requested = self._slew_stop_requested, False
                self.set_activity(
                    "Slew stopped" if stopped else "Slew finished",
                    source="mount",
                    topic="mount",
                    log=False,
                )
            return new

    def _mount_from_reading(self, reading: MountReading) -> MountState:
        """The current record with a new reading (target, geometry, jog kept)."""
        with self._lock:
            return dataclasses.replace(
                self._mount_state,
                state=reading.state,
                ra_hours=reading.ra_hours,
                dec_deg=reading.dec_deg,
                alt_deg=reading.alt_deg,
                az_deg=reading.az_deg,
                tracking=reading.tracking,
                pier_side=reading.pier_side,
            )

    def _set_mount_extras(self, **changes: Any) -> None:
        """Lock held: change wave 3 mount fields (jog, rate…) and announce them."""
        self._apply_mount(dataclasses.replace(self._mount_state, **changes), telemetry=True)

    # -- log and activity ------------------------------------------------------

    def log(
        self, level: LogLevel, message: str, *, source: str = "server", topic: str = "app"
    ) -> None:
        """Log to Python logging and to every ``/ws/events`` client."""
        logger.log(_PY_LEVELS.get(level, logging.INFO), message)
        self.publish_log(level, message, source=source, topic=topic)

    def publish_log(
        self, level: LogLevel, message: str, *, source: str = "server", topic: str = "app"
    ) -> None:
        """Record one observer log line and send it (no Python logging)."""
        if level == "debug" and str(self.config.get("ui.log_level", "INFO")).upper() != "DEBUG":
            return
        with self._log_lock:
            entry = self.logbook.append(level, message, source, topic)
            self.bus.publish("log", None, entry)

    def log_history(self) -> list[dict[str, Any]]:
        """The last :data:`LOG_HISTORY` log events, oldest first."""
        return self.logbook.recent(LOG_HISTORY)

    def set_activity(
        self, text: str, *, source: str = "server", topic: str = "app", log: bool = True
    ) -> None:
        """The status-bar activity text (row A4); also a ``cmd`` log line if *log*."""
        with self._lock:
            self._activity = {"text": text, "source": source, "t": utc_iso()}
            self._publish("activity", dict(self._activity))
        if log:
            self.log("cmd", text, source=source, topic=topic)

    # -- site check (PROPOSAL §7) -------------------------------------------------

    def _announce_site_check(self) -> None:
        """Publish the site-check record and a ``status`` (called with no checker lock)."""
        with self._lock:
            self._publish("site_check", self.site_check.record())
            self._publish_status()

    def _site_check_log(self, level: str, message: str) -> None:
        known: LogLevel = level if level in _PY_LEVELS else "info"  # type: ignore[assignment]
        self.log(known, message, source="mount", topic="mount")

    def site_check_state(self) -> dict[str, Any]:
        """``GET /api/site/check``."""
        return self.site_check.record()

    def site_check_now(self) -> dict[str, Any]:
        """``POST /api/site/check``: compare the latest mount reading now."""
        record = self.site_check.check_now()
        if record is None:
            raise ApiError(409, "not_connected", "No mount connected")
        return record

    # ------------------------------------------------------------------
    # Configuration side effects (called with the store lock held)
    # ------------------------------------------------------------------

    def _on_config_changed(
        self, changed: dict[str, Any], values: dict[str, Any], revision: int, source: str
    ) -> None:
        with self._lock:
            self._publish(
                "config",
                {"changed": changed, "values": values, "revision": revision, "source": source},
            )
        if self._settings.manage_process:
            if "ui.log_level" in changed:
                runtime.apply_log_level(changed["ui.log_level"])
            if DATA_PATH_KEYS & changed.keys():
                runtime.apply_data_paths(self.config.get)
        if "alpaca.host" in changed or "alpaca.port" in changed:
            self.network.wake()
        if SITE_KEYS & changed.keys():
            self.site_check.site_changed()
        if "hardware.profile" in changed or any(
            key.startswith("hardware.overrides.") for key in changed
        ):
            self._apply_profile_from_config(announce=True)

    def _apply_profile_from_config(self, announce: bool) -> None:
        """``active.load_from_config`` (active.py:92-110) on the server's config."""
        profile = active.load_from_config(self.config)
        with self._lock:
            self._publish_status()
        if announce:
            message = f"Telescope profile: {profile.describe()}"
            self.log("info", message, source="profile", topic="connection")

    def _alpaca_address(self) -> tuple[str, int]:
        host = self.config.get("alpaca.host", "") or ""
        try:
            port = int(self.config.get("alpaca.port", 32323))
        except (TypeError, ValueError):
            port = 32323
        return str(host), port

    # ------------------------------------------------------------------
    # Profiles (row A17)
    # ------------------------------------------------------------------

    def _profile_locked_reason(self) -> str | None:
        for slot in self._slots.values():
            if slot.state in ("connecting", "connected") or slot.retrying:
                return PROFILE_LOCKED
        return None

    def profiles(self) -> dict[str, Any]:
        with self._lock:
            reason = self._profile_locked_reason()
        return profile_records.profiles_state(reason, self.config.get("hardware.overrides", {}))

    def set_profile(self, key: str) -> dict[str, Any]:
        """``PUT /api/profile``: port of ``apply_telescope_profile``.

        ``connection_page.py:237-258``: refused while equipment is connected;
        choosing the active profile again is always accepted.
        """
        if catalog.get(key) is None:
            known = ", ".join(catalog.keys())
            raise ApiError(400, "invalid_argument", f"Unknown telescope {key!r} (known: {known})")
        with self._profile_guard:
            with self._lock:
                if key != active.profile().key:
                    reason = self._profile_locked_reason()
                    if reason is not None:
                        raise ApiError(409, "busy", reason)
            self.config.set_internal({"hardware.profile": key}, source="api")
            if active.profile().key != key:  # unchanged in the file, stale in memory
                self._apply_profile_from_config(announce=True)
        return self.profiles()

    # ------------------------------------------------------------------
    # Devices (rows A13-A15) and the v1 connection
    # ------------------------------------------------------------------

    def _slot(self, device_id: str) -> _Slot:
        slot = self._slots.get(device_id)
        if slot is None:
            raise ApiError(404, "not_found", f"Unknown device {device_id!r}")
        return slot

    def resolve_link(self, mode: str, host: str | None, port: int | None) -> Link:
        """The link a connect request names, with the config's address as default."""
        if mode == "simulator":
            return Link("simulator")
        if mode != "alpaca":
            raise ApiError(400, "invalid_argument", f"Unknown connection mode {mode!r}")
        cfg_host, cfg_port = self._alpaca_address()
        host = (host or cfg_host or "").strip()
        if not host:
            raise ApiError(400, "invalid_argument", "Enter the Seestar address first")
        return Link("alpaca", host, int(port if port is not None else cfg_port))

    def _check_link(self, link: Link) -> None:
        """One link at a time (lock held): 409 if a device uses another one."""
        for slot in self._slots.values():
            holds = slot.state in ("connecting", "connected") or slot.retrying
            if holds and slot.link is not None and slot.link != link:
                raise ApiError(
                    409,
                    "busy",
                    f"Devices are connected to {slot.link.where} — disconnect them before "
                    f"connecting to {link.where}",
                )

    def _open_device(self, device_id: str, link: Link) -> Any:
        """Create and connect one device handle (blocking; never under the lock)."""
        if link.mode == "simulator":
            sim = self._sim
            if device_id == "camera":
                from argos.server.devices.sim_camera import SimCamera

                return SimCamera(
                    sim.width,
                    sim.height,
                    seed=sim.seed,
                    n_stars=sim.n_stars,
                    optics=self._sim_optics,
                )
            if device_id == "mount":
                from argos.server.devices.sim_mount import SimMount

                return SimMount(
                    slew_rate_deg_s=sim.slew_rate_deg_s, poll_interval_s=sim.mount_poll_s
                )
            from argos.server.devices.sim_aux import SimFilterWheel, SimFocuser

            if device_id == "filterwheel":
                return SimFilterWheel(self._sim_optics, slot_s=sim.wheel_slot_s)
            return SimFocuser(self._sim_optics, speed_steps_s=sim.focuser_speed_steps_s)
        if link.mode == "alpaca":
            self._precheck(str(link.host), int(link.port or 0))
            from argos.server.devices import alpaca as adapter

            factory = {
                "camera": adapter.AlpacaCamera,
                "mount": adapter.AlpacaMount,
                "filterwheel": adapter.AlpacaFilterWheel,
                "focuser": adapter.AlpacaFocuser,
            }[device_id]
            return factory(str(link.host), int(link.port or 0))
        raise ApiError(400, "invalid_argument", f"Unknown connection mode {link.mode!r}")

    def _precheck(self, host: str, port: int) -> None:
        """One TCP connect before any Alpaca call (see protocol.md "Unreachable addresses").

        alpyca holds one process-wide lock during each HTTP request
        (``alpaca.device.Device._ctid_lock``), so a request hanging on a
        black-hole address would stall every other device for its 5 s
        timeout; this check fails such an address first, outside that lock.
        """
        timeout = self._settings.connect_timeout_s
        if not timeout:
            return
        try:
            with socket.create_connection((host, port), timeout=timeout):
                pass
        except socket.timeout as exc:
            raise DeviceError(
                f"Cannot reach {host}:{port} — timed out after {timeout:g} s"
            ) from exc
        except OSError as exc:
            reason = exc.strerror or str(exc) or exc.__class__.__name__
            raise DeviceError(f"Cannot reach {host}:{port} — {reason}") from exc

    @staticmethod
    def _connect_report(handle: Any) -> list[tuple[str, str]]:
        report = getattr(handle, "connect_report", None)
        if report is None:
            return []
        try:
            return list(report())
        except Exception as exc:  # a description must never fail a connect
            logger.warning("Connect report failed: %s", exc)
            return []

    def _connect_device(
        self, device_id: str, link: Link, quiet: bool = False, claimed: int | None = None
    ) -> str:
        """Connect one device; returns ``"connected"``, ``"skipped"`` (already was)
        or ``"released"`` (a Connect all's claim that was released meanwhile).

        Blocking (≤ connect-timeout + the driver's timeouts); call it from a
        worker thread. *quiet* keeps the per-device log lines out (the v1
        route logs one summary line instead, as API 1 did). *claimed* is the
        slot generation a Connect all reserved (``connecting``, info
        ``queued``): the device is opened under it, unless a disconnect
        released it meanwhile.
        """
        label = LABELS[device_id]
        with self._profile_guard:
            with self._lock:
                slot = self._slot(device_id)
                waiter = None
                if claimed is not None:
                    if slot.generation != claimed or slot.state != "connecting":
                        return "released"
                    generation = claimed
                    slot.info = None  # its turn: no longer queued
                    self._publish_status()
                elif slot.state == "connected" and slot.link == link:
                    return "skipped"
                elif slot.state == "connecting" and slot.link == link and slot.settled is not None:
                    waiter = slot.settled
                else:
                    self._check_link(link)
                    self._stop_retry(slot)
                    slot.generation += 1
                    generation = slot.generation
                    slot.reset()
                    slot.state, slot.link, slot.since = "connecting", link, utc_iso()
                    slot.settled = threading.Event()
                    self._publish_status()
        if waiter is not None:
            return self._wait_for_connect(device_id, link, waiter)

        self.set_activity(
            f"Connecting {label.lower()} {link.where}…",
            source=device_id,
            topic="connection",
            log=not quiet,
        )
        reading: MountReading | None = None
        try:
            handle = self._open_device(device_id, link)
        except ApiError:
            with self._lock:
                if slot.generation == generation:
                    settled, slot.settled = slot.settled, None
                    slot.reset()
                    self._publish_status()
                    if settled is not None:
                        settled.set()
            raise
        except Exception as exc:
            text = _error_text(exc, label)
            with self._lock:
                current = slot.generation == generation
                settled = None
                if current:
                    settled, slot.settled = slot.settled, None
                    slot.state, slot.error, slot.info, slot.since = "error", text, text, utc_iso()
                    self._publish_status()
            if settled is not None:
                settled.set()
            if not current:
                raise ApiError(
                    409, "not_connected", f"{label} was disconnected while connecting"
                ) from exc
            # The outcome replaces "Connecting …" in the status bar (no ellipsis).
            self.set_activity(f"{label}: {text}", source=device_id, topic="connection", log=False)
            if not quiet:
                self.log("error", f"{label}: {text}", source=device_id, topic="connection")
            raise ApiError(502, "connection_failed", text) from exc

        report = self._connect_report(handle)
        extras: dict[str, Any] = {}
        if device_id == "mount":
            try:
                reading = handle.read()
            except Exception as exc:
                logger.warning("First mount read failed: %s", exc)
            extras = _mount_extras(handle)
        elif device_id == "camera":
            extras = _camera_extras(handle)
        if not self._install(device_id, generation, handle, report, reading, extras):
            _close_quietly(handle)
            raise ApiError(409, "not_connected", f"{label} was disconnected while connecting")

        name = getattr(handle, "name", None) or label
        self.set_activity(f"{label} connected", source=device_id, topic="connection", log=False)
        if not quiet:
            if device_id == "filterwheel":
                line = f"Filter wheel connected — {handle.info()}"
            elif device_id == "focuser":
                line = f"Focuser connected: {name}  pos={getattr(handle, 'position', '?')}"
            else:
                line = f"{label} connected: {name}"
            self.log("ok", line, source=device_id, topic="connection")
        self._log_report(report, device_id)
        if link.mode == "alpaca":
            self._remember_address(link)
        return "connected"

    def _log_report(self, report: list[tuple[str, str]], device_id: str) -> None:
        for level, message in report:
            known: LogLevel = level if level in _PY_LEVELS else "info"  # type: ignore[assignment]
            self.log(known, message, source=device_id, topic="connection")

    def _wait_for_connect(self, device_id: str, link: Link, settled: threading.Event) -> str:
        label = LABELS[device_id]
        settled.wait(_CONNECT_WAIT_S)
        with self._lock:
            slot = self._slots[device_id]
            if slot.state == "connected" and slot.link == link:
                return "connected"
            if slot.state == "error" and slot.link == link:
                raise ApiError(502, "connection_failed", slot.error or f"{label} failed")
            if slot.state == "connecting":
                raise ApiError(409, "busy", f"{label} is still connecting")
        raise ApiError(409, "not_connected", f"{label} was disconnected while connecting")

    def _install(
        self,
        device_id: str,
        generation: int,
        handle: Any,
        report: list[tuple[str, str]],
        reading: MountReading | None,
        extras: dict[str, Any] | None = None,
    ) -> bool:
        """Store a freshly connected handle unless the attempt was superseded."""
        extras = extras or {}
        with self._lock:
            slot = self._slots[device_id]
            if slot.generation != generation or slot.state != "connecting":
                return False
            settled, slot.settled = slot.settled, None
            slot.handle = handle
            slot.state, slot.since = "connected", utc_iso()
            slot.name = getattr(handle, "name", None)
            slot.info = handle.info() if device_id in ("filterwheel", "focuser") else slot.name
            slot.error = None
            slot.warnings = tuple(m for level, m in report if level in ("warning", "error"))
            if device_id == "camera":
                limits: CameraLimits | None = extras.get("limits")
                self._camera_limits = limits
                offset = extras.get("offset")
                self._capture_settings = dataclasses.replace(
                    self._capture_settings,
                    offset=offset,
                    binning=1,
                )
                self._camera_state = dataclasses.replace(
                    self._camera_state,
                    state="idle",
                    sensor=handle.sensor(),
                    owner="idle",
                    current=None,
                    save_pending=0,
                    waiting_for=None,
                    limits=_limits_record(limits),
                    offset=(
                        {"min": limits.offset_range[0], "max": limits.offset_range[1]}
                        if limits is not None and limits.offset_range is not None
                        else None
                    ),
                    binning=(
                        {"max": limits.max_bin}
                        if limits is not None and limits.max_bin > 1
                        else None
                    ),
                    temperature_c=extras.get("temperature_c"),
                )
                self._refresh_camera()
                self._publish("camera", {"camera": self._camera_state.to_dict()})
                self._start_camera_temperature(handle, generation)
            elif device_id == "mount":
                self._mount_failing = False
                self._last_reading = reading
                # A fresh record: nothing (a target…) carries over from a previous session.
                self._mount_state = MountState(jog=self.jog.record(), **extras)
                if reading is not None:
                    self._mount_state = self._mount_from_reading(reading)
                self._start_poller(handle, generation)
            self._publish_status()
        if settled is not None:
            settled.set()
        if device_id == "mount":
            self.site_check.mount_connected(generation, _driver_site(handle))
        elif device_id == "filterwheel":
            self.wheel.attach(handle, generation)
        elif device_id == "focuser":
            self.focuser.attach(handle, generation)
        return True

    def _remember_address(self, link: Link) -> None:
        """The last Alpaca address used becomes the default (device_session.py:266-267)."""
        changes: dict[str, Any] = {}
        if self.config.get("alpaca.host") != link.host:
            changes["alpaca.host"] = link.host
        if self.config.get("alpaca.port") != link.port:
            changes["alpaca.port"] = link.port
        if changes:
            try:
                self.config.set_internal(changes, source="api")
            except ApiError as exc:
                logger.warning("Could not remember the Alpaca address: %s", exc.message)

    def _stop_retry(self, slot: _Slot) -> None:
        """Lock held: end the mount's auto-retry loop (the generation bump follows)."""
        if slot.retry_stop is not None:
            slot.retry_stop.set()
            slot.retry_stop = None
        slot.retrying = False

    def _disconnect_device(self, device_id: str, quiet: bool = False) -> None:
        """Stop the device's threads, close it; idempotent (stops the auto-retry too)."""
        label = LABELS[device_id]
        job = cancel = poller = stop = None
        if device_id == "mount":
            # H3: a jogging axis is stopped while the handle can still reach the mount.
            self.jog.stop_all_before("Mount disconnected")
        with self._lock:
            slot = self._slot(device_id)
            was, was_retrying = slot.state, slot.retrying
            # Claimed by a Connect all but never opened: nothing to announce.
            was_queued = was == "connecting" and slot.info == QUEUED
            slot.generation += 1
            generation = slot.generation
            handle, slot.handle = slot.handle, None
            settled, slot.settled = slot.settled, None
            self._stop_retry(slot)
            if device_id == "camera":
                job, cancel = self._job, self._job_cancel
                self._job = self._job_cancel = None
                self._save = None
                if self._camera_temp_stop is not None:
                    self._camera_temp_stop.set()
                    self._camera_temp_stop = None
            elif device_id == "mount":
                poller, stop = self._poller, self._poller_stop
                self._poller = self._poller_stop = None
                self._last_reading = None  # X1: no pointing from a gone mount
            slot.reset()
            self._publish_status()
            run = self._autofocus
        if settled is not None:
            settled.set()
        if run is not None and device_id == "camera":
            run.stop()  # the focuser goes back to its start; the camera is gone
        elif run is not None and device_id == "focuser":
            run.halt()  # nothing can move a focuser being disconnected
        if device_id == "mount":
            self.jog.mount_gone()
        elif device_id == "filterwheel":
            self.wheel.detach()
        elif device_id == "focuser":
            self.focuser.detach()
        if cancel is not None:
            cancel.set()
        if job is not None and handle is not None:
            try:
                handle.abort()
            except Exception as exc:
                logger.warning("Camera abort: %s", exc)
        if job is not None:
            job.join(_SHUTDOWN_JOIN_S)
        if stop is not None:
            stop.set()
        if poller is not None and poller is not threading.current_thread():
            poller.join(_SHUTDOWN_JOIN_S)
        if handle is not None:
            _close_quietly(handle)
        with self._lock:
            current = slot.generation == generation  # no new connect started meanwhile
            if current:
                if device_id == "camera":
                    self._camera_limits = None
                    self._set_camera(
                        state="idle",
                        sensor=None,
                        owner="autofocus" if self._autofocus is not None else "idle",
                        current=None,
                        save_pending=0,
                        waiting_for=None,
                        limits=None,
                        offset=None,
                        binning=None,
                        temperature_c=None,
                    )
                elif device_id == "mount" and self._mount_state != MountState():
                    self._mount_state = MountState()
                    self._publish_status()
        if device_id == "mount" and current:
            self.site_check.mount_disconnected(before=generation)
        if not quiet and not was_queued and (was in ("connecting", "connected") or was_retrying):
            self.log("info", f"{label} disconnected.", source=device_id, topic="connection")
            self.set_activity(
                f"{label} disconnected", source=device_id, topic="connection", log=False
            )

    def connect_device(
        self, device_id: str, mode: str = "alpaca", host: str | None = None, port: int | None = None
    ) -> dict[str, Any]:
        """``POST /api/devices/{id}/connect``."""
        self._slot(device_id)
        self._connect_device(device_id, self.resolve_link(mode, host, port))
        return self.devices()

    def disconnect_device(self, device_id: str) -> dict[str, Any]:
        """``DELETE /api/devices/{id}`` (also "Stop retrying" for the mount)."""
        self._slot(device_id)
        self._disconnect_device(device_id)
        return self.devices()

    def connect_all(
        self, mode: str = "alpaca", host: str | None = None, port: int | None = None
    ) -> dict[str, Any]:
        """``POST /api/devices/connect-all``: skips the devices already connected.

        Every device still to connect is claimed at once: it is
        ``connecting`` with ``info: "queued"`` until its turn, so the profile
        is locked, the clients show the run and Disconnect all (or a row's
        Cancel) can stop it from the first moment. The address is then
        checked once: when nothing answers there, every claimed device fails
        at once with that reason, instead of the observer waiting for one
        timeout per device.
        """
        link = self.resolve_link(mode, host, port)
        claimed: dict[str, int] = {}
        with self._profile_guard:
            with self._lock:
                self._check_link(link)
                epoch = self._release_epoch
                for device_id in CONNECT_ORDER:
                    slot = self._slots[device_id]
                    if slot.state in ("connected", "connecting"):
                        continue  # done already, or another request is opening it
                    self._stop_retry(slot)
                    slot.generation += 1
                    slot.reset()
                    slot.state, slot.link, slot.since = "connecting", link, utc_iso()
                    slot.info = QUEUED
                    slot.settled = threading.Event()
                    claimed[device_id] = slot.generation
                if claimed:
                    self._publish_status()
        if link.mode == "alpaca" and claimed:
            self.set_activity(
                f"Connecting equipment {link.where}…", source="server", topic="connection"
            )
            try:
                self._precheck(str(link.host), int(link.port or 0))
            except DeviceError as exc:
                self._fail_unreachable(claimed, link, str(exc))
                return self.devices()
        for device_id in CONNECT_ORDER:
            # "Disconnect all" meanwhile cancels the rest of the sequence (the
            # device being opened is dropped by its own generation check).
            with self._lock:
                if self._release_epoch != epoch:
                    break
            try:
                self._connect_device(device_id, link, claimed=claimed.get(device_id))
            except ApiError as exc:
                if exc.code not in ("connection_failed", "not_connected", "busy"):
                    raise
                # Recorded in the device's state and the log; carry on (Qt did).
        with self._lock:
            cancelled = self._release_epoch != epoch
            devices = self._devices_payload()
        if not cancelled and claimed:
            self.set_activity(
                _connect_all_outcome(devices), source="server", topic="connection", log=False
            )
        return devices

    def _fail_unreachable(self, claimed: dict[str, int], link: Link, text: str) -> None:
        """Fail the devices a Connect all claimed with the address's reason, unopened."""
        failed: list[str] = []
        settled: list[threading.Event] = []
        with self._lock:
            for device_id in CONNECT_ORDER:
                slot = self._slots[device_id]
                if device_id not in claimed or slot.generation != claimed[device_id]:
                    continue  # released (Cancel, Disconnect all) meanwhile
                if slot.settled is not None:
                    settled.append(slot.settled)
                    slot.settled = None
                slot.state, slot.link, slot.since = "error", link, utc_iso()
                slot.error = slot.info = text
                failed.append(LABELS[device_id].lower())
            if failed:
                self._publish_status()
        for event in settled:
            event.set()
        if failed:
            summary = f"{text} ({', '.join(failed)} not connected)"
            self.set_activity(summary, source="server", topic="connection", log=False)
            self.log("error", summary, source="server", topic="connection")

    def disconnect_all(self) -> dict[str, Any]:
        """``DELETE /api/devices`` (device_session.py:258-263).

        Also cancels a connect-all in progress: it connects no further device.
        """
        with self._lock:
            self._release_epoch += 1
        for device_id in DISCONNECT_ORDER:
            self._disconnect_device(device_id)
        self.set_activity("Disconnected", source="server", topic="connection", log=False)
        return self.devices()

    def connect(self, mode: str, host: str | None = None, port: int | None = None) -> dict:
        """v1 ``POST /api/connection``: mount then camera, both must succeed."""
        link = self.resolve_link(mode, host, port)
        with self._lock:
            pair = (self._slots["mount"], self._slots["camera"])
            if all(s.state == "connected" and s.link == link for s in pair):
                return self._connection().to_dict()  # idempotent
            self._check_link(link)
        opened: list[str] = []
        try:
            for device_id in ("mount", "camera"):
                if self._connect_device(device_id, link, quiet=True) == "connected":
                    opened.append(device_id)
        except ApiError as exc:
            if exc.code == "connection_failed":
                for device_id in opened:  # v1: both or neither
                    self._disconnect_device(device_id, quiet=True)
                self.log("error", f"Connection failed: {exc.message}", topic="connection")
            raise
        with self._lock:
            connection = self._connection()
        if opened:
            self.log(
                "info", f"Connected to {connection.device_name} ({link.where})", topic="connection"
            )
            self.set_activity(
                f"Connected to {connection.device_name}", topic="connection", log=False
            )
        return connection.to_dict()

    def disconnect(self) -> dict:
        """v1 ``DELETE /api/connection``: stop everything and release every device."""
        with self._lock:
            was = self._connection().state
        for device_id in DISCONNECT_ORDER:
            self._disconnect_device(device_id, quiet=True)
        if was == "connected":
            self.log("info", "Disconnected", topic="connection")
        self.set_activity("Disconnected", source="server", topic="connection", log=False)
        with self._lock:
            return self._connection().to_dict()

    @property
    def _camera(self) -> CameraDevice | None:
        return self._slots["camera"].handle

    @property
    def _mount(self) -> MountDevice | None:
        return self._slots["mount"].handle

    def _require(self, device_id: str) -> Any:
        slot = self._slots[device_id]
        if slot.state != "connected" or slot.handle is None:
            raise ApiError(409, "not_connected", f"No {LABELS[device_id].lower()} connected")
        return slot.handle

    # ------------------------------------------------------------------
    # Discovery (row A16)
    # ------------------------------------------------------------------

    def start_discovery(
        self,
        port: int | None = None,
        candidates: list[str] | None = None,
        broadcast_timeout_s: float | None = None,
    ) -> dict[str, Any]:
        cfg_host, cfg_port = self._alpaca_address()
        port = int(port or cfg_port)
        if candidates is None:
            # device_session.py:203-205: the last-used host, then the AP-mode address.
            candidates = [cfg_host, active.profile().ap_host]
        timeout = float(broadcast_timeout_s or 8.0)
        layers = self.discovery_layers

        def body(ctx: JobContext) -> dict[str, Any]:
            self.set_activity(
                "Searching for Alpaca devices…", source="discovery", topic="discovery", log=False
            )
            self.log("info", "Starting Alpaca discovery…", source="discovery", topic="discovery")
            try:
                result = run_discovery(
                    ctx,
                    port=port,
                    candidates=tuple(candidates),
                    broadcast_timeout_s=timeout,
                    layers=layers,
                )
            except JobCancelled:
                self.log("info", "Discovery cancelled.", source="discovery", topic="discovery")
                self.set_activity(
                    "Discovery cancelled", source="discovery", topic="discovery", log=False
                )
                raise
            except Exception as exc:
                self.log("error", f"Discovery: {exc}", source="discovery", topic="discovery")
                self.set_activity(
                    f"Discovery failed: {exc}", source="discovery", topic="discovery", log=False
                )
                raise
            found = len(result["devices"])
            self.set_activity(
                (
                    f"Discovery: {found} device{'s' if found != 1 else ''} found"
                    if found
                    else "Discovery: no Alpaca device found"
                ),
                source="discovery",
                topic="discovery",
                log=False,
            )
            if not result["devices"]:
                self.log(
                    "warning",
                    "No Alpaca devices found (broadcast, direct probes and subnet scan).",
                    source="discovery",
                    topic="discovery",
                )
            for device in result["devices"]:
                name = f" ({device['name']})" if device["name"] else ""
                self.log(
                    "ok",
                    f"Found {device['host']}:{device['port']}{name}",
                    source="discovery",
                    topic="discovery",
                )
            return result

        return self.jobs.start("discovery", body, total=3, stage="broadcast")

    # ------------------------------------------------------------------
    # Wave 2: files, sessions, support bundle, Settings helpers (A5-A6, A11, A67, A81-A84)
    # ------------------------------------------------------------------

    def _places_extra(self) -> list[tuple[str, str, Path | None]]:
        return [
            ("diagnostics", "Logs", self._settings.log_dir),
            ("config", "Configuration", self.config.directory),
        ]

    def _sessions_root(self) -> Path:
        return Path(str(self.config.get("sessions_path", "") or "~/Argos/sessions")).expanduser()

    def fs_list(
        self,
        path: str | None,
        kind: str = "any",
        ext: str | None = None,
        counts: str | None = None,
        hidden: bool = False,
    ) -> dict[str, Any]:
        """``GET /api/fs/list`` (row A11)."""
        return list_folder(
            self.fs_roots,
            path,
            default=self._sessions_root(),
            kind=kind,
            exts=parse_exts(ext),
            counts=counts,
            hidden=hidden,
            places=self.fs_roots.places(self._places_extra()),
        )

    def sessions_page(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        """``GET /api/sessions`` (row A67, list only)."""
        return self.sessions.page(self._sessions_root(), offset=offset, limit=limit)

    def crash_reports(self, since: str | None = None) -> dict[str, Any]:
        """``GET /api/diagnostics/crash-reports`` (row A6)."""
        directory = self._settings.log_dir
        reports = support.crash_reports(directory)
        if since:
            try:
                after = datetime.fromisoformat(since.strip().replace("Z", "+00:00"))
            except ValueError as exc:
                raise ApiError(400, "invalid_argument", f"since: not an ISO time: {since}") from exc
            if after.tzinfo is None:
                after = after.replace(tzinfo=timezone.utc)
            reports = [
                r for r in reports if datetime.fromisoformat(r["t"].replace("Z", "+00:00")) > after
            ]
        return {"directory": str(directory) if directory else None, "reports": reports}

    def astap_state(
        self, path: str | None = None, database_path: str | None = None, database: str | None = None
    ) -> dict[str, Any]:
        """``GET /api/astrometry/astap`` (row A81); each argument defaults to the config."""
        get = self.config.get
        return settings_helpers.astap_state(
            path if path is not None else str(get("astrometry.astap_path", "") or ""),
            (
                database_path
                if database_path is not None
                else str(get("astrometry.database_path", "") or "")
            ),
            database if database is not None else str(get("astrometry.database", "") or ""),
        )

    def caches(self) -> dict[str, Any]:
        """``GET /api/caches`` (row A83)."""
        return {"caches": settings_helpers.cache_records(self.config.get)}

    def clear_cache(self, kind: str) -> dict[str, Any]:
        """``DELETE /api/caches/{kind}`` (row A83): local only, nothing downloaded."""
        record, removed = settings_helpers.clear_cache(kind, self.config.get)
        noun = "file" if removed == 1 else "files"
        self.log("info", f"Cleared the {record['label']} ({removed} {noun}).", topic="config")
        return {"cache": record, "removed": removed}

    def start_site_search(self, query: str) -> dict[str, Any]:
        """``POST /api/site/search`` (row A82): a cancellable ``site_search`` job."""
        text = " ".join(str(query).split())
        if not text:
            raise ApiError(400, "invalid_argument", "Enter a city, country, or address first.")
        http_get = self.place_http_get

        def body(ctx: JobContext) -> dict[str, Any]:
            def progress(done: int, total: int, stage: str) -> None:
                ctx.progress(done, total=total, stage=stage)

            try:
                places = settings_helpers.search_places(
                    text, http_get=http_get, cancel=ctx.cancel_event, progress=progress
                )
            except settings_helpers.LookupFailed as exc:
                self.log("warning", f"Place search: {exc}", source="server", topic="config")
                raise ApiError(502, "lookup_failed", str(exc)) from exc
            except settings_helpers.PlaceNotFound as exc:
                raise ApiError(404, "not_found", str(exc)) from exc
            ctx.check()
            return {"query": text, "places": places}

        return self.jobs.start("site_search", body, total=None, stage="search")

    def _bundle_target(self, destination: str, overwrite: bool) -> Path:
        real, _root = self.fs_roots.resolve(destination, what="destination")
        # A folder is refused before any suffix is added: "<folder>" must not
        # silently become "<folder>.zip" next to it.
        if real.is_dir():
            raise ApiError(400, "invalid_argument", f"{real} is a folder: name the .zip file")
        if real.suffix.lower() != ".zip":
            # Appended, never swapped: "c.tar.gz" -> "c.tar.gz.zip", not "c.tar.zip"
            # (support_bundle.py:177-179 swapped it).
            real = real.with_name(real.name + ".zip")
        if not self.fs_roots.allows(real):
            raise ApiError(403, "forbidden_path", f"{real} is outside the allowed folders")
        if real.is_dir():
            raise ApiError(400, "invalid_argument", f"{real} is a folder: name the .zip file")
        if real.exists() and not overwrite:
            raise ApiError(
                409, "file_exists", f"{real.name} already exists: choose another name or replace it"
            )
        return real

    def start_support_bundle(
        self,
        destination: str | None = None,
        include_session: bool = False,
        session_dir: str | None = None,
        include_site: bool = False,
        include_crash_reports: bool = True,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """``POST /api/support-bundle`` (row A5): a ``support_bundle`` job (not cancellable)."""
        target = self._bundle_target(destination, overwrite) if destination else None
        session: Path | None = None
        if include_session:
            if not session_dir:
                raise ApiError(
                    400, "invalid_argument", "Choose the session whose metadata to include"
                )
            session, _root = self.fs_roots.resolve(session_dir, what="session folder")
            if not is_session(session):
                raise ApiError(
                    400, "session_invalid", f"{session} is not an ARGOS session (no session.json)"
                )
        get = self.config.get
        coordinates = support.site_coordinates(get)
        driver = self.site_check.record().get("driver_site")
        if driver:
            coordinates += [driver["latitude"], driver["longitude"], driver["elevation_m"]]
        redactor = support.Redactor(
            token=self._settings.token,
            home=Path.home(),
            include_site=include_site,
            coordinates=coordinates,
        )
        summary = {
            "hardware.profile": get("hardware.profile", ""),
            "ui.log_level": get("ui.log_level", "INFO"),
            "diagnostics.enabled": bool(get("diagnostics.enabled", False)),
            "astap_configured": bool(get("astrometry.astap_path", "")),  # shell.py:511-516
            "api": API_VERSION,
        }
        log_dir = self._settings.log_dir

        def body(ctx: JobContext) -> dict[str, Any]:
            name = target.name if target is not None else support.default_name()
            path = target if target is not None else self._download_path(ctx.id, name)
            try:
                result = support.create_bundle(
                    path,
                    redactor=redactor,
                    log_directory=log_dir,
                    session_directory=session,
                    include_crash_reports=include_crash_reports,
                    config_summary=summary,
                )
            except (support.BundleError, OSError) as exc:
                reason = str(exc)
                self.log("error", f"Support bundle failed: {reason}", topic="app")
                raise ApiError(500, "bundle_failed", f"Could not create the ZIP: {reason}") from exc
            if target is None:
                with self._downloads_lock:
                    self._downloads[ctx.id] = (result.path, name)
            count = len(result.files)
            self.log(
                "info",
                f"Support bundle created: {name} ({count} file{'s' if count != 1 else ''}). "
                "ARGOS did not upload it.",
                topic="app",
            )
            return {
                "path": str(result.path) if target is not None else None,
                "name": name,
                "bytes": result.bytes,
                "files": list(result.files),
                "download": target is None,
                "session_included": session is not None,
                "site_included": include_site,
            }

        self._prune_downloads()
        return self.jobs.start("support_bundle", body, cancellable=False, stage="writing")

    def _download_path(self, job_id: str, name: str) -> Path:
        with self._downloads_lock:
            if self._download_dir is None:
                self._download_dir = Path(tempfile.mkdtemp(prefix="argos-downloads-"))
            folder = self._download_dir / job_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder / name

    def _prune_downloads(self) -> None:
        """Delete the files of jobs that have expired (kept as long as the job, 10 min)."""
        with self._downloads_lock:
            ids = list(self._downloads)
        for job_id in ids:
            try:
                self.jobs.get(job_id)
            except ApiError:
                with self._downloads_lock:
                    entry = self._downloads.pop(job_id, None)
                if entry is not None:
                    shutil.rmtree(entry[0].parent, ignore_errors=True)

    def job_download(self, job_id: str) -> tuple[Path, str]:
        """``GET /api/jobs/{id}/download``: the file a finished job left for the browser."""
        self._prune_downloads()
        job = self.jobs.get(job_id)  # 404 for an unknown or expired job
        if job["state"] in ("queued", "running"):
            raise ApiError(409, "not_ready", "The job is still running")
        with self._downloads_lock:
            entry = self._downloads.get(job_id)
        if entry is None or not entry[0].is_file():
            raise ApiError(404, "not_found", "This job has no file to download")
        return entry

    # ------------------------------------------------------------------
    # Network (row A18)
    # ------------------------------------------------------------------

    def network_state(self) -> dict[str, Any]:
        return self.network.snapshot()

    def network_check(self, internet: bool = False) -> dict[str, Any]:
        state = self.network.check(internet=internet)
        if internet:
            word = "reachable" if state["internet"] else "not reachable"
            self.log("info", f"Internet {word}", source="network", topic="network")
        return state

    # ------------------------------------------------------------------
    # Stellarium bridge (row A19)
    # ------------------------------------------------------------------

    def _stellarium_state(self) -> dict[str, Any]:
        """The ``stellarium`` record (lock held or not: the bridge has its own)."""
        return {
            **self.stellarium.snapshot(),
            "last_goto": self._last_goto,
            # wave 3 (A20): the newest target-name suggestion
            "suggestions": self.observation.suggestions(),
        }

    def _publish_stellarium(self) -> None:
        with self._lock:
            self._publish("stellarium", self._stellarium_state())

    def stellarium_state(self) -> dict[str, Any]:
        with self._lock:
            return self._stellarium_state()

    def stellarium_start(self, host: str | None = None, port: int | None = None) -> dict[str, Any]:
        """``POST /api/stellarium``: port of ``start_stellarium`` (device_session.py:783-798).

        The host and port are the config's unless given; both are written to
        the config before the bridge starts, as the Qt app did (the port is
        now also saved by the Planetarium card on commit). A bind error is
        answered ``502 bind_failed`` and stays in the record until the next
        start (the Qt card never showed it, 02 H14).
        """
        host = (host or str(self.config.get("stellarium.host", "127.0.0.1")) or "").strip()
        port = int(port if port is not None else self.config.get("stellarium.port", 10001))
        changes: dict[str, Any] = {}
        if self.config.get("stellarium.host") != host:
            changes["stellarium.host"] = host
        if self.config.get("stellarium.port") != port:
            changes["stellarium.port"] = port
        if changes:
            self.config.set_internal(changes, source="api")
        self.log(
            "info",
            f"Stellarium server starting on {host}:{port}",
            source="stellarium",
            topic="planetarium",
        )
        with self._lock:
            self._last_goto = None  # a new bridge session: no GoTo yet
        error = self.stellarium.start(host, port)
        if error is not None:
            self.log("error", f"Stellarium: {error}", source="stellarium", topic="planetarium")
            raise ApiError(502, "bind_failed", f"Stellarium: {error}")
        self.log(
            "ok",
            f"Stellarium bridge listening on {host}:{port}",
            source="stellarium",
            topic="planetarium",
        )
        return self.stellarium_state()

    def stellarium_stop(self) -> dict[str, Any]:
        """``DELETE /api/stellarium``: port of ``stop_stellarium`` (device_session.py:800-806)."""
        if self.stellarium.stop():
            self.log("info", "Stellarium bridge stopped", source="stellarium", topic="planetarium")
        return self.stellarium_state()

    def _on_stellarium_goto(self, ra_hours: float, dec_deg: float) -> None:
        """A GoTo from Stellarium (bridge loop thread): slew, off the loop.

        Port of ``shell.py:346-353`` → ``ImagingPage.goto_target``: the mount
        slews to the J2000 coordinates Stellarium sent. The target-name
        suggestion (``target_suggestions``) comes with the Observe wave.
        """
        threading.Thread(
            target=self._stellarium_goto,
            args=(ra_hours % 24.0, dec_deg),
            name="argos-stellarium-goto",
            daemon=True,
        ).start()

    def _stellarium_goto(self, ra_hours: float, dec_deg: float) -> None:
        where = f"RA {ra_hours:.4f} h, Dec {dec_deg:+.4f}°"
        self.log("info", f"Stellarium GoTo → {where}", source="stellarium", topic="planetarium")
        try:
            self.mount_goto(ra_hours, dec_deg)
            outcome, level = "slewing", "ok"
        except ApiError as exc:
            outcome = {
                "not_connected": "mount not connected",
                "parked": "mount parked",
            }.get(exc.code, exc.message)
            level = "warning"
        except Exception as exc:  # never kill the bridge's callback thread
            outcome, level = str(exc) or exc.__class__.__name__, "error"
        with self._lock:
            self._last_goto = {
                "ra_hours": ra_hours,
                "dec_deg": dec_deg,
                "t": utc_iso(),
                "outcome": outcome,
            }
            self._publish("stellarium", self._stellarium_state())
        if level != "ok":
            self.log(
                level,  # type: ignore[arg-type]
                f"Stellarium GoTo not sent: {outcome}",
                source="stellarium",
                topic="planetarium",
            )
        # A20: offer names near the GoTo coordinates (never sets one).
        self.observation.suggest_after_goto(ra_hours, dec_deg)

    # ------------------------------------------------------------------
    # Camera (v1 routes, wave 3 rows A21-A27)
    # ------------------------------------------------------------------

    def _refresh_camera(self, **changes: Any) -> CameraState:
        """Lock held: the camera record with its derived v1 fields, published on change.

        ``exposure_s`` / ``gain`` keep their v1 meaning: the frame being
        exposed while one is, else the settings.
        """
        settings = self._capture_settings
        current = changes.get("current", self._camera_state.current)
        source = current if current is not None else settings.to_dict()
        return self._set_camera(
            settings=settings.to_dict(),
            exposure_s=float(source["exposure_s"]),
            gain=int(source["gain"]),
            **changes,
        )

    def camera_owner(self) -> str:
        return self._camera_state.owner

    def _refuse_if_owned(self) -> None:
        """Lock held: 409 busy while autofocus or a sequence owns the camera."""
        owner = self._camera_state.owner
        if owner == "autofocus":
            raise ApiError(
                409, "busy", "Autofocus owns the camera — stop it first.", details={"owner": owner}
            )
        if owner == "sequence":
            raise ApiError(409, "busy", "A sequence owns the camera.", details={"owner": owner})

    def _validated_settings(self, changes: dict[str, Any]) -> CaptureSettings:
        """Lock held: the settings with *changes*, every field checked, never clamped (§3.4)."""
        settings = self._capture_settings
        limits = self._camera_limits
        if "exposure_s" in changes:
            exposure = float(changes["exposure_s"])
            low, high = (
                (limits.exposure_min_s, limits.exposure_max_s)
                if limits is not None
                else (0.0, FALLBACK_EXPOSURE_MAX_S)
            )
            if not (exposure > 0 and low <= exposure <= high):
                raise ApiError(
                    400,
                    "invalid_argument",
                    f"Exposure {exposure:g} s is outside {low:g}–{high:g} s"
                    + (" (the camera's range)." if limits is not None else "."),
                )
            settings = dataclasses.replace(settings, exposure_s=exposure)
        if "gain" in changes:
            gain = int(changes["gain"])
            low, high = (
                (limits.gain_min, limits.gain_max) if limits is not None else (0, FALLBACK_GAIN_MAX)
            )
            if not low <= gain <= high:
                raise ApiError(
                    400,
                    "invalid_argument",
                    f"Gain {gain} is outside {low}–{high}"
                    + (" (the camera's range)." if limits is not None else "."),
                )
            settings = dataclasses.replace(settings, gain=gain)
        if "frame_type" in changes:
            frame_type = str(changes["frame_type"])
            if frame_type not in FRAME_TYPES:
                raise ApiError(400, "invalid_argument", f"Unknown frame type {frame_type!r}")
            settings = dataclasses.replace(settings, frame_type=frame_type)
        if "filter" in changes:
            name = " ".join(str(changes["filter"]).split())
            if not name or len(name) > 32:
                raise ApiError(400, "invalid_argument", "A filter name has 1 to 32 characters")
            if self.wheel.connected:
                slot = self.wheel.canonical(name)
                if slot is None:
                    slots = ", ".join(self.wheel.record()["slots"]) or "none"
                    raise ApiError(
                        400, "invalid_argument", f"No wheel slot named '{name}' (slots: {slots})"
                    )
                name = slot
            settings = dataclasses.replace(settings, filter=name)
        if "offset" in changes:
            if self._slots["camera"].state != "connected":
                raise ApiError(409, "not_connected", "No camera connected")
            if limits is None or limits.offset_range is None:
                raise ApiError(400, "invalid_argument", "This camera has no offset setting")
            offset = int(changes["offset"])
            low, high = limits.offset_range
            if not low <= offset <= high:
                raise ApiError(400, "invalid_argument", f"Offset {offset} is outside {low}–{high}.")
            settings = dataclasses.replace(settings, offset=offset)
        if "binning" in changes:
            if self._slots["camera"].state != "connected":
                raise ApiError(409, "not_connected", "No camera connected")
            binning = int(changes["binning"])
            top = limits.max_bin if limits is not None else 1
            if not 1 <= binning <= top:
                raise ApiError(
                    400,
                    "invalid_argument",
                    f"Binning {binning} is outside 1–{top}"
                    + (" (this camera does not bin)." if top == 1 else "."),
                )
            settings = dataclasses.replace(settings, binning=binning)
        return settings

    def camera_settings(self) -> dict[str, Any]:
        with self._lock:
            return self._capture_settings.to_dict()

    def set_camera_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        """``PUT /api/camera/settings`` (A22): one commit, applied from the next frame."""
        with self._lock:
            self._refuse_if_owned()
            new = self._validated_settings(changes)
            old = self._capture_settings
            camera = self._slots["camera"].handle
            offset_change = "offset" in changes and new.offset != old.offset
            binning_change = "binning" in changes and new.binning != old.binning
            move_to = None
            if "filter" in changes and self.wheel.connected:
                if new.filter != self.wheel.slot or self.wheel.moving:
                    move_to = new.filter
            # Every refusal before any device call: the PUT is one commit (A22).
            if move_to is not None and self.wheel.moving:
                raise ApiError(
                    409,
                    "busy",
                    f"The filter wheel is moving to '{self.wheel.target}' — wait for it.",
                    details={"owner": "filterwheel"},
                )
            if (offset_change or binning_change) and (
                self._save is not None or self._saves_in_flight
            ):
                what = "offset" if offset_change else "binning"
                raise ApiError(
                    409,
                    "busy",
                    f"A Take shot is waiting for its frame or being saved — change the {what} "
                    "after it (FITS OFFSET and binning describe the frame).",
                    details={"owner": self._camera_state.owner},
                )
            if offset_change or binning_change:
                self._readout_changing += 1
        # Offset and binning go to the driver at once (off the event loop) and are read back.
        try:
            if offset_change:
                try:
                    camera.set_offset(int(new.offset))
                    read = camera.get_offset() if hasattr(camera, "get_offset") else new.offset
                except Exception as exc:
                    self.log("error", f"Offset: {exc}", source="camera", topic="camera")
                    raise ApiError(502, "device_error", f"Offset: {exc}") from exc
                new = dataclasses.replace(new, offset=read)
                self.log("cmd", f"Offset → {read}", source="camera", topic="camera")
            if binning_change:
                try:
                    camera.set_binning(int(new.binning))
                except Exception as exc:
                    self.log("error", f"Binning: {exc}", source="camera", topic="camera")
                    raise ApiError(502, "device_error", f"Binning: {exc}") from exc
                self.log(
                    "cmd",
                    f"Binning → {new.binning}×{new.binning}",
                    source="camera",
                    topic="camera",
                )
        finally:
            if offset_change or binning_change:
                with self._lock:
                    self._readout_changing -= 1
                    self._readout_changed_at = datetime.now(timezone.utc)
        if move_to is not None:
            self.wheel.select(move_to)  # 409 while it moves; settings follow the wheel
        elif "filter" in changes and not self.wheel.connected and new.filter != old.filter:
            self.log(
                "info",
                f"No filter wheel: '{new.filter}' is written to FITS FILTER only.",
                source="camera",
                topic="camera",
            )
        with self._lock:
            self._refuse_if_owned()
            self._capture_settings = new
            state = self._refresh_camera()
        return state.to_dict()

    def _on_wheel_settled(self, slot: str | None) -> None:
        """Every wheel move ended: the settings follow the slot it reports (S3)."""
        with self._lock:
            changes: dict[str, Any] = {}
            if slot and slot != self._capture_settings.filter:
                self._capture_settings = dataclasses.replace(self._capture_settings, filter=slot)
            if self._camera_state.waiting_for and not self.wheel.moving:
                changes["waiting_for"] = None
            self._refresh_camera(**changes)

    def capture(
        self,
        exposure_s: float | None = None,
        gain: int | None = None,
        frame_type: str | None = None,
        save: bool = False,
    ) -> dict:
        """``POST /api/camera/capture``: one frame, or a Take shot with ``save``."""
        changes = _given(exposure_s=exposure_s, gain=gain, frame_type=frame_type)
        with self._lock:
            self._require("camera")
            self._refuse_if_owned()
            settings = self._validated_settings(changes)
            if save and settings.binning != 1:
                # fits_writer.py writes XBINNING = YBINNING = 1 and unbinned pixel
                # sizes: a binned frame would be saved with false metadata.
                raise ApiError(
                    409,
                    "unsupported",
                    "Take shot saves unbinned frames only (FITS XBINNING and pixel size "
                    "assume 1×1): set Binning to 1.",
                )
            live = self._camera_state.owner == "live"
            if live and not save:
                raise ApiError(409, "busy", "Camera is busy (live) — stop it first")
            if live and self._save is not None:
                raise ApiError(409, "busy", "A Take shot is already waiting for its frame")
            if not live and (self._camera_state.state in CAMERA_BUSY or self._job is not None):
                if self._job is not None and self._camera_state.state not in CAMERA_BUSY:
                    raise ApiError(409, "busy", "Camera is still stopping — try again in a moment")
                raise ApiError(
                    409, "busy", f"Camera is busy ({self._camera_state.state}) — stop it first"
                )
            # Published with the state change below (one camera event, as in v1).
            self._capture_settings = settings
        if not save:
            return self._start_job(live=False)
        self._refuse_light_through_dark(settings.frame_type)
        waiting = self._prepare_dark(settings.frame_type)
        with self._lock:
            self._require("camera")
            self._refuse_if_owned()
            request = SaveRequest(
                settings.frame_type,
                live=live,
                accepted_utc=utc_iso(),
                exposure_s=settings.exposure_s,
                gain=settings.gain,
            )
            if live:
                if self._camera_state.owner != "live" or self._save is not None:
                    raise ApiError(409, "busy", "Live view stopped meanwhile — take the shot again")
                self._save = request
                self._save_notes = set()
                state = self._refresh_camera(
                    save_pending=1, waiting_for="filterwheel" if waiting else None
                )
            else:
                state = None
        self.log("cmd", "Take shot — saving next frame…", source="camera", topic="camera")
        if live:
            return state.to_dict()
        return self._start_job(live=False, save=request, waiting=waiting)

    def _refuse_light_through_dark(self, frame_type: str) -> None:
        """A Light or Flat Take shot behind the opaque slot is refused (S1 counterpart).

        The web path turns the wheel to Dark by itself for a Dark/Bias shot
        (``_prepare_dark``) and nothing turns it back, so the usual "darks,
        then a light" would save a pure-pedestal frame as a Light Frame
        (science review of wave 3). Sequences refuse it already (S7).
        """
        if not is_light_frame(frame_type):
            return
        with self._lock:
            if not self.wheel.has_dark_slot:
                return
            moving, target, slot = self.wheel.moving, self.wheel.target, self.wheel.slot
        label = image_type(frame_type)
        if moving and is_dark_slot(target):
            raise ApiError(
                409,
                "dark_slot",
                f"The filter wheel is turning to '{target}', which blocks the light — "
                f"select a filter for the {label}.",
                details={"slot": target},
            )
        if not moving and is_dark_slot(slot):
            raise ApiError(
                409,
                "dark_slot",
                f"The filter wheel is on '{slot}', which blocks the light — select a filter "
                f"for the {label}.",
                details={"slot": slot},
            )

    def _prepare_dark(self, frame_type: str) -> bool:
        """A Dark/Bias Take shot needs the wheel settled on its Dark slot (S1).

        Port of ``_dark_shot_allowed`` (``acquisition_engine.py:437-470``)
        plus the move-then-expose chain 0.5.0 left to the web UI: the wheel
        is sent to Dark here. Returns True when the shot waits for that move.
        """
        if is_light_frame(frame_type):
            return False
        label = image_type(frame_type)
        with self._lock:
            has_dark = self.wheel.has_dark_slot
            moving = self.wheel.moving
            target = self.wheel.target
            slot = self.wheel.slot
        if not has_dark:
            self.log(
                "warning",
                f"{label}: no filter wheel to block the light — the frame is only dark if "
                "the telescope is covered.",
                source="camera",
                topic="camera",
            )
            return False
        if moving:
            if is_dark_slot(target):
                return True
            raise ApiError(
                409,
                "busy",
                f"The filter wheel is moving to '{target}' — wait for it, then take the {label}.",
                details={"owner": "filterwheel"},
            )
        if is_dark_slot(slot):
            return False
        dark = self.wheel.canonical("Dark") or "Dark"
        self.wheel.select(
            dark, reason=f"Filter → {dark} for the {label} (the Seestar has no shutter)."
        )
        with self._lock:
            settings = dataclasses.replace(self._capture_settings, filter=dark)
            self._capture_settings = settings
            self._refresh_camera()
        return True

    def live(
        self,
        exposure_s: float | None = None,
        gain: int | None = None,
        frame_type: str | None = None,
    ) -> dict:
        changes = _given(exposure_s=exposure_s, gain=gain, frame_type=frame_type)
        with self._lock:
            self._require("camera")
            self._refuse_if_owned()
            if self._camera_state.state in CAMERA_BUSY:
                raise ApiError(
                    409, "busy", f"Camera is busy ({self._camera_state.state}) — stop it first"
                )
            if self._job is not None:
                raise ApiError(409, "busy", "Camera is still stopping — try again in a moment")
            # Published with the state change of _start_job (one camera event).
            self._capture_settings = self._validated_settings(changes)
        return self._start_job(live=True)

    def _start_job(
        self, live: bool, save: SaveRequest | None = None, waiting: bool = False
    ) -> dict:
        with self._lock:
            camera = self._require("camera")
            self._refuse_if_owned()
            if self._camera_state.state in CAMERA_BUSY:
                raise ApiError(
                    409, "busy", f"Camera is busy ({self._camera_state.state}) — stop it first"
                )
            if self._job is not None:
                # A stopped job still finishing its download: one exposure at a time.
                raise ApiError(409, "busy", "Camera is still stopping — try again in a moment")
            settings = self._capture_settings
            cancel = threading.Event()
            # The first frame's snapshot (S2) goes with the state change, so a
            # single capture still announces exposing → downloading → idle.
            first = self._frame_settings("live" if live else "single")
            # A single shot that waits for a turning wheel takes its snapshot
            # once the wheel has settled: its filter is the new slot (review).
            snapshot_later = waiting or (not live and self.wheel.moving)
            job = threading.Thread(
                target=self._run_job,
                args=(camera, live, cancel, None if snapshot_later else first),
                name="argos-live" if live else "argos-capture",
                daemon=True,
            )
            self._job, self._job_cancel = job, cancel
            self._save = save
            self._save_notes = set()
            state = self._refresh_camera(
                state="live" if live else "exposing",
                owner="live" if live else "single",
                current=first.to_dict(),
                save_pending=1 if save is not None else 0,
                waiting_for="filterwheel" if waiting else None,
            )
            job.start()
        exposure_s, gain = settings.exposure_s, settings.gain
        what = "Live view" if live else "Capture"
        self.log("info", f"{what}: {exposure_s:g} s, gain {gain}", source="camera", topic="camera")
        self.set_activity(
            "Live preview" if live else f"Exposing {exposure_s:g} s…",
            source="camera",
            topic="camera",
            log=False,
        )
        return state.to_dict()

    def _frame_settings(self, origin: str) -> FrameSettings:
        """Lock held: the snapshot of the frame about to start (S2)."""
        s = self._capture_settings
        return FrameSettings(
            exposure_s=s.exposure_s,
            gain=s.gain,
            frame_type=s.frame_type,
            filter=s.filter,
            object_name=self.observation.object_name,
            light=is_light_frame(s.frame_type),
            origin=origin,  # type: ignore[arg-type]
        )

    def _save_decision(self, frame: FrameSettings, start: datetime | None) -> tuple[str, str, str]:
        """Lock held: is this frame the one the pending Take shot saves?

        Port of ``_on_frame`` (``acquisition_engine.py:600-631``): never a
        frame exposed while the wheel turned (S3 review); never a frame of
        another type (wave 3); never a dark whose wheel left the Dark slot
        (S1). Returns ``(decision, level, message)``.
        """
        request = self._save
        if request is None:
            return "none", "", ""
        if self.wheel.moved_since(start):
            return (
                "skip",
                "info",
                "Take shot: the filter wheel moved during this exposure — saving the next "
                "frame instead.",
            )
        changed = self._readout_changed_at
        if self._readout_changing or (changed is not None and (start is None or changed > start)):
            # FITS OFFSET is read from the camera at save time: a frame exposed
            # across an offset or binning change would record the new value.
            return (
                "skip",
                "info",
                "Take shot: the offset or binning changed during this exposure — saving the "
                "next frame instead.",
            )
        if self._capture_settings.binning != 1:
            return (
                "drop",
                "warning",
                f"Take shot not saved: binning is {self._capture_settings.binning}×"
                f"{self._capture_settings.binning} and FITS XBINNING assumes 1×1.",
            )
        if frame.frame_type != request.frame_type:
            return (
                "skip",
                "info",
                f"Take shot: this frame is a {image_type(frame.frame_type)}; saving the next "
                f"{image_type(request.frame_type)} instead.",
            )
        if not is_light_frame(frame.frame_type) and self.wheel.has_dark_slot:
            problem = self.wheel.not_on_dark()
            if problem:
                return (
                    "drop",
                    "warning",
                    f"{image_type(frame.frame_type)} shot not saved: {problem}",
                )
        return "save", "", ""

    def _wait_for_wheel(self, cancel: threading.Event) -> str | None:
        """Single Take shot: wait for a turning wheel; a Dark/Bias one then needs Dark.

        Returns why the shot cannot be taken, or ``None``.
        """
        with self._lock:
            request = self._save
            moving = self.wheel.moving
        if request is None:
            return None
        if moving:
            if not self.wheel.wait_settled(cancel):
                return None if cancel.is_set() else "the filter wheel did not settle"
        with self._lock:
            if self._camera_state.waiting_for:
                self._refresh_camera(waiting_for=None)
            if is_light_frame(request.frame_type) or not self.wheel.has_dark_slot:
                return None
            return self.wheel.not_on_dark()

    def _run_job(
        self,
        camera: CameraDevice,
        live: bool,
        cancel: threading.Event,
        first: FrameSettings | None = None,
    ) -> None:
        origin = "live" if live else "single"
        attempts = 0
        times: dict[str, datetime] = {}

        def on_start() -> None:
            times["start"] = datetime.now(timezone.utc)

        def on_readout() -> None:
            times["end"] = datetime.now(timezone.utc)
            if not live:
                with self._lock:
                    if self._job_cancel is cancel and not cancel.is_set():
                        self._set_camera(state="downloading")

        try:
            while not cancel.is_set():
                if not live:
                    # A single Take shot waits for a turning wheel before each
                    # exposure; a Dark/Bias one then needs it on Dark (S1).
                    problem = self._wait_for_wheel(cancel)
                    if cancel.is_set():
                        raise ExposureCancelled()
                    if problem:
                        with self._lock:
                            label = (
                                image_type(self._save.frame_type) if self._save else "Dark Frame"
                            )
                        self.log(
                            "warning",
                            f"{label} shot not taken: {problem}",
                            source="camera",
                            topic="camera",
                        )
                        self._end_single(cancel, None)
                        return
                with self._lock:
                    if self._job_cancel is not cancel:
                        break
                    frame = first if first is not None else self._frame_settings(origin)
                    first = None
                    changes = {"current": frame.to_dict()}
                    if not live:
                        changes["state"] = "exposing"
                    self._refresh_camera(**changes)
                times.clear()
                pixels = camera.expose(
                    frame.exposure_s,
                    frame.gain,
                    cancel,
                    on_readout,
                    light=frame.light,
                    on_start=on_start,
                )
                if cancel.is_set():
                    break
                start = times.get("start")
                end = times.get("end") or datetime.now(timezone.utc)
                if start is None:  # a device that does not report its start
                    start = end - timedelta(seconds=frame.exposure_s)
                frame = dataclasses.replace(frame, started_utc=utc_iso(start))
                with self._lock:
                    decision, level, message = self._save_decision(frame, start)
                    request_seen = self._save if decision == "save" else None
                    self._frame_seq += 1
                    seq = self._frame_seq
                    if decision == "save":
                        frame = dataclasses.replace(frame, save=True)
                    job = self._metrics_job(seq, pixels, frame, start, end)
                    save_job = (
                        self._save_job(pixels, start, end, frame, seq)
                        if decision == "save"
                        else None
                    )
                    bayer = self._camera_state.sensor.bayer if self._camera_state.sensor else None
                header = {
                    "bayer": bayer,
                    "origin": origin,
                    "frame_type": frame.frame_type,
                    "gain": frame.gain,
                    "filter": frame.filter,
                    "started_utc": frame.started_utc,
                    "save": frame.save,
                }
                encoded = encode_frame(
                    pixels,
                    seq=seq,
                    exposure_s=frame.exposure_s,
                    timestamp=utc_iso(end),
                    source=camera.source,
                    extra=header,
                )
                changes: dict[str, Any]
                with self._lock:
                    if cancel.is_set() or self._job_cancel is not cancel:
                        break  # stopped while encoding: drop the frame
                    self.bus.publish_frame(encoded)
                    if decision in ("save", "drop"):
                        self._save = None
                    if save_job is not None:
                        self._saves_in_flight += 1  # until _save_task has written it
                    notes = self._save_notes
                    log_note = decision in ("skip", "drop") and message not in notes
                    if log_note:
                        notes.add(message)
                    changes = {"last_frame_seq": seq}
                    if decision in ("save", "drop"):
                        changes.update(save_pending=0, waiting_for=None)
                    if live:
                        self._refresh_camera(**changes)
                self.metrics.submit(job)
                if log_note:
                    self.log(level, message, source="camera", topic="camera")  # type: ignore[arg-type]
                if save_job is not None:
                    if request_seen is not None and (
                        request_seen.exposure_s != frame.exposure_s
                        or request_seen.gain != frame.gain
                    ):
                        # S2 keeps the frame in progress (Qt parity): say so.
                        self.log(
                            "info",
                            f"Take shot: saving the frame in progress, exposed "
                            f"{frame.exposure_s:g} s at gain {frame.gain} (the shot asked "
                            f"{request_seen.exposure_s:g} s at gain {request_seen.gain}).",
                            source="camera",
                            topic="camera",
                        )
                    self._saver.submit(self._save_task, save_job)
                if live:
                    continue
                attempts += 1
                if decision == "skip" and attempts < _SINGLE_ATTEMPTS:
                    with self._lock:
                        self._refresh_camera(last_frame_seq=seq)
                    continue
                if decision == "skip":
                    self.log(
                        "warning",
                        f"Take shot not saved after {attempts} frames: {message}",
                        source="camera",
                        topic="camera",
                    )
                self._end_single(cancel, seq, frame.exposure_s)
                return
        except ExposureCancelled:
            pass
        except Exception as exc:
            with self._lock:
                current = self._job_cancel is cancel
                if current:
                    self._job = self._job_cancel = None
                    self._save = None
                    self._set_camera(
                        state="error", owner="idle", current=None, save_pending=0, waiting_for=None
                    )
            if current:
                self.log("error", f"Camera: {exc}", source="camera", topic="camera")
                self.set_activity(f"Camera: {exc}", source="camera", topic="camera", log=False)
            else:  # stopped or disconnected meanwhile: the failure is moot
                logger.info("Camera job ended after stop: %s", exc)
            return
        # Cancelled: back to idle unless stop/teardown already settled the state.
        with self._lock:
            if self._job_cancel is cancel:
                self._job = self._job_cancel = None
                self._save = None
                changes = {"current": None, "save_pending": 0, "waiting_for": None}
                if self._camera_state.owner in ("live", "single"):
                    changes["owner"] = "idle"
                if self._camera_state.state in CAMERA_BUSY:
                    changes["state"] = "idle"
                self._refresh_camera(**changes)

    def _end_single(
        self, cancel: threading.Event, seq: int | None, exposure_s: float = 0.0
    ) -> None:
        """A single capture is over: release the job *with* the idle transition."""
        with self._lock:
            if self._job_cancel is not cancel:
                return
            # Release the job with the idle transition, so a client reacting
            # to "idle" can start the next capture at once.
            self._job = self._job_cancel = None
            self._save = None
            changes: dict[str, Any] = {
                "state": "idle",
                "owner": "idle",
                "current": None,
                "save_pending": 0,
                "waiting_for": None,
            }
            if seq is not None:
                changes["last_frame_seq"] = seq
            self._refresh_camera(**changes)
            if seq is not None:
                self.set_activity(
                    f"Frame #{seq} received ({exposure_s:g} s)",
                    source="camera",
                    topic="camera",
                    log=False,
                )

    # -- per-frame context: metrics, conditions, save (lock held) -------------------

    def _pointing(self) -> Pointing | None:
        """X1: the newest reading of a connected mount, else None."""
        reading = self._last_reading
        if reading is None or self._slots["mount"].state != "connected":
            return None
        return Pointing(reading.ra_hours, reading.dec_deg, reading.alt_deg, reading.az_deg)

    def _star_radius(self) -> int:
        try:
            return max(2, int(self.config.get("imaging.star_radius_px", 5) or 5))
        except (TypeError, ValueError):
            return 5

    def _metrics_job(
        self,
        seq: int,
        pixels: Any,
        frame: FrameSettings,
        start: datetime,
        end: datetime,
    ) -> MetricsJob:
        mid = start + (end - start) / 2
        pointing = self._pointing()
        airmass_mount = (
            compute_airmass(pointing.alt_deg)
            if pointing is not None and pointing.alt_deg is not None
            else None
        )
        airmass_target = None
        target = self.observation.target
        site = observing_site(self.config)
        if target is not None and site is not None:
            airmass_target = airmass_at(
                julian_date(mid), target["ra_hours"] * 15.0, target["dec_deg"], site[0], site[1]
            )
        focuser = self.focuser.record()
        row = {
            "frame_seq": seq,
            "t": utc_iso(mid),
            "origin": frame.origin,
            "exposure_s": frame.exposure_s,
            "gain": frame.gain,
            "frame_type": frame.frame_type,
            "filter": frame.filter,
            "airmass_mount": airmass_mount,
            "airmass_target": airmass_target,
            "sensor_temp_c": self._camera_state.temperature_c,
            "focuser_temp_c": focuser["temperature_c"],
            "focuser_position": focuser["position"],
        }
        return MetricsJob(
            seq=seq, arr=pixels, origin=frame.origin, radius=self._star_radius(), row=row
        )

    def _save_job(
        self, pixels: Any, start: datetime, end: datetime, frame: FrameSettings, seq: int
    ) -> SaveJob:
        return SaveJob(
            arr=pixels,
            start=start,
            end=end,
            frame=frame,
            frame_seq=seq,
            sessions_path=self._sessions_root(),
            pointing=self._pointing(),
            target=self._goto_target,
            site=observing_site(self.config),
            observer=str(self.config.get("observer.name", "") or "").strip(),
            camera=self._slots["camera"].handle,
            wheel=self.wheel.handle if self.wheel.connected else None,
        )

    def _save_task(self, job: SaveJob) -> None:
        """The save thread: write the FITS, then ``frame_saved`` (A24)."""

        def log(level: str, message: str) -> None:
            self.log(level, message, source="camera", topic="camera")  # type: ignore[arg-type]

        try:
            result = save_frame(job, log)
        except Exception as exc:
            logger.exception("FITS save failed")
            self.log("error", f"FITS save failed: {exc}", source="camera", topic="camera")
            return
        finally:
            with self._lock:
                self._saves_in_flight = max(0, self._saves_in_flight - 1)
        frame = job.frame
        with self._lock:
            self._save_seq += 1
            record = {
                "type": "frame_saved",
                "seq": self._save_seq,
                "frame_seq": job.frame_seq,
                "path": str(result.path),
                "name": result.path.name,
                "source": "single",
                "object": frame.object_name.strip() or "Unknown",
                "filter": result.filter_name,
                "frame_type": frame.frame_type,
                "image_type": image_type(frame.frame_type),
                "exposure_s": frame.exposure_s,
                "gain": frame.gain,
                "date_obs": frame.started_utc,
                "t": utc_iso(),
                "record": result.record,
            }
            self._saves.append(record)
            self.bus.publish("frame_saved", None, dict(record))
        self.log("ok", f"Saved {result.path.name}", source="camera", topic="camera")

    def saved(self, after: int = 0, limit: int = 200) -> dict[str, Any]:
        """``GET /api/camera/saved`` (A24): the saves after *after*."""
        with self._lock:
            saves = [dict(r) for r in self._saves if r["seq"] > after][:limit]
            last = self._save_seq or None
        return {"saves": saves, "last_seq": last}

    def _on_metrics(self, job: MetricsJob, result: dict[str, Any]) -> None:
        """The metrics thread measured a frame: ``frame_metrics`` and a conditions row."""
        with self._lock:
            self._publish("frame_metrics", {"seq": job.seq, **result, "t": utc_iso()})
        if job.row is None:
            return
        row = self.conditions.append(
            {
                **job.row,
                "hfd_px": result["hfd_px"],
                "fwhm_px": result["fwhm_px"],
                "star_count": result["star_count"],
                "sky_adu": result["sky_adu"],
                "peak_adu": result["peak_adu"],
            }
        )
        self.bus.publish("conditions", None, row)

    def conditions_page(self, since_seq: int = 0, limit: int = 5000) -> dict[str, Any]:
        return self.conditions.page(since_seq=since_seq, limit=limit)

    def _start_camera_temperature(self, camera: Any, generation: int) -> None:
        """Lock held: read the sensor temperature every 10 s while connected (A21)."""
        reader = getattr(camera, "temperature", None)
        if reader is None:
            return
        stop = threading.Event()
        self._camera_temp_stop = stop

        def poll() -> None:
            while not stop.wait(_CAMERA_TEMPERATURE_S):
                try:
                    value = reader()
                except Exception:
                    value = None
                with self._lock:
                    if stop.is_set() or self._slots["camera"].generation != generation:
                        return
                    if value != self._camera_state.temperature_c:
                        self._set_camera(temperature_c=value)

        threading.Thread(target=poll, name="argos-camera-temp", daemon=True).start()

    def _stop_job(self, join_s: float) -> None:
        with self._lock:
            job, cancel, camera = self._job, self._job_cancel, self._camera
        if cancel is not None:
            cancel.set()
        if job is not None and camera is not None:
            try:
                camera.abort()
            except Exception as exc:
                logger.warning("Camera abort: %s", exc)
        if job is not None:
            job.join(join_s)

    def update_live(self, exposure_s: float, gain: int) -> dict:
        """Change the running live view's exposure and gain from its next frame on.

        The exposure in progress finishes with the old settings; the camera
        record (``exposure_s``, ``gain``) changes when the next one starts,
        so it always describes the frame being taken. Wave 3: an alias of
        ``PUT /api/camera/settings`` limited to these two fields.
        """
        with self._lock:
            self._require("camera")
            if self._camera_state.state != "live" or self._job is None:
                raise ApiError(409, "not_live", "Live view is not running")
            self._capture_settings = self._validated_settings(
                {"exposure_s": exposure_s, "gain": gain}
            )
            state = self._refresh_camera()
        self.log(
            "info",
            f"Live view: next frame {exposure_s:g} s, gain {gain}",
            source="camera",
            topic="camera",
        )
        return state.to_dict()

    def stop_camera(self) -> dict:
        """Stop a capture or live view; also clears a camera error."""
        with self._lock:
            self._require("camera")
            self._refuse_if_owned()
            running = self._job is not None
        self._stop_job(join_s=_STOP_JOIN_S)
        with self._lock:
            # Idle now even if an Alpaca download is still draining: the job
            # drops its frame, and _start_job refuses until it has exited.
            self._save = None
            changes: dict[str, Any] = {"current": None, "save_pending": 0, "waiting_for": None}
            if self._camera_state.owner in ("live", "single"):
                changes["owner"] = "idle"
            if self._camera_state.state != "idle":
                changes["state"] = "idle"
            state = self._refresh_camera(**changes)
        if running:
            self.log("info", "Camera stopped", source="camera", topic="camera")
            self.set_activity("Camera idle", source="camera", topic="camera", log=False)
        return state.to_dict()

    def open_fits(self, path: str) -> dict:
        """Open a raw FITS frame as the current frame (A27; works without a connection)."""
        p = Path(path)
        if not p.is_absolute():
            raise ApiError(400, "invalid_argument", "path must be absolute")
        if p.suffix.lower() not in FITS_SUFFIXES:
            raise ApiError(400, "invalid_argument", "only .fit, .fits and .fts files can be opened")
        try:
            exists = p.is_file()
        except OSError as exc:  # name too long, unreadable parent directory…
            raise ApiError(400, "invalid_argument", f"Cannot read {p}: {exc.strerror}") from exc
        if not exists:
            raise ApiError(404, "not_found", f"No such file: {p}")
        with self._lock:
            owner = self._camera_state.owner
            if owner in ("single", "autofocus", "sequence"):
                raise ApiError(
                    409,
                    "busy",
                    "Camera is busy — wait for it before opening a file",
                    details={"owner": owner},
                )
        try:
            opened = load_raw_fits_frame(p)
        except FitsReadError as exc:
            raise ApiError(400, "invalid_fits", f"{p.name}: {exc}") from exc
        with self._lock:
            live = self._camera_state.owner == "live"
        if live:
            # Q-O11: the opened frame must not be replaced by the next live frame.
            self._stop_job(join_s=_STOP_JOIN_S)
            with self._lock:
                self._save = None
                self._refresh_camera(
                    state="idle", owner="idle", current=None, save_pending=0, waiting_for=None
                )
            self.log(
                "info", f"Live view stopped to open {p.name}.", source="camera", topic="camera"
            )
        source: FrameSource = "file"
        with self._lock:
            if self._camera_state.state in CAMERA_BUSY or self._job is not None:
                raise ApiError(409, "busy", "Camera is busy — stop it before opening a file")
            self._frame_seq += 1
            seq = self._frame_seq
            bayer = opened.bayer or active.profile().bayer_pattern
        header = {
            "bayer": bayer,
            "origin": "file",
            "path": str(p),
            "file_name": p.name,
            "date_obs": opened.date_obs,
            "epoch_utc": opened.epoch_utc,
        }
        frame = encode_frame(
            opened.pixels,
            seq=seq,
            exposure_s=opened.exposure_s,
            timestamp=opened.timestamp,
            source=source,
            extra=header,
        )
        with self._lock:
            self.bus.publish_frame(frame)
            state = self._set_camera(last_frame_seq=seq)
        self.metrics.submit(
            MetricsJob(seq=seq, arr=opened.pixels, origin="file", radius=self._star_radius())
        )
        shape = "×".join(str(n) for n in (opened.pixels.shape[1], opened.pixels.shape[0]))
        self.log("info", f"Opened {p.name} ({shape})", source="camera", topic="camera")
        if opened.epoch_utc is None:
            self.log(
                "warning",
                f"{p.name} has no usable DATE-OBS time (or EXPTIME) — no photometry point can "
                "be dated, so none will be measured on it.",
                source="camera",
                topic="camera",
            )
        return state.to_dict()

    # ------------------------------------------------------------------
    # Autofocus (row A36)
    # ------------------------------------------------------------------

    def _autofocus_record(self) -> dict[str, Any]:
        run = self._autofocus
        return dict(run.record) if run is not None else dict(self._af_record)

    def autofocus_state(self) -> dict[str, Any]:
        with self._lock:
            return self._autofocus_record()

    def start_autofocus(
        self,
        exposure_s: float | None = None,
        gain: int | None = None,
        half_range: int | None = None,
        num_steps: int | None = None,
    ) -> dict[str, Any]:
        """``POST /api/autofocus/start`` (``acquisition_engine.py:923-961``)."""
        with self._lock:
            if self._slots["camera"].state != "connected" or self._camera is None:
                raise ApiError(409, "not_connected", "Autofocus needs the camera connected")
            focuser = self.focuser.handle
            if focuser is None:
                raise ApiError(409, "not_connected", "Autofocus needs the focuser connected")
            run = self._autofocus
            if run is not None:
                message = (
                    "Autofocus is stopping — the focuser is still returning to its start."
                    if run.returning or run.mode is not None
                    else "Autofocus is already running."
                )
                raise ApiError(409, "busy", message, details={"owner": "autofocus"})
            if self._camera_state.owner == "sequence":
                raise ApiError(
                    409, "busy", "A sequence owns the camera.", details={"owner": "sequence"}
                )
            if self.wheel.has_dark_slot:
                # A sweep behind the opaque slot only measures hot pixels and
                # ends "flat HFD curve" without naming the cause (review).
                if self.wheel.moving:
                    raise ApiError(
                        409,
                        "busy",
                        f"The filter wheel is moving to '{self.wheel.target}' — wait for it.",
                        details={"owner": "filterwheel"},
                    )
                if is_dark_slot(self.wheel.slot):
                    raise ApiError(
                        409,
                        "dark_slot",
                        f"The filter wheel is on '{self.wheel.slot}', which blocks the light — "
                        "select a filter before autofocus.",
                        details={"slot": self.wheel.slot},
                    )
            settings = self._capture_settings
            checks: dict[str, Any] = {
                "exposure_s": (
                    float(exposure_s)
                    if exposure_s is not None
                    else min(settings.exposure_s, MAX_DEFAULT_EXPOSURE_S)
                ),
                "gain": int(gain) if gain is not None else settings.gain,
            }
            checked = self._validated_settings(checks)  # 400 outside the camera's limits
            params = AutofocusParams(
                exposure_s=checked.exposure_s,
                gain=checked.gain,
                half_range=int(half_range) if half_range is not None else 2000,
                num_steps=int(num_steps) if num_steps is not None else 9,
            )
            preempt = self._camera_state.owner in ("live", "single")
        if preempt:
            self._stop_job(join_s=_STOP_JOIN_S)
            with self._lock:
                self._save = None
            self.log(
                "info",
                "Live view stopped: autofocus owns the camera.",
                source="camera",
                topic="camera",
            )
        with self._lock:
            camera = self._camera
            if camera is None or self.focuser.handle is not focuser:
                raise ApiError(409, "not_connected", "Autofocus needs camera and focuser connected")
            if self._job is not None or self._autofocus is not None:
                raise ApiError(409, "busy", "Camera is still stopping — try again in a moment")
            self._af_runs += 1
            run = AutofocusRun(
                self,
                camera,
                focuser,
                params,
                self._af_runs,
                settle_s=self._settings.autofocus_settle_s,
                poll_s=self._settings.autofocus_poll_s,
                publish_frame=self._publish_autofocus_frame,
                on_end=self._on_autofocus_end,
            )
            run.record = {
                **idle_record(run.run),
                "state": "running",
                "stage": "coarse",
                "params": params.to_dict(),
                "started_utc": utc_iso(),
            }
            self._autofocus = run
            self._publish("autofocus", dict(run.record))
            self._refresh_camera(
                state="exposing",
                owner="autofocus",
                current=None,
                save_pending=0,
                waiting_for=None,
            )
        self.focuser.lock("autofocus")
        run.thread.start()
        self.log(
            "cmd",
            f"Autofocus started… ({params.exposure_s:g} s, gain {params.gain}, "
            f"±{params.half_range} steps, {params.num_steps} positions)",
            source="autofocus",
            topic="focuser",
        )
        self.set_activity("Autofocus…", source="autofocus", topic="focuser", log=False)
        with self._lock:
            return dict(run.record)

    def stop_autofocus(self) -> dict[str, Any]:
        """``POST /api/autofocus/stop``: cancel and return to the start (S23)."""
        with self._lock:
            run = self._autofocus
        if run is None:
            return self.autofocus_state()
        if run.stop():
            run._update(state="stopping")
            self.log(
                "info",
                "Autofocus stopping — the focuser returns to its start; the camera is released "
                "when it is back.",
                source="autofocus",
                topic="focuser",
            )
        return self.autofocus_state()

    def _halt_autofocus(self) -> dict[str, Any] | None:
        """``POST /api/focuser/halt`` during autofocus: stop where it is (Q-O6)."""
        with self._lock:
            run = self._autofocus
        if run is None:
            return None
        if run.halt():
            run._update(state="stopping")
            self.log(
                "cmd",
                "Focuser halted — autofocus stops where it is.",
                source="focuser",
                topic="focuser",
            )
        else:
            self.log(
                "info",
                "Halt ignored: autofocus is returning the focuser to its start.",
                source="focuser",
                topic="focuser",
            )
        return self.autofocus_state()

    def _publish_autofocus_frame(
        self, pixels: Any, exposure_s: float, gain: int, timestamp: str, started: str
    ) -> int:
        with self._lock:
            self._frame_seq += 1
            seq = self._frame_seq
            camera = self._camera
            bayer = self._camera_state.sensor.bayer if self._camera_state.sensor else None
        encoded = encode_frame(
            pixels,
            seq=seq,
            exposure_s=exposure_s,
            timestamp=timestamp,
            source=getattr(camera, "source", "simulator"),
            extra={
                "bayer": bayer,
                "origin": "autofocus",
                "frame_type": "light",
                "gain": gain,
                "filter": self._capture_settings.filter,
                "started_utc": started or None,
                "save": False,
            },
        )
        with self._lock:
            self.bus.publish_frame(encoded)
            self._set_camera(last_frame_seq=seq)
        self.metrics.submit(
            MetricsJob(seq=seq, arr=pixels, origin="autofocus", radius=self._star_radius())
        )
        return seq

    def _on_autofocus_end(self, run: AutofocusRun) -> None:
        """The sweep thread ended: release the focuser and the camera, log the outcome."""
        with self._lock:
            if self._autofocus is run:
                self._autofocus = None
                self._af_record = dict(run.record)
            if self._camera_state.owner == "autofocus":
                changes: dict[str, Any] = {"owner": "idle"}
                if self._camera_state.state in CAMERA_BUSY:
                    changes["state"] = "idle"
                self._refresh_camera(**changes)
            self._publish_status()
        self.focuser.lock(None)
        self.focuser.wake()
        record = run.record
        message = record.get("message") or ""
        level = {"done": "ok", "rejected": "warning", "cancelled": "info", "failed": "error"}
        state = record.get("state")
        text = message if state != "failed" else f"Autofocus: {message}"
        self.log(level.get(state, "info"), text, source="autofocus", topic="focuser")  # type: ignore[arg-type]
        activity = {
            "done": f"Focused  pos={record.get('position')}",
            "rejected": "Autofocus rejected",
            "cancelled": "Autofocus stopped",
            "failed": "Autofocus failed",
        }.get(state, "Autofocus ended")
        self.set_activity(activity, source="autofocus", topic="focuser", log=False)

    # ------------------------------------------------------------------
    # Mount
    # ------------------------------------------------------------------

    def _mount_command(self, action: str, *args: Any, target: Any = ...) -> dict:
        with self._lock:
            mount = self._require("mount")
            generation = self._slots["mount"].generation
        try:
            getattr(mount, action)(*args)
        except MountParked as exc:
            # The refusal tells us the mount is parked: show it now rather
            # than at the next poll (2 s away on a Seestar).
            self._refresh_mount(mount, generation, action)
            raise ApiError(409, "parked", str(exc)) from exc
        except Exception as exc:
            with self._lock:
                current = generation == self._slots["mount"].generation
            if not current:
                raise ApiError(409, "not_connected", "Disconnected during the command") from exc
            self.log("error", f"Mount {action}: {exc}", source="mount", topic="mount")
            raise ApiError(502, "device_error", str(exc) or action) from exc
        state = self._refresh_mount(mount, generation, action, target)
        if state is None:
            raise ApiError(409, "not_connected", "Disconnected during the command")
        return state.to_dict()

    def _refresh_mount(
        self, mount: MountDevice, generation: int, action: str, target: Any = ...
    ) -> MountState | None:
        """Read the mount after a command and store it (with a new *target* if given).

        Returns ``None``, storing nothing, when the session the command was
        sent in has ended meanwhile.
        """
        try:
            reading: MountReading | None = mount.read()
        except Exception as exc:
            logger.warning("Mount read after %s failed: %s", action, exc)
            reading = None
        with self._lock:
            if generation != self._slots["mount"].generation:
                return None
            if reading is not None:
                self._last_reading = reading
            new = self._mount_from_reading(reading) if reading else self._mount_state
            if target is not ...:
                new = dataclasses.replace(new, target=target)
            return self._apply_mount(new, telemetry=False)

    def mount_goto(self, ra_hours: float, dec_deg: float) -> dict:
        ra = float(ra_hours) % 24.0
        with self._lock:
            self._require("mount")
            blocked = self._mount_state.goto_blocked
        if blocked is not None:
            # H4: refused before any call, with the connect message.
            raise ApiError(409, "clock_error", blocked["message"])
        self.jog.stop_all_before("GoTo")
        result = self._mount_command("goto", ra, float(dec_deg), target=Target(ra, float(dec_deg)))
        with self._lock:
            self._goto_target = (ra, float(dec_deg))
        self.log("info", f"GoTo RA {ra:.4f} h, Dec {dec_deg:+.4f}°", source="mount", topic="mount")
        with self._lock:
            # Under the lock that also announces "Slew finished": a slew that
            # already ended never leaves "Slewing" behind it.
            if self._mount_state.state == "slewing":
                self.set_activity("Slewing", source="mount", topic="mount", log=False)
        return result

    def mount_stop(self) -> dict:
        with self._lock:
            self._require("mount")
            self._slew_stop_requested = (
                self._mount_state.state == "slewing" and not self.jog.active()
            )
        self.jog.stop_all_before("Abort")
        return self._mount_command("stop")

    def mount_park(self) -> dict:
        with self._lock:
            self._require("mount")
        self.jog.stop_all_before("Park")
        result = self._mount_command("park", target=None)
        self.log("info", "Parking", source="mount", topic="mount")
        return result

    def mount_unpark(self) -> dict:
        return self._mount_command("unpark")

    def mount_tracking(self, enabled: bool) -> dict:
        return self._mount_command("set_tracking", bool(enabled))

    # -- wave 3: jog and tracking rate (A29-A31) ---------------------------------

    def mount_jog(
        self,
        axis: str,
        rate_deg_s: float,
        client: str | None = None,
        seq: int | None = None,
        renew: bool = False,
    ) -> dict:
        """``POST /api/mount/jog``: start or renew one axis (dead-man in ``jog.py``)."""
        return self.jog.jog(axis, rate_deg_s, client=client, seq=seq, renew=renew)

    def mount_jog_stop(
        self, axis: str | None = None, client: str | None = None, seq: int | None = None
    ) -> dict:
        """``POST /api/mount/jog/stop``: one axis, or both whatever the server believes."""
        return self.jog.stop(axis, client=client, seq=seq)

    def client_gone(self, client: str | None) -> None:
        """A ``/ws/events`` socket opened with ``?client=`` closed: stop its jog."""
        self.jog.client_gone(client, "the client's event socket closed")

    def client_message(self, client: str | None, message: Any) -> None:
        """A text message from a ``/ws/events`` client; only ``jog_stop`` is known."""
        if isinstance(message, dict) and message.get("type") == "jog_stop":
            self.jog.client_gone(client, "the client left the window")

    def mount_tracking_rate(self, rate: str) -> dict:
        """``POST /api/mount/tracking-rate`` (``telescope.py:610-634``), read back (H6)."""
        with self._lock:
            mount = self._require("mount")
            generation = self._slots["mount"].generation
            listed = self._mount_state.tracking_rates
        if listed and rate not in listed:
            raise ApiError(
                400,
                "invalid_argument",
                f"The mount does not offer the {rate} rate (it lists: {', '.join(listed)})",
            )
        setter = getattr(mount, "set_tracking_rate", None)
        if setter is None:
            raise ApiError(400, "invalid_argument", "This mount has no tracking-rate setting")
        try:
            setter(rate)
            reader = getattr(mount, "tracking_rate", None)
            read = reader() if reader is not None else rate
        except Exception as exc:
            self.log("error", f"Tracking rate: {exc}", source="mount", topic="mount")
            raise ApiError(502, "device_error", str(exc) or "tracking rate") from exc
        with self._lock:
            if generation != self._slots["mount"].generation:
                raise ApiError(409, "not_connected", "Disconnected during the command")
            self._set_mount_extras(tracking_rate=read)
            state = self._mount_state
        self.log("cmd", f"Tracking rate → {read or rate}", source="mount", topic="mount")
        return state.to_dict()

    # -- poller, lost connection and auto-retry ------------------------------------

    def _start_poller(self, mount: MountDevice, generation: int) -> None:
        """Lock held."""
        stop = threading.Event()
        poller = threading.Thread(
            target=self._poll_mount,
            args=(mount, stop, generation),
            name="argos-mount-poll",
            daemon=True,
        )
        self._poller, self._poller_stop = poller, stop
        poller.start()

    def _poll_mount(self, mount: MountDevice, stop: threading.Event, generation: int) -> None:
        interval = max(0.25, float(getattr(mount, "poll_interval_s", 0.25)))
        failures = 0
        while not stop.wait(interval):
            try:
                reading = mount.read()
            except Exception as exc:
                failures += 1
                with self._lock:
                    if stop.is_set():
                        return
                    first = not self._mount_failing
                    self._mount_failing = True
                    self._apply_mount(
                        dataclasses.replace(self._mount_state, state="error"), telemetry=True
                    )
                if first:
                    self.log("error", f"Mount not responding: {exc}", source="mount", topic="mount")
                if failures >= max(1, self._settings.mount_lost_after):
                    self._mount_lost(mount, generation)
                    return
                continue
            failures = 0
            with self._lock:
                if stop.is_set():
                    return  # disconnected while reading: do not resurrect state
                recovered = self._mount_failing
                self._mount_failing = False
                self._last_reading = reading
                self._apply_mount(self._mount_from_reading(reading), telemetry=True)
            self.site_check.on_reading(reading, generation)
            if recovered:
                self.log("info", "Mount responding again", source="mount", topic="mount")

    def _mount_lost(self, mount: MountDevice, generation: int) -> None:
        """Port of ``_on_mount_lost`` (device_session.py:557-567) + ``polling_worker.py:84-87``."""
        interval = self._settings.mount_retry_s
        with self._lock:
            slot = self._slots["mount"]
            if slot.generation != generation or slot.handle is not mount:
                return
            slot.generation += 1
            retry_generation = slot.generation
            slot.handle = None
            self._poller = self._poller_stop = None  # this thread, about to return
            self._last_reading = None  # X1: frames saved while retrying carry no pointing
            link = slot.link
            slot.state, slot.since = "error", utc_iso()
            slot.error = "Connection lost"
            slot.info = f"Connection lost · retrying every {interval:g} s"
            slot.retrying = True
            stop = threading.Event()
            slot.retry_stop = stop
            self._publish_status()
        _close_quietly(mount)
        self.jog.mount_gone()
        self.site_check.mount_disconnected(before=retry_generation)
        self.set_activity(
            f"Mount connection lost · retrying every {interval:g} s",
            source="mount",
            topic="connection",
            log=False,
        )
        self.log("error", "Mount connection lost.", source="mount", topic="connection")
        self.log(
            "info",
            f"Retrying the mount every {interval:g}s — disconnect to stop.",
            source="mount",
            topic="connection",
        )
        threading.Thread(
            target=self._retry_mount,
            args=(link, retry_generation, stop),
            name="argos-mount-retry",
            daemon=True,
        ).start()

    def _retry_mount(self, link: Link, generation: int, stop: threading.Event) -> None:
        """One reconnect attempt per interval (device_session.py:299-333)."""
        while not stop.wait(self._settings.mount_retry_s):
            with self._lock:
                if self._slots["mount"].generation != generation:
                    return
            try:
                handle = self._open_device("mount", link)
            except Exception as exc:
                logger.info("Mount reconnect attempt failed: %s", exc)
                continue  # the loop keeps trying
            report = self._connect_report(handle)
            try:
                reading: MountReading | None = handle.read()
            except Exception:
                reading = None
            extras = _mount_extras(handle)
            with self._lock:
                slot = self._slots["mount"]
                stale = slot.generation != generation or stop.is_set()
                if not stale:
                    slot.retry_stop = None
                    slot.handle = handle
                    slot.state, slot.since = "connected", utc_iso()
                    slot.retrying = False
                    slot.error = None
                    slot.name = slot.info = getattr(handle, "name", None)
                    slot.warnings = tuple(m for lvl, m in report if lvl in ("warning", "error"))
                    self._mount_failing = False
                    self._last_reading = reading
                    self._mount_state = MountState(jog=self.jog.record(), **extras)
                    if reading is not None:
                        self._mount_state = self._mount_from_reading(reading)
                    self._start_poller(handle, generation)
                    self._publish_status()
            if stale:
                _close_quietly(handle)
                return
            self.site_check.mount_connected(generation, _driver_site(handle))
            self.log("ok", f"Mount reconnected: {slot.name}", source="mount", topic="connection")
            self.set_activity("Mount reconnected", source="mount", topic="connection", log=False)
            self._log_report(report, "mount")
            return


def _connect_all_outcome(devices: dict[str, Any]) -> str:
    """Status-bar line once a Connect all has finished: what is ready, what failed."""
    ready = sum(1 for d in devices.values() if d["state"] in ("connected", "busy"))
    failed = [LABELS[k].lower() for k, d in devices.items() if d["state"] == "error"]
    total = len(devices)
    if ready == total:
        return "Equipment ready"
    text = f"{ready} of {total} devices ready"
    if failed:
        text += f" · {', '.join(failed)} failed"
    return text


def _driver_site(handle: Any) -> tuple[float, float, float | None] | None:
    """The mount driver's own site, read by the adapter at connect time (or ``None``)."""
    site = getattr(handle, "driver_site", None)
    if site is None:
        return None
    try:
        lat, lon = float(site[0]), float(site[1])
        elev = float(site[2]) if len(site) > 2 and site[2] is not None else None
    except (TypeError, ValueError, IndexError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon, elev


def _given(**values: Any) -> dict[str, Any]:
    """The keyword arguments that were given (not None)."""
    return {key: value for key, value in values.items() if value is not None}


def _limits_record(limits: CameraLimits | None) -> dict[str, Any] | None:
    if limits is None:
        return None
    return {
        "gain_min": limits.gain_min,
        "gain_max": limits.gain_max,
        "exposure_min_s": limits.exposure_min_s,
        "exposure_max_s": limits.exposure_max_s,
    }


def _camera_extras(handle: Any) -> dict[str, Any]:
    """Limits, offset and temperature of a new camera (connect thread, A21)."""
    extras: dict[str, Any] = {}
    reader = getattr(handle, "limits", None)
    if reader is not None:
        try:
            extras["limits"] = reader()
        except Exception as exc:
            logger.warning("Camera limits unavailable: %s", exc)
    offset = getattr(handle, "get_offset", None)
    if offset is not None:
        try:
            extras["offset"] = offset()
        except Exception:
            extras["offset"] = None
    temperature = getattr(handle, "temperature", None)
    if temperature is not None:
        try:
            extras["temperature_c"] = temperature()
        except Exception:
            extras["temperature_c"] = None
    return extras


def _mount_extras(handle: Any) -> dict[str, Any]:
    """Geometry, tracking rates and the clock guard of a new mount (A29, H4)."""
    alignment = getattr(handle, "alignment", None)
    rates: list[str] = []
    rate: str | None = None
    lister = getattr(handle, "tracking_rates", None)
    if lister is not None:
        try:
            rates = [str(r) for r in lister()]
        except Exception as exc:
            logger.info("Tracking rates unavailable: %s", exc)
    reader = getattr(handle, "tracking_rate", None)
    if reader is not None:
        try:
            rate = reader()
        except Exception as exc:
            logger.info("Tracking rate unavailable: %s", exc)
    blocked = None
    clock = getattr(handle, "clock_error_s", None)
    if isinstance(clock, (int, float)) and clock > _CLOCK_LIMIT_S:
        blocked = {
            "reason": "clock",
            "clock_error_s": float(clock),
            "message": (
                f"Mount clock is {clock / 3600.0:.1f} h off — correct the date/time in the "
                "Seestar app, then reconnect. GoTo, Sync and Center will be refused until then."
            ),
        }
    return {
        "alignment": alignment if alignment in ("altaz", "eq", "eq_gem") else None,
        "tracking_rates": tuple(rates),
        "tracking_rate": rate,
        "goto_blocked": blocked,
    }


def _close_quietly(device: Any) -> None:
    try:
        device.close()
    except Exception as exc:
        logger.warning("Closing %s: %s", type(device).__name__, exc)
