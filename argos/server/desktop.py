"""The desktop app's server half (wave 8): shutdown (A7), reveal (A12), the shell's stdin.

- :func:`busy_items` says what a quit would stop (P39: the Qt app stopped a
  sequence silently, ``acquisition_engine.py:1621-1622``).
- :class:`ShutdownService` runs ``POST /api/app/shutdown``: refused with
  ``what`` while something is busy unless forced, then ``Hub.shutdown`` with
  one ``shutdown`` event per stage (port of ``Shell.closeEvent``,
  ``shell.py:611-625``), then the process exits within a bounded budget.
- :class:`Revealer` shows a file in the OS file manager, only for a server
  the desktop shell started (``--desktop``).
- :func:`watch_stdin_eof` (``--exit-on-stdin-eof``): when the shell's pipe
  closes, however the shell ended, the server takes its SIGTERM path.

protocol.md "Desktop app (wave 8)" is the contract.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from argos.server.errors import ApiError
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub
    from argos.server.settings import Settings

logger = logging.getLogger(__name__)

#: The whole shutdown's bound: a CLI server still in its stages after this
#: ends its process at once (protocol.md "Shutdown (A7)").
SHUTDOWN_BUDGET_S = 60.0
#: Exit status of a server that overran :data:`SHUTDOWN_BUDGET_S`.
OVERRUN_EXIT_STATUS = 70
#: Between the ``exit`` event and the exit request, so the event reaches clients.
_EXIT_GRACE_S = 0.3
#: How long reveal waits for the file manager command's answer.
_REVEAL_WAIT_S = 5.0

#: ``(id, label)`` in the order ``Hub.shutdown`` runs them; ``exit`` is last.
STAGES: tuple[tuple[str, str], ...] = (
    ("sequence", "Stopping the sequence"),
    ("services", "Stopping background tasks"),
    ("devices", "Closing the equipment connections"),
    ("files", "Finishing file writes"),
    ("exit", "Stopping the ARGOS server"),
)
_LABELS = dict(STAGES)

_ENDED_JOB = frozenset({"done", "failed", "cancelled"})
#: Jobs that write files: a quit would cut what they write.
WRITE_JOBS = frozenset({"export", "support_bundle", "rerun"})
_JOB_TEXT = {
    "discovery": "Searching the network for devices.",
    "site_search": "Searching for a place.",
    "field_solve": "Plate-solving the frame.",
    "file_solve": "Plate-solving a file.",
    "file_catalogue": "Querying the catalogue for a file.",
    "sessions_scan": "Scanning the sessions folder.",
    "session_open": "Opening a session.",
    "export": "Writing an export file.",
    "support_bundle": "Writing a support bundle.",
    "rerun": "Re-running photometry",
}


def _item(kind: str, text: str, job: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": text,
        "job_id": job["id"] if job else None,
        "job_kind": job["kind"] if job else None,
    }


def _seconds(value: Any) -> str:
    try:
        return f"{float(value):g} s"
    except (TypeError, ValueError):
        return "?"


def _run_item(record: dict[str, Any]) -> dict[str, Any]:
    name = record.get("object_name")
    state = record.get("state")
    progress = f"{record.get('frames_done') or 0} of {record.get('frames_total') or 0} frames"
    # "SS Cyg, 34 of 120 frames"; without a name the count comes first (design review W8).
    detail = f"{name}, {progress}" if name else f"{progress} (no object name)"
    if state == "waiting":
        text = f"A sequence waits for its start time{f': {name}' if name else ''}."
    elif state == "stopping":
        text = f"A sequence is stopping: {name}." if name else "A sequence is stopping."
    elif state in ("pausing", "paused"):
        text = f"A sequence is paused: {detail}."
    else:
        text = f"A sequence is running: {detail}."
    return _item("run", text)


def _job_item(job: dict[str, Any]) -> dict[str, Any]:
    kind = str(job.get("kind"))
    text = _JOB_TEXT.get(kind, f"A {kind.replace('_', ' ')} task is running.")
    if kind == "rerun":
        done, total = job.get("done"), job.get("total")
        text += f" ({int(done or 0)} of {int(total)} frames)." if total else "."
    return _item("write" if kind in WRITE_JOBS else "job", text, job)


def busy_items(hub: "Hub") -> list[dict[str, Any]]:
    """What a quit would stop now, in the order of protocol.md's table."""
    items: list[dict[str, Any]] = []
    with hub._lock:
        run = hub.sequence.record()
        run_active = bool(run.get("active"))
        camera = hub._camera_state
        autofocus = hub._autofocus is not None
        save_waiting = hub._save is not None
        mount_slewing = hub._mount_state.state == "slewing"
        jogging = hub.jog.active()
        writing = hub._saves_in_flight
    if run_active:
        items.append(_run_item(run))
    # The camera and an autofocus of the run belong to its item.
    if not run_active or camera.owner not in ("sequence", "autofocus"):
        if camera.state == "live" or camera.owner == "live":
            items.append(_item("exposure", "Live view is running."))
        elif camera.state == "exposing" and camera.owner != "autofocus":
            current = camera.current or {}
            exposure = current.get("exposure_s", camera.exposure_s)
            items.append(_item("exposure", f"The camera is exposing ({_seconds(exposure)})."))
        elif camera.state == "downloading" and camera.owner != "autofocus":
            items.append(_item("exposure", "The camera is downloading a frame."))
        elif save_waiting:
            items.append(_item("exposure", "A Take shot waits for its frame."))
    if autofocus and not run_active:
        items.append(_item("exposure", "Autofocus is running."))
    if mount_slewing:
        items.append(_item("slew", "The mount is slewing."))
    elif jogging:
        items.append(_item("slew", "The mount is being jogged."))
    # The job manager's lock is taken outside the hub lock (its events take the hub's).
    jobs = [job for job in hub.jobs.list() if job.get("state") not in _ENDED_JOB]
    items += [_job_item(job) for job in jobs if job.get("kind") not in WRITE_JOBS]
    if writing:
        items.append(
            _item(
                "write",
                (
                    "A FITS file is being written."
                    if writing == 1
                    else f"{writing} FITS files are being written."
                ),
            )
        )
    items += [_job_item(job) for job in jobs if job.get("kind") in WRITE_JOBS]
    return items


