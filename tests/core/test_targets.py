"""Tests for the persistent target set (Qt-free, no hardware)."""

from __future__ import annotations

from argos.core.catalog.targets import (
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    TargetStar,
)


def _star(role=ROLE_TARGET, auid="000-BBB-001", ra=83.6, dec=22.0, name="NU Ori"):
    return TargetStar(role=role, ra_deg=ra, dec_deg=dec, auid=auid, name=name, source="vsx")


def test_set_role_adds_then_updates_by_identity() -> None:
    ts = TargetSet(object_name="M42")
    ts.set_role(_star(role=ROLE_TARGET))
    assert len(ts.stars) == 1
    # Same AUID → update in place (role change), not a duplicate.
    ts.set_role(_star(role=ROLE_COMPARISON))
    assert len(ts.stars) == 1
    assert ts.stars[0].role == ROLE_COMPARISON


def test_key_falls_back_to_position_without_auid() -> None:
    a = TargetStar(role=ROLE_TARGET, ra_deg=10.0, dec_deg=-5.0)
    b = TargetStar(role=ROLE_TARGET, ra_deg=10.0, dec_deg=-5.0)
    assert a.key() == b.key()  # same position → same identity
    assert a.key() != _star().key()


def test_by_role_and_remove() -> None:
    ts = TargetSet()
    ts.set_role(_star(auid="A", role=ROLE_TARGET))
    ts.set_role(_star(auid="B", role=ROLE_COMPARISON, name="comp"))
    assert len(ts.by_role(ROLE_TARGET)) == 1
    assert len(ts.by_role(ROLE_COMPARISON)) == 1
    ts.remove("auid:A")
    assert [s.auid for s in ts.stars] == ["B"]


def test_json_round_trip(tmp_path) -> None:
    ts = TargetSet(object_name="M42")
    ts.set_role(_star(role=ROLE_TARGET))
    ts.set_role(_star(auid="C", role=ROLE_COMPARISON, name="HD 37041"))
    path = tmp_path / "sub" / "targets.json"
    ts.save(path)  # creates parent dirs, atomic write
    back = TargetSet.load(path)
    assert back.object_name == "M42"
    assert {s.auid for s in back.stars} == {"000-BBB-001", "C"}
    assert back.by_role(ROLE_TARGET)[0].name == "NU Ori"


def test_load_missing_returns_empty(tmp_path) -> None:
    assert TargetSet.load(tmp_path / "nope.json").stars == []


def test_from_dict_ignores_unknown_keys() -> None:
    ts = TargetSet.from_dict(
        {"object": "X", "stars": [{"role": "target", "ra_deg": 1.0, "dec_deg": 2.0, "future": 9}]}
    )
    assert ts.stars[0].ra_deg == 1.0  # unknown 'future' key dropped, no crash


def test_display_name_prefers_name_then_auid() -> None:
    assert _star(name="NU Ori").display_name == "NU Ori"
    assert TargetStar(role="check", ra_deg=1, dec_deg=2, auid="Z").display_name == "Z"
