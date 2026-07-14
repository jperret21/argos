"""Typed signal payloads for the session layer.

Frozen dataclasses carried by DeviceSession / AcquisitionEngine signals,
replacing the loose ``pyqtSignal(object, ...)`` tuples the ImagingPage used
internally. Modeled on :class:`argos.workers.preview_processor.ProcessedFrame`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True)
class CameraCapabilities:
    """Driver-derived camera limits + optional parameters, read at connect.

    Sourced from the fields :meth:`argos.core.alpaca.camera.Camera.connect`
    populates. ``offset``/``offset_min``/``offset_max`` are ``None`` when the
    driver doesn't support offset; ``max_bin`` is 1 when binning is fixed.
    """

    gain_min: int
    gain_max: int
    exposure_min: float
    exposure_max: float
    offset_min: int | None
    offset_max: int | None
    offset: int | None
    max_bin: int
    binning: int


@dataclass(frozen=True)
class FilterWheelState:
    """Filter wheel snapshot at connect: slot names + current position."""

    names: tuple[str, ...]
    position: int  # -1 while the wheel is moving
    position_name: str


@dataclass(frozen=True)
class FocuserState:
    """Focuser snapshot at connect: capabilities + current position."""

    name: str
    position: int
    max_step: int
    max_increment: int
    absolute: bool


@dataclass(frozen=True)
class LiveFrame:
    """One acquired frame, as published by the AcquisitionEngine.

    ``preview`` is the (possibly stride-decimated) display array; ``full``
    is always the full-resolution readout. ``decimated`` is True when the
    two differ — plate-solve/photometry must skip such frames (their plate
    scale is wrong). ``start``/``end`` are the exposure UTC timestamps
    (``None`` for sequence frames, which are timestamped by their worker).
    """

    preview: np.ndarray
    full: np.ndarray
    start: datetime | None
    end: datetime | None
    decimated: bool


@dataclass(frozen=True)
class PhotometryPoint:
    """One differential-photometry light-curve point for a measured star."""

    key: str  # AUID or display name — the light-curve dict key
    name: str  # display name for the plot legend
    jd: float
    mag: float
    mag_err: float
    saturated: bool
    role: str = "target"  # target / check / comparison — display grouping
