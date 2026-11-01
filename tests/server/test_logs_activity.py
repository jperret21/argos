"""Log stream v2 and replay (A2), activity (A4), app info (A1), event compaction."""

from __future__ import annotations

import asyncio
import logging

from argos import __version__
from argos.server.events import EVENT_BACKLOG, EventSubscriber
from argos.server.logbook import LOG_HISTORY, LOG_RING, LogBook
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until

LOG_FIELDS = {"type", "id", "seq", "level", "source", "topic", "message", "t"}


def test_log_lines_carry_seq_level_source_and_topic(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        client.post("/api/devices/mount/connect", json={"mode": "simulator"}, headers=AUTH)
        seen: list[dict] = []
        receive_until(events, lambda m: m["type"] == "log" and m["level"] == "ok", seen=seen)
    logs = [m for m in seen if m["type"] == "log"]
    for line in logs:
        assert set(line) == LOG_FIELDS and line["id"] == line["seq"] and line["t"].endswith("Z")
    assert [(m["level"], m["message"]) for m in logs] == [
        ("cmd", "Connecting mount simulator…"),
        ("ok", "Mount connected: ARGOS mount simulator"),
    ]
    assert {(m["source"], m["topic"]) for m in logs} == {("mount", "connection")}
    assert logs[1]["seq"] == logs[0]["seq"] + 1


def test_ring_keeps_5000_lines_and_pages_them():
    book = LogBook()
    for i in range(LOG_RING + 10):
        book.append("info" if i % 2 else "warning", f"line {i}", "server", "app")
    page = book.page()
    assert page["first_seq"] == 11 and page["last_seq"] == LOG_RING + 10
    assert page["truncated"] is True  # lines 1-10 were dropped
    assert len(page["entries"]) == 1000  # default limit
    tail = book.page(after=LOG_RING + 5, limit=10)
    assert [e["seq"] for e in tail["entries"]] == [LOG_RING + 6 + i for i in range(5)]
    assert tail["truncated"] is False
    warnings = book.page(after=LOG_RING, level="warning")["entries"]
    assert {e["level"] for e in warnings} == {"warning"}
    assert len(book.recent()) == LOG_HISTORY


def test_logs_route_filters_and_validates(client):
    hub = client.app.state.hub
    for i in range(30):
        hub.log("info", f"note {i}")
    hub.log("error", "the bad one")
    page = client.get("/api/logs?after=10&limit=5", headers=AUTH).json()
    assert [e["seq"] for e in page["entries"]] == [11, 12, 13, 14, 15]
    errors = client.get("/api/logs?level=error", headers=AUTH).json()["entries"]
    assert [e["message"] for e in errors] == ["the bad one"]
    for query in ("limit=0", "limit=5001", "after=-1", "level=loud"):
        assert client.get(f"/api/logs?{query}", headers=AUTH).status_code == 400, query


def test_replay_gives_the_newest_200_and_rest_comes_from_the_route(client):
    hub = client.app.state.hub
    for i in range(LOG_HISTORY + 50):
        hub.log("info", f"line {i}")
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        assert receive_json(events)["type"] == "status"
        assert receive_json(events)["type"] == "network"
        assert receive_json(events)["type"] == "stellarium"
        replayed = [receive_json(events) for _ in range(LOG_HISTORY)]
    assert [m["type"] for m in replayed] == ["log"] * LOG_HISTORY
    assert (
        replayed[0]["message"] == "line 50"
        and replayed[-1]["message"] == f"line {LOG_HISTORY + 49}"
    )
    older = client.get(f"/api/logs?limit={replayed[0]['seq'] - 1}", headers=AUTH).json()
    assert len(older["entries"]) == 50 and older["entries"][0]["message"] == "line 0"


def test_core_warnings_are_tagged_core(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        logging.getLogger("argos.core.alpaca.camera").warning("driver says no gain")
        line = receive_until(events, lambda m: m.get("message") == "driver says no gain")
    assert (line["source"], line["topic"], line["level"]) == ("core", "camera", "warning")


def test_activity_event_and_its_replay(client):
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        client.post("/api/devices/camera/connect", json={"mode": "simulator"}, headers=AUTH)
        activity = receive_until(events, lambda m: m["type"] == "activity")
    assert activity["text"] == "Connecting camera simulator…"
    assert activity["source"] == "camera" and activity["t"].endswith("Z")
    client.delete("/api/devices", headers=AUTH)
    # A page opened later gets the latest activity right after status, network and
    # the Stellarium bridge's record.
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        messages = [receive_json(events) for _ in range(4)]
    assert [m["type"] for m in messages] == ["status", "network", "stellarium", "activity"]
    assert messages[3]["text"] == "Disconnected"


def test_app_info(client):
    info = client.get("/api/app/info", headers=AUTH).json()
    assert info["version"] == __version__ and info["api"] == 2
    assert info["paths"]["config"].endswith("config.json")
    assert info["paths"]["diagnostics"] is None and info["paths"]["log_file"] is None
    assert info["profile"]["key"] == "s30pro"
    assert info["licence"] == "GPL-3.0-or-later"
    assert info["docs_url"] == "https://perretjules.com/argos/"
    assert info["project_url"] == "https://github.com/jperret21/argos"
    assert info["astap_configured"] is False and info["diagnostics_enabled"] is False
    assert {c["name"] for c in info["credits"]} >= {"NumPy", "Astropy", "alpyca", "FastAPI"}
    assert client.get("/api/app/info").status_code == 401


def test_backlog_keeps_the_newest_event_of_each_job():
    async def scenario():
        sub = EventSubscriber()
        sub.offer("job:a", 1, {"type": "job", "job": {"id": "a", "seq": 1}})
        sub.offer("job:b", 2, {"type": "job", "job": {"id": "b", "seq": 2}})
        for i in range(EVENT_BACKLOG):
            sub.offer("job:a", 3 + i, {"type": "job", "job": {"id": "a", "seq": 3 + i}})
        return await sub.next_batch()

    batch = asyncio.run(scenario())
    jobs = {m["job"]["id"]: m["job"]["seq"] for m in batch}
    assert jobs == {"a": EVENT_BACKLOG + 2, "b": 2}  # b's state survives a's flood


def test_status_covers_older_devices_events():
    async def scenario():
        sub = EventSubscriber()
        sub.offer("status", 10, {"type": "status"})
        sub.offer("devices", 9, {"type": "devices"})  # older than the status: dropped
        sub.offer("devices", 11, {"type": "devices", "new": True})
        return await sub.next_batch()

    assert asyncio.run(scenario()) == [{"type": "status"}, {"type": "devices", "new": True}]


def test_log_lines_reach_the_bus_in_seq_order_under_contention(tmp_path):
    """Numbering and publishing happen under one lock: threads logging at the same
    time never deliver line n+1 before line n (a reorder made clients see false
    gaps and re-read GET /api/logs)."""
    import sys
    import threading

    from argos.server.events import EventBus
    from argos.server.hub import Hub
    from tests.server.conftest import make_settings

    published: list[int] = []
    order_lock = threading.Lock()

    class RecordingBus(EventBus):
        def publish(self, kind, seq, payload):
            if kind == "log":
                with order_lock:
                    published.append(payload["seq"])

    hub = Hub(RecordingBus(), settings=make_settings(config_dir=tmp_path))
    before = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [
            threading.Thread(
                target=lambda n=n: [hub.publish_log("info", f"t{n} {i}") for i in range(500)]
            )
            for n in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(before)
    assert len(published) == 4000
    assert published == sorted(published)


def test_boot_id_names_the_server_process_everywhere(client):
    boot = client.get("/api/health").json()["boot_id"]
    assert client.get("/api/status", headers=AUTH).json()["boot_id"] == boot
    assert client.get("/api/logs", headers=AUTH).json()["boot_id"] == boot
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        status = receive_json(events)
    assert status["type"] == "status" and status["boot_id"] == boot
