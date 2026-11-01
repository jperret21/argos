"""The hub: device ownership, state machine, worker threads and event emission.

The HTTP layer is thin: every route calls one :class:`Hub` method from
FastAPI's threadpool. The hub keeps the three contract records (connection,
camera, mount) and is the only writer of them.

Threads:

- the **request threads** (FastAPI's pool) run commands; a slow Alpaca call
  blocks only its own request;
- one **exposure job** thread at a time runs a single capture or a live loop;
- one **mount poller** thread reads the mount every ``poll_interval_s``
  (0.25 s for the simulator — the contract's 4 Hz ceiling) and publishes it.

Locking: ``_lock`` guards the records and is never held across device I/O or
a thread join. Every state change happens under it together with the
publication of its event and a fresh sequence number, so events leave in the
order the changes happened. ``_ops`` serialises connect/disconnect/shutdown.

A command that was already talking to a device when the observer
disconnected must not write its answer into the state afterwards: every
connect and teardown bumps ``_generation``, and a result read under an older
generation is discarded.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from collections import deque
from pathlib import Path
from typing import Any, Literal

from argos.server.devices.base import (
    CameraDevice,
    ExposureCancelled,
    MountDevice,
    MountParked,
    MountReading,
)
from argos.server.errors import ApiError
from argos.server.events import EventBus
from argos.server.fits_source import FITS_SUFFIXES, FitsReadError, load_fits_frame
from argos.server.frames import FrameSource, encode_frame
from argos.server.settings import SimOptions
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
#: Log lines kept for a page that connects mid-session.
LOG_HISTORY = 200

LogLevel = Literal["info", "warning", "error"]
_LOG_LEVELS = {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}


class Hub:
    """Owns the devices and the contract state; thread-safe."""

    def __init__(self, bus: EventBus | None = None, sim: SimOptions | None = None) -> None:
        self.bus = bus or EventBus()
        self._sim = sim or SimOptions()
        self._lock = threading.RLock()
        self._ops = threading.Lock()
        self._seq = 0  # event sequence (ordering of snapshots)
        self._frame_seq = 0  # frame sequence (contract "seq")

        self._connection = ConnectionState()
        self._camera_state = CameraState()
        self._mount_state = MountState()
        self._connect_request: tuple[str, str | None, int | None] | None = None

        self._camera: CameraDevice | None = None
        self._mount: MountDevice | None = None
        self._job: threading.Thread | None = None
        self._job_cancel: threading.Event | None = None
        self._poller: threading.Thread | None = None
        self._poller_stop: threading.Event | None = None
        self._mount_failing = False
        #: Bumped on every connect and teardown (see the module docstring).
        self._generation = 0
        #: Exposure and gain the running live view uses from its next frame on.
        self._live_settings: tuple[float, int] | None = None
        self._log_history: deque[dict[str, Any]] = deque(maxlen=LOG_HISTORY)
        self._log_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Snapshots and events
    # ------------------------------------------------------------------

    def _status_payload(self) -> dict[str, Any]:
        return {
            "connection": self._connection.to_dict(),
            "camera": self._camera_state.to_dict(),
            "mount": self._mount_state.to_dict(),
        }

    def status(self) -> dict[str, Any]:
        """``GET /api/status`` body."""
        with self._lock:
            return self._status_payload()

    def status_event(self) -> tuple[int, dict[str, Any]]:
        """The current ``status`` event with its sequence number (for a new client)."""
        with self._lock:
            return self._seq, {"type": "status", **self._status_payload()}

    def _publish(self, kind: str, payload: dict[str, Any]) -> None:
        """Publish a snapshot event (lock held, so the sequence follows the changes)."""
        self._seq += 1
        self.bus.publish(kind, self._seq, {"type": kind, **payload})

    def _publish_status(self) -> None:
        self._publish("status", self._status_payload())

    def _set_connection(self, **changes: Any) -> ConnectionState:
        with self._lock:
            new = dataclasses.replace(self._connection, **changes)
            if new != self._connection:
                self._connection = new
                self._publish_status()
            return new

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
            self._mount_state = new
            if changed:
                self._publish_status()
            if telemetry:
                self._publish("mount", {"mount": new.to_dict()})
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

    def log(self, level: LogLevel, message: str) -> None:
        """Log to Python logging and to every ``/ws/events`` client."""
        logger.log(_LOG_LEVELS.get(level, logging.INFO), message)
        self.publish_log(level, message)

    def publish_log(self, level: LogLevel, message: str) -> None:
        payload = {"type": "log", "level": level, "message": message, "t": utc_iso()}
        with self._log_lock:
            self._log_history.append(payload)
        self.bus.publish("log", None, payload)

    def log_history(self) -> list[dict[str, Any]]:
        """The last :data:`LOG_HISTORY` log events, oldest first."""
        with self._log_lock:
            return list(self._log_history)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, mode: str, host: str | None = None, port: int | None = None) -> dict:
        """Connect the simulator or a Seestar; returns the ConnectionState."""
        request = (mode, host, port)
        with self._ops:
            with self._lock:
                if self._connection.state == "connected":
                    if self._connect_request == request:
                        return self._connection.to_dict()  # idempotent
                    raise ApiError(
                        409, "busy", "Already connected — disconnect before connecting again"
                    )
            self._set_connection(state="connecting", mode=mode, device_name=None, message=None)
            try:
                camera, mount = self._open_devices(mode, host, port)
            except ApiError:
                self._set_connection(state="disconnected", mode=None)
                raise
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                self._set_connection(state="error", message=message)
                self.log("error", f"Connection failed: {message}")
                raise ApiError(502, "connection_failed", message) from exc

            reading: MountReading | None = None
            try:
                reading = mount.read()
            except Exception as exc:
                logger.warning("First mount read failed: %s", exc)

            with self._lock:
                self._generation += 1
                self._camera, self._mount = camera, mount
                self._connect_request = request
                self._mount_failing = False
                name = mount.name if mode == "alpaca" else "ARGOS Simulator (Seestar S50)"
                self._camera_state = dataclasses.replace(
                    self._camera_state, state="idle", sensor=camera.sensor()
                )
                # A fresh record: nothing (a target…) carries over from a previous session.
                self._mount_state = MountState()
                if reading is not None:
                    self._mount_state = self._mount_from_reading(reading)
                self._connection = ConnectionState(
                    state="connected", mode=mode, device_name=name, message=None
                )
                self._publish("camera", {"camera": self._camera_state.to_dict()})
                self._publish_status()
                self._start_poller(mount)
            where = "simulator" if mode == "simulator" else f"{host}:{port}"
            self.log("info", f"Connected to {name} ({where})")
            return self.status()["connection"]

    def _open_devices(
        self, mode: str, host: str | None, port: int | None
    ) -> tuple[CameraDevice, MountDevice]:
        if mode == "simulator":
            from argos.server.devices.sim_camera import SimCamera
            from argos.server.devices.sim_mount import SimMount

            sim = self._sim
            camera = SimCamera(sim.width, sim.height, seed=sim.seed, n_stars=sim.n_stars)
            mount = SimMount(slew_rate_deg_s=sim.slew_rate_deg_s, poll_interval_s=sim.mount_poll_s)
            return camera, mount
        if mode == "alpaca":
            from argos.server.devices.alpaca import AlpacaCamera, AlpacaMount

            # The mount first, like DeviceSession.connect_all: its connect
            # also syncs the clock, which every later GoTo depends on.
            mount = AlpacaMount(host, int(port))
            try:
                camera = AlpacaCamera(host, int(port))
            except Exception:
                _close_quietly(mount)
                raise
            return camera, mount
        raise ApiError(400, "invalid_argument", f"Unknown connection mode {mode!r}")

    def disconnect(self) -> dict:
        """Stop everything and release the devices; idempotent."""
        with self._ops:
            self._teardown()
            with self._lock:
                was = self._connection.state
            self._set_connection(state="disconnected", mode=None, device_name=None, message=None)
            if was == "connected":
                self.log("info", "Disconnected")
            return self.status()["connection"]

    def _teardown(self) -> None:
        """Stop the job and the poller, close the devices (``_ops`` held).

        The devices are detached first, under the lock: from then on
        ``_require_connected`` refuses new jobs and mount commands, and a
        command still in flight is discarded (generation check). Whatever job
        is running at that moment is cancelled, then orphaned if it hangs: it
        can no longer write.
        """
        with self._lock:
            self._generation += 1
            camera, mount = self._camera, self._mount
            self._camera = self._mount = None
            job, cancel = self._job, self._job_cancel
            self._job = self._job_cancel = None
            self._live_settings = None
            poller, stop = self._poller, self._poller_stop
            self._poller = self._poller_stop = None
            self._connect_request = None
        if cancel is not None:
            cancel.set()
        if job is not None and camera is not None:
            try:
                camera.abort()
            except Exception as exc:
                logger.warning("Camera abort: %s", exc)
        if job is not None:
            job.join(_SHUTDOWN_JOIN_S)
        if stop is not None:
            stop.set()
        if poller is not None:
            poller.join(_SHUTDOWN_JOIN_S)
        for device in (camera, mount):
            if device is not None:
                _close_quietly(device)
        with self._lock:
            self._camera_state = dataclasses.replace(self._camera_state, state="idle", sensor=None)
            self._mount_state = MountState()
            self._publish("camera", {"camera": self._camera_state.to_dict()})
            self._publish_status()

    def shutdown(self) -> None:
        """Release everything at server exit."""
        with self._ops:
            self._teardown()
            with self._lock:
                self._connection = ConnectionState()
                self._publish_status()
        self.log("info", "Server shutting down — devices released")

    def _require_connected(self) -> None:
        if self._connection.state != "connected" or self._camera is None:
            raise ApiError(409, "not_connected", "No device connected")

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def capture(self, exposure_s: float, gain: int) -> dict:
        return self._start_job(live=False, exposure_s=exposure_s, gain=gain)

    def live(self, exposure_s: float, gain: int) -> dict:
        return self._start_job(live=True, exposure_s=exposure_s, gain=gain)

    def _start_job(self, live: bool, exposure_s: float, gain: int) -> dict:
        with self._lock:
            self._require_connected()
            if self._camera_state.state in CAMERA_BUSY:
                raise ApiError(
                    409, "busy", f"Camera is busy ({self._camera_state.state}) — stop it first"
                )
            if self._job is not None:
                # A stopped job still finishing its download: one exposure at a time.
                raise ApiError(409, "busy", "Camera is still stopping — try again in a moment")
            camera = self._camera
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
        self.log("info", f"{what}: {exposure_s:g} s, gain {gain}")
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
                self.log("error", f"Camera: {exc}")
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
            self._require_connected()
            if self._camera_state.state != "live" or self._job is None:
                raise ApiError(409, "not_live", "Live view is not running")
            self._live_settings = (float(exposure_s), int(gain))
            state = self._camera_state
        self.log("info", f"Live view: next frame {exposure_s:g} s, gain {gain}")
        return state.to_dict()

    def stop_camera(self) -> dict:
        """Stop a capture or live view; also clears a camera error."""
        with self._lock:
            self._require_connected()
            running = self._job is not None
        self._stop_job(join_s=_STOP_JOIN_S)
        with self._lock:
            # Idle now even if an Alpaca download is still draining: the job
            # drops its frame, and _start_job refuses until it has exited.
            if self._camera_state.state != "idle":
                self._set_camera(state="idle")
            state = self._camera_state
        if running:
            self.log("info", "Camera stopped")
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
        self.log("info", f"Opened {p.name} ({shape})")
        return state.to_dict()

    # ------------------------------------------------------------------
    # Mount
    # ------------------------------------------------------------------

    def _mount_command(self, action: str, *args: Any, target: Any = ...) -> dict:
        with self._lock:
            self._require_connected()
            mount, generation = self._mount, self._generation
        try:
            getattr(mount, action)(*args)
        except MountParked as exc:
            # The refusal tells us the mount is parked: show it now rather
            # than at the next poll (2 s away on a Seestar).
            self._refresh_mount(mount, generation, action)
            raise ApiError(409, "parked", str(exc)) from exc
        except Exception as exc:
            with self._lock:
                current = generation == self._generation
            if not current:
                raise ApiError(409, "not_connected", "Disconnected during the command") from exc
            self.log("error", f"Mount {action}: {exc}")
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
            if generation != self._generation:
                return None
            new = self._mount_from_reading(reading) if reading else self._mount_state
            if target is not ...:
                new = dataclasses.replace(new, target=target)
            return self._apply_mount(new, telemetry=False)

    def mount_goto(self, ra_hours: float, dec_deg: float) -> dict:
        ra = float(ra_hours) % 24.0
        result = self._mount_command("goto", ra, float(dec_deg), target=Target(ra, float(dec_deg)))
        self.log("info", f"GoTo RA {ra:.4f} h, Dec {dec_deg:+.4f}°")
        return result

    def mount_stop(self) -> dict:
        return self._mount_command("stop")

    def mount_park(self) -> dict:
        result = self._mount_command("park", target=None)
        self.log("info", "Parking")
        return result

    def mount_unpark(self) -> dict:
        return self._mount_command("unpark")

    def mount_tracking(self, enabled: bool) -> dict:
        return self._mount_command("set_tracking", bool(enabled))

    # -- poller ------------------------------------------------------------

    def _start_poller(self, mount: MountDevice) -> None:
        stop = threading.Event()
        poller = threading.Thread(
            target=self._poll_mount, args=(mount, stop), name="argos-mount-poll", daemon=True
        )
        self._poller, self._poller_stop = poller, stop
        poller.start()

    def _poll_mount(self, mount: MountDevice, stop: threading.Event) -> None:
        interval = max(0.25, float(getattr(mount, "poll_interval_s", 0.25)))
        while not stop.wait(interval):
            try:
                reading = mount.read()
            except Exception as exc:
                with self._lock:
                    if stop.is_set():
                        return
                    first = not self._mount_failing
                    self._mount_failing = True
                    self._apply_mount(
                        dataclasses.replace(self._mount_state, state="error"), telemetry=True
                    )
                if first:
                    self.log("error", f"Mount not responding: {exc}")
                continue
            with self._lock:
                if stop.is_set():
                    return  # disconnected while reading: do not resurrect state
                recovered = self._mount_failing
                self._mount_failing = False
                self._apply_mount(self._mount_from_reading(reading), telemetry=True)
            if recovered:
                self.log("info", "Mount responding again")


def _close_quietly(device: Any) -> None:
    try:
        device.close()
    except Exception as exc:
        logger.warning("Closing %s: %s", type(device).__name__, exc)
