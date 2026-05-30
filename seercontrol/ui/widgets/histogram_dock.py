"""Histogram dock — compact distribution + summary stats for the Imaging mode.

Receives raw frames via :meth:`update_frame` and updates the histogram on a
worker-friendly cadence (each call schedules the calculation, then redraws).
The full ``analysis_panel`` (with stretch sliders, etc.) is reachable in R5
through a "Detailed histogram…" dialog; this dock keeps the right rail thin.
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import (
    QFormLayout,
    QSizePolicy,
    QWidget,
)

from seercontrol.ui import design, theme

logger = logging.getLogger(__name__)

_HIST_BINS = 128


class HistogramDock(design.Card):
    """Histogram + min/max/mean/median compact panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Histogram", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        pg.setConfigOptions(antialias=True)
        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG2)
        # Hard cap — pyqtgraph asks for ~500 px by default which would push
        # the dock past the visible area and stack widgets on top of each
        # other. 130 px keeps the histogram readable without sprawling.
        self._plot.setMinimumHeight(100)
        self._plot.setMaximumHeight(130)
        self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._plot.showGrid(x=False, y=False)
        self._plot.getAxis("left").hide()
        bottom = self._plot.getAxis("bottom")
        bottom.setTextPen(pg.mkPen(theme.FG_MUTED))
        bottom.setPen(pg.mkPen(theme.BORDER))

        self._bars = pg.BarGraphItem(
            x=np.linspace(0, 65535, _HIST_BINS),
            height=np.zeros(_HIST_BINS),
            width=65535 / _HIST_BINS,
            brush=pg.mkBrush(theme.ACCENT + "90"),
            pen=pg.mkPen(None),
        )
        self._plot.addItem(self._bars)
        outer.addWidget(self._plot)

        # Stats — 4 short lines, mono font so columns align across frames.
        stats = QFormLayout()
        stats.setHorizontalSpacing(design.SPACING_MD)
        stats.setVerticalSpacing(design.SPACING_XS)
        self._min_lbl    = design.MetricLabel("—")
        self._max_lbl    = design.MetricLabel("—")
        self._mean_lbl   = design.MetricLabel("—")
        self._median_lbl = design.MetricLabel("—")
        for label, widget in (
            ("Min", self._min_lbl),
            ("Max", self._max_lbl),
            ("Mean", self._mean_lbl),
            ("Median", self._median_lbl),
        ):
            stats.addRow(design.MutedLabel(label), widget)
        outer.addLayout(stats)

    @pyqtSlot(object)
    def update_frame(self, arr) -> None:
        """Compute the histogram for ``arr`` (numpy uint16) and refresh stats."""
        if arr is None or arr.ndim not in (2, 3):
            return
        # Work on a single grayscale-equivalent channel to keep math cheap.
        if arr.ndim == 3:
            arr = arr.mean(axis=2)

        hist, _edges = np.histogram(arr, bins=_HIST_BINS, range=(0, 65535))
        # Log scale visually flattens the long tail; clip + 1 avoids log(0).
        self._bars.setOpts(height=np.log1p(hist))

        self._min_lbl.setText(f"{int(arr.min())}")
        self._max_lbl.setText(f"{int(arr.max())}")
        self._mean_lbl.setText(f"{arr.mean():.0f}")
        self._median_lbl.setText(f"{int(np.median(arr))}")
