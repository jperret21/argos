"""Persistent application configuration stored as JSON.

Config file location: ~/.argos/config.json
All values have sensible defaults and can be updated at runtime.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".argos"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS: dict[str, Any] = {
    "alpaca": {
        "host": "",
        "port": 4700,
    },
    "sessions_path": str(Path.home() / "Argos" / "sessions"),
    "observer": {
        "name": "",
        "obscode": "",  # AAVSO observer code — stamped on every AAVSO export
        "latitude": 0.0,
        "longitude": 0.0,
        "elevation": 0.0,
    },
    "ui": {
        "log_level": "INFO",
        "window_state": None,  # base64 QMainWindow.saveState()
        "window_geometry": None,
    },
    # Sensor characteristics — confirm against hardware (see docs/capture_panel.md §8).
    # IMX585 Starvis 2: 12-bit ADC scaled to 16-bit; "full_well_adu" is the
    # saturation/linearity threshold used by the display clipping indicator.
    "camera": {
        "adc_bits": 12,
        "full_well_adu": 60000,
        "linearity_max_adu": 50000,
        "egain_table": {},  # {gain_value: e-/ADU}; empty → driver/IMX585 lookup
    },
    # Plate-solving (ASTAP) + the live auto-solve policy. See
    # docs/photometry_plan.md §4/§8. Empty astap_path/database → auto-detect.
    "astrometry": {
        "astap_path": "",
        "database": "",
        "downsample": 2,
        "search_radius_deg": 30,  # thorough/manual solve (around a hint)
        "use_scale_hint": True,
        "grid_spacing_arcmin": 0,  # 0 = adaptive 1/2/5 grid
        "live_search_radius_deg": 5,  # small radius w/ mount hint (auto-solve)
        "live_resolve_s": 20,  # re-solve cadence ceiling (auto)
        "live_resolve_arcmin": 2,  # re-solve once the mount moves this far
        "live_timeout_s": 25,  # bound the live solve so the cadence never stalls
    },
    # VSX/VSP variable-star catalog cone search (docs/photometry_plan.md §5).
    "catalog": {
        "mag_limit": 15.0,
        "max_results": 250,
        "include_suspected": True,
    },
    # Differential-photometry preview (docs/photometry_plan.md §6).
    "photometry": {
        "aperture_fwhm_mult": 2.5,
        "aperture_min_px": 4,
        "annulus_in_px": 8,
        "annulus_out_px": 12,
        "read_noise_e": 1.5,
        "default_band": "TG",
        "min_comparisons": 2,
    },
}


class Config:
    """Application configuration backed by a JSON file.

    Usage:
        config = Config.load()
        config.set("alpaca.host", "192.168.1.42")
        config.save()
        host = config.get("alpaca.host")
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def load(cls) -> "Config":
        """Load config from disk, creating defaults if the file does not exist."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not _CONFIG_FILE.exists():
            logger.info("No config file found, creating defaults at %s", _CONFIG_FILE)
            instance = cls(_deep_copy(_DEFAULTS))
            instance.save()
            return instance

        try:
            with _CONFIG_FILE.open("r", encoding="utf-8") as f:
                on_disk = json.load(f)
            data = _deep_merge(_DEFAULTS, on_disk)
            logger.debug("Config loaded from %s", _CONFIG_FILE)
            return cls(data)
        except Exception as exc:
            logger.error("Failed to load config (%s), using defaults", exc)
            return cls(_deep_copy(_DEFAULTS))

    def save(self) -> None:
        """Persist current config to disk."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with _CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            logger.debug("Config saved to %s", _CONFIG_FILE)
        except Exception as exc:
            logger.error("Failed to save config: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value using dot-notation key (e.g. 'alpaca.host')."""
        parts = key.split(".")
        node: Any = self._data
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> None:
        """Set a value using dot-notation key and persist immediately."""
        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self.save()

    # Convenience properties for the most-used values

    @property
    def alpaca_host(self) -> str:
        return self.get("alpaca.host", "")

    @alpaca_host.setter
    def alpaca_host(self, value: str) -> None:
        self.set("alpaca.host", value)

    @property
    def alpaca_port(self) -> int:
        return self.get("alpaca.port", 4700)

    @alpaca_port.setter
    def alpaca_port(self, value: int) -> None:
        self.set("alpaca.port", value)

    @property
    def sessions_path(self) -> Path:
        return Path(self.get("sessions_path", str(Path.home() / "Argos" / "sessions")))

    @sessions_path.setter
    def sessions_path(self, value: Path | str) -> None:
        self.set("sessions_path", str(value))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively. Override wins on conflicts."""
    result = _deep_copy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
