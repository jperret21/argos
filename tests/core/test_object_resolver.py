from __future__ import annotations

from pathlib import Path

import pytest

from argos.core.catalog import object_resolver
from argos.core.catalog.object_resolver import ObjectResolutionError, resolve_object

_SESAME_XML = """<?xml version='1.0'?>
<Sesame>
  <Target>
    <Resolver name='Simbad'>
      <oname>HD 189733</oname>
      <otype>Star</otype>
      <jradeg>300.18210000</jradeg>
      <jdedeg>22.70990000</jdedeg>
    </Resolver>
  </Target>
</Sesame>
"""


def test_resolve_object_parses_and_caches_response(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    class Response:
        text = _SESAME_XML

        def raise_for_status(self) -> None:
            pass

    def fake_get(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Response()

    monkeypatch.setattr(object_resolver.requests, "get", fake_get)
    cache = tmp_path / "resolver.json"

    first = resolve_object("HD 189733", cache_path=cache)
    second = resolve_object("  hd   189733 ", cache_path=cache)

    assert first.name == "HD 189733"
    assert first.ra_hours == pytest.approx(20.01214)
    assert first.dec_degrees == pytest.approx(22.7099)
    assert second == first
    assert calls == 1


def test_resolve_object_rejects_empty_query(tmp_path: Path) -> None:
    with pytest.raises(ObjectResolutionError, match="designation"):
        resolve_object("  ", cache_path=tmp_path / "resolver.json")
