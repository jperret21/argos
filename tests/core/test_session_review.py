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
