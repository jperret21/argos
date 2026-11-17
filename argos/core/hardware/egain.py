"""The camera's e-/ADU at a gain setting, and where it comes from (S41, S42, S73).

One order for every consumer — the photometry's errors, the FITS ``EGAIN`` and the
re-run of saved frames:

1. ``camera.egain_table``, the observer's own calibration at that gain;
2. the observer's own photon-transfer file at that gain (``camera_calibration*.json``,
   Settings > Photon-transfer calibrations): a measurement of their own camera beats
   one made on another unit (S73, the owner's call of 2026-11-16; it was read with the
   reference curve, last);
3. the telescope profile's photon-transfer measurement at that gain, or scaled from
   it along the sensor's gain curve (:meth:`TelescopeProfile.measured_gain`);
4. the camera driver's ``ElectronsPerADU``;
5. the sensor's reference curve, which no frame of this camera has confirmed.

The value is an :class:`Egain`, a ``float`` that also says where it came from and,
for a measurement (the file's ``rdnoise``, the profile's, or one scaled from it), the
read noise measured with it: code that only wants the number keeps working unchanged.

Qt-free.
"""

from __future__ import annotations

import json
import logging
import math

from argos.core.hardware import catalog
from argos.core.hardware.profile import TelescopeProfile

logger = logging.getLogger(__name__)

SOURCE_TABLE = "egain_table"
SOURCE_DRIVER = "driver"
SOURCE_HEADER = "header EGAIN"
#: The observer's photon-transfer file, after the sensor's name ("IMX585 PTC file").
SOURCE_CALIBRATION = "PTC file"

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


def from_calibration(sensor: str, gain_setting) -> Egain | None:
    """The observer's own photon-transfer file's e-/ADU at exactly ``gain_setting``
    (S73), with its ``rdnoise`` there as the read noise measured with it, or None (no
    file, no entry at that gain, an unknown sensor, a value that is no e-/ADU).

    The file is the one Settings > Photon-transfer calibrations points to
    (``sensor_models.calibration_path``), JSON ``{"80": {"egain": 0.23, "rdnoise":
    2.6}}``. An entry without ``rdnoise`` takes the Settings read noise, as any e-/ADU
    without a measured one does; that is logged once with the e-/ADU."""
    found = _calibration_entry(sensor, gain_setting)
    if found is None:
        return None
    entry, key, label, path = found
    value = positive(entry.get("egain"))
    if value is None:
        return None
    read_noise = positive(entry.get("rdnoise"))
    _note_calibration(label, key, value, path, read_noise)
    return Egain(value, label, read_noise)


def calibration_read_noise(sensor: str, gain_setting) -> tuple[float, str] | None:
    """The observer's photon-transfer file's ``rdnoise`` at exactly ``gain_setting``, with
    its source ("IMX585 PTC file"), or None: what a frame's ``RDNOISE`` names when its
    e-/ADU carries no read noise of its own (a gain table's, the driver's)."""
    found = _calibration_entry(sensor, gain_setting)
    if found is None:
        return None
    entry, _key, label, _path = found
    read_noise = positive(entry.get("rdnoise"))
    return (read_noise, label) if read_noise is not None else None


def _calibration_entry(sensor: str, gain_setting):
    """``(entry, gain key, source label, path)`` of the observer's photon-transfer file at
    exactly ``gain_setting``, or None (no file, no such entry, an unknown sensor)."""
    from argos.core.imaging import sensor_models

    path = sensor_models.calibration_path(sensor)
    if path is None:
        return None
    try:
        key = str(int(gain_setting))
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    entry = data.get(key) if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        return None
    label = f"{sensor_models.for_sensor(sensor).SENSOR_NAME} {SOURCE_CALIBRATION}"
    return entry, key, label, path


def _note_calibration(label: str, key: str, value: float, path, read_noise) -> None:
    noted = (label, int(key))
    if noted in _warned:
        return
    _warned.add(noted)
    logger.info(
        "e-/ADU at gain %s from your photon-transfer file %s: %.4g, read noise %s (S73:"
        " before the telescope profile's measurement and the driver)",
        key,
        path.name,
        value,
        f"{read_noise:.3g} e-" if read_noise is not None else "not in the file: the Settings one",
    )


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
    value = (
        from_table(table, gain_setting)
        or from_calibration(profile.sensor, gain_setting)
        or from_profile(profile, gain_setting)
    )
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
    at its ``GAIN``; then an ``EGAIN`` the observer's table wrote; then, for the
    camera its ``TELESCOP`` names, the observer's photon-transfer file at that
    ``GAIN``, an ``EGAIN`` such a file wrote (with the ``RDNOISE`` it wrote), and the
    profile's photon-transfer
    measurement (S73: an S30 Pro frame at gain 80 says 0.8 or 1.723, the driver's or
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
    profile = profile_of_header(header)
    if gain is not None and profile is not None:
        value = from_calibration(profile.sensor, gain)
        if value is not None:
            return value
    if written is not None and SOURCE_CALIBRATION in comment:
        # with the read noise that file gave with it, when the frame's RDNOISE names it
        read_noise = (
            positive(header.get("RDNOISE"))
            if SOURCE_CALIBRATION in _comment(header, "RDNOISE")
            else None
        )
        return Egain(written, f"{SOURCE_HEADER} ({SOURCE_CALIBRATION})", read_noise)
    if gain is not None:
        value = from_profile(profile, gain)
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
