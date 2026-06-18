"""Filter wheel wrapper validation against the ASCOM Alpaca simulator.

The Seestar S30 Pro has an internal filter wheel — Dark / IR-cut / LP
(light-pollution), see ``POSITION_NAMES``. The sequencer drives it on filter
changes. The simulator exposes a wheel, so we validate connect + position
change here. Auto-skipped when the simulator is down.
"""

from __future__ import annotations

import time

from argos.core.alpaca.filterwheel import FilterWheel
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required


def _settle(fw: FilterWheel, timeout: float = 30.0) -> int:
    """Wait until the wheel stops moving (get_position != -1)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        pos = fw.get_position()
        if pos != -1:
            return pos
        time.sleep(0.2)
    raise AssertionError("wheel kept moving past timeout")


@simulator_required
def test_connect_and_read_position() -> None:
    fw = FilterWheel(SIMULATOR_HOST, SIMULATOR_PORT)
    fw.connect()
    try:
        assert fw.is_connected
        assert _settle(fw) >= 0
        assert isinstance(fw.position_name(), str)
    finally:
        fw.disconnect()
        assert not fw.is_connected


@simulator_required
def test_change_position() -> None:
    fw = FilterWheel(SIMULATOR_HOST, SIMULATOR_PORT)
    fw.connect()
    try:
        _settle(fw)
        fw.set_position(1)
        assert _settle(fw) == 1
        fw.set_position(0)
        assert _settle(fw) == 0
    finally:
        fw.disconnect()
