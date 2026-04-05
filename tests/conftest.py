"""pytest fixtures and shared configuration."""

import pytest
import requests

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
