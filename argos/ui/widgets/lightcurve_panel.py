"""Live differential light-curve plot (docs/photometry_plan.md §6 C5).

One series per target: points + error bars, magnitude axis inverted (brighter at
top), X = JD (UTC). Fed a point at a time from the page as solved frames arrive.
Saturated points are ringed distinctly (× marker) so a busted sub is obvious;
this same panel class backs the live dock and the detachable window.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from argos.ui import theme

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

    def add_point(
        self, name: str, jd: float, mag: float, err: float, saturated: bool = False
    ) -> None:
        s = self._series.get(name)
        if s is None:
            color = _PALETTE[len(self._series) % len(_PALETTE)]
            curve = self._plot.plot(
                [],
                [],
                pen=None,
                symbol="o",
                symbolSize=6,
                symbolBrush=color,
                symbolPen=color,
                name=name,
            )
            errbar = pg.ErrorBarItem(
                x=np.array([]), y=np.array([]), pen=pg.mkPen(color, width=1), beam=0.0
            )
            self._plot.addItem(errbar)
            # Saturated overlay: red ×, drawn on top so a bad sub stands out.
            sat = self._plot.plot(
                [],
                [],
                pen=None,
                symbol="x",
                symbolSize=11,
                symbolBrush=theme.DANGER,
                symbolPen=pg.mkPen(theme.DANGER, width=2),
            )
            s = {
                "jd": [],
                "mag": [],
                "err": [],
                "sat_jd": [],
                "sat_mag": [],
                "color": color,
                "curve": curve,
                "errbar": errbar,
                "sat": sat,
            }
            self._series[name] = s
        s["jd"].append(float(jd))
        s["mag"].append(float(mag))
        s["err"].append(float(err or 0.0))
        if saturated:
            s["sat_jd"].append(float(jd))
            s["sat_mag"].append(float(mag))
        x, y, e = np.array(s["jd"]), np.array(s["mag"]), np.array(s["err"])
        s["curve"].setData(x, y)
        s["errbar"].setData(x=x, y=y, top=e, bottom=e, beam=0.0)
        s["sat"].setData(np.array(s["sat_jd"]), np.array(s["sat_mag"]))

    def has_data(self) -> bool:
        return any(s["jd"] for s in self._series.values())

    def clear(self) -> None:
        for s in self._series.values():
            self._plot.removeItem(s["errbar"])
            self._plot.removeItem(s["curve"])
            self._plot.removeItem(s["sat"])
        self._series = {}
