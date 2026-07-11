"""CameraService — the single camera-ownership state machine.

Exactly one activity may drive the camera at a time. Before WS3, every
handler in the imaging page re-derived "who owns the camera" from scattered
``isRunning()`` checks over three workers — each new feature had to remember
every guard. This service makes contention bugs impossible by construction:
callers *acquire* the camera for a :class:`CameraState` and *release* it when
done; the service is the one source of truth.

It deliberately does **not** re-implement exposures. LivePreviewWorker,
SequenceWorker and AutofocusWorker keep their acquisition loops; the service
arbitrates ownership and centralises start/stop of the LivePreviewWorker via
injected hooks (so it stays hardware-free and unit-testable).

Priority (highest wins): SEQUENCE > AUTOFOCUS > LIVE / SINGLE.

    acquire(requested)
        IDLE                        → granted
        same state                  → refused ("already running")
        LIVE/SINGLE, higher-priority requestor
                                    → granted, the preview loop is preempted
        SINGLE → LIVE               → granted in place (the transient
                                      Take-shot loop is upgraded to Live;
                                      the preview worker keeps running)
        anything else               → refused with a human-readable reason

    begin_sequence_autofocus()
        SEQUENCE → AUTOFOCUS, remembering to resume SEQUENCE on release —
        the mid-sequence AF handshake (the sequence worker is blocked on
        ``resume_after_autofocus`` while AF owns the camera).

    release(owner)
        Only the current owner releases; stale/double releases are safe
        no-ops. Releasing AUTOFOCUS returns to SEQUENCE when the handshake
        is active, else to IDLE.

Signals:
    state_changed(CameraState)  — after every ownership transition
    acquire_refused(str)        — human-readable reason (log as WARN)
    preempted(str)              — a live/single preview was stopped for a
                                  higher-priority owner (log as INFO)
"""

from __future__ import annotations

import logging
from enum import Enum, unique
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


@unique
class CameraState(Enum):
    """Who owns the camera right now."""

    IDLE = "idle"
    LIVE = "live"  # user-requested continuous preview loop
    SINGLE = "single"  # transient Take-shot preview loop (saves N frames)
    SEQUENCE = "sequence"  # SequenceWorker runs the plan
    AUTOFOCUS = "autofocus"  # AutofocusWorker sweeps the focuser


#: Arbitration priority — a higher-priority requestor preempts LIVE/SINGLE.
_PRIORITY: dict[CameraState, int] = {
    CameraState.IDLE: 0,
    CameraState.LIVE: 1,
    CameraState.SINGLE: 1,
    CameraState.AUTOFOCUS: 2,
    CameraState.SEQUENCE: 3,
}

#: Why an acquire was refused, phrased for the session log (kept identical to
#: the pre-service WS1 guard messages where one existed).
_BUSY_REASON: dict[CameraState, str] = {
    CameraState.SEQUENCE: "Sequence running — the sequence owns the camera. Stop it first.",
    CameraState.AUTOFOCUS: "Autofocus running — it owns the camera. Wait for it to finish.",
    CameraState.LIVE: "Live preview running — it owns the camera. Stop it first.",
    CameraState.SINGLE: "A single shot is in progress — wait for it to finish.",
}

#: Who took the camera, phrased for the preemption INFO message.
_OWNER_LABEL: dict[CameraState, str] = {
    CameraState.SEQUENCE: "the sequence",
    CameraState.AUTOFOCUS: "autofocus",
}


