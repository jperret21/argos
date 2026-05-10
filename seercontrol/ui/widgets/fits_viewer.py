"""FITS / raw image viewer widget based on PyQtGraph.

Displays either:
  - 2-D numpy uint16 array (H, W) — raw or single channel, with auto-stretch
  - 3-D numpy uint8  array (H, W, 3) — debayered RGB, levels fixed at 0–255

Controls:
  - Auto Stretch button (grayscale only)
  - Native PyQtGraph zoom / pan and interactive histogram
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget


class FitsViewer(QWidget):
    """Image viewer with histogram and auto-stretch.

    Args:
        parent: Optional parent widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._first_frame = True
        self._is_rgb = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        self._auto_btn = QPushButton("Auto Stretch")
        self._auto_btn.setFixedHeight(24)
        self._auto_btn.setToolTip("Reset display levels to 1%–99% percentile")
        self._auto_btn.clicked.connect(self._auto_stretch)
        toolbar.addStretch()
        toolbar.addWidget(self._auto_btn)
        layout.addLayout(toolbar)

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

        self._is_rgb = arr.ndim == 3

        self._view.setImage(
            arr,
            autoRange=False,
            autoLevels=False,
            autoHistogramRange=False,
        )

        if self._first_frame or self._is_rgb:
            self._auto_stretch()
            self._first_frame = False

        self._auto_btn.setEnabled(not self._is_rgb)

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
