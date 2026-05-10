"""Acquisition sequence model — frame types, config, Siril-compatible folder layout.

Siril OSC preprocessing script expects:
    <session>/
        lights/
        darks/
        flats/
        biases/

All folder names are lowercase to match Siril's built-in script conventions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class FrameType(str, Enum):
    """FITS IMAGETYP values, used as Enum keys throughout the app."""

    LIGHT = "Light Frame"
    DARK  = "Dark Frame"
    FLAT  = "Flat Frame"
    BIAS  = "Bias Frame"     # called "Offset" in some tools

    @property
    def fits_value(self) -> str:
        return self.value

    @property
    def siril_folder(self) -> str:
        """Lowercase folder name expected by Siril's built-in scripts."""
        return _SIRIL_FOLDERS[self]

    @property
    def label(self) -> str:
        """Human-readable label for UI combo boxes."""
        return _LABELS[self]

    @property
    def needs_exposure(self) -> bool:
        return self is not FrameType.BIAS

    @property
    def needs_filter(self) -> bool:
        return self in (FrameType.LIGHT, FrameType.FLAT)

    @property
    def needs_object(self) -> bool:
        return self is FrameType.LIGHT


_SIRIL_FOLDERS: dict[FrameType, str] = {
    FrameType.LIGHT: "lights",
    FrameType.DARK:  "darks",
    FrameType.FLAT:  "flats",
    FrameType.BIAS:  "biases",
}

_LABELS: dict[FrameType, str] = {
    FrameType.LIGHT: "Light",
    FrameType.DARK:  "Dark",
    FrameType.FLAT:  "Flat",
    FrameType.BIAS:  "Bias (Offset)",
}


@dataclass
class SequenceConfig:
    """Full description of a single acquisition sequence.

    Args:
        frame_type:  Type of frames to acquire (Light/Dark/Flat/Bias).
        count:       Number of frames.
        exposure:    Exposure time in seconds (ignored for Bias).
        gain:        Camera gain.
        filter_name: Filter name used for Lights and Flats.
        object_name: Target name used for Light frames.
        save_folder: User-chosen base output directory.
    """

    frame_type:  FrameType
    count:       int
    exposure:    float
    gain:        int
    filter_name: str  = "LRGB"
    object_name: str  = ""
    save_folder: Path = field(default_factory=lambda: Path.home() / "SeerControl")

    @property
    def actual_exposure(self) -> float:
        """Bias frames use the minimum exposure the camera allows."""
        return 0.001 if self.frame_type is FrameType.BIAS else self.exposure

    def frame_folder(self, session_start: datetime) -> Path:
        """Return the Siril-compatible output folder for this sequence.

        Structure::

            {save_folder}/{YYYYMMDD}_{object}/{siril_folder}/

        For Bias/Dark, object name is replaced with "calibration".
        """
        date = session_start.strftime("%Y%m%d")
        if self.frame_type.needs_object and self.object_name:
            obj = _sanitize(self.object_name)
        else:
            obj = "calibration"
        session_name = f"{date}_{obj}"
        return self.save_folder / session_name / self.frame_type.siril_folder

    def build_filename(self, frame_index: int, exposure_start: datetime) -> str:
        """Build a filename following the project naming convention.

        Format::

            {object}_{type}_{date}_{time}_{exp}s_{filter}_{index:04d}.fits
        """
        obj  = _sanitize(self.object_name) if self.object_name else _sanitize(self.frame_type.label)
        typ  = _sanitize(self.frame_type.label.replace(" ", "_"))
        date = exposure_start.strftime("%Y%m%d")
        tstr = exposure_start.strftime("%H%M%S")
        filt = _sanitize(self.filter_name) if self.frame_type.needs_filter else "NoFilter"
        exp  = _format_exp(self.actual_exposure)
        return f"{obj}_{typ}_{date}_{tstr}_{exp}s_{filt}_{frame_index:04d}.fits"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(s: str) -> str:
    return re.sub(r"[^\w\-]", "", s.replace(" ", "_"))


def _format_exp(seconds: float) -> str:
    if seconds == int(seconds):
        return str(int(seconds))
    return f"{seconds:.3f}".rstrip("0").rstrip(".").replace(".", "p")
