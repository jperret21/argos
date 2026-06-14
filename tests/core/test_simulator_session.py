"""End-to-end session check against the ASCOM Alpaca simulator.

Drives the real Camera/Telescope wrappers + the display pipeline the way a live
session does — connect, expose, read the image, run debayer/metrics/stretch.
Automatically skipped when the simulator is not running.

Launch the OmniSimulator on localhost:32323 first:
  https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases
Then:  .venv/bin/python -m pytest tests/core/test_simulator_session.py -v
"""

from __future__ import annotations

import time

import numpy as np

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.telescope import Telescope
from seercontrol.core.imaging.debayer import VIEW_SUPERPIXEL, render_view
from seercontrol.core.imaging.metrics import frame_metrics
from seercontrol.core.imaging.stretch import apply_stretch, auto_stf
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required


@simulator_required
def test_camera_exposure_runs_through_display_pipeline() -> None:
    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    try:
        cam.set_gain(80)
        cam.start_exposure(1.0, light=True)
        deadline = time.time() + 20.0
        while not cam.is_image_ready():
            assert time.time() < deadline, "exposure never became ready"
            time.sleep(0.2)
        arr = cam.get_image_array()
        assert arr.ndim == 2 and arr.size > 0

        # Same path the live preview takes (off-thread in the app).
        display = render_view(arr, VIEW_SUPERPIXEL)
        assert display.ndim == 3
        metrics = frame_metrics(arr)
        assert metrics.star_count >= 0
        assert metrics.sky_adu >= 0
        black, white, mid = auto_stf(arr)
        shown = apply_stretch(arr, black, white, "Linear", mid)
        assert shown.dtype == np.uint8
    finally:
        cam.disconnect()


@simulator_required
def test_telescope_reports_position() -> None:
    scope = Telescope(SIMULATOR_HOST, SIMULATOR_PORT)
    scope.connect()
    try:
        pos = scope.get_position()
        assert pos is not None
        assert -90.0 <= pos.dec <= 90.0
        assert 0.0 <= pos.ra < 24.0
    finally:
        scope.disconnect()
