"""Tests for the config migration onto telescope profiles (Qt-free, no hardware).

``camera.adc_bits`` / ``full_well_adu`` / ``linearity_max_adu`` moved onto the
telescope profile. An observer who tuned those for their own unit must keep
that tuning across the upgrade — silently reverting a saturation threshold
would change what photometry flags as saturated, without telling anyone.
"""

from __future__ import annotations

import json

from argos.core import config as config_module
from argos.core.config import (
    _DEFAULTS,
    _migrate_alpaca_profiles,
    _migrate_camera_keys,
    _migrate_catalogue_display_limit,
    _migrate_diagnostics_opt_in,
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


def test_legacy_enabled_diagnostics_become_opt_in():
    """The old default was true, not an affirmative privacy choice."""
    data = {"diagnostics": {"enabled": True}}
    _migrate_diagnostics_opt_in(data, on_disk={"diagnostics": {"enabled": True}})
    assert data["diagnostics"]["enabled"] is False


def test_explicit_local_diagnostics_choice_is_preserved():
    data = {"diagnostics": {"enabled": True}}
    saved = {"diagnostics": {"enabled": True, "local_opt_in_v1": True}}
    _migrate_diagnostics_opt_in(data, on_disk=saved)
    assert data["diagnostics"]["enabled"] is True


def test_config_load_disables_legacy_diagnostics_without_opt_in():
    config_module._CONFIG_DIR.mkdir(parents=True)
    config_module._CONFIG_FILE.write_text(
        json.dumps({"diagnostics": {"enabled": True}}), encoding="utf-8"
    )
    loaded = config_module.Config.load()
    assert loaded.get("diagnostics.enabled") is False


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


def test_shallow_legacy_catalogue_display_limit_moves_to_gaia_g18():
    data = {"catalog": {"display_mag_limit": 14.0}}
    _migrate_catalogue_display_limit(data, on_disk={"catalog": {"display_mag_limit": 14.0}})
    assert data["catalog"]["display_mag_limit"] == 18.0
    assert data["catalog"]["display_limit_version"] == 2


def test_versioned_catalogue_display_choice_is_preserved():
    data = {"catalog": {"display_mag_limit": 12.0, "display_limit_version": 2}}
    _migrate_catalogue_display_limit(data, on_disk={"catalog": dict(data["catalog"])})
    assert data["catalog"]["display_mag_limit"] == 12.0
