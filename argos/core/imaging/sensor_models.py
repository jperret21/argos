"""Select the correct sensor reference model from a telescope profile."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from argos.core.imaging import imx462, imx585, imx662

_MODELS: dict[str, ModuleType] = {
    imx585.SENSOR_NAME: imx585,
    imx662.SENSOR_NAME: imx662,
    imx462.SENSOR_NAME: imx462,
}


def for_sensor(sensor_name: str) -> ModuleType:
    """Return a reference model, retaining IMX585 only for unknown legacy gear."""
    return _MODELS.get((sensor_name or "").upper(), imx585)


def is_known(sensor_name: str) -> bool:
    return (sensor_name or "").upper() in _MODELS


def calibration_path(sensor_name: str) -> Path | None:
    """The observer's photon-transfer file of a known sensor (Settings > Photon-transfer
    calibrations: ``camera_calibration.json`` for the IMX585, else
    ``camera_calibration_<sensor>.json``), None for an unknown sensor (S73)."""
    if not is_known(sensor_name):
        return None
    model = for_sensor(sensor_name)
    reference = getattr(model, "REFERENCE", None)
    return reference.calibration_path if reference is not None else model.calibration_path()


def lookup_egain(sensor_name: str, gain_setting: int) -> float:
    return float(for_sensor(sensor_name).lookup_egain(gain_setting))


def lookup_read_noise(sensor_name: str, gain_setting: int) -> float:
    return float(for_sensor(sensor_name).lookup_read_noise(gain_setting))


def full_well_capacity(sensor_name: str, gain_setting: int) -> int:
    return int(for_sensor(sensor_name).full_well_capacity(gain_setting))
