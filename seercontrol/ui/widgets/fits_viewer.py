"""FITS / raw image viewer widget based on PyQtGraph.

Displays a 2-D numpy uint16 array with:
  - Auto-stretch on first display (1 %–99 % percentile)
  - Interactive histogram + manual levels
  - Native PyQtGraph zoom / pan
  - "Auto Stretch" button to reset levels

Usage::

    viewer = FitsViewer()
    viewer.display(arr)   # arr: np.ndarray, shape (H, W), dtype uint16
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
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        self._auto_btn = QPushButton("Auto Stretch")
        self._auto_btn.setFixedHeight(24)
        self._auto_btn.clicked.connect(self._auto_stretch)
        toolbar.addStretch()
        toolbar.addWidget(self._auto_btn)
        layout.addLayout(toolbar)

        # Image view
        pg.setConfigOptions(imageAxisOrder="row-major")
        self._view = pg.ImageView()
        self._view.ui.roiBtn.hide()
        self._view.ui.menuBtn.hide()
        layout.addWidget(self._view)

    def display(self, arr: np.ndarray) -> None:
        """Display a new frame.

        Args:
            arr: 2-D numpy array, shape (H, W), dtype uint16.
                 Displayed as-is; no Bayer demosaicing applied here.
        """
        if arr.ndim != 2:
            return

        # PyQtGraph ImageView expects (rows, cols) with imageAxisOrder="row-major"
        self._view.setImage(
            arr,
            autoRange=False,
            autoLevels=False,
            autoHistogramRange=False,
        )

        if self._first_frame:
            self._auto_stretch()
            self._first_frame = False

    def _auto_stretch(self) -> None:
        """Set display levels to 1 %–99 % percentile of current image."""
        img = self._view.image
        if img is None:
            return
        lo = float(np.percentile(img, 1))
        hi = float(np.percentile(img, 99))
        if hi <= lo:
            hi = lo + 1
        self._view.setLevels(lo, hi)
