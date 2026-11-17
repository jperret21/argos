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


class _SlowCamera(_Camera):
    """A camera whose settings round trips and download take time, as a
    Seestar's over Wi-Fi do (the ImageArray of a 10 s sub took ~10 s)."""

    EXPOSURE_S = 0.2

    def __init__(self) -> None:
        super().__init__()
        self.started_at = None

    def try_get_gain(self):
        import time

        time.sleep(0.3)
        return self.gain

    def start_exposure(self, exposure_s: float, light: bool = True) -> None:
        from datetime import datetime, timezone

        self.started_at = datetime.now(timezone.utc)

    def is_image_ready(self) -> bool:
        from datetime import datetime, timezone

        return (datetime.now(timezone.utc) - self.started_at).total_seconds() >= self.EXPOSURE_S

    def get_image_array(self):
        import time

        time.sleep(1.0)
        return super().get_image_array()


def test_sequence_frame_times_are_the_exposure_not_the_download(tmp_path) -> None:
    """S36: the sequence clock stopped after the ImageArray download, so DATE-AVG
    and MJD-AVG of every sequence frame were late by half the download time
    (median +5.2 s on the owner's RR Lyr run of 10 s subs), and it started before
    the gain and filter read-backs. Open FITS dates a frame by DATE-AVG (S4)."""
    from datetime import datetime

    from astropy.io import fits

    from argos.core.imaging.sequencer import SequencePlan, SequenceStep

    camera = _SlowCamera()
    plan = SequencePlan(
        steps=[SequenceStep(frame_type="Light", exposure_s=_SlowCamera.EXPOSURE_S, count=1)],
        object_name="T",
    )
    SequenceWorker(
        camera=camera,
        telescope=None,
        filterwheel=None,
        plan=plan,
        frame_context_provider=lambda object_name, filter_name: FrameContext(
            object_name=object_name, filter_name=filter_name
        ),
        base_dir=tmp_path / "sessions",
    ).run()

    (path,) = (tmp_path / "sessions").rglob("*.fit*")
    hdr = fits.getheader(path)
    obs = datetime.fromisoformat(hdr["DATE-OBS"] + "+00:00")
    avg = datetime.fromisoformat(hdr["DATE-AVG"] + "+00:00")
    assert abs((obs - camera.started_at).total_seconds()) < 0.1  # −0.3 s before the fix
    # Half the exposure plus at most half a poll (0.2 s); 0.6 s before the fix.
    assert 0.09 <= (avg - obs).total_seconds() <= 0.25
