"""Plan editor: what the table and its options hand to a run (offscreen Qt).

The SequencerPage is built with fake session/engine QObjects; astropy-backed
helpers (BJD now, local transit window) are stubbed so no IERS download runs.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.core.catalog.exoplanets import ExoplanetTarget  # noqa: E402
from argos.core.config import Config  # noqa: E402
from argos.core.exoplanet.transit import make_transit_sequence, predict_next_transit  # noqa: E402
from argos.core.imaging.sequencer import (  # noqa: E402
    SequencePlan,
    SequenceStep,
    plan_to_dict,
)

# Strong reference: the QApplication must outlive every widget below.
_APP = QApplication.instance() or QApplication(["test"])

_SITE = {"site": {"name": "Home", "latitude": 45.0, "longitude": 5.0, "elevation": 0.0}}


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


class _FakeSession(QObject):
    capabilities_ready = pyqtSignal(object)
    filterwheel_state = pyqtSignal(object)
    device_state_changed = pyqtSignal(str, str, str)


class _FakeEngine(QObject):
    sequence_running = pyqtSignal(bool)
    sequence_paused = pyqtSignal(bool)
    sequence_progress = pyqtSignal(str, int, int, float)
    sequence_step = pyqtSignal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self.started_plans: list = []

    def pause_sequence(self) -> None:
        pass

    def resume_sequence_run(self) -> None:
        pass

    def stop_sequence(self) -> None:
        pass

    def start_sequence(self, plan) -> bool:
        self.started_plans.append(plan)
        return True


def _hd189733() -> ExoplanetTarget:
    # The NASA PSCompPars row of tests/core/test_exoplanets.py.
    return ExoplanetTarget(
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


def _transit_plan(exposure_s: float = 10.0, cadence_s: float = 13.0) -> SequencePlan:
    target = _hd189733()
    window = predict_next_transit(target, target.epoch_bjd_tdb + 0.1, baseline_minutes=60)
    return make_transit_sequence(
        target, window, exposure_s=exposure_s, cadence_s=cadence_s, gain=80, filter_name="IR"
    )


def _page(config: dict):
    from argos.ui.pages.sequencer_page import SequencerPage

    engine = _FakeEngine()
    page = SequencerPage(Config(config), _FakeSession(), engine)
    target = _hd189733()
    page._current_bjd_tdb = lambda _t: target.epoch_bjd_tdb + 0.1  # no astropy / IERS
    page._local_transit_window = lambda _t, _w: None
    return page, engine


def _dispose(widget) -> None:
    widget.close()
    widget.deleteLater()
    _APP.processEvents()


def test_prepared_transit_keeps_metadata_through_the_editor() -> None:
    """S5: Prepare transit's planning hand-off never reached the run."""
    page, engine = _page(_SITE)
    try:
        page._exoplanet_target = _hd189733()
        page._prepare_transit_plan()
        page.panel._on_start()

        started = engine.started_plans[-1]
        assert started.metadata["observation_type"] == "exoplanet_transit"
        assert started.metadata["planet_name"] == "HD 189733 b"
        assert plan_to_dict(page.panel.to_plan())["metadata"] == started.metadata

        # Never written for another object, nor after another plan is loaded.
        page.panel.set_object_name("M 42")
        assert page.panel.to_plan().metadata == {}
        page.panel.set_object_name("HD 189733")
        page.panel.load_plan(
            SequencePlan(steps=[SequenceStep(filter_name="IR")], object_name="HD 189733")
        )
        assert page.panel.to_plan().metadata == {}
    finally:
        _dispose(page)


def test_preset_load_does_not_restore_a_stale_transit_window(tmp_path, monkeypatch) -> None:
    """S5: a transit window is for one event; a preset reused another night
    must not declare it in observation.json."""
    from argos.ui.widgets import sequence_panel as sp

    preset = tmp_path / "transit.json"
    preset.write_text(json.dumps(plan_to_dict(_transit_plan())))
    panel = sp.SequencePanel()
    try:
        monkeypatch.setattr(
            sp.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(preset), ""))
        )
        monkeypatch.setattr(panel, "_presets_dir", lambda: str(tmp_path))
        panel._on_load_preset()
        assert panel.to_plan().steps[0].cadence_s == 13.0  # the plan itself loads
        assert panel.to_plan().metadata == {}
        assert "Prepare transit" in panel._status_lbl.text()
    finally:
        _dispose(panel)
