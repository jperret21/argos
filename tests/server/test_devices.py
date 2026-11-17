"""Per-device connection (API 2, rows A13-A15) with fakes: no hardware, no network.

Covers connect / disconnect / retry per device, connect-all skipping what is
already connected, the one-link rule, full error texts, the derived v1
connection record, the mount's lost-connection auto-retry, and connects that
are superseded by a disconnect.
"""

from __future__ import annotations

import threading
import time

import pytest

from argos.core.alpaca.client import AlpacaError
from argos.core.alpaca.telescope import MountPosition
from argos.server.devices import alpaca as adapter
from argos.server.devices.sim_mount import SimMount
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until, wait_for

SEESTAR = {"mode": "alpaca", "host": "10.0.0.1", "port": 32323}
LONG_ERROR = (
    "Cannot connect to 10.0.0.1:32323 — HTTPConnectionPool(host='10.0.0.1', port=32323): "
    "Max retries exceeded (Caused by ConnectTimeoutError)"
)


class FakeTelescope:
    instances = 0
    fail: str | None = None
    gate: threading.Event | None = None  # connect blocks until set
    closed = 0

    def __init__(self, host, port):
        FakeTelescope.instances += 1

    def connect(self):
        if FakeTelescope.gate is not None:
            FakeTelescope.gate.wait(5)
        if FakeTelescope.fail:
            raise AlpacaError(0, FakeTelescope.fail)
        return "Seestar S30 Pro"

    equatorial_system = "Topocentric"
    clock_error_seconds = 7200.0  # two hours off: a warning the UI must show

    def get_position(self):
        return MountPosition(
            ra=5.5, dec=22.0, altitude=40.0, azimuth=120.0, tracking=False, slewing=False
        )

    def is_parked(self):
        return False

    def side_of_pier(self):
        return None

    def disconnect(self):
        FakeTelescope.closed += 1


class FakeCamera:
    instances = 0
    fail: str | None = None

    def __init__(self, host, port):
        FakeCamera.instances += 1
        self.width, self.height = 1920, 1080
        self.gain_min, self.gain_max = 0, 600
        self.exposure_min, self.exposure_max = 0.001, 600.0
        self.max_bin = 1

    def connect(self):
        if FakeCamera.fail:
            raise AlpacaError(0, FakeCamera.fail)
        return "Seestar S30 Camera"

    def get_sensor_metadata(self):
        return {"sensor_type": 2}

    def get_offset(self):
        return None

    def disconnect(self):
        pass


class FakeFilterWheel:
    instances = 0

    def __init__(self, host, port):
        FakeFilterWheel.instances += 1

    def connect(self):
        pass

    def position_name(self):
        return "IR"

    def disconnect(self):
        pass


class FakeFocuser:
    instances = 0
    fail: str | None = None

    def __init__(self, host, port):
        FakeFocuser.instances += 1

    def connect(self):
        if FakeFocuser.fail:
            raise AlpacaError(0, FakeFocuser.fail)
        return "Seestar Focuser"

    def get_position(self):
        return 1234

    def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    for fake in (FakeTelescope, FakeCamera, FakeFilterWheel, FakeFocuser):
        fake.instances = 0
        fake.fail = None
    FakeTelescope.gate = None
    FakeTelescope.closed = 0
    monkeypatch.setattr(adapter, "Telescope", FakeTelescope)
    monkeypatch.setattr(adapter, "Camera", FakeCamera)
    monkeypatch.setattr(adapter, "FilterWheel", FakeFilterWheel)
    monkeypatch.setattr(adapter, "Focuser", FakeFocuser)


def _devices(client) -> dict:
    return client.get("/api/devices", headers=AUTH).json()


def test_status_and_devices_start_disconnected(client):
    status = client.get("/api/status", headers=AUTH).json()
    assert set(status) >= {"connection", "camera", "mount", "devices", "profile"}
    assert set(status["devices"]) == {"mount", "camera", "filterwheel", "focuser"}
    for record in status["devices"].values():
        assert record["state"] == "disconnected"
        assert set(record) == {
            "state", "name", "info", "error", "retrying", "warnings", "link", "since"
        }  # fmt: skip
        assert record["since"].endswith("Z")
    assert status["profile"] == {"key": "s30pro", "name": "ZWO Seestar S30 Pro", "validated": True}


