"""Analysis panel — histogram, image statistics, and display stretch controls.

Right-dock panel that receives raw frames, computes a live histogram and
pixel statistics, and lets the user adjust black/white point + gamma.
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from seercontrol.ui import theme

logger = logging.getLogger(__name__)

_HIST_BINS = 256
_HIST_COLOR = theme.ACCENT + "90"   # semi-transparent fill


class AnalysisPanel(QWidget):
    """Image analysis panel with live histogram and stretch controls.

    Signals:
        levels_changed:         (black, white) in pixel units (0–65535).
        gamma_changed:          Gamma exponent float.
        channel_changed:        Channel name string for CapturePanel.
        auto_stretch_requested: Request viewer to auto-stretch.
    """

    levels_changed        = pyqtSignal(float, float)
    gamma_changed         = pyqtSignal(float)
    channel_changed       = pyqtSignal(str)
    auto_stretch_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_arr: np.ndarray | None = None
        self._black: float = 0.0
        self._white: float = 65535.0
        self._build_ui()
        self.setMinimumWidth(220)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._build_histogram_group())
        root.addWidget(self._build_stats_group())
        root.addWidget(self._build_display_group())
        root.addStretch()

    def _build_histogram_group(self) -> QGroupBox:
        group = QGroupBox("Histogram")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(0)

        pg.setConfigOptions(antialias=True)
        self._hist_plot = pg.PlotWidget()
        self._hist_plot.setBackground(theme.SURFACE_1)
        self._hist_plot.setMinimumHeight(120)
        self._hist_plot.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._hist_plot.showGrid(x=False, y=False)
        self._hist_plot.getAxis("left").hide()
        bottom = self._hist_plot.getAxis("bottom")
        bottom.setTextPen(pg.mkPen(theme.TEXT_MUTED))
        bottom.setPen(pg.mkPen(theme.SURFACE_4))

        self._hist_bars = pg.BarGraphItem(
            x=np.linspace(0, 65535, _HIST_BINS),
            height=np.zeros(_HIST_BINS),
            width=65535 / _HIST_BINS,
            brush=pg.mkBrush(_HIST_COLOR),
            pen=pg.mkPen(None),
        )
        self._hist_plot.addItem(self._hist_bars)

        # Black/white markers on the histogram
        self._black_line = pg.InfiniteLine(
            pos=0, angle=90,
            pen=pg.mkPen(theme.ACCENT, width=1, style=Qt.PenStyle.DashLine),
            label="B", labelOpts={"color": theme.ACCENT, "fill": theme.SURFACE_1},
        )
        self._white_line = pg.InfiniteLine(
            pos=65535, angle=90,
            pen=pg.mkPen(theme.WARNING, width=1, style=Qt.PenStyle.DashLine),
            label="W", labelOpts={"color": theme.WARNING, "fill": theme.SURFACE_1},
        )
        self._hist_plot.addItem(self._black_line)
        self._hist_plot.addItem(self._white_line)

        layout.addWidget(self._hist_plot)
        return group

    def _build_stats_group(self) -> QGroupBox:
        group = QGroupBox("Statistics")
        form = QFormLayout(group)
        form.setContentsMargins(8, 12, 8, 8)
        form.setSpacing(4)

        self._min_lbl    = _val_label("—")
        self._max_lbl    = _val_label("—")
        self._mean_lbl   = _val_label("—")
        self._median_lbl = _val_label("—")
        self._std_lbl    = _val_label("—")

        form.addRow(_key("Min"), self._min_lbl)
        form.addRow(_key("Max"), self._max_lbl)
        form.addRow(_key("Mean"), self._mean_lbl)
        form.addRow(_key("Median"), self._median_lbl)
        form.addRow(_key("StdDev"), self._std_lbl)

        return group

    def _build_display_group(self) -> QGroupBox:
        group = QGroupBox("Display")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        # Channel
        ch_row = QHBoxLayout()
        ch_row.addWidget(_key("Channel"))
        self._channel_combo = QComboBox()
        for ch in ["Raw", "R", "G", "B", "RGB"]:
            self._channel_combo.addItem(ch)
        self._channel_combo.currentTextChanged.connect(self.channel_changed)
        ch_row.addWidget(self._channel_combo)
        layout.addLayout(ch_row)

        # Auto-stretch button
        self._auto_btn = QPushButton("☀  Auto Stretch")
        self._auto_btn.clicked.connect(self.auto_stretch_requested)
        layout.addWidget(self._auto_btn)

        # Black point
        black_row = QHBoxLayout()
        black_row.addWidget(_key("Black"))
        self._black_slider = QSlider(Qt.Orientation.Horizontal)
        self._black_slider.setRange(0, 65535)
        self._black_slider.setValue(0)
        self._black_slider.valueChanged.connect(self._on_black_changed)
        self._black_lbl = QLabel("0")
        self._black_lbl.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:10px; min-width:38px;"
        )
        black_row.addWidget(self._black_slider)
        black_row.addWidget(self._black_lbl)
        layout.addLayout(black_row)

        # White point
        white_row = QHBoxLayout()
        white_row.addWidget(_key("White"))
        self._white_slider = QSlider(Qt.Orientation.Horizontal)
        self._white_slider.setRange(0, 65535)
        self._white_slider.setValue(65535)
        self._white_slider.valueChanged.connect(self._on_white_changed)
        self._white_lbl = QLabel("65535")
        self._white_lbl.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:10px; min-width:38px;"
        )
        white_row.addWidget(self._white_slider)
        white_row.addWidget(self._white_lbl)
        layout.addLayout(white_row)

        # Gamma
        gamma_row = QHBoxLayout()
        gamma_row.addWidget(_key("Gamma"))
        self._gamma_slider = QSlider(Qt.Orientation.Horizontal)
        self._gamma_slider.setRange(10, 300)
        self._gamma_slider.setValue(100)
        self._gamma_slider.valueChanged.connect(self._on_gamma_changed)
        self._gamma_lbl = QLabel("1.0×")
        self._gamma_lbl.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:10px; min-width:38px;"
        )
        gamma_row.addWidget(self._gamma_slider)
        gamma_row.addWidget(self._gamma_lbl)
        layout.addLayout(gamma_row)

        return group

    # ------------------------------------------------------------------
    # Public slot — receives frames from CapturePanel
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def update_frame(self, arr: np.ndarray) -> None:
        """Update histogram and statistics from a new frame."""
        self._last_arr = arr

        # Use grayscale for stats — green channel for RGB, direct for mono
        if arr.ndim == 3:
            flat = arr[:, :, 1].ravel().astype(np.float32)
            hist_range = (0, 255)
        else:
            flat = arr.ravel().astype(np.float32)
            hist_range = (0, 65535)

        # Histogram
        hist, edges = np.histogram(flat, bins=_HIST_BINS, range=hist_range)
        self._hist_bars.setOpts(
            x=edges[:-1],
            height=hist.astype(float),
            width=float(edges[1] - edges[0]),
        )

        # Stats (use subsample for speed on large frames)
        sample = flat[::4] if len(flat) > 1_000_000 else flat
        self._min_lbl.setText(f"{int(sample.min()):,}")
        self._max_lbl.setText(f"{int(sample.max()):,}")
        self._mean_lbl.setText(f"{sample.mean():.0f}")
        self._median_lbl.setText(f"{float(np.median(sample)):.0f}")
        self._std_lbl.setText(f"{sample.std():.0f}")

    # ------------------------------------------------------------------
    # Slider callbacks
    # ------------------------------------------------------------------

    def _on_black_changed(self, value: int) -> None:
        self._black = float(value)
        self._black_lbl.setText(str(value))
        self._black_line.setValue(value)
        if self._black < self._white:
            self.levels_changed.emit(self._black, self._white)

    def _on_white_changed(self, value: int) -> None:
        self._white = float(value)
        self._white_lbl.setText(str(value))
        self._white_line.setValue(value)
        if self._black < self._white:
            self.levels_changed.emit(self._black, self._white)

    def _on_gamma_changed(self, value: int) -> None:
        gamma = value / 100.0
        self._gamma_lbl.setText(f"{gamma:.1f}×")
        self.gamma_changed.emit(gamma)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _key(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
    return lbl


def _val_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.ACCENT}; font-size:11px; font-family:{theme.FONT_MONO};"
    )
    return lbl
