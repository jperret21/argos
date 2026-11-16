#!/usr/bin/env python3
"""Run the ARGOS web UI for development: the server, the Vite dev server, the browser.

    .venv/bin/python run_web.py                  # your config (~/.argos) and devices
    .venv/bin/python run_web.py --sim            # the simulator, a separate dev config
    .venv/bin/python run_web.py --replay DIR     # the simulator replays DIR's FITS frames
    .venv/bin/python run_web.py -- --connect-timeout 5   # after "--": server arguments

The server (``python -m argos.server``) prints its port and token on stdout; the UI is
opened with them (``?api=…&token=…``). Vite reloads the UI on every edit under web/src;
a change to the Python server needs a restart of this command. Ctrl+C stops both.

With --sim or --replay, the server uses a dev config (default ~/.argos-dev/config, seeded
once) whose sessions, sequences, caches and logs live under ~/.argos-dev, so simulated
runs never land in ~/Argos/sessions or touch ~/.argos/config.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    server_args: list[str] = []
    if "--" in argv:
        cut = argv.index("--")
        argv, server_args = argv[:cut], argv[cut + 1 :]
    parser = argparse.ArgumentParser(
        prog="run_web.py",
        description="ARGOS web UI for development: server + Vite + browser.",
        epilog='Arguments after "--" go to the server (python -m argos.server --help).',
    )
    parser.add_argument("--sim", action="store_true", help="connect the built-in simulator")
    parser.add_argument(
        "--replay", metavar="DIR", type=Path, help="simulator replaying the FITS frames of DIR"
    )
    parser.add_argument("--port", type=int, default=8742, help="server port (0 = any free one)")
    parser.add_argument("--token", help="fixed bearer token (default: a random one per launch)")
    parser.add_argument(
        "--dev-dir",
        type=Path,
        default=Path.home() / ".argos-dev",
        help="dev config and data folder for --sim / --replay (default ~/.argos-dev)",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    return parser.parse_args(argv), server_args


def seed_dev_config(dev_dir: Path) -> Path:
    """The dev config folder, its config.json seeded once with paths under ``dev_dir``."""
    config_dir = dev_dir / "config"
    config_file = config_dir / "config.json"
    if not config_file.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        cache = dev_dir / "cache"
        seed = {
            "sessions_path": str(dev_dir / "sessions"),
            "data_paths": {
                "sequence_presets_directory": str(dev_dir / "sequences"),
                "camera_calibration_directory": str(config_dir),
                "object_catalogue_cache": str(cache / "object_resolver.json"),
                "exoplanet_cache": str(cache / "exoplanets.json"),
                "aavso_cache_directory": str(cache / "catalog"),
                "gaia_cache_directory": str(cache / "gaia"),
                "field_catalogue_cache_directory": str(cache / "field_catalogue"),
            },
        }
        config_file.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
        print(f"run_web: dev config created in {config_dir}")
    return config_dir


def server_command(args: argparse.Namespace, extra: list[str], token: str) -> list[str]:
    cmd = [sys.executable, "-m", "argos.server", "--host", "127.0.0.1"]
    cmd += ["--port", str(args.port), "--dev-token", token]
    if args.sim or args.replay:
        cmd.append("--simulator")
        if args.replay:
            cmd += ["--sim-replay", str(args.replay.expanduser().resolve())]
        if "--config-dir" not in extra:
            cmd += ["--config-dir", str(seed_dev_config(args.dev_dir.expanduser()))]
        if "--log-dir" not in extra:
            cmd += ["--log-dir", str(args.dev_dir.expanduser() / "logs")]
    return cmd + extra


def stop(proc: subprocess.Popen | None, first: int, grace: float) -> None:
    """Signal a child's process group, then SIGKILL it after ``grace`` seconds."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, first)
        else:
            proc.terminate()
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait()
    except ProcessLookupError:
        pass


def pump(stream, prefix: str, found: dict, pattern: re.Pattern | None) -> None:
    """Copy a child's output to ours; remember the first match of ``pattern``."""
    for line in iter(stream.readline, ""):
        clean = ANSI.sub("", line)
        if pattern is not None and "url" not in found:
            m = pattern.search(clean)
            if m:
                found["url"] = m.group(1)
        sys.stdout.write(prefix + line)
        sys.stdout.flush()


def main(argv: list[str]) -> int:
    args, extra = parse_args(argv)
    if not (WEB / "node_modules").is_dir():
        print("run_web: web/node_modules is missing: run `cd web && npm install` once.")
        return 1
    npm = shutil.which("npm")
    if npm is None:
        print("run_web: npm not found on PATH (install Node.js).")
        return 1
    token = args.token or secrets.token_urlsafe(16)
    group = {"start_new_session": True} if os.name == "posix" else {}

    server = vite = None

    def on_term(_signum, _frame):
        raise KeyboardInterrupt

    # Line by line even when piped, and Ctrl+C honoured even if the parent ignored SIGINT.
    sys.stdout.reconfigure(line_buffering=True)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, on_term)
    try:
        server = subprocess.Popen(
            server_command(args, extra, token),
            cwd=ROOT,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            **group,
        )
        port = None
        deadline = time.monotonic() + 60
        while port is None:
            line = server.stdout.readline()
            if not line:
                code = server.wait()
                print(f"run_web: the server stopped before it was ready (exit {code}).")
                if args.port:
                    print(f"run_web: port {args.port} in use? Try --port 0.")
                return code or 1
            sys.stdout.write(line)
            if line.startswith("ARGOS_PORT="):
                port = int(line.split("=", 1)[1])
            if time.monotonic() > deadline:
                print("run_web: no ARGOS_PORT line within 60 s.")
                return 1
        threading.Thread(target=pump, args=(server.stdout, "", {}, None), daemon=True).start()

        vite = subprocess.Popen(
            [npm, "run", "dev"],
            cwd=WEB,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **group,
        )
        found: dict = {}
        local = re.compile(r"Local:\s+(http://\S+)")
        threading.Thread(
            target=pump, args=(vite.stdout, "web │ ", found, local), daemon=True
        ).start()
        deadline = time.monotonic() + 60
        while "url" not in found and vite.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if "url" not in found:
            print("run_web: Vite did not report its address.")
            return 1

        api = f"http://127.0.0.1:{port}"
        url = f"{found['url'].rstrip('/')}/?api={quote(api, safe='')}&token={quote(token)}"
        print(f"\nrun_web: ARGOS web UI → {url}\nrun_web: Ctrl+C stops the server and Vite.\n")
        if not args.no_browser:
            webbrowser.open(url)

        while True:
            if server.poll() is not None:
                print(f"run_web: the server stopped (exit {server.returncode}).")
                return server.returncode or 0
            if vite.poll() is not None:
                print(f"run_web: Vite stopped (exit {vite.returncode}).")
                return vite.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nrun_web: stopping…")
        return 0
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        stop(vite, signal.SIGTERM, 5)
        # SIGINT takes the server's graceful path (a run is ended, devices released).
        stop(server, signal.SIGINT, 30)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
