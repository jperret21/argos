"""Scientific live-preview validation of leave-one-out comparison curves."""

from __future__ import annotations

import json

from argos.core.catalog.targets import ROLE_COMPARISON, TargetSet, TargetStar
from argos.core.photometry.lightcurve import LcPoint, LightCurve
from argos.core.photometry.quality import comparison_quality_report, save_comparison_quality_report


def _curve(name: str, values: list[float], error: float = 0.02) -> LightCurve:
    curve = LightCurve(auid=name, name=name, role=ROLE_COMPARISON)
    for index, value in enumerate(values):
        curve.append(LcPoint(2450000.0 + index / 1440.0, value, error, formal_mag_err=error))
    return curve


def test_quality_report_marks_stable_ensemble_after_ten_points(tmp_path) -> None:
    target_set = TargetSet(
        object_name="Test",
        stars=[
            TargetStar(ROLE_COMPARISON, 1.0, 1.0, auid="C1"),
            TargetStar(ROLE_COMPARISON, 2.0, 2.0, auid="C2"),
            TargetStar(ROLE_COMPARISON, 3.0, 3.0, auid="C3"),
        ],
    )
    values = [10.0, 10.01, 9.99, 10.0, 10.01, 10.0, 9.99, 10.0, 10.01, 10.0]
    report = comparison_quality_report(
        target_set, {name: _curve(name, values) for name in ("C1", "C2", "C3")}
    )
    assert report["selection_status"] == "live_preview_consistent"
    assert {entry["status"] for entry in report["comparison_stars"]} == {"stable"}

    path = tmp_path / "photometry_quality.json"
    save_comparison_quality_report(path, report)
    assert json.loads(path.read_text())["selection_status"] == "live_preview_consistent"


def test_quality_report_never_calls_short_or_noisy_curve_stable() -> None:
    target_set = TargetSet(stars=[TargetStar(ROLE_COMPARISON, 1.0, 1.0, auid="C1")])
    short = _curve("C1", [10.0, 10.2, 9.8])
    report = comparison_quality_report(target_set, {"C1": short})
    assert report["selection_status"] == "insufficient_data"
    assert report["comparison_stars"][0]["status"] == "insufficient_data"
