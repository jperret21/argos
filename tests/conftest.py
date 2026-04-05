"""pytest fixtures and shared configuration."""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
# ASCOM Alpaca Simulator (localhost:32323) — for telescope/camera Alpaca tests
# ---------------------------------------------------------------------------

SIMULATOR_HOST = "localhost"
SIMULATOR_PORT = 32323


def is_simulator_running() -> bool:
    """Check if the ASCOM Alpaca Simulator is reachable."""
    try:
        requests.get(
            f"http://{SIMULATOR_HOST}:{SIMULATOR_PORT}/api/v1/telescope/0/connected",
            timeout=1,
        )
        return True
    except Exception:
        return False


simulator_required = pytest.mark.skipif(
    not is_simulator_running(),
    reason="ASCOM Alpaca Simulator not running on localhost:32323",
)


# ---------------------------------------------------------------------------
# Seestar native simulator (seestar_alp) — for native JSON-RPC client tests
# ---------------------------------------------------------------------------

#: Absolute path to the seestar_alp simulator source directory.
_SEESTAR_SIM_DIR = Path(__file__).parents[2] / "seestar_alp-main" / "simulator" / "src"

#: Ports used by the simulator during tests (different from real device ports).
_SIM_TCP_PORT = 14700
_SIM_UDP_PORT = 14720
_SIM_HOST     = "127.0.0.1"


def _is_seestar_sim_available() -> bool:
    return (_SEESTAR_SIM_DIR / "main.py").exists()


def _wait_for_tcp(host: str, port: int, timeout: float = 8.0) -> bool:
    """Poll until the TCP port accepts connections or the timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


@pytest.fixture(scope="session")
def seestar_simulator():
    """Start the seestar_alp simulator in an in-process background thread.

    Yields a dict with ``host``, ``tcp_port``, and ``udp_port``.
    Automatically skipped if the seestar_alp project is not present next to
    Seestar_controller, or if its dependencies are not installed.

    Install simulator dependencies (once, into the system/active Python):
        pip install tomlkit pyhocon blinker pydash geomag tzlocal
    """
    if not _is_seestar_sim_available():
        pytest.skip(
            f"seestar_alp simulator not found at {_SEESTAR_SIM_DIR}. "
            "Clone seestar_alp-main next to Seestar_controller to run native tests."
        )

    # Add simulator source to sys.path so its local imports resolve.
    sim_dir_str = str(_SEESTAR_SIM_DIR)
    added_to_path = sim_dir_str not in sys.path
    if added_to_path:
        sys.path.insert(0, sim_dir_str)

    try:
        from config import Config as _SimConfig  # type: ignore[import]
        import log as _sim_log                   # type: ignore[import]
        from listener import SocketListener      # type: ignore[import]
    except ModuleNotFoundError as exc:
        pytest.skip(
            f"Seestar simulator dependency missing: {exc}. "
            "Run: pip install tomlkit pyhocon blinker pydash geomag tzlocal"
        )
        return  # unreachable, satisfies type checker

    # Configure the simulator to use test ports so it doesn't collide with a
    # real device that might be on the network.
    _SimConfig.load_toml()
    _SimConfig.ip_address         = _SIM_HOST
    _SimConfig.tcp_port           = _SIM_TCP_PORT
    _SimConfig.udp_port           = _SIM_UDP_PORT
    _SimConfig.log_to_stdout      = False
    _SimConfig.log_heartbeat_msgs = False

    logger   = _sim_log.init_logging()
    listener = SocketListener(logger, _SIM_HOST, _SIM_TCP_PORT, _SIM_UDP_PORT)
    shutdown = threading.Event()
    listener.shutdown_event = shutdown

    thread = threading.Thread(
        target=listener._start_socket_listener,
        name="seestar-sim",
        daemon=True,
    )
    thread.start()

    if not _wait_for_tcp(_SIM_HOST, _SIM_TCP_PORT, timeout=8.0):
        shutdown.set()
        thread.join(timeout=2.0)
        pytest.fail("Seestar simulator TCP port did not open within 8 s")

    yield {
        "host":     _SIM_HOST,
        "tcp_port": _SIM_TCP_PORT,
        "udp_port": _SIM_UDP_PORT,
    }

    # Teardown: stop the listener thread gracefully.
    shutdown.set()
    thread.join(timeout=3.0)
    if added_to_path:
        sys.path.remove(sim_dir_str)
