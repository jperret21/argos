"""An unreachable Seestar never freezes the server (API 2, rows A14-A15).

Measured, not assumed: while a device connect hangs, other requests and the
event stream keep answering within a small fraction of a second.

- A closed port fails at once through the real Alpaca adapter and the TCP
  pre-check ("connection refused").
- A black-hole address (192.0.2.1, TEST-NET-1, never assigned) fails within
  the pre-check budget; latency is measured during the attempt. On a
  machine without a route the OS refuses at once, which the test accepts.
- A driver call that hangs (the alpyca 5 s timeout, simulated) with the
  pre-check off: same measurement, deterministic.
"""

from __future__ import annotations

import socket
import statistics
import threading
import time

from argos.core.alpaca.client import AlpacaError
from argos.server.devices import alpaca as adapter
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until, wait_for

BLACK_HOLE = "192.0.2.1"
#: A request is "not frozen" if it answers within this (s); a hung connect
#: lasts seconds. The worst latency seen on the reference machine is ~20 ms.
FAST_S = 0.3


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _measure(client, until: threading.Thread, paths=("/api/status", "/api/config")) -> list[float]:
    """Latencies of GETs issued while *until* runs (at least a few)."""
    latencies: list[float] = []
    while until.is_alive() or len(latencies) < 4:
        for path in paths:
            started = time.monotonic()
            response = client.get(path, headers=AUTH)
            latencies.append(time.monotonic() - started)
            assert response.status_code == 200
        if not until.is_alive() and len(latencies) >= 4:
            break
        time.sleep(0.02)
    return latencies


def test_closed_port_fails_fast_with_the_os_reason(make_client):
    client = make_client(connect_timeout_s=0.5)
    port = _closed_port()
    started = time.monotonic()
    response = client.post(
        "/api/devices/mount/connect",
        json={"mode": "alpaca", "host": "127.0.0.1", "port": port},
        headers=AUTH,
    )
    elapsed = time.monotonic() - started
    assert response.status_code == 502
    assert response.json()["error"]["message"] == (
        f"Cannot reach 127.0.0.1:{port} — Connection refused"
    )
    assert elapsed < 1.0
    mount = client.get("/api/devices", headers=AUTH).json()["mount"]
    assert mount["state"] == "error" and "Connection refused" in mount["error"]


def test_black_hole_address_is_bounded_and_does_not_freeze(make_client):
    client = make_client(connect_timeout_s=0.3)
    answers: list = []
    attempt = threading.Thread(
        target=lambda: answers.append(
            client.post(
                "/api/devices/connect-all",
                json={"mode": "alpaca", "host": BLACK_HOLE, "port": 32323},
                headers=AUTH,
            )
        )
    )
    started = time.monotonic()
    attempt.start()
    latencies = _measure(client, attempt)
    attempt.join(10)
    elapsed = time.monotonic() - started
    # One pre-check of the address for the four devices (or refused at once).
    assert elapsed < 0.3 + 1.0
    assert answers[0].status_code == 200
    devices = answers[0].json()
    assert {d["state"] for d in devices.values()} == {"error"}
    assert all(
        d["error"].startswith(f"Cannot reach {BLACK_HOLE}:32323 — ") for d in devices.values()
    )
    assert max(latencies) < FAST_S, latencies
    print(  # recorded in the report with -s
        f"\nblack hole: connect-all {elapsed:.2f} s, {len(latencies)} GETs meanwhile, "
        f"median {statistics.median(latencies) * 1000:.1f} ms, max {max(latencies) * 1000:.1f} ms"
    )


class HangingTelescope:
    """``Telescope.connect`` stuck in the driver (alpyca's 5 s timeout), then refused."""

    release = threading.Event()

    def __init__(self, host, port):
        pass

    def connect(self):
        HangingTelescope.release.wait(5)
        raise AlpacaError(0, "Timeout connecting to 10.0.0.1:32323")

    def disconnect(self):
        pass


def test_hung_driver_call_freezes_neither_requests_nor_events(make_client, monkeypatch):
    monkeypatch.setattr(adapter, "Telescope", HangingTelescope)
    HangingTelescope.release = threading.Event()
    client = make_client()  # no pre-check: the driver call itself hangs
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        attempt = threading.Thread(
            target=lambda: client.post(
                "/api/devices/mount/connect",
                json={"mode": "alpaca", "host": "10.0.0.1", "port": 32323},
                headers=AUTH,
            )
        )
        attempt.start()
        wait_for(
            lambda: client.get("/api/devices", headers=AUTH).json()["mount"]["state"]
            == "connecting"
        )
        # Requests: status, config read, a config commit and its event.
        stopper = threading.Timer(1.0, HangingTelescope.release.set)
        stopper.start()
        latencies = _measure(client, stopper)
        started = time.monotonic()
        patched = client.patch("/api/config", json={"site.name": "Home"}, headers=AUTH)
        assert patched.status_code == 200
        receive_until(events, lambda m: m["type"] == "config", timeout=1.0)
        event_latency = time.monotonic() - started
        attempt.join(10)
    assert max(latencies) < FAST_S, latencies
    assert event_latency < FAST_S
    mount = client.get("/api/devices", headers=AUTH).json()["mount"]
    assert mount["state"] == "error"
    print(
        f"\nhung driver: {len(latencies)} GETs during the hang, "
        f"max {max(latencies) * 1000:.1f} ms; config event after {event_latency * 1000:.1f} ms"
    )


def test_connect_all_checks_a_dead_address_once(make_client, monkeypatch):
    client = make_client(connect_timeout_s=0.5)
    opened: list = []
    monkeypatch.setattr(adapter, "Telescope", lambda *a: opened.append(a))
    port = _closed_port()
    response = client.post(
        "/api/devices/connect-all",
        json={"mode": "alpaca", "host": "127.0.0.1", "port": port},
        headers=AUTH,
    )
    assert response.status_code == 200
    reason = f"Cannot reach 127.0.0.1:{port} — Connection refused"
    assert {d["state"] for d in response.json().values()} == {"error"}
    assert {d["error"] for d in response.json().values()} == {reason}
    assert opened == []  # no driver call was made
    errors = client.get("/api/logs?level=error", headers=AUTH).json()["entries"]
    assert [e["message"] for e in errors] == [
        f"{reason} (mount, camera, filter wheel, focuser not connected)"
    ]
