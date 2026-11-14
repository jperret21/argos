"""Keep the computer awake while a run is active (wave 6b, PROPOSAL §3.1).

A sleeping computer stops a run: the exposure, the wheel and the save all
stop with it. While a sequence is active the server holds an OS sleep
assertion with the tools the OS already has (no new dependency):

- macOS: ``caffeinate -i -w <server pid>``, a ``PreventUserIdleSystemSleep``
  assertion named "caffeinate command-line tool" in ``pmset -g assertions``.
  ``-w`` ties it to the server process, so it ends even if the server dies.
- Linux: ``systemd-inhibit --what=idle:sleep --mode=block`` around
  ``tail --pid=<server pid> -f /dev/null`` (it ends with the server too).
- Windows: ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)``
  through ``ctypes``, on a holder thread (the state belongs to the thread
  that set it and ends with it).

The display may still sleep (the Watch view adds ``navigator.wakeLock``);
closing a laptop lid still sleeps most laptops: out of software reach, the
preflight says so.

:class:`KeepAwake` is driven by :meth:`want` (non-blocking, safe under the
hub lock); a small worker thread starts and stops the assertion, so no
process is spawned under a lock. Only the CLI server (``manage_process``)
uses the real OS backends; in-process tests get :class:`NullBackend` or a
fake.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

STATES = ("off", "held", "failed", "unsupported", "disabled")
#: How long the worker waits for a spawned helper to prove it is alive.
_ALIVE_CHECK_S = 0.2
_STOP_WAIT_S = 3.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Assertion(Protocol):
    def release(self) -> None: ...


class Backend(Protocol):
    """One OS method: ``available()`` says whether it can work here and why not."""

    method: str | None

    def available(self) -> tuple[bool, str | None]: ...

    def acquire(self, reason: str) -> Assertion: ...


class _Process:
    """A helper process holding the assertion; released by terminating it."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc

    def release(self) -> None:
        proc = self.proc
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(_STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(_STOP_WAIT_S)


def _spawn(argv: list[str]) -> _Process:
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        close_fds=True,
    )
    try:
        code = proc.wait(_ALIVE_CHECK_S)
    except subprocess.TimeoutExpired:
        return _Process(proc)  # still running: the assertion is held
    err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace").strip()
    raise OSError(
        f"{os.path.basename(argv[0])} exited at once (code {code}){': ' + err if err else ''}"
    )


class CaffeinateBackend:
    """macOS: ``caffeinate -i -w <pid>``."""

    method = "caffeinate"

    def __init__(self, pid: int | None = None) -> None:
        self.pid = pid or os.getpid()

    def available(self) -> tuple[bool, str | None]:
        if shutil.which("caffeinate") is None:
            return False, "caffeinate was not found"
        return True, None

    def acquire(self, reason: str) -> Assertion:
        return _spawn([shutil.which("caffeinate") or "caffeinate", "-i", "-w", str(self.pid)])


class SystemdInhibitBackend:
    """Linux: ``systemd-inhibit`` for as long as the server process lives."""

    method = "systemd-inhibit"

    def __init__(self, pid: int | None = None) -> None:
        self.pid = pid or os.getpid()

    def available(self) -> tuple[bool, str | None]:
        if shutil.which("systemd-inhibit") is None:
            return False, "systemd-inhibit was not found (no systemd)"
        if shutil.which("tail") is None:
            return False, "tail was not found"
        return True, None

    def acquire(self, reason: str) -> Assertion:
        return _spawn(
            [
                shutil.which("systemd-inhibit") or "systemd-inhibit",
                "--what=idle:sleep",
                "--who=ARGOS",
                f"--why={reason}",
                "--mode=block",
                shutil.which("tail") or "tail",
                f"--pid={self.pid}",
                "-f",
                "/dev/null",
            ]
        )


