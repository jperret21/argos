"""Live differential light-curve plot (docs/photometry_plan.md §6 C5).

One series per target: points + error bars, magnitude axis inverted (brighter at
top), X = JD (UTC). Fed a point at a time from the page as solved frames arrive.
"""

from __future__ import annotations

import csv

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from seercontrol.ui import theme

_PALETTE = (theme.SUCCESS, theme.CYAN, theme.WARNING, theme.VARIABLE, theme.ACCENT, theme.DANGER)


class LightCurvePanel(QWidget):
    """A pyqtgraph plot of differential magnitude vs JD, with error bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plot = pg.PlotWidget()
        self._plot.setMenuEnabled(False)  # no link-axis menu (avoids pg global state)
        self._plot.setBackground(theme.BG2)
        self._plot.setLabel("left", "mag (differential)")
        self._plot.setLabel("bottom", "JD (UTC)")
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._plot.getViewBox().invertY(True)  # brighter magnitudes at the top
        self._plot.addLegend()
        layout.addWidget(self._plot)
        self._series: dict[str, dict] = {}

    def add_point(self, name: str, jd: float, mag: float, err: float, saturated: bool = False) -> None:
        s = self._series.get(name)
        if s is None:
            color = _PALETTE[len(self._series) % len(_PALETTE)]
            curve = self._plot.plot(
                [], [], pen=None, symbol="o", symbolSize=6, symbolBrush=color,
                symbolPen=color, name=name,
            )
            errbar = pg.ErrorBarItem(
                x=np.array([]), y=np.array([]), pen=pg.mkPen(color, width=1), beam=0.0
            )
            self._plot.addItem(errbar)
            s = {"jd": [], "mag": [], "err": [], "curve": curve, "errbar": errbar}
            self._series[name] = s
        s["jd"].append(float(jd))
        s["mag"].append(float(mag))
        s["err"].append(float(err or 0.0))
        x, y, e = np.array(s["jd"]), np.array(s["mag"]), np.array(s["err"])
        s["curve"].setData(x, y)
        s["errbar"].setData(x=x, y=y, top=e, bottom=e, beam=0.0)

    def has_data(self) -> bool:
        return any(s["jd"] for s in self._series.values())

    def clear(self) -> None:
        for s in self._series.values():
            self._plot.removeItem(s["errbar"])
            self._plot.removeItem(s["curve"])
        self._series = {}

    def export_csv(self, path) -> None:
        """Write every series to one CSV (target, jd_utc, mag, mag_err)."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["target", "jd_utc", "mag", "mag_err"])
            for name, s in self._series.items():
                for jd, mag, err in zip(s["jd"], s["mag"], s["err"]):
                    w.writerow([name, jd, mag, err])
