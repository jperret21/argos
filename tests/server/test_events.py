"""/ws/events behaviour and the bounded per-client buffers of the event bus."""

from __future__ import annotations

import asyncio

from argos.server.events import EventBus, EventSubscriber, FrameSubscriber
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until


def test_status_is_sent_immediately_on_connect(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        message = receive_json(events)
    assert message["type"] == "status"
    assert message["connection"] == {
        "state": "disconnected",
        "mode": None,
        "device_name": None,
        "message": None,
    }
    assert set(message["camera"]) == {"state", "exposure_s", "gain", "last_frame_seq", "sensor"}
    assert set(message["mount"]) == {
        "state",
        "ra_hours",
        "dec_deg",
        "alt_deg",
        "az_deg",
        "tracking",
        "pier_side",
        "target",
    }


def test_connect_emits_connecting_then_connected_and_a_log(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        client.post("/api/connection", json={"mode": "simulator"}, headers=AUTH)
        seen: list[dict] = []
        receive_until(
            events,
            lambda m: m["type"] == "log" and m["message"].startswith("Connected"),
            seen=seen,
        )
    states = [m["connection"]["state"] for m in seen if m["type"] == "status"]
    assert states[0] == "connecting" and states[-1] == "connected"
    log = seen[-1]
    assert log["level"] == "info" and log["t"].endswith("Z")


def test_status_snapshot_reflects_current_state(connected):
    with connected.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        message = receive_json(events)
    assert message["connection"]["state"] == "connected"
    assert message["camera"]["sensor"]["width"] == 160
    assert message["mount"]["state"] == "parked"


def test_camera_failure_becomes_error_state_and_log(connected, monkeypatch):
    from argos.server.devices.sim_camera import SimCamera

    def broken(*_args, **_kwargs):
        raise RuntimeError("sensor fault")

    monkeypatch.setattr(SimCamera, "render", broken)
    with connected.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        connected.post("/api/camera/capture", json={"exposure_s": 0.01, "gain": 80}, headers=AUTH)
        seen: list[dict] = []
        receive_until(events, lambda m: m["type"] == "log" and m["level"] == "error", seen=seen)
    assert seen[-1]["message"] == "Camera: sensor fault"
    status = connected.get("/api/status", headers=AUTH).json()
    assert status["camera"]["state"] == "error"
    assert status["connection"]["state"] == "connected"  # the server carries on

    monkeypatch.undo()
    assert connected.post("/api/camera/stop", headers=AUTH).json()["state"] == "idle"
    response = connected.post(
        "/api/camera/capture", json={"exposure_s": 0.01, "gain": 80}, headers=AUTH
    )
    assert response.status_code == 200


# -- bus internals ----------------------------------------------------------


def _drain(sub: EventSubscriber) -> list[dict]:
    return asyncio.run(asyncio.wait_for(sub.next_batch(), 1.0))


def test_a_client_that_keeps_up_sees_every_transition():
    sub = EventSubscriber()
    sub.offer("status", 1, {"type": "status", "state": "connecting"})
    sub.offer("status", 2, {"type": "status", "state": "connected"})
    sub.offer("log", None, {"type": "log"})
    assert [m.get("state", "log") for m in _drain(sub)] == ["connecting", "connected", "log"]


def test_backlog_compacts_to_the_newest_snapshots():
    sub = EventSubscriber(capacity=5)
    sub.offer("log", None, {"type": "log", "i": 0})
    for seq in range(1, 50):
        sub.offer("mount", seq, {"type": "mount", "n": seq})
    sub.offer("camera", 50, {"type": "camera", "n": 50})
    batch = _drain(sub)
    assert batch == [
        {"type": "log", "i": 0},
        {"type": "mount", "n": 49},
        {"type": "camera", "n": 50},
    ]
    assert sub.dropped > 0


def test_older_snapshots_than_a_status_are_dropped():
    sub = EventSubscriber()
    sub.offer("status", 10, {"type": "status"})
    _drain(sub)
    sub.offer("mount", 9, {"type": "mount", "stale": True})  # queued before the snapshot
    sub.offer("camera", 8, {"type": "camera", "stale": True})
    sub.offer("mount", 11, {"type": "mount", "fresh": True})
    assert _drain(sub) == [{"type": "mount", "fresh": True}]


def test_log_backlog_is_bounded():
    sub = EventSubscriber(capacity=5)
    for i in range(100):
        sub.offer("log", None, {"type": "log", "i": i})
    assert [m["i"] for m in _drain(sub)] == [95, 96, 97, 98, 99]


def test_frames_are_latest_wins():
    sub = FrameSubscriber()
    for i in range(10):
        sub.offer(bytes([i]))
    assert asyncio.run(sub.next_frame()) == bytes([9])
    assert sub.skipped == 9


def test_closed_subscribers_release_their_reader():
    async def scenario():
        bus = EventBus()
        bus.attach(asyncio.get_running_loop())
        events, frames = bus.subscribe_events(), bus.subscribe_frames()
        waiting = asyncio.gather(events.next_batch(), frames.next_frame())
        await asyncio.sleep(0)
        bus.detach()
        return await asyncio.wait_for(waiting, 1.0)

    assert asyncio.run(scenario()) == [[], None]


def test_publish_from_a_thread_reaches_the_loop():
    import threading

    async def scenario():
        bus = EventBus()
        bus.attach(asyncio.get_running_loop())
        sub = bus.subscribe_events()
        threading.Thread(target=bus.publish, args=("log", None, {"type": "log"})).start()
        return await asyncio.wait_for(sub.next_batch(), 1.0)

    assert asyncio.run(scenario()) == [{"type": "log"}]


def test_publish_without_loop_is_a_no_op():
    EventBus().publish("log", None, {"type": "log"})
    EventBus().publish_frame(b"x")


def test_a_page_opened_later_receives_the_recent_log(connected):
    with connected.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        first = receive_json(events)
        replayed = receive_json(events)
    assert first["type"] == "status"  # the contract: status first
    assert replayed["type"] == "log" and replayed["message"].startswith("Connected")


def test_log_history_is_bounded():
    from argos.server.hub import LOG_HISTORY, Hub

    hub = Hub()
    for i in range(LOG_HISTORY + 50):
        hub.publish_log("info", f"line {i}")
    history = hub.log_history()
    assert len(history) == LOG_HISTORY
    assert history[-1]["message"] == f"line {LOG_HISTORY + 49}"


def test_core_info_stays_out_and_warnings_come_once(client):
    import logging

    core = logging.getLogger("argos.core.alpaca.camera")
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        core.info("Starting 1.00s light exposure")  # every frame in live view
        for _ in range(3):
            core.warning("Camera does not implement Gain — skipping")
        core.error("sentinel")
        seen: list[dict] = []
        receive_until(events, lambda m: m.get("message") == "sentinel", seen=seen)
    messages = [m["message"] for m in seen if m["type"] == "log"]
    assert messages == ["Camera does not implement Gain — skipping", "sentinel"]
