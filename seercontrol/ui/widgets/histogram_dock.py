"""Display panel — per-channel histogram, stretch controls, measurement readouts.

The control surface for the display pipeline (capture_panel.md §3/§4). It owns
nothing about the data: it shows per-channel (R/G/B) histograms of the raw CFA,
drives the viewer's stretch (black/white/midtones + linear/log/asinh), and shows
the pixel readout + ROI region stats coming back from the viewer.

Signals:
    stretch_changed(black, white, midtones, mode)
    auto_requested()
    saturation_toggled(bool)
    roi_toggled(bool)
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QSizePolicy,
    QSlider,
    QWidget,
)

from seercontrol.core.imaging.stretch import STRETCH_MODES, channel_histograms
from seercontrol.ui import design, theme

logger = logging.getLogger(__name__)

_HIST_BINS = 128
_MAX_ADU = 65535


class HistogramDock(design.Card):
    """Per-channel histogram + stretch + measurement readouts (the Display tab)."""

    stretch_changed = pyqtSignal(float, float, float, str)  # black, white, midtones, mode
    auto_requested = pyqtSignal()
    saturation_toggled = pyqtSignal(bool)
    roi_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Display", parent)
        self._guard = False
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        pg.setConfigOptions(antialias=True)
        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG2)
        self._plot.setMinimumHeight(120)
        self._plot.setMaximumHeight(180)
        self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._plot.showGrid(x=False, y=False)
        self._plot.getAxis("left").hide()
        bottom = self._plot.getAxis("bottom")
        bottom.setTextPen(pg.mkPen(theme.FG_MUTED))
        bottom.setPen(pg.mkPen(theme.BORDER))
        self._r_curve = self._plot.plot(pen=pg.mkPen(theme.DANGER, width=1))
        self._g_curve = self._plot.plot(pen=pg.mkPen(theme.SUCCESS, width=1))
        self._b_curve = self._plot.plot(pen=pg.mkPen(theme.ACCENT, width=1))
        outer.addWidget(self._plot)

        # Stretch sliders.
        grid = QGridLayout()
        grid.setHorizontalSpacing(design.SPACING_MD)
        grid.setVerticalSpacing(design.SPACING_SM)
        grid.setColumnStretch(1, 1)

        self._black = self._slider(0, _MAX_ADU, 0)
        self._white = self._slider(0, _MAX_ADU, _MAX_ADU)
        self._mid = self._slider(1, 999, 500)
        for r, (label, sld) in enumerate(
            (("Black", self._black), ("White", self._white), ("Midtones", self._mid))
        ):
            grid.addWidget(design.MutedLabel(label), r, 0)
            grid.addWidget(sld, r, 1)
            sld.valueChanged.connect(self._emit_stretch)
        outer.addLayout(grid)

        # Mode + auto.
        mode_form = QFormLayout()
        mode_form.setHorizontalSpacing(design.SPACING_MD)
        mode_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(STRETCH_MODES)
        self._mode_combo.currentTextChanged.connect(lambda _t: self._emit_stretch())
        mode_form.addRow(design.MutedLabel("Stretch"), self._mode_combo)
        outer.addLayout(mode_form)

        self._auto_btn = design.PrimaryButton("Auto-stretch")
        self._auto_btn.clicked.connect(self.auto_requested)
        outer.addLayout(design.button_row(self._auto_btn))

        # Measurement toggles.
        self._sat_chk = QCheckBox("Highlight saturation")
        self._sat_chk.toggled.connect(self.saturation_toggled)
        outer.addWidget(self._sat_chk)
        self._roi_chk = QCheckBox("Region stats (ROI)")
        self._roi_chk.toggled.connect(self.roi_toggled)
        outer.addWidget(self._roi_chk)

        # Readouts.
        self._pixel_lbl = design.MetricLabel("—")
        self._region_lbl = design.MutedLabel("")
        self._region_lbl.setWordWrap(True)
        read = QFormLayout()
        read.setHorizontalSpacing(design.SPACING_MD)
        read.addRow(design.MutedLabel("Pixel"), self._pixel_lbl)
        outer.addLayout(read)
        outer.addWidget(self._region_lbl)

        # Whole-frame stats.
        stats = QFormLayout()
        stats.setHorizontalSpacing(design.SPACING_MD)
        stats.setVerticalSpacing(design.SPACING_XS)
        self._min_lbl = design.MetricLabel("—")
        self._max_lbl = design.MetricLabel("—")
        self._mean_lbl = design.MetricLabel("—")
        self._median_lbl = design.MetricLabel("—")
        for label, widget in (
            ("Min", self._min_lbl),
            ("Max", self._max_lbl),
            ("Mean", self._mean_lbl),
            ("Median", self._median_lbl),
        ):
            stats.addRow(design.MutedLabel(label), widget)
        outer.addLayout(stats)

    @staticmethod
    def _slider(lo: int, hi: int, value: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(value)
        return s

    # ------------------------------------------------------------------
    # Frame → histogram + stats
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def update_frame(self, raw) -> None:
        """Refresh per-channel histograms + whole-frame stats from a raw frame."""
        if raw is None or raw.ndim != 2:
            return
        lo = float(raw.min())
        hi = float(np.percentile(raw, 99.8))
        if hi <= lo:
            hi = float(raw.max()) if float(raw.max()) > lo else lo + 1.0

        # Adapt the black/white slider range to the data so they aren't
        # hyper-sensitive (the whole signal used to sit in <1% of a 0–65535 bar).
        self._guard = True
        self._black.setRange(int(lo), int(hi))
        self._white.setRange(int(lo), int(hi))
        self._guard = False

        centers, rh, gh, bh = channel_histograms(raw, bins=_HIST_BINS, lo=lo, hi=hi)
        self._r_curve.setData(centers, np.log1p(rh))
        self._g_curve.setData(centers, np.log1p(gh))
        self._b_curve.setData(centers, np.log1p(bh))
        self._plot.setXRange(lo, hi, padding=0)

        self._min_lbl.setText(f"{int(raw.min())}")
        self._max_lbl.setText(f"{int(raw.max())}")
        self._mean_lbl.setText(f"{raw.mean():.0f}")
        self._median_lbl.setText(f"{int(np.median(raw))}")

    # ------------------------------------------------------------------
    # Sync from the viewer
    # ------------------------------------------------------------------

    def set_levels(self, black: float, white: float, midtones: float) -> None:
        """Sync the black/white/midtones sliders after an auto-stretch (no re-emit)."""
        self._guard = True
        self._black.setValue(int(black))
        self._white.setValue(int(white))
        self._mid.setValue(int(round(midtones * 1000)))
        self._guard = False

    def set_pixel_info(self, text: str) -> None:
        self._pixel_lbl.setText(text or "—")

    def set_region_info(self, stats) -> None:
        if not stats:
            self._region_lbl.setText("")
            return
        self._region_lbl.setText(
            f"ROI  n={int(stats['n'])}  mean={stats['mean']:.0f}  "
            f"median={stats['median']:.0f}  std={stats['std']:.1f}  "
            f"min={stats['min']:.0f}  max={stats['max']:.0f}"
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _emit_stretch(self) -> None:
        if self._guard:
            return
        self.stretch_changed.emit(
            float(self._black.value()),
            float(self._white.value()),
            self._mid.value() / 1000.0,
            self._mode_combo.currentText(),
        )
