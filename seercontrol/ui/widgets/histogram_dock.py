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
    crosshair_toggled = pyqtSignal(bool)

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
        self._cross_chk = QCheckBox("Crosshair on image")
        self._cross_chk.setChecked(True)  # visible by default
        self._cross_chk.toggled.connect(self.crosshair_toggled)
        outer.addWidget(self._cross_chk)
        self._sat_chk = QCheckBox("Highlight saturation")
        self._sat_chk.toggled.connect(self.saturation_toggled)
        outer.addWidget(self._sat_chk)
        self._roi_chk = QCheckBox("Region stats (drag the box on the image)")
        self._roi_chk.toggled.connect(self.roi_toggled)
        outer.addWidget(self._roi_chk)

        # ROI stats — compact aligned grid (filled while the ROI is active).
        outer.addWidget(design.SectionLabel("ROI stats"))
        rg = QGridLayout()
        rg.setHorizontalSpacing(design.SPACING_MD)
        rg.setVerticalSpacing(design.SPACING_XS)
        rg.setColumnStretch(1, 1)
        rg.setColumnStretch(3, 1)
        self._rg_mean = design.MetricLabel("—")
        self._rg_median = design.MetricLabel("—")
        self._rg_std = design.MetricLabel("—")
        self._rg_min = design.MetricLabel("—")
        self._rg_max = design.MetricLabel("—")
        self._rg_n = design.MetricLabel("—")
        for r, (k1, w1, k2, w2) in enumerate(
            (
                ("Mean", self._rg_mean, "Median", self._rg_median),
                ("Std", self._rg_std, "N", self._rg_n),
                ("Min", self._rg_min, "Max", self._rg_max),
            )
        ):
            rg.addWidget(design.MutedLabel(k1), r, 0)
            rg.addWidget(w1, r, 1)
            rg.addWidget(design.MutedLabel(k2), r, 2)
            rg.addWidget(w2, r, 3)
        outer.addLayout(rg)

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

    def set_region_info(self, stats) -> None:
        if not stats:
            for lbl in (
                self._rg_mean,
                self._rg_median,
                self._rg_std,
                self._rg_min,
                self._rg_max,
                self._rg_n,
            ):
                lbl.setText("—")
            return
        self._rg_mean.setText(f"{stats['mean']:.0f}")
        self._rg_median.setText(f"{stats['median']:.0f}")
        self._rg_std.setText(f"{stats['std']:.1f}")
        self._rg_min.setText(f"{stats['min']:.0f}")
        self._rg_max.setText(f"{stats['max']:.0f}")
        self._rg_n.setText(f"{int(stats['n'])}")

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
