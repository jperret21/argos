"""Reference sensor models used when a Seestar driver omits EGAIN."""

from __future__ import annotations

import pytest

from argos.core.imaging import imx462, imx662, sensor_models


@pytest.mark.parametrize(
    "model",
    (imx662, imx462),
)
def test_reference_models_have_sane_electron_noise_ranges(model) -> None:
    gains = (0, model.HCG_THRESHOLD, 300, 600)
    assert all(model.lookup_egain(gain) > 0 for gain in gains)
    assert all(0.1 <= model.lookup_read_noise(gain) <= 10.0 for gain in gains)
    assert model.lookup_read_noise(model.HCG_THRESHOLD) <= model.lookup_read_noise(0)
    assert model.full_well_capacity(model.HCG_THRESHOLD) < model.FULL_WELL_E


@pytest.mark.parametrize(
    ("sensor", "model"),
    (("IMX662", imx662), ("imx462", imx462)),
)
def test_registry_selects_each_sensor_model(sensor, model) -> None:
    assert sensor_models.for_sensor(sensor) is model
    assert sensor_models.lookup_egain(sensor, 80) == model.lookup_egain(80)


def test_unknown_sensor_retains_legacy_imx585_fallback() -> None:
    assert sensor_models.is_known("unknown") is False
    assert sensor_models.for_sensor("unknown").SENSOR_NAME == "IMX585"
