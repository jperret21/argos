"""Tests for telescope profiles (Qt-free, no hardware).

Two things are worth pinning here. First, the derived quantities: the whole
package exists because a focal ratio was hard-coded as ``FOCALLEN / 50.0`` and
reported f/3.2 for an f/5.3 telescope, so the arithmetic that replaces it is
tested against the instrument's published figures. Second, the honesty rules:
an unvalidated profile must say so, and a bad config must not stop Argos from
starting.
"""

from __future__ import annotations

import pytest

from argos.core.hardware import active, catalog
from argos.core.hardware.profile import TelescopeProfile


@pytest.fixture(autouse=True)
def _restore_active_profile():
    """The active profile is process-wide state — put it back after each test."""
    before = active.profile()
    yield
    active.set_profile(before)


# --------------------------------------------------------------------------- #
# Derived quantities                                                           #
# --------------------------------------------------------------------------- #


def test_s30_pro_focal_ratio_is_f5_3_not_f3_2():
    """The bug this package exists to kill: 160/50 = 3.2, but the S30 Pro is f/5.3."""
    assert catalog.S30_PRO.focal_ratio == pytest.approx(5.33, abs=0.01)


def test_s30_pro_plate_scale_matches_the_documented_value():
    """206.265 × 2.9 / 160 ≈ 3.74″/px — the constant metrics.py used to hard-code."""
    assert catalog.S30_PRO.arcsec_per_full_px == pytest.approx(3.74, abs=0.01)


def test_green_plane_scale_is_twice_the_full_res_scale():
    """One green sample per 2×2 CFA tile, so a green pixel spans twice the sky."""
    p = catalog.S30_PRO
    assert p.arcsec_per_green_px == pytest.approx(2 * p.arcsec_per_full_px)


@pytest.mark.parametrize(
    "profile,width_deg,height_deg",
    [
        # Cross-check against the manufacturer's published fields of view:
        # the S30 Pro is quoted at 3.98° × 2.26°, the S50 at 1.3° × 0.7°.
        (catalog.S30_PRO, 3.99, 2.24),
        (catalog.S50, 1.28, 0.72),
    ],
)
def test_field_of_view_matches_published_figures(profile, width_deg, height_deg):
    w, h = profile.fov_deg
    assert w == pytest.approx(width_deg, abs=0.02)
    assert h == pytest.approx(height_deg, abs=0.02)


def test_focal_ratio_without_an_aperture_raises():
    """Better a loud failure than silently reproducing the f/3.2 bug."""
    bare = TelescopeProfile(key="x", name="X", validated=False, focal_length_mm=160.0)
    with pytest.raises(ValueError, match="aperture"):
        _ = bare.focal_ratio


# --------------------------------------------------------------------------- #
# The registry                                                                 #
# --------------------------------------------------------------------------- #


def test_only_the_reference_profile_is_marked_validated():
    validated = [p.key for p in catalog.PROFILES.values() if p.validated]
    assert validated == ["s30pro"]


def test_every_unvalidated_profile_names_its_caveats():
    """An unvalidated profile that claims nothing is worse than no profile."""
    for p in catalog.PROFILES.values():
        if not p.validated:
            assert p.caveats, f"{p.key} is unvalidated but lists no caveats"


def test_s50_pro_is_absent_until_its_sensor_is_confirmed():
    """No pixel pitch means no plate scale — the astrometry path needs one."""
    assert catalog.get("s50pro") is None


def test_the_reference_profile_leads_the_registry():
    assert catalog.keys()[0] == "s30pro"


# --------------------------------------------------------------------------- #
# Resolution from config                                                       #
# --------------------------------------------------------------------------- #


class _FakeConfig:
    def __init__(self, values: dict):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def test_load_from_config_selects_the_named_profile():
    cfg = _FakeConfig({active.CFG_PROFILE: "s50"})
    assert active.load_from_config(cfg).key == "s50"
    assert active.profile().key == "s50"


def test_unknown_profile_falls_back_to_the_reference():
    """A typo in config must not stop Argos from starting."""
    cfg = _FakeConfig({active.CFG_PROFILE: "s99-imaginary"})
    assert active.load_from_config(cfg).key == "s30pro"


def test_overrides_are_applied_on_top_of_the_profile():
    cfg = _FakeConfig(
        {active.CFG_PROFILE: "s30pro", active.CFG_OVERRIDES: {"linearity_max_adu": 44000}}
    )
    resolved = active.load_from_config(cfg)
    assert resolved.linearity_max_adu == 44000
    assert resolved.focal_length_mm == 160.0  # untouched
    assert catalog.S30_PRO.linearity_max_adu == 50000  # the registry is frozen


def test_non_overridable_fields_are_refused():
    """Optics are not user-tunable — a wrong focal length is a profile bug."""
    cfg = _FakeConfig(
        {active.CFG_PROFILE: "s30pro", active.CFG_OVERRIDES: {"focal_length_mm": 999.0}}
    )
    assert active.load_from_config(cfg).focal_length_mm == 160.0


def test_garbage_override_value_does_not_stop_startup():
    cfg = _FakeConfig({active.CFG_PROFILE: "s30pro", active.CFG_OVERRIDES: "not-a-dict"})
    assert active.load_from_config(cfg).key == "s30pro"
