"""Wave 6a, plan: the sequence draft, its presets and plan files (rows A59-A61).

Parity: totals, estimate and preset files come from the core model the Qt
Plan editor uses (``sequencer.py``); the Qt panel itself is driven offscreen
where the comparison needs it (estimate label, preset save and load).
No silent clamp: every value Qt's spin boxes clamp is an issue here.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from argos.core.imaging.sequencer import (
    SequencePlan,
    SequenceStep,
    estimated_duration_s,
    plan_from_dict,
    plan_to_dict,
    total_frames,
)
from argos.server import sequence_plan as sp
from argos.server.errors import ApiError
from tests.server.conftest import AUTH, receive_until, science_client

NOW = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)


def _plan(**over) -> dict:
    plan = {
        "schema": 2,
        "object_name": "SS Cyg",
        "repeat": 2,
        "autofocus_every_n": 5,
        "autofocus_on_filter_change": True,
        "on_complete": "Park mount",
        "base_dir": None,
        "metadata": {},
        "start_at_utc": None,
        "steps": [
            {
                "enabled": True,
                "frame_type": "Light",
                "filter_name": "IR",
                "exposure_s": 30.0,
                "gain": 80,
                "count": 20,
                "interval_s": 2.0,
                "cadence_s": None,
                "dither_every": 0,
            },
            {
                "enabled": True,
                "frame_type": "Light",
                "filter_name": "LP",
                "exposure_s": 10.0,
                "gain": 100,
                "count": 12,
                "interval_s": 0.0,
                "cadence_s": 13.0,
                "dither_every": 0,
            },
            {
                "enabled": False,
                "frame_type": "Dark",
                "filter_name": "Dark",
                "exposure_s": 30.0,
                "gain": 80,
                "count": 10,
                "interval_s": 0.0,
                "cadence_s": None,
                "dither_every": 0,
            },
        ],
    }
    plan.update(over)
    return plan


def _qt_plan(plan: dict) -> SequencePlan:
    return plan_from_dict({k: v for k, v in plan.items() if k not in ("schema", "start_at_utc")})


@pytest.fixture
def plan_client(make_client, tmp_path):
    """A client with a config folder (the draft is written there) and temporary data paths."""
    client = make_client(config_dir=tmp_path / "config")
    answer = client.patch(
        "/api/config",
        json={
            "sessions_path": str(tmp_path / "sessions"),
            "data_paths.sequence_presets_directory": str(tmp_path / "presets"),
        },
        headers=AUTH,
    )
    assert answer.status_code == 200, answer.text
    hub = client.app.state.hub
    hub.plan.clock = lambda: NOW
    client.hub = hub  # type: ignore[attr-defined]
    client.tmp = tmp_path  # type: ignore[attr-defined]
    return client


def _put(client, plan: dict, status: int = 200) -> dict:
    answer = client.put("/api/sequence/plan", json=plan, headers=AUTH)
    assert answer.status_code == status, answer.text
    return answer.json()


def force_run_active(monkeypatch, hub) -> None:
    """A run is active, through the hook the plan service asks (``hub.sequence.run_active``)."""
    if getattr(hub, "sequence", None) is not None:
        monkeypatch.setattr(hub.sequence, "run_active", lambda: True)
    else:
        monkeypatch.setattr(
            hub, "sequence", SimpleNamespace(run_active=lambda: True), raising=False
        )


def _codes(record: dict) -> set[tuple]:
    return {(i["step"], i["field"], i["code"], i["level"]) for i in record["issues"]}


# -- A59: the draft ---------------------------------------------------------------------


def test_the_first_draft_is_qt_s_first_row_on_a_light_slot(plan_client):
    record = plan_client.get("/api/sequence/plan", headers=AUTH).json()
    (step,) = record["plan"]["steps"]
    # SequenceStep() defaults, on the first slot that passes light (S7), never Dark.
    assert step == {**plan_to_dict(SequencePlan(steps=[SequenceStep()]))["steps"][0],
                    "filter_name": "IR"}  # fmt: skip
    assert record["plan"]["schema"] == 2 and record["plan"]["metadata"] == {}
    assert record["derived"]["total_frames"] == 10
    assert record["derived"]["estimate_s"] == 130.0  # 10 x (10 s + 0 + 3 s), Qt's floor
    assert record["filters"] == {"names": ["Dark", "IR", "LP"], "source": "profile"}
    assert record["limits"] == {"exposure_s": [0.01, 600.0], "gain": [0, 600], "source": "default"}
    assert record["locked"] is False and record["ready"] is True


@pytest.mark.parametrize(
    "over",
    [
        {},
        {"repeat": 1},
        {"repeat": 7},
        {"repeat": 0},  # Qt's max(1, repeat) in the estimate, and an issue
        {"steps": []},
    ],
)
def test_totals_and_estimate_are_the_core_s_on_the_same_plan(plan_client, over):
    plan = _plan(**over)
    record = _put(plan_client, plan)
    qt = _qt_plan(plan)
    derived = record["derived"]
    assert derived["total_frames"] == total_frames(qt)
    assert derived["estimate_s"] == pytest.approx(estimated_duration_s(qt), abs=0)
    assert sum(derived["per_step_s"]) * max(1, qt.repeat) == pytest.approx(derived["estimate_s"])
    assert len(derived["per_step_s"]) == len(plan["steps"])
    if plan["steps"]:
        # 20 x (30 + 2 + 3 s); 12 x 13 s cadence; a disabled step costs nothing.
        assert derived["per_step_s"] == [700.0, 156.0, 0.0]


def test_estimate_matches_the_qt_editor_label(plan_client):
    """The Qt Plan editor's estimate is ``estimated_duration_s(to_plan())``."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from argos.ui.widgets.sequence_panel import SequencePanel

    app = QApplication.instance() or QApplication(["test"])
    plan = _plan()
    panel = SequencePanel()
    try:
        notes = panel.load_plan(_qt_plan(plan))
        qt_estimate = estimated_duration_s(panel.to_plan())
        qt_total = total_frames(panel.to_plan())
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()
    assert notes == []
    record = _put(plan_client, plan)
    assert record["derived"]["estimate_s"] == qt_estimate == 2 * (700.0 + 156.0)
    assert record["derived"]["total_frames"] == qt_total == 64


