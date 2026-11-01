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


def test_add_after_wheel_connect_never_defaults_a_light_step_to_the_opaque_slot() -> None:
    """S7: every Seestar wheel has 'Dark' at slot 0; '+ Add' and any unknown
    filter fell back to index 0, so a whole Light step shot black frames."""
    from argos.core.imaging.sequencer import expand_plan
    from argos.ui.widgets.sequence_panel import SequencePanel

    panel = SequencePanel()
    try:
        panel.set_filter_options(["Dark", "IR", "LP"])  # the wheel connected
        panel._add_row(False)  # what the "+ Add" button's clicked(bool) delivers
        step = panel.to_plan().steps[1]
        assert step.frame_type == "Light"
        assert next(expand_plan(SequencePlan(steps=[step]))).wheel_filter != "Dark"

        # A row whose filter vanishes from the wheel does not fall onto Dark either.
        panel.set_filter_options(["IR", "LP", "Halpha"])
        panel._table.cellWidget(1, 2).setCurrentText("Halpha")
        panel.set_filter_options(["Dark", "IR", "LP"])
        assert panel.to_plan().steps[1].filter_name == "IR"
    finally:
        _dispose(panel)


def test_preset_substitutions_are_reported() -> None:
    """S7: an unknown filter or a clamped exposure/gain changed silently."""
    from argos.ui.widgets.sequence_panel import SequencePanel

    panel = SequencePanel()
    try:
        panel.set_filter_options(["Dark", "IR", "LP"])
        notes = panel.load_plan(
            SequencePlan(
                steps=[SequenceStep(frame_type="Light", filter_name="V", exposure_s=900.0)]
            )
        )
        step = panel.to_plan().steps[0]
        assert step.filter_name == "IR"
        assert notes and any("'V'" in note for note in notes), notes
        assert any("900" in note for note in notes), notes
    finally:
        _dispose(panel)


def test_camera_disconnect_keeps_plan_values() -> None:
    """S7: a disconnect reset the ranges to the defaults and clamped 900 s to 600 s."""
    page, _engine = _page({})
    try:
        page.panel.set_camera_limits(0, 600, 0.0001, 3600.0)
        page.panel._table.cellWidget(0, 3).setValue(900.0)
        page._on_device_state("camera", "disconnected", "")
        assert page.panel.to_plan().steps[0].exposure_s == 900.0
    finally:
        _dispose(page)


def test_no_saved_site_draws_no_altitude_curve() -> None:
    """S26a: without a saved site the curve was computed for latitude and
    longitude 0/0 (Vega peaking at 51° instead of 84° at 45° N)."""
    page, _engine = _page({"site": {"name": "", "latitude": 0.0, "longitude": 0.0}})
    try:
        page.set_target_coordinates("Vega", 18.6156, 38.7837)
        x, _y = page.panel._visibility_plot._curve.getData()
        assert x is None or len(x) == 0
        assert "site" in page.panel._visibility_plot._summary.text().lower()
        assert page.panel.to_plan().object_name == "Vega"  # the identity still syncs
    finally:
        _dispose(page)


def test_transit_after_midnight_is_inside_the_plotted_night() -> None:
    """S26b: a 00:30-03:30 coverage was shaded outside the plotted 18:00-06:00."""
    from datetime import datetime, timedelta

    page, _engine = _page(_SITE)
    try:
        day = (datetime.now().astimezone() + timedelta(days=1)).date()
        start = datetime(day.year, day.month, day.day, 0, 30).astimezone()
        end = start + timedelta(hours=3)
        page.panel.set_transit_visibility("HD 189733", 20.0121, 22.7099, 45.0, 5.0, start, end)
        x, _y = page.panel._visibility_plot._curve.getData()
        assert x[0] <= start.timestamp() and end.timestamp() <= x[-1]
    finally:
        _dispose(page)


def test_find_planet_uses_the_baseline_field() -> None:
    """S26c: Find ignored the Baseline field (always 60 min)."""
    page, _engine = _page(_SITE)
    try:
        page.panel._transit_baseline_spin.setValue(20)
        page._on_exoplanet_resolved(_hd189733())
        assert page._transit_window.baseline_minutes == 20.0
    finally:
        _dispose(page)


def test_find_planet_reports_the_real_cause_when_coverage_is_unavailable() -> None:
    """S26d: a missing published duration was reported as a missing site."""
    import dataclasses

    page, _engine = _page(_SITE)
    try:
        page._on_exoplanet_resolved(dataclasses.replace(_hd189733(), duration_hours=None))
        text = page.panel._transit_result.text()
        assert "Observing site required" not in text
        assert "duration" in text
    finally:
        _dispose(page)
