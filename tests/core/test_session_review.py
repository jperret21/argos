"""Offline Review reads a durable session without mutating it."""

from __future__ import annotations

import json

from argos.core.session.review import load_session


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
    assert any("Missing FITS frame" in issue for issue in review.readiness_issues())
