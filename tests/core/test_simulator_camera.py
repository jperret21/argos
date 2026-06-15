"""Camera wrapper validation against the ASCOM Alpaca simulator.

Exercises the real :class:`Camera` wrapper end-to-end the way a live session
does: connect, read metadata, run the exposure state machine, download the
frame, and push it through the display pipeline. Auto-skipped when the
simulator is not running (see ``docs/simulator_testing.md``).
"""

from __future__ import annotations

import time

import numpy as np

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.imaging.debayer import (
    VIEW_G,
    VIEW_INTERP,
    VIEW_RAW,
    VIEW_SUPERPIXEL,
    render_view,
)
from seercontrol.core.imaging.metrics import detect_stars, frame_metrics
from seercontrol.core.imaging.stretch import apply_stretch, auto_stf
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required


def _exposed_frame(cam: Camera, exposure: float = 0.5) -> np.ndarray:
    """Take one exposure and return the downloaded uint16 frame."""
    cam.start_exposure(exposure, light=True)
    deadline = time.time() + exposure + 20.0
    while not cam.is_image_ready():
        assert time.time() < deadline, "exposure never became ready"
        time.sleep(0.1)
    return cam.get_image_array()


@simulator_required
def test_connect_reports_metadata() -> None:
    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    name = cam.connect()
    try:
        assert isinstance(name, str) and name
        assert cam.is_connected
        assert cam.width > 0 and cam.height > 0
        assert cam.gain_max >= cam.gain_min
    finally:
        cam.disconnect()
        assert not cam.is_connected


@simulator_required
def test_gain_is_tolerant_when_unimplemented() -> None:
    # The OmniSim camera has no Gain property; the wrapper must not raise.
    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    try:
        cam.set_gain(80)  # no-op + warning, never an exception
        assert cam.gain_min <= cam.get_gain() <= cam.gain_max
    finally:
        cam.disconnect()


@simulator_required
def test_exposure_state_machine_and_download() -> None:
    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    try:
        arr = _exposed_frame(cam)
        assert arr.ndim == 2 and arr.dtype == np.uint16
        assert arr.shape[0] > 0 and arr.shape[1] > 0
    finally:
        cam.disconnect()


@simulator_required
def test_optional_properties_never_raise() -> None:
    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    try:
        # Each may be None on the sim — the contract is "no exception".
        cam.get_ccd_temperature()
        cam.get_electrons_per_adu()
        cam.get_offset()
        cam.get_readout_mode_name()
        assert isinstance(cam.get_sensor_metadata(), dict)
    finally:
        cam.disconnect()


@simulator_required
def test_frame_runs_through_full_display_pipeline() -> None:
    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    try:
        arr = _exposed_frame(cam)

        # Every display view must render without error.
        for view in (VIEW_RAW, VIEW_SUPERPIXEL, VIEW_INTERP, VIEW_G):
            out = render_view(arr, view)
            assert out.ndim in (2, 3)

        metrics = frame_metrics(arr)
        assert metrics.star_count >= 0 and metrics.sky_adu >= 0

        field = detect_stars(arr)
        assert field.count >= 0  # may be 0 on a featureless sim frame

        black, white, mid = auto_stf(arr)
        shown = apply_stretch(arr, black, white, "Linear", mid)
        assert shown.dtype == np.uint8
    finally:
        cam.disconnect()
