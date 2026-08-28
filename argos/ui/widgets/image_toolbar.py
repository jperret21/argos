"""Small observer-facing toolbar above the FITS image."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from argos.core.imaging import debayer
from argos.ui import theme

logger = logging.getLogger(__name__)


def _lbl(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
    return label


class ImageToolbar(QWidget):
    """Horizontal toolbar with the view (debayer mode / channel) selector.

    Solve / auto-solve / photometry actions live in the Shell's menu bar
    (Astrometry / Photometry menus) — field feedback: no dropdown buttons here.

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

        self._open_btn = QPushButton("Open image…")
        self._open_btn.setToolTip("Open a FITS image")
        self._open_btn.clicked.connect(self.open_requested)
        layout.addWidget(self._open_btn)

        layout.addWidget(_lbl("Preview:"))
        self._channel_combo = QComboBox()
        self._channel_combo.setMinimumWidth(120)
        self._channel_combo.setStyleSheet("font-size: 11px;")
        labels = {
            debayer.VIEW_SUPERPIXEL: "Colour",
            debayer.VIEW_INTERP: "Smooth colour",
            debayer.VIEW_RAW: "Raw sensor",
            debayer.VIEW_R: "Red channel",
            debayer.VIEW_G: "Green channel",
            debayer.VIEW_B: "Blue channel",
            debayer.VIEW_G1: "Green 1",
            debayer.VIEW_G2: "Green 2",
            debayer.VIEW_LUM: "Luminance",
        }
        for view in debayer.VIEWS:
            self._channel_combo.addItem(labels[view], view)
        self._channel_combo.setCurrentIndex(0)  # Super-pixel (clean colour preview)
        self._channel_combo.setToolTip(
            "Changes only the on-screen preview; the FITS data are unchanged."
        )
        self._channel_combo.currentIndexChanged.connect(
            lambda _index: self.channel_changed.emit(str(self._channel_combo.currentData()))
        )
        layout.addWidget(self._channel_combo)

        layout.addStretch()
        layout.addWidget(_lbl("Preview only · FITS unchanged"))

    def set_view(self, view: str) -> None:
        """Programmatically select a view without re-emitting ``channel_changed``."""
        idx = self._channel_combo.findData(view)
        if idx < 0:
            return
        self._channel_combo.blockSignals(True)
        self._channel_combo.setCurrentIndex(idx)
        self._channel_combo.blockSignals(False)
