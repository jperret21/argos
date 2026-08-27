"""Live differential-photometry plots.

The scientific target/check light curves and the comparison-star diagnostics
serve different jobs. They deliberately live in separate, X-linked plots:
the target keeps its calibrated magnitude scale while each comparison is
shown as a residual about its own median. This prevents an ensemble spanning
several magnitudes from making the science curve unreadable.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QLabel, QSplitter, QVBoxLayout, QWidget

from argos.ui import theme

_PALETTE = (theme.SUCCESS, theme.CYAN, theme.WARNING, theme.VARIABLE, theme.ACCENT, theme.DANGER)


class LightCurvePanel(QWidget):
    """Two X-linked plots for science curves and comparison diagnostics."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QLabel("Target and check star")
        header.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:12px; font-weight:600; "
            "background:transparent; padding:2px 4px;"
        )
        layout.addWidget(header)

        self._target_plot = self._make_plot("Differential mag", "Time (JD UTC)")
        self._comparison_plot = self._make_plot("Δmag from own median", "Time (JD UTC)")
        self._comparison_plot.setXLink(self._target_plot)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._target_plot)
        splitter.addWidget(self._comparison_plot)
        splitter.setSizes([260, 150])
        layout.addWidget(splitter, 1)

        self._errors = QCheckBox("Show uncertainties")
        self._errors.setChecked(True)
        self._errors.setToolTip("Show the per-image photometric uncertainty")
        self._errors.toggled.connect(self._apply_error_visibility)
        layout.addWidget(self._errors, 0, Qt.AlignmentFlag.AlignRight)

        self._series: dict[str, dict] = {}

    @staticmethod
    def _make_plot(left_label: str, bottom_label: str) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.setMenuEnabled(False)
        plot.setBackground(theme.BG2)
        plot.setLabel("left", left_label)
        plot.setLabel("bottom", bottom_label)
        plot.showGrid(x=True, y=True, alpha=0.2)
        plot.getViewBox().invertY(True)
        plot.addLegend()
        return plot

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
        """Append a point to its scientific or comparison-diagnostic plot."""
        if not (np.isfinite(jd) and np.isfinite(mag)):
            return
        s = self._series.get(name)
        if s is None:
            color = _PALETTE[len(self._series) % len(_PALETTE)]
            comparison = role == "comparison"
            plot = self._comparison_plot if comparison else self._target_plot
            curve = plot.plot(
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
                x=np.array([]), y=np.array([]), pen=pg.mkPen(color, width=1), beam=3.0
            )
            plot.addItem(errbar)
            sat = plot.plot(
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
                "curve": curve,
                "errbar": errbar,
                "sat": sat,
                "role": role,
                "plot": plot,
            }
            self._series[name] = s

        safe_err = float(err or 0.0)
        if not np.isfinite(safe_err) or safe_err < 0:
            safe_err = 0.0
        s["jd"].append(float(jd))
        s["mag"].append(float(mag))
        s["err"].append(safe_err)
        if saturated:
            s["sat_jd"].append(float(jd))
            s["sat_mag"].append(float(mag))
        self._refresh_series(name)

    def _refresh_series(self, name: str) -> None:
        """Refresh one series and restore its error-bar visibility.

        ``ErrorBarItem.setData`` makes the item visible in pyqtgraph 0.13,
        so visibility must be applied *after* it. This used to leak hidden
        comparison error bars into the target plot's auto-range.
        """
        s = self._series[name]
        x = np.asarray(s["jd"], dtype=float)
        y = np.asarray(s["mag"], dtype=float)
        sat_y = np.asarray(s["sat_mag"], dtype=float)
        if s["role"] == "comparison" and y.size:
            baseline = float(np.median(y))
            y = y - baseline
            sat_y = sat_y - baseline
        e = np.asarray(s["err"], dtype=float)
        s["curve"].setData(x, y)
        s["errbar"].setData(x=x, y=y, top=e, bottom=e, beam=3.0)
        s["sat"].setData(np.asarray(s["sat_jd"], dtype=float), sat_y)
        s["errbar"].setVisible(self._errors.isChecked())

    def set_curves(self, curves: dict) -> None:
        """Replace the plots with ``key → LightCurve`` from the engine store."""
        self.clear()
        for lc in curves.values():
            label = lc.name or lc.auid or "TARGET"
            role = getattr(lc, "role", "target")
            for p in lc.points:
                self.add_point(label, p.jd_utc, p.mag, p.mag_err, saturated=p.saturated, role=role)
        self._auto_range()

    def has_data(self) -> bool:
        return any(s["jd"] for s in self._series.values())

    def clear(self) -> None:
        for s in self._series.values():
            for item_key in ("errbar", "curve", "sat"):
                s["plot"].removeItem(s[item_key])
        self._series = {}

    # ------------------------------------------------------------------
    # View state
    # ------------------------------------------------------------------

    def _apply_error_visibility(self, visible: bool) -> None:
        for s in self._series.values():
            s["errbar"].setVisible(bool(visible))

    def _auto_range(self) -> None:
        for plot in (self._target_plot, self._comparison_plot):
            plot.getViewBox().autoRange()
