from __future__ import annotations

from pathlib import Path

import pytest

from argos.core.catalog import exoplanets
from argos.core.catalog.exoplanets import (
    ExoplanetLookupError,
    lookup_exoplanet,
    normalize_exoplanet_designation,
)
from argos.core.exoplanet.transit import make_transit_sequence, predict_next_transit

_ROW = {
    "pl_name": "HD 189733 b",
    "hostname": "HD 189733",
    "ra": 300.1821,
    "dec": 22.7099,
    "pl_orbper": 2.21857567,
    "pl_orbpererr1": 0.00000015,
    "pl_tranmid": 2454279.436714,
    "pl_tranmiderr1": 0.000017,
    "pl_tranmid_systemref": "BJD TDB",
    "pl_trandur": 1.827,
    "pl_trandep": 2.4,
}


def test_lookup_parses_and_caches_nasa_ephemeris(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return [_ROW]

    def fake_get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr(exoplanets.requests, "get", fake_get)
    cache = tmp_path / "exoplanets.json"
    first = lookup_exoplanet("HD 189733 b", cache_path=cache)
    second = lookup_exoplanet("  hd  189733   b ", cache_path=cache)

    assert first.planet_name == "HD 189733 b"
    assert first.host_name == "HD 189733"
    assert first.ra_hours == pytest.approx(20.01214)
    assert first.duration_hours == pytest.approx(1.827)
    assert second == first
    assert calls == 1


def test_lookup_requires_planet_name(tmp_path: Path) -> None:
    with pytest.raises(ExoplanetLookupError, match="planet designation"):
        lookup_exoplanet(" ", cache_path=tmp_path / "exoplanets.json")


def test_compact_designation_is_normalised_and_falls_back_to_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    replies = [[], [_ROW]]

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return replies.pop(0)

    monkeypatch.setattr(exoplanets.requests, "get", lambda *_a, **_kw: Response())
    result = lookup_exoplanet("hd18973", cache_path=tmp_path / "exoplanets.json")
    assert normalize_exoplanet_designation("HD189733B") == "HD 189733 b"
    assert result.planet_name == "HD 189733 b"


def test_predicts_coverage_and_builds_stable_light_sequence(tmp_path: Path, monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return [_ROW]

    monkeypatch.setattr(exoplanets.requests, "get", lambda *_a, **_kw: Response())
    target = lookup_exoplanet("HD 189733 b", cache_path=tmp_path / "exoplanets.json")
    window = predict_next_transit(target, target.epoch_bjd_tdb + 0.1, baseline_minutes=60)
    plan = make_transit_sequence(
        target,
        window,
        exposure_s=10.0,
        cadence_s=13.0,
        gain=80,
        filter_name="IR",
    )

    assert window.epoch_number == 1
    assert window.ingress_bjd_tdb < window.mid_bjd_tdb < window.egress_bjd_tdb
    assert window.coverage_hours == pytest.approx(target.duration_hours + 2.0)
    assert plan.object_name == "HD 189733"
    assert plan.autofocus_every_n == 0
    assert plan.autofocus_on_filter_change is False
    assert len(plan.steps) == 1
    assert plan.steps[0].frame_type == "Light"
    assert plan.steps[0].interval_s == 0.0
    assert plan.steps[0].cadence_s == pytest.approx(13.0)
    assert plan.steps[0].dither_every == 0
    assert plan.steps[0].count * 13.0 >= window.coverage_hours * 3600.0
    assert plan.metadata["observation_type"] == "exoplanet_transit"
    assert plan.metadata["planet_name"] == "HD 189733 b"
    assert plan.metadata["coverage_end_bjd_tdb"] == window.coverage_end_bjd_tdb


def test_transit_sequence_rejects_cadence_shorter_than_exposure(
    tmp_path: Path, monkeypatch
) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return [_ROW]

    monkeypatch.setattr(exoplanets.requests, "get", lambda *_a, **_kw: Response())
    target = lookup_exoplanet("HD 189733 b", cache_path=tmp_path / "exoplanets.json")
    window = predict_next_transit(target, target.epoch_bjd_tdb)
    with pytest.raises(ValueError, match="cannot be shorter"):
        make_transit_sequence(
            target,
            window,
            exposure_s=13.0,
            cadence_s=10.0,
            gain=80,
            filter_name="IR",
        )
