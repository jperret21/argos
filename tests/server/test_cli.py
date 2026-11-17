"""``python -m argos.server`` as a real process: stdout contract, uvicorn, shutdown.

The in-process tests use Starlette's TestClient; this one goes through
uvicorn and a real WebSocket client, which is what the browser will see.
"""

from __future__ import annotations

import json
import os
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
websockets_sync = pytest.importorskip("websockets.sync.client")


def _start(stderr_path: Path, *args: str) -> tuple[subprocess.Popen, int, str]:
    # The configuration and the log go to the test directory, never to
    # ~/.argos or ~/Library/Logs; HOME points there too, as a second fence.
    base = stderr_path.parent
    env = {**os.environ, "HOME": str(base)}
    env.pop("ARGOS_CONFIG_DIR", None)
    env.pop("ARGOS_LOG_DIR", None)
    folders = ("--config-dir", str(base / "config"), "--log-dir", str(base / "logs"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "argos.server", "--port", "0", *folders, *args],
        cwd=REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=stderr_path.open("w"),
        text=True,
    )
    lines: list[str] = []

    def read_two() -> None:
        for _ in range(2):
            lines.append(proc.stdout.readline().strip())

    reader = threading.Thread(target=read_two, daemon=True)
    reader.start()
    reader.join(30)
    if len(lines) < 2:
        proc.kill()
        pytest.fail(f"server did not announce itself: {lines}")
    assert lines[0].startswith("ARGOS_PORT=") and lines[1].startswith("ARGOS_TOKEN=")
    return proc, int(lines[0].split("=", 1)[1]), lines[1].split("=", 1)[1]


def _stop(proc: subprocess.Popen) -> tuple[int, str]:
    """SIGTERM, then wait. uvicorn re-raises the signal after its graceful
    shutdown, so the exit status is -SIGTERM, not 0, when all went well."""
    proc.send_signal(signal.SIGTERM)
    try:
        rest, _ = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("server did not shut down within 15 s of SIGTERM")
    return proc.returncode, rest


def test_cli_end_to_end_with_simulator(tmp_path):
    stderr = tmp_path / "server.log"
    proc, port, token = _start(stderr, "--simulator", "--dev-token", "dev-tok")
    try:
        assert token == "dev-tok"
        base = f"http://127.0.0.1:{port}"
        auth = {"Authorization": f"Bearer {token}"}
        assert httpx.get(f"{base}/api/health").json()["ok"] is True
        assert httpx.get(f"{base}/api/status").status_code == 401
        status = httpx.get(f"{base}/api/status", headers=auth).json()
        assert status["connection"]["state"] == "connected"  # --simulator

        ws_base = f"ws://127.0.0.1:{port}"
        with websockets_sync.connect(f"{ws_base}/ws/events?token={token}") as events:
            assert json.loads(events.recv(timeout=5))["type"] == "status"

        with websockets_sync.connect(f"{ws_base}/ws/frames?token={token}", max_size=None) as frames:
            httpx.post(
                f"{base}/api/camera/capture",
                json={"exposure_s": 0.05, "gain": 80},
                headers=auth,
            ).raise_for_status()
            data = frames.recv(timeout=10)
            # No permessage-deflate: it would zlib every frame on the event loop.
            assert frames.response.headers.get("Sec-WebSocket-Extensions") is None
        (n,) = struct.unpack_from("<I", data)
        header = json.loads(data[4 : 4 + n])
        assert (header["width"], header["height"]) == (1080, 1920)
        assert header["pixel_offset"] % 8 == 0
        assert len(data) == header["pixel_offset"] + 1080 * 1920 * 2

        # Through real uvicorn, a bad token is a 4401 close, not a handshake failure.
        with websockets_sync.connect(f"{ws_base}/ws/events?token=wrong") as rejected:
            with pytest.raises(Exception):
                rejected.recv(timeout=5)
        assert rejected.close_code == 4401

        # A client left connected must not block shutdown.
        with websockets_sync.connect(
            f"{ws_base}/ws/frames?token={token}", max_size=None
        ) as lingering:
            lingering.recv(timeout=10)  # the latest frame, sent on connect
            started = time.monotonic()
            code, rest = _stop(proc)
            assert code in (0, -signal.SIGTERM)
            assert time.monotonic() - started < 10
        assert rest.strip() == "", f"unexpected stdout after startup: {rest!r}"
        log = stderr.read_text()
        # The lifespan shutdown ran: devices released, then uvicorn finished.
        assert "devices released" in log, log[-2000:]
        assert "Application shutdown complete" in log, log[-2000:]
        # The token never reaches the logs, even in WebSocket URLs.
        assert "dev-tok" not in log and "token=***" in log
        assert "Telescope profile:" in log
        # Start-up reads the configuration and never writes it (API 2, A3);
        # the rotating log file is in --log-dir, token redacted there too.
        assert not (tmp_path / "config" / "config.json").exists()
        assert not (tmp_path / ".argos").exists()
        file_log = (tmp_path / "logs" / "argos.log").read_text()
        assert "devices released" in file_log
        assert "dev-tok" not in file_log
    finally:
        if proc.poll() is None:
            proc.kill()


def test_cli_random_token_by_default(tmp_path):
    proc, _port, token = _start(tmp_path / "server.log")
    try:
        assert len(token) >= 32
    finally:
        _stop(proc)


def test_cli_ctrl_c_exits_cleanly(tmp_path):
    stderr = tmp_path / "server.log"
    proc, port, token = _start(stderr, "--simulator", "--dev-token", "a-long-enough-dev-token")
    try:
        auth = {"Authorization": f"Bearer {token}"}
        base = f"http://127.0.0.1:{port}"
        httpx.post(
            f"{base}/api/camera/live", json={"exposure_s": 0.05, "gain": 80}, headers=auth
        ).raise_for_status()
        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
    log = stderr.read_text()
    assert proc.returncode == 0, log[-2000:]
    assert "Traceback" not in log and "KeyboardInterrupt" not in log, log[-2000:]
    assert "devices released" in log
    assert "development only" not in log  # a long token draws no warning
