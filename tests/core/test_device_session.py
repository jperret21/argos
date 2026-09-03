"""Focused unit tests for mount commands owned by ``DeviceSession``."""

from __future__ import annotations

from unittest.mock import MagicMock

from argos.core.config import _DEFAULTS, Config
from argos.core.session.device_session import DeviceSession


def test_center_target_syncs_solved_field_then_repeats_goto() -> None:
    session = DeviceSession(Config(dict(_DEFAULTS)))
    telescope = MagicMock()
    session._telescope = telescope

    session.center_target_from_solution(20.0357, 58.7516, 20.054345, 58.954590)

    telescope.set_tracking.assert_called_once_with(True)
    telescope.sync_to.assert_called_once_with(20.0357, 58.7516)
    telescope.slew_to.assert_called_once_with(20.054345, 58.954590)
    assert session.target_radec == (20.054345, 58.954590)
