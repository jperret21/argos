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
first: ``_profile_guard`` → the config store's lock → ``_lock``; the hub
never waits for the store while holding ``_lock``.

A command or connect that was already talking to a device when the observer
disconnected it must not write its answer into the state afterwards: every
connect and teardown bumps that slot's ``generation``, and a result read
under an older generation is discarded.
"""

from __future__ import annotations

import dataclasses
import logging
import secrets
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from argos.core.hardware import active, catalog
from argos.server import profiles as profile_records
from argos.server import runtime
from argos.server.config_meta import DATA_PATH_KEYS
from argos.server.config_store import ConfigStore
from argos.server.devices.base import (
    CameraDevice,
    DeviceError,
    ExposureCancelled,
    MountDevice,
    MountParked,
    MountReading,
)
from argos.server.discovery import DEFAULT_LAYERS, DiscoveryLayers, run_discovery
from argos.server.errors import ApiError
from argos.server.events import EventBus
from argos.server.fits_source import FITS_SUFFIXES, FitsReadError, load_fits_frame
from argos.server.frames import FrameSource, encode_frame
from argos.server.jobs import JobCancelled, JobContext, JobManager
from argos.server.logbook import LOG_HISTORY, LogBook
from argos.server.network import NetworkMonitor
from argos.server.settings import Settings, SimOptions
from argos.server.stellarium import StellariumBridge
from argos.server.state import (
    CAMERA_BUSY,
    CameraState,
    ConnectionState,
    MountState,
    Target,
    utc_iso,
)

logger = logging.getLogger(__name__)

#: How long ``stop`` waits for an exposure job to wind down before answering.
_STOP_JOIN_S = 2.0
#: How long disconnect/shutdown wait for a worker thread.
_SHUTDOWN_JOIN_S = 5.0
#: How long a request waits for a connect already running for the same device.
_CONNECT_WAIT_S = 60.0

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
        for dev in DISCONNECT_ORDER:
            self._disconnect_device(dev, quiet=True)
        with self._lock:
            self._publish_status()
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
        with self._lock:
            target = self._mount_state.target
        return MountState(
            state=reading.state,
            ra_hours=reading.ra_hours,
            dec_deg=reading.dec_deg,
            alt_deg=reading.alt_deg,
            az_deg=reading.az_deg,
            tracking=reading.tracking,
            pier_side=reading.pier_side,
            target=target,
        )

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

                return SimCamera(sim.width, sim.height, seed=sim.seed, n_stars=sim.n_stars)
            if device_id == "mount":
                from argos.server.devices.sim_mount import SimMount

                return SimMount(
                    slew_rate_deg_s=sim.slew_rate_deg_s, poll_interval_s=sim.mount_poll_s
                )
            from argos.server.devices.sim_aux import SimFilterWheel, SimFocuser

            return SimFilterWheel() if device_id == "filterwheel" else SimFocuser()
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
        if device_id == "mount":
            try:
                reading = handle.read()
            except Exception as exc:
                logger.warning("First mount read failed: %s", exc)
        if not self._install(device_id, generation, handle, report, reading):
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
    ) -> bool:
        """Store a freshly connected handle unless the attempt was superseded."""
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
                self._camera_state = dataclasses.replace(
                    self._camera_state, state="idle", sensor=handle.sensor()
                )
                self._publish("camera", {"camera": self._camera_state.to_dict()})
            elif device_id == "mount":
                self._mount_failing = False
                # A fresh record: nothing (a target…) carries over from a previous session.
                self._mount_state = MountState()
                if reading is not None:
                    self._mount_state = self._mount_from_reading(reading)
                self._start_poller(handle, generation)
            self._publish_status()
        if settled is not None:
            settled.set()
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
                self._live_settings = None
            elif device_id == "mount":
                poller, stop = self._poller, self._poller_stop
                self._poller = self._poller_stop = None
            slot.reset()
            self._publish_status()
        if settled is not None:
            settled.set()
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
            if slot.generation == generation:  # no new connect started meanwhile
                if device_id == "camera":
                    self._set_camera(state="idle", sensor=None)
                elif device_id == "mount" and self._mount_state != MountState():
                    self._mount_state = MountState()
                    self._publish_status()
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
        return {**self.stellarium.snapshot(), "last_goto": self._last_goto}

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

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def capture(self, exposure_s: float, gain: int) -> dict:
        return self._start_job(live=False, exposure_s=exposure_s, gain=gain)

    def live(self, exposure_s: float, gain: int) -> dict:
        return self._start_job(live=True, exposure_s=exposure_s, gain=gain)

    def _start_job(self, live: bool, exposure_s: float, gain: int) -> dict:
        with self._lock:
            camera = self._require("camera")
            if self._camera_state.state in CAMERA_BUSY:
                raise ApiError(
                    409, "busy", f"Camera is busy ({self._camera_state.state}) — stop it first"
                )
            if self._job is not None:
                # A stopped job still finishing its download: one exposure at a time.
                raise ApiError(409, "busy", "Camera is still stopping — try again in a moment")
            self._live_settings = (float(exposure_s), int(gain)) if live else None
            cancel = threading.Event()
            job = threading.Thread(
                target=self._run_job,
                args=(camera, live, float(exposure_s), int(gain), cancel),
                name="argos-live" if live else "argos-capture",
                daemon=True,
            )
            self._job, self._job_cancel = job, cancel
            state = self._set_camera(
                state="live" if live else "exposing", exposure_s=float(exposure_s), gain=int(gain)
            )
            job.start()
        what = "Live view" if live else "Capture"
        self.log("info", f"{what}: {exposure_s:g} s, gain {gain}", source="camera", topic="camera")
        self.set_activity(
            "Live preview" if live else f"Exposing {exposure_s:g} s…",
            source="camera",
            topic="camera",
            log=False,
        )
        return state.to_dict()

    def _run_job(
        self,
        camera: CameraDevice,
        live: bool,
        exposure_s: float,
        gain: int,
        cancel: threading.Event,
    ) -> None:
        # Frames are stamped when the shutter closes, not after the download.
        readout_at: list[str] = []

        def on_readout() -> None:
            readout_at.append(utc_iso())
            if not live:
                with self._lock:
                    if self._job_cancel is cancel and not cancel.is_set():
                        self._set_camera(state="downloading")

        try:
            while not cancel.is_set():
                if live:
                    # Settings changed with PATCH /api/camera/live apply from
                    # this exposure on, announced as it starts.
                    with self._lock:
                        if self._job_cancel is not cancel:
                            break
                        wanted = self._live_settings
                        if wanted is not None and wanted != (exposure_s, gain):
                            exposure_s, gain = wanted
                            self._set_camera(exposure_s=exposure_s, gain=gain)
                readout_at.clear()
                pixels = camera.expose(exposure_s, gain, cancel, on_readout)
                if cancel.is_set():
                    break
                with self._lock:
                    self._frame_seq += 1
                    seq = self._frame_seq
                frame = encode_frame(
                    pixels,
                    seq=seq,
                    exposure_s=exposure_s,
                    timestamp=readout_at[0] if readout_at else utc_iso(),
                    source=camera.source,
                )
                with self._lock:
                    if cancel.is_set() or self._job_cancel is not cancel:
                        break  # stopped while encoding: drop the frame
                    self.bus.publish_frame(frame)
                    if live:
                        self._set_camera(last_frame_seq=seq)
                        continue
                    # Release the job *with* the idle transition, so a client
                    # reacting to "idle" can start the next capture at once.
                    self._job = self._job_cancel = None
                    self._set_camera(state="idle", last_frame_seq=seq)
                    self.set_activity(
                        f"Frame #{seq} received ({exposure_s:g} s)",
                        source="camera",
                        topic="camera",
                        log=False,
                    )
                    return
        except ExposureCancelled:
            pass
        except Exception as exc:
            with self._lock:
                current = self._job_cancel is cancel
                if current:
                    self._job = self._job_cancel = None
                    self._set_camera(state="error")
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
                if self._camera_state.state in CAMERA_BUSY:
                    self._set_camera(state="idle")

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
        so it always describes the frame being taken.
        """
        with self._lock:
            self._require("camera")
            if self._camera_state.state != "live" or self._job is None:
                raise ApiError(409, "not_live", "Live view is not running")
            self._live_settings = (float(exposure_s), int(gain))
            state = self._camera_state
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
            running = self._job is not None
        self._stop_job(join_s=_STOP_JOIN_S)
        with self._lock:
            # Idle now even if an Alpaca download is still draining: the job
            # drops its frame, and _start_job refuses until it has exited.
            if self._camera_state.state != "idle":
                self._set_camera(state="idle")
            state = self._camera_state
        if running:
            self.log("info", "Camera stopped", source="camera", topic="camera")
            self.set_activity("Camera idle", source="camera", topic="camera", log=False)
        return state.to_dict()

    def open_fits(self, path: str) -> dict:
        """Publish a FITS file as the current frame (works without a connection)."""
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
            if self._camera_state.state in CAMERA_BUSY:
                raise ApiError(409, "busy", "Camera is busy — stop it before opening a file")
        try:
            pixels, exposure_s, timestamp = load_fits_frame(p)
        except FitsReadError as exc:
            raise ApiError(400, "invalid_fits", f"{p.name}: {exc}") from exc
        source: FrameSource = "file"
        with self._lock:
            if self._camera_state.state in CAMERA_BUSY:  # a capture started meanwhile
                raise ApiError(409, "busy", "Camera is busy — stop it before opening a file")
            self._frame_seq += 1
            seq = self._frame_seq
        frame = encode_frame(
            pixels, seq=seq, exposure_s=exposure_s, timestamp=timestamp, source=source
        )
        with self._lock:
            self.bus.publish_frame(frame)
            state = self._set_camera(last_frame_seq=seq)
        shape = "×".join(str(n) for n in (pixels.shape[1], pixels.shape[0]))
        self.log("info", f"Opened {p.name} ({shape})", source="camera", topic="camera")
        return state.to_dict()

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
            new = self._mount_from_reading(reading) if reading else self._mount_state
            if target is not ...:
                new = dataclasses.replace(new, target=target)
            return self._apply_mount(new, telemetry=False)

    def mount_goto(self, ra_hours: float, dec_deg: float) -> dict:
        ra = float(ra_hours) % 24.0
        result = self._mount_command("goto", ra, float(dec_deg), target=Target(ra, float(dec_deg)))
        self.log("info", f"GoTo RA {ra:.4f} h, Dec {dec_deg:+.4f}°", source="mount", topic="mount")
        with self._lock:
            # Under the lock that also announces "Slew finished": a slew that
            # already ended never leaves "Slewing" behind it.
            if self._mount_state.state == "slewing":
                self.set_activity("Slewing", source="mount", topic="mount", log=False)
        return result

    def mount_stop(self) -> dict:
        with self._lock:
            self._slew_stop_requested = self._mount_state.state == "slewing"
        return self._mount_command("stop")

    def mount_park(self) -> dict:
        result = self._mount_command("park", target=None)
        self.log("info", "Parking", source="mount", topic="mount")
        return result

    def mount_unpark(self) -> dict:
        return self._mount_command("unpark")

    def mount_tracking(self, enabled: bool) -> dict:
        return self._mount_command("set_tracking", bool(enabled))

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
                self._apply_mount(self._mount_from_reading(reading), telemetry=True)
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
            link = slot.link
            slot.state, slot.since = "error", utc_iso()
            slot.error = "Connection lost"
            slot.info = f"Connection lost · retrying every {interval:g} s"
            slot.retrying = True
            stop = threading.Event()
            slot.retry_stop = stop
            self._publish_status()
        _close_quietly(mount)
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
                    self._mount_state = MountState()
                    if reading is not None:
                        self._mount_state = self._mount_from_reading(reading)
                    self._start_poller(handle, generation)
                    self._publish_status()
            if stale:
                _close_quietly(handle)
                return
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


def _close_quietly(device: Any) -> None:
    try:
        device.close()
    except Exception as exc:
        logger.warning("Closing %s: %s", type(device).__name__, exc)
