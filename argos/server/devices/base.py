"""What the hub needs from a camera and a mount.

Both protocols are synchronous and blocking: the hub calls them from worker
threads (exposure job, mount poller) or from FastAPI's threadpool, never from
the event loop.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Literal, Protocol

import numpy as np

from argos.server.state import MountStateName, SensorInfo


class DeviceError(Exception):
    """A device refused a command or stopped answering."""


class ExposureCancelled(Exception):
    """The exposure was aborted through its cancel event."""


class MountParked(DeviceError):
    """The command needs an unparked mount."""


class CameraDevice(Protocol):
    source: Literal["simulator", "alpaca"]
    name: str

    def sensor(self) -> SensorInfo: ...

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
        """Take one exposure and return it as uint16, row 0 = top.

        Blocks for the exposure time; returns early with
        :class:`ExposureCancelled` once *cancel* is set. *on_start* is called
        right before ``StartExposure`` (the frame's ``DATE-OBS``, as
        ``exposure_worker.py:160``), *on_readout* when ``ImageReady`` turns
        true, before the download (the end of the exposure). *light* is the
        ASCOM ``Light`` flag: a Seestar has no shutter, so it closes nothing
        (wave 3: only the wheel's Dark slot blocks the light).
        """
        ...

    def abort(self) -> None:
        """Abort a running exposure (best effort, never raises)."""
        ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class MountReading:
    """One poll of the mount, in Argos coordinates (ICRS/J2000)."""

    state: MountStateName
    ra_hours: float
    dec_deg: float
    alt_deg: float | None
    az_deg: float | None
    tracking: bool
    pier_side: Literal["east", "west"] | None


class MountDevice(Protocol):
    name: str
    #: Period of the hub's telemetry poll for this mount (s).
    poll_interval_s: float

    def read(self) -> MountReading: ...

    def goto(self, ra_hours: float, dec_deg: float) -> None: ...

    def stop(self) -> None:
        """Abort a slew (ASCOM ``AbortSlew``); tracking is left as it was."""
        ...

    def park(self) -> None: ...

    def unpark(self) -> None: ...

    def set_tracking(self, enabled: bool) -> None: ...

    # Wave 4 (A32, A33), optional: ``sync(ra_hours, dec_deg)`` — SyncToCoordinates.

    def close(self) -> None: ...


class AuxDevice(Protocol):
    """A filter wheel or a focuser, as the device table describes it."""

    name: str

    def info(self) -> str:
        """One line for the device table (filter slot, focuser position…)."""
        ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Wave 3: what the services need beyond the v1 protocols. Every call blocks
# (Alpaca HTTP) and runs on a worker thread or in FastAPI's threadpool.
# Optional features are duck-typed: a method that is absent means "the
# driver does not have it" (an older fake, a minimal adapter).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraLimits:
    """The driver's ranges, read at connect (``camera.py:70-133``)."""

    gain_min: int
    gain_max: int
    exposure_min_s: float
    exposure_max_s: float
    #: ``(min, max)`` of ``Offset``, or ``None`` when the driver has none.
    offset_range: tuple[int, int] | None = None
    #: ``min(MaxBinX, MaxBinY)``; 1 = no binning.
    max_bin: int = 1


class CameraExtras(Protocol):
    """Optional camera features (``AlpacaCamera``, ``SimCamera``)."""

    def limits(self) -> CameraLimits: ...

    def get_offset(self) -> int | None: ...

    def set_offset(self, value: int) -> None: ...

    def set_binning(self, value: int) -> None: ...

    def temperature(self) -> float | None:
        """Sensor temperature (°C), ``None`` when unavailable (never raises)."""
        ...

    def fits_readings(self) -> dict[str, object]:
        """What a FITS save reads from the camera (``acquisition_engine.py:1856-1859``):
        ``ccd_temp``, ``egain_driver``, ``offset``, ``readout_mode`` (each may be None)."""
        ...


class FilterWheelDevice(Protocol):
    """A filter wheel (``argos.core.alpaca.filterwheel.FilterWheel``)."""

    name: str
    #: Slot names in wheel order (the active profile's ``filter_names``).
    slots: tuple[str, ...]

    def get_position(self) -> int:
        """Current slot index; −1 while the wheel turns."""
        ...

    def set_position(self, index: int) -> None:
        """Start a move (asynchronous: ``get_position`` reads −1 until it ends)."""
        ...

    def position_name(self) -> str:
        """Slot name, ``"Moving…"`` while turning (``filterwheel.py:129-134``)."""
        ...


class FocuserDevice(Protocol):
    """A focuser (``argos.core.alpaca.focuser.Focuser``)."""

    name: str
    max_step: int
    max_increment: int
    absolute: bool
    step_size_um: float | None

    def get_position(self) -> int: ...

    def is_moving(self) -> bool: ...

    def move_to(self, position: int) -> None: ...

    def halt(self) -> None: ...

    def get_temperature(self) -> float | None: ...


class MountExtras(Protocol):
    """Optional mount features (wave 3, rows A29-A31)."""

    #: ``"altaz"``, ``"eq"``, ``"eq_gem"`` or ``None`` (``AlignmentMode`` at connect).
    alignment: str | None
    #: Mount-vs-computer clock offset measured at connect (s), or ``None``.
    clock_error_s: float | None

    def move_axis(self, axis: int, rate_deg_s: float) -> None:
        """ASCOM ``MoveAxis``: 0 = primary, 1 = secondary; 0.0 stops the axis."""
        ...

    def tracking_rates(self) -> list[str]: ...

    def tracking_rate(self) -> str | None: ...

    def set_tracking_rate(self, rate: str) -> None: ...


#: ``(level, message)`` lines a device reports right after it connected; the
#: hub logs them, and keeps the ``warning`` / ``error`` ones as the device's
#: ``warnings``. Adapters expose them as an optional ``connect_report()``.
ConnectReport = list[tuple[str, str]]
