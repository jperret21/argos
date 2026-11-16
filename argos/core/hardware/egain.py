"""The camera's e-/ADU at a gain setting, and where it comes from (S41, S42, S73).

One order for every consumer — the photometry's errors, the FITS ``EGAIN`` and the
re-run of saved frames:

1. ``camera.egain_table``, the observer's own calibration at that gain;
2. the telescope profile's photon-transfer measurement at that gain, or scaled from
   it along the sensor's gain curve (:meth:`TelescopeProfile.measured_gain`);
3. the camera driver's ``ElectronsPerADU``;
4. the sensor's reference curve, which no frame of this camera has confirmed.

The value is an :class:`Egain`, a ``float`` that also says where it came from and,
for a profile measurement (or one scaled from it), the read noise measured with it:
code that only wants the number keeps working unchanged.

Qt-free.
"""

from __future__ import annotations

import logging
import math

from argos.core.hardware import catalog
from argos.core.hardware.profile import TelescopeProfile

logger = logging.getLogger(__name__)

SOURCE_TABLE = "egain_table"
SOURCE_DRIVER = "driver"
SOURCE_HEADER = "header EGAIN"

#: Gain settings already warned about (one warning per process and gain).
_warned: set[tuple[str, int]] = set()


class Egain(float):
    """e-/ADU (a ``float``) with its ``source`` and, when measured with it, the read noise."""

    source: str
    read_noise_e: float | None

    def __new__(cls, value: float, source: str, read_noise_e: float | None = None) -> "Egain":
        obj = super().__new__(cls, float(value))
        obj.source = source
        obj.read_noise_e = read_noise_e
        return obj

    def __reduce__(self):  # pickling and copying keep the source
        return (Egain, (float(self), self.source, self.read_noise_e))


def positive(value) -> float | None:
    """``value`` as a plausible e-/ADU (0 < e <= 100), else None."""
    if isinstance(value, bool):
        return None
    try:
        egain = float(value)
    except (TypeError, ValueError):
        return None
    return egain if math.isfinite(egain) and 0 < egain <= 100 else None


def from_table(table, gain_setting) -> Egain | None:
    """The ``camera.egain_table`` entry at ``gain_setting``, or None."""
    if not isinstance(table, dict):
        return None
    try:
        key = str(int(gain_setting))
    except (TypeError, ValueError):
        return None
    value = positive(table.get(key))
    return Egain(value, SOURCE_TABLE) if value is not None else None


def from_profile(profile: TelescopeProfile | None, gain_setting) -> Egain | None:
    """The profile's photon-transfer e-/ADU at ``gain_setting`` (S73), or None.

    A value scaled from another gain carries the measured read noise too (the owner's
    decision: 2.6 e- rather than the 1.5 e- Settings default) and is logged once as
    "scaled, not measured" unless a measurement confirmed it (gain 100)."""
    if profile is None:
        return None
    found = profile.measured_gain(gain_setting)
    if found is None:
        return None
    m, scaled = found
    if scaled:
        _note_scaled(profile, m)
    return Egain(m.e_per_adu, m.method, m.read_noise_e)


def _note_scaled(profile: TelescopeProfile, m) -> None:
    key = (profile.key, int(m.gain))
    if m.gain in profile.gain_scaling_checked or key in _warned:
        return
    _warned.add(key)
    measured = ", ".join(str(g.gain) for g in profile.gain_measurements)
    logger.warning(
        "e-/ADU at gain %s scaled, not measured: %.4g, the %s's gain-%s photon transfer at"
        " %.2g dB per step (S73)",
        m.gain,
        m.e_per_adu,
        profile.name,
        measured,
        profile.gain_step_db,
    )


def from_reference(sensor: str, gain_setting: int) -> Egain:
    """The sensor reference curve (no frame of this camera confirms it)."""
    from argos.core.imaging import sensor_models

    model = sensor_models.for_sensor(sensor)
    source = f"{model.SENSOR_NAME} ref"
    if not sensor_models.is_known(sensor):
        source += " fallback"
    return Egain(sensor_models.lookup_egain(sensor, gain_setting), source)


def live(
    gain_setting: int,
    *,
    table=None,
    driver=None,
    profile: TelescopeProfile | None = None,
) -> Egain:
    """The e-/ADU of a frame taken now at ``gain_setting`` (the order above).

    ``driver``: the driver's value, or a callable that reads it (called only when
    the table and the profile have nothing). ``profile`` defaults to the active one.
    A value from the driver or the reference curve is logged once per gain as
    unverified when the profile has measurements (they cover other gains only).
    """
    if profile is None:
        from argos.core.hardware import active

        profile = active.profile()
    value = from_table(table, gain_setting) or from_profile(profile, gain_setting)
    if value is not None:
        return value
    if callable(driver):
        driver = driver()
    driven = positive(driver)
    value = (
        Egain(driven, SOURCE_DRIVER)
        if driven is not None
        else from_reference(profile.sensor, gain_setting)
    )
    _warn_unverified(profile, gain_setting, value)
    return value


def profile_of_header(header) -> TelescopeProfile | None:
    """The built-in profile a saved frame's ``TELESCOP`` names, or None."""
    name = str(header.get("TELESCOP", "") or "").strip()
    if not name:
        return None
    for p in catalog.PROFILES.values():
        if p.name == name:
            return p
    return None


def of_frame(header, table=None) -> Egain | None:
    """The e-/ADU of a saved frame (Open FITS, batch re-run), or None if unknown.

    The frame's own gain, never the Camera form's: the ``camera.egain_table`` entry
    at its ``GAIN``; then an ``EGAIN`` the observer's table wrote; then the
    photon-transfer measurement of the camera its ``TELESCOP`` names at that
    ``GAIN`` (S73: an S30 Pro frame at gain 80 says 0.8 or 1.723, the driver's or
    the reference curve's, where the camera measures 0.228); then its ``EGAIN``.
    None (the caller keeps its live chain) when nothing is usable.
    """
    gain = header.get("GAIN")
    if isinstance(gain, bool) or not isinstance(gain, (int, float)):
        gain = None
    elif not float(gain).is_integer():
        gain = None
    value = from_table(table, gain) if gain is not None else None
    if value is not None:
        return value
    written = positive(header.get("EGAIN"))
    comment = _comment(header, "EGAIN")
    if written is not None and SOURCE_TABLE in comment:
        return Egain(written, f"{SOURCE_HEADER} ({SOURCE_TABLE})")
    if gain is not None:
        value = from_profile(profile_of_header(header), gain)
        if value is not None:
            return value
    if written is not None:
        return Egain(written, SOURCE_HEADER)
    return None


def _comment(header, key: str) -> str:
    try:
        return str(header.comments[key] or "")
    except (AttributeError, KeyError, IndexError, TypeError):
        return ""


def _warn_unverified(profile: TelescopeProfile, gain_setting, value: Egain) -> None:
    if not profile.gain_measurements:
        return
    try:
        key = (profile.key, int(gain_setting))
    except (TypeError, ValueError):
        return
    if key in _warned:
        return
    _warned.add(key)
    measured = ", ".join(str(m.gain) for m in profile.gain_measurements)
    logger.warning(
        "e-/ADU at gain %s is the %s's %.4g, unverified: the %s is measured at gain %s"
        " only (photon transfer, S73)",
        gain_setting,
        value.source,
        float(value),
        profile.name,
        measured,
    )
