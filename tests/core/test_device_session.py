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


class _SyncPool:
    """QThreadPool stand-in that runs a runnable at once, on this thread."""

    def start(self, task) -> None:
        task.run()


def test_failed_filter_move_ends_busy_and_reports_the_real_slot(monkeypatch) -> None:
    """H9: a refused wheel move must not leave the wheel 'busy' and the form stale."""
    import argos.core.session.device_session as ds
    from argos.core.alpaca.client import AlpacaError

    monkeypatch.setattr(ds.QThreadPool, "globalInstance", staticmethod(lambda: _SyncPool()))
    session = DeviceSession(Config(dict(_DEFAULTS)))
    wheel = MagicMock()
    wheel.set_position.side_effect = AlpacaError(1025, "Invalid value")
    wheel.get_position.return_value = 1  # the wheel stayed on IR
    wheel.position_name.return_value = "IR"
    session._filterwheel = wheel
    moved: list[tuple[int, str]] = []
    states: list[tuple[str, str, str]] = []
    logs: list[tuple[str, str]] = []
    session.filter_moved.connect(lambda pos, name: moved.append((pos, name)))
    session.device_state_changed.connect(lambda d, s, i: states.append((d, s, i)))
    session.log_message.connect(lambda level, msg: logs.append((level, msg)))

    session.move_filter(2)  # LP requested

    # The page resyncs the combo on filter_moved: it must name the slot the
    # wheel is on, and the wheel must not stay "busy".
    assert moved == [(1, "IR")]
    assert states[-1] == ("filterwheel", "connected", "IR")
    assert any(level == "ERROR" and "Filter move" in msg for level, msg in logs)
    assert not any(level == "CMD" for level, _ in logs)  # no "Filter → …" for a refused move

    # A wheel that cannot even be read back ends in error, never in "busy".
    wheel.get_position.side_effect = AlpacaError(0, "Timeout")
    wheel.position_name.side_effect = AlpacaError(0, "Timeout")
    moved.clear()
    states.clear()

    session.move_filter(2)

    assert moved == [(-1, "")]
    assert states[-1][:2] == ("filterwheel", "error")
