"""LivePreviewWorker — the settings a frame was exposed with travel with it.

The loop is run synchronously on this thread with a fake camera; no event
loop is needed because ``frame_ready`` is observed through a direct
connection.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from argos.workers.exposure_worker import LivePreviewWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Camera:
    """Changes the worker's settings mid-exposure, then stops after one frame."""

    def __init__(self) -> None:
        self.worker: LivePreviewWorker | None = None
        self.gains: list[int] = []
        self.exposures: list[tuple[float, bool]] = []

    def set_gain(self, gain: int) -> None:
        self.gains.append(gain)

    def start_exposure(self, exposure: float, light: bool = True) -> None:
        self.exposures.append((exposure, light))

    def is_image_ready(self) -> bool:
        # The observer edits the form while the shutter is open.
        self.worker.update_settings(30.0, 200, light=False)
        return True

    def get_image_array(self) -> np.ndarray:
        self.worker.stop()
        return np.zeros((8, 8), dtype=np.uint16)

    def stop_exposure(self) -> None:
        pass


def test_frame_carries_the_settings_it_was_exposed_with(qapp) -> None:
    """S2: a mid-exposure update must not be what the frame reports."""
    camera = _Camera()
    worker = LivePreviewWorker(camera, exposure=10.0, gain=80, preview_scale=1, light=True)
    camera.worker = worker
    frames: list[tuple] = []
    worker.frame_ready.connect(lambda *args: frames.append(args))

    worker.run()

    assert camera.gains == [80] and camera.exposures == [(10.0, True)]
    assert len(frames) == 1
    used = frames[0][-1]
    assert (used.exposure_s, used.gain, used.light) == (10.0, 80, True)
