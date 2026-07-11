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
