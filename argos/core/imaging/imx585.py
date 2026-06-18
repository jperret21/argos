"""Sony IMX585 calibration constants for the Seestar S30 Pro telephoto camera.

Provides EGAIN (e-/ADU) and read-noise lookups as a function of the gain
setting reported by the Alpaca driver (0–600 on the Seestar S30 Pro).

When the Alpaca driver exposes ``ElectronsPerADU`` directly we prefer that
value; this module is the fallback so every FITS frame still carries a
sensible ``EGAIN`` header for the post-processing pipeline.

Anchor values are interpolated from the public ZWO ASI585MC characterisation
(same sensor): EGAIN in log-space, read noise linearly. The Seestar may apply
a small global offset depending on firmware, but the *shape* of the curve is
sensor-intrinsic.

If the user has produced a personal calibration (photon-transfer-curve via
``Tools → Calibrate Camera…``), :func:`lookup_egain` will prefer that JSON
file at ``~/.argos/camera_calibration.json``.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Sensor-intrinsic constants (datasheet)
FULL_WELL_E      = 38_000     # electrons at saturation (low-gain mode)
HCG_THRESHOLD    = 252        # gain setting at which HCG mode engages
PIXEL_SIZE_UM    = 2.9
SENSOR_NAME      = "IMX585"


# Reference points: (gain_setting, EGAIN [e-/ADU], read_noise [e-]).
# Derived from ZWO ASI585MC published characterisation; piecewise log-linear
# fit between anchors. Validated against forum bias-frame measurements.
_ANCHORS: list[tuple[int, float, float]] = [
    (0,   3.00, 3.60),
    (100, 1.50, 2.60),
    (252, 0.55, 1.05),   # HCG mode kicks in
    (300, 0.40, 0.95),
    (400, 0.18, 0.92),
    (500, 0.07, 0.90),
    (600, 0.04, 0.90),
]


_USER_CALIB_PATH = Path.home() / ".argos" / "camera_calibration.json"


def lookup_egain(gain_setting: int) -> float:
    """Return e-/ADU for the given gain setting (0–600).

    Prefers the user calibration file when available, otherwise interpolates
    between the built-in IMX585 anchor points. Values outside [0, 600] are
    clamped to the nearest endpoint — no extrapolation off the curve.
    """
    g = _clamp_gain(gain_setting)
    user_value = _load_user_calibration(g, "egain")
    if user_value is not None:
        return user_value
    return _interpolate_log(g, index=1)


def lookup_read_noise(gain_setting: int) -> float:
    """Return read noise in electrons for the given gain setting (0–600)."""
    g = _clamp_gain(gain_setting)
    user_value = _load_user_calibration(g, "rdnoise")
    if user_value is not None:
        return user_value
    return _interpolate_linear(g, index=2)


def full_well_capacity(gain_setting: int) -> int:
    """Return effective full-well capacity in electrons.

    Drops sharply once HCG mode engages — the on-sensor amplifier trades
    dynamic range for read noise.
    """
    if gain_setting < HCG_THRESHOLD:
        return FULL_WELL_E
    # HCG roughly quarters the well
    return int(FULL_WELL_E * 0.25)


# --------------------------------------------------------------------------- #
# Internals                                                                    #
# --------------------------------------------------------------------------- #

def _clamp_gain(g: int) -> int:
    return max(_ANCHORS[0][0], min(_ANCHORS[-1][0], int(g)))


def _bracket(g: int) -> tuple[tuple[int, float, float], tuple[int, float, float]]:
    """Return the two anchor points bracketing ``g``."""
    g = _clamp_gain(g)
    for i in range(len(_ANCHORS) - 1):
        lo, hi = _ANCHORS[i], _ANCHORS[i + 1]
        if lo[0] <= g <= hi[0]:
            return lo, hi
    return _ANCHORS[-2], _ANCHORS[-1]


def _interpolate_log(g: int, index: int) -> float:
    """Interpolate column ``index`` of the anchor table in log-space."""
    lo, hi = _bracket(g)
    if lo[0] == hi[0]:
        return lo[index]
    t = (g - lo[0]) / (hi[0] - lo[0])
    log_value = math.log(lo[index]) + t * (math.log(hi[index]) - math.log(lo[index]))
    return round(math.exp(log_value), 4)


def _interpolate_linear(g: int, index: int) -> float:
    lo, hi = _bracket(g)
    if lo[0] == hi[0]:
        return lo[index]
    t = (g - lo[0]) / (hi[0] - lo[0])
    return round(lo[index] + t * (hi[index] - lo[index]), 3)


def _load_user_calibration(gain_setting: int, key: str) -> Optional[float]:
    """Return a user-calibrated value for ``gain_setting`` if available.

    Expected JSON structure::

        {
          "100": {"egain": 1.42, "rdnoise": 2.7},
          "252": {"egain": 0.52, "rdnoise": 1.05}
        }
    """
    if not _USER_CALIB_PATH.is_file():
        return None
    try:
        data = json.loads(_USER_CALIB_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read user calibration %s: %s", _USER_CALIB_PATH, exc)
        return None

    entry = data.get(str(gain_setting))
    if entry is None:
        return None
    value = entry.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
