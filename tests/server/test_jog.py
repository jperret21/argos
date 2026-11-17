"""Mount jog with the server dead-man (A30), tracking rate (A31), geometry (A29)."""

from __future__ import annotations

import time

import pytest

from argos.server.devices.base import DeviceError
from argos.server.devices.sim_mount import SimMount
from tests.server.conftest import AUTH, TOKEN, log_messages, science_client, status, wait_for


@pytest.fixture
def mount(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("mount",))
    assert client.post("/api/mount/unpark", headers=AUTH).status_code == 200
    return client


def _sim(client) -> SimMount:
    return client.app.state.hub._slots["mount"].handle


def _jog(http, axis="primary", rate=2.0, **extra):
    return http.post("/api/mount/jog", json={"axis": axis, "rate_deg_s": rate, **extra},
                     headers=AUTH)  # fmt: skip


def test_mount_record_carries_geometry_and_rates(mount):
    record = status(mount)["mount"]
    assert record["alignment"] == "eq_gem"
    assert record["tracking_rates"] == ["sidereal", "lunar", "solar", "king"]
    assert record["tracking_rate"] == "sidereal" and record["goto_blocked"] is None
    assert record["center_available"] is False
    assert record["jog"]["primary"] == 0.0 and record["jog"]["deadman_s"] == 0.3
    assert record["jog"]["max_rate_deg_s"] == 5.0


def test_jog_starts_renews_and_stops(mount):
    sim = _sim(mount)
    answer = _jog(mount, rate=2.0)
    assert answer.status_code == 200 and answer.json()["jog"]["primary"] == 2.0
    assert sim.axis_calls == [(0, 2.0)]
    _jog(mount, rate=2.0)  # renewal: no device call
    assert sim.axis_calls == [(0, 2.0)]
    stopped = mount.post("/api/mount/jog/stop", json={"axis": "primary"}, headers=AUTH).json()
    assert stopped["jog"]["primary"] == 0.0
    assert sim.axis_calls[-1] == (0, 0.0)


def test_the_dead_man_stops_an_axis_that_is_not_renewed(mount):
    sim = _sim(mount)
    _jog(mount, axis="secondary", rate=-1.0)
    time.sleep(0.15)
    _jog(mount, axis="secondary", rate=-1.0)  # renewed in time: still moving
    time.sleep(0.15)
    assert sim.axis_rates() == (0.0, -1.0)
    wait_for(lambda: sim.axis_rates() == (0.0, 0.0), timeout=2)
    record = status(mount)["mount"]["jog"]
    assert record["secondary"] == 0.0 and record["last_stop"]["reason"] == "no renewal"
    assert "Jog stopped by the server: no renewal for 0.3 s (secondary axis)." in log_messages(
        mount
    )


def test_a_diagonal_jog_stops_each_axis_on_its_own(mount):
    """H3: both axes are tracked; releasing one stops only that one."""
    sim = _sim(mount)
    _jog(mount, "primary", 1.0)
    _jog(mount, "secondary", 1.0)
    mount.post("/api/mount/jog/stop", json={"axis": "primary"}, headers=AUTH)
    assert sim.axis_rates() == (0.0, 1.0)
    mount.post("/api/mount/jog/stop", headers=AUTH)  # ■: both, whatever is believed
    assert sim.axis_rates() == (0.0, 0.0)
    assert (0, 0.0) in sim.axis_calls and (1, 0.0) in sim.axis_calls


def test_closing_the_event_socket_stops_its_jog(make_client, tmp_path):
    # A long dead-man, so only the socket can have stopped the axis.
    client = science_client(make_client, tmp_path, connect=("mount",), jog_deadman_s=30.0)
    client.post("/api/mount/unpark", headers=AUTH)
    sim = _sim(client)
    with client.websocket_connect(f"/ws/events?token={TOKEN}&client=tab-1") as events:
        events.receive_json()
        _jog(client, rate=3.0, client="tab-1")
        assert sim.axis_rates() == (3.0, 0.0)
    wait_for(lambda: sim.axis_rates() == (0.0, 0.0), timeout=3)
    assert any("the client's event socket closed" in m for m in log_messages(client))


def test_a_blur_message_stops_the_jog(mount):
    sim = _sim(mount)
    with mount.websocket_connect(f"/ws/events?token={TOKEN}&client=tab-2") as events:
        events.receive_json()
        _jog(mount, rate=-2.0, client="tab-2")
        events.send_json({"type": "jog_stop"})
        wait_for(lambda: sim.axis_rates() == (0.0, 0.0), timeout=2)
    assert any("the client left the window" in m for m in log_messages(mount))