def _busy_message(items: list[dict[str, Any]]) -> str:
    return "Quitting now would stop this: " + " ".join(item["text"] for item in items)


class ShutdownService:
    """``POST /api/app/shutdown`` (row A7): refusal, stages, the exit.

    ``request_exit`` is set by the CLI (uvicorn's ``should_exit``); without
    it (in-process tests) the stages run and the process stays. A CLI server
    still in its stages after :data:`SHUTDOWN_BUDGET_S` ends at once:
    ``hard_exit`` is ``os._exit`` only when the CLI sets it, so an in-process
    server (tests) only logs the overrun.
    """

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self.request_exit: Callable[[], None] | None = None
        self.hard_exit: Callable[[int], None] | None = None
        self.budget_s = SHUTDOWN_BUDGET_S
        self._lock = threading.Lock()
        self._started: dict[str, Any] | None = None
        self._stage: str | None = None
        self._forced = False
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def closing(self) -> bool:
        """A shutdown was accepted (other changing requests are refused)."""
        return self._started is not None

    def wait(self, timeout: float | None = None) -> bool:
        """Until every stage ran (tests)."""
        return self._done.wait(timeout)

    def request(self, force: bool = False) -> dict[str, Any]:
        """Start the shutdown, or ``409 busy`` with ``what``; idempotent once started."""
        with self._lock:
            if self._started is not None:
                return dict(self._started)
            what = busy_items(self._hub)
            if what and not force:
                raise ApiError(409, "busy", _busy_message(what), details={"what": what})
            self._forced = bool(force)
            self._started = {
                "state": "shutting_down",
                "forced": self._forced,
                "what": what,
                "stages": [{"id": sid, "label": label} for sid, label in STAGES],
                "budget_s": self.budget_s,
            }
            if what:
                logger.warning("Quit forced while busy: %s", " ".join(i["text"] for i in what))
            self._thread = threading.Thread(target=self._run, name="argos-shutdown", daemon=True)
            self._thread.start()
            return dict(self._started)

    def _announce(self, stage: str) -> None:
        self._stage = stage
        index = next(i for i, (sid, _label) in enumerate(STAGES, 1) if sid == stage)
        logger.info("Shutdown %d/%d: %s", index, len(STAGES), _LABELS[stage])
        try:
            self._hub.publish_event(
                "shutdown",
                {
                    "type": "shutdown",
                    "stage": stage,
                    "label": _LABELS[stage],
                    "index": index,
                    "count": len(STAGES),
                    "forced": self._forced,
                    "budget_s": self.budget_s,
                    "t": utc_iso(),
                },
            )
        except Exception:  # a closed bus never stops the shutdown
            logger.exception("Shutdown event %s not sent", stage)

    def _overrun(self) -> None:
        if self._done.is_set():
            return  # the stages ended meanwhile: uvicorn's own exit is bounded
        if self.hard_exit is None:
            logger.error("Shutdown still at stage %s after %g s", self._stage, self.budget_s)
            return
        logger.error(
            "Shutdown still at stage %s after %g s: ending the server process now",
            self._stage,
            self.budget_s,
        )
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        self.hard_exit(OVERRUN_EXIT_STATUS)

    def _run(self) -> None:
        watchdog = threading.Timer(self.budget_s, self._overrun)
        watchdog.daemon = True
        watchdog.start()
        try:
            self._hub.shutdown(stage=self._announce)
        except Exception:
            logger.exception("Shutdown failed at stage %s", self._stage)
        finally:
            watchdog.cancel()  # the budget bounds the stages only
            self._announce("exit")
            self._done.set()
            if self.request_exit is not None:
                time.sleep(_EXIT_GRACE_S)
                self.request_exit()


