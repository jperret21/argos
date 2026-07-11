"""Tests for the layered Alpaca discovery (probe + fallback logic).

The UDP broadcast itself is not exercised (it needs a live network); these
tests cover the TCP fallbacks with a local HTTP server standing in for the
Seestar's Alpaca management endpoint.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from argos.core.alpaca import discovery
from argos.core.alpaca.discovery import AlpacaDevice, discover_all, probe_alpaca


class _AlpacaHandler(BaseHTTPRequestHandler):
    """Answers every GET like an Alpaca management endpoint."""

    def do_GET(self):  # noqa: N802 (http.server API)
        body = b'{"Value": [], "ClientTransactionID": 0, "ServerTransactionID": 0}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence per-request stderr noise
        pass


@pytest.fixture
def alpaca_server():
    """A throwaway local server mimicking the Seestar's Alpaca HTTP port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AlpacaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "127.0.0.1", server.server_address[1]
    server.shutdown()
    thread.join(timeout=2)


def test_probe_alpaca_hits_a_live_server(alpaca_server) -> None:
    host, port = alpaca_server
    assert probe_alpaca(host, port, timeout=2.0)


def test_probe_alpaca_false_on_closed_port() -> None:
    # Port 9 (discard) is never an HTTP server on localhost.
    assert not probe_alpaca("127.0.0.1", 9, timeout=0.5)


def test_discover_all_prefers_broadcast(monkeypatch) -> None:
    hit = [AlpacaDevice("192.0.2.10", 32323)]
    monkeypatch.setattr(discovery, "discover", lambda timeout: hit)
    monkeypatch.setattr(
        discovery, "probe_alpaca", lambda *a, **k: pytest.fail("probe must not run")
    )
    assert discover_all(32323, candidates=("192.0.2.99",)) == hit


def test_discover_all_falls_back_to_candidates(monkeypatch, alpaca_server) -> None:
    host, port = alpaca_server
    monkeypatch.setattr(discovery, "discover", lambda timeout: [])
    monkeypatch.setattr(discovery, "scan_subnet", lambda *a, **k: pytest.fail("scan must not run"))
    # An empty and a dead candidate are skipped; the live one wins.
    found = discover_all(port, candidates=("", "127.0.0.1", host))
    # "127.0.0.1" IS the live host here — the first probe already hits.
    assert found == [AlpacaDevice(host, port)]


def test_discover_all_reaches_subnet_scan_last(monkeypatch) -> None:
    scanned = [AlpacaDevice("192.0.2.20", 32323)]
    monkeypatch.setattr(discovery, "discover", lambda timeout: [])
    monkeypatch.setattr(discovery, "probe_alpaca", lambda *a, **k: False)
    monkeypatch.setattr(discovery, "scan_subnet", lambda port: scanned)
    assert discover_all(32323, candidates=("192.0.2.99",)) == scanned


def test_discover_all_dedupes_candidates(monkeypatch) -> None:
    calls: list[str] = []

    def fake_probe(host, port, timeout=1.0):
        calls.append(host)
        return False

    monkeypatch.setattr(discovery, "discover", lambda timeout: [])
    monkeypatch.setattr(discovery, "probe_alpaca", fake_probe)
    monkeypatch.setattr(discovery, "scan_subnet", lambda port: [])
    discover_all(32323, candidates=("10.0.0.1", "10.0.0.1", " 10.0.0.1 "))
    assert calls == ["10.0.0.1"]