def test_another_clients_socket_does_not_stop_this_jog(mount):
    sim = _sim(mount)
    _jog(mount, rate=1.0, client="tab-a")
    with mount.websocket_connect(f"/ws/events?token={TOKEN}&client=tab-b") as events:
        events.receive_json()
    time.sleep(0.1)
    assert sim.axis_rates() == (1.0, 0.0)
    mount.post("/api/mount/jog/stop", headers=AUTH)


def test_a_failed_stop_is_retried(mount, monkeypatch):
    sim = _sim(mount)
    real = SimMount.move_axis
    failures = {"left": 2}

    def flaky(self, axis, rate):
        if rate == 0.0 and failures["left"] > 0:
            failures["left"] -= 1
            raise DeviceError("network blip")
        return real(self, axis, rate)

    monkeypatch.setattr(SimMount, "move_axis", flaky)
    _jog(mount, rate=1.5)
    record = mount.post("/api/mount/jog/stop", json={"axis": "primary"}, headers=AUTH).json()
    assert record["jog"]["stop_pending"] == ["primary"]
    wait_for(lambda: sim.axis_rates() == (0.0, 0.0), timeout=4)
    wait_for(lambda: status(mount)["mount"]["jog"]["stop_pending"] == [], timeout=2)
    assert "Stop failed (primary axis): network blip — retrying." in log_messages(mount)


def test_a_stop_that_keeps_failing_says_to_use_abort(mount, monkeypatch):
    hub = mount.app.state.hub
    hub.jog._retry_s = 0.02
    real = SimMount.move_axis

    def broken(self, axis, rate):
        if rate == 0.0:
            raise DeviceError("no answer")
        return real(self, axis, rate)

    monkeypatch.setattr(SimMount, "move_axis", broken)
    _jog(mount, rate=1.0)
    mount.post("/api/mount/jog/stop", json={"axis": "primary"}, headers=AUTH)
    wait_for(
        lambda: any("use Abort on the Mount card" in m for m in log_messages(mount)), timeout=4
    )
    monkeypatch.setattr(SimMount, "move_axis", real)
    mount.post("/api/mount/stop", headers=AUTH)  # Abort stops the axes too


def test_jog_refusals(mount):
    assert _jog(mount, rate=0.0).status_code == 400
    assert _jog(mount, rate=6.0).status_code == 400
    assert _jog(mount, axis="tertiary").status_code == 400
    mount.post("/api/mount/park", headers=AUTH)
    wait_for(lambda: status(mount)["mount"]["state"] == "parked", timeout=5)
    parked = _jog(mount)
    assert parked.status_code == 409 and parked.json()["error"]["code"] == "parked"


def test_jog_is_refused_during_a_goto_slew(make_client, tmp_path):
    from argos.server.settings import SimOptions

    slow = SimOptions(width=160, height=120, n_stars=10, slew_rate_deg_s=0.5)
    client = science_client(make_client, tmp_path, connect=("mount",), sim=slow)
    client.post("/api/mount/unpark", headers=AUTH)
    client.post("/api/mount/goto", json={"ra_hours": 3.0, "dec_deg": 10.0}, headers=AUTH)
    busy = _jog(client)
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "busy"
    assert "Abort the slew before jogging" in busy.json()["error"]["message"]
    client.post("/api/mount/stop", headers=AUTH)


def test_an_older_command_of_a_client_is_ignored(mount):
    sim = _sim(mount)
    _jog(mount, rate=1.0, client="tab", seq=5)
    _jog(mount, rate=4.0, client="tab", seq=3)  # arrived late: ignored
    assert sim.axis_rates() == (1.0, 0.0)
    mount.post("/api/mount/jog/stop", json={"client": "tab", "seq": 6}, headers=AUTH)
    assert sim.axis_rates() == (0.0, 0.0)


def test_goto_park_and_abort_stop_a_jog_first(mount):
    sim = _sim(mount)
    _jog(mount, rate=1.0)
    mount.post("/api/mount/goto", json={"ra_hours": 5.0, "dec_deg": 20.0}, headers=AUTH)
    assert sim.axis_rates() == (0.0, 0.0)
    assert status(mount)["mount"]["jog"]["last_stop"]["reason"] == "GoTo"


