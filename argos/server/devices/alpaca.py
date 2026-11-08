"""Real Seestar over ASCOM Alpaca — thin adapters over ``argos.core.alpaca``.

``argos.core.alpaca.camera.Camera`` and ``argos.core.alpaca.telescope.Telescope``
are already Qt-free and synchronous (the Qt app calls them from QThreads);
this module only maps them onto the server's device protocols. Every
scientific decision stays in the core: the J2000 ↔ topocentric-of-date
conversion and the clock-sync guard of ``Telescope``, the ImageBytes download
and its row-major ``(height, width)`` orientation in ``Camera``.

The exposure loop mirrors ``LivePreviewWorker``: set gain, start the
exposure, poll ``ImageReady`` every 100 ms with a deadline of exposure + 20 s,
then download.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import numpy as np

from argos.core.alpaca.camera import Camera
from argos.core.alpaca.client import AlpacaError
from argos.core.alpaca.filterwheel import FilterWheel
from argos.core.alpaca.focuser import Focuser
from argos.core.alpaca.telescope import Telescope
from argos.core.hardware import active as hardware
from argos.core.hardware import detect
from argos.server.devices.base import (
    CameraLimits,
    ConnectReport,
    DeviceError,
    ExposureCancelled,
    MountParked,
    MountReading,
)
from argos.server.state import SensorInfo

logger = logging.getLogger(__name__)

#: Telemetry period for a real mount. Each poll is ~8 Alpaca GETs; the Qt app
#: polls every 2 s (``POLL_INTERVAL_MS``) and the Seestar copes with that.
ALPACA_MOUNT_POLL_S = 2.0
#: Extra wait after the exposure time before giving up on ImageReady.
_READY_GRACE_S = 20.0
_READY_POLL_S = 0.1


class AlpacaCamera:
    """Implements :class:`~argos.server.devices.base.CameraDevice`."""

    source = "alpaca"

    def __init__(self, host: str, port: int) -> None:
        self._cam = Camera(host, port)
        try:
            self.name = self._cam.connect()
        except AlpacaError as exc:
            raise DeviceError(f"Camera: {exc}") from exc
        # ASCOM SensorType 0 = monochrome; anything else is a colour sensor
        # whose raw frame is a CFA mosaic laid out as the profile says.
        sensor_type = self._cam.get_sensor_metadata().get("sensor_type")
        mono = sensor_type is not None and int(sensor_type) == 0
        self._bayer = None if mono else hardware.profile().bayer_pattern
        #: The last gain refusal, logged once per streak (the gain itself is
        #: sent before every exposure, as LivePreviewWorker does).
        self._gain_error: str | None = None

    def sensor(self) -> SensorInfo:
        return SensorInfo(
            width=int(self._cam.width), height=int(self._cam.height), bitpix=16, bayer=self._bayer
        )

    def connect_report(self) -> ConnectReport:
        """The Qt connect messages (``device_session.py:368-415``), as data.

        Profile mismatches are advisory: the profile is never switched here
        (``detect.py`` module docstring); the observer decides.
        """
        report: ConnectReport = []
        scope = hardware.profile()
        width = getattr(self._cam, "width", None)
        height = getattr(self._cam, "height", None)
        for note in detect.mismatches(scope, camera_name=self.name, width=width, height=height):
            report.append(("warning", f"Profile mismatch — {note}"))
        better = detect.suggest(camera_name=self.name, width=width, height=height)
        if better is not None and better.key != scope.key:
            report.append(
                ("warning", f"This looks like a {better.name} — change the telescope profile.")
            )
        try:
            offset = self._cam.get_offset()
            max_bin = int(getattr(self._cam, "max_bin", 1) or 1)
            report.append(
                (
                    "info",
                    f"Camera limits: gain {self._cam.gain_min}–{self._cam.gain_max}, "
                    f"exposure {self._cam.exposure_min:g}–{self._cam.exposure_max:g}s"
                    + (", offset" if offset is not None else "")
                    + (f", bin ≤{max_bin}" if max_bin > 1 else ""),
                )
            )
        except Exception as exc:  # a description, never a reason to fail the connect
            logger.debug("Camera limits unavailable: %s", exc)
        return report

    def expose(
        self,
        exposure_s: float,
        gain: int,
        cancel: threading.Event,
        on_readout: Callable[[], None],
        *,
        light: bool = True,
        on_start: Callable[[], None] | None = None,
    ) -> np.ndarray:
        try:
            # Sent before EVERY exposure (exposure_worker.py:145-149): a refused
            # or lost set is retried on the next frame, and a gain changed by
            # another client (the Seestar app, a driver restart) is restored, so
            # FITS GAIN / EGAIN describe the frame (science review of wave 3).
            try:
                self._cam.set_gain(int(gain))
                self._gain_error = None
            except AlpacaError as exc:
                text = str(exc)
                if text != self._gain_error:
                    logger.warning(
                        "Could not set gain %d: %s — this frame's gain is not confirmed",
                        int(gain),
                        text,
                    )
                self._gain_error = text
            if on_start is not None:
                on_start()  # DATE-OBS: just before StartExposure (exposure_worker.py:160)
            self._cam.start_exposure(float(exposure_s), light=bool(light))
            deadline = time.monotonic() + float(exposure_s) + _READY_GRACE_S
            while not self._cam.is_image_ready():
                if cancel.wait(_READY_POLL_S):
                    self.abort()
                    raise ExposureCancelled()
                if time.monotonic() > deadline:
                    raise DeviceError("Exposure timeout — no image after the expected duration")
            if cancel.is_set():
                raise ExposureCancelled()
            on_readout()
            return self._cam.get_image_array()
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def abort(self) -> None:
        self._cam.stop_exposure()  # logs and swallows its own errors

    def close(self) -> None:
        self._cam.disconnect()

    # -- wave 3 camera extras (camera.py:70-133, 205-306) ---------------------

    def limits(self) -> CameraLimits:
        cam = self._cam
        low = getattr(cam, "offset_min", None)
        high = getattr(cam, "offset_max", None)
        offset_range: tuple[int, int] | None = None
        if self.get_offset() is not None:
            offset_range = (
                int(low) if low is not None else 0,
                int(high) if high is not None else 255,
            )
        return CameraLimits(
            gain_min=int(getattr(cam, "gain_min", 0)),
            gain_max=int(getattr(cam, "gain_max", 600)),
            exposure_min_s=float(getattr(cam, "exposure_min", 0.001)),
            exposure_max_s=float(getattr(cam, "exposure_max", 3600.0)),
            offset_range=offset_range,
            max_bin=max(1, int(getattr(cam, "max_bin", 1) or 1)),
        )

    def get_offset(self) -> int | None:
        reader = getattr(self._cam, "get_offset", None)
        if reader is None:
            return None
        try:
            return reader()
        except Exception as exc:
            logger.debug("Offset read failed: %s", exc)
            return None

    def set_offset(self, value: int) -> None:
        try:
            self._cam.set_offset(int(value))
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def set_binning(self, value: int) -> None:
        try:
            self._cam.set_binning(int(value))
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def temperature(self) -> float | None:
        reader = getattr(self._cam, "get_ccd_temperature", None)
        if reader is None:
            return None
        try:
            return reader()
        except Exception:
            return None

    def fits_readings(self) -> dict[str, object]:
        """The four camera reads of a Take-shot save (acquisition_engine.py:1856-1859)."""
        out: dict[str, object] = {}
        for key, method in (
            ("ccd_temp", "get_ccd_temperature"),
            ("egain_driver", "get_electrons_per_adu"),
            ("offset", "get_offset"),
            ("readout_mode", "get_readout_mode_name"),
        ):
            reader = getattr(self._cam, method, None)
            try:
                out[key] = reader() if reader is not None else None
            except Exception as exc:  # the core readers are tolerant; a fake may not be
                logger.debug("%s failed: %s", method, exc)
                out[key] = None
        return out


class AlpacaMount:
    """Implements :class:`~argos.server.devices.base.MountDevice`."""

    poll_interval_s = ALPACA_MOUNT_POLL_S

    def __init__(self, host: str, port: int) -> None:
        self._scope = Telescope(host, port)
        try:
            self.name = self._scope.connect()
        except AlpacaError as exc:
            raise DeviceError(f"Mount: {exc}") from exc
        #: The driver's own site ``(lat, lon, elev|None)``, or ``None`` when it
        #: does not expose one; read once here, at connect time, on the
        #: connecting thread (the site check compares it, wave 2).
        self.driver_site = self._read_driver_site()
        #: AlignmentMode at connect (telescope.py:266-271), as the API names it.
        mode = getattr(self._scope, "alignment_mode", None)
        self.alignment = _ALIGNMENTS.get(mode) if isinstance(mode, str) else None
        clock = getattr(self._scope, "clock_error_seconds", None)
        self.clock_error_s = float(clock) if isinstance(clock, (int, float)) else None

    def _read_driver_site(self) -> tuple[float, float, float | None] | None:
        """``SiteLatitude`` / ``SiteLongitude`` (``telescope.py:193-215``).

        ``Telescope.connect`` reads them only for a topocentric driver and keeps
        them private (``_site``); otherwise they are read here, once, from the
        alpyca device. Several Seestar firmwares do not expose them: ``None``.
        """
        site = getattr(self._scope, "_site", None)
        if site is not None:
            try:
                return float(site[0]), float(site[1]), float(site[2])
            except (TypeError, ValueError, IndexError):
                return None
        device = getattr(self._scope, "_scope", None)
        if device is None:
            return None
        try:
            latitude = float(device.SiteLatitude)
            longitude = float(device.SiteLongitude)
        except Exception as exc:  # property not implemented, or no answer
            logger.info("Mount site unavailable: %s", exc)
            return None
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            return None
        try:
            elevation: float | None = float(device.SiteElevation)
        except Exception:
            elevation = None
        return latitude, longitude, elevation

    def connect_report(self) -> ConnectReport:
        """The Qt mount connect messages (``device_session.py:276-291``), as data."""
        report: ConnectReport = []
        system = getattr(self._scope, "equatorial_system", None)
        if system:
            report.append(
                ("info", f"Mount coordinates: {system} → Argos J2000 conversion enabled.")
            )
        else:
            report.append(
                (
                    "warning",
                    "Mount coordinate system unavailable; assuming the driver accepts J2000.",
                )
            )
        clock = getattr(self._scope, "clock_error_seconds", None)
        if clock is not None and clock > 60.0:
            report.append(
                (
                    "error",
                    # H4 (device_session.py:377-382): what is really refused.
                    "Mount clock is %.1f h off — correct the date/time in the Seestar app, then "
                    "reconnect. GoTo, Sync and Center will be refused until then."
                    % (clock / 3600.0),
                )
            )
        return report

    def read(self) -> MountReading:
        try:
            pos = self._scope.get_position()
            parked = self._scope.is_parked()
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc
        pier = {"EAST": "east", "WEST": "west"}.get(self._scope.side_of_pier() or "")
        if parked:
            state = "parked"
        elif pos.slewing:
            state = "slewing"
        elif pos.tracking:
            state = "tracking"
        else:
            state = "idle"
        return MountReading(
            state=state,
            ra_hours=pos.ra,
            dec_deg=pos.dec,
            alt_deg=pos.altitude,
            az_deg=pos.azimuth,
            tracking=pos.tracking,
            pier_side=pier,
        )

    def _call(self, fn: Callable[..., object], *args: object) -> None:
        try:
            fn(*args)
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def _refuse_if_parked(self, action: str) -> None:
        # Same message and error code as the simulator; the driver would also
        # refuse, but with a generic error the UI cannot act on.
        try:
            parked = self._scope.is_parked()
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc
        if parked:
            raise MountParked(f"Mount is parked — unpark before {action}")

    def goto(self, ra_hours: float, dec_deg: float) -> None:
        self._refuse_if_parked("slewing")
        self._call(self._scope.slew_to, ra_hours, dec_deg)  # enables tracking first

    def stop(self) -> None:
        self._call(self._scope.abort_slew)

    def park(self) -> None:
        self._call(self._scope.park)

    def unpark(self) -> None:
        self._call(self._scope.unpark)

    def set_tracking(self, enabled: bool) -> None:
        self._refuse_if_parked("changing tracking")
        self._call(self._scope.set_tracking, bool(enabled))

    def close(self) -> None:
        self._scope.disconnect()

    # -- wave 3: jog and tracking rate (telescope.py:564-634) ----------------

    def move_axis(self, axis: int, rate_deg_s: float) -> None:
        self._call(self._scope.move_axis, int(axis), float(rate_deg_s))

    def tracking_rates(self) -> list[str]:
        """``TrackingRates`` as the driver lists them (Q-O15); [] when unknown."""
        device = getattr(self._scope, "_scope", None)
        try:
            rates = list(device.TrackingRates) if device is not None else []
        except Exception as exc:
            logger.info("TrackingRates unavailable: %s", exc)
            return []
        names = []
        for rate in rates:
            try:
                name = _DRIVE_RATES.get(int(rate))
            except (TypeError, ValueError):
                name = None
            if name is not None and name not in names:
                names.append(name)
        return names

    def tracking_rate(self) -> str | None:
        reader = getattr(self._scope, "get_tracking_rate", None)
        value = reader() if reader is not None else None
        return _DRIVE_RATES.get(value) if value is not None else None

    def set_tracking_rate(self, rate: str) -> None:
        index = {name: i for i, name in _DRIVE_RATES.items()}.get(rate)
        if index is None:
            raise DeviceError(f"Unknown tracking rate {rate!r}")
        self._call(self._scope.set_tracking_rate, index)


#: ASCOM DriveRates (telescope.py:610-622).
_DRIVE_RATES = {0: "sidereal", 1: "lunar", 2: "solar", 3: "king"}
#: Telescope.alignment_mode → MountState.alignment.
_ALIGNMENTS = {"Alt-Az": "altaz", "EQ": "eq", "EQ (GEM)": "eq_gem"}


class AlpacaFilterWheel:
    """Implements :class:`~argos.server.devices.base.FilterWheelDevice`
    (``device_session.py:430-448``; moves ``:85-122, 681-701``)."""

    name = "Filter wheel"

    def __init__(self, host: str, port: int) -> None:
        self._fw = FilterWheel(host, port)
        try:
            self._fw.connect()
            self._position_name = self._fw.position_name()
        except AlpacaError as exc:
            raise DeviceError(f"Filter wheel: {exc}") from exc
        #: Slot names from the active profile (``filterwheel.py:24-31``).
        self.slots: tuple[str, ...] = tuple(hardware.profile().filter_names)

    def info(self) -> str:
        return self._position_name

    def get_position(self) -> int:
        try:
            return int(self._fw.get_position())
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def set_position(self, index: int) -> None:
        try:
            self._fw.set_position(int(index))
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def position_name(self) -> str:
        try:
            name = str(self._fw.position_name())
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc
        self._position_name = name
        return name

    def close(self) -> None:
        self._fw.disconnect()


class AlpacaFocuser:
    """Implements :class:`~argos.server.devices.base.FocuserDevice`
    (``device_session.py:460-488``; moves ``:705-739``)."""

    def __init__(self, host: str, port: int) -> None:
        self._focuser = Focuser(host, port)
        try:
            self.name = self._focuser.connect()
            self.position = self._focuser.get_position()
        except AlpacaError as exc:
            raise DeviceError(f"Focuser: {exc}") from exc
        # Capability flags cached by Focuser.connect (focuser.py:52-83).
        self.max_step = int(getattr(self._focuser, "max_step", 100_000) or 100_000)
        self.max_increment = int(getattr(self._focuser, "max_increment", 1_000) or 1_000)
        self.absolute = bool(getattr(self._focuser, "absolute", True))
        size = getattr(self._focuser, "step_size_um", None)
        self.step_size_um = float(size) if isinstance(size, (int, float)) else None

    def info(self) -> str:
        return self.name

    def get_position(self) -> int:
        try:
            return int(self._focuser.get_position())
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def is_moving(self) -> bool:
        try:
            return bool(self._focuser.is_moving())
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def move_to(self, position: int) -> None:
        try:
            self._focuser.move_to(int(position))
        except AlpacaError as exc:
            raise DeviceError(str(exc)) from exc

    def halt(self) -> None:
        self._focuser.halt()  # logs and swallows its own errors (focuser.py:151-156)

    def get_temperature(self) -> float | None:
        reader = getattr(self._focuser, "get_temperature", None)
        try:
            return reader() if reader is not None else None
        except Exception:
            return None

    def close(self) -> None:
        self._focuser.disconnect()
