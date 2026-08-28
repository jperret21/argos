"""Reusable reference gain/noise model for a Sony sensor family.

The Seestar firmware can scale its public gain control differently from an
ASI camera using the same Sony sensor.  These curves are therefore only a
fallback for frames whose Alpaca driver does not provide ``ElectronsPerADU``;
the FITS headers label that fact, and a per-sensor photon-transfer calibration
always wins.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SensorReference:
    """Published reference anchors for one sensor / camera electronics pair."""

    name: str
    full_well_e: int
    hcg_threshold: int
    anchors: tuple[tuple[int, float, float], ...]  # gain, e-/ADU, read noise e-
    hcg_full_well_fraction: float = 0.25

    @property
    def calibration_path(self) -> Path:
        return Path.home() / ".argos" / f"camera_calibration_{self.name.lower()}.json"

    def lookup_egain(self, gain_setting: int) -> float:
        gain = self._clamp(gain_setting)
        user = self._user_value(gain, "egain")
        return user if user is not None else self._interpolate_log(gain, 1)

    def lookup_read_noise(self, gain_setting: int) -> float:
        gain = self._clamp(gain_setting)
        user = self._user_value(gain, "rdnoise")
        return user if user is not None else self._interpolate_linear(gain, 2)

    def full_well_capacity(self, gain_setting: int) -> int:
        if self._clamp(gain_setting) < self.hcg_threshold:
            return self.full_well_e
        return int(self.full_well_e * self.hcg_full_well_fraction)

    def _clamp(self, gain: int) -> int:
        return max(self.anchors[0][0], min(self.anchors[-1][0], int(gain)))

    def _bracket(self, gain: int) -> tuple[tuple[int, float, float], tuple[int, float, float]]:
        gain = self._clamp(gain)
        for lo, hi in zip(self.anchors, self.anchors[1:]):
            if lo[0] <= gain <= hi[0]:
                return lo, hi
        return self.anchors[-2], self.anchors[-1]

    def _interpolate_log(self, gain: int, index: int) -> float:
        lo, hi = self._bracket(gain)
        if lo[0] == hi[0]:
            return lo[index]
        fraction = (gain - lo[0]) / (hi[0] - lo[0])
        value = math.exp(
            math.log(lo[index]) + fraction * (math.log(hi[index]) - math.log(lo[index]))
        )
        return round(value, 4)

    def _interpolate_linear(self, gain: int, index: int) -> float:
        lo, hi = self._bracket(gain)
        if lo[0] == hi[0]:
            return lo[index]
        fraction = (gain - lo[0]) / (hi[0] - lo[0])
        return round(lo[index] + fraction * (hi[index] - lo[index]), 3)

    def _user_value(self, gain: int, key: str) -> float | None:
        """Read an exact local photon-transfer calibration when supplied."""
        try:
            data = json.loads(self.calibration_path.read_text(encoding="utf-8"))
            value = data.get(str(gain), {}).get(key)
            return float(value) if value is not None else None
        except (OSError, ValueError, TypeError):
            return None
