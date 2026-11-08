"""Filter wheel (row A28): moves off the event loop, every outcome published.

A Qt-free port of ``DeviceSession.move_filter`` and ``_FilterMoveRunnable``
(``device_session.py:85-122, 681-746``) with the 0.5.0 fixes:

- **H9**: errors always end ``moving``. A refused move reads the wheel back
  and reports the slot it is really on (``idle`` with the refusal as
  ``message``), or ``error`` "position unknown" when it cannot be read;
- **S1 review**: the slot the wheel last *reported it settled on* and the
  time that move ended are kept (``_note_filter_move_ended``,
  ``device_session.py:704-708``), so a Dark Take shot can require the wheel
  settled on Dark and a frame exposed while it turned is never saved;
- **S3**: every mover goes through here and publishes (a Camera-card
  select, a Dark Take shot, later a sequence), and the hub makes
  ``CameraState.settings.filter`` follow the settled slot.

The settle poll is the Qt one: position −1 while turning, read every
0.15 s, 20 s at most.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from argos.core.imaging.sequencer import DARK_FILTER_NAME
from argos.server.errors import ApiError
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: ``_FilterMoveRunnable._settle`` (device_session.py:118-122).
SETTLE_POLL_S = 0.15
SETTLE_TIMEOUT_S = 20.0
STILL_TURNING = "Still turning after 20 s: position unknown"


def _disconnected() -> dict[str, Any]:
    return {
        "state": "disconnected",
        "name": None,
        "slots": [],
        "dark_slot": False,
        "position": None,
        "slot": None,
        "target": None,
        "message": None,
        "settled_utc": None,
    }


class FilterWheelService:
    """The wheel's record and its moves; the hub's lock guards the record."""

    def __init__(self, hub: "Hub", settle_poll_s: float = SETTLE_POLL_S) -> None:
        self._hub = hub
        self._record: dict[str, Any] = _disconnected()
        self._handle: Any = None
        self._generation = 0
        #: When the last move ended (settled or failed): compared with a frame's start.
        self._settled_at: datetime | None = None
        self._moving = False
        self._settle_poll_s = settle_poll_s
        #: Called (outside the hub lock) with the settled slot name after every move.
        self.on_settled: Callable[[str | None], None] | None = None

    # -- state (hub lock held by the callers that need consistency) ----------

    def record(self) -> dict[str, Any]:
        return dict(self._record, slots=list(self._record["slots"]))

    @property
    def connected(self) -> bool:
        return self._handle is not None

    @property
    def moving(self) -> bool:
        return self._moving

    @property
    def slot(self) -> str | None:
        """The slot the wheel last reported it settled on (None: unknown or moving)."""
        return self._record["slot"]

    @property
    def target(self) -> str | None:
        return self._record["target"]

    @property
    def settled_at(self) -> datetime | None:
        return self._settled_at

    @property
    def has_dark_slot(self) -> bool:
        """A wheel is connected and its profile has an opaque Dark slot (S1)."""
        return self._handle is not None and bool(self._record["dark_slot"])

    @property
    def handle(self) -> Any:
        return self._handle

    def slot_index(self, name: str) -> int | None:
        """Slot whose name matches *name*, case-insensitive (``filter_position_for``)."""
        wanted = str(name).strip().lower()
        for index, slot in enumerate(self._record["slots"]):
            if str(slot).lower() == wanted:
                return index
        return None

    def canonical(self, name: str) -> str | None:
        index = self.slot_index(name)
        return None if index is None else self._record["slots"][index]

    def not_on_dark(self) -> str | None:
        """Why the wheel cannot be trusted to sit on Dark (``_wheel_not_on_dark``,
        ``acquisition_engine.py:477-493``), or ``None``."""
        if self._moving:
            return (
                f"the filter wheel is still turning. Wait until it has settled on "
                f"'{DARK_FILTER_NAME}' (the Seestar has no shutter)."
            )
        slot = self._record["slot"]
        if slot is None:
            return (
                f"the filter wheel's position is unknown. Select Filter "
                f"'{DARK_FILTER_NAME}' again and wait for the wheel to settle."
            )
        if slot.strip().lower() != DARK_FILTER_NAME.lower():
            return f"the filter wheel reports '{slot}', not '{DARK_FILTER_NAME}'."
        return None

    def moved_since(self, start: datetime | None) -> bool:
        """The wheel turned, or is turning, since *start* (``_wheel_moved_during``,
        ``acquisition_engine.py:495-510``)."""
        if self._handle is None:
            return False
        if self._moving:
            return True
        settled = self._settled_at
        if settled is None:
            return False
        if start is None:
            return True  # cannot compare: assume moved
        return settled > start

    def _set(self, **changes: Any) -> None:
        """Hub lock held: change the record, publish it and the device row."""
        hub = self._hub
        self._record = {**self._record, **changes}
        slot = hub._slots["filterwheel"]
        if slot.state == "connected":
            record = self._record
            info = (
                f"moving to {record['target']}"
                if record["state"] == "moving"
                else (record["slot"] or record["message"] or "position unknown")
            )
            if slot.info != info:
                slot.info = info
                hub._publish_status()
        hub._publish("filterwheel", self.record())

    # -- lifecycle ------------------------------------------------------------

    def attach(self, handle: Any, generation: int) -> None:
        """A wheel connected: read where it is (connect thread, before the hub lock)."""
        slots = [str(s) for s in getattr(handle, "slots", ())]
        name = getattr(handle, "name", None)
        position: int | None = None
        slot_name: str | None = None
        message: str | None = None
        try:
            position = int(handle.get_position())
            if position >= 0:
                slot_name = handle.position_name()
            else:
                position, message = None, "Moving"
        except Exception as exc:
            # A wheel whose position cannot be read is not trusted (H9).
            position, message = None, f"position unknown ({exc})"
        with self._hub._lock:
            self._handle = handle
            self._generation = generation
            self._moving = False
            self._settled_at = None
            self._set(
                state="idle" if message is None else "error",
                name=name,
                slots=slots,
                dark_slot=any(s.lower() == DARK_FILTER_NAME.lower() for s in slots),
                position=position,
                slot=slot_name,
                target=None,
                message=message,
                settled_utc=None,
            )
        if slot_name is not None and self.on_settled is not None:
            self.on_settled(slot_name)

    def detach(self) -> None:
        with self._hub._lock:
            self._handle = None
            self._generation += 1
            self._moving = False
            self._record = _disconnected()
            self._hub._publish("filterwheel", self.record())

    # -- moves ----------------------------------------------------------------

    def select(self, name: str, *, reason: str | None = None) -> dict[str, Any]:
        """Start a move to the slot *name* (``POST /api/filterwheel/select``).

        Answers at once (``moving``); a worker thread waits for the wheel to
        settle and publishes the outcome. *reason* replaces the CMD line
        (a Dark Take shot says why the wheel moves).
        """
        hub = self._hub
        with hub._lock:
            handle = self._handle
            if handle is None:
                raise ApiError(409, "not_connected", "No filter wheel connected")
            index = self.slot_index(name)
            if index is None:
                slots = ", ".join(self._record["slots"]) or "none"
                raise ApiError(
                    400, "invalid_argument", f"No wheel slot named '{name}' (slots: {slots})"
                )
            if self._moving:
                raise ApiError(
                    409,
                    "busy",
                    f"The filter wheel is moving to '{self._record['target']}' — wait for it.",
                    details={"owner": "filterwheel"},
                )
            target = self._record["slots"][index]
            generation = self._generation
            self._moving = True
            self._set(state="moving", position=None, slot=None, target=target, message=None)
            thread = threading.Thread(
                target=self._run_move,
                args=(handle, index, target, generation),
                name="argos-filter-move",
                daemon=True,
            )
            thread.start()
        hub.log(
            "cmd",
            reason or f"Filter → {target}",
            source="filterwheel",
            topic="camera",
        )
        with hub._lock:
            return self.record()

    def _settle(self, handle: Any) -> tuple[int, str]:
        deadline = time.monotonic() + SETTLE_TIMEOUT_S
        while handle.get_position() == -1 and time.monotonic() < deadline:
            time.sleep(self._settle_poll_s)
        return int(handle.get_position()), str(handle.position_name())

    def _run_move(self, handle: Any, index: int, target: str, generation: int) -> None:
        hub = self._hub
        refusal: str | None = None
        try:
            handle.set_position(index)
            position, name = self._settle(handle)
        except Exception as exc:
            refusal = str(exc) or exc.__class__.__name__
            hub.log("error", f"Filter move: {refusal}", source="filterwheel", topic="camera")
            try:
                position, name = self._settle(handle)
            except Exception:
                position, name = -1, ""
        settled_name: str | None = None
        with hub._lock:
            if generation != self._generation or handle is not self._handle:
                return  # disconnected meanwhile: the record is already "disconnected"
            self._moving = False
            self._settled_at = datetime.now(timezone.utc)
            if position >= 0:
                settled_name = name
                self._set(
                    state="idle",
                    position=position,
                    slot=name,
                    target=None,
                    message=refusal,
                    settled_utc=utc_iso(self._settled_at),
                )
            else:
                message = "position unknown" if refusal else STILL_TURNING
                if refusal:
                    message = f"{refusal} — position unknown"
                self._set(
                    state="error",
                    position=None,
                    slot=None,
                    target=None,
                    message=message,
                    settled_utc=utc_iso(self._settled_at),
                )
        if refusal is None and position >= 0 and name.lower() != target.lower():
            hub.log(
                "warning",
                f"The filter wheel stopped on '{name}', not on '{target}'.",
                source="filterwheel",
                topic="camera",
            )
        elif refusal is None and position < 0:
            hub.log("error", f"Filter move: {STILL_TURNING}", source="filterwheel", topic="camera")
        if self.on_settled is not None:
            try:
                self.on_settled(settled_name)
            except Exception:  # never kill the move thread on a listener
                logger.exception("Filter settle listener failed")

    def wait_settled(
        self, cancel: threading.Event, timeout_s: float = SETTLE_TIMEOUT_S + 5
    ) -> bool:
        """Block until no move is in flight; False on *cancel* or timeout."""
        deadline = time.monotonic() + timeout_s
        while True:
            with self._hub._lock:
                if not self._moving:
                    return True
            if cancel.wait(0.05) or time.monotonic() > deadline:
                return False
