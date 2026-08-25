"""The active telescope profile for this process.

One module-level profile, resolved from config at startup and readable from
anywhere::

    from argos.core.hardware import active
    scale = active.profile().arcsec_per_full_px

**Call it, don't bind it.** Every consumer reads through :func:`profile` at the
point of use rather than copying the value into a module constant at import
time. The theme layer does bind at import, which is why ``main.py`` carries a
comment about applying the palette before any widget is constructed — a real
ordering constraint that is easy to break. Nothing here has that hazard: a
profile change is visible to the next call, wherever it comes from.

User overrides ride on top of the built-in profile, so a corrected saturation
threshold survives an Argos upgrade that revises the shipped defaults.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from argos.core.hardware import catalog
from argos.core.hardware.profile import TelescopeProfile

logger = logging.getLogger(__name__)

#: Config keys.
CFG_PROFILE = "hardware.profile"
CFG_OVERRIDES = "hardware.overrides"

#: Fields a user may override. Deliberately narrow: these are the values a
#: careful observer can measure themselves (saturation, linearity, ADC depth)
#: or must correct for a variant. Optics and CFA layout are not in the list —
#: if those are wrong, the profile is wrong and needs fixing at the source.
OVERRIDABLE = frozenset(
    {
        "adc_bits",
        "full_well_adu",
        "linearity_max_adu",
        "alpaca_port",
        "ap_host",
    }
)

_active: TelescopeProfile = catalog.DEFAULT_PROFILE


def profile() -> TelescopeProfile:
    """The profile in force right now."""
    return _active


def set_profile(new: TelescopeProfile) -> None:
    """Make *new* the active profile."""
    global _active
    _active = new
    logger.info("Telescope profile: %s", new.describe())
    if not new.validated:
        for caveat in new.caveats:
            logger.warning("Profile %s is unvalidated — %s", new.key, caveat)


def apply_overrides(base: TelescopeProfile, overrides: dict[str, Any]) -> TelescopeProfile:
    """Return *base* with the whitelisted entries of *overrides* applied.

    Unknown or non-overridable keys are logged and skipped rather than raising:
    a hand-edited config should never stop the application from starting.
    """
    if not isinstance(overrides, dict):
        if overrides:
            logger.warning("Ignoring hardware overrides — expected a mapping, got %r", overrides)
        return base

    accepted: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in OVERRIDABLE:
            logger.warning("Ignoring hardware override %r — not an overridable field", key)
            continue
        accepted[key] = value
    if not accepted:
        return base
    try:
        return dataclasses.replace(base, **accepted)
    except (TypeError, ValueError) as exc:
        logger.warning("Ignoring hardware overrides %r — %s", accepted, exc)
        return base


def load_from_config(config) -> TelescopeProfile:
    """Resolve the profile named in *config*, apply overrides, make it active.

    An unknown key falls back to the reference profile with a warning: landing
    on a working telescope beats refusing to start over a typo.
    """
    key = config.get(CFG_PROFILE, catalog.DEFAULT_PROFILE.key)
    base = catalog.get(key)
    if base is None:
        logger.warning(
            "Unknown telescope profile %r — falling back to %s",
            key,
            catalog.DEFAULT_PROFILE.key,
        )
        base = catalog.DEFAULT_PROFILE

    resolved = apply_overrides(base, config.get(CFG_OVERRIDES, {}) or {})
    set_profile(resolved)
    return resolved
