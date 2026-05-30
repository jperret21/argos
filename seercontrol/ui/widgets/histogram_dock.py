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
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from seercontrol.ui import theme

logger = logging.getLogger(__name__)

_HIST_BINS = 128


class HistogramDock(QGroupBox):
    """Histogram + min/max/mean/median compact panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Histogram", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 14, 4, 6)
        outer.setSpacing(4)

        pg.setConfigOptions(antialias=True)
        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG2)
        self._plot.setMinimumHeight(110)
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
        stats.setHorizontalSpacing(8)
        stats.setVerticalSpacing(2)
        self._min_lbl    = _stat("—")
        self._max_lbl    = _stat("—")
        self._mean_lbl   = _stat("—")
        self._median_lbl = _stat("—")
        stats.addRow(_key("Min"),    self._min_lbl)
        stats.addRow(_key("Max"),    self._max_lbl)
        stats.addRow(_key("Mean"),   self._mean_lbl)
        stats.addRow(_key("Median"), self._median_lbl)
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


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _key(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:10px; background:transparent;")
    return lbl


def _stat(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.FG}; font-size:11px; font-family:{theme.FONT_MONO};"
        f" background:transparent;"
    )
    return lbl
