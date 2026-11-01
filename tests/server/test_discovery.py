"""Discovery as a cancellable job (row A16), without leaving the machine.

The UDP broadcast and the subnet sweep would touch the LAN, so they are
faked; the HTTP probe and the ``ServerName`` read run for real against a
tiny Alpaca management server on 127.0.0.1.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from argos.server import discovery
from argos.server.discovery import DEFAULT_LAYERS, DiscoveryLayers
from tests.server.conftest import AUTH, TOKEN, receive_json, receive_until, wait_for


class _Management(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        if self.path.startswith("/management/v1/configureddevices"):
            body = {"Value": [{"DeviceType": "Telescope", "DeviceNumber": 0}]}
        elif self.path.startswith("/management/v1/description"):
            body = {"Value": {"ServerName": "Seestar Alpaca Server", "Manufacturer": "ZWO"}}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


@pytest.fixture
def alpaca_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Management)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def _silent_broadcast(timeout_s, cancel):
    return []


def _no_scan(port, cancel):
    return []


def _layers(**changes) -> DiscoveryLayers:
    base = dict(
        broadcast=_silent_broadcast, probe=DEFAULT_LAYERS.probe, scan=_no_scan,
        name=DEFAULT_LAYERS.name,
    )  # fmt: skip
    base.update(changes)
    return DiscoveryLayers(**base)


def _final(client, job_id: str) -> dict:
    return wait_for(
        lambda: (j := client.get(f"/api/jobs/{job_id}", headers=AUTH).json())["state"]
        in ("done", "failed", "cancelled")
        and j,
        timeout=10,
    )


def test_probe_layer_finds_the_candidate_and_reads_its_name(client, alpaca_server):
    client.app.state.hub.discovery_layers = _layers()
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_json(events)
        response = client.post(
            "/api/discovery",
            json={"port": alpaca_server, "candidates": ["127.0.0.1"], "broadcast_timeout_s": 0.5},
            headers=AUTH,
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert response.json()["job"]["kind"] == "discovery"
        seen: list[dict] = []
        receive_until(
            events, lambda m: m["type"] == "job" and m["job"]["state"] == "done", seen=seen
        )
    final = _final(client, job_id)
    assert final["result"] == {
        "devices": [{"host": "127.0.0.1", "port": alpaca_server, "name": "Seestar Alpaca Server"}],
        "method": "probe",
        "searched": ["broadcast", "probe"],
    }
    stages = [m["job"]["stage"] for m in seen if m["type"] == "job"]
    assert stages[0] == "broadcast" and stages[-1] == "names"
    logs = [(m["level"], m["message"], m["topic"]) for m in seen if m["type"] == "log"]
    assert ("info", "Starting Alpaca discovery…", "discovery") in logs
    assert (
        "ok",
        f"Found 127.0.0.1:{alpaca_server} (Seestar Alpaca Server)",
        "discovery",
    ) in logs
    # The server never fills the address itself.
    assert client.get("/api/config", headers=AUTH).json()["values"]["alpaca.host"] == ""


def test_broadcast_results_are_all_returned(client):
    found = [("192.168.1.42", 32323), ("192.168.1.43", 11111)]
    client.app.state.hub.discovery_layers = _layers(
        broadcast=lambda timeout, cancel: list(found), name=lambda host, port: None
    )
    job_id = client.post("/api/discovery", headers=AUTH).json()["job_id"]
    result = _final(client, job_id)["result"]
    assert result["method"] == "broadcast" and result["searched"] == ["broadcast"]
    assert [(d["host"], d["port"], d["name"]) for d in result["devices"]] == [
        ("192.168.1.42", 32323, None),
        ("192.168.1.43", 11111, None),
    ]


def test_nothing_found_is_a_warning_and_an_empty_result(client):
    client.app.state.hub.discovery_layers = _layers(probe=lambda host, port: False)
    job_id = client.post("/api/discovery", json={"candidates": ["10.9.9.9"]}, headers=AUTH).json()[
        "job_id"
    ]
    final = _final(client, job_id)
    assert final["state"] == "done"
    assert final["result"] == {
        "devices": [],
        "method": None,
        "searched": ["broadcast", "probe", "subnet"],
    }
    entries = client.get("/api/logs?level=warning", headers=AUTH).json()["entries"]
    assert entries[-1]["message"] == (
        "No Alpaca devices found (broadcast, direct probes and subnet scan)."
    )


def test_default_candidates_are_the_last_host_and_the_ap_address(client):
    probed: list[tuple[str, int]] = []
    client.app.state.hub.discovery_layers = _layers(
        probe=lambda host, port: probed.append((host, port)) or False
    )
    client.patch("/api/config", json={"alpaca.host": "192.168.1.42"}, headers=AUTH)
    _final(client, client.post("/api/discovery", headers=AUTH).json()["job_id"])
    assert probed == [("192.168.1.42", 32323), ("10.0.0.1", 32323)]  # device_session.py:205


def test_cancel_during_the_broadcast_is_prompt(client):
    def listening(timeout_s, cancel):
        cancel.wait(30)  # the real layer checks every 0.25 s
        return []

    client.app.state.hub.discovery_layers = _layers(broadcast=listening)
    job_id = client.post("/api/discovery", headers=AUTH).json()["job_id"]
    busy = client.post("/api/discovery", headers=AUTH)
    assert busy.status_code == 409
    assert busy.json()["error"] == {
        "code": "busy",
        "message": "A discovery job is already running",
        "owner": job_id,
    }
    started = time.monotonic()
    client.delete(f"/api/jobs/{job_id}", headers=AUTH)
    final = _final(client, job_id)
    assert time.monotonic() - started < 0.5
    assert final["state"] == "cancelled" and final["result"] is None
    messages = [e["message"] for e in client.get("/api/logs", headers=AUTH).json()["entries"]]
    assert messages[-1] == "Discovery cancelled."


def test_cancel_does_not_wait_for_a_hanging_http_probe(client):
    released = threading.Event()

    def hanging_probe(host, port):
        released.wait(5)  # an HTTP call that cannot be interrupted
        return False

    client.app.state.hub.discovery_layers = _layers(probe=hanging_probe)
    job_id = client.post("/api/discovery", json={"candidates": ["10.9.9.9"]}, headers=AUTH).json()[
        "job_id"
    ]
    wait_for(lambda: client.get(f"/api/jobs/{job_id}", headers=AUTH).json()["stage"] == "probe")
    started = time.monotonic()
    client.delete(f"/api/jobs/{job_id}", headers=AUTH)
    final = _final(client, job_id)
    assert time.monotonic() - started < 0.5
    assert final["state"] == "cancelled"
    released.set()


def test_discovery_body_is_validated(client):
    for body in (
        {"port": 0},
        {"broadcast_timeout_s": 120},
        {"candidates": [""]},
        {"unknown": 1},
    ):
        response = client.post("/api/discovery", json=body, headers=AUTH)
        assert response.status_code == 400, body


# -- the cancellable ports of the core layers ----------------------------------


def test_scan_port_sweeps_the_24_and_confirms_hits(monkeypatch):
    monkeypatch.setattr(discovery.core, "local_ipv4", lambda: "192.168.7.20")

    class Open:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def connect(address, timeout):
        assert timeout == discovery.core.SCAN_CONNECT_TIMEOUT
        if address[0] in ("192.168.7.42", "192.168.7.43"):
            return Open()
        raise OSError("refused")

    monkeypatch.setattr(discovery.socket, "create_connection", connect)
    monkeypatch.setattr(discovery.core, "probe_alpaca", lambda host, port: host.endswith(".42"))
    assert discovery.scan(32323, threading.Event()) == [("192.168.7.42", 32323)]


def test_scan_port_stops_on_cancel(monkeypatch):
    monkeypatch.setattr(discovery.core, "local_ipv4", lambda: "192.168.7.20")
    cancel = threading.Event()

    def slow(address, timeout):
        time.sleep(0.2)
        raise OSError("timed out")

    monkeypatch.setattr(discovery.socket, "create_connection", slow)
    threading.Timer(0.1, cancel.set).start()
    started = time.monotonic()
    assert discovery.scan(32323, cancel) == []
    assert time.monotonic() - started < 0.5  # not 254 × 0.2 s / 64 workers ≈ 0.8 s


def test_broadcast_port_listens_and_parses_replies(monkeypatch):
    """The UDP layer, with a fake socket (no packet leaves the machine)."""
    sent: list = []
    replies = [
        (b'{"AlpacaPort": 32323}', ("192.168.1.42", 32227)),
        (b'{"AlpacaPort": 32323}', ("192.168.1.42", 32227)),  # duplicate
        (b"not json", ("192.168.1.50", 32227)),
    ]

    class FakeSocket:
        def __init__(self, *args):
            pass

        def setsockopt(self, *args):
            pass

        def settimeout(self, value):
            assert value <= 0.25

        def bind(self, address):
            pass

        def sendto(self, data, address):
            sent.append((data, address))

        def recvfrom(self, size):
            if replies:
                return replies.pop(0)
            raise socket.timeout()

        def close(self):
            pass

    monkeypatch.setattr(discovery.socket, "socket", FakeSocket)
    found = discovery.broadcast(0.3, threading.Event())
    assert sent == [(b"alpacadiscovery1", ("255.255.255.255", 32227))]
    assert found == [("192.168.1.42", 32323)]
