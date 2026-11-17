"""The synthetic camera: statistics, determinism, drift, timing."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from argos.server.devices.base import ExposureCancelled
from argos.server.devices.sim_camera import SATURATION_ADU, SimCamera


@pytest.fixture(scope="module")
def camera() -> SimCamera:
    return SimCamera()  # full S50 geometry


def test_reference_frame_statistics(camera):
    frame = camera.render(1, exposure_s=2.0, gain=80)
    assert frame.shape == (1920, 1080) and frame.dtype == np.uint16
    median = float(np.median(frame))
    mad = float(np.median(np.abs(frame - median)))
    assert 1950 <= median <= 2050  # "sky background around 2000 ADU"
    assert 18 <= mad <= 32  # shot + read noise ≈ 37 ADU rms → MAD ≈ 25
    saturated = int((frame == SATURATION_ADU).sum())
    assert 20 < saturated < 5000  # a few saturated stars, not a white frame


def test_stars_are_there_and_sharp(camera):
    frame = camera.render(1, exposure_s=2.0, gain=80).astype(np.float64)
    background = np.median(frame)
    sigma = 1.4826 * np.median(np.abs(frame - background))
    # Local maxima 10σ above the sky: there should be well over a hundred.
    core = frame[1:-1, 1:-1]
    peaks = (
        (core > background + 10 * sigma)
        & (core >= frame[:-2, 1:-1])
        & (core >= frame[2:, 1:-1])
        & (core >= frame[1:-1, :-2])
        & (core >= frame[1:-1, 2:])
    )
    assert 100 < int(peaks.sum()) < 400


def test_frames_are_deterministic_per_index(camera):
    a = camera.render(5, exposure_s=1.0, gain=80)
    b = camera.render(5, exposure_s=1.0, gain=80)
    c = camera.render(6, exposure_s=1.0, gain=80)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


def test_field_drifts_slightly_between_frames(camera):
    offsets = [camera.drift(i) for i in range(1, 50)]
    steps = [np.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(offsets, offsets[1:])]
    assert 0 < max(steps) < 2.0  # sub-few-pixel jitter + slow wander
    assert max(np.hypot(x, y) for x, y in offsets) < 8.0


def test_gain_and_exposure_scale_the_signal(camera):
    low = float(np.median(camera.render(1, exposure_s=2.0, gain=80)))
    long = float(np.median(camera.render(1, exposure_s=4.0, gain=80)))
    high = float(np.median(camera.render(1, exposure_s=2.0, gain=280)))
    assert long - 1600 == pytest.approx(2 * (low - 1600), rel=0.05)
    assert high - 1600 == pytest.approx(10 * (low - 1600), rel=0.05)  # +200 = ×10


def test_exposure_time_is_waited():
    camera = SimCamera(64, 48)
    readouts = []
    t0 = time.monotonic()
    frame = camera.expose(0.2, 80, threading.Event(), lambda: readouts.append(time.monotonic()))
    assert frame.shape == (48, 64)
    assert readouts and readouts[0] - t0 >= 0.19


def test_cancel_interrupts_the_exposure():
    camera = SimCamera(64, 48)
    cancel = threading.Event()
    threading.Timer(0.05, cancel.set).start()
    t0 = time.monotonic()
    with pytest.raises(ExposureCancelled):
        camera.expose(30.0, 80, cancel, lambda: None)
    assert time.monotonic() - t0 < 1.0


def test_render_is_fast_enough_for_live_view(camera):
    camera.render(1, 2.0, 80)
    t0 = time.perf_counter()
    camera.render(2, 2.0, 80)
    assert time.perf_counter() - t0 < 0.25  # ~20 ms measured