# ---------------------------------------------------------------------------
# Reveal (A12)
# ---------------------------------------------------------------------------

#: Runs one command: ``(exit status or None while it still runs, stderr text)``.
Runner = Callable[[list[str]], tuple[int | None, str]]


def run_command(argv: list[str], timeout_s: float = _REVEAL_WAIT_S) -> tuple[int | None, str]:
    """Start *argv*, wait up to *timeout_s* for its answer; a slow one is reaped later."""
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        close_fds=True,
        start_new_session=True,
    )
    try:
        _out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        threading.Thread(target=proc.communicate, name="argos-reveal", daemon=True).start()
        return None, ""
    return proc.returncode, (err or b"").decode("utf-8", "replace").strip()


def reveal_commands(path: Path, platform: str | None = None) -> list[tuple[str, list[str]]]:
    """``(method, argv)`` to try in order for *path* on *platform*."""
    platform = platform or sys.platform
    if platform == "darwin":
        return [("open -R", ["/usr/bin/open", "-R", str(path)])]
    if platform == "win32":
        return [("explorer", ["explorer", f"/select,{path}"])]
    commands: list[tuple[str, list[str]]] = []
    dbus = shutil.which("dbus-send")
    if dbus:
        commands.append(
            (
                "FileManager1",
                [
                    dbus,
                    "--session",
                    "--print-reply",
                    "--dest=org.freedesktop.FileManager1",
                    "--type=method_call",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:{path.as_uri()}",
                    "string:",
                ],
            )
        )
    xdg = shutil.which("xdg-open")
    if xdg:
        commands.append(("xdg-open", [xdg, str(path if path.is_dir() else path.parent)]))
    return commands


class Revealer:
    """``POST /api/fs/reveal`` (row A12): desktop app only, allowed roots only."""

    def __init__(self, hub: "Hub", settings: "Settings") -> None:
        self._hub = hub
        self._desktop = bool(getattr(settings, "desktop", False))
        #: The command runner and the platform (tests replace them).
        self.run: Runner = run_command
        self.platform = sys.platform

    def reveal(self, raw: str) -> dict[str, Any]:
        if not self._desktop:
            raise ApiError(
                403,
                "desktop_only",
                "Showing a file in the file manager needs the ARGOS desktop app",
            )
        real, _root = self._hub.fs_roots.resolve(raw, what="path")
        if not real.exists():
            raise ApiError(404, "not_found", f"{real} does not exist")
        commands = reveal_commands(real, self.platform)
        if not commands:
            raise ApiError(
                502, "reveal_failed", "No file manager command was found (dbus-send, xdg-open)"
            )
        errors: list[str] = []
        for method, argv in commands:
            try:
                code, err = self.run(argv)
            except OSError as exc:
                errors.append(f"{method}: {exc.strerror or exc}")
                continue
            # explorer answers 1 even when it shows the file.
            if code in (0, None) or method == "explorer":
                return {"path": str(real), "method": method}
            errors.append(f"{method}: {err or f'exit status {code}'}")
        raise ApiError(
            502, "reveal_failed", "The file manager could not show it: " + "; ".join(errors)
        )


# ---------------------------------------------------------------------------
# --exit-on-stdin-eof
# ---------------------------------------------------------------------------


def _signal_handlers_installed() -> bool:
    """uvicorn installed its SIGTERM handler (``Server.capture_signals``)."""
    return callable(signal.getsignal(signal.SIGTERM))


def watch_stdin_eof(
    fd: int = 0,
    *,
    ready: Callable[[], bool] = _signal_handlers_installed,
    kill: Callable[[int, int], None] = os.kill,
    poll_s: float = 0.05,
) -> threading.Thread:
    """Read *fd* until end of file, then SIGTERM this process (the graceful path).

    The signal waits until *ready* (uvicorn's handlers installed), so an end
    of file during start-up still takes the graceful path.
    """

    def run() -> None:
        try:
            while os.read(fd, 4096):
                pass
            reason = "Standard input closed (the desktop shell is gone): shutting down."
        except OSError as exc:
            reason = f"Standard input unreadable ({exc.strerror or exc}): shutting down."
        while not ready():
            time.sleep(poll_s)
        logger.warning(reason)
        kill(os.getpid(), signal.SIGTERM)

    thread = threading.Thread(target=run, name="argos-stdin-eof", daemon=True)
    thread.start()
    return thread


__all__ = [
    "STAGES",
    "SHUTDOWN_BUDGET_S",
    "Revealer",
    "ShutdownService",
    "busy_items",
    "reveal_commands",
    "run_command",
    "watch_stdin_eof",
]
