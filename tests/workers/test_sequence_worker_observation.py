"""A transit plan that went through the Plan editor writes observation.json.

The SequenceWorker runs synchronously with a fake camera; the plan comes out
of a real SequencePanel (offscreen), as a run started from the UI does.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.core.catalog.exoplanets import ExoplanetTarget  # noqa: E402
from argos.core.exoplanet.transit import make_transit_sequence, predict_next_transit  # noqa: E402
from argos.core.imaging.fits_writer import FrameContext  # noqa: E402
from argos.workers.sequence_worker import OBSERVATION_FILENAME, SequenceWorker  # noqa: E402

_APP = QApplication.instance() or QApplication(["test"])


class _Camera:
    def __init__(self) -> None:
        self.gain = 0

    def set_gain(self, gain: int) -> None:
        self.gain = gain

    def try_get_gain(self):
        return self.gain

    def start_exposure(self, exposure_s: float, light: bool = True) -> None:
        pass

    def is_image_ready(self) -> bool:
        return True

    def get_image_array(self):
        return np.full((64, 64), 1000, dtype=np.uint16)

    def stop_exposure(self) -> None:
        pass


def test_transit_run_from_the_editor_writes_observation_json(tmp_path, monkeypatch) -> None:
    """S5: no UI path in 0.4.2 could produce observation.json."""
    from argos.ui.widgets.sequence_panel import SequencePanel

    monkeypatch.setenv("HOME", str(tmp_path))
    target = ExoplanetTarget(
        planet_name="HD 189733 b",
        host_name="HD 189733",
        ra_degrees=300.1821,
        dec_degrees=22.7099,
        period_days=2.21857567,
        epoch_bjd_tdb=2454279.436714,
        duration_hours=1.827,
        depth_percent=2.4,
        epoch_system="BJD TDB",
    )
    window = predict_next_transit(target, target.epoch_bjd_tdb + 0.1, baseline_minutes=60)
    transit = make_transit_sequence(
        target, window, exposure_s=0.01, cadence_s=0.01, gain=80, filter_name="IR"
    )
    panel = SequencePanel()
    try:
        panel.load_plan(transit)
        plan = panel.to_plan()
    finally:
        panel.close()
        panel.deleteLater()
        _APP.processEvents()
    plan.steps[0].count = 1

    SequenceWorker(
        camera=_Camera(),
        telescope=None,
        filterwheel=None,
        plan=plan,
        frame_context_provider=lambda object_name, filter_name: FrameContext(
            object_name=object_name, filter_name=filter_name
        ),
        base_dir=tmp_path / "sessions",
    ).run()

    (path,) = (tmp_path / "sessions").glob("*/" + OBSERVATION_FILENAME)
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    assert payload["object_name"] == "HD 189733"
    assert payload["planet_name"] == "HD 189733 b"
