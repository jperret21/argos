"""Server settings — what the CLI (or a test) hands to :func:`create_app`."""

from __future__ import annotations

from dataclasses import dataclass, field

from argos.server import DEFAULT_PORT


@dataclass(frozen=True)
class SimOptions:
    """Knobs of the built-in simulator.

    The defaults describe a Seestar S50 as it delivers frames: 1080 px wide by
    1920 px high (portrait — the Qt viewer's "auto" rotation exists for exactly
    this). Tests shrink the frame and speed up the mount so the suite stays fast.
    """

    width: int = 1080
    height: int = 1920
    #: Base seed of the synthetic sky. Frame *n* is a pure function of
    #: ``(seed, n, exposure, gain)``, so a run is reproducible.
    seed: int = 20261101
    n_stars: int = 240
    #: Simulated slew speed on each axis (deg/s).
    slew_rate_deg_s: float = 4.0
    #: Mount telemetry period (s). 0.25 s is the contract's 4 Hz ceiling.
    mount_poll_s: float = 0.25


@dataclass(frozen=True)
class Settings:
    """Runtime settings of one server instance.

    Args:
        token: Bearer token every protected route and WebSocket must present.
        host: Interface the CLI bound (informational inside the app).
        port: Port the CLI bound (informational inside the app).
        simulator: Connect the simulator during startup (``--simulator``).
        sim: Simulator parameters.
    """

    token: str
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    simulator: bool = False
    sim: SimOptions = field(default_factory=SimOptions)
