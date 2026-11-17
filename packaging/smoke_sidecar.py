"""Smoke test of the frozen ARGOS server (the desktop app's one-dir sidecar).

    python packaging/smoke_sidecar.py web/src-tauri/binaries/argos-server/argos-server

Starts it as the Tauri shell does (``--host 127.0.0.1 --port 0 --desktop
--exit-on-stdin-eof``, stdin a pipe kept open), with a temporary config and
log folder, and checks that:

0. ``--self-check`` loads the app and every module the server reads by file path
   (``argos/core/session/review.py``: a freeze without it fails only in Review);
1. it prints ``ARGOS_PORT`` then ``ARGOS_TOKEN`` (its ready line) in time;
2. ``/api/health`` answers and ``/api/app/info`` reports this tree's
   ``argos.__version__`` and ``"desktop": true``;
3. closing its stdin (the shell gone) ends it within a few seconds.

Building is not proof that the frozen server starts: the release workflow
runs this before any installer is made. Standard library only, so it runs
with any Python 3.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

READY_TIMEOUT_S = 120.0  # a cold runner scans every new binary first
EXIT_TIMEOUT_S = 30.0
ROOT = Path(__file__).resolve().parent.parent


def tree_version() -> str:
    text = (ROOT / "argos" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("no __version__ in argos/__init__.py")
    return match.group(1)


def get(url: str, token: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
        return json.loads(r.read().decode())


def main(exe: str) -> int:
    with tempfile.TemporaryDirectory(prefix="argos-smoke-") as tmp:
        env = dict(
            os.environ,
            ARGOS_CONFIG_DIR=f"{tmp}/config",
            ARGOS_LOG_DIR=f"{tmp}/logs",
        )
        check = subprocess.run(
            [exe, "--self-check"],
            capture_output=True,
            text=True,
            env=env,
            timeout=READY_TIMEOUT_S,
        )
        sys.stdout.write(check.stdout)
        if check.returncode != 0 or "self-check: ok" not in check.stdout:
            sys.stdout.write(check.stderr[-4000:])
            print(f"FAIL: --self-check ended with status {check.returncode}")
            return 1
        args = [exe, "--host", "127.0.0.1", "--port", "0", "--desktop", "--exit-on-stdin-eof"]
        began = time.monotonic()
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        lines: queue.Queue[str | None] = queue.Queue()
        stderr: list[str] = []

        def pump_stdout() -> None:
            for line in proc.stdout:
                lines.put(line.strip())
            lines.put(None)

        def pump_stderr() -> None:
            stderr.extend(proc.stderr)

        threading.Thread(target=pump_stdout, daemon=True).start()
        threading.Thread(target=pump_stderr, daemon=True).start()

        def fail(why: str) -> int:
            proc.kill()
            proc.wait()
            time.sleep(0.2)
            sys.stdout.write("".join(stderr[-80:]))
            print(f"FAIL: {why}")
            return 1

        found: dict[str, str] = {}
        while not {"ARGOS_PORT", "ARGOS_TOKEN"} <= found.keys():
            left = READY_TIMEOUT_S - (time.monotonic() - began)
            try:
                line = lines.get(timeout=max(left, 0.01))
            except queue.Empty:
                return fail(f"no ready line within {READY_TIMEOUT_S:.0f} s")
            if line is None:
                return fail(f"the server ended during start-up (status {proc.wait()})")
            key, _, value = line.partition("=")
            found[key] = value
        ready = time.monotonic() - began
        print(f"ready line after {ready:.2f} s on port {found['ARGOS_PORT']}")

        base = f"http://127.0.0.1:{found['ARGOS_PORT']}"
        try:
            health = get(f"{base}/api/health")
            info = get(f"{base}/api/app/info", found["ARGOS_TOKEN"])
        except OSError as err:
            return fail(f"the server does not answer: {err}")
        version = tree_version()
        print(
            f"health: {health}; app info: version {info.get('version')}, desktop {info.get('desktop')}"
        )
        if info.get("version") != version:
            return fail(f"version {info.get('version')!r}, argos/__init__.py says {version!r}")
        if info.get("desktop") is not True:
            return fail("app info does not say desktop: true (--desktop)")

        closed = time.monotonic()
        proc.stdin.close()  # the shell is gone
        try:
            status = proc.wait(timeout=EXIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return fail(f"still running {EXIT_TIMEOUT_S:.0f} s after its stdin closed")
        print(f"stdin closed: ended in {time.monotonic() - closed:.2f} s (status {status})")
        print("OK")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
