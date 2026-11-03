"""Server settings — what the CLI (or a test) hands to :func:`create_app`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
        config_dir: Folder of ``config.json``. ``None`` keeps the configuration
            in memory (defaults, never written): what tests get unless they
            pass a temporary folder. The CLI always passes a folder.
        log_dir: Folder of the rotating log file and crash reports (CLI only;
            informational inside the app, reported by ``/api/app/info``).
        log_file: The rotating log file in use, if any (informational).
        manage_process: Let the app change process-wide state: the root log
            level (``ui.log_level``) and the core modules' cache and calibration
            folders (``data_paths.*``). The CLI sets it; in-process tests leave
            it off so one test's configuration never leaks into the next.
        connect_timeout_s: TCP pre-check budget before an Alpaca device is
            opened (``--connect-timeout``); ``None`` skips the pre-check.
        network_interval_s: Period of the Seestar reachability probe; ``0``
            turns the background probe off (tests), the on-demand check stays.
        network_probe_timeout_s: TCP connect timeout of one reachability probe.
        mount_lost_after: Consecutive failed mount polls that declare the
            connection lost (``polling_worker.py:49``: 3).
        mount_retry_s: Period of the mount auto-reconnect
            (``device_session.py:159``: 10 s).
        site_check_period_s: Period of the site-against-mount re-check while
            the mount is connected (wave 2, ``site_check.py``: 300 s).
        site_check_settle_s: After a site change, wait until the site has
            stayed unchanged this long before checking (``site_check.py``: 2 s).
    """

    token: str
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    simulator: bool = False
    sim: SimOptions = field(default_factory=SimOptions)
    config_dir: Path | None = None
    log_dir: Path | None = None
    log_file: Path | None = None
    manage_process: bool = False
    connect_timeout_s: float | None = 3.0
    network_interval_s: float = 10.0
    network_probe_timeout_s: float = 1.5
    mount_lost_after: int = 3
    mount_retry_s: float = 10.0
    site_check_period_s: float = 300.0
    site_check_settle_s: float = 2.0
