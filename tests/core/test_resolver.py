"""Simbad sim-script response parser + disk-cache flow."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from seercontrol.core.targets import resolver
from seercontrol.core.targets.resolver import (
    _parse_simbad_response,
    resolve_name,
)


# --------------------------------------------------------------------------- #
# Pure parser tests                                                            #
# --------------------------------------------------------------------------- #

def test_parses_typical_simbad_response() -> None:
    body = (
        ":: data ::::\n"
        "##|M  42|83.82208333|-5.39111111|HII|4.00|##\n"
    )
    target = _parse_simbad_response(body, queried_name="M42")
    assert target is not None
    assert target.name == "M  42"
    assert target.ra_hours == pytest.approx(83.82208333 / 15.0, abs=1e-4)
    assert target.dec_degrees == pytest.approx(-5.39111111, abs=1e-4)
    assert target.object_type == "HII"
    assert target.magnitude == pytest.approx(4.00)


def test_parses_response_without_magnitude() -> None:
    body = "##|T CrB|239.875|25.92|Nova|~|##\n"
    target = _parse_simbad_response(body, queried_name="T CrB")
    assert target is not None
    assert target.magnitude is None


def test_returns_none_when_simbad_reports_not_found() -> None:
    body = (
        "::error::\n"
        "[3] Identifier not found in the database : NOPE-1234\n"
    )
    assert _parse_simbad_response(body, queried_name="NOPE-1234") is None


def test_returns_none_on_unparseable_response() -> None:
    assert _parse_simbad_response("hello world", queried_name="X") is None


# --------------------------------------------------------------------------- #
# End-to-end resolve_name (network mocked)                                     #
# --------------------------------------------------------------------------- #

class _FakeResp:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self.status_code = status


def test_resolve_name_caches_to_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []

    def fake_post(url, data, timeout):
        calls.append(data["script"])
        return _FakeResp("##|M  42|83.82208333|-5.39111111|HII|4.00|##\n")

    monkeypatch.setattr(resolver.requests, "post", fake_post)
    cache = tmp_path / "target_cache.json"

    first = resolve_name("M 42", cache_path=cache)
    assert first is not None and first.name == "M  42"
    assert len(calls) == 1
    assert cache.is_file()

    # Same identifier with different casing/whitespace normalises to the same
    # cache key — Simbad must not be contacted a second time.
    second = resolve_name("m  42", cache_path=cache)
    assert second is not None and second.name == "M  42"
    assert len(calls) == 1


def test_resolve_name_returns_none_on_network_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(*a, **kw):
        raise requests.ConnectionError("no internet")
    monkeypatch.setattr(resolver.requests, "post", boom)
    assert resolve_name("M42", cache_path=tmp_path / "cache.json") is None


def test_resolve_name_returns_none_on_unknown_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        resolver.requests,
        "post",
        lambda *a, **kw: _FakeResp(
            "::error::\n[3] Identifier not found in the database : NOPE\n"
        ),
    )
    assert resolve_name("NOPE", cache_path=tmp_path / "cache.json") is None
