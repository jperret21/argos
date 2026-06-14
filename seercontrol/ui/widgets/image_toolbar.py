"""Compact toolbar above the image — debayer-mode / channel selection.

Stretch, histogram and measurement controls live in the Display tab
(``HistogramDock``); this bar just picks the *view* (debayer mode / CFA channel)
and shows the persistent "display ≠ data" reminder.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from seercontrol.core.imaging import debayer
from seercontrol.ui import theme

logger = logging.getLogger(__name__)


def _lbl(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
    return label


class ImageToolbar(QWidget):
    """Horizontal toolbar with the view (debayer mode / channel) selector.

    Signals:
        channel_changed(str): the selected view (see ``debayer.VIEWS``).
        open_requested():     the user wants to open a FITS file from disk.
    """

    channel_changed = pyqtSignal(str)
    open_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(38)
        self.setMaximumHeight(48)
        self.setStyleSheet(
            f"background-color: {theme.SURFACE_3}; border-bottom: 1px solid {theme.SURFACE_4};"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        layout.addWidget(_lbl("View:"))
        self._channel_combo = QComboBox()
        self._channel_combo.setMinimumWidth(120)
        self._channel_combo.setStyleSheet("font-size: 11px;")
        for view in debayer.VIEWS:
            self._channel_combo.addItem(view)
        self._channel_combo.setCurrentIndex(0)  # Super-pixel (clean colour preview)
        self._channel_combo.setToolTip(
            "Display only — the saved FITS stays raw, linear, CFA.\n"
            "Super-pixel  — 2×2→1 RGB, no interpolation (clean preview)\n"
            "Interpolated — bilinear RGB, cosmetic only\n"
            "Raw CFA      — the Bayer mosaic (check GRBG alignment / hot pixels)\n"
            "R/G/B/G1/G2/Luminance — real CFA pixels (measurement-safe)"
        )
        self._channel_combo.currentTextChanged.connect(self.channel_changed)
        layout.addWidget(self._channel_combo)

        self._open_btn = QPushButton("Open FITS…")
        self._open_btn.setStyleSheet("font-size: 11px;")
        self._open_btn.setToolTip("Load a FITS file from disk into the viewer")
        self._open_btn.clicked.connect(self.open_requested)
        layout.addWidget(self._open_btn)

        layout.addStretch()

        # Persistent reminder: the on-screen image is stretched/debayered while
        # the data written to disk stays raw + linear (capture_panel.md §0).
        indicator = QLabel("display stretched · data linear on disk")
        indicator.setStyleSheet(
            f"color: {theme.WARNING}; font-size: 10px; background: transparent;"
        )
        layout.addWidget(indicator)

    def set_view(self, view: str) -> None:
        """Programmatically select a view without re-emitting ``channel_changed``."""
        idx = self._channel_combo.findText(view)
        if idx < 0:
            return
        self._channel_combo.blockSignals(True)
        self._channel_combo.setCurrentIndex(idx)
        self._channel_combo.blockSignals(False)
