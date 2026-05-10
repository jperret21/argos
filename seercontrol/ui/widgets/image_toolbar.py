"""Compact horizontal toolbar above the FITS image viewer.

Provides quick access to channel selection, gamma correction, and auto-stretch
displayed in a single responsive bar.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

from seercontrol.ui import theme

logger = logging.getLogger(__name__)


def _sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    line.setStyleSheet(f"color: {theme.SURFACE_4};")
    line.setFixedWidth(1)
    return line


def _lbl(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
    return label


class ImageToolbar(QWidget):
    """Horizontal toolbar with image display controls.

    Signals:
        channel_changed:        Emitted when the channel combo changes.
        gamma_changed:          Emitted when the gamma slider changes (float 0.1–3.0).
        auto_stretch_requested: Emitted when the Auto-Stretch button is clicked.
    """

    channel_changed        = pyqtSignal(str)
    gamma_changed          = pyqtSignal(float)
    auto_stretch_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(38)
        self.setMaximumHeight(48)
        self.setStyleSheet(
            f"background-color: {theme.SURFACE_3};"
            f"border-bottom: 1px solid {theme.SURFACE_4};"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # ── Channel ────────────────────────────────────────────────────
        layout.addWidget(_lbl("Channel:"))
        self._channel_combo = QComboBox()
        self._channel_combo.setMinimumWidth(68)
        self._channel_combo.setStyleSheet("font-size: 11px;")
        for ch in ["Raw", "R", "G", "B", "RGB"]:
            self._channel_combo.addItem(ch)
        self._channel_combo.setCurrentIndex(0)
        self._channel_combo.setToolTip(
            "Raw   — direct sensor data (no debayer)\n"
            "R/G/B — single Bayer channel, half resolution\n"
            "RGB   — colour composite, half resolution"
        )
        self._channel_combo.currentTextChanged.connect(self.channel_changed)
        layout.addWidget(self._channel_combo)

        layout.addWidget(_sep())

        # ── Gamma ──────────────────────────────────────────────────────
        layout.addWidget(_lbl("γ:"))
        self._gamma_slider = QSlider(Qt.Orientation.Horizontal)
        self._gamma_slider.setFixedHeight(20)
        self._gamma_slider.setMinimumWidth(80)
        self._gamma_slider.setMaximumWidth(160)
        self._gamma_slider.setRange(10, 300)
        self._gamma_slider.setValue(100)
        self._gamma_slider.setToolTip("Gamma: 0.1 (dark boost) – 3.0 (bright boost)")
        self._gamma_slider.valueChanged.connect(self._on_gamma_changed)
        layout.addWidget(self._gamma_slider)

        self._gamma_lbl = QLabel("1.0×")
        self._gamma_lbl.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 11px; "
            f"min-width: 32px; background: transparent;"
        )
        self._gamma_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._gamma_lbl)

        layout.addWidget(_sep())

        # ── Auto stretch ───────────────────────────────────────────────
        self._auto_btn = QPushButton("Auto ☀")
        self._auto_btn.setMinimumWidth(60)
        self._auto_btn.setStyleSheet("font-size: 11px;")
        self._auto_btn.setToolTip("Reset display levels to 1%–99% percentile")
        self._auto_btn.clicked.connect(self.auto_stretch_requested)
        layout.addWidget(self._auto_btn)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_gamma_changed(self, value: int) -> None:
        gamma = value / 100.0
        self._gamma_lbl.setText(f"{gamma:.1f}×")
        self.gamma_changed.emit(gamma)