class CameraService(QObject):
    """Arbitrates camera ownership between preview, sequence and autofocus."""

    state_changed = pyqtSignal(object)  # CameraState
    acquire_refused = pyqtSignal(str)  # human-readable reason
    preempted = pyqtSignal(str)  # human-readable "live stopped for X" note

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = CameraState.IDLE
        #: State to restore when AUTOFOCUS releases (the AF-mid-sequence
        #: handshake); None outside the handshake.
        self._resume_to: CameraState | None = None
        self._start_preview: Callable[[], None] | None = None
        self._stop_preview: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_preview_hooks(self, start: Callable[[], None], stop: Callable[[], None]) -> None:
        """Register how to start/stop the LivePreviewWorker.

        The service centralises when the preview loop runs (grant of
        LIVE/SINGLE, release, preemption); the hooks say how. Both must be
        idempotent — the stop hook may fire for an already-stopped worker.
        """
        self._start_preview = start
        self._stop_preview = stop

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> CameraState:
        """The current camera owner (single source of truth for guards)."""
        return self._state

    # ------------------------------------------------------------------
    # Arbitration API
    # ------------------------------------------------------------------

    def acquire(self, requested: CameraState) -> bool:
        """Request camera ownership for ``requested``.

        Returns True when granted. On refusal, emits
        :attr:`acquire_refused` with a log-ready reason and returns False.
        A higher-priority requestor (SEQUENCE, AUTOFOCUS) preempts a running
        LIVE/SINGLE preview loop instead of being refused.
        """
        if requested is CameraState.IDLE:
            raise ValueError("IDLE cannot be acquired — call release() instead.")
        current = self._state
        if current is requested:
            self.acquire_refused.emit(_BUSY_REASON[requested])
            return False
        if current is CameraState.IDLE:
            self._enter(requested)
            return True
        if current is CameraState.SINGLE and requested is CameraState.LIVE:
            # Upgrade the transient Take-shot loop to a user Live loop; the
            # preview worker is already running, only the ownership changes.
            self._set_state(CameraState.LIVE)
            return True
        if current in (CameraState.LIVE, CameraState.SINGLE) and (
            _PRIORITY[requested] > _PRIORITY[current]
        ):
            self._call(self._stop_preview)
            self.preempted.emit(
                f"Live preview stopped — {_OWNER_LABEL[requested]} owns the camera."
            )
            self._enter(requested)
            return True
        self.acquire_refused.emit(_BUSY_REASON[current])
        return False

    def begin_sequence_autofocus(self) -> bool:
        """SEQUENCE yields the camera to a mid-sequence autofocus pass.

        Only valid while the sequence owns the camera (its worker is blocked
        on the AF handshake). Releasing AUTOFOCUS afterwards restores
        SEQUENCE. Returns False (with a refusal reason) otherwise.
        """
        if self._state is not CameraState.SEQUENCE:
            self.acquire_refused.emit("Autofocus handshake refused — no sequence owns the camera.")
            return False
        self._resume_to = CameraState.SEQUENCE
        self._set_state(CameraState.AUTOFOCUS)
        return True

    def release(self, owner: CameraState) -> None:
        """Release the camera held as ``owner``.

        Safe against double/stale releases: only the current owner
        transitions the state. Releasing SEQUENCE while AUTOFOCUS holds the
        camera (sequence aborted mid-handshake) just cancels the pending
        resume — AF then releases to IDLE.
        """
        if (
            owner is CameraState.SEQUENCE
            and self._state is CameraState.AUTOFOCUS
            and self._resume_to is CameraState.SEQUENCE
        ):
            self._resume_to = None  # nothing left to resume to
            return
        if self._state is not owner:
            return  # double release / stale signal — no-op by design
        if owner in (CameraState.LIVE, CameraState.SINGLE):
            self._call(self._stop_preview)
        next_state = self._resume_to or CameraState.IDLE
        self._resume_to = None
        self._set_state(next_state)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enter(self, requested: CameraState) -> None:
        self._set_state(requested)
        if requested in (CameraState.LIVE, CameraState.SINGLE):
            self._call(self._start_preview)

    def _set_state(self, state: CameraState) -> None:
        if state is self._state:
            return
        logger.debug("Camera ownership: %s → %s", self._state.value, state.value)
        self._state = state
        self.state_changed.emit(state)

    @staticmethod
    def _call(hook: Callable[[], None] | None) -> None:
        if hook is not None:
            hook()
