"""Synthetic 16-bit camera: a plausible Seestar star field, deterministic per frame.

Not a physics engine — a test pattern with the statistics a photometry UI
must cope with: a sky pedestal near 2000 ADU, shot noise plus read noise, a
few hundred Gaussian stars over a steep luminosity function (a handful
saturate), fixed hot pixels, a gentle sky gradient, slight seeing changes and
a small pointing drift between frames.

Frame *n* is a pure function of ``(seed, n, exposure, gain)``: the star field
comes from the seed, the noise and the jitter from ``(seed, n)``. Units are
16-bit ADU throughout; the "reference" settings are a 2 s exposure at the
Seestar's default gain of 80.

Wave 3: with a :class:`~argos.server.devices.sim_aux.SimOptics` the frame
also follows the simulated focuser (the stars blur away from best focus,
their flux conserved, so ``compute_hfd`` traces a V-curve) and the filter
wheel (the Dark slot blocks the light: sky and stars vanish, the pedestal,
read noise and hot pixels stay). The ``light`` flag of an exposure closes
nothing, as on a Seestar. Offset shifts the pedestal by 2 ADU per unit.
"""

from __future__ import annotations

import math
import threading
from typing import Callable

import numpy as np

from argos.server.devices.base import CameraLimits, ExposureCancelled
from argos.server.state import SensorInfo

#: Zero-exposure level (ADU), as a bias frame would read.
PEDESTAL_ADU = 1600.0
#: Sky brightness at the reference gain (ADU/s): 2 s brings the frame to ~2000 ADU.
SKY_RATE_ADU_S = 200.0
#: Read noise (ADU rms) and system gain (ADU per photo-electron) at the reference gain.
READ_NOISE_ADU = 12.0
ADU_PER_E = 3.0
REFERENCE_GAIN = 80
#: Median seeing (px FWHM): 6.7″ at the S50's 2.39″/px (206.265 × 2.9 µm / 250 mm).
FWHM_PX = 2.8
SATURATION_ADU = 65535
#: Stars are generated over a slightly larger field so drift reveals new ones.
_MARGIN_PX = 16
#: Offset (ASCOM ``Offset``) at which the pedestal is PEDESTAL_ADU, and its slope.
REFERENCE_OFFSET = 10
ADU_PER_OFFSET = 2.0
#: Driver ranges the simulator advertises (wave 3, ``CameraLimits``).
SIM_LIMITS = CameraLimits(
    gain_min=0,
    gain_max=600,
    exposure_min_s=0.001,
    exposure_max_s=3600.0,
    offset_range=(0, 255),
    max_bin=1,
)
#: Sensor temperature the simulator reports (°C).
SENSOR_TEMPERATURE_C = 21.0


