"""Fixtures for the headless server tests — no Qt, no network.

The app runs in-process through Starlette's TestClient. Its WebSocket
``receive`` blocks forever when nothing comes, so tests read sockets through
:func:`receive_json` / :func:`receive_bytes`, which fail after a timeout
instead of hanging the suite.
"""

from __future__ import annotations

import json
import struct
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable
from urllib.parse import urljoin

import numpy as np
import pytest

with warnings.catch_warnings():
    # Starlette 1.x prefers the httpx2 fork and warns once at import; httpx
    # works fine and is what pyproject's dev extra installs.
    warnings.filterwarnings("ignore", message=".*httpx2.*")
    from starlette.testclient import TestClient

from argos.server.app import create_app
from argos.server.settings import Settings, SimOptions

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
#: The server only answers on loopback names (DNS-rebinding guard), so the
#: test client talks to 127.0.0.1 rather than Starlette's "testserver".
BASE_URL = "http://127.0.0.1:8742"

#: Small frames and a fast mount keep the suite quick.
FAST_SIM = SimOptions(width=160, height=120, n_stars=40, slew_rate_deg_s=400.0)

_reader = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ws-reader")


class LoopbackClient(TestClient):
    """TestClient whose WebSockets also go to 127.0.0.1 (Starlette hard-codes "testserver")."""

    def websocket_connect(self, url: str, subprotocols=None, **kwargs: Any):
        return super().websocket_connect(
            urljoin("ws://127.0.0.1:8742", url), subprotocols, **kwargs
        )


def _receive(call: Callable[[], Any], timeout: float) -> Any:
    future = _reader.submit(call)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout:
        pytest.fail(f"no WebSocket message within {timeout} s")


def receive_json(ws, timeout: float = 5.0) -> dict:
    return _receive(ws.receive_json, timeout)


def receive_bytes(ws, timeout: float = 5.0) -> bytes:
    return _receive(ws.receive_bytes, timeout)


def receive_until(
    ws, predicate: Callable[[dict], bool], timeout: float = 5.0, seen: list | None = None
) -> dict:
    """Read events until *predicate* matches one; every message read goes to *seen*."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail("expected WebSocket event never arrived")
        message = receive_json(ws, timeout=remaining)
        if seen is not None:
            seen.append(message)
        if predicate(message):
            return message


def wait_for(predicate: Callable[[], Any], timeout: float = 5.0, interval: float = 0.02) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    pytest.fail("condition not met in time")


def decode_frame(data: bytes) -> tuple[dict, np.ndarray]:
    """Independent decoder of the /ws/frames layout (deliberately not argos code)."""
    (n,) = struct.unpack_from("<I", data, 0)
    header = json.loads(data[4 : 4 + n].decode("utf-8"))
    offset = header["pixel_offset"]
    assert offset % 8 == 0, "pixel data must be 8-byte aligned"
    assert offset >= 4 + n
    assert data[4 + n : offset] == b"\x00" * (offset - 4 - n), "padding must be zeros"
    count = header["width"] * header["height"] * header["channels"]
    assert len(data) == offset + 2 * count, "payload length must match the geometry"
    pixels = np.frombuffer(data, dtype="<u2", count=count, offset=offset)
    shape = (header["height"], header["width"])
    if header["channels"] > 1:
        shape = shape + (header["channels"],)
    return header, pixels.reshape(shape)


def reference_stats(pixels: np.ndarray) -> dict:
    flat = pixels.astype(np.float64).ravel()
    median = float(np.median(flat))
    return {
        "min": int(flat.min()),
        "max": int(flat.max()),
        "median": median,
        "mad": float(np.median(np.abs(flat - median))),
        "mean": float(flat.mean()),
    }


@pytest.fixture
def make_client():
    """Factory of started TestClients (lifespan run), all closed at teardown."""
    started: list[TestClient] = []

    def _make(sim: SimOptions = FAST_SIM, simulator: bool = False) -> TestClient:
        client = LoopbackClient(
            create_app(Settings(token=TOKEN, simulator=simulator, sim=sim)), base_url=BASE_URL
        )
        client.__enter__()
        started.append(client)
        return client

    yield _make
    for client in reversed(started):
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def connected(client) -> TestClient:
    response = client.post("/api/connection", json={"mode": "simulator"}, headers=AUTH)
    assert response.status_code == 200, response.text
    return client
