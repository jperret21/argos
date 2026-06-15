"""Focuser wrapper validation against the ASCOM Alpaca simulator.

Connect, read position/temperature, move absolute + relative, and halt — the
operations the autofocus worker and Focus tab rely on. Auto-skipped when the
simulator is down.
"""

from __future__ import annotations

import time

from seercontrol.core.alpaca.focuser import Focuser
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required


def _wait_still(foc: Focuser, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not foc.is_moving():
            return
        time.sleep(0.2)
    raise AssertionError("focuser kept moving past timeout")


@simulator_required
def test_connect_caps_and_position() -> None:
    foc = Focuser(SIMULATOR_HOST, SIMULATOR_PORT)
    name = foc.connect()
    try:
        assert isinstance(name, str)
        assert foc.is_connected
        assert foc.max_step > 0
        assert foc.get_position() >= 0
        foc.get_temperature()  # None or float — must not raise
    finally:
        foc.disconnect()
        assert not foc.is_connected


@simulator_required
def test_move_to_absolute() -> None:
    foc = Focuser(SIMULATOR_HOST, SIMULATOR_PORT)
    foc.connect()
    try:
        target = min(foc.max_step, foc.get_position() + 200)
        foc.move_to(target)
        _wait_still(foc)
        assert abs(foc.get_position() - target) <= 1
    finally:
        foc.disconnect()


@simulator_required
def test_step_relative_returns_target() -> None:
    foc = Focuser(SIMULATOR_HOST, SIMULATOR_PORT)
    foc.connect()
    try:
        start = foc.get_position()
        target = foc.step(-150)
        _wait_still(foc)
        assert target == max(0, start - 150)
        assert abs(foc.get_position() - target) <= 1
    finally:
        foc.disconnect()


@simulator_required
def test_halt_is_safe_when_idle() -> None:
    foc = Focuser(SIMULATOR_HOST, SIMULATOR_PORT)
    foc.connect()
    try:
        foc.halt()  # must not raise even with no motion in progress
    finally:
        foc.disconnect()