def test_end_time_runs_from_now_or_from_the_scheduled_start(plan_client):
    record = _put(plan_client, _plan())
    estimate = record["derived"]["estimate_s"]
    assert record["derived"]["start_utc"] == "2026-11-12T18:00:00.000Z"
    end = NOW + timedelta(seconds=estimate)
    assert record["derived"]["end_utc"] == end.isoformat(timespec="milliseconds")[:-6] + "Z"

    later = _put(plan_client, _plan(start_at_utc="2026-11-12T21:30:00+01:00"))
    assert later["plan"]["start_at_utc"] == "2026-11-12T20:30:00.000Z"
    assert later["derived"]["start_utc"] == "2026-11-12T20:30:00.000Z"
    start = datetime(2026, 11, 12, 20, 30, tzinfo=timezone.utc)
    assert later["derived"]["end_utc"] == utc(start + timedelta(seconds=estimate))
    assert not any(i["code"] == "start_in_past" for i in later["issues"])

    past = _put(plan_client, _plan(start_at_utc="2026-11-12T17:00:00Z"))
    assert past["derived"]["start_utc"] == "2026-11-12T18:00:00.000Z"
    assert (None, "start_at_utc", "start_in_past", "warning") in _codes(past)


def utc(when: datetime) -> str:
    return when.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def test_no_silent_clamp_every_qt_clamp_is_an_issue_and_the_plan_is_stored_as_typed(plan_client):
    plan = _plan(
        repeat=1000,
        autofocus_every_n=-1,
        on_complete="Explode",
        base_dir="relative/folder",
        steps=[
            {"exposure_s": 900.0, "gain": 700, "count": 0, "interval_s": -1.0,
             "dither_every": 1000, "filter_name": "IR"},
            {"exposure_s": 10.0, "count": 10000, "interval_s": 3601.0, "cadence_s": 5.0,
             "filter_name": "IR"},
            {"frame_type": "Dusk", "cadence_s": 0.001, "filter_name": "IR"},
            {"enabled": False, "frame_type": "flat", "filter_name": "IR"},
        ],
    )  # fmt: skip
    record = _put(plan_client, plan)
    stored = record["plan"]
    # As typed: no value changed (Qt: 900 s -> 600 s, count 0 -> 1, "Explode" -> Nothing…).
    assert stored["steps"][0]["exposure_s"] == 900.0
    assert stored["steps"][0]["gain"] == 700
    assert stored["steps"][0]["count"] == 0
    assert stored["steps"][1]["count"] == 10000
    assert stored["steps"][2]["frame_type"] == "Dusk"
    assert stored["steps"][3]["frame_type"] == "Flat"  # plan_from_dict's case-insensitive match
    assert stored["repeat"] == 1000 and stored["on_complete"] == "Explode"
    assert stored["autofocus_every_n"] == -1 and stored["base_dir"] == "relative/folder"
    codes = _codes(record)
    for expected in [
        (0, "exposure_s", "out_of_range", "error"),
        (0, "gain", "out_of_range", "error"),
        (0, "count", "out_of_range", "error"),
        (0, "interval_s", "out_of_range", "error"),
        (0, "dither_every", "out_of_range", "error"),
        (1, "count", "out_of_range", "error"),
        (1, "interval_s", "out_of_range", "error"),
        (1, "cadence_s", "cadence_short", "error"),
        (1, "interval_s", "interval_ignored", "warning"),
        (2, "frame_type", "unknown_frame_type", "error"),
        (2, "cadence_s", "out_of_range", "error"),
        (None, "repeat", "out_of_range", "error"),
        (None, "autofocus_every_n", "out_of_range", "error"),
        (None, "on_complete", "unknown_on_complete", "error"),
        (None, "base_dir", "base_dir_relative", "error"),
    ]:
        assert expected in codes, expected
    assert record["ready"] is False
    message = next(i["message"] for i in record["issues"] if i["field"] == "exposure_s")
    assert message == "Step 1: exposure 900 s is outside 0.01–600 s (the range without a camera)."
    # The file keeps it as typed too.
    on_disk = json.loads(Path(record["path"]).read_text())
    assert on_disk["steps"][0]["exposure_s"] == 900.0