class _WindowsHold:
    """A thread that sets the execution state and keeps it until released."""

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error: str | None = None
        self._thread = threading.Thread(target=self._run, name="argos-keep-awake", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        if self._error is not None:
            raise OSError(self._error)

    def _run(self) -> None:
        import ctypes  # Windows only

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not kernel32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED):
            self._error = "SetThreadExecutionState failed"
            self._ready.set()
            return
        self._ready.set()
        self._stop.wait()
        kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)

    def release(self) -> None:
        self._stop.set()
        self._thread.join(_STOP_WAIT_S)


class WindowsBackend:
    method = "SetThreadExecutionState"

    def available(self) -> tuple[bool, str | None]:
        return True, None

    def acquire(self, reason: str) -> Assertion:
        return _WindowsHold()


class NullBackend:
    """No OS call: in-process tests and platforms without a method."""

    def __init__(self, reason: str = "keep-awake is off in this process") -> None:
        self.method: str | None = None
        self._reason = reason

    def available(self) -> tuple[bool, str | None]:
        return False, self._reason

    def acquire(self, reason: str) -> Assertion:  # pragma: no cover - never called
        raise OSError(self._reason)


def os_backend(platform: str | None = None) -> Backend:
    """The real backend for this OS."""
    platform = platform or sys.platform
    if platform == "darwin":
        return CaffeinateBackend()
    if platform.startswith("linux"):
        return SystemdInhibitBackend()
    if platform == "win32":
        return WindowsBackend()
    return NullBackend(f"no keep-awake method on {platform}")


