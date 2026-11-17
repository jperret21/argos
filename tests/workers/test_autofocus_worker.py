"""AutofocusWorker — degenerate V-curve refusal (P6), with fake devices.

The worker runs synchronously (``run()`` on the test thread); the fake camera
returns a synthetic star whose width does — or deliberately does not — depend
on the fake focuser's position.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PyQt6.QtCore import QCoreApplication  # noqa: E402

import argos.workers.autofocus_worker as af_mod  # noqa: E402
from argos.workers.autofocus_worker import AutofocusWorker  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture(autouse=True)
def _fast_settle(monkeypatch):
    monkeypatch.setattr(af_mod, "_SETTLE_S", 0.0)
    monkeypatch.setattr(af_mod, "_POLL_INTERVAL_MS", 1)


class _FakeFocuser:
    max_step = 50_000

    def __init__(self, pos=25_000):
        self._pos = pos
        self.moves: list[int] = []

    def get_position(self):
        return self._pos

    def move_to(self, pos):
        self._pos = int(pos)
        self.moves.append(int(pos))

    def is_moving(self):
        return False

    def halt(self):
        pass


class _FakeCamera:
    """Star field whose FWHM follows |pos − best| when coupled, else constant."""

    def __init__(self, focuser, best=25_000, coupled=True):
        self._focuser = focuser
        self._best = best
        self._coupled = coupled

    def start_exposure(self, _exposure, light=True):
        pass

    def is_image_ready(self):
        return True

    def get_image_array(self):
        if self._coupled:
            sigma = 1.2 + 3.0 * abs(self._focuser.get_position() - self._best) / 2000.0
        else:
            sigma = 2.0
        yy, xx = np.mgrid[0:120, 0:120]
        star = 20000.0 * np.exp(-((xx - 60.0) ** 2 + (yy - 60.0) ** 2) / (2 * sigma**2))
        return (star + 200.0).astype(np.uint16)


def _run(worker):
    errors, best = [], []
    worker.error_occurred.connect(errors.append)
    worker.best_found.connect(lambda pos, hfd: best.append((pos, hfd)))
    worker.run()
    return errors, best


def test_flat_curve_is_refused_and_focus_restored() -> None:
    foc = _FakeFocuser(pos=25_000)
    cam = _FakeCamera(foc, coupled=False)  # focuser has no optical effect
    worker = AutofocusWorker(foc, cam, exposure_s=0.0, half_range=2000, num_steps=5)
    errors, best = _run(worker)

    assert errors and "focus unchanged" in errors[0]
    assert best == [(25_000, None)]  # no confident best on a flat curve
    assert foc.get_position() == 25_000  # returned to start


def test_clean_v_curve_moves_to_the_vertex() -> None:
    foc = _FakeFocuser(pos=24_500)  # start slightly off best
    cam = _FakeCamera(foc, best=25_000, coupled=True)
    worker = AutofocusWorker(foc, cam, exposure_s=0.0, half_range=2000, num_steps=7)
    errors, best = _run(worker)

    assert not errors
    pos, hfd = best[0]
    assert hfd is not None
    assert abs(pos - 25_000) < 300  # vertex near the true best
    assert foc.get_position() == pos


class _GainCamera(_FakeCamera):
    """Records the order of gain and exposure commands."""

    def __init__(self, focuser, **kwargs):
        super().__init__(focuser, **kwargs)
        self.calls: list[tuple] = []

    def set_gain(self, gain):
        self.calls.append(("gain", gain))

    def start_exposure(self, exposure, light=True):
        self.calls.append(("expose", exposure))


def test_sweep_frames_use_the_requested_gain() -> None:
    """S22: the gain was stored and never applied — AF frames used whatever
    gain the camera last had (a preview, a sequence step)."""
    foc = _FakeFocuser(pos=24_500)
    cam = _GainCamera(foc, best=25_000, coupled=True)
    worker = AutofocusWorker(foc, cam, exposure_s=0.0, gain=200, half_range=2000, num_steps=7)
    _run(worker)

    assert cam.calls[0] == ("gain", 200)  # before the first sample
    assert ("expose", 0.0) in cam.calls


class _MotorFocuser(_FakeFocuser):
    """Moves ``speed`` steps per is_moving() poll, like a real motor."""

    def __init__(self, pos=25_000, speed=200):
        super().__init__(pos)
        self.target = pos
        self.speed = speed

    def move_to(self, pos):
        self.target = int(pos)
        self.moves.append(int(pos))

    def is_moving(self):
        if self._pos != self.target:
            self._pos += max(-self.speed, min(self.speed, self.target - self._pos))
        return self._pos != self.target

    def halt(self):
        self.target = self._pos


def test_stop_returns_the_focuser_to_its_start_before_the_worker_ends() -> None:
    """S23: on Stop AF the worker commanded the return to the start and ended
    at once; the page's trailing Halt then froze the focuser mid-sweep."""
    foc = _MotorFocuser(pos=25_000, speed=200)
    worker = None

    class _StopOnThirdFrame(_FakeCamera):
        frames = 0

        def get_image_array(self):
            self.frames += 1
            if self.frames == 3:  # the observer presses Stop AF
                worker.stop()
            return super().get_image_array()

    worker = AutofocusWorker(foc, _StopOnThirdFrame(foc), exposure_s=0.0, num_steps=9)
    _errors, best = _run(worker)

    assert foc.is_moving() is False  # the return move is over when run() ends
    assert foc.get_position() == 25_000
    assert best == [(25_000, None)]
    foc.halt()  # a Halt after the worker ended can no longer strand it
    assert foc.get_position() == 25_000


def test_stop_halts_the_sweep_before_the_worker_can_start_the_return() -> None:
    """S23 follow-up: stop() runs on the UI thread. It raised the stop flag
    and only then halted the focuser, so a worker that woke in between could
    command the return to the start, and that halt then froze it midway."""
    foc = _MotorFocuser(pos=25_000)
    worker = AutofocusWorker(foc, _FakeCamera(foc), exposure_s=0.0)
    flag_at_halt: list[bool] = []
    foc.halt = lambda: flag_at_halt.append(worker._stop_flag)

    worker.stop()

    assert flag_at_halt == [False]  # [True] before: the worker could already see the stop
    assert worker._stop_flag is True


def test_stop_during_the_move_to_best_focus_returns_to_the_start() -> None:
    """S23 follow-up: a Stop during the final move to the fitted best focus
    halted that move, and the worker still reported the fitted position and
    HFD, so the page logged "Autofocus complete" at a position never reached."""
    foc = _MotorFocuser(pos=24_500, speed=200)
    worker = AutofocusWorker(foc, _FakeCamera(foc, best=25_000), exposure_s=0.0, num_steps=9)
    armed = {"verify_move": False}
    worker.step_done.connect(
        lambda step, total, _pos, _hfd: armed.update(verify_move=step == total - 1)
    )
    move_to = foc.move_to

    def move_then_stop(pos):
        move_to(pos)
        if armed["verify_move"]:  # the observer presses Stop AF on the way
            armed["verify_move"] = False
            worker.stop()

    foc.move_to = move_then_stop
    _errors, best = _run(worker)

    assert best == [(24_500, None)]  # (fitted best, fitted HFD) before
    assert foc.get_position() == 24_500 and foc.is_moving() is False
