"""FITS / raw image viewer widget based on PyQtGraph.

Displays either:
  - 2-D numpy uint16 array (H, W) — raw or single channel, with auto-stretch
  - 3-D numpy uint8  array (H, W, 3) — debayered RGB, levels fixed at 0–255

Controls:
  - Auto Stretch button (grayscale only)
  - Gamma correction via set_gamma()
  - Native PyQtGraph zoom / pan and interactive histogram
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class FitsViewer(QWidget):
    """Image viewer with histogram, auto-stretch, and gamma correction.

    Args:
        parent: Optional parent widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._first_frame = True
        self._is_rgb = False
        self._last_arr: np.ndarray | None = None
        self._gamma: float = 1.0
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        pg.setConfigOptions(imageAxisOrder="row-major")
        self._view = pg.ImageView()
        self._view.ui.roiBtn.hide()
        self._view.ui.menuBtn.hide()
        layout.addWidget(self._view)

    def display(self, arr: np.ndarray) -> None:
        """Display a new frame.

        Args:
            arr: Either:
                 - 2-D uint16 (H, W)   — raw / single channel
                 - 3-D uint8  (H, W, 3) — debayered RGB
        """
        if arr.ndim not in (2, 3):
            return

        self._last_arr = arr
        self._is_rgb = arr.ndim == 3

        display = self._apply_gamma(arr)

        self._view.setImage(
            display,
            autoRange=False,
            autoLevels=False,
            autoHistogramRange=False,
        )

        if self._first_frame or self._is_rgb:
            self._auto_stretch()
            self._first_frame = False

    def set_gamma(self, value: float) -> None:
        """Set gamma correction value and re-render the last frame.

        Args:
            value: Gamma exponent. 1.0 = neutral. < 1.0 darkens, > 1.0 brightens.
        """
        self._gamma = max(0.01, value)
        if self._last_arr is not None:
            self.display(self._last_arr)

    def _apply_gamma(self, arr: np.ndarray) -> np.ndarray:
        """Apply gamma correction to an array.

        Args:
            arr: Input array (uint16 2-D or uint8 3-D).

        Returns:
            Gamma-corrected array of the same dtype and shape.
        """
        if self._gamma == 1.0:
            return arr

        if arr.ndim == 2:
            # uint16 grayscale
            f = arr.astype(np.float32) / 65535.0
            f = np.power(np.clip(f, 0.0, 1.0), 1.0 / self._gamma)
            return (f * 65535.0).astype(np.uint16)
        else:
            # uint8 RGB
            f = arr.astype(np.float32) / 255.0
            f = np.power(np.clip(f, 0.0, 1.0), 1.0 / self._gamma)
            return (f * 255.0).astype(np.uint8)

    def _auto_stretch(self) -> None:
        """Set display levels to 1%–99% percentile (grayscale) or 0–255 (RGB)."""
        img = self._view.image
        if img is None:
            return
        if self._is_rgb:
            self._view.setLevels(0, 255)
        else:
            lo = float(np.percentile(img, 1))
            hi = float(np.percentile(img, 99))
            if hi <= lo:
                hi = lo + 1
            self._view.setLevels(lo, hi)

    def reset(self) -> None:
        """Reset viewer state (call when switching targets)."""
        self._first_frame = True
        self._is_rgb = False
        self._last_arr = None
        self._gamma = 1.0
