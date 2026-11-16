"""Wave 8, the desktop app's server half: shutdown (A7), reveal (A12), stdin end of file.

In-process tests drive ``POST /api/app/shutdown`` and ``POST /api/fs/reveal``
on the simulator (temporary folders, the OS command faked); the CLI tests
start ``python -m argos.server`` as a real process to check that it exits:
status 0 after the route, the SIGTERM path (−15) when stdin reaches end of
file. The real keep-awake assertion is checked by the live smoke run, never
in the suite (``test_night.py``).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from argos.server import desktop
from argos.server.settings import SimOptions
from tests.server.conftest import (
    AUTH,
    TOKEN,
    log_messages,
    receive_json,
    receive_until,
    science_client,
    status,
    wait_for,
)
from tests.server.test_night import fake
from tests.server.test_sequence import ALL, SEQ_SIM, light, put_plan, start, state

REPO = Path(__file__).resolve().parents[2]
STAGE_IDS = ["sequence", "services", "devices", "files", "exit"]

#: A slow mount (a GoTo lasts seconds) and a quick everything else.
SLOW_MOUNT = SimOptions(
    width=160,
    height=120,
    n_stars=40,
    slew_rate_deg_s=2.0,
    wheel_slot_s=0.02,
    focuser_speed_steps_s=200_000.0,
    mount_poll_s=0.05,
)


@pytest.fixture
def seq(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=ALL, sim=SEQ_SIM, autofocus_settle_s=0.0)
    client.hub = client.app.state.hub  # type: ignore[attr-defined]
    return client


def shutdown(client, **body):
    return client.post("/api/app/shutdown", json=body or None, headers=AUTH)


def exits_of(client) -> list[float]:
    """Record the exit requests the route makes (the CLI sets uvicorn's should_exit)."""
    calls: list[float] = []
    client.app.state.lifecycle.request_exit = lambda: calls.append(time.monotonic())
    assert client.app.state.lifecycle.hard_exit is None  # in-process: never os._exit
    return calls


def gated_job(client, kind: str, **options) -> threading.Event:
    """A job of *kind* that runs until the returned event is set (or it is cancelled)."""
    gate = threading.Event()

    def body(ctx):
        while not gate.is_set() and not ctx.cancelled:
            time.sleep(0.01)

    client.app.state.hub.jobs.start(kind, body, **options)
    return gate


# -- shutdown (A7) --------------------------------------------------------------------


def test_an_idle_shutdown_runs_every_stage_then_asks_the_process_to_exit(seq):
    exits = exits_of(seq)
    seen: list[dict] = []
    with seq.websocket_connect(f"/ws/events?token={TOKEN}") as ws:
        assert receive_json(ws)["type"] == "status"
        answer = shutdown(seq)
        assert answer.status_code == 202, answer.text
        assert answer.json() == {
            "state": "shutting_down",
            "forced": False,
            "what": [],
            "stages": [{"id": sid, "label": label} for sid, label in desktop.STAGES],
            "budget_s": 60.0,
        }
        receive_until(ws, lambda m: m.get("stage") == "exit", timeout=30, seen=seen)
    events = [m for m in seen if m["type"] == "shutdown"]
    assert [m["stage"] for m in events] == STAGE_IDS
    assert [m["index"] for m in events] == [1, 2, 3, 4, 5]
    assert {m["count"] for m in events} == {5} and not any(m["forced"] for m in events)
    assert events[0]["label"] == "Stopping the sequence" and events[-1]["t"].endswith("Z")
    assert seq.app.state.lifecycle.wait(5)
    wait_for(lambda: exits, timeout=3)
    assert len(exits) == 1
    # Devices released, once: the lifespan's own shutdown later does nothing more.
    assert {d["state"] for d in status(seq)["devices"].values()} == {"disconnected"}
    assert log_messages(seq).count("Server shutting down — devices released") == 1


def test_during_the_shutdown_only_reads_and_the_shutdown_route_answer(seq):
    exits_of(seq)
    first = shutdown(seq)
    assert first.status_code == 202
    again = shutdown(seq, force=True)  # idempotent: the first record, forced as it was
    assert again.status_code == 202 and again.json() == first.json()
    refused = seq.post("/api/camera/capture", json={"exposure_s": 0.1, "gain": 80}, headers=AUTH)
    assert refused.status_code == 503
    assert refused.json()["error"] == {
        "code": "shutting_down",
        "message": "ARGOS is shutting down",
    }
    assert seq.patch("/api/config", json={}, headers=AUTH).status_code == 503
    assert seq.get("/api/status", headers=AUTH).status_code == 200
    assert seq.get("/api/app/info", headers=AUTH).status_code == 200
    # The token is still checked first.
    assert seq.post("/api/devices/connect-all").status_code == 401
    assert seq.app.state.lifecycle.wait(30)


def test_a_running_sequence_refuses_the_quit_until_forced(seq):
    backend = fake(seq)
    exits = exits_of(seq)
    put_plan(seq, steps=[light(count=60, exposure_s=0.3)])
    start(seq)
    wait_for(lambda: backend.held == 1, timeout=5)
    refused = shutdown(seq)
    assert refused.status_code == 409
    error = refused.json()["error"]
    assert error["code"] == "busy"
    (item,) = error["what"]
    assert item["kind"] == "run" and item["job_id"] is None and item["job_kind"] is None
    assert item["text"].startswith("A sequence is running: SYN Var, ")
    assert item["text"].endswith(" of 60 frames.")
    assert error["message"] == "Quitting now would stop this: " + item["text"]
    # Nothing was stopped.
    assert state(seq)["active"] and backend.held == 1 and not exits

    forced = shutdown(seq, force=True)
    assert forced.status_code == 202
    body = forced.json()
    assert body["forced"] is True and [i["kind"] for i in body["what"]] == ["run"]
    assert seq.app.state.lifecycle.wait(30)
    record = seq.hub.sequence.record()
    assert record["state"] == "idle" and record["last_result"]["reason"] == "shutdown"
    assert backend.held == 0 and seq.hub.keep_awake.record()["state"] == "off"
    wait_for(lambda: exits, timeout=3)


def test_waiting_and_paused_runs_are_named_as_such():
    waiting = {"state": "waiting", "object_name": "RR Lyr", "frames_done": 0, "frames_total": 9}
    paused = {"state": "paused", "object_name": "RR Lyr", "frames_done": 3, "frames_total": 9}
    stopping = {"state": "stopping", "object_name": None}
    assert desktop._run_item(waiting)["text"] == "A sequence waits for its start time: RR Lyr."
    assert desktop._run_item(paused)["text"] == "A sequence is paused: RR Lyr, 3 of 9 frames."
    assert desktop._run_item(stopping)["text"] == "A sequence is stopping."
    unnamed = {"state": "running", "object_name": None, "frames_done": 0, "frames_total": 10}
    assert (
        desktop._run_item(unnamed)["text"]
        == "A sequence is running: 0 of 10 frames (no object name)."
    )


def test_each_busy_kind_outside_a_run(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=ALL, sim=SLOW_MOUNT)
    hub = client.app.state.hub

    def what() -> list[dict]:
        answer = shutdown(client)
        assert answer.status_code == 409, answer.text
        return answer.json()["error"]["what"]

    capture = client.post("/api/camera/capture", json={"exposure_s": 5.0, "gain": 80}, headers=AUTH)
    assert capture.status_code == 200, capture.text
    assert client.post("/api/mount/unpark", headers=AUTH).status_code == 200
    goto = client.post("/api/mount/goto", json={"ra_hours": 18.0, "dec_deg": 60.0}, headers=AUTH)
    assert goto.status_code == 200, goto.text
    wait_for(lambda: status(client)["mount"]["state"] == "slewing", timeout=5)
    solve = gated_job(client, "field_solve", resource="test")
    later = gated_job(client, "future_thing")
    export = gated_job(client, "export", cancellable=False)
    rerun = gated_job(client, "rerun", total=340)
    with hub._lock:
        hub._saves_in_flight = 2
    try:
        items = what()
        assert [i["kind"] for i in items] == [
            "exposure",
            "slew",
            "job",
            "job",
            "write",
            "write",
            "write",
        ]
        texts = [i["text"] for i in items]
        assert texts[:4] == [
            "The camera is exposing (5 s).",
            "The mount is slewing.",
            "Plate-solving the frame.",
            "A future thing task is running.",
        ]
        assert texts[4] == "2 FITS files are being written."
        assert set(texts[5:]) == {
            "Writing an export file.",
            "Re-running photometry (0 of 340 frames).",
        }
        assert {i["job_kind"] for i in items if i["job_id"]} == {
            "field_solve",
            "future_thing",
            "export",
            "rerun",
        }
    finally:
        with hub._lock:
            hub._saves_in_flight = 0
        for gate in (solve, later, export, rerun):
            gate.set()
    client.post("/api/camera/stop", headers=AUTH)
    client.post("/api/mount/stop", headers=AUTH)
    wait_for(lambda: status(client)["mount"]["state"] != "slewing", timeout=5)
    wait_for(lambda: not hub.jobs.active_count(), timeout=5)

    live = client.post("/api/camera/live", json={"exposure_s": 0.05, "gain": 80}, headers=AUTH)
    assert live.status_code == 200, live.text
    assert what() == [
        {"kind": "exposure", "text": "Live view is running.", "job_id": None, "job_kind": None}
    ]
    client.post("/api/camera/stop", headers=AUTH)
    wait_for(lambda: status(client)["camera"]["state"] == "idle", timeout=5)

    af = client.post("/api/autofocus/start", json={"exposure_s": 0.5, "num_steps": 9}, headers=AUTH)
    assert af.status_code == 200, af.text
    assert "Autofocus is running." in [i["text"] for i in what()]
    client.post("/api/autofocus/stop", headers=AUTH)
    wait_for(lambda: hub._autofocus is None, timeout=10)
    exits_of(client)
    assert shutdown(client).status_code == 202  # idle again: no refusal


def test_a_shutdown_over_its_budget_ends_the_process(seq, monkeypatch):
    lifecycle = seq.app.state.lifecycle
    ended: list[int] = []
    release = threading.Event()
    real_shutdown = seq.hub.shutdown

    def stuck(stage=None):
        if stage is not None:  # (the lifespan's call at teardown passes none)
            stage("sequence")
        release.wait(10)
        real_shutdown()

    monkeypatch.setattr(seq.hub, "shutdown", stuck)
    lifecycle.request_exit = lambda: None
    lifecycle.hard_exit = ended.append
    lifecycle.budget_s = 0.2
    assert shutdown(seq).json()["budget_s"] == 0.2
    wait_for(lambda: ended, timeout=5)
    assert ended == [desktop.OVERRUN_EXIT_STATUS]
    release.set()
    assert lifecycle.wait(15)


def test_a_shutdown_within_its_budget_never_ends_the_process_later(seq):
    # The budget bounds the stages only: once they ended, uvicorn's own exit
    # follows (bounded), and the watchdog must never fire afterwards.
    lifecycle = seq.app.state.lifecycle
    ended: list[int] = []
    exits = exits_of(seq)
    lifecycle.hard_exit = ended.append
    lifecycle.budget_s = 0.8
    assert shutdown(seq).status_code == 202
    assert lifecycle.wait(5)
    wait_for(lambda: exits, timeout=3)
    time.sleep(1.2)  # past the budget
    assert ended == []


def test_shutdown_body_is_strict(seq):
    for body in ({"force": "yes"}, {"force": 1}, {"now": True}):
        answer = seq.post("/api/app/shutdown", json=body, headers=AUTH)
        assert answer.status_code == 400, body
    assert not seq.app.state.lifecycle.closing


# -- reveal (A12) ---------------------------------------------------------------------


class Runner:
    def __init__(self, *answers) -> None:
        self.calls: list[list[str]] = []
        self.answers = list(answers) or [(0, "")]

    def __call__(self, argv: list[str]):
        self.calls.append(list(argv))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def reveal(client, path):
    return client.post("/api/fs/reveal", json={"path": str(path)}, headers=AUTH)


@pytest.fixture
def desk(make_client, tmp_path):
    client = science_client(make_client, tmp_path, desktop=True)
    client.revealer = client.app.state.revealer  # type: ignore[attr-defined]
    folder = client.sessions_path / "run 1"
    folder.mkdir(parents=True)
    (folder / "bundle.zip").write_bytes(b"PK")
    client.target = folder / "bundle.zip"  # type: ignore[attr-defined]
    return client


def test_reveal_needs_the_desktop_app(client, tmp_path):
    assert client.get("/api/app/info", headers=AUTH).json()["desktop"] is False
    answer = reveal(client, tmp_path)
    assert answer.status_code == 403
    assert answer.json()["error"]["code"] == "desktop_only"


def test_reveal_in_finder(desk):
    assert desk.get("/api/app/info", headers=AUTH).json()["desktop"] is True
    runner = Runner()
    desk.revealer.run, desk.revealer.platform = runner, "darwin"
    answer = reveal(desk, desk.target)
    assert answer.status_code == 200, answer.text
    real = str(Path(os.path.realpath(desk.target)))
    assert answer.json() == {"path": real, "method": "open -R"}
    assert runner.calls == [["/usr/bin/open", "-R", real]]


def test_reveal_on_linux_falls_back_to_xdg_open(desk, monkeypatch):
    monkeypatch.setattr(desktop.shutil, "which", lambda name: f"/usr/bin/{name}")
    runner = Runner((1, "org.freedesktop.DBus.Error.ServiceUnknown"), (0, ""))
    desk.revealer.run, desk.revealer.platform = runner, "linux"
    answer = reveal(desk, desk.target)
    assert answer.status_code == 200 and answer.json()["method"] == "xdg-open"
    real = Path(os.path.realpath(desk.target))
    assert runner.calls[0][:2] == ["/usr/bin/dbus-send", "--session"]
    assert runner.calls[0][-2:] == [f"array:string:{real.as_uri()}", "string:"]
    assert runner.calls[1] == ["/usr/bin/xdg-open", str(real.parent)]
    # A folder opens itself with xdg-open.
    runner = Runner((1, "no service"), (0, ""))
    desk.revealer.run = runner
    assert reveal(desk, real.parent).status_code == 200
    assert runner.calls[1] == ["/usr/bin/xdg-open", str(real.parent)]


def test_reveal_on_windows_ignores_explorers_exit_status(desk):
    runner = Runner((1, ""))
    desk.revealer.run, desk.revealer.platform = runner, "win32"
    answer = reveal(desk, desk.target)
    assert answer.status_code == 200 and answer.json()["method"] == "explorer"
    assert runner.calls[0][1].startswith("/select,")


def test_reveal_checks_the_path(desk):
    runner = Runner()
    desk.revealer.run, desk.revealer.platform = runner, "darwin"
    relative = reveal(desk, "run 1/bundle.zip")
    assert relative.status_code == 400 and relative.json()["error"]["code"] == "invalid_argument"
    outside = reveal(desk, "/usr/bin")
    assert outside.status_code == 403 and outside.json()["error"]["code"] == "forbidden_path"
    missing = reveal(desk, desk.target.parent / "gone.zip")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    assert desk.post("/api/fs/reveal", json={}, headers=AUTH).status_code == 400
    assert runner.calls == []


def test_a_failed_reveal_says_why(desk, monkeypatch):
    desk.revealer.run = Runner((1, "LSOpenURLsWithRole() failed with error -10814."))
    desk.revealer.platform = "darwin"
    answer = reveal(desk, desk.target)
    assert answer.status_code == 502
    assert answer.json()["error"] == {
        "code": "reveal_failed",
        "message": "The file manager could not show it: open -R: "
        "LSOpenURLsWithRole() failed with error -10814.",
    }
    desk.revealer.run = Runner(FileNotFoundError(2, "No such file or directory"))
    answer = reveal(desk, desk.target)
    assert answer.status_code == 502
    assert answer.json()["error"]["message"].endswith("open -R: No such file or directory")
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    desk.revealer.platform = "linux"
    answer = reveal(desk, desk.target)
    assert answer.status_code == 502 and "dbus-send, xdg-open" in answer.json()["error"]["message"]


def test_the_real_runner_reports_status_and_stderr(tmp_path):
    code, err = desktop.run_command([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert code == 3 and err == ""
    code, err = desktop.run_command(
        [sys.executable, "-c", "import sys; sys.stderr.write('nope'); sys.exit(1)"]
    )
    assert (code, err) == (1, "nope")
    code, err = desktop.run_command(
        [sys.executable, "-c", "import time; time.sleep(2)"], timeout_s=0.2
    )
    assert (code, err) == (None, "")  # still running: taken as shown, reaped later


# -- --exit-on-stdin-eof ------------------------------------------------------------------


def test_the_stdin_watcher_waits_for_the_signal_handlers_then_sends_sigterm():
    read_fd, write_fd = os.pipe()
    ready = threading.Event()
    kills: list[tuple[int, int]] = []
    try:
        thread = desktop.watch_stdin_eof(
            read_fd, ready=ready.is_set, kill=lambda pid, sig: kills.append((pid, sig)), poll_s=0.01
        )
        os.write(write_fd, b"anything\n")  # data is not an end of file
        time.sleep(0.1)
        assert not kills
        os.close(write_fd)
        time.sleep(0.1)
        assert not kills  # end of file, but uvicorn's handlers are not there yet
        ready.set()
        thread.join(2)
        assert kills == [(os.getpid(), signal.SIGTERM)]
    finally:
        os.close(read_fd)


# -- the real process -----------------------------------------------------------------------


def _spawn(base: Path, *args: str, stdin=subprocess.PIPE) -> tuple[subprocess.Popen, int, str]:
    env = {**os.environ, "HOME": str(base)}
    env.pop("ARGOS_CONFIG_DIR", None)
    env.pop("ARGOS_LOG_DIR", None)
    folders = ("--config-dir", str(base / "config"), "--log-dir", str(base / "logs"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "argos.server", "--port", "0", *folders, *args],
        cwd=REPO,
        env=env,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=(base / "server.log").open("w"),
        text=True,
    )
    lines: list[str] = []

    def read_two() -> None:
        for _ in range(2):
            lines.append(proc.stdout.readline().strip())

    reader = threading.Thread(target=read_two, daemon=True)
    reader.start()
    reader.join(30)
    if len(lines) < 2 or not lines[1].startswith("ARGOS_TOKEN="):
        proc.kill()
        pytest.fail(f"server did not announce itself: {lines}")
    return proc, int(lines[0].split("=", 1)[1]), lines[1].split("=", 1)[1]


def _wait_exit(proc: subprocess.Popen, timeout: float = 20) -> int:
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail(f"server still running {timeout} s later")
    return proc.returncode


def test_the_shutdown_route_ends_the_process_with_status_0(tmp_path):
    websockets_sync = pytest.importorskip("websockets.sync.client")
    token = "a-long-enough-dev-token"
    proc, port, _ = _spawn(tmp_path, "--simulator", "--desktop", "--dev-token", token)
    try:
        base = f"http://127.0.0.1:{port}"
        auth = {"Authorization": f"Bearer {token}"}
        assert httpx.get(f"{base}/api/app/info", headers=auth).json()["desktop"] is True
        httpx.post(
            f"{base}/api/camera/live", json={"exposure_s": 0.05, "gain": 80}, headers=auth
        ).raise_for_status()
        refused = httpx.post(f"{base}/api/app/shutdown", headers=auth)
        assert refused.status_code == 409
        assert [i["text"] for i in refused.json()["error"]["what"]] == ["Live view is running."]
        stages: list[str] = []
        with websockets_sync.connect(f"ws://127.0.0.1:{port}/ws/events?token={token}") as ws:
            forced = httpx.post(f"{base}/api/app/shutdown", json={"force": True}, headers=auth)
            assert forced.status_code == 202
            try:
                while True:
                    message = json.loads(ws.recv(timeout=20))
                    if message["type"] == "shutdown":
                        stages.append(message["stage"])
            except Exception:
                pass  # the server closed the socket
        assert _wait_exit(proc) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert stages == STAGE_IDS
    log = (tmp_path / "server.log").read_text()
    assert "Quit forced while busy: Live view is running." in log
    assert "Shutdown 5/5: Stopping the ARGOS server" in log
    assert log.count("devices released") == 1, log[-2000:]
    assert "Application shutdown complete" in log and "Traceback" not in log


def test_stdin_end_of_file_takes_the_graceful_path(tmp_path):
    token = "a-long-enough-dev-token"
    proc, port, _ = _spawn(tmp_path, "--simulator", "--exit-on-stdin-eof", "--dev-token", token)
    try:
        auth = {"Authorization": f"Bearer {token}"}
        httpx.post(
            f"http://127.0.0.1:{port}/api/camera/live",
            json={"exposure_s": 0.05, "gain": 80},
            headers=auth,
        ).raise_for_status()
        time.sleep(0.5)
        assert proc.poll() is None  # an open stdin keeps it running
        proc.stdin.close()  # the shell is gone
        assert _wait_exit(proc) == -signal.SIGTERM
    finally:
        if proc.poll() is None:
            proc.kill()
    log = (tmp_path / "server.log").read_text()
    assert "Standard input closed (the desktop shell is gone): shutting down." in log
    assert "devices released" in log and "Application shutdown complete" in log, log[-2000:]


def test_a_stdin_at_end_of_file_from_the_start_still_stops_gracefully(tmp_path):
    proc, _port, _ = _spawn(tmp_path, "--exit-on-stdin-eof", stdin=subprocess.DEVNULL)
    try:
        assert _wait_exit(proc) == -signal.SIGTERM
    finally:
        if proc.poll() is None:
            proc.kill()
    log = (tmp_path / "server.log").read_text()
    assert "Standard input closed" in log and "Application shutdown complete" in log, log[-2000:]
