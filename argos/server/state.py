"""The three state records of the contract, as immutable snapshots.

``ConnectionState``, ``CameraState`` and ``MountState`` are frozen dataclasses:
the hub swaps whole records under its lock and hands the same objects to any
thread, so a reader can never observe a half-updated state. ``to_dict()``
gives exactly the JSON shape documented in ``protocol.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

ConnectionStateName = Literal["disconnected", "connecting", "connected", "error"]
CameraStateName = Literal["idle", "exposing", "downloading", "live", "error"]
MountStateName = Literal["parked", "idle", "slewing", "tracking", "error"]

#: Camera states during which a new exposure (or an opened file) is refused.
CAMERA_BUSY = frozenset({"exposing", "downloading", "live"})


def utc_iso(when: datetime | None = None) -> str:
    """ISO 8601 UTC with millisecond precision and a ``Z`` suffix."""
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class SensorInfo:
    width: int
    height: int
    bitpix: int = 16
    #: CFA layout of a raw colour sensor (``"GRBG"``…), ``None`` for mono data.
    bayer: str | None = None


@dataclass(frozen=True)
class ConnectionState:
    state: ConnectionStateName = "disconnected"
    mode: Literal["simulator", "alpaca"] | None = None
    device_name: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CameraOwner = Literal["idle", "live", "single", "autofocus", "sequence"]


@dataclass(frozen=True)
class CameraState:
    state: CameraStateName = "idle"
    #: v1: the frame being exposed (``current``) while one is, else the settings.
    exposure_s: float = 2.0
    gain: int = 80
    last_frame_seq: int | None = None
    sensor: SensorInfo | None = None
    # -- wave 3 (A21), additive ------------------------------------------------
    #: Who drives the camera (``camera_service.py:60-77``).
    owner: CameraOwner = "idle"
    #: ``CaptureSettings`` as a dict: what the NEXT frame uses.
    settings: dict[str, Any] | None = None
    #: ``FrameSettings`` of the frame being exposed now, or ``None``.
    current: dict[str, Any] | None = None
    #: Take shots still waiting for their frame (0 or 1).
    save_pending: int = 0
    #: A Dark/Bias Take shot waiting for the wheel to reach Dark.
    waiting_for: Literal["filterwheel"] | None = None
    limits: dict[str, Any] | None = None
    offset: dict[str, int] | None = None
    binning: dict[str, int] | None = None
    temperature_c: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Target:
    ra_hours: float
    dec_deg: float


@dataclass(frozen=True)
class MountState:
    state: MountStateName = "idle"
    ra_hours: float = 0.0
    dec_deg: float = 0.0
    alt_deg: float | None = None
    az_deg: float | None = None
    tracking: bool = False
    pier_side: Literal["east", "west"] | None = None
    target: Target | None = None
    # -- wave 3 (A29), additive ------------------------------------------------
    alignment: Literal["altaz", "eq", "eq_gem"] | None = None
    tracking_rate: str | None = None
    tracking_rates: tuple[str, ...] = ()
    goto_blocked: dict[str, Any] | None = None
    center_available: bool = False
    jog: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["tracking_rates"] = list(self.tracking_rates)
        return record

    def discrete(self) -> tuple:
        """Everything but the continuously moving coordinates.

        A change here is a *state transition* and is announced with a
        ``status`` event; coordinate changes alone only feed the 4 Hz
        ``mount`` telemetry.
        """
        return (
            self.state,
            self.tracking,
            self.pier_side,
            self.target,
            self.alignment,
            self.tracking_rate,
            self.tracking_rates,
            self.goto_blocked,
            self.jog,
        )
