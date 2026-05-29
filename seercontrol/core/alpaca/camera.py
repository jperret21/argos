"""ASCOM Alpaca camera wrapper — backed by alpyca.

Uses alpyca which automatically handles:
  - ImageBytes (binary, 8x faster than JSON) vs JSON imagearray
  - Typed exceptions
  - Thread-safe HTTP session

All methods are synchronous — run inside a QThread worker only.

Seestar S30 Pro constraints:
  - Do NOT use ROI/subframing (firmware bug in Alpaca driver)
  - Sensor: IMX585, Bayer GRBG, pixel size 2.9 µm, focal length 160 mm
"""

from __future__ import annotations

import logging
import time

import numpy as np
from alpaca.camera import Camera as _AlpacaCamera
from alpaca.exceptions import DriverException, InvalidValueException, NotImplementedException

from seercontrol.core.alpaca.client import AlpacaError

logger = logging.getLogger(__name__)

# IMX585 physical characteristics (Seestar S30 Pro)
PIXEL_SIZE_UM = 2.9
FOCAL_LENGTH  = 160
BAYER_PATTERN = "GRBG"
INSTRUMENT    = "IMX585"
TELESCOPE_NAME = "ZWO Seestar S30 Pro"


def _wrap(exc: Exception) -> AlpacaError:
    if isinstance(exc, DriverException):
        return AlpacaError(exc.number, str(exc))
    return AlpacaError(0, str(exc))


