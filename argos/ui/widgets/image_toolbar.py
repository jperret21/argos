"""Compact toolbar above the image — debayer-mode / channel selection.

Stretch, histogram and measurement controls live in the Display tab
(``HistogramDock``); this bar just picks the *view* (debayer mode / CFA channel)
and shows the persistent "display ≠ data" reminder.
"""

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

    Signals:
        channel_changed(str): the selected view (see ``debayer.VIEWS``).
        open_requested():     the user wants to open a FITS file from disk.
        solve_requested():    plate-solve the current live frame (§6).
        auto_solve_toggled(bool): arm/disarm per-frame auto plate-solving (§6).
        photometry_requested(): open the live photometry window (§6 P4).
        photometry_setup_requested(): open the photometry setup window.
    """

    channel_changed = pyqtSignal(str)
    open_requested = pyqtSignal()
    solve_requested = pyqtSignal()
    auto_solve_toggled = pyqtSignal(bool)
    photometry_requested = pyqtSignal()
    photometry_setup_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, show_solve: bool = True) -> None:
        super().__init__(parent)
        self._show_solve = show_solve  # the live page owns solving; Open-FITS has its own bar
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

        if self._show_solve:
            self._solve_btn = QPushButton("Solve")
            self._solve_btn.setStyleSheet("font-size: 11px;")
            self._solve_btn.setToolTip(
                "Plate-solve the current live frame via ASTAP (uses the mount as a\n"
                "position hint). Shows centre RA/Dec + an RA/Dec grid overlay."
            )
            self._solve_btn.clicked.connect(self.solve_requested)
            layout.addWidget(self._solve_btn)

            self._auto_solve_btn = QPushButton("Auto-solve")
            self._auto_solve_btn.setCheckable(True)
            self._auto_solve_btn.setStyleSheet("font-size: 11px;")
            self._auto_solve_btn.setToolTip(
                "Re-solve the live frame automatically as the sequence runs, so the\n"
                "RA/Dec grid tracks the field instead of going stale. Re-solves only\n"
                "when due (mount moved or a few seconds elapsed); keeps the last grid\n"
                "if a solve misses."
            )
            self._auto_solve_btn.toggled.connect(self.auto_solve_toggled)
            layout.addWidget(self._auto_solve_btn)

            self._phot_btn = QPushButton("Photometry")
            self._phot_btn.setStyleSheet("font-size: 11px;")
            self._phot_btn.setToolTip(
                "Open the live differential light-curve preview + session metrics\n"
                "(temperature / airmass / FWHM vs time) for the saved target set."
            )
            self._phot_btn.clicked.connect(self.photometry_requested)
            layout.addWidget(self._phot_btn)

            self._phot_setup_btn = QPushButton("Setup")
            self._phot_setup_btn.setStyleSheet("font-size: 11px;")
            self._phot_setup_btn.setToolTip(
                "Open the photometry setup window — pick a reference frame, solve,\n"
                "select targets (VSX), assign comparisons, configure apertures,\n"
                "then run differential photometry on all sequence frames."
            )
            self._phot_setup_btn.clicked.connect(self.photometry_setup_requested)
            layout.addWidget(self._phot_setup_btn)

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
