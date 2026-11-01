"""Telescope profiles as JSON records (row A17).

Wraps ``argos.core.hardware``: the built-in catalogue (``catalog.py:99-112``),
the frozen :class:`TelescopeProfile` with its derived quantities
(``profile.py:91-121``: focal ratio, plate scale and field of view are
computed, never stored) and the active-profile registry with the user's
overrides (``active.py:56-110``). The change guard of the Qt Connection page
(``connection_page.py:237-258``: refused while equipment is connected) is
enforced by the hub, which knows the device states.
"""

from __future__ import annotations

from typing import Any

from argos.core.hardware import active, catalog
from argos.core.hardware.profile import TelescopeProfile


def summary(profile: TelescopeProfile) -> dict[str, Any]:
    """The ``profile`` field of the status record."""
    return {"key": profile.key, "name": profile.name, "validated": profile.validated}


def record(profile: TelescopeProfile, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """One ``Profile`` record; *overrides* lists what was applied (active profile)."""
    fov_w, fov_h = profile.fov_deg
    return {
        "key": profile.key,
        "name": profile.name,
        "validated": profile.validated,
        "caveats": list(profile.caveats),
        "aperture_mm": profile.aperture_mm,
        "focal_length_mm": profile.focal_length_mm,
        "focal_ratio": profile.focal_ratio,
        "sensor": profile.sensor,
        "pixel_size_um": profile.pixel_size_um,
        "sensor_px": [profile.sensor_width_px, profile.sensor_height_px],
        "bayer": profile.bayer_pattern,
        "arcsec_per_px": profile.arcsec_per_full_px,
        "fov_deg": [fov_w, fov_h],
        "adc_bits": profile.adc_bits,
        "full_well_adu": profile.full_well_adu,
        "linearity_max_adu": profile.linearity_max_adu,
        "filter_names": list(profile.filter_names),
        "ap_host": profile.ap_host,
        "overrides": dict(overrides or {}),
    }


def applied_overrides(raw: Any) -> dict[str, Any]:
    """The entries of ``hardware.overrides`` that ``apply_overrides`` honours."""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in active.OVERRIDABLE and v is not None}


def profiles_state(locked_reason: str | None, raw_overrides: Any) -> dict[str, Any]:
    """``GET /api/profiles``."""
    current = active.profile()
    overrides = applied_overrides(raw_overrides)
    profiles = []
    for base in catalog.PROFILES.values():
        if base.key == current.key:
            profiles.append(record(current, overrides))
        else:
            profiles.append(record(base))
    return {
        "active": current.key,
        "locked": locked_reason is not None,
        "locked_reason": locked_reason,
        "profiles": profiles,
    }
