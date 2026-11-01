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


class _FakePoller:
    """Thread-less stand-in for MountPollingWorker / TemperaturePollingWorker."""

    def __init__(self, *_args, parent=None) -> None:
        self.running = False
        self.position_updated = MagicMock()
        self.error_occurred = MagicMock()
        self.connection_lost = MagicMock()
        self.temperature_updated = MagicMock()

    def start(self) -> None:
        self.running = True

    def isRunning(self) -> bool:  # noqa: N802 — QThread API
        return self.running

    def stop(self) -> None:
        self.running = False

    def wait(self, _ms: int = 0) -> bool:
        return True


def _fake_devices(monkeypatch, focuser_failures: int = 0) -> dict[str, list]:
    """Replace the four Alpaca device classes; record every handle created."""
    import argos.core.session.device_session as ds
    from argos.core.alpaca.client import AlpacaError

    created: dict[str, list] = {"mount": [], "camera": [], "filterwheel": [], "focuser": []}
    pollers: list[_FakePoller] = []

    def poller(*args, parent=None):
        p = _FakePoller(*args, parent=parent)
        pollers.append(p)
        return p

    def telescope(host, port):
        t = MagicMock(equatorial_system="J2000", clock_error_seconds=0.0, alignment_mode="Alt-Az")
        t.connect.return_value = "Seestar mount"
        created["mount"].append(t)
        return t

    def camera(host, port):
        c = MagicMock(
            gain_min=0,
            gain_max=600,
            exposure_min=0.01,
            exposure_max=600.0,
            offset_min=0,
            offset_max=300,
            max_bin=1,
        )
        c.connect.return_value = "Seestar camera"
        c.get_offset.return_value = 10
        created["camera"].append(c)
        return c

    def filterwheel(host, port):
        w = MagicMock()
        w.get_position.return_value = 1
        w.position_name.return_value = "IR"
        created["filterwheel"].append(w)
        return w

    def focuser(host, port):
        f = MagicMock(max_step=60_000, max_increment=1_000, absolute=True)
        if len(created["focuser"]) < focuser_failures:
            f.connect.side_effect = AlpacaError(0, "Timeout")
        else:
            f.connect.return_value = "Seestar focuser"
        f.get_position.return_value = 24_500
        created["focuser"].append(f)
        return f

    monkeypatch.setattr(ds, "Telescope", telescope)
    monkeypatch.setattr(ds, "Camera", camera)
    monkeypatch.setattr(ds, "FilterWheel", filterwheel)
    monkeypatch.setattr(ds, "Focuser", focuser)
    monkeypatch.setattr(ds, "MountPollingWorker", poller)
    monkeypatch.setattr(ds, "TemperaturePollingWorker", poller)
    monkeypatch.setattr(ds.DeviceSession, "_check_profile_against", lambda *_a: None)
    created["pollers"] = pollers
    return created


def test_connect_all_again_only_connects_what_is_not_connected(monkeypatch) -> None:
    """H2: "Connect equipment" stays enabled until all four devices are up;
    pressing it again (to retry a failed focuser) reconnected every device,
    leaked a second mount poller and dropped the camera without disconnect."""
    created = _fake_devices(monkeypatch, focuser_failures=1)
    session = DeviceSession(Config(dict(_DEFAULTS)))

    session.connect_all("192.168.1.20", 32323)
    assert session.focuser is None  # the first focuser connect failed
    first_camera = session.camera

    session.connect_all("192.168.1.20", 32323)  # the retry

    assert len(created["mount"]) == 1
    assert len(created["camera"]) == 1
    assert len(created["filterwheel"]) == 1
    assert len(created["focuser"]) == 2  # only the failed device is retried
    assert session.focuser is created["focuser"][1]
    assert session.camera is first_camera
    first_camera.disconnect.assert_not_called()
    mount_pollers = [p for p in created["pollers"] if p.position_updated.connect.called]
    assert len(mount_pollers) == 1 and mount_pollers[0].running


def test_restarting_the_mount_poller_stops_the_previous_one(monkeypatch) -> None:
    """H2: _start_polling started a new MountPollingWorker without stopping
    the running one, which kept emitting positions after a disconnect."""
    created = _fake_devices(monkeypatch)
    session = DeviceSession(Config(dict(_DEFAULTS)))
    session._telescope = MagicMock()

    session._start_polling()
    session._start_polling()

    first, second = created["pollers"]
    assert not first.running
    assert second.running
    session.disconnect_mount()
    assert not second.running


def test_mount_clock_error_message_says_what_happens(monkeypatch) -> None:
    """H4: the log said "GoTo and Sync are disabled" while Slew, Sync and
    Center stayed enabled; the Telescope guard refuses them on use."""
    import argos.core.session.device_session as ds

    def telescope(host, port):
        t = MagicMock(equatorial_system="J2000", clock_error_seconds=7200.0)
        t.connect.return_value = "Seestar mount"
        return t

    monkeypatch.setattr(ds, "Telescope", telescope)
    monkeypatch.setattr(ds.DeviceSession, "_start_polling", lambda self: None)
    session = DeviceSession(Config(dict(_DEFAULTS)))
    logs: list[tuple[str, str]] = []
    session.log_message.connect(lambda level, msg: logs.append((level, msg)))

    session.connect_mount("192.168.1.20", 32323)
    session._telescope = None  # the auto-reconnect path logs the same check
    session._retry_mount()

    clock = [msg for level, msg in logs if level == "ERROR" and "clock" in msg]
    assert len(clock) == 2
    for msg in clock:
        assert "2.0 h off" in msg
        assert "refused" in msg
        assert "disabled" not in msg


def test_connection_failures_carry_their_reason(monkeypatch) -> None:
    """H12: a lost mount showed a bare "Error" while it retried, and a
    connect error was cut to 48 characters (port and cause lost)."""
    import argos.core.session.device_session as ds
    from argos.core.alpaca.client import AlpacaError

    reason = (
        "Cannot connect to 192.168.1.20:32323 — HTTPConnectionPool: Max retries "
        "exceeded (Connection refused by the Seestar)"
    )

    def camera(host, port):
        c = MagicMock()
        c.connect.side_effect = AlpacaError(0, reason)
        return c

    monkeypatch.setattr(ds, "Camera", camera)
    session = DeviceSession(Config(dict(_DEFAULTS)))
    states: list[tuple[str, str, str]] = []
    session.device_state_changed.connect(lambda d, s, i: states.append((d, s, i)))

    session.connect_camera("192.168.1.20", 32323)
    assert states[-1] == ("camera", "error", f"Alpaca error 0: {reason}")
    assert len(states[-1][2]) > 100

    session._telescope = MagicMock()
    session._mount_endpoint = ("192.168.1.20", 32323)
    try:
        session._on_mount_lost()
    finally:
        session._mount_retry.stop()
    device, state, info = states[-1]
    assert (device, state) == ("mount", "error")
    assert "lost" in info and "retrying" in info
