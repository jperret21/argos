"""Profile dataclass + JSON merge."""

from __future__ import annotations

import json
from pathlib import Path

from seercontrol.core.profiles import (
    Profile,
    builtin_profiles,
    find_profile,
    load_profiles,
)


def test_builtin_profiles_cover_photometry_use_cases() -> None:
    names = {p.name for p in builtin_profiles()}
    # Reflect the use cases the wizard advertises.
    assert any("CV" in n for n in names)
    assert any("LPV" in n for n in names)
    assert any("transit" in n.lower() for n in names)
    assert any("deep" in n.lower() for n in names)


def test_profile_duration_and_size_estimates_are_finite() -> None:
    for p in builtin_profiles():
        assert p.total_duration_s > 0
        assert p.estimated_size_mb > 0


def test_user_profiles_override_builtins_by_name(tmp_path: Path) -> None:
    builtin = builtin_profiles()[0]
    override = {
        "name": builtin.name,
        "description": "User-tweaked variant",
        "frame_type": "Light Frame",
        "exposure_s": 999.0,
        "gain": 42,
        "filter_name": "Ha",
        "frames": 1,
        "continuous": False,
    }
    user_file = tmp_path / "profiles.json"
    user_file.write_text(json.dumps([override]))

    profiles = load_profiles(user_path=user_file)
    overridden = next(p for p in profiles if p.name == builtin.name)
    assert overridden.exposure_s == 999.0
    assert overridden.gain == 42


def test_user_profiles_can_add_new_entries(tmp_path: Path) -> None:
    user_file = tmp_path / "profiles.json"
    user_file.write_text(json.dumps([{
        "name": "Custom — narrowband",
        "description": "user-only",
        "frame_type": "Light Frame",
        "exposure_s": 300.0,
        "gain": 100,
        "filter_name": "Ha",
        "frames": 12,
    }]))
    profiles = load_profiles(user_path=user_file)
    assert find_profile("Custom — narrowband", profiles) is not None


def test_load_profiles_ignores_malformed_file(tmp_path: Path) -> None:
    bad = tmp_path / "profiles.json"
    bad.write_text("{not json}")
    # Should still return at least the built-ins.
    assert len(load_profiles(user_path=bad)) >= 4


def test_profile_roundtrips_through_to_dict_from_dict() -> None:
    original = builtin_profiles()[1]
    reborn = Profile.from_dict(original.to_dict())
    assert reborn == original
