"""Tests for the config migration onto telescope profiles (Qt-free, no hardware).

``camera.adc_bits`` / ``full_well_adu`` / ``linearity_max_adu`` moved onto the
telescope profile. An observer who tuned those for their own unit must keep
that tuning across the upgrade — silently reverting a saturation threshold
would change what photometry flags as saturated, without telling anyone.
"""

from __future__ import annotations

from argos.core.config import _DEFAULTS, _migrate_camera_keys


def _fresh(**camera):
    """A config dict as it comes off disk, with the given camera overrides."""
    return {
        "camera": {**_DEFAULTS["camera"], **camera},
        "hardware": {"profile": "s30pro", "overrides": {}},
    }


def test_tuned_values_move_to_overrides():
    data = _fresh(linearity_max_adu=44000, full_well_adu=58000)
    _migrate_camera_keys(data)
    assert data["hardware"]["overrides"] == {
        "linearity_max_adu": 44000,
        "full_well_adu": 58000,
    }


def test_untouched_config_gains_no_overrides():
    """A user who never tuned anything should not acquire override entries."""
    data = _fresh()
    _migrate_camera_keys(data)
    assert data["hardware"]["overrides"] == {}


def test_legacy_keys_are_left_in_place():
    """An older Argos reading the same file must still find what it expects."""
    data = _fresh(adc_bits=14)
    _migrate_camera_keys(data)
    assert data["camera"]["adc_bits"] == 14


def test_existing_overrides_are_never_overwritten():
    """The migration runs once; a later hand edit wins over a stale legacy key."""
    data = _fresh(linearity_max_adu=44000)
    data["hardware"]["overrides"] = {"linearity_max_adu": 47000}
    _migrate_camera_keys(data)
    assert data["hardware"]["overrides"] == {"linearity_max_adu": 47000}


def test_missing_sections_do_not_raise():
    """Configs from older versions have no hardware section at all."""
    data = {}
    _migrate_camera_keys(data)
    assert data["hardware"]["overrides"] == {}