class Camera:
    """ASCOM Alpaca camera controller, backed by alpyca.

    Args:
        host: IP address of the Seestar.
        port: Alpaca HTTP port.
    """

    def __init__(self, host: str, port: int) -> None:
        self._cam = _AlpacaCamera(f"{host}:{port}", 0)
        self._connected = False
        self.width:    int = 3840
        self.height:   int = 2160
        self.gain_min: int = 0
        self.gain_max: int = 100

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> str:
        """Connect and return the camera name.

        Also reads sensor dimensions and gain range for the UI.

        Raises:
            AlpacaError: Connection or device error.
        """
        try:
            self._cam.Connected = True
        except Exception as exc:
            raise _wrap(exc) from exc

        self._connected = True

        try:
            self.width    = int(self._cam.CameraXSize)
            self.height   = int(self._cam.CameraYSize)
            self.gain_min = int(self._cam.GainMin)
            self.gain_max = int(self._cam.GainMax)
            logger.debug(
                "Camera metadata: CameraXSize=%d CameraYSize=%d GainMin=%d GainMax=%d",
                self.width, self.height, self.gain_min, self.gain_max,
            )
        except Exception as exc:
            logger.warning("Could not read camera metadata (using defaults): %s", exc)

        try:
            name = self._cam.Name or "Unknown"
        except Exception:
            name = "Unknown"

        logger.info(
            "Camera connected: %s  %dx%d  gain %d–%d",
            name, self.width, self.height, self.gain_min, self.gain_max,
        )
        return name

    def disconnect(self) -> None:
        """Disconnect from the camera."""
        try:
            self._cam.Connected = False
        except Exception as exc:
            logger.warning("Camera disconnect error: %s", exc)
        finally:
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_state(self) -> int:
        """Return the current camera state (0–5)."""
        try:
            return int(self._cam.CameraState)
        except Exception as exc:
            raise _wrap(exc) from exc

    def is_image_ready(self) -> bool:
        """Return True when a new image is available to download."""
        try:
            return bool(self._cam.ImageReady)
        except Exception as exc:
            raise _wrap(exc) from exc

    def get_gain(self) -> int:
        """Return the current gain value."""
        try:
            return int(self._cam.Gain)
        except Exception as exc:
            raise _wrap(exc) from exc

    def set_gain(self, gain: int) -> None:
        """Set camera gain (clamped to valid range)."""
        gain = max(self.gain_min, min(self.gain_max, gain))
        try:
            self._cam.Gain = gain
            logger.debug("Gain set to %d", gain)
        except Exception as exc:
            raise _wrap(exc) from exc

    # ------------------------------------------------------------------
    # Optional properties (driver may or may not expose them)
    # ------------------------------------------------------------------

    def get_ccd_temperature(self) -> float | None:
        """Return sensor temperature in °C, or None if unsupported.

        Falls back to ``HeatSinkTemperature`` if ``CCDTemperature`` is absent
        (the Seestar is air-cooled — no Peltier — but exposes a sensor probe).
        """
        for attr in ("CCDTemperature", "HeatSinkTemperature"):
            try:
                value = getattr(self._cam, attr)
                if value is None:
                    continue
                return round(float(value), 2)
            except (AttributeError, NotImplementedException, InvalidValueException, DriverException):
                continue
            except Exception as exc:
                logger.debug("%s read failed: %s", attr, exc)
        return None

    def get_electrons_per_adu(self) -> float | None:
        """Return ElectronsPerADU from the driver, or None if not exposed."""
        try:
            value = self._cam.ElectronsPerADU
            if value is None or value <= 0:
                return None
            return round(float(value), 4)
        except (AttributeError, NotImplementedException, InvalidValueException, DriverException):
            return None
        except Exception as exc:
            logger.debug("ElectronsPerADU read failed: %s", exc)
            return None

    def get_offset(self) -> int | None:
        """Return the electronic offset (bias level setting), or None."""
        try:
            return int(self._cam.Offset)
        except (AttributeError, NotImplementedException, InvalidValueException, DriverException):
            return None
        except Exception as exc:
            logger.debug("Offset read failed: %s", exc)
            return None

    def get_readout_mode_name(self) -> str | None:
        """Return current readout mode name (e.g. 'Normal', 'HCG'), or None."""
        try:
            idx = int(self._cam.ReadoutMode)
        except (AttributeError, NotImplementedException, InvalidValueException, DriverException):
            return None
        except Exception as exc:
            logger.debug("ReadoutMode read failed: %s", exc)
            return None
        try:
            modes = self._cam.ReadoutModes
            if modes and 0 <= idx < len(modes):
                return str(modes[idx])
        except Exception:
            pass
        return f"mode{idx}"

    def get_full_well(self) -> int | None:
        """Return full-well capacity in electrons, or None."""
        try:
            value = self._cam.FullWellCapacity
            if value is None or value <= 0:
                return None
            return int(value)
        except (AttributeError, NotImplementedException, InvalidValueException, DriverException):
            return None
        except Exception as exc:
            logger.debug("FullWellCapacity read failed: %s", exc)
            return None

    def get_sensor_metadata(self) -> dict:
        """Snapshot of static sensor metadata for FITS / diagnostics.

        Each field is tolerant — missing values are simply absent from the dict.
        """
        out: dict = {}
        for key, attr in [
            ("name",         "Name"),
            ("sensor_name",  "SensorName"),
            ("sensor_type",  "SensorType"),
            ("bayer_off_x",  "BayerOffsetX"),
            ("bayer_off_y",  "BayerOffsetY"),
            ("max_bin_x",    "MaxBinX"),
            ("max_bin_y",    "MaxBinY"),
            ("driver_info",  "DriverInfo"),
            ("driver_ver",   "DriverVersion"),
        ]:
            try:
                value = getattr(self._cam, attr)
                if value is not None:
                    out[key] = value
            except Exception:
                continue
        return out

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def start_exposure(self, duration: float, light: bool = True) -> None:
        """Start a single exposure.

        Args:
            duration: Exposure time in seconds.
            light:    True for light frame, False for dark/bias.

        Raises:
            AlpacaError: If the camera rejects the command.
        """
        logger.info("Starting %.2fs %s exposure", duration, "light" if light else "dark")
        try:
            self._cam.StartExposure(duration, light)
        except Exception as exc:
            raise _wrap(exc) from exc

    def stop_exposure(self) -> None:
        """Abort any running exposure."""
        try:
            self._cam.StopExposure()
        except Exception as exc:
            logger.warning("Stop exposure: %s", exc)

    def get_image_array(self) -> np.ndarray:
        """Download the last captured image as a 2-D numpy uint16 array.

        Tries ImageArrayRaw first (binary ImageBytes, zero-copy numpy path) and
        falls back to ImageArray (JSON) if the device does not support ImageBytes.

        Returns:
            2-D numpy array, shape (height, width), dtype uint16.

        Raises:
            AlpacaError: On communication or device error.
        """
        _TYPECODE_DTYPE = {
            'H': np.uint16,
            'h': np.int16,
            'i': np.int32,
            'I': np.uint32,
            'd': np.float64,
        }
        t0 = time.perf_counter()

        try:
            # -- Fast path: ImageBytes (binary, 8x faster than JSON) --------
            # ImageArrayRaw raises InvalidValueException if device returns JSON.
            raw = self._cam.ImageArrayRaw          # flat array.array
            meta = self._cam.ImageArrayInfo        # set as side-effect above
            dtype = _TYPECODE_DTYPE.get(raw.typecode, np.int32)

            # Binary layout: column-major [X][Y] — Dimension1=width, Dimension2=height
            # np.frombuffer → zero-copy view; .T → metadata change only; .astype → one copy
            arr = (
                np.frombuffer(raw, dtype=dtype)
                .reshape(meta.Dimension1, meta.Dimension2)
                .T                                  # (height, width)
                .astype(np.uint16)                  # makes a writeable copy
            )
            if dtype not in (np.uint16,):
                np.clip(arr, 0, 65535, out=arr)
            logger.info(
                "Image downloaded (ImageBytes): %.2fs  shape=%s  typecode=%s",
                time.perf_counter() - t0, arr.shape, raw.typecode,
            )
            return arr

        except (InvalidValueException, NotImplementedException):
            # -- Slow path: JSON nested list, column-major [X][Y] -----------
            logger.info("ImageBytes not supported — using JSON imagearray")
            try:
                raw = self._cam.ImageArray          # List[List[int]]
            except Exception as exc:
                raise _wrap(exc) from exc

            if raw is None:
                raise AlpacaError(0, "imagearray returned None")

            t1 = time.perf_counter()
            # Use uint16 directly — IMX585 values are always in [0, 65535]
            arr = np.array(raw, dtype=np.uint16).T  # (height, width)
            logger.info(
                "Image downloaded (JSON): %.2fs transfer + %.2fs convert = %.2fs total  shape=%s",
                t1 - t0, time.perf_counter() - t1, time.perf_counter() - t0, arr.shape,
            )

        except Exception as exc:
            raise _wrap(exc) from exc

        return arr
