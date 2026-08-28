"""Offline quality plots for a finished Argos observing session."""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from argos.core.session.review import ReviewedSession
from argos.ui import theme

_METRICS = (
    ("fwhm", "FWHM (green px)"),
    ("hfd", "HFD (green px)"),
    ("ccd_temp", "Sensor temperature (°C)"),
    ("sky_adu", "Sky background (ADU)"),
    ("star_count", "Star count"),
    ("eccentricity", "Eccentricity"),
)


class SessionQualityPlot(QWidget):
    """One metric selector over complete, persisted session samples."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Quality trend"))
        self._metric = QComboBox()
        for key, label in _METRICS:
            self._metric.addItem(label, key)
        self._metric.currentIndexChanged.connect(self._refresh)
        row.addWidget(self._metric)
        row.addStretch(1)
        layout.addLayout(row)
        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG2)
        self._plot.setLabel("bottom", "Elapsed time (h)")
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._curve = self._plot.plot(
            pen=pg.mkPen(theme.ACCENT, width=2), symbol="o", symbolSize=5, symbolBrush=theme.ACCENT
        )
        layout.addWidget(self._plot, 1)
        self._review: ReviewedSession | None = None

    def set_session(self, review: ReviewedSession) -> None:
        self._review = review
        self._refresh()

    def _refresh(self) -> None:
        key = str(self._metric.currentData() or "fwhm")
        label = self._metric.currentText()
        xs, ys = [], []
        if self._review is not None:
            for elapsed, frame in self._review.metric_samples():
                value = getattr(frame, key, None)
                if value is not None:
                    xs.append(elapsed / 3600.0)
                    ys.append(value)
        self._plot.setLabel("left", label)
        self._curve.setData(xs, ys)