def test_disconnecting_the_mount_forgets_the_jog(mount):
    _jog(mount, rate=1.0)
    mount.delete("/api/devices/mount", headers=AUTH)
    mount.post("/api/devices/mount/connect", json={"mode": "simulator"}, headers=AUTH)
    assert status(mount)["mount"]["jog"]["primary"] == 0.0


def test_jog_needs_a_mount(make_client, tmp_path):
    client = science_client(make_client, tmp_path)
    answer = _jog(client)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "not_connected"


# -- tracking rate (A31) and the clock guard (H4) --------------------------------------


def test_tracking_rate_is_set_and_read_back(mount):
    record = mount.post("/api/mount/tracking-rate", json={"rate": "lunar"}, headers=AUTH).json()
    assert record["tracking_rate"] == "lunar"
    assert _sim(mount).tracking_rate() == "lunar"
    assert "Tracking rate → lunar" in log_messages(mount)


def test_a_rate_the_driver_does_not_list_is_refused(mount):
    hub = mount.app.state.hub
    with hub._lock:
        hub._set_mount_extras(tracking_rates=("sidereal",))
    answer = mount.post("/api/mount/tracking-rate", json={"rate": "solar"}, headers=AUTH)
    assert answer.status_code == 400
    bad = mount.post("/api/mount/tracking-rate", json={"rate": "warp"}, headers=AUTH)
    assert bad.status_code == 400


def test_a_stale_mount_clock_blocks_goto(make_client, tmp_path, monkeypatch):
    monkeypatch.setattr(SimMount, "clock_error_s", 7200.0)
    client = science_client(make_client, tmp_path, connect=("mount",))
    blocked = status(client)["mount"]["goto_blocked"]
    assert blocked["reason"] == "clock" and blocked["clock_error_s"] == 7200.0
    client.post("/api/mount/unpark", headers=AUTH)
    answer = client.post("/api/mount/goto", json={"ra_hours": 1.0, "dec_deg": 5.0}, headers=AUTH)
    assert answer.status_code == 409 and answer.json()["error"]["code"] == "clock_error"
    assert "GoTo, Sync and Center will be refused" in answer.json()["error"]["message"]
    assert _sim(client).read().state != "slewing"


def test_disconnecting_the_mount_stops_its_axes_first(mount):
    sim = _sim(mount)
    _jog(mount, rate=1.0)
    _jog(mount, axis="secondary", rate=-1.0)
    mount.delete("/api/devices/mount", headers=AUTH)
    assert sim.axis_rates() == (0.0, 0.0)  # stopped before the handle was closed


# -- review of wave 3: admission, stop ordering, failed stops, two windows ------------


def test_a_stop_is_never_dropped_by_a_newer_renewal_of_the_other_axis(mount):
    """Numbers are per axis: releasing one key of a diagonal always stops it."""
    sim = _sim(mount)
    _jog(mount, "primary", 2.0, client="tab", seq=1)
    _jog(mount, "secondary", 2.0, client="tab", seq=2)
    _jog(mount, "primary", 2.0, client="tab", seq=5)  # renewal, processed first
    answer = mount.post(
        "/api/mount/jog/stop", json={"axis": "secondary", "client": "tab", "seq": 4}, headers=AUTH
    ).json()
    assert answer["jog"]["secondary"] == 0.0 and sim.axis_rates() == (2.0, 0.0)
    # ... and an older start of that axis, arriving after its stop, is ignored.
    late = _jog(mount, "secondary", 2.0, client="tab", seq=3).json()
    assert late["jog_command"] == {"outcome": "ignored", "why": "stale"}
    assert sim.axis_rates() == (2.0, 0.0)
    mount.post("/api/mount/jog/stop", headers=AUTH)


def test_a_renewal_never_restarts_an_axis_the_server_stopped(mount):
    sim = _sim(mount)
    assert _jog(mount, rate=1.0, client="tab", seq=1).json()["jog_command"]["outcome"] == "started"
    renewed = _jog(mount, rate=1.0, client="tab", seq=2, renew=True).json()
    assert renewed["jog_command"]["outcome"] == "renewed"
    wait_for(lambda: sim.axis_rates() == (0.0, 0.0), timeout=2)  # dead-man
    calls = len(sim.axis_calls)
    late = _jog(mount, rate=1.0, client="tab", seq=3, renew=True).json()
    assert late["jog_command"] == {"outcome": "ignored", "why": "stopped"}
    assert len(sim.axis_calls) == calls and sim.axis_rates() == (0.0, 0.0)
    # A fresh press (no renew flag) starts it again.
    assert _jog(mount, rate=1.0, client="tab", seq=4).json()["jog_command"]["outcome"] == "started"
    mount.post("/api/mount/jog/stop", headers=AUTH)