def test_the_qt_editor_would_have_clamped_those_values(plan_client):
    """The behaviour replaced: SequencePanel.load_plan adjusts and only notes it (S7)."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from argos.ui.widgets.sequence_panel import SequencePanel

    app = QApplication.instance() or QApplication(["test"])
    panel = SequencePanel()
    try:
        notes = panel.load_plan(
            SequencePlan(steps=[SequenceStep(exposure_s=900.0, count=0, filter_name="LRGB")])
        )
        qt = panel.to_plan()
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()
    assert qt.steps[0].exposure_s == 600.0 and qt.steps[0].count == 1  # count: not even noted
    assert any("900 s → 600 s" in n for n in notes)
    record = _put(
        plan_client,
        _plan(steps=[{"exposure_s": 900.0, "count": 0, "filter_name": "LRGB"}], repeat=1),
    )
    assert record["plan"]["steps"][0]["exposure_s"] == 900.0
    assert record["plan"]["steps"][0]["count"] == 0
    assert record["plan"]["steps"][0]["filter_name"] == "LRGB"
    assert {
        (0, "count", "out_of_range", "error"),
        (0, "filter_name", "unknown_filter", "warning"),
    } <= _codes(record)


def test_no_enabled_step_refuses_a_run(plan_client):
    record = _put(plan_client, _plan(steps=[{"enabled": False, "filter_name": "IR"}]))
    assert (None, "steps", "no_enabled_step", "error") in _codes(record)
    with pytest.raises(ApiError) as caught:
        plan_client.hub.plan.plan_for_run()
    assert caught.value.status == 400
    assert caught.value.message == "Fix the plan: add an enabled step."


def test_plan_for_run_names_the_first_error_and_gives_the_core_plan(plan_client):
    _put(plan_client, _plan(steps=[{"exposure_s": 10.0, "cadence_s": 5.0, "filter_name": "IR"}]))
    with pytest.raises(ApiError) as caught:
        plan_client.hub.plan.plan_for_run()
    assert caught.value.message == "Fix step 1: cadence 5 s is shorter than the 10 s exposure."
    plan = _plan()
    _put(plan_client, plan)
    run = plan_client.hub.plan.plan_for_run()
    assert isinstance(run, SequencePlan)
    assert plan_to_dict(run) == plan_to_dict(_qt_plan(plan))


def test_s7_light_on_the_dark_slot_and_unknown_filters_with_the_wheel(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("filterwheel",))
    plan = _plan(
        steps=[
            {"frame_type": "Light", "filter_name": "Dark"},
            {"frame_type": "Flat", "filter_name": "LRGB"},
            {"frame_type": "Dark", "filter_name": "IR"},  # Dark/Bias go to the Dark slot
            {"frame_type": "Light", "filter_name": "ir"},  # the wheel's match is case-insensitive
        ]
    )
    record = _put(client, plan)
    assert record["filters"]["source"] == "wheel"
    codes = _codes(record)
    assert (0, "filter_name", "dark_slot", "error") in codes  # the engine refuses it too
    assert (1, "filter_name", "unknown_filter", "error") in codes
    assert not any(i["step"] in (2, 3) and i["field"] == "filter_name" for i in record["issues"])
    message = next(i["message"] for i in record["issues"] if i["code"] == "dark_slot")
    assert message == "Step 1: a Light step on the opaque Dark slot gives black frames."
    with pytest.raises(ApiError) as caught:
        client.app.state.hub.plan.plan_for_run()
    assert caught.value.message == (
        "Fix step 1: a Light step on the opaque Dark slot gives black frames."
    )


def test_camera_limits_then_the_last_camera_s_after_a_disconnect(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera",))
    plan = _plan(steps=[{"exposure_s": 900.0, "filter_name": "IR"}], repeat=1)
    record = _put(client, plan)
    # Sim camera 0.001-3600 s: Qt's set_camera_limits keeps 0.01 s as the floor.
    assert record["limits"] == {"exposure_s": [0.01, 3600.0], "gain": [0, 600], "source": "camera"}
    assert not any(i["field"] == "exposure_s" for i in record["issues"])
    assert client.delete("/api/devices/camera", headers=AUTH).status_code == 200
    record = client.get("/api/sequence/plan", headers=AUTH).json()
    # S7: a camera disconnect no longer resets the ranges (900 s stayed valid).
    assert record["limits"]["source"] == "last_camera"
    assert not any(i["field"] == "exposure_s" for i in record["issues"])


@pytest.mark.parametrize(
    "body, text",
    [
        ({"steps": [{"exposure_s": "10"}]}, "step 1: exposure_s"),
        ({"steps": [{"gain": 80.0}]}, "gain"),
        ({"steps": [{"enabled": 1}]}, "enabled"),
        ({"steps": [{"colour": "red"}]}, "colour"),
        ({"surprise": 1}, "surprise"),
        ({"schema": 3}, "schema"),
        ({"start_at_utc": "tonight"}, "start_at_utc"),
        ({"metadata": {"nested": {"a": 1}}}, "metadata"),
        ({"steps": [{"exposure_s": 1e12}]}, "exposure_s"),
    ],
)
def test_the_body_is_strict(plan_client, body, text):
    answer = plan_client.put("/api/sequence/plan", json=body, headers=AUTH)
    assert answer.status_code == 400, answer.text
    assert answer.json()["error"]["code"] == "invalid_argument"
    assert text.split(":")[-1].strip() in answer.json()["error"]["message"]


def test_a_non_finite_number_is_refused(plan_client):
    answer = plan_client.put(
        "/api/sequence/plan",
        content=b'{"steps": [{"exposure_s": NaN}]}',
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert answer.status_code == 400


def test_the_draft_is_restored_after_a_restart(make_client, tmp_path):
    config = tmp_path / "config"
    first = make_client(config_dir=config)
    plan = _plan(start_at_utc="2026-11-12T21:00:00Z", metadata={"note": "x"})
    _put(first, plan)
    path = config / sp.DRAFT_FILENAME
    on_disk = json.loads(path.read_text())
    # The draft file is a Plan, and a Qt preset: plan_from_dict reads it.
    assert plan_to_dict(plan_from_dict(on_disk)) == plan_to_dict(_qt_plan(plan))
    second = make_client(config_dir=config)
    restored = second.get("/api/sequence/plan", headers=AUTH).json()
    assert restored["plan"] == {**plan, "start_at_utc": "2026-11-12T21:00:00.000Z"}


def test_the_draft_is_written_atomically(plan_client, monkeypatch):
    first = _put(plan_client, _plan())
    path = Path(first["path"])
    before = path.read_bytes()

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(sp.os, "replace", fail)
    answer = plan_client.put("/api/sequence/plan", json=_plan(repeat=5), headers=AUTH)
    assert answer.status_code == 500
    assert "disk full" in answer.json()["error"]["message"]
    monkeypatch.undo()
    assert path.read_bytes() == before  # never a half-written draft
    assert [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")] == []
    # The previous draft is still the one served.
    assert plan_client.get("/api/sequence/plan", headers=AUTH).json()["plan"]["repeat"] == 2


def test_an_unreadable_draft_is_kept_aside(make_client, tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / sp.DRAFT_FILENAME).write_text("{not json")
    client = make_client(config_dir=config)
    record = client.get("/api/sequence/plan", headers=AUTH).json()
    assert len(record["plan"]["steps"]) == 1
    kept = list(config.glob(f"{sp.DRAFT_FILENAME}.unreadable-*"))
    assert len(kept) == 1 and kept[0].read_text() == "{not json"
    assert "kept as" in record["notes"][0]


def test_the_plan_is_locked_while_a_run_is_active(plan_client, monkeypatch):
    hub = plan_client.hub
    _put(plan_client, _plan())
    force_run_active(monkeypatch, hub)
    answer = plan_client.put("/api/sequence/plan", json=_plan(repeat=3), headers=AUTH)
    assert answer.status_code == 409
    assert answer.json()["error"] == {
        "code": "run_active",
        "message": "The plan is locked while the sequence runs.",
    }
    record = plan_client.get("/api/sequence/plan", headers=AUTH).json()
    assert record["locked"] is True and record["plan"]["repeat"] == 2
    assert record["locked_reason"] == "The plan is locked while the sequence runs."
    answer = plan_client.post(
        "/api/sequence/plan/import", json={"preset": "anything"}, headers=AUTH
    )
    assert answer.status_code == 409
    # Presets save and export stay available during a run.
    assert plan_client.put("/api/sequence/presets/during", headers=AUTH).status_code == 200
    target = plan_client.tmp / "sessions" / "during.json"
    target.parent.mkdir(parents=True, exist_ok=True)  # export needs an existing folder
    answer = plan_client.post("/api/sequence/plan/export", json={"path": str(target)}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    answer = plan_client.post("/api/sequence/plan/import", json={"preset": "during"}, headers=AUTH)
    assert answer.status_code == 409
    monkeypatch.undo()
    assert plan_client.get("/api/sequence/plan", headers=AUTH).json()["locked"] is False


def test_one_object_per_plan_shared_with_the_observation(plan_client):
    record = _put(plan_client, _plan(object_name="  T   CrB "))
    assert record["plan"]["object_name"] == "T CrB"
    assert plan_client.get("/api/observation", headers=AUTH).json()["object_name"] == "T CrB"
    # Observe changes the object: the draft follows.
    plan_client.put("/api/observation", json={"object_name": "RR Lyr"}, headers=AUTH)
    record = plan_client.get("/api/sequence/plan", headers=AUTH).json()
    assert record["plan"]["object_name"] == "RR Lyr"
    assert record["notes"] == ["Object follows the observation: RR Lyr."]
    # An empty name never clears the observation (P10: a calibration preset).
    record = _put(plan_client, _plan(object_name=""))
    assert plan_client.get("/api/observation", headers=AUTH).json()["object_name"] == "RR Lyr"
    assert record["plan"]["object_name"] == "RR Lyr"


def test_s5_metadata_is_kept_for_its_own_object_only(plan_client):
    metadata = {"observation_type": "exoplanet_transit", "planet_name": "HD 189733 b"}
    record = _put(plan_client, _plan(object_name="HD 189733", metadata=metadata))
    assert record["plan"]["metadata"] == metadata
    # An echo of the draft (a cell edit) keeps it.
    record = _put(plan_client, {**record["plan"], "repeat": 3})
    assert record["plan"]["metadata"] == metadata
    # Another object: dropped, and said.
    record = _put(plan_client, {**record["plan"], "object_name": "WASP-12"})
    assert record["plan"]["metadata"] == {}
    assert "Planning metadata dropped: it was prepared for HD 189733." in record["notes"]
    # The same through Observe.
    _put(plan_client, _plan(object_name="HD 189733", metadata=metadata))
    plan_client.put("/api/observation", json={"object_name": "XX Cyg"}, headers=AUTH)
    record = plan_client.get("/api/sequence/plan", headers=AUTH).json()
    assert record["plan"]["metadata"] == {}
    assert plan_client.hub.plan.plan_for_run().metadata == {}


def test_observation_json_is_written_as_the_qt_worker_writes_it(plan_client, tmp_path):
    """``observation_json`` is SequenceWorker._write_observation_metadata's text."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np
    from PyQt6.QtWidgets import QApplication

    from argos.core.imaging.fits_writer import FrameContext
    from argos.workers.sequence_worker import OBSERVATION_FILENAME, SequenceWorker

    QApplication.instance() or QApplication(["test"])
    metadata = {"observation_type": "exoplanet_transit", "epoch_bjd_tdb": 2454279.436714,
                "depth_percent": None, "planet_name": "HD 189733 b"}  # fmt: skip
    _put(
        plan_client,
        _plan(object_name="HD 189733", metadata=metadata, repeat=1,
              steps=[{"exposure_s": 0.01, "count": 1, "filter_name": "IR"}]),
    )  # fmt: skip
    plan = plan_client.hub.plan.plan_for_run()

    class Camera:
        def set_gain(self, gain):
            pass

        def try_get_gain(self):
            return 80

        def start_exposure(self, exposure_s, light=True):
            pass

        def is_image_ready(self):
            return True

        def get_image_array(self):
            return np.full((32, 32), 1000, dtype=np.uint16)

        def stop_exposure(self):
            pass

    SequenceWorker(
        camera=Camera(),
        telescope=None,
        filterwheel=None,
        plan=plan,
        frame_context_provider=lambda object_name, filter_name: FrameContext(
            object_name=object_name, filter_name=filter_name
        ),
        base_dir=tmp_path / "qt-run",
    ).run()
    (written,) = (tmp_path / "qt-run").glob("*/" + OBSERVATION_FILENAME)
    assert written.read_text(encoding="utf-8") == sp.observation_json(plan)


