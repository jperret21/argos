"""Live differential light-curve plot (docs/photometry_plan.md §6 C5).

One series per measured star: points + error bars, magnitude axis inverted
(brighter at top), X = JD (UTC). Fed a point at a time from the page as solved
frames arrive, or all at once via :meth:`set_curves`; this same panel class
backs the live dock and the detachable window, so both always render the same
store the same way.

A "Show" selector filters the plot: **All targets** (default — the science
curves only) or any single star, including check stars (``K ·``) and the
leave-one-out comparison vetting curves (``C ·``).
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from argos.ui import theme

_PALETTE = (theme.SUCCESS, theme.CYAN, theme.WARNING, theme.VARIABLE, theme.ACCENT, theme.DANGER)

_ALL_TARGETS = "All targets"
#: Quiet role prefixes for the selector (targets stay unprefixed).
_ROLE_PREFIX = {"check": "K · ", "comparison": "C · "}


class LightCurvePanel(QWidget):
    """A pyqtgraph plot of differential magnitude vs JD, with error bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        selector_row = QHBoxLayout()
        selector_row.setContentsMargins(4, 2, 4, 0)
        show_lbl = QLabel("Show:")
        show_lbl.setStyleSheet(
            f"color: {theme.FG_MUTED}; font-size: 11px; background: transparent;"
        )
        selector_row.addWidget(show_lbl)
        self._selector = QComboBox()
        self._selector.setStyleSheet("font-size: 11px;")
        self._selector.addItem(_ALL_TARGETS, None)
        self._selector.currentIndexChanged.connect(lambda _i: self._apply_visibility())
        selector_row.addWidget(self._selector)
        selector_row.addStretch()
        layout.addLayout(selector_row)

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

    # ------------------------------------------------------------------
    # Feeding
    # ------------------------------------------------------------------

    def add_point(
        self,
        name: str,
        jd: float,
        mag: float,
        err: float,
        saturated: bool = False,
        role: str = "target",
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
                "role": role,
            }
            self._series[name] = s
            self._selector_add(name, role)
            self._apply_series_visibility(name)
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

    def set_curves(self, curves: dict) -> None:
        """Replace the plot with ``key → LightCurve`` (the engine's store).

        The one rendering path shared by the dock and the window: clear, then
        replay every point. Keeps the current Show selection when the star
        still exists (a store refresh must not yank the user's focus).
        """
        selected = self._selector.currentText()
        self.clear()
        for lc in curves.values():
            label = lc.name or lc.auid or "TARGET"
            role = getattr(lc, "role", "target")
            for p in lc.points:
                self.add_point(
                    label, p.jd_utc, p.mag, p.mag_err, saturated=p.saturated, role=role
                )
        idx = self._selector.findText(selected)
        if idx >= 0:
            self._selector.setCurrentIndex(idx)

    def has_data(self) -> bool:
        return any(s["jd"] for s in self._series.values())

    def clear(self) -> None:
        for s in self._series.values():
            self._plot.removeItem(s["errbar"])
            self._plot.removeItem(s["curve"])
            self._plot.removeItem(s["sat"])
        self._series = {}
        self._selector.blockSignals(True)
        self._selector.clear()
        self._selector.addItem(_ALL_TARGETS, None)
        self._selector.setCurrentIndex(0)
        self._selector.blockSignals(False)

    # ------------------------------------------------------------------
    # Show selector
    # ------------------------------------------------------------------

    def _selector_add(self, name: str, role: str) -> None:
        label = _ROLE_PREFIX.get(role, "") + name
        self._selector.blockSignals(True)
        self._selector.addItem(label, name)
        self._selector.blockSignals(False)

    def _selected_name(self) -> str | None:
        """The chosen series name, or ``None`` for the All-targets view."""
        return self._selector.currentData()

    def _apply_visibility(self) -> None:
        for name in self._series:
            self._apply_series_visibility(name)

    def _apply_series_visibility(self, name: str) -> None:
        s = self._series[name]
        chosen = self._selected_name()
        visible = (name == chosen) if chosen else (s["role"] == "target")
        for item_key in ("curve", "errbar", "sat"):
            s[item_key].setVisible(visible)
