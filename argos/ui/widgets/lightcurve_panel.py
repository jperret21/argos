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
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QLabel, QSplitter, QVBoxLayout, QWidget

from argos.ui import theme

_PALETTE = (theme.SUCCESS, theme.CYAN, theme.WARNING, theme.VARIABLE, theme.ACCENT, theme.DANGER)


class LightCurvePanel(QWidget):
    """Two X-linked plots for science curves and comparison diagnostics."""

    point_hovered = pyqtSignal(str, float, float, float)
    point_clicked = pyqtSignal(str, float, float, float)

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
        self._relative_flux = QCheckBox("Relative flux")
        self._relative_flux.setToolTip(
            "Median-normalised live preview; final normalisation and detrending belong to post-processing"
        )
        self._relative_flux.toggled.connect(self._set_relative_flux)
        layout.addWidget(self._relative_flux, 0, Qt.AlignmentFlag.AlignRight)

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
        relative_flux: float | None = None,
        relative_flux_err: float | None = None,
    ) -> None:
        """Append a point to its scientific or comparison-diagnostic plot."""
        if not np.isfinite(jd) or not (np.isfinite(mag) or np.isfinite(relative_flux)):
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
                "flux": [],
                "flux_err": [],
                "sat_jd": [],
                "sat_mag": [],
                "sat_flux": [],
                "curve": curve,
                "errbar": errbar,
                "sat": sat,
                "role": role,
                "plot": plot,
            }
            curve.sigPointsHovered.connect(
                lambda _curve, points, _event, series=name: self._emit_point_event(
                    self.point_hovered, series, points
                )
            )
            curve.sigPointsClicked.connect(
                lambda _curve, points, _event, series=name: self._emit_point_event(
                    self.point_clicked, series, points
                )
            )
            self._series[name] = s

        safe_err = float(err or 0.0)
        if not np.isfinite(safe_err) or safe_err < 0:
            safe_err = 0.0
        s["jd"].append(float(jd))
        s["mag"].append(float(mag))
        s["err"].append(safe_err)
        s["flux"].append(float(relative_flux) if relative_flux is not None else float("nan"))
        flux_err = float(relative_flux_err or 0.0)
        s["flux_err"].append(flux_err if np.isfinite(flux_err) and flux_err >= 0 else 0.0)
        if saturated:
            s["sat_jd"].append(float(jd))
            s["sat_mag"].append(float(mag))
            s["sat_flux"].append(
                float(relative_flux) if relative_flux is not None else float("nan")
            )
        self._refresh_series(name)

    def _refresh_series(self, name: str) -> None:
        """Refresh one series and restore its error-bar visibility.

        ``ErrorBarItem.setData`` makes the item visible in pyqtgraph 0.13,
        so visibility must be applied *after* it. This used to leak hidden
        comparison error bars into the target plot's auto-range.
        """
        s = self._series[name]
        x = np.asarray(s["jd"], dtype=float)
        flux_mode = self._relative_flux.isChecked()
        y = np.asarray(s["flux" if flux_mode else "mag"], dtype=float)
        e = np.asarray(s["flux_err" if flux_mode else "err"], dtype=float)
        sat_y = np.asarray(s["sat_flux" if flux_mode else "sat_mag"], dtype=float)
        finite = np.isfinite(y)
        if not finite.any():
            s["curve"].setData([], [])
            s["errbar"].setData(x=np.array([]), y=np.array([]))
            s["sat"].setData([], [])
            return
        if flux_mode:
            baseline = float(np.median(y[finite]))
            if baseline <= 0:
                return
            y, e, sat_y = y / baseline, e / baseline, sat_y / baseline
            if s["role"] == "comparison":
                y, sat_y = y - 1.0, sat_y - 1.0
        elif s["role"] == "comparison":
            baseline = float(np.median(y[finite]))
            y = y - baseline
            sat_y = sat_y - baseline
        s["curve"].setData(x, y, data=[{"err": value} for value in e])
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
                self.add_point(
                    label,
                    p.jd_utc,
                    p.mag,
                    p.mag_err,
                    saturated=p.saturated,
                    role=role,
                    relative_flux=p.relative_flux,
                    relative_flux_err=p.relative_flux_err,
                )
        self._auto_range()

    def has_data(self) -> bool:
        return any(s["jd"] for s in self._series.values())

    def clear(self) -> None:
        for s in self._series.values():
            for item_key in ("errbar", "curve", "sat"):
                s["plot"].removeItem(s[item_key])
        self._series = {}

    @staticmethod
    def _emit_point_event(signal, name: str, points) -> None:
        if not points:
            return
        point = points[0]
        data = point.data() or {}
        signal.emit(
            name, float(point.pos().x()), float(point.pos().y()), float(data.get("err", 0.0))
        )

    # ------------------------------------------------------------------
    # View state
    # ------------------------------------------------------------------

    def _apply_error_visibility(self, visible: bool) -> None:
        for s in self._series.values():
            s["errbar"].setVisible(bool(visible))

    def _set_relative_flux(self, enabled: bool) -> None:
        self._target_plot.setLabel(
            "left", "Relative flux (median-normalised)" if enabled else "Differential mag"
        )
        self._comparison_plot.setLabel(
            "left", "Δ relative flux" if enabled else "Δmag from own median"
        )
        self._target_plot.getViewBox().invertY(not enabled)
        self._comparison_plot.getViewBox().invertY(not enabled)
        for name in self._series:
            self._refresh_series(name)
        self._auto_range()

    def _auto_range(self) -> None:
        for plot in (self._target_plot, self._comparison_plot):
            plot.getViewBox().autoRange()