def test_sequence_plan_event_after_a_change(plan_client):
    with plan_client.websocket_connect(f"/ws/events?token={AUTH['Authorization'][7:]}") as ws:
        record = _put(plan_client, _plan(repeat=4))
        event = receive_until(
            ws, lambda m: m.get("type") == "sequence_plan" and m["plan"]["repeat"] == 4
        )
        assert event["revision"] == record["revision"]
        assert event["derived"] == record["derived"]


# -- A60: presets ------------------------------------------------------------------------


def test_presets_are_saved_listed_read_and_deleted_in_qt_s_format(plan_client):
    plan = _plan()
    answer = plan_client.put("/api/sequence/presets/T CrB 10s", json=plan, headers=AUTH)
    assert answer.status_code == 200, answer.text
    listing = answer.json()
    directory = plan_client.tmp / "presets"
    assert listing["directory"] == str(directory)
    (row,) = listing["presets"]
    assert row["name"] == "T CrB 10s" and row["error"] is None
    assert row["total_frames"] == 64 and row["object_name"] == "SS Cyg"
    path = directory / "T CrB 10s.json"
    # Exactly what Qt's Save preset writes: plan_to_dict, indent 2, no schema.
    assert path.read_text() == json.dumps(plan_to_dict(_qt_plan(plan)), indent=2)
    got = plan_client.get("/api/sequence/presets/T CrB 10s.json", headers=AUTH).json()
    assert got["plan"] == plan and got["name"] == "T CrB 10s"
    assert got["derived"]["total_frames"] == 64
    again = plan_client.put("/api/sequence/presets/T CrB 10s", json=plan, headers=AUTH)
    assert again.status_code == 409 and again.json()["error"]["code"] == "file_exists"
    over = plan_client.put(
        "/api/sequence/presets/T CrB 10s?overwrite=true", json=_plan(repeat=1), headers=AUTH
    )
    assert over.status_code == 200 and over.json()["presets"][0]["total_frames"] == 32
    assert plan_client.delete("/api/sequence/presets/T CrB 10s", headers=AUTH).json() == {
        "directory": str(directory),
        "presets": [],
    }
    assert plan_client.delete("/api/sequence/presets/T CrB 10s", headers=AUTH).status_code == 404
    assert plan_client.get("/api/sequence/presets/T CrB 10s", headers=AUTH).status_code == 404


