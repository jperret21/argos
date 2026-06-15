"""Telescope wrapper validation against the ASCOM Alpaca simulator.

Drives the real :class:`Telescope` wrapper: read position, slew and reach a
target, sync, toggle tracking. Auto-skipped when the simulator is down.

The motion tests are **self-restoring** — they return the mount to its starting
pointing (slew back / sync back) so repeated runs can't drift the simulator into
a below-horizon or stuck state. Every test aborts + disconnects in ``finally``.
"""

from __future__ import annotations

import time

from seercontrol.core.alpaca.telescope import Telescope
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required


def _wait_slew_done(scope: Telescope, timeout: float = 60.0) -> bool:
    """Block until the mount stops slewing. Returns False on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not scope.get_position().slewing:
            return True
        time.sleep(0.3)
    return False


def _wait_slew_started(scope: Telescope, timeout: float = 8.0) -> bool:
    """Return True once the mount reports Slewing (slew was accepted)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if scope.get_position().slewing:
            return True
        time.sleep(0.2)
    return False


@simulator_required
def test_connect_and_position_ranges() -> None:
    scope = Telescope(SIMULATOR_HOST, SIMULATOR_PORT)
    name = scope.connect()
    try:
        assert isinstance(name, str)
        pos = scope.get_position()
        assert 0.0 <= pos.ra < 24.0
        assert -90.0 <= pos.dec <= 90.0
        alt, az = scope.get_altaz()
        assert -90.0 <= alt <= 90.0
        assert 0.0 <= az <= 360.0
    finally:
        scope.disconnect()


@simulator_required
def test_slew_reaches_target_then_returns() -> None:
    scope = Telescope(SIMULATOR_HOST, SIMULATOR_PORT)
    scope.connect()
    try:
        if scope.is_parked():
            scope.unpark()
        scope.set_tracking(True)
        start = scope.get_position()
        # Small offset → quick slew that stays near the (above-horizon) start.
        target_ra = (start.ra + 0.3) % 24.0
        target_dec = max(-80.0, min(80.0, start.dec + 2.0))

        scope.slew_to(target_ra, target_dec)
        assert _wait_slew_started(scope), "mount never reported Slewing"
        assert _wait_slew_done(scope), "slew did not finish in time"

        pos = scope.get_position()
        assert abs(pos.ra - target_ra) < 0.1  # RA in hours
        assert abs(pos.dec - target_dec) < 1.0

        # Restore: slew back to the starting pointing so runs don't accumulate.
        scope.slew_to(start.ra, start.dec)
        _wait_slew_done(scope)
    finally:
        scope.abort_slew()
        scope.disconnect()


@simulator_required
def test_tracking_toggle() -> None:
    scope = Telescope(SIMULATOR_HOST, SIMULATOR_PORT)
    scope.connect()
    try:
        scope.set_tracking(True)
        assert scope.get_position().tracking is True
        scope.set_tracking(False)
        assert scope.get_position().tracking is False
    finally:
        scope.set_tracking(False)
        scope.disconnect()


@simulator_required
def test_sync_updates_pointing_then_restores() -> None:
    scope = Telescope(SIMULATOR_HOST, SIMULATOR_PORT)
    scope.connect()
    try:
        if scope.is_parked():
            scope.unpark()
        scope.set_tracking(True)
        before = scope.get_position()
        sync_ra = (before.ra + 0.2) % 24.0
        scope.sync_to(sync_ra, before.dec)
        after = scope.get_position()
        assert abs(after.ra - sync_ra) < 0.1
        # Restore the pointing model so the offset doesn't accumulate across runs.
        scope.sync_to(before.ra, before.dec)
    finally:
        scope.set_tracking(False)
        scope.disconnect()
