"""Offline Review reads a durable session without mutating it."""

from __future__ import annotations

import json

from argos.core.session.review import load_session, load_session_curves


def test_load_session_summarises_frames_and_flags_missing_fits(tmp_path) -> None:
    root = tmp_path / "20260828T010203Z_HD189733"
    root.mkdir()
    (root / "session.json").write_text(
        json.dumps(
            {
                "object": "HD 189733",
                "software": "Argos 0.4.1",
                "started_utc": "2026-08-28T01:02:03+00:00",
                "frames": [
                    {
                        "filename": "hd189733_ir_light_00001.fit",
                        "image_type": "Light Frame",
                        "filter_name": "IR",
                        "exposure_s": 10,
                        "gain": 80,
                        "timestamp": "2026-08-28T01:02:03+00:00",
                        "fwhm": 2.1,
                        "hfd": 3.8,
                        "star_count": 155,
                    },
                    {
                        "filename": "hd189733_dark_00001.fit",
                        "image_type": "Dark Frame",
                        "filter_name": "Dark",
                        "exposure_s": 10,
                        "gain": 80,
                        "timestamp": "2026-08-28T01:03:03+00:00",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    review = load_session(root, read_temperature=False)

    assert review.object_name == "HD 189733"
    assert len(review.frames) == 2
    assert len(review.light_frames) == 1
    assert review.filter_counts == {"IR": 1, "Dark": 1}
    assert review.metric_samples()[0][0] == 0.0
    jd = review.light_frames[0].timestamp.timestamp() / 86_400.0 + 2_440_587.5
    assert review.nearest_light_frame(jd).filename.endswith("00001.fit")
    assert any("Missing FITS frame" in issue for issue in review.readiness_issues())


def test_review_recovers_roles_from_per_star_curve_files(tmp_path) -> None:
    root = tmp_path / "20260828T010203Z_XX_Cyg"
    photometry = root / "photometry"
    photometry.mkdir(parents=True)
    (root / "session.json").write_text(json.dumps({"object": "XX Cyg", "frames": []}))
    (root / "targets.json").write_text(
        json.dumps(
            {
                "object": "XX Cyg",
                "stars": [
                    {
                        "role": "target",
                        "ra_deg": 300.81517,
                        "dec_deg": 58.95458,
                        "auid": "000-BCK-301",
                        "name": "XX Cyg",
                    },
                    {
                        "role": "target",
                        "ra_deg": 300.81517513,
                        "dec_deg": 58.95459035,
                        "name": "XX Cyg",
                    },
                    {
                        "role": "comparison",
                        "ra_deg": 300.899125,
                        "dec_deg": 58.92267,
                        "auid": "000-BJV-171",
                        "name": "106",
                    },
                ],
            }
        )
    )
    header = "jd_utc,mag,mag_err,saturated\n"
    row = "2461281.7,11.6,0.02,0\n"
    (photometry / "target_XX_Cyg_000-BCK-301.csv").write_text(header + row)
    (photometry / "target_XX_Cyg_XX_Cyg.csv").write_text(header + row)
    (photometry / "comparison_XX_Cyg_000-BJV-171.csv").write_text(header + row)

    curves = load_session_curves(load_session(root, read_temperature=False))

    assert len(curves) == 2  # aliases of XX Cyg collapse to one physical target
    target = next(curve for curve in curves.values() if curve.role == "target")
    comparison = next(curve for curve in curves.values() if curve.role == "comparison")
    assert target.name == "XX Cyg"
    assert comparison.name == "106" and comparison.auid == "000-BJV-171"


def test_review_loads_persisted_comparison_quality(tmp_path) -> None:
    root = tmp_path / "20260828T010203Z_XX_Cyg"
    root.mkdir()
    (root / "session.json").write_text(json.dumps({"object": "XX Cyg", "frames": []}))
    (root / "photometry_quality.json").write_text(
        json.dumps(
            {
                "criteria": {"min_points": 10},
                "comparison_stars": [
                    {
                        "name": "106",
                        "auid": "000-BJV-171",
                        "n_valid": 12,
                        "scatter_mag": 0.021,
                        "median_formal_error_mag": 0.012,
                        "status": "stable",
                    }
                ],
            }
        )
    )

    review = load_session(root, read_temperature=False)

    assert review.comparison_quality["comparison_stars"][0]["status"] == "stable"


def _engine_like_session(tmp_path, *, with_targets: bool = True):
    """A run folder as the engine writes it: role-prefixed per-star CSVs."""
    from argos.core.catalog.targets import TargetSet, TargetStar

    root = tmp_path / "20261101T200000Z_SS_Cyg"
    photometry = root / "photometry"
    photometry.mkdir(parents=True)
    (root / "session.json").write_text(json.dumps({"object": "SS Cyg", "frames": []}))
    if with_targets:
        TargetSet(
            object_name="SS Cyg",
            stars=[
                TargetStar("target", 325.6780, 43.5862, auid="000-BCP-095", name="SS Cyg"),
                TargetStar("comparison", 325.70, 43.60, auid="000-AAA-111", name="111"),
                TargetStar("check", 325.65, 43.55, auid="000-KKK-222", name="K1"),
            ],
        ).save(root / "targets.json")
    header = "jd_utc,mag,mag_err,saturated\n"
    (photometry / "target_SS_Cyg_000-BCP-095.csv").write_text(header + "2461315.5,12.0,0.02,0\n")
    (photometry / "comparison_SS_Cyg_000-AAA-111.csv").write_text(
        header + "2461315.5,11.0,0.02,0\n"
    )
    (photometry / "check_SS_Cyg_000-KKK-222.csv").write_text(header + "2461315.5,12.5,0.02,0\n")
    return root


def test_review_keeps_check_star_role(tmp_path) -> None:
    """S9: a check_ file became a second science target named after its stem."""
    root = _engine_like_session(tmp_path)

    curves = load_session_curves(load_session(root, read_temperature=False))

    assert sorted(curve.role for curve in curves.values()) == ["check", "comparison", "target"]
    check = next(curve for curve in curves.values() if curve.role == "check")
    assert check.name == "K1" and check.auid == "000-KKK-222"
    assert not any(str(key).startswith("target:check_") for key in curves)


def _aavso_rows(path) -> list[str]:
    return [line for line in path.read_text().splitlines() if not line.startswith("#")]


def test_single_star_csv_restores_role_and_name(tmp_path) -> None:
    """S10: 'Open curve CSV' exported every per-star file as a science
    target named after the file stem — comparison stars included."""
    from argos.core.catalog.targets import TargetSet
    from argos.core.photometry.lightcurve import read_curves_csv, write_aavso
    from argos.core.session.review import identify_curve_file

    root = _engine_like_session(tmp_path)
    targets = TargetSet.load(root / "targets.json")
    photometry = root / "photometry"

    path = photometry / "comparison_SS_Cyg_000-AAA-111.csv"
    curves, problems = identify_curve_file(path, read_curves_csv(path), targets)
    ((comparison),) = curves.values()
    assert problems == []
    assert comparison.role == "comparison" and comparison.auid == "000-AAA-111"
    write_aavso(tmp_path / "comp.txt", list(curves.values()), obscode="ABC")
    assert _aavso_rows(tmp_path / "comp.txt") == []  # never a science row

    path = photometry / "target_SS_Cyg_000-BCP-095.csv"
    curves, problems = identify_curve_file(path, read_curves_csv(path), targets)
    ((target),) = curves.values()
    assert problems == [] and target.role == "target" and target.name == "SS Cyg"
    write_aavso(tmp_path / "target.txt", list(curves.values()), obscode="ABC")
    (row,) = _aavso_rows(tmp_path / "target.txt")
    assert row.startswith("SS CYG,2461315.500000,")

    # An unprefixed file (legacy, batch re-run) takes the role of its star.
    legacy = photometry / "SS_Cyg_000-AAA-111.csv"
    legacy.write_text("jd_utc,mag,mag_err,saturated\n2461315.5,11.0,0.02,0\n")
    curves, problems = identify_curve_file(legacy, read_curves_csv(legacy), targets)
    ((comparison),) = curves.values()
    assert problems == [] and comparison.role == "comparison"

    # Nothing to identify it with: say so rather than guess.
    curves, problems = identify_curve_file(legacy, read_curves_csv(legacy), TargetSet())
    assert problems and "role unknown" in problems[0]