def test_saving_a_preset_without_a_body_saves_the_draft(plan_client):
    _put(plan_client, _plan(object_name="RR Lyr"))
    assert plan_client.put("/api/sequence/presets/draft", headers=AUTH).status_code == 200
    got = plan_client.get("/api/sequence/presets/draft", headers=AUTH).json()
    assert got["plan"]["object_name"] == "RR Lyr"


@pytest.mark.parametrize("name", ["..", ".hidden", "a:b", " lead", "trail ", "x" * 101, "a*b"])
def test_preset_names_are_validated(plan_client, name):
    with pytest.raises(ApiError) as caught:
        sp.preset_name(name)
    assert (caught.value.status, caught.value.code) == (400, "invalid_argument")
    answer = plan_client.put(f"/api/sequence/presets/{name}", headers=AUTH)
    # ".." never reaches the route: the client resolves it in the URL.
    assert answer.status_code == 400 or name == "..", answer.text
    assert set(plan_client.tmp.rglob("*.json")) == set(plan_client.tmp.glob("config/*.json"))


def test_a_file_qt_cannot_read_is_listed_with_its_reason(plan_client):
    directory = plan_client.tmp / "presets"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "broken.json").write_text(json.dumps({"steps": [{"colour": "red"}]}))
    (directory / "dusk.json").write_text(json.dumps({"steps": [{"frame_type": "Dusk"}]}))
    (directory / ".hidden.json").write_text("{}")
    rows = {
        r["name"]: r
        for r in plan_client.get("/api/sequence/presets", headers=AUTH).json()["presets"]
    }
    assert set(rows) == {"broken", "dusk"}
    assert rows["broken"]["error"] == "broken.json: unknown step key 'colour'"
    assert "unknown frame type 'Dusk'" in rows["dusk"]["error"]
    answer = plan_client.get("/api/sequence/presets/broken", headers=AUTH)
    assert answer.status_code == 400