def test_connect_one_device_then_disconnect(client):
    response = client.post("/api/devices/focuser/connect", json=SEESTAR, headers=AUTH)
    assert response.status_code == 200, response.text
    focuser = response.json()["focuser"]
    assert focuser["state"] == "connected"
    assert focuser["name"] == focuser["info"] == "Seestar Focuser"
    assert focuser["link"] == SEESTAR
    assert response.json()["mount"]["state"] == "disconnected"  # only that device
    # v1 record: neither camera nor mount, so still disconnected.
    assert client.get("/api/status", headers=AUTH).json()["connection"]["state"] == "disconnected"

    response = client.delete("/api/devices/focuser", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["focuser"]["state"] == "disconnected"
    assert response.json()["focuser"]["link"] is None
    again = client.delete("/api/devices/focuser", headers=AUTH)  # idempotent
    assert again.status_code == 200


def test_connect_uses_the_configured_address_and_remembers_a_new_one(client):
    response = client.post("/api/devices/mount/connect", json={}, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "invalid_argument",
        "message": "Enter the Seestar address first",
    }
    # A connect with an explicit address writes it to the config (Qt did).
    client.post("/api/devices/filterwheel/connect", json=SEESTAR, headers=AUTH)
    values = client.get("/api/config", headers=AUTH).json()["values"]
    assert values["alpaca.host"] == "10.0.0.1" and values["alpaca.port"] == 32323
    # Without a body, the configured address is used.
    response = client.post("/api/devices/focuser/connect", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["focuser"]["link"] == SEESTAR


def test_unknown_device_is_404_and_body_is_strict(client):
    assert client.post("/api/devices/dome/connect", json=SEESTAR, headers=AUTH).status_code == 404
    assert client.delete("/api/devices/dome", headers=AUTH).status_code == 404
    bad = client.post("/api/devices/mount/connect", json={**SEESTAR, "port": "32323"}, headers=AUTH)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_argument"


def test_failure_keeps_the_full_error_text_and_retry_works(client):
    FakeFocuser.fail = LONG_ERROR
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        response = client.post("/api/devices/focuser/connect", json=SEESTAR, headers=AUTH)
        seen: list[dict] = []
        receive_until(events, lambda m: m["type"] == "log" and m["level"] == "error", seen=seen)
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "connection_failed"
    assert error["message"] == f"Alpaca error 0: {LONG_ERROR}"  # not cut to 48 characters
    focuser = _devices(client)["focuser"]
    assert focuser["state"] == "error"
    assert focuser["error"] == focuser["info"] == error["message"]
    log = seen[-1]
    assert log["message"] == f"Focuser: {error['message']}"
    assert log["source"] == "focuser" and log["topic"] == "connection"
    states = [m["devices"]["focuser"]["state"] for m in seen if m["type"] == "devices"]
    assert states == ["connecting", "error"]

    FakeFocuser.fail = None  # "Retry" is the same request again
    response = client.post("/api/devices/focuser/connect", json=SEESTAR, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["focuser"]["state"] == "connected"
    assert response.json()["focuser"]["error"] is None


def test_mount_connect_reports_clock_and_coordinate_warnings(client):
    client.post("/api/devices/mount/connect", json=SEESTAR, headers=AUTH)
    mount = _devices(client)["mount"]
    assert mount["state"] == "connected" and mount["name"] == "Seestar S30 Pro"
    assert mount["warnings"] == [
        # H4 (0.5.0): the message says what is refused (device_session.py:377-382).
        "Mount clock is 2.0 h off — correct the date/time in the Seestar app, then "
        "reconnect. GoTo, Sync and Center will be refused until then."
    ]
    messages = [e["message"] for e in client.get("/api/logs", headers=AUTH).json()["entries"]]
    assert "Mount connected: Seestar S30 Pro" in messages
    assert "Mount coordinates: Topocentric → Argos J2000 conversion enabled." in messages


def test_camera_profile_mismatch_is_a_device_warning(client):
    client.post("/api/devices/camera/connect", json=SEESTAR, headers=AUTH)
    camera = _devices(client)["camera"]
    assert camera["state"] == "connected"
    # A 1920×1080 driver under the S30 Pro profile (3840×2160): advisory only.
    assert camera["warnings"][0] == (
        "Profile mismatch — driver reports 1920×1080, profile s30pro expects 3840×2160"
    )
    assert client.get("/api/profiles", headers=AUTH).json()["active"] == "s30pro"


def test_connect_all_order_and_skip_of_connected_devices(client):
    client.post("/api/devices/mount/connect", json=SEESTAR, headers=AUTH)
    assert FakeTelescope.instances == 1
    polls_before = [t.name for t in threading.enumerate()].count("argos-mount-poll")
    response = client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
    assert response.status_code == 200
    assert {k: v["state"] for k, v in response.json().items()} == {
        "mount": "connected",
        "camera": "connected",
        "filterwheel": "connected",
        "focuser": "connected",
    }
    # The connected mount was skipped: no second handle, no second poller (02 P: Qt
    # connect_all started a second MountPollingWorker).
    assert FakeTelescope.instances == 1
    assert [t.name for t in threading.enumerate()].count("argos-mount-poll") == polls_before == 1
    again = client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
    assert again.status_code == 200
    assert (FakeTelescope.instances, FakeCamera.instances) == (1, 1)
    assert FakeFilterWheel.instances == FakeFocuser.instances == 1
    status = client.get("/api/status", headers=AUTH).json()
    assert status["connection"] == {
        "state": "connected",
        "mode": "alpaca",
        "device_name": "Seestar S30 Pro",
        "message": None,
    }


def test_connect_all_carries_on_after_a_failure(client):
    FakeCamera.fail = "camera refused"
    response = client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
    assert response.status_code == 200
    states = {k: v["state"] for k, v in response.json().items()}
    assert states == {
        "mount": "connected",
        "camera": "error",
        "filterwheel": "connected",
        "focuser": "connected",
    }
    assert response.json()["camera"]["error"] == "Alpaca error 0: camera refused"


def test_disconnect_all_releases_everything(client):
    client.post("/api/devices/connect-all", json={"mode": "simulator"}, headers=AUTH)
    client.post("/api/camera/live", json={"exposure_s": 0.05, "gain": 80}, headers=AUTH)
    assert _devices(client)["camera"]["state"] == "busy"  # live view
    response = client.delete("/api/devices", headers=AUTH)
    assert response.status_code == 200
    assert {v["state"] for v in response.json().values()} == {"disconnected"}
    status = client.get("/api/status", headers=AUTH).json()
    assert status["camera"]["state"] == "idle" and status["camera"]["sensor"] is None
    assert status["connection"]["state"] == "disconnected"
    assert "argos-mount-poll" not in [t.name for t in threading.enumerate()]


def test_one_link_at_a_time(client):
    client.post("/api/devices/focuser/connect", json={"mode": "simulator"}, headers=AUTH)
    for path in ("/api/devices/mount/connect", "/api/devices/connect-all", "/api/connection"):
        response = client.post(path, json=SEESTAR, headers=AUTH)
        assert response.status_code == 409, path
        assert response.json()["error"]["code"] == "busy"
        assert "simulator" in response.json()["error"]["message"]
    assert FakeTelescope.instances == 0


def test_simulator_has_four_devices_and_v1_view_of_them(client):
    response = client.post("/api/devices/connect-all", json={"mode": "simulator"}, headers=AUTH)
    devices = response.json()
    # Wave 3: the simulated wheel starts on the first light slot (the Qt form's IR).
    assert devices["filterwheel"]["info"] == "IR"
    assert devices["focuser"]["name"] == "ARGOS Simulator focuser"
    connection = client.get("/api/status", headers=AUTH).json()["connection"]
    assert connection["device_name"] == "ARGOS Simulator (Seestar S50)"
    # The v1 routes see the same devices.
    capture = client.post(
        "/api/camera/capture", json={"exposure_s": 0.01, "gain": 80}, headers=AUTH
    )
    assert capture.status_code == 200
    again = client.post("/api/connection", json={"mode": "simulator"}, headers=AUTH)
    assert again.status_code == 200 and again.json()["state"] == "connected"


def test_busy_is_derived_from_a_slewing_mount(client):
    client.post("/api/devices/mount/connect", json={"mode": "simulator"}, headers=AUTH)
    client.post("/api/mount/unpark", headers=AUTH)
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        client.post("/api/mount/goto", json={"ra_hours": 3.0, "dec_deg": 10.0}, headers=AUTH)
        busy = receive_until(
            events, lambda m: m["type"] == "devices" and m["devices"]["mount"]["state"] == "busy"
        )
    assert busy["devices"]["mount"]["info"] == "slewing"


def test_disconnect_while_connecting_wins(client):
    FakeTelescope.gate = threading.Event()
    answers: list = []
    worker = threading.Thread(
        target=lambda: answers.append(
            client.post("/api/devices/mount/connect", json=SEESTAR, headers=AUTH)
        )
    )
    worker.start()
    wait_for(lambda: _devices(client)["mount"]["state"] == "connecting")
    started = time.monotonic()
    response = client.delete("/api/devices/mount", headers=AUTH)
    assert time.monotonic() - started < 1.0  # never waits for the hung connect
    assert response.json()["mount"]["state"] == "disconnected"
    FakeTelescope.gate.set()
    worker.join(5)
    assert answers[0].status_code == 409
    assert answers[0].json()["error"]["code"] == "not_connected"
    assert _devices(client)["mount"]["state"] == "disconnected"
    assert FakeTelescope.closed == 1  # the late handle was closed, not leaked


def test_disconnect_all_cancels_a_running_connect_all(client):
    """Disconnect all during Connect all: the device being opened is dropped and
    the devices after it are not connected (integration bug found in wave 1)."""
    FakeTelescope.gate = threading.Event()
    answers: list = []
    worker = threading.Thread(
        target=lambda: answers.append(
            client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
        )
    )
    worker.start()
    try:
        wait_for(lambda: _devices(client)["mount"]["state"] == "connecting")
        response = client.delete("/api/devices", headers=AUTH)
        assert {v["state"] for v in response.json().values()} == {"disconnected"}
    finally:
        FakeTelescope.gate.set()
        worker.join(5)
    assert answers[0].status_code == 200
    assert {v["state"] for v in answers[0].json().values()} == {"disconnected"}
    assert FakeCamera.instances == FakeFilterWheel.instances == FakeFocuser.instances == 0
    assert {v["state"] for v in _devices(client).values()} == {"disconnected"}


def test_a_device_cancel_during_connect_all_lets_the_others_connect(client):
    """The row's Cancel releases that device only: Connect all carries on."""
    FakeTelescope.gate = threading.Event()
    answers: list = []
    worker = threading.Thread(
        target=lambda: answers.append(
            client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
        )
    )
    worker.start()
    try:
        wait_for(lambda: _devices(client)["mount"]["state"] == "connecting")
        client.delete("/api/devices/mount", headers=AUTH)
    finally:
        FakeTelescope.gate.set()
        worker.join(5)
    states = {k: v["state"] for k, v in answers[0].json().items()}
    assert states == {
        "mount": "disconnected",
        "camera": "connected",
        "filterwheel": "connected",
        "focuser": "connected",
    }


def test_a_second_identical_connect_waits_for_the_first(client):
    FakeTelescope.gate = threading.Event()
    answers: list = []

    def post():
        answers.append(client.post("/api/devices/mount/connect", json=SEESTAR, headers=AUTH))

    workers = [threading.Thread(target=post) for _ in range(2)]
    for worker in workers:
        worker.start()
    wait_for(lambda: _devices(client)["mount"]["state"] == "connecting")
    time.sleep(0.1)
    FakeTelescope.gate.set()
    for worker in workers:
        worker.join(5)
    assert [a.status_code for a in answers] == [200, 200]
    assert FakeTelescope.instances == 1


def test_other_devices_connect_while_one_hangs(client):
    """Per-device connects are independent: a hung mount does not hold the focuser."""
    FakeTelescope.gate = threading.Event()
    worker = threading.Thread(
        target=lambda: client.post("/api/devices/mount/connect", json=SEESTAR, headers=AUTH)
    )
    worker.start()
    try:
        wait_for(lambda: _devices(client)["mount"]["state"] == "connecting")
        started = time.monotonic()
        response = client.post("/api/devices/focuser/connect", json=SEESTAR, headers=AUTH)
        assert response.status_code == 200
        assert time.monotonic() - started < 1.0
        assert response.json()["mount"]["state"] == "connecting"
    finally:
        FakeTelescope.gate.set()
        worker.join(5)


# -- Mount connection lost: auto-retry every N s (device_session.py:155-160, 557-567) ----


@pytest.fixture
def retrying(make_client, monkeypatch):
    """A simulator whose mount stops answering, with fast loss and retry timings."""
    client = make_client(mount_lost_after=2, mount_retry_s=0.1)
    state = {"read_fails": False, "open_fails": False, "opens": 0}
    original_read, original_init = SimMount.read, SimMount.__init__

    def read(self):
        if state["read_fails"]:
            raise OSError("no route to host")
        return original_read(self)

    def init(self, *args, **kwargs):
        state["opens"] += 1
        if state["open_fails"]:
            raise OSError("Cannot reach the mount")
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(SimMount, "read", read)
    monkeypatch.setattr(SimMount, "__init__", init)
    client.post("/api/devices/mount/connect", json={"mode": "simulator"}, headers=AUTH)
    return client, state


def test_lost_mount_retries_then_reconnects(retrying):
    client, state = retrying
    state["read_fails"] = state["open_fails"] = True
    mount = wait_for(lambda: (m := _devices(client)["mount"])["retrying"] and m, timeout=5)
    assert mount["state"] == "error" and mount["error"] == "Connection lost"
    assert mount["link"] == {"mode": "simulator", "host": None, "port": None}
    wait_for(lambda: state["opens"] >= 3)  # attempts keep coming, every 0.1 s
    state["read_fails"] = state["open_fails"] = False
    mount = wait_for(lambda: (m := _devices(client)["mount"])["state"] == "connected" and m)
    assert mount["retrying"] is False and mount["error"] is None
    messages = [e["message"] for e in client.get("/api/logs", headers=AUTH).json()["entries"]]
    assert "Mount connection lost." in messages
    assert "Retrying the mount every 0.1s — disconnect to stop." in messages
    assert "Mount reconnected: ARGOS mount simulator" in messages
    # The new session polls again (one poller).
    assert [t.name for t in threading.enumerate()].count("argos-mount-poll") == 1


def test_stop_retrying_is_a_disconnect(retrying):
    client, state = retrying
    state["read_fails"] = state["open_fails"] = True
    wait_for(lambda: _devices(client)["mount"]["retrying"], timeout=5)
    # The profile stays locked while the mount may come back.
    assert client.put("/api/profile", json={"key": "s50"}, headers=AUTH).status_code == 409
    response = client.delete("/api/devices/mount", headers=AUTH)
    assert response.json()["mount"] == {
        **response.json()["mount"],
        "state": "disconnected",
        "retrying": False,
        "error": None,
    }
    attempts = state["opens"]
    time.sleep(0.4)
    assert state["opens"] == attempts  # no attempt after "Stop retrying"
    assert "argos-mount-retry" not in [t.name for t in threading.enumerate()]


# -- Connect all claims its devices before the address check (wave 1 review) ------------


@pytest.fixture
def gated_precheck(make_client, monkeypatch):
    """A client whose Alpaca address check blocks until the test opens the gate."""
    from argos.server.hub import Hub

    gate = threading.Event()
    entered = threading.Event()

    def precheck(self, host, port):
        entered.set()
        gate.wait(5)

    monkeypatch.setattr(Hub, "_precheck", precheck)
    client = make_client()
    yield client, gate, entered
    gate.set()


def _connect_all_in_background(client, answers: list) -> threading.Thread:
    worker = threading.Thread(
        target=lambda: answers.append(
            client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
        )
    )
    worker.start()
    return worker


def test_connect_all_claims_every_device_during_the_address_check(gated_precheck):
    """While the address is checked the run is visible, locks the profile and is
    cancellable: the devices are `connecting` with info "queued" (they were
    `disconnected`, and Disconnect all looked like it had nothing to stop)."""
    client, gate, entered = gated_precheck
    answers: list = []
    worker = _connect_all_in_background(client, answers)
    try:
        assert entered.wait(5)
        devices = _devices(client)
        assert {d["state"] for d in devices.values()} == {"connecting"}
        assert {d["info"] for d in devices.values()} == {"queued"}
        assert {tuple(sorted(d["link"].items())) for d in devices.values()} == {
            tuple(sorted(SEESTAR.items()))
        }
        refused = client.put("/api/profile", json={"key": "s50"}, headers=AUTH)
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "busy"
        assert client.get("/api/profiles", headers=AUTH).json()["locked"] is True
    finally:
        gate.set()
        worker.join(5)
    assert answers[0].status_code == 200
    assert {d["state"] for d in answers[0].json().values()} == {"connected"}
    assert {d["info"] for d in answers[0].json().values()} != {"queued"}


def test_disconnect_all_during_the_address_check_cancels_connect_all(gated_precheck):
    client, gate, entered = gated_precheck
    answers: list = []
    worker = _connect_all_in_background(client, answers)
    try:
        assert entered.wait(5)
        response = client.delete("/api/devices", headers=AUTH)
        assert {d["state"] for d in response.json().values()} == {"disconnected"}
    finally:
        gate.set()
        worker.join(5)
    assert {d["state"] for d in answers[0].json().values()} == {"disconnected"}
    assert FakeTelescope.instances == FakeCamera.instances == 0
    assert FakeFilterWheel.instances == FakeFocuser.instances == 0
    # Never opened: no "<Device> disconnected." line for the queued devices.
    messages = [e["message"] for e in client.get("/api/logs", headers=AUTH).json()["entries"]]
    assert not [m for m in messages if m.endswith("disconnected.")]


def test_a_queued_device_released_during_connect_all_is_not_opened(gated_precheck):
    client, gate, entered = gated_precheck
    answers: list = []
    worker = _connect_all_in_background(client, answers)
    try:
        assert entered.wait(5)
        client.delete("/api/devices/camera", headers=AUTH)  # the row's Cancel
    finally:
        gate.set()
        worker.join(5)
    states = {k: v["state"] for k, v in answers[0].json().items()}
    assert states == {
        "mount": "connected",
        "camera": "disconnected",
        "filterwheel": "connected",
        "focuser": "connected",
    }
    assert FakeCamera.instances == 0


def test_queued_devices_go_connecting_one_at_a_time_in_order(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
        seen: list[dict] = []
        receive_until(
            events,
            lambda m: m["type"] == "devices" and m["devices"]["focuser"]["state"] == "connected",
            seen=seen,
        )
    snapshots = [m["devices"] for m in seen if m["type"] == "devices"]
    # First event: all four claimed and queued, none opened yet.
    assert {d["state"] for d in snapshots[0].values()} == {"connecting"}
    assert {d["info"] for d in snapshots[0].values()} == {"queued"}
    # Then each one leaves the queue (info None) in CONNECT_ORDER.
    opened = []
    for snap in snapshots[1:]:
        for dev in ("mount", "camera", "filterwheel", "focuser"):
            if snap[dev]["state"] == "connecting" and snap[dev]["info"] is None:
                if dev not in opened:
                    opened.append(dev)
    assert opened == ["mount", "camera", "filterwheel", "focuser"]


# -- Activity: every outcome replaces "… in progress" (wave 1 design review) ------------


def _activity(client) -> str:
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        for _ in range(4):
            message = receive_json(events)
            if message["type"] == "activity":
                return message["text"]
    raise AssertionError("no activity replayed")


def test_activity_reports_each_outcome(client):
    client.post("/api/devices/focuser/connect", json=SEESTAR, headers=AUTH)
    assert _activity(client) == "Focuser connected"
    client.delete("/api/devices/focuser", headers=AUTH)
    assert _activity(client) == "Focuser disconnected"
    FakeCamera.fail = "camera refused"
    client.post("/api/devices/camera/connect", json=SEESTAR, headers=AUTH)
    assert _activity(client) == "Camera: Alpaca error 0: camera refused"
    client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
    assert _activity(client) == "3 of 4 devices ready · camera failed"
    FakeCamera.fail = None
    client.post("/api/devices/connect-all", json=SEESTAR, headers=AUTH)
    assert _activity(client) == "Equipment ready"
    client.delete("/api/devices", headers=AUTH)
    assert _activity(client) == "Disconnected"


def test_activity_reports_the_end_of_a_capture_and_of_a_slew(client):
    client.post("/api/devices/connect-all", json={"mode": "simulator"}, headers=AUTH)
    client.post("/api/camera/capture", json={"exposure_s": 0.01, "gain": 80}, headers=AUTH)
    wait_for(lambda: client.get("/api/status", headers=AUTH).json()["camera"]["state"] == "idle")
    assert _activity(client).startswith("Frame #")
    client.post("/api/mount/unpark", headers=AUTH)
    client.post("/api/mount/goto", json={"ra_hours": 3.0, "dec_deg": 10.0}, headers=AUTH)
    wait_for(lambda: client.get("/api/status", headers=AUTH).json()["mount"]["state"] != "slewing")
    assert _activity(client) == "Slew finished"
    client.post("/api/mount/goto", json={"ra_hours": 15.0, "dec_deg": -10.0}, headers=AUTH)
    client.post("/api/mount/stop", headers=AUTH)
    wait_for(lambda: client.get("/api/status", headers=AUTH).json()["mount"]["state"] != "slewing")
    assert _activity(client) == "Slew stopped"
