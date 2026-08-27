"""Unit tests for the Qt-free sequence model (no hardware, no Qt)."""

from __future__ import annotations

from argos.core.imaging.sequencer import (
    SequencePlan,
    SequenceStep,
    expand_plan,
    plan_from_dict,
    plan_to_dict,
    total_frames,
)


def test_total_and_expansion_count() -> None:
    plan = SequencePlan(
        steps=[
            SequenceStep(count=5),
            SequenceStep(frame_type="Dark", filter_name="NoFilter", count=3),
        ]
    )
    assert total_frames(plan) == 8
    assert len(list(expand_plan(plan))) == 8


def test_repeat_replays_step_list() -> None:
    plan = SequencePlan(steps=[SequenceStep(count=2)], repeat=3)
    assert total_frames(plan) == 6
    assert len(list(expand_plan(plan))) == 6


def test_ordering_and_step_index() -> None:
    plan = SequencePlan(
        steps=[
            SequenceStep(filter_name="Ha", count=2),
            SequenceStep(filter_name="OIII", count=2),
        ]
    )
    frames = list(expand_plan(plan))
    assert [f.filter_name for f in frames] == ["Ha", "Ha", "OIII", "OIII"]
    assert [f.step_index for f in frames] == [0, 0, 1, 1]


def test_wheel_filter_sends_calibration_frames_to_the_dark_slot() -> None:
    # A shutterless camera's wheel is its only shutter: Dark/Bias must sit on
    # the opaque slot whatever the step's filter says (field bug 2026-07-11 —
    # "darks" shot through IR were lights). Light/Flat keep the step's filter.
    plan = SequencePlan(
        steps=[
            SequenceStep(frame_type="Light", filter_name="IR", count=1),
            SequenceStep(frame_type="Dark", filter_name="IR", count=1),
            SequenceStep(frame_type="Bias", filter_name="LP", count=1),
            SequenceStep(frame_type="Flat", filter_name="LP", count=1),
        ]
    )
    frames = list(expand_plan(plan))
    assert [f.wheel_filter for f in frames] == ["IR", "Dark", "Dark", "LP"]


def test_frame_index_is_per_bucket_and_monotonic_across_repeats() -> None:
    plan = SequencePlan(steps=[SequenceStep(filter_name="Ha", count=3)], repeat=2)
    frames = list(expand_plan(plan))
    assert [f.frame_index for f in frames] == [1, 2, 3, 4, 5, 6]


def test_distinct_buckets_have_independent_counters() -> None:
    plan = SequencePlan(
        steps=[
            SequenceStep(filter_name="Ha", count=2),
            SequenceStep(filter_name="OIII", count=2),
        ]
    )
    frames = list(expand_plan(plan))
    by_filter = {}
    for f in frames:
        by_filter.setdefault(f.filter_name, []).append(f.frame_index)
    assert by_filter["Ha"] == [1, 2]
    assert by_filter["OIII"] == [1, 2]


def test_disabled_step_is_skipped() -> None:
    plan = SequencePlan(steps=[SequenceStep(count=2, enabled=False), SequenceStep(count=3)])
    assert total_frames(plan) == 3
    assert len(list(expand_plan(plan))) == 3


def test_zero_count_step_is_skipped() -> None:
    plan = SequencePlan(steps=[SequenceStep(count=0), SequenceStep(count=4)])
    assert total_frames(plan) == 4


def test_image_type_mapping_and_light_flag() -> None:
    dark = next(expand_plan(SequencePlan(steps=[SequenceStep(frame_type="Dark", count=1)])))
    assert dark.image_type == "Dark Frame"
    assert dark.is_light is False
    assert dark.needs_filter is False

    light = next(expand_plan(SequencePlan(steps=[SequenceStep(count=1)])))
    assert light.image_type == "Light Frame"
    assert light.is_light is True
    assert light.needs_filter is True


def test_preset_round_trip(tmp_path) -> None:
    plan = SequencePlan(
        steps=[
            SequenceStep(filter_name="Ha", count=4, exposure_s=60.0, gain=100, interval_s=2.0),
            SequenceStep(frame_type="Flat", filter_name="OIII", count=10),
        ],
        object_name="M42",
        repeat=2,
        autofocus_every_n=10,
        autofocus_on_filter_change=True,
        base_dir=tmp_path,
    )
    restored = plan_from_dict(plan_to_dict(plan))
    assert restored.object_name == "M42"
    assert restored.repeat == 2
    assert restored.autofocus_every_n == 10
    assert restored.autofocus_on_filter_change is True
    assert restored.base_dir == tmp_path
    assert len(restored.steps) == 2
    assert restored.steps[0].filter_name == "Ha"
    assert restored.steps[0].exposure_s == 60.0
    assert restored.steps[0].interval_s == 2.0
    assert restored.steps[1].frame_type == "Flat"


def test_preset_round_trip_without_base_dir() -> None:
    plan = SequencePlan(steps=[SequenceStep(count=1)])
    restored = plan_from_dict(plan_to_dict(plan))
    assert restored.base_dir is None
    assert total_frames(restored) == 1


def test_expand_plan_keeps_calibration_series_homogeneous() -> None:
    """Different gain/exposure settings must never reuse a Siril index series."""
    plan = SequencePlan(
        object_name="M42",
        steps=[
            SequenceStep(frame_type="Dark", filter_name="Dark", exposure_s=10.0, gain=80, count=1),
            SequenceStep(frame_type="Dark", filter_name="Dark", exposure_s=20.0, gain=80, count=1),
            SequenceStep(frame_type="Dark", filter_name="Dark", exposure_s=10.0, gain=100, count=1),
        ],
    )
    frames = list(expand_plan(plan))
    assert [frame.frame_index for frame in frames] == [1, 1, 1]


def test_on_complete_round_trip_and_default() -> None:
    from argos.core.imaging.sequencer import ON_COMPLETE_CHOICES

    plan = SequencePlan(steps=[SequenceStep(count=1)], on_complete="Park mount")
    assert plan.on_complete in ON_COMPLETE_CHOICES
    restored = plan_from_dict(plan_to_dict(plan))
    assert restored.on_complete == "Park mount"
    # Old presets (no key) default to the safe choice.
    legacy = plan_from_dict({"steps": [{"count": 1}]})
    assert legacy.on_complete == "Nothing"


def test_estimated_duration_counts_enabled_frames_only() -> None:
    from argos.core.imaging.sequencer import estimated_duration_s

    plan = SequencePlan(
        steps=[
            SequenceStep(count=10, exposure_s=30.0, interval_s=2.0),
            SequenceStep(count=99, exposure_s=60.0, enabled=False),
        ],
        repeat=2,
    )
    est = estimated_duration_s(plan)
    # 2 passes × 10 frames × (30 + 2 + overhead) — the disabled step is ignored.
    assert 2 * 10 * 32 <= est <= 2 * 10 * 40
