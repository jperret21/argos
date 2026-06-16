"""Session metrics over time (docs/photometry_plan.md §6 C6).

A single plot with a metric selector — sensor temperature, airmass, sky level,
FWHM, HFD, star count vs elapsed time. Each series stores its own samples (fed at
whatever cadence is available), so a missing value simply doesn't extend its line.
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from seercontrol.ui import theme

#: (key, axis label) — order = combo order.
_METRICS = (
    ("airmass", "Airmass"),
    ("fwhm", "FWHM (green px)"),
    ("sky", "Sky (ADU)"),
    ("hfd", "HFD (green px)"),
    ("stars", "Star count"),
    ("temp", "Sensor temp (°C)"),
)


class MetricsPanel(QWidget):
    """Pick a metric; plot its samples vs elapsed time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        lbl = QLabel("Metric:")
        lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")
        row.addWidget(lbl)
        self._combo = QComboBox()
        for _key, label in _METRICS:
            self._combo.addItem(label)
        self._combo.currentIndexChanged.connect(self._refresh)
        row.addWidget(self._combo)
        row.addStretch()
        layout.addLayout(row)

        self._plot = pg.PlotWidget()
        self._plot.setMenuEnabled(False)  # no link-axis menu (avoids pg global state)
        self._plot.setBackground(theme.BG2)
        self._plot.setLabel("bottom", "elapsed (s)")
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._curve = self._plot.plot([], [], pen=pg.mkPen(theme.SUCCESS, width=2),
                                      symbol="o", symbolSize=4, symbolBrush=theme.SUCCESS)
        layout.addWidget(self._plot)
        self._data: dict[str, tuple[list, list]] = {}

    def add_sample(self, t: float, **values) -> None:
        """Append ``key=value`` samples at time ``t`` (None values are skipped)."""
        for key, value in values.items():
            if value is None:
                continue
            xs, ys = self._data.setdefault(key, ([], []))
            xs.append(float(t))
            ys.append(float(value))
        self._refresh()

    def _refresh(self) -> None:
        key, label = _METRICS[self._combo.currentIndex()]
        xs, ys = self._data.get(key, ([], []))
        self._plot.setLabel("left", label)
        self._curve.setData(xs, ys)

    def clear(self) -> None:
        self._data = {}
        self._refresh()