class KeepAwake:
    """The run's sleep assertion: wanted while a run is active, held by a worker."""

    def __init__(
        self,
        backend: Backend,
        on_change: Callable[[], None] = lambda: None,
        enabled: Callable[[], bool] = lambda: True,
        log: Callable[[str, str], None] = lambda level, text: None,
    ) -> None:
        self.backend = backend
        self._on_change = on_change
        self._enabled = enabled
        self._log = log
        self._cond = threading.Condition()
        self._wanted: str | None = None  # the reason, or None
        self._held: Assertion | None = None
        #: The reason the last acquire was made for (success or not): no retry loop.
        self._attempted: str | None = None
        self._record: dict[str, Any] = self._idle_record()
        self._thread: threading.Thread | None = None
        self._closed = False
        #: The worker is inside backend.acquire(): settle() and close() wait for it.
        self._acquiring = False
        #: ``enabled()`` as last read outside the condition (``recheck``).
        self._on = bool(enabled())
        #: Assertions taken and released (tests and the smoke check).
        self.acquired = 0
        self.released = 0

    # -- records ---------------------------------------------------------------------

    def _idle_record(self) -> dict[str, Any]:
        return self._idle_record_for(bool(self._enabled()))

    def _idle_record_for(self, enabled: bool) -> dict[str, Any]:
        ok, why = self.backend.available()
        if not ok:
            state = "unsupported"
        elif not enabled:
            state, why = "disabled", "Keep-awake is off in Settings › Alerts."
        else:
            state, why = "off", None
        return {
            "state": state,
            "method": self.backend.method if ok else None,
            "since": None,
            "reason": None,
            "message": why,
        }

    def record(self) -> dict[str, Any]:
        with self._cond:
            return dict(self._record)

    def capability(self) -> tuple[bool, str | None, str | None]:
        """For the preflight: (works, method, why not)."""
        ok, why = self.backend.available()
        if ok and not self._enabled():
            return False, None, "keep-awake is off in Settings › Alerts"
        return ok, self.backend.method if ok else None, why

    # -- driving -----------------------------------------------------------------------

    def want(self, reason: str | None) -> None:
        """Hold (a reason) or release (None); non-blocking, any thread, any lock."""
        with self._cond:
            if self._closed or reason == self._wanted:
                return
            self._wanted = reason
            self._wake()

    def recheck(self) -> None:
        """``alerts.keep_awake`` changed: apply it to the run in progress now.

        Turned off during a run, the assertion is released; turned on, it is
        taken (before, both waited for the next run).
        """
        on = bool(self._enabled())
        with self._cond:
            if self._closed:
                return
            self._on = on
            self._attempted = None
            if self._wanted is None:
                self._record = self._idle_record_for(on)
            self._wake()
        self._on_change()

    def _wake(self) -> None:
        """Condition held: start the worker if needed and notify it."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._worker, name="argos-keep-awake", daemon=True
            )
            self._thread.start()
        self._cond.notify_all()

    def settle(self, timeout: float = 5.0) -> bool:
        """Wait until the held state matches the wanted one (tests, shutdown)."""
        with self._cond:
            return self._cond.wait_for(lambda: self._closed or not self._needs_work(), timeout)

    def close(self) -> None:
        """Server shutdown: release now (synchronously) and stop the worker."""
        self.want(None)
        self.settle(_STOP_WAIT_S + 1.0)
        with self._cond:
            self._closed = True
            held, self._held = self._held, None
            self._cond.notify_all()
        if held is not None:  # the worker did not get there: release here
            self._release(held)

    def _needs_work(self) -> bool:
        """Condition held."""
        if self._acquiring:
            return True
        wanted, held = self._wanted, self._held
        if wanted is None:
            return held is not None or self._record["state"] in ("held", "failed")
        if held is None:
            return self._attempted != wanted
        return not self._on or self._record.get("reason") != wanted

    def _worker(self) -> None:
        while True:
            with self._cond:
                while not self._closed and not self._needs_work():
                    self._cond.wait()
                if self._closed:
                    return
                wanted, held = self._wanted, self._held
                # Released when the run ends, or when Settings turned keep-awake off.
                drop = held is not None and (wanted is None or not self._on)
                if drop:
                    self._held = None
                if wanted is None:
                    self._attempted = None
                elif drop:
                    self._attempted = wanted  # off in Settings: no re-acquire
                self._acquiring = wanted is not None and held is None
            if drop:
                self._release(held)  # type: ignore[arg-type]
                self._set(self._idle_record())
            elif wanted is None:
                self._set(self._idle_record())
            elif held is None:
                try:
                    self._acquire(wanted)
                finally:
                    with self._cond:
                        self._acquiring = False
                        self._cond.notify_all()
            else:  # a new reason while held: say it
                self._set({**self.record(), "reason": wanted})

    def _acquire(self, reason: str) -> None:
        ok, _why = self.backend.available()
        if not ok or not self._enabled():
            record = self._idle_record()
        else:
            try:
                held = self.backend.acquire(reason)
            except Exception as exc:  # OSError, ctypes errors: the run goes on
                self._log(
                    "warning",
                    f"The computer could not be kept awake ({self.backend.method}): {exc}",
                )
                record = {
                    "state": "failed",
                    "method": self.backend.method,
                    "since": None,
                    "reason": None,
                    "message": str(exc),
                }
            else:
                with self._cond:
                    # close() or a Stop arrived while acquire() ran: never keep it
                    # (before, close() returned at once and this assertion was kept).
                    stale = self._closed or self._wanted != reason
                    if not stale:
                        self._held = held
                    self.acquired += 1
                if stale:
                    self._release(held)
                    with self._cond:
                        self._attempted = reason
                    self._set(self._idle_record())
                    return
                record = {
                    "state": "held",
                    "method": self.backend.method,
                    "since": _utc_iso(),
                    "reason": reason,
                    "message": None,
                }
                self._log(
                    "info", f"Keeping the computer awake during the run ({self.backend.method})."
                )
        with self._cond:
            self._attempted = reason
        self._set(record)

    def _release(self, held: Assertion) -> None:
        try:
            held.release()
        except Exception:
            logger.warning("Keep-awake release failed", exc_info=True)
        with self._cond:
            self.released += 1
        self._log("info", "The computer may sleep again: the run ended.")

    def _set(self, record: dict[str, Any]) -> None:
        with self._cond:
            changed = record != self._record
            self._record = record
            self._cond.notify_all()
        if changed:
            self._on_change()


__all__ = [
    "CaffeinateBackend",
    "KeepAwake",
    "NullBackend",
    "SystemdInhibitBackend",
    "WindowsBackend",
    "os_backend",
]
