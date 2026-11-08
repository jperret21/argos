"""Focuser (rows A34, A35): polled record, Go to, steps, halt and the D9 queue.

A Qt-free port of the focuser commands of ``DeviceSession``
(``device_session.py:705-739``) over ``argos.core.alpaca.focuser.Focuser``,
with the 0.5.0 fixes and what the Qt app left to the web UI:

- **H10**: Go to is bounded by the connected focuser's ``MaxStep`` and never
  clamped silently (``400``); a step is clamped to ``0…MaxStep`` and the
  clamp is reported; moves are refused while autofocus owns the focuser,
  Halt stays accepted;
- **polling** (absent in Qt, 05 P4): position and ``IsMoving`` every 0.5 s
  while moving, every 5 s when idle, the temperature every 10 s;
- **D9**: a move or a step that arrives while the focuser moves is queued
  (steps add up) and sent as one move when the current one ends.

Device calls run on the request thread (FastAPI's threadpool) or on the
poll thread, never on the event loop; they are serialised by one command
lock so a queued move and a halt cannot cross.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

from argos.server.errors import ApiError
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

POLL_MOVING_S = 0.5
POLL_IDLE_S = 5.0
TEMPERATURE_S = 10.0
AF_BUSY = "Autofocus owns the focuser."


def _disconnected() -> dict[str, Any]:
    return {
        "state": "disconnected",
        "name": None,
        "position": None,
        "target": None,
        "queued": None,
        "temperature_c": None,
        "max_step": None,
        "max_increment": None,
        "absolute": None,
        "step_size_um": None,
        "locked_by": None,
        "message": None,
        "t": utc_iso(),
    }


class FocuserService:
    """The focuser's record, its poll thread and the manual commands."""

    def __init__(
        self,
        hub: "Hub",
        poll_moving_s: float = POLL_MOVING_S,
        poll_idle_s: float = POLL_IDLE_S,
        temperature_s: float = TEMPERATURE_S,
    ) -> None:
        self._hub = hub
        self._record: dict[str, Any] = _disconnected()
        self._handle: Any = None
        self._generation = 0
        self._cmd = threading.RLock()  # device commands, in order
        self._queued: int | None = None
        self._moving = False
        self._poll_moving_s = poll_moving_s
        self._poll_idle_s = poll_idle_s
        self._temperature_s = temperature_s
        self._wake = threading.Event()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None
        #: ``"autofocus"`` while an autofocus sweep (or its return) owns the focuser.
        self._locked_by: str | None = None
        #: Called by a Halt while autofocus runs (the hub ends the sweep where it is).
        self.on_halt_during_autofocus: Callable[[], dict[str, Any] | None] | None = None

    # -- record ----------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        return dict(self._record)

    @property
    def handle(self) -> Any:
        return self._handle

    @property
    def position(self) -> int | None:
        return self._record["position"]

    @property
    def temperature_c(self) -> float | None:
        return self._record["temperature_c"]

    @property
    def max_step(self) -> int | None:
        return self._record["max_step"]

    def _set(self, **changes: Any) -> None:
        """Hub lock held: change the record and publish it (only on a real change)."""
        new = {**self._record, **changes}
        if new == self._record:
            return
        new["t"] = utc_iso()
        self._record = new
        self._hub._publish("focuser", self.record())

    def lock(self, owner: str | None) -> None:
        """Autofocus takes (``"autofocus"``) or releases (``None``) the focuser."""
        with self._hub._lock:
            self._locked_by = owner
            if owner is not None:
                self._queued = None
            self._set(locked_by=owner, queued=None if owner else self._record["queued"])

    # -- lifecycle ------------------------------------------------------------

    def attach(self, handle: Any, generation: int) -> None:
        """A focuser connected (connect thread): read it, start the poll thread."""
        try:
            position: int | None = int(handle.get_position())
        except Exception as exc:
            logger.warning("Focuser position unreadable at connect: %s", exc)
            position = None
        temperature = _temperature(handle)
        stop = threading.Event()
        with self._hub._lock:
            self._handle = handle
            self._generation = generation
            self._queued = None
            self._moving = False
            self._locked_by = None
            self._set(
                state="idle",
                name=getattr(handle, "name", None),
                position=position,
                target=position,
                queued=None,
                temperature_c=temperature,
                max_step=_int_or_none(getattr(handle, "max_step", None)),
                max_increment=_int_or_none(getattr(handle, "max_increment", None)),
                absolute=_bool_or_none(getattr(handle, "absolute", None)),
                step_size_um=_float_or_none(getattr(handle, "step_size_um", None)),
                locked_by=None,
                message=None,
            )
            self._stop = stop
            self._thread = threading.Thread(
                target=self._poll,
                args=(handle, generation, stop),
                name="argos-focuser-poll",
                daemon=True,
            )
            self._thread.start()

    def detach(self) -> None:
        with self._hub._lock:
            stop, thread = self._stop, self._thread
            self._stop = self._thread = None
            self._handle = None
            self._generation += 1
            self._queued = None
            self._moving = False
            self._locked_by = None
            self._record = _disconnected()
            self._hub._publish("focuser", self.record())
        if stop is not None:
            stop.set()
        self._wake.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(2.0)

    # -- polling ---------------------------------------------------------------

    def _poll(self, handle: Any, generation: int, stop: threading.Event) -> None:
        next_temperature = time.monotonic() + self._temperature_s
        while not stop.is_set():
            period = self._poll_moving_s if self._moving else self._poll_idle_s
            self._wake.wait(period)
            self._wake.clear()
            if stop.is_set():
                return
            try:
                with self._cmd:
                    position = int(handle.get_position())
                    moving = bool(handle.is_moving())
                    temperature = None
                    if time.monotonic() >= next_temperature:
                        next_temperature = time.monotonic() + self._temperature_s
                        temperature = _temperature(handle)
                    send = None
                    with self._hub._lock:
                        if generation != self._generation:
                            return
                        changes: dict[str, Any] = {"position": position, "message": None}
                        if temperature is not None:
                            changes["temperature_c"] = temperature
                        if not moving and self._queued is not None and self._locked_by is None:
                            send, self._queued = self._queued, None
                            moving = True
                            changes.update(target=send, queued=None)
                        self._moving = moving
                        changes["state"] = "moving" if moving else "idle"
                        self._set(**changes)
                    if send is not None:
                        handle.move_to(send)
            except Exception as exc:
                with self._hub._lock:
                    if generation != self._generation:
                        return
                    self._set(message=f"Focuser poll: {exc}")
                continue
            if send is not None:
                self._hub.log(
                    "cmd", f"Focuser move → {send} (queued)", source="focuser", topic="focuser"
                )

    def wake(self) -> None:
        self._wake.set()

    # -- commands ----------------------------------------------------------------

    def _require(self) -> tuple[Any, int]:
        handle = self._handle
        if handle is None:
            raise ApiError(409, "not_connected", "No focuser connected")
        if self._locked_by is not None:
            raise ApiError(409, "busy", AF_BUSY, details={"owner": self._locked_by})
        return handle, self._generation

    def _command(self, requested: int, sent: int | None, clamped: bool, queued: bool) -> dict:
        return {
            "focuser": self.record(),
            "requested": requested,
            "sent": sent,
            "clamped": clamped,
            "queued": queued,
        }

    def move(self, position: int) -> dict[str, Any]:
        """Go to (``POST /api/focuser/move``): refused outside ``0…MaxStep`` (H10)."""
        with self._hub._lock:
            handle, generation = self._require()
            max_step = self._record["max_step"]
        position = int(position)
        if position < 0 or (max_step is not None and position > max_step):
            top = f"{max_step}" if max_step is not None else "MaxStep"
            raise ApiError(
                400,
                "invalid_argument",
                f"Position {position} is outside 0–{top} (the focuser's MaxStep).",
            )
        return self._go(handle, generation, position, position, False, f"Focuser move → {position}")

    def step(self, delta: int) -> dict[str, Any]:
        """Out (−) / In (+) from the queued or current target, clamped and reported."""
        delta = int(delta)
        with self._cmd:
            with self._hub._lock:
                handle, generation = self._require()
                max_step = self._record["max_step"]
                base = self._queued
            if base is None:
                base = self._record["target"] if self._moving else None
            if base is None:
                try:
                    base = int(handle.get_position())
                except Exception as exc:
                    raise ApiError(502, "device_error", f"Focuser: {exc}") from exc
            requested = base + delta
            top = max_step if max_step is not None else requested
            target = max(0, min(int(top), requested))
            clamped = target != requested
            line = f"Focuser step {delta:+d} → {target}" + (" (clamped)" if clamped else "")
            return self._go(handle, generation, requested, target, clamped, line)

    def _go(
        self, handle: Any, generation: int, requested: int, target: int, clamped: bool, line: str
    ) -> dict[str, Any]:
        with self._cmd:
            try:
                moving = bool(handle.is_moving())
            except Exception as exc:
                raise ApiError(502, "device_error", f"Focuser: {exc}") from exc
            with self._hub._lock:
                if generation != self._generation:
                    raise ApiError(409, "not_connected", "Focuser disconnected during the command")
                if self._locked_by is not None:
                    raise ApiError(409, "busy", AF_BUSY, details={"owner": self._locked_by})
                if moving or self._moving:
                    # D9: no Move while moving; one move when this one ends.
                    self._queued = target
                    self._set(queued=target)
                    result = self._command(requested, None, clamped, True)
                    queued = True
                else:
                    queued = False
            if queued:
                self._hub.log(
                    "info",
                    f"{line} queued: the focuser is moving",
                    source="focuser",
                    topic="focuser",
                )
                self._wake.set()
                return result
            try:
                handle.move_to(target)
            except Exception as exc:
                self._hub.log("error", f"Focuser move: {exc}", source="focuser", topic="focuser")
                raise ApiError(502, "device_error", f"Focuser: {exc}") from exc
            with self._hub._lock:
                self._moving = True
                self._set(state="moving", target=target, queued=None, message=None)
                result = self._command(requested, target, clamped, False)
        self._hub.log("cmd", line, source="focuser", topic="focuser")
        self._wake.set()
        return result

    def halt(self) -> dict[str, Any]:
        """Halt at once and clear the queue; during autofocus, end it where it is (Q-O6)."""
        with self._hub._lock:
            handle = self._handle
            if handle is None:
                raise ApiError(409, "not_connected", "No focuser connected")
            locked = self._locked_by
        if locked is not None and self.on_halt_during_autofocus is not None:
            self.on_halt_during_autofocus()
            with self._hub._lock:
                return self._command(self._record["position"] or 0, None, False, False)
        with self._cmd:
            try:
                handle.halt()
            except Exception as exc:
                self._hub.log("warning", f"Focuser halt: {exc}", source="focuser", topic="focuser")
            try:
                position: int | None = int(handle.get_position())
            except Exception:
                position = None
            with self._hub._lock:
                self._queued = None
                changes: dict[str, Any] = {"queued": None}
                if position is not None:
                    changes.update(position=position, target=position)
                self._set(**changes)
                result = self._command(position or 0, None, False, False)
        self._hub.log("cmd", "Focuser halted", source="focuser", topic="focuser")
        self._wake.set()
        return result

    def note_target(self, target: int) -> None:
        """Autofocus reports a move it sent: the record's ``target`` is the last move
        sent, whoever sent it (the commanded target drawn by the Focuser card)."""
        with self._hub._lock:
            if self._handle is None:
                return
            self._moving = True
            self._set(state="moving", target=int(target))

    def note_position(self, position: int | None, moving: bool | None = None) -> None:
        """Autofocus reports where it drove the focuser (between polls)."""
        with self._hub._lock:
            if self._handle is None:
                return
            changes: dict[str, Any] = {}
            if position is not None:
                changes["position"] = int(position)
            if moving is not None:
                self._moving = moving
                changes["state"] = "moving" if moving else "idle"
            self._set(**changes)


def _temperature(handle: Any) -> float | None:
    reader = getattr(handle, "get_temperature", None)
    try:
        value = reader() if reader is not None else None
        return None if value is None else round(float(value), 2)
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    return None if value is None else bool(value)