class SimCamera:
    """Implements :class:`~argos.server.devices.base.CameraDevice`."""

    source = "simulator"
    name = "ARGOS camera simulator"

    def __init__(
        self,
        width: int = 1080,
        height: int = 1920,
        seed: int = 20261101,
        n_stars: int = 240,
        optics=None,
    ) -> None:
        if width < 8 or height < 8:
            raise ValueError("simulated sensor must be at least 8×8")
        self.width = int(width)
        self.height = int(height)
        self._seed = int(seed)
        self._lock = threading.Lock()
        self._index = 0
        #: ``SimOptics`` shared with the simulated focuser and wheel (or None).
        self._optics = optics
        self._offset = REFERENCE_OFFSET
        #: Light flags of the exposures, newest last (tests read them).
        self.light_flags: list[bool] = []

        rng = np.random.default_rng([self._seed, 0])
        self._star_x = rng.uniform(-_MARGIN_PX, self.width + _MARGIN_PX, n_stars)
        self._star_y = rng.uniform(-_MARGIN_PX, self.height + _MARGIN_PX, n_stars)
        # Peak brightness (ADU/s at the reference gain): a Pareto tail, so faint
        # stars dominate (cumulative counts ∝ flux^-0.6) and bright ones are rare.
        peak_ref = 90.0 * rng.uniform(1e-6, 1.0, n_stars) ** (-1.0 / 0.6)
        self._peak_rate = np.minimum(peak_ref, 3e6) / 2.0
        # Guarantee a few saturated stars well inside the frame, whatever the seed.
        n_bright = min(4, n_stars)
        self._star_x[:n_bright] = rng.uniform(0.1, 0.9, n_bright) * self.width
        self._star_y[:n_bright] = rng.uniform(0.1, 0.9, n_bright) * self.height
        self._peak_rate[:n_bright] = rng.uniform(1.5e5, 8e5, n_bright) / 2.0

        # Hot pixels are fixed on the sensor: they do not drift with the sky.
        n_hot = max(1, self.width * self.height // 50_000)
        self._hot_x = rng.integers(0, self.width, n_hot)
        self._hot_y = rng.integers(0, self.height, n_hot)
        self._hot_rate = rng.uniform(300.0, 20_000.0, n_hot)  # ADU/s
        # Light-pollution gradient: the sky brightens by 4 % towards the bottom.
        self._gradient = (1.0 + 0.04 * np.linspace(-0.5, 0.5, self.height, dtype=np.float32))[
            :, None
        ]

    # -- CameraDevice ------------------------------------------------------

    def sensor(self) -> SensorInfo:
        return SensorInfo(width=self.width, height=self.height, bitpix=16, bayer=None)

    def expose(
        self,
        exposure_s: float,
        gain: int,
        cancel: threading.Event,
        on_readout: Callable[[], None],
        *,
        light: bool = True,
        on_start: Callable[[], None] | None = None,
    ) -> np.ndarray:
        with self._lock:
            self._index += 1
            index = self._index
            offset = self._offset
            self.light_flags = (self.light_flags + [bool(light)])[-64:]
        if on_start is not None:
            on_start()
        optics = self._optics
        # Focus and filter at the start and the end of the exposure: a wheel
        # that turns during it, or a focuser that moves, shows in the frame.
        start = (optics.fwhm_factor(), optics.transmission()) if optics is not None else (1, 1)
        # The exposure time is really waited, and stop interrupts it at once.
        if cancel.wait(max(0.0, float(exposure_s))):
            raise ExposureCancelled()
        on_readout()
        end = (optics.fwhm_factor(), optics.transmission()) if optics is not None else (1, 1)
        frame = self.render(
            index,
            exposure_s,
            gain,
            fwhm_factor=max(start[0], end[0]),
            transmission=min(start[1], end[1]),
            offset=offset,
        )
        if cancel.is_set():
            raise ExposureCancelled()
        return frame

    def abort(self) -> None:
        pass  # expose() watches its cancel event

    def close(self) -> None:
        pass

    # -- wave 3 camera extras ------------------------------------------------

    def limits(self) -> CameraLimits:
        return SIM_LIMITS

    def get_offset(self) -> int | None:
        with self._lock:
            return self._offset

    def set_offset(self, value: int) -> None:
        low, high = SIM_LIMITS.offset_range or (0, 0)
        with self._lock:
            self._offset = max(low, min(high, int(value)))

    def set_binning(self, value: int) -> None:
        if int(value) != 1:
            from argos.server.devices.base import DeviceError

            raise DeviceError("The simulated camera does not bin")

    def temperature(self) -> float | None:
        return SENSOR_TEMPERATURE_C

    def fits_readings(self) -> dict[str, object]:
        return {
            "ccd_temp": SENSOR_TEMPERATURE_C,
            "egain_driver": None,  # FITS EGAIN from the sensor reference
            "offset": self.get_offset(),
            "readout_mode": None,
        }

    # -- synthesis ---------------------------------------------------------

    def drift(self, index: int) -> tuple[float, float]:
        """Pointing offset (px) of frame *index*: slow periodic wander + jitter."""
        rng = np.random.default_rng([self._seed, index, 1])
        dx = 5.0 * math.sin(2.0 * math.pi * index / 360.0) + rng.normal(0.0, 0.25)
        dy = 4.0 * math.sin(2.0 * math.pi * index / 500.0 + 1.0) + rng.normal(0.0, 0.25)
        return float(dx), float(dy)

    def render(
        self,
        index: int,
        exposure_s: float,
        gain: int,
        *,
        fwhm_factor: float = 1.0,
        transmission: float = 1.0,
        offset: int = REFERENCE_OFFSET,
    ) -> np.ndarray:
        """Synthesize frame *index* — deterministic, ~25 ms at 1080×1920.

        *fwhm_factor* widens every star (defocus) with its flux conserved;
        *transmission* scales sky and stars (0 = the wheel's Dark slot).
        """
        h, w = self.height, self.width
        t = max(0.0, float(exposure_s))
        # ZWO gain is in 0.1 dB steps: ×10^(Δgain/200) on every ADU figure.
        g = 10.0 ** ((int(gain) - REFERENCE_GAIN) / 200.0)
        rng = np.random.default_rng([self._seed, index])
        light = max(0.0, float(transmission))
        blur = max(1.0, float(fwhm_factor))

        sky = np.float32(SKY_RATE_ADU_S * t * g * light)
        img = np.empty((h, w), dtype=np.float32)
        img[:] = sky * self._gradient

        dx, dy = self.drift(index)
        # Seeing varies a few percent from frame to frame.
        sigma = blur * max(0.5, FWHM_PX * (1.0 + 0.04 * rng.standard_normal()) / 2.3548)
        for x0, y0, rate in zip(self._star_x, self._star_y, self._peak_rate):
            # Defocus spreads the same flux over blur² more area.
            peak = rate * t * g * light / (blur * blur)
            if peak < 1.0:
                continue
            x, y = x0 + dx, y0 + dy
            self._add_gaussian(img, x, y, peak, sigma)
            if peak > 20_000.0:
                # Faint wide wings so bright stars are not hard-edged discs.
                self._add_gaussian(img, x, y, 0.015 * peak, 3.5 * sigma)

        # Shot noise on everything above the pedestal, plus read noise.
        variance = img * np.float32(ADU_PER_E * g)
        variance += np.float32((READ_NOISE_ADU * g) ** 2)
        noise = rng.standard_normal((h, w), dtype=np.float32)
        noise *= np.sqrt(variance)
        img += noise
        pedestal = PEDESTAL_ADU + ADU_PER_OFFSET * (int(offset) - REFERENCE_OFFSET)
        img += np.float32(pedestal + 0.5)  # +0.5: round, not truncate, below
        img[self._hot_y, self._hot_x] += (self._hot_rate * t).astype(np.float32)
        np.clip(img, 0.0, SATURATION_ADU, out=img)
        return img.astype(np.uint16)

    @staticmethod
    def _add_gaussian(img: np.ndarray, x: float, y: float, peak: float, sigma: float) -> None:
        """Add a circular Gaussian, cut where it falls below 0.5 ADU."""
        h, w = img.shape
        radius = min(60, int(math.ceil(sigma * math.sqrt(2.0 * math.log(max(peak, 1.0) / 0.5)))))
        xi, yi = int(math.floor(x)), int(math.floor(y))
        x_lo, x_hi = max(0, xi - radius), min(w, xi + radius + 2)
        y_lo, y_hi = max(0, yi - radius), min(h, yi + radius + 2)
        if x_lo >= x_hi or y_lo >= y_hi:
            return
        gx = np.exp(-0.5 * ((np.arange(x_lo, x_hi) - x) / sigma) ** 2)
        gy = np.exp(-0.5 * ((np.arange(y_lo, y_hi) - y) / sigma) ** 2)
        img[y_lo:y_hi, x_lo:x_hi] += (peak * np.outer(gy, gx)).astype(np.float32)
