"""Sony IMX462 reference calibration for the Seestar S50 telephoto camera.

The reference follows ZWO's published ASI462MC curve for the same sensor.  It
is only the fallback if the Seestar Alpaca driver exposes no electron gain;
``~/.argos/camera_calibration_imx462.json`` can hold a field PTC for exact
values on a specific telescope / firmware.
"""

from __future__ import annotations

from argos.core.imaging.sensor_reference import SensorReference

SENSOR_NAME = "IMX462"
PIXEL_SIZE_UM = 2.9
FULL_WELL_E = 11_200
HCG_THRESHOLD = 80

# Published ASI462MC performance references: full well 11.2 ke-, read noise
# 0.47–2.65 e-, with the HCG transition at gain 80.  As with IMX662, these are
# intentionally reference anchors, not an assertion about Seestar firmware.
REFERENCE = SensorReference(
    name=SENSOR_NAME,
    full_well_e=FULL_WELL_E,
    hcg_threshold=HCG_THRESHOLD,
    anchors=(
        (0, 2.7, 2.65),
        (80, 1.1, 0.47),
        (100, 0.85, 0.47),
        (200, 0.27, 0.47),
        (300, 0.09, 0.47),
        (400, 0.03, 0.47),
        (500, 0.01, 0.47),
        (600, 0.004, 0.47),
    ),
)


def lookup_egain(gain_setting: int) -> float:
    return REFERENCE.lookup_egain(gain_setting)


def lookup_read_noise(gain_setting: int) -> float:
    return REFERENCE.lookup_read_noise(gain_setting)


def full_well_capacity(gain_setting: int) -> int:
    return REFERENCE.full_well_capacity(gain_setting)
