"""Select the correct sensor reference model from a telescope profile."""

from __future__ import annotations

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


def lookup_egain(sensor_name: str, gain_setting: int) -> float:
    return float(for_sensor(sensor_name).lookup_egain(gain_setting))


def lookup_read_noise(sensor_name: str, gain_setting: int) -> float:
    return float(for_sensor(sensor_name).lookup_read_noise(gain_setting))


def full_well_capacity(sensor_name: str, gain_setting: int) -> int:
    return int(for_sensor(sensor_name).full_well_capacity(gain_setting))
