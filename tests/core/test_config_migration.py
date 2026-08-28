"""Tests for the config migration onto telescope profiles (Qt-free, no hardware).

``camera.adc_bits`` / ``full_well_adu`` / ``linearity_max_adu`` moved onto the
telescope profile. An observer who tuned those for their own unit must keep
that tuning across the upgrade — silently reverting a saturation threshold
would change what photometry flags as saturated, without telling anyone.
"""

from __future__ import annotations

from argos.core.config import (
    _DEFAULTS,
    _migrate_alpaca_profiles,
    _migrate_camera_keys,
    _migrate_legacy_site,
)


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


def test_legacy_observer_coordinates_migrate_when_no_site_exists():
    data = {"observer": {"latitude": 46.2, "longitude": 6.1, "elevation": 430.0}}
    _migrate_legacy_site(data, on_disk={"observer": data["observer"]})
    assert data["site"] == {"latitude": 46.2, "longitude": 6.1, "elevation": 430.0}


def test_explicit_site_is_never_overwritten_by_legacy_observer_values():
    data = {
        "observer": {"latitude": 46.2, "longitude": 6.1, "elevation": 430.0},
        "site": {"latitude": 0.0, "longitude": 0.0, "elevation": 0.0},
    }
    _migrate_legacy_site(data, on_disk={"site": data["site"]})
    assert data["site"]["latitude"] == 0.0


def test_active_legacy_alpaca_profile_becomes_the_single_endpoint():
    old = {
        "alpaca": {
            "profile": "field_ap",
            "profiles": {
                "home": {"host": "192.168.1.42", "port": 32323},
                "field_ap": {"host": "10.0.0.1", "port": 41234},
            },
        }
    }
    data = {"alpaca": {"host": "", "port": 32323, **old["alpaca"]}}

    _migrate_alpaca_profiles(data, old)

    assert data["alpaca"] == {"host": "10.0.0.1", "port": 41234}
