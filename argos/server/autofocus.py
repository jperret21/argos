"""Autofocus (row A36): the two-stage HFD V-curve sweep on a server thread.

A Qt-free port of ``AutofocusWorker`` (``argos/workers/autofocus_worker.py``,
release 0.5.0) with ``argos.core.imaging.focus`` unchanged:

1. coarse sweep of ``num_steps`` positions across ±``half_range``
   (``autofocus_worker.py:117-131``);
2. the degenerate-sweep guard: fewer than three valid samples, a flat curve
   or an edge minimum restore the start and end ``rejected``
   (``:133-147``);
3. four fine samples around the raw minimum, the parabola fitted on them and
   the coarse minimum (``:149-167``);
4. a move to the best position and one verification exposure (``:169-185``).

With the 0.5.0 fixes:

- **S22**: the requested gain is applied: it is sent with every sample
  exposure (``CameraDevice.expose`` sets it);
- **S23**: Stop = cancel and *return to the start*. The sweep move is
  halted first, then the flag is raised (``autofocus_worker.py:84-93``);
  the return is waited for whatever the flag (30 s at most) and the
  position is read back; the camera is released only when the thread has
  ended. A stop on the way to best focus also returns to the start.
- **Halt** (Q-O6, left to the web UI by 0.5.0): ``POST /api/focuser/halt``
  during a sweep stops it *where it is*, with no return.

Halt, Stop and every sweep move go through one control lock, so no sweep
move is sent after a stop or a halt, and a halt never freezes the return
move (it is ignored once the return has started).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from argos.core.imaging.debayer import compute_hfd
from argos.core.imaging.focus import fit_v_curve, refine_positions, sweep_is_degenerate
from argos.server.devices.base import ExposureCancelled
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: autofocus_worker.py:44-46.
SETTLE_S = 1.0
POLL_S = 0.3
FINE_COUNT = 4
#: Bound of every focuser wait (autofocus_worker.py:220).
MOVE_DEADLINE_S = 30.0
#: Defaults of AutofocusWorker.__init__ (autofocus_worker.py:63-82).
DEFAULT_HALF_RANGE = 2000
DEFAULT_NUM_STEPS = 9
#: acquisition_engine.py:945: the capture exposure, at most 10 s.
MAX_DEFAULT_EXPOSURE_S = 10.0


@dataclass(frozen=True)
class AutofocusParams:
    exposure_s: float
    gain: int
    half_range: int = DEFAULT_HALF_RANGE
    num_steps: int = DEFAULT_NUM_STEPS

    def to_dict(self) -> dict[str, Any]:
        return {
            "exposure_s": self.exposure_s,
            "gain": self.gain,
            "half_range": self.half_range,
            "num_steps": self.num_steps,
        }


def idle_record(run: int = 0) -> dict[str, Any]:
    return {
        "state": "idle",
        "stage": None,
        "step": 0,
        "total": 0,
        "params": None,
        "start_position": None,
        "position": None,
        "samples": [],
        "best": None,
        "fit": None,
        "message": None,
        "run": run,
        "started_utc": None,
        "ended_utc": None,
    }


class _Stopped(Exception):
    """The sweep was stopped or halted (raised between steps)."""


@dataclass(frozen=True)
class _Return:
    """How a return to the start ended (S23): reached only when read back there."""

    start: int
    position: int | None
    #: How the wait ended: "idle", "error" or "timeout" (``AutofocusRun._wait``).
    ended: str

    @property
    def reached(self) -> bool:
        return self.ended == "idle" and self.position == self.start

    def words(self) -> str:
        if self.position is None or self.ended == "error":
            return f"could not read the focuser back: it may not be at its start ({self.start})."
        if self.ended == "timeout":
            return (
                f"focuser at {self.position} and still moving, not yet back at its start "
                f"({self.start})."
            )
        return f"focuser at {self.position}, not back at its start ({self.start})."


class AutofocusRun:
    """One sweep: the thread body and its stop / halt controls."""

    def __init__(
        self,
        hub: "Hub",
        camera: Any,
        focuser: Any,
        params: AutofocusParams,
        run: int,
        *,
        settle_s: float = SETTLE_S,
        poll_s: float = POLL_S,
        deadline_s: float = MOVE_DEADLINE_S,
        publish_frame: Callable[[np.ndarray, float, int, str, str], int],
        on_end: Callable[["AutofocusRun"], None],
    ) -> None:
        self._hub = hub
        self._camera = camera
        self._focuser = focuser
        self.params = params
        self.run = run
        self._settle_s = settle_s
        self._poll_s = poll_s
        self._deadline_s = float(deadline_s)
        self._publish_frame = publish_frame
        self._on_end = on_end
        #: Serialises stop / halt decisions with the sweep's moves.
        self._ctl = threading.Lock()
        self._stop_flag = False
        #: "return" (Stop AF) or "halt" (focuser Halt); the first one wins.
        self.mode: str | None = None
        self._returning = False
        self._cancel = threading.Event()
        self.record = idle_record(run)
        self.thread = threading.Thread(target=self._main, name="argos-autofocus", daemon=True)

    # -- controls (request threads) ---------------------------------------------

    @property
    def returning(self) -> bool:
        return self._returning

    def stop(self) -> bool:
        """Stop AF: halt the sweep move, then raise the flag (return to the start).

        Returns False when a stop or halt was already requested (harmless).
        """
        with self._ctl:
            if self.mode is not None:
                return False
            self.mode = "return"
            # autofocus_worker.py:84-93: halt first, then the flag.
            try:
                self._focuser.halt()
            except Exception:
                pass
            self._stop_flag = True
            self._cancel.set()
        return True

    def halt(self) -> bool:
        """Focuser Halt during a sweep: stop where it is, no return (Q-O6).

        Ignored (False) once a stop's return move runs: a halt must never
        freeze it (S23).
        """
        with self._ctl:
            if self._returning or self.mode == "return":
                return False
            if self.mode is None:
                self.mode = "halt"
            try:
                self._focuser.halt()
            except Exception:
                pass
            self._stop_flag = True
            self._cancel.set()
        return True

    # -- record ------------------------------------------------------------------

    def _update(self, **changes: Any) -> None:
        hub = self._hub
        with hub._lock:
            self.record = {**self.record, **changes}
            hub._publish("autofocus", dict(self.record))

    # -- the sweep -------------------------------------------------------------------

    def _main(self) -> None:
        state, message = "failed", "Autofocus ended unexpectedly."
        try:
            try:
                state, message = self._run()
            except _Stopped:
                state, message = self._stopped()
            except Exception as exc:
                logger.exception("Autofocus error")
                if self.mode is not None:
                    state, message = self._stopped()
                else:
                    state, message = "failed", self._after_failure(exc)
        except Exception as exc:  # the stop / return itself failed: say so, release all
            logger.exception("Autofocus stop failed")
            state = "failed"
            message = f"{exc or exc.__class__.__name__} — the focuser may not be at its start"
        finally:
            try:
                self._update(state=state, stage=None, message=message, ended_utc=utc_iso())
            finally:
                self._on_end(self)

    def _after_failure(self, exc: Exception) -> str:
        """A failed sweep: never leave the focus somewhere in the sweep range."""
        message = str(exc) or exc.__class__.__name__
        start = self.record.get("start_position")
        if start is None:
            return message
        try:
            back = self._restore(int(start))
        except Exception as restore_exc:
            return f"{message} — the focuser could not be returned ({restore_exc})"
        if not back.reached:
            return f"{message} — {back.words()}"
        return f"{message} — focuser returned to {back.position}"

    def _stopped(self) -> tuple[str, str]:
        if self.mode == "halt":
            try:
                position = int(self._focuser.get_position())
            except Exception:
                position = self.record.get("position")
            self._update(position=position)
            return "cancelled", f"Halted at {position}: focus left there."
        start = self.record.get("start_position")
        if start is None:
            return "cancelled", "Stopped before the sweep started."
        back = self._restore(int(start))
        if not back.reached:
            # Never "Returned to <start>" without reading it back (S23 review).
            return "failed", f"Stopped — {back.words()}"
        return "cancelled", f"Returned to {back.position}."

    def _run(self) -> tuple[str, str]:
        p = self.params
        start_pos = int(self._focuser.get_position())
        max_step = int(getattr(self._focuser, "max_step", 100_000) or 100_000)
        low = max(0, start_pos - p.half_range)
        high = min(max_step, start_pos + p.half_range)
        coarse = [int(x) for x in np.unique(np.linspace(low, high, max(3, p.num_steps), dtype=int))]
        spacing = coarse[1] - coarse[0] if len(coarse) > 1 else p.half_range
        total = len(coarse) + FINE_COUNT + 1
        self._update(
            state="running",
            stage="coarse",
            step=0,
            total=total,
            params=p.to_dict(),
            start_position=start_pos,
            position=start_pos,
            samples=[],
            best=None,
            fit=None,
            message=None,
            started_utc=utc_iso(),
            ended_utc=None,
        )

        # Stage 1: coarse sweep — only the raw minimum is trusted.
        measurements = self._measure(coarse, "coarse", 0, total)
        valid = [(pos, h) for pos, h in measurements if not math.isnan(h)]
        if len(valid) < 3:
            return self._rejected("fewer than 3 valid samples", start_pos)
        reason = sweep_is_degenerate(tuple(sorted(valid)))
        if reason is not None:
            return self._rejected(reason, start_pos)
        raw_min_pos, raw_min_hfd = min(valid, key=lambda t: t[1])

        # Stage 2: fine samples around the raw minimum.
        fine = refine_positions(raw_min_pos, spacing, low, high, count=FINE_COUNT)
        self._update(stage="fine")
        fine_meas = self._measure(fine, "fine", len(coarse), total)
        window = fine_meas + [(raw_min_pos, raw_min_hfd)]
        lo, hi = raw_min_pos - spacing, raw_min_pos + spacing
        result = fit_v_curve(window, lo, hi)
        best_pos = int(result.best_position)
        self._update(
            fit={
                "coeffs": list(result.coeffs) if result.coeffs is not None else None,
                "window": [lo, hi],
                "samples": [[int(pos), float(h)] for pos, h in result.samples],
            }
        )

        # Stage 3: verify — measure at the final position, report reality.
        self._update(stage="verify")
        self._move(best_pos)
        verified = self._capture()
        self._sample(best_pos, verified, "verify", total, total)
        if verified is not None and result.best_hfd and verified > result.best_hfd * 2.0:
            logger.warning(
                "AF verification HFD %.1f much worse than fitted %.1f", verified, result.best_hfd
            )
        best_hfd = verified if verified is not None else result.best_hfd
        self._update(
            position=best_pos,
            best={
                "position": best_pos,
                "hfd_px": verified,
                "fitted_hfd_px": result.best_hfd,
                "method": result.method,
            },
        )
        if best_hfd is None:
            return "rejected", f"Autofocus: no measurable star at {best_pos} — focus left there."
        return "done", f"Autofocus complete — best pos={best_pos}  HFD={best_hfd:.1f}"

    def _rejected(self, reason: str, start_pos: int) -> tuple[str, str]:
        """A degenerate sweep: back to the start, said only once it is read back."""
        back = self._restore(start_pos)
        if not back.reached:
            return "failed", f"Autofocus: {reason} — {back.words()}"
        return "rejected", f"Autofocus: {reason} — focus unchanged ({back.position})."

    def _measure(
        self, positions: list[int], stage: str, done: int, total: int
    ) -> list[tuple[int, float]]:
        out: list[tuple[int, float]] = []
        for i, pos in enumerate(positions):
            self._move(int(pos))
            hfd = self._capture()
            out.append((int(pos), hfd if hfd is not None else float("nan")))
            self._sample(int(pos), hfd, stage, done + i + 1, total)
        return out

    def _sample(self, position: int, hfd: float | None, stage: str, step: int, total: int) -> None:
        sample = {"position": position, "hfd_px": hfd, "stage": stage, "t": utc_iso()}
        self._update(
            step=step,
            total=total,
            position=position,
            samples=[*self.record["samples"], sample],
        )
        hfd_text = f"{hfd:.1f}" if hfd is not None else "—"
        self._hub.log(
            "info",
            f"AF {step}/{total}  pos={position}  HFD={hfd_text}",
            source="autofocus",
            topic="focuser",
        )

    def _move(self, position: int) -> None:
        """A sweep move: never sent after a stop or a halt (control lock)."""
        with self._ctl:
            if self._stop_flag:
                raise _Stopped()
            self._focuser.move_to(int(position))
        self._note_target(position)
        self._wait()
        if self._stop_flag:
            raise _Stopped()

    def _wait(self, ignore_stop: bool = False) -> str:
        """``_wait_for_focuser`` (autofocus_worker.py:213-231).

        Returns how the wait ended: ``"idle"``, ``"stopped"``, ``"error"``
        (``is_moving`` failed) or ``"timeout"`` (still moving at the deadline).
        """
        deadline = time.monotonic() + self._deadline_s
        outcome = "timeout"
        while time.monotonic() < deadline:
            if not ignore_stop and self._stop_flag:
                outcome = "stopped"
                break
            try:
                moving = bool(self._focuser.is_moving())
            except Exception as exc:
                logger.warning("AF: focuser state unreadable (%s)", exc)
                outcome = "error"
                break
            self._note_focuser(moving)
            if not moving:
                outcome = "idle"
                break
            time.sleep(self._poll_s)
        if not self._stop_flag and not ignore_stop and self._settle_s > 0:
            time.sleep(self._settle_s)
        return outcome

    def _note_target(self, target: int) -> None:
        """The focuser record's ``target`` follows the sweep's moves (the web Focuser card)."""
        service = getattr(self._hub, "focuser", None)
        if service is not None:
            service.note_target(int(target))

    def _note_focuser(self, moving: bool) -> None:
        service = getattr(self._hub, "focuser", None)
        if service is None:
            return
        try:
            position = int(self._focuser.get_position())
        except Exception:
            position = None
        service.note_position(position, moving)

    def _restore(self, start_pos: int) -> "_Return":
        """Back to the start, waited for whatever the stop flag (S23).

        The start is reported as reached only when the focuser was read back
        there, idle (review of wave 3): a lost focuser, an unreadable
        position or a return slower than the wait limit is said, with an
        ERROR line, instead of "Returned to <start>".
        """
        with self._ctl:
            self._returning = True
        self._update(stage="returning")
        self._focuser.move_to(int(start_pos))
        self._note_target(start_pos)
        ended = self._wait(ignore_stop=True)
        try:
            position: int | None = int(self._focuser.get_position())
        except Exception as exc:
            logger.warning("AF: focuser position unreadable after the return (%s)", exc)
            position = None
        back = _Return(start=start_pos, position=position, ended=ended)
        if position is not None:
            self._update(position=position)
            self._note_focuser(ended != "idle")
        if not back.reached:
            self._hub.log(
                "error", f"Autofocus: {back.words()}", source="autofocus", topic="focuser"
            )
        return back

    def _capture(self) -> float | None:
        """One sample exposure at the AF gain (S22); its HFD, or None."""
        if self._stop_flag:
            raise _Stopped()
        p = self.params
        times: dict[str, str] = {}
        try:
            arr = self._camera.expose(
                p.exposure_s,
                p.gain,
                self._cancel,
                lambda: times.setdefault("end", utc_iso()),
                light=True,
                on_start=lambda: times.setdefault("start", utc_iso()),
            )
        except ExposureCancelled:
            raise _Stopped() from None
        except Exception as exc:
            if self._stop_flag:
                raise _Stopped() from None
            logger.warning("AF exposure: %s", exc)
            return None
        if self._stop_flag:
            raise _Stopped()
        try:
            self._publish_frame(
                arr, p.exposure_s, p.gain, times.get("end") or utc_iso(), times.get("start", "")
            )
        except Exception:
            logger.exception("Publishing an autofocus frame failed")
        return compute_hfd(arr)
