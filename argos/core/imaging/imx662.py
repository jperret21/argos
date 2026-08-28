"""Sony IMX662 reference calibration for the Seestar S30 telephoto camera.

The S30 identifies its telephoto sensor as IMX662.  The fallback anchors below
are a digitised, conservative reference to ZWO's published ASI662MC camera
curve (0–600 gain units); they are *not* a replacement for a Seestar
photon-transfer calibration.  Driver ``ElectronsPerADU`` is preferred by the
capture path and a local ``~/.argos/camera_calibration_imx662.json`` overrides
these values point by point.
"""

from __future__ import annotations

from argos.core.imaging.sensor_reference import SensorReference

SENSOR_NAME = "IMX662"
PIXEL_SIZE_UM = 2.9
FULL_WELL_E = 38_200
HCG_THRESHOLD = 200

# Published ASI662MC performance references: full well 38.2 ke-, read noise
# 0.8–6.9 e-, HCG at gain 200.  Intermediate points deliberately remain coarse
# so they cannot be mistaken for an instrument-specific laboratory calibration.
REFERENCE = SensorReference(
    name=SENSOR_NAME,
    full_well_e=FULL_WELL_E,
    hcg_threshold=HCG_THRESHOLD,
    anchors=(
        (0, 6.0, 6.9),
        (100, 3.0, 3.2),
        (200, 1.0, 0.8),
        (300, 0.42, 0.8),
        (400, 0.18, 0.8),
        (500, 0.08, 0.8),
        (600, 0.04, 0.8),
    ),
)


def lookup_egain(gain_setting: int) -> float:
    return REFERENCE.lookup_egain(gain_setting)


def lookup_read_noise(gain_setting: int) -> float:
    return REFERENCE.lookup_read_noise(gain_setting)


def full_well_capacity(gain_setting: int) -> int:
    return REFERENCE.full_well_capacity(gain_setting)