def test_presets_round_trip_between_qt_and_the_web(plan_client, monkeypatch):
    """A web preset loads in the Qt editor unchanged; a Qt preset reads back in the web."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QFileDialog

    from argos.ui.widgets import sequence_panel as qt_panel

    app = QApplication.instance() or QApplication(["test"])
    directory = plan_client.tmp / "presets"
    plan = _plan(metadata={"observation_type": "test"})

    # web -> Qt: the file the server wrote, through Qt's Load preset.
    assert plan_client.put("/api/sequence/presets/web", json=plan, headers=AUTH).status_code == 200
    panel = qt_panel.SequencePanel()
    try:
        panel._config = {"data_paths.sequence_presets_directory": str(directory)}
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *a, **k: (str(directory / "web.json"), "")
        )
        panel._on_load_preset()
        status = panel._status_lbl.text()
        loaded = panel.to_plan()
        # Qt -> web: Qt's Save preset of the same editor state.
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName", lambda *a, **k: (str(directory / "qt"), "")
        )
        panel._on_save_preset()
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()
    assert "adjusted" not in status  # nothing substituted or clamped
    assert "planning metadata not restored" in status  # Qt's own rule, as the web's import
    expected = plan_to_dict(_qt_plan({**plan, "metadata": {}}))
    assert plan_to_dict(loaded) == expected
    got = plan_client.get("/api/sequence/presets/qt", headers=AUTH).json()
    assert got["plan"] == {**plan, "metadata": {}}
    imported = plan_client.post("/api/sequence/plan/import", json={"preset": "web"}, headers=AUTH)
    assert imported.status_code == 200, imported.text
    record = imported.json()
    assert record["plan"] == {**plan, "metadata": {}}  # the web's Load: Qt's rule too
    assert record["notes"] == ["Loaded web.", sp.METADATA_NOT_RESTORED]


# -- A61: import / export ------------------------------------------------------------------


def test_export_and_import_a_plan_file(plan_client):
    plan = _plan(metadata={"planet_name": "HD 189733 b"}, object_name="HD 189733")
    _put(plan_client, plan)
    sessions = plan_client.tmp / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    answer = plan_client.post(
        "/api/sequence/plan/export", json={"path": str(sessions / "tonight")}, headers=AUTH
    )
    assert answer.status_code == 200, answer.text
    target = sessions / "tonight.json"  # Qt appends .json
    assert answer.json() == {"path": str(target.resolve())}
    # Qt's format, metadata included (as Qt's Save preset).
    assert target.read_text() == json.dumps(plan_to_dict(_qt_plan(plan)), indent=2)
    again = plan_client.post("/api/sequence/plan/export", json={"path": str(target)}, headers=AUTH)
    assert again.status_code == 409 and again.json()["error"]["code"] == "file_exists"
    assert (
        plan_client.post(
            "/api/sequence/plan/export", json={"path": str(target), "overwrite": True}, headers=AUTH
        ).status_code
        == 200
    )
    bad = plan_client.post(
        "/api/sequence/plan/export", json={"path": str(sessions / "x.txt")}, headers=AUTH
    )
    assert bad.status_code == 400

    _put(plan_client, _plan(repeat=9))
    imported = plan_client.post(
        "/api/sequence/plan/import", json={"path": str(target)}, headers=AUTH
    ).json()
    assert imported["plan"]["repeat"] == 2
    assert imported["plan"]["metadata"] == {}
    assert sp.METADATA_NOT_RESTORED in imported["notes"]


@pytest.mark.parametrize(
    "body, status",
    [
        ({"path": "relative.json"}, 400),
        ({"path": "/etc/hosts.json"}, 403),
        ({"preset": "missing"}, 404),
        ({"preset": "a", "path": "/x.json"}, 400),
        ({}, 400),
    ],
)
def test_import_errors(plan_client, body, status):
    answer = plan_client.post("/api/sequence/plan/import", json=body, headers=AUTH)
    assert answer.status_code == status, answer.text


def test_import_of_a_missing_file_and_of_a_file_qt_cannot_read(plan_client):
    sessions = plan_client.tmp / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    missing = plan_client.post(
        "/api/sequence/plan/import", json={"path": str(sessions / "none.json")}, headers=AUTH
    )
    assert missing.status_code == 404
    (sessions / "bad.json").write_text(json.dumps({"steps": [{"colour": 1}]}))
    bad = plan_client.post(
        "/api/sequence/plan/import", json={"path": str(sessions / "bad.json")}, headers=AUTH
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["message"] == "bad.json: unknown step key 'colour'"


def test_plan_files_get_a_plain_file_s_mode_and_export_needs_its_folder(plan_client):
    """Technical review: mkstemp left 0600; export created any missing folder."""
    umask = os.umask(0)
    os.umask(umask)
    expected = 0o666 & ~umask
    _put(plan_client, _plan())
    assert (
        plan_client.put("/api/sequence/presets/mode", json=_plan(), headers=AUTH).status_code == 200
    )
    preset = plan_client.tmp / "presets" / "mode.json"
    assert preset.stat().st_mode & 0o777 == expected
    sessions = plan_client.tmp / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    target = sessions / "shared.json"
    answer = plan_client.post("/api/sequence/plan/export", json={"path": str(target)}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    assert target.stat().st_mode & 0o777 == expected
    target.chmod(0o640)  # a replaced file keeps its own mode
    answer = plan_client.post(
        "/api/sequence/plan/export", json={"path": str(target), "overwrite": True}, headers=AUTH
    )
    assert answer.status_code == 200 and target.stat().st_mode & 0o777 == 0o640
    deep = sessions / "a" / "b" / "plan.json"
    answer = plan_client.post("/api/sequence/plan/export", json={"path": str(deep)}, headers=AUTH)
    assert answer.status_code == 400 and "No folder" in answer.json()["error"]["message"]
    assert not (sessions / "a").exists()
    draft = plan_client.hub.plan._path
    assert draft.stat().st_mode & 0o777 == expected


def test_light_steps_through_two_filters_are_a_warning_s49(plan_client):
    """Release S49: each filter gets its own light curve and CSV; the plan says so."""
    steps = [
        {"frame_type": "Light", "filter_name": "IR", "count": 5},
        {"frame_type": "Dark", "filter_name": "Dark", "count": 5},
    ]
    assert not any(
        i["code"] == "light_filters" for i in _put(plan_client, _plan(steps=steps))["issues"]
    )
    steps.append({"frame_type": "Light", "filter_name": "LP", "count": 5})
    record = _put(plan_client, _plan(steps=steps))
    (issue,) = [i for i in record["issues"] if i["code"] == "light_filters"]
    assert (issue["step"], issue["field"], issue["level"]) == (None, "filter_name", "warning")
    assert issue["message"] == (
        "Light steps use 2 filters (IR and LP): each star gets one light curve and one "
        "CSV per filter."
    )  # the Qt editor's words (release sequencer.light_filters_warning)
    steps[2]["enabled"] = False
    assert not any(
        i["code"] == "light_filters" for i in _put(plan_client, _plan(steps=steps))["issues"]
    )


def _core_light_filters_warning():
    """GUARD (pending merge of release/0.5.0): the core's S49 plan warning, or None."""
    from argos.core.imaging import sequencer

    return getattr(sequencer, "light_filters_warning", None)