def test_renewals_never_wait_behind_a_slow_moveaxis(mount, monkeypatch):
    """A slow driver must not pile renewals up in the request threads (review)."""
    import threading

    real = SimMount.move_axis
    gate = threading.Event()

    def slow(self, axis, rate):
        if rate != 0.0:
            gate.wait(2.0)
        return real(self, axis, rate)

    monkeypatch.setattr(SimMount, "move_axis", slow)
    hub = mount.app.state.hub
    starter = threading.Thread(target=lambda: hub.mount_jog("primary", 2.0, client="t", seq=1))
    starter.start()
    wait_for(lambda: "primary" in hub.jog._starting, timeout=2)
    t0 = time.monotonic()
    answer = hub.mount_jog("primary", 2.0, client="t", seq=2, renew=True)
    assert time.monotonic() - t0 < 0.2
    assert answer["jog_command"]["outcome"] == "pending"
    gate.set()
    starter.join(3)
    assert _sim(mount).axis_rates() == (2.0, 0.0)
    mount.post("/api/mount/jog/stop", headers=AUTH)


def test_a_start_that_waited_longer_than_the_dead_man_is_dropped(mount, monkeypatch):
    import threading

    real = SimMount.move_axis

    def slow(self, axis, rate):
        if axis == 0 and rate != 0.0:
            time.sleep(0.5)  # longer than the 0.3 s dead-man of the tests
        return real(self, axis, rate)

    monkeypatch.setattr(SimMount, "move_axis", slow)
    hub = mount.app.state.hub
    starter = threading.Thread(target=lambda: hub.mount_jog("primary", 1.0, client="a", seq=1))
    starter.start()
    wait_for(lambda: "primary" in hub.jog._starting, timeout=2)
    late = hub.mount_jog("secondary", 1.0, client="a", seq=2)
    assert late["jog_command"] == {"outcome": "ignored", "why": "late"}
    starter.join(3)
    assert _sim(mount).axis_rates()[1] == 0.0
    mount.post("/api/mount/jog/stop", headers=AUTH)


def test_another_window_cannot_reverse_a_jogging_axis(mount):
    sim = _sim(mount)
    _jog(mount, rate=2.0, client="tab-a", seq=1)
    other = _jog(mount, rate=-2.0, client="tab-b", seq=1)
    assert other.status_code == 409 and other.json()["error"]["owner"] == "jog"
    assert sim.axis_rates() == (2.0, 0.0)
    # The other axis is free, and the ■ stop of any window stops everything.
    assert _jog(mount, "secondary", 1.0, client="tab-b", seq=2).status_code == 200
    mount.post("/api/mount/jog/stop", json={"client": "tab-b", "seq": 3}, headers=AUTH)
    assert sim.axis_rates() == (0.0, 0.0)


def test_a_stop_that_keeps_failing_stays_pending_and_is_never_a_dead_man_stop(mount, monkeypatch):
    hub = mount.app.state.hub
    hub.jog._retry_s = 0.02
    real = SimMount.move_axis

    def broken(self, axis, rate):
        if rate == 0.0:
            raise DeviceError("no answer")
        return real(self, axis, rate)

    monkeypatch.setattr(SimMount, "move_axis", broken)
    _jog(mount, rate=1.0)
    mount.post("/api/mount/jog/stop", json={"axis": "primary"}, headers=AUTH)
    wait_for(lambda: status(mount)["mount"]["jog"]["stop_failed"] == ["primary"], timeout=4)
    time.sleep(0.6)  # beyond the dead-man: no "no renewal" stop for a failed stop
    record = status(mount)["mount"]["jog"]
    assert record["stop_pending"] == ["primary"] and record["stop_failed"] == ["primary"]
    messages = log_messages(mount)
    assert not any("no renewal" in m for m in messages)
    assert sum("use Abort on the Mount card" in m for m in messages) == 1
    monkeypatch.setattr(SimMount, "move_axis", real)
    mount.post("/api/mount/stop", headers=AUTH)  # Abort: the stop goes through
    record = status(mount)["mount"]["jog"]
    assert record["stop_pending"] == [] and record["stop_failed"] == []
    assert "Stop confirmed (primary axis)." in log_messages(mount)
