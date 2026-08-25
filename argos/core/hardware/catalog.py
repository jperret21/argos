"""The built-in telescope profiles — data, not logic.

Adding a model means adding an entry here and nothing else. Every number is
either measured on the instrument or taken from the manufacturer's published
specification; anything neither measured nor published belongs in ``caveats``,
not in a plausible-looking field.

Only the **S30 Pro** is validated: it is the model Argos was built against and
every one of its values is confirmed by the code it replaces. The S30 and S50
entries carry published optics and sensor geometry — the plate scales they
imply match the manufacturer's own field-of-view figures, which is a real
cross-check — but their CFA layout and gain behaviour have never been seen by
this code. They are marked accordingly and must not be trusted for photometry
until someone runs them on hardware.

The **S50 Pro** is deliberately absent. Its optics are published (50 mm,
260 mm, f/5.2) but its sensor is described only as "1/1.2-inch 4K", and
without a confirmed pixel pitch there is no plate scale — the one number the
whole astrometry path depends on. A profile that cannot be filled honestly is
worse than a missing one, so it lands when the specification does.
"""

from __future__ import annotations

from argos.core.hardware.profile import TelescopeProfile

#: Fields that no unvalidated profile has confirmed. The CFA layout matters
#: most: a wrong Bayer pattern does not fail loudly, it quietly measures the
#: wrong photosites and poisons every magnitude derived from them.
_UNSEEN = (
    "Bayer pattern assumed GRBG — confirm before trusting photometry",
    "gain range and EGAIN curve not characterised",
    "ADC depth and saturation thresholds inherited from the S30 Pro",
)


S30_PRO = TelescopeProfile(
    key="s30pro",
    name="ZWO Seestar S30 Pro",
    validated=True,
    aperture_mm=30.0,
    focal_length_mm=160.0,
    sensor="IMX585",
    pixel_size_um=2.9,
    sensor_width_px=3840,
    sensor_height_px=2160,
    bayer_pattern="GRBG",
    adc_bits=12,
    full_well_adu=60000,
    linearity_max_adu=50000,
    filter_names=("Dark", "IR", "LP"),
    ap_host="10.0.0.1",
)

S30 = TelescopeProfile(
    key="s30",
    name="ZWO Seestar S30",
    validated=False,
    caveats=_UNSEEN,
    aperture_mm=30.0,
    focal_length_mm=150.0,
    sensor="IMX662",
    pixel_size_um=2.9,
    sensor_width_px=1920,
    sensor_height_px=1080,
    bayer_pattern="GRBG",
    adc_bits=12,
    full_well_adu=60000,
    linearity_max_adu=50000,
    filter_names=("Dark", "IR", "LP"),
    ap_host="10.0.0.1",
)

S50 = TelescopeProfile(
    key="s50",
    name="ZWO Seestar S50",
    validated=False,
    caveats=_UNSEEN,
    aperture_mm=50.0,
    focal_length_mm=250.0,
    sensor="IMX462",
    pixel_size_um=2.9,
    sensor_width_px=1920,
    sensor_height_px=1080,
    bayer_pattern="GRBG",
    adc_bits=12,
    full_well_adu=60000,
    linearity_max_adu=50000,
    filter_names=("Dark", "IR", "LP"),
    ap_host="10.0.0.1",
)


#: Ordered registry, keyed by :attr:`TelescopeProfile.key`. The reference model
#: comes first so pickers default to the one that is actually validated.
PROFILES: dict[str, TelescopeProfile] = {p.key: p for p in (S30_PRO, S30, S50)}

#: Used whenever config names a profile that does not exist.
DEFAULT_PROFILE = S30_PRO


def get(key: str) -> TelescopeProfile | None:
    """Return the profile registered under *key*, or ``None``."""
    return PROFILES.get(key)


def keys() -> tuple[str, ...]:
    """Registered profile keys, in display order."""
    return tuple(PROFILES)