@pytest.mark.skipif(
    _core_light_filters_warning() is None,
    reason="the core has no S49 yet (release/0.5.0 not merged)",
)
def test_the_two_filter_warning_is_the_qt_editors_s49():
    """The server's ``light_filters`` issue says what the Qt sequence panel says."""
    core = _core_light_filters_warning()
    cases = [
        [("Light", "IR", 5, True)],
        [("Light", "IR", 5, True), ("Light", "LP", 5, True)],
        [("Light", "IR", 5, True), ("Light", "LP", 5, False), ("Dark", "Dark", 5, True)],
        [("Light", "V", 5, True), ("Light", "B", 5, True), ("Light", "V", 3, True)],
        [("Light", "Ha", 5, True), ("Light", "ha", 5, True)],  # one token: one curve
        [("Light", "", 5, True), ("Light", "IR-cut", 5, True), ("Light", "LRGB", 0, True)],
        [("Flat", "IR", 5, True), ("Light", "LP", 5, True)],
    ]
    for steps in cases:
        plan = SequencePlan(
            steps=[
                SequenceStep(frame_type=t, filter_name=f, count=n, enabled=on)
                for t, f, n, on in steps
            ]
        )
        assert sp.light_filters_warning(plan_to_dict(plan)) == core(plan), steps
