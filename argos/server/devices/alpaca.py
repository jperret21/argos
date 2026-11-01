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
from argos.core.alpaca.telescope import Telescope
from argos.core.hardware import active as hardware
from argos.server.devices.base import DeviceError, ExposureCancelled, MountParked, MountReading
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
        #: Gain last sent to the driver: set once per change, not on every
        #: live frame (a driver without Gain would warn on each one).
        self._gain_sent: int | None = None

    def sensor(self) -> SensorInfo:
        return SensorInfo(
            width=int(self._cam.width), height=int(self._cam.height), bitpix=16, bayer=self._bayer
        )

    def expose(
        self,
        exposure_s: float,
        gain: int,
        cancel: threading.Event,
        on_readout: Callable[[], None],
    ) -> np.ndarray:
        try:
            if int(gain) != self._gain_sent:
                self._gain_sent = int(gain)  # tried once, even if refused
                try:
                    self._cam.set_gain(int(gain))
                except AlpacaError as exc:
                    logger.warning("Could not set gain: %s", exc)
            self._cam.start_exposure(float(exposure_s), light=True)
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


class AlpacaMount:
    """Implements :class:`~argos.server.devices.base.MountDevice`."""

    poll_interval_s = ALPACA_MOUNT_POLL_S

    def __init__(self, host: str, port: int) -> None:
        self._scope = Telescope(host, port)
        try:
            self.name = self._scope.connect()
        except AlpacaError as exc:
            raise DeviceError(f"Mount: {exc}") from exc

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
