"""The Alpaca adapters, with the core Camera/Telescope replaced by fakes.

No hardware and no network: this checks the mapping onto the contract
(states, pier side, parked refusals, error surfacing, the exposure loop).
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from argos.core.alpaca.client import AlpacaError
from argos.core.alpaca.telescope import MountPosition
from argos.server.devices import alpaca as adapter
from tests.server.conftest import AUTH, TOKEN, decode_frame, receive_bytes, wait_for

ALPACA = {"mode": "alpaca", "host": "10.0.0.1", "port": 32323}


class FakeCamera:
    fail_connect = False
    fail_download = False

    def __init__(self, host, port):
        self.width, self.height = 8, 6
        self._ready_at = None
        self.gains: list[int] = []

    def connect(self):
        if FakeCamera.fail_connect:
            raise AlpacaError(0, "Cannot connect to 10.0.0.1:32323")
        return "Seestar S50 Camera"

    def get_sensor_metadata(self):
        return {"sensor_type": 2}  # RGGB-family colour sensor

    def set_gain(self, gain):
        self.gains.append(gain)

    def start_exposure(self, duration, light=True):
        self._ready_at = time.monotonic() + duration

    def is_image_ready(self):
        return self._ready_at is not None and time.monotonic() >= self._ready_at

    def get_image_array(self):
        if FakeCamera.fail_download:
            raise AlpacaError(1279, "download failed")
        frame = np.arange(48, dtype=np.uint16).reshape(6, 8)
        return frame

    def stop_exposure(self):
        self._ready_at = None

    def disconnect(self):
        pass


class FakeTelescope:
    parked = False

    def __init__(self, host, port):
        self.calls: list[tuple] = []

    def connect(self):
        return "Seestar S50"

    def get_position(self):
        return MountPosition(
            ra=5.5, dec=22.0, altitude=40.0, azimuth=120.0, tracking=True, slewing=False
        )

    def is_parked(self):
        return FakeTelescope.parked

    def side_of_pier(self):
        return "WEST"

    def slew_to(self, ra, dec):
        self.calls.append(("slew_to", ra, dec))

    def abort_slew(self):
        self.calls.append(("abort_slew",))

    def park(self):
        self.calls.append(("park",))

    def unpark(self):
        self.calls.append(("unpark",))

    def set_tracking(self, enabled):
        self.calls.append(("set_tracking", enabled))

    def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    FakeCamera.fail_connect = FakeCamera.fail_download = False
    FakeTelescope.parked = False
    monkeypatch.setattr(adapter, "Camera", FakeCamera)
    monkeypatch.setattr(adapter, "Telescope", FakeTelescope)


def test_connect_maps_names_sensor_and_mount(client):
    response = client.post("/api/connection", json=ALPACA, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "state": "connected",
        "mode": "alpaca",
        "device_name": "Seestar S50",
        "message": None,
    }
    status = client.get("/api/status", headers=AUTH).json()
    assert status["camera"]["sensor"] == {"width": 8, "height": 6, "bitpix": 16, "bayer": "GRBG"}
    assert status["mount"]["state"] == "tracking"
    assert status["mount"]["pier_side"] == "west"
    assert status["mount"]["alt_deg"] == 40.0


def test_connect_failure_is_502_and_error_state(client):
    FakeCamera.fail_connect = True
    response = client.post("/api/connection", json=ALPACA, headers=AUTH)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "connection_failed"
    connection = client.get("/api/status", headers=AUTH).json()["connection"]
    assert connection["state"] == "error"
    assert "Cannot connect" in connection["message"]


def test_capture_runs_the_alpaca_exposure_loop(client):
    client.post("/api/connection", json=ALPACA, headers=AUTH)
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        client.post("/api/camera/capture", json={"exposure_s": 0.05, "gain": 42}, headers=AUTH)
        header, pixels = decode_frame(receive_bytes(frames))
    assert header["source"] == "alpaca"
    np.testing.assert_array_equal(pixels, np.arange(48, dtype=np.uint16).reshape(6, 8))


def test_download_failure_sets_camera_error(client):
    client.post("/api/connection", json=ALPACA, headers=AUTH)
    FakeCamera.fail_download = True
    client.post("/api/camera/capture", json={"exposure_s": 0.01, "gain": 80}, headers=AUTH)
    wait_for(lambda: client.get("/api/status", headers=AUTH).json()["camera"]["state"] == "error")


def test_parked_mount_refuses_goto_with_parked_code(client):
    client.post("/api/connection", json=ALPACA, headers=AUTH)
    FakeTelescope.parked = True
    response = client.post("/api/mount/goto", json={"ra_hours": 1.0, "dec_deg": 2.0}, headers=AUTH)
    assert response.status_code == 409 and response.json()["error"]["code"] == "parked"
    assert client.get("/api/status", headers=AUTH).json()["mount"]["state"] == "parked"


def test_mount_commands_reach_the_core_wrapper(client):
    client.post("/api/connection", json=ALPACA, headers=AUTH)
    hub = client.app.state.hub
    scope = hub._mount._scope
    client.post("/api/mount/goto", json={"ra_hours": 1.5, "dec_deg": -2.0}, headers=AUTH)
    client.post("/api/mount/stop", headers=AUTH)
    client.post("/api/mount/tracking", json={"enabled": False}, headers=AUTH)
    client.post("/api/mount/park", headers=AUTH)
    client.post("/api/mount/unpark", headers=AUTH)
    assert scope.calls == [
        ("slew_to", 1.5, -2.0),
        ("abort_slew",),
        ("set_tracking", False),
        ("park",),
        ("unpark",),
    ]


def test_driver_error_is_502_device_error(client, monkeypatch):
    client.post("/api/connection", json=ALPACA, headers=AUTH)

    def refuse(self):
        raise AlpacaError(1035, "Park not supported")

    monkeypatch.setattr(FakeTelescope, "park", refuse)
    response = client.post("/api/mount/park", headers=AUTH)
    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": "device_error", "message": "Alpaca error 1035: Park not supported"}
    }


def test_gain_is_sent_before_every_frame_as_qt_does(client):
    """exposure_worker.py:145-149 sends the gain before each frame (science review W3)."""
    client.post("/api/connection", json=ALPACA, headers=AUTH)
    camera = client.app.state.hub._camera._cam
    client.post("/api/camera/live", json={"exposure_s": 0.01, "gain": 42}, headers=AUTH)
    wait_for(
        lambda: (client.get("/api/status", headers=AUTH).json()["camera"]["last_frame_seq"] or 0)
        >= 3
    )
    client.post("/api/camera/stop", headers=AUTH)
    assert len(camera.gains) >= 3 and set(camera.gains) == {42}


def test_a_refused_gain_is_sent_again_on_the_next_frame():
    """One failed set_gain must not leave every later frame at the old gain (FITS GAIN)."""
    import threading

    cam = adapter.AlpacaCamera.__new__(adapter.AlpacaCamera)
    fake = FakeCamera("10.0.0.1", 32323)
    calls: list[int] = []

    def set_gain(gain, _left=[1]):
        calls.append(gain)
        if _left[0]:
            _left[0] -= 1
            raise AlpacaError(0, "timeout")
        fake.gains.append(gain)

    fake.set_gain = set_gain  # type: ignore[method-assign]
    cam._cam = fake
    cam._gain_error = None
    for _ in range(3):
        cam.expose(0.0, 120, threading.Event(), lambda: None)
    assert calls == [120, 120, 120] and fake.gains == [120, 120]
    # A gain changed by another client is restored before the next frame.
    fake.gains.clear()
    cam.expose(0.0, 120, threading.Event(), lambda: None)
    assert fake.gains == [120]
