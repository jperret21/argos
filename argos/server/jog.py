"""Mount jog with a server-side dead-man (row A30).

A port of the Manual Control dialog's ``MoveAxis`` jog (``telescope.py:
564-592``, ``device_session.py:45-67, 665-679``) with the 0.5.0 fix H3 and
the parts it left to the web UI:

- **every axis it moved** is tracked on its own; a stop names its axis, and
  "stop" without an axis stops both whatever the server believes (the ■
  button);
- **a failed stop is retried**: the axis stays in ``stop_pending`` (WARN),
  retried every 0.5 s, five times, then an ERROR says to use Abort, and it
  stays pending (``stop_failed``), retried every 5 s until a stop or Abort
  succeeds: the record never shows a failed stop as resolved;
- **a dead-man** (new): an axis whose renewal does not arrive within
  ``deadman_s`` is stopped by the server; so are the axes of a client whose
  event socket closes or reports a blur (``{"type": "jog_stop"}``);
- ``MoveAxis`` runs off the event loop, and every device call goes through
  one lock in arrival order, so a stop can never overtake its start (the
  reason 0.5.0 kept it on the UI thread).

Admission (review of wave 3): a renewal is answered under the hub lock and
never waits on device I/O (a slow ``MoveAxis`` would otherwise pile up
renewals in the request threads); command numbers are compared per client
**and per axis**, and a stop is never dropped as stale; a start that waited
longer than the dead-man for the device lock, or that was sent before its
client's socket closed or blurred, is dropped; a renewal (``renew: true``)
never restarts an axis the server stopped; another client's axis is busy.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from argos.server.errors import ApiError
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

AXES = ("primary", "secondary")
#: The Qt dialog's top speed (manual_control_dialog.py:49-58: 0.5, 2 and 5 °/s).
MAX_RATE_DEG_S = 5.0
DEADMAN_S = 1.0
STOP_RETRY_S = 0.5
STOP_RETRIES = 5
#: After the ERROR, a failed stop keeps being retried, this much slower.
STOP_FAILED_SLOWDOWN = 10
_WATCH_S = 0.05
_NEVER = float("-inf")


@dataclass
class _Axis:
    rate: float = 0.0
    client: str | None = None
    renewed: float = 0.0


class JogService:
    """Per-axis jog state, the dead-man watcher and the stop retries."""

    def __init__(
        self,
        hub: "Hub",
        deadman_s: float = DEADMAN_S,
        retry_s: float = STOP_RETRY_S,
        retries: int = STOP_RETRIES,
        max_rate_deg_s: float = MAX_RATE_DEG_S,
    ) -> None:
        self._hub = hub
        self.deadman_s = float(deadman_s)
        self._retry_s = float(retry_s)
        self._retries = int(retries)
        self.max_rate_deg_s = float(max_rate_deg_s)
        self._io = threading.Lock()  # MoveAxis calls, in arrival order
        self._axes = {axis: _Axis() for axis in AXES}
        self._stop_pending: dict[str, int] = {}  # axis -> failed attempts
        #: Axes whose stop failed past the retries (ERROR said): retried slower.
        self._stop_failed: set[str] = set()
        self._last_stop: dict[str, Any] | None = None
        #: (client, axis) -> highest command number seen (starts and stops).
        self._client_seq: dict[tuple[str, str], int] = {}
        #: client -> when the server stopped its axes (socket closed, blur).
        self._gone: dict[str, float] = {}
        #: axis -> (rate, client) of a start waiting for, or inside, MoveAxis.
        self._starting: dict[str, tuple[float, str | None]] = {}
        self._watcher: threading.Thread | None = None
        self._wake = threading.Event()
        self._closed = False

    # -- record (hub lock held) -------------------------------------------------

    def record(self) -> dict[str, Any]:
        return {
            "primary": self._axes["primary"].rate,
            "secondary": self._axes["secondary"].rate,
            "stop_pending": sorted(self._stop_pending),
            "stop_failed": sorted(self._stop_failed),
            "max_rate_deg_s": self.max_rate_deg_s,
            "deadman_s": self.deadman_s,
            "last_stop": dict(self._last_stop) if self._last_stop else None,
        }

    def active(self) -> bool:
        return any(a.rate for a in self._axes.values()) or bool(self._stop_pending)

    def _publish(self) -> None:
        """Hub lock held: the jog record into MountState (a ``status`` and a ``mount``)."""
        self._hub._set_mount_extras(jog=self.record())

    # -- commands -------------------------------------------------------------------

    def jog(
        self,
        axis: str,
        rate: float,
        client: str | None = None,
        seq: int | None = None,
        renew: bool = False,
    ) -> dict[str, Any]:
        """Start an axis, or renew it when the rate is unchanged (no device call).

        The answer is the MountState plus ``jog_command``: ``started``,
        ``renewed``, ``pending`` (a renewal of a start still in its
        ``MoveAxis``) or ``ignored`` with ``why`` (``stale``: an older
        number than one this client already sent for the axis; ``stopped``:
        a renewal of an axis the server stopped; ``late``: a start that
        waited longer than the dead-man, or was sent before this client's
        socket closed or blurred).
        """
        hub = self._hub
        received = time.monotonic()
        rate = float(rate)
        if axis not in AXES:
            raise ApiError(400, "invalid_argument", f"Unknown axis {axis!r}")
        if rate == 0.0 or abs(rate) > self.max_rate_deg_s:
            raise ApiError(
                400,
                "invalid_argument",
                f"rate_deg_s must be non-zero and within ±{self.max_rate_deg_s:g} °/s",
            )
        # Phase 1, hub lock only: refusals, stale numbers and renewals never wait on I/O.
        with hub._lock:
            hub._require("mount")
            if self._stale(client, axis, seq):
                return self._answer("ignored", "stale")
            if client is not None and self._gone.get(client, _NEVER) >= received:
                return self._answer("ignored", "late")
            self._refusals(axis, rate, client)
            current = self._axes[axis]
            if current.rate == rate and axis not in self._stop_pending:
                current.renewed = time.monotonic()
                current.client = client or current.client
                return self._answer("renewed")
            starting = self._starting.get(axis)
            if starting is not None and starting[0] == rate:
                return self._answer("pending")
            if renew:
                # The server stopped this axis (dead-man, socket, Abort…): a
                # renewal never restarts it; the observer presses again.
                return self._answer("ignored", "stopped")
        # Phase 2: the device lock, in arrival order behind any start or stop.
        stop_after: str | None = None
        with self._io:
            with hub._lock:
                mount = hub._require("mount")
                if self._newer_command(client, axis, seq):
                    return self._answer("ignored", "stale")
                if client is not None and self._gone.get(client, _NEVER) >= received:
                    return self._answer("ignored", "late")
                if time.monotonic() - received > self.deadman_s:
                    # Waited behind a slow MoveAxis longer than the dead-man: the
                    # finger may be gone; a fresh press or renewal starts it again.
                    return self._answer("ignored", "late")
                self._refusals(axis, rate, client)
                current = self._axes[axis]
                if current.rate == rate and axis not in self._stop_pending:
                    current.renewed = time.monotonic()
                    current.client = client or current.client
                    return self._answer("renewed")
                self._starting[axis] = (rate, client)
            try:
                mount.move_axis(AXES.index(axis), rate)
            except Exception as exc:
                text = str(exc) or exc.__class__.__name__
                hub.log("error", f"Jog: {text}", source="mount", topic="mount")
                # A start that raised may still have reached the mount (H3).
                with hub._lock:
                    self._starting.pop(axis, None)
                    self._stop_pending[axis] = self._stop_pending.get(axis, 0)
                    self._publish()
                self._wake.set()
                self._ensure_watcher()
                if "park" in text.lower():
                    raise ApiError(409, "parked", text) from exc
                raise ApiError(502, "device_error", text) from exc
            with hub._lock:
                self._starting.pop(axis, None)
                was = self._axes[axis].rate
                self._axes[axis] = _Axis(rate=rate, client=client, renewed=time.monotonic())
                self._stop_pending.pop(axis, None)
                self._stop_failed.discard(axis)
                self._publish()
                if client is not None and self._gone.get(client, _NEVER) >= received:
                    stop_after = "the client's event socket closed or the window blurred"
                result = self._answer("started")
        if stop_after is not None:
            # The client went away while its start was inside MoveAxis.
            self._stop_axes([axis], stop_after, quiet=True)
            with hub._lock:
                return self._answer("ignored", "late")
        if not was:
            hub.log("cmd", f"Jog {axis} {rate:+g} °/s", source="mount", topic="mount")
        self._ensure_watcher()
        return result

    def _refusals(self, axis: str, rate: float, client: str | None) -> None:
        """Hub lock held: parked, a GoTo slew, or another client's axis."""
        state = self._hub._mount_state
        if state.state == "parked":
            raise ApiError(409, "parked", "Mount is parked — unpark before jogging")
        if state.state == "slewing" and not self.active() and not self._starting:
            raise ApiError(
                409,
                "busy",
                "The mount is slewing to a target — Abort the slew before jogging.",
                details={"owner": "goto"},
            )
        current = self._axes[axis]
        owner = current.client if current.rate else None
        starting = self._starting.get(axis)
        if owner is None and starting is not None:
            owner = starting[1]
        if client is not None and owner is not None and owner != client:
            # Two windows on one axis would reverse it at every renewal (review).
            raise ApiError(
                409,
                "busy",
                f"Another window is jogging the {axis} axis — it must release it first.",
                details={"owner": "jog"},
            )

    def _answer(self, outcome: str, why: str | None = None) -> dict[str, Any]:
        """Hub lock held: the MountState with how this command was handled."""
        result = self._hub._mount_state.to_dict()
        result["jog_command"] = {"outcome": outcome, "why": why}
        return result

    def stop(
        self,
        axis: str | None = None,
        *,
        reason: str = "client",
        client: str | None = None,
        seq: int | None = None,
        quiet: bool = False,
    ) -> dict[str, Any]:
        """Stop one axis, or both whatever the server believes (``axis=None``).

        A stop is never dropped as stale (it is idempotent and safe); its
        number only invalidates this client's older starts of that axis.
        """
        hub = self._hub
        if axis is not None and axis not in AXES:
            raise ApiError(400, "invalid_argument", f"Unknown axis {axis!r}")
        axes = [axis] if axis is not None else list(AXES)
        with hub._lock:
            hub._require("mount")
            if client is not None and seq is not None:
                for name in axes:
                    key = (client, name)
                    self._client_seq[key] = max(self._client_seq.get(key, seq), seq)
        self._stop_axes(axes, reason, quiet=quiet)
        with hub._lock:
            return hub._mount_state.to_dict()

    def _stale(self, client: str | None, axis: str, seq: int | None) -> bool:
        """Hub lock held: a start or renewal older than this client's last command on the axis."""
        if client is None or seq is None:
            return False
        key = (client, axis)
        last = self._client_seq.get(key)
        if last is not None and seq <= last:
            return True
        self._client_seq[key] = seq
        return False

    def _newer_command(self, client: str | None, axis: str, seq: int | None) -> bool:
        """Hub lock held: a later command (a stop) of this client on the axis came meanwhile."""
        if client is None or seq is None:
            return False
        return self._client_seq.get((client, axis), seq) > seq

    def _stop_axes(self, axes: list[str], reason: str, quiet: bool = False) -> list[str]:
        """Send ``MoveAxis(axis, 0)`` to each axis; failures stay pending. Returns the failed."""
        hub = self._hub
        failed: list[str] = []
        stopped: list[str] = []
        with self._io:
            with hub._lock:
                mount = hub._slots["mount"].handle
            if mount is None:
                with hub._lock:
                    for axis in axes:
                        self._axes[axis] = _Axis()
                        self._stop_pending.pop(axis, None)
                    self._publish()
                return []
            for axis in axes:
                with hub._lock:
                    was_moving = bool(self._axes[axis].rate) or axis in self._stop_pending
                try:
                    mount.move_axis(AXES.index(axis), 0.0)
                except Exception as exc:
                    failed.append(axis)
                    text = str(exc) or exc.__class__.__name__
                    with hub._lock:
                        attempts = self._stop_pending.get(axis, 0) + 1
                        self._stop_pending[axis] = attempts
                        self._axes[axis].renewed = time.monotonic()
                        self._publish()
                    if attempts == 1:
                        hub.log(
                            "warning",
                            f"Stop failed ({axis} axis): {text} — retrying.",
                            source="mount",
                            topic="mount",
                        )
                    elif attempts == self._retries + 1:
                        # Still pending (never shown as resolved): retried slower,
                        # never re-entering through the dead-man (review).
                        hub.log(
                            "error",
                            f"Stop failed again ({axis} axis): {text} — the mount may still be "
                            "moving; use Abort on the Mount card.",
                            source="mount",
                            topic="mount",
                        )
                        with hub._lock:
                            self._stop_failed.add(axis)
                            self._publish()
                    continue
                with hub._lock:
                    confirmed = axis in self._stop_failed
                    self._axes[axis] = _Axis()
                    self._stop_pending.pop(axis, None)
                    self._stop_failed.discard(axis)
                    if was_moving:
                        self._last_stop = {"axis": axis, "reason": reason, "t": utc_iso()}
                    self._publish()
                if confirmed:
                    hub.log("ok", f"Stop confirmed ({axis} axis).", source="mount", topic="mount")
                if was_moving:
                    stopped.append(axis)
        if stopped and not quiet and reason != "client":
            names = " and ".join(stopped)
            hub.log("info", f"Jog stopped ({names}): {reason}", source="mount", topic="mount")
        if failed:
            self._ensure_watcher()
        return failed

    # -- dead-man -------------------------------------------------------------------

    def client_gone(self, client: str | None, why: str = "the client's socket closed") -> None:
        """Stop every axis this client is jogging (socket closed, blur, hidden tab)."""
        if not client:
            return
        with self._hub._lock:
            # Starts this client sent before now are dropped (queued or late).
            self._gone[client] = time.monotonic()
            axes = [name for name, a in self._axes.items() if a.rate and a.client == client]
        if axes:
            self._hub.log(
                "warning",
                f"Jog stopped by the server: {why} ({' and '.join(axes)} axis).",
                source="mount",
                topic="mount",
            )
            self._stop_axes(axes, why, quiet=True)

    def stop_all_before(self, action: str) -> None:
        """Abort, Park and GoTo first stop any jogging axis (device calls in order)."""
        with self._hub._lock:
            if not self.active():
                return
        self._stop_axes(list(AXES), action, quiet=True)

    def mount_gone(self) -> None:
        """The mount was disconnected or lost: nothing can be stopped any more."""
        with self._hub._lock:
            self._axes = {axis: _Axis() for axis in AXES}
            self._stop_pending.clear()
            self._stop_failed.clear()
            self._client_seq.clear()
            self._gone.clear()
            self._starting.clear()

    def close(self) -> None:
        self._closed = True
        self._wake.set()

    def _ensure_watcher(self) -> None:
        with self._hub._lock:
            if self._watcher is not None and self._watcher.is_alive():
                self._wake.set()
                return
            self._watcher = threading.Thread(
                target=self._watch, name="argos-jog-deadman", daemon=True
            )
            self._watcher.start()

    def _watch(self) -> None:
        """Stop axes whose renewal is overdue; retry failed stops."""
        hub = self._hub
        while not self._closed:
            self._wake.wait(_WATCH_S)
            self._wake.clear()
            now = time.monotonic()
            with hub._lock:
                if not self.active():
                    self._watcher = None
                    return
                overdue = [
                    name
                    for name, a in self._axes.items()
                    if a.rate
                    and name not in self._stop_pending
                    and now - a.renewed > self.deadman_s
                ]
                retry = [
                    name
                    for name in self._stop_pending
                    if now - self._axes[name].renewed
                    >= self._retry_s * (STOP_FAILED_SLOWDOWN if name in self._stop_failed else 1)
                ]
            for axis in overdue:
                hub.log(
                    "warning",
                    f"Jog stopped by the server: no renewal for {self.deadman_s:.1f} s "
                    f"({axis} axis).",
                    source="mount",
                    topic="mount",
                )
            if overdue:
                self._stop_axes(overdue, "no renewal", quiet=True)
            if retry:
                self._stop_axes(retry, "retry", quiet=True)
