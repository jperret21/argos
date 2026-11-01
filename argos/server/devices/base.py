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
    ) -> np.ndarray:
        """Take one exposure and return it as uint16, row 0 = top.

        Blocks for the exposure time; returns early with
        :class:`ExposureCancelled` once *cancel* is set. *on_readout* is called
        when the shutter closes and the download starts.
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

    def close(self) -> None: ...


class AuxDevice(Protocol):
    """A filter wheel or a focuser: connected and described, driven in a later wave."""

    name: str

    def info(self) -> str:
        """One line for the device table (filter slot, focuser position…)."""
        ...

    def close(self) -> None: ...


#: ``(level, message)`` lines a device reports right after it connected; the
#: hub logs them, and keeps the ``warning`` / ``error`` ones as the device's
#: ``warnings``. Adapters expose them as an optional ``connect_report()``.
ConnectReport = list[tuple[str, str]]
