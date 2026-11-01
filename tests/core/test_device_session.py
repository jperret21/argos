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


def test_refresh_filter_reports_where_the_wheel_is(monkeypatch) -> None:
    """S3: after a sequence moved the wheel, the Camera form must be told."""
    import argos.core.session.device_session as ds

    class _SyncPool:
        def start(self, task) -> None:
            task.run()

    monkeypatch.setattr(ds.QThreadPool, "globalInstance", staticmethod(lambda: _SyncPool()))
    session = DeviceSession(Config(dict(_DEFAULTS)))
    wheel = MagicMock()
    wheel.get_position.return_value = 2
    wheel.position_name.return_value = "LP"
    session._filterwheel = wheel
    moved: list[tuple[int, str]] = []
    session.filter_moved.connect(lambda pos, name: moved.append((pos, name)))

    session.refresh_filter()

    assert moved == [(2, "LP")]
    wheel.set_position.assert_not_called()  # a read, never a move
