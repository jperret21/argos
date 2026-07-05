"""Compact HFD V-curve — the canonical autofocus visual.

Plots the sweep samples (HFD against focuser position), the fitted parabola
and its vertex (best focus). Lives inside the FocuserDock so focus is watched
where capture happens; stays verifiable headless through the public
``add_sample`` / ``set_best`` / ``set_samples`` API (mirrors
``AutofocusWorker.step_done`` / ``best_found``).
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from argos.core.imaging.focus import FocusResult, fit_v_curve
from argos.ui import design, theme


class VCurveWidget(QWidget):
    """Sweep samples + fitted parabola + vertex line, rail-tab sized."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: list[tuple[int, float]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(design.SPACING_SM)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG2)
        self._plot.setMinimumHeight(140)
        self._plot.setMaximumHeight(180)
        self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._plot.setLabel("bottom", "Position", units="steps")
        self._plot.setLabel("left", "HFD", units="px")
        self._plot.getAxis("bottom").setTextPen(pg.mkPen(theme.FG_MUTED))
        self._plot.getAxis("left").setTextPen(pg.mkPen(theme.FG_MUTED))

        self._fit_curve = self._plot.plot(pen=pg.mkPen(theme.ACCENT, width=2))
        self._sample_points = pg.ScatterPlotItem(
            size=7, brush=pg.mkBrush(theme.FG), pen=pg.mkPen(theme.BG2)
        )
        self._plot.addItem(self._sample_points)
        self._vertex_line = pg.InfiniteLine(
            angle=90, pen=pg.mkPen(theme.SUCCESS, width=1, style=Qt.PenStyle.DashLine)
        )
        self._vertex_line.hide()
        self._plot.addItem(self._vertex_line)
        layout.addWidget(self._plot)

        self._summary = QLabel("")
        self._summary.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent;"
        )
        layout.addWidget(self._summary)

        self._redraw()

    # ------------------------------------------------------------------
    # Public API (mirrors the AutofocusWorker signals)
    # ------------------------------------------------------------------

    def add_sample(self, position: int, hfd: object) -> None:
        """Append one live sweep sample."""
        if hfd is not None:
            self._samples.append((int(position), float(hfd)))
        self._redraw()

    def set_best(self, position: int, hfd: object) -> None:
        """Mark the final best position reported by the sweep."""
        self._redraw()
        hfd_txt = f"{float(hfd):.2f} px" if hfd is not None else "—"
        self._summary.setText(f"Best focus  {hfd_txt} at {int(position):,}")
        self._summary.setStyleSheet(
            f"color:{theme.SUCCESS}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent;"
        )

    def set_samples(self, measurements: list[tuple[int, float]]) -> None:
        """Replace all samples at once (e.g. re-display a finished sweep)."""
        self._samples = [(int(p), float(h)) for p, h in measurements]
        self._redraw()

    def start_sweep(self) -> None:
        """A new sweep begins — drop the previous curve."""
        self._samples.clear()
        self._summary.setText("")
        self._summary.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent;"
        )
        self._redraw()

    def clear(self) -> None:
        self.start_sweep()

    def result(self) -> FocusResult:
        """The current fit of the collected samples (for tests / read-back)."""
        return fit_v_curve(self._samples)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _redraw(self) -> None:
        if self._samples:
            xs = [p for p, _ in self._samples]
            ys = [h for _, h in self._samples]
            self._sample_points.setData(xs, ys)
        else:
            self._sample_points.setData([], [])

        result = fit_v_curve(self._samples)
        fx, fy = result.fit_curve()
        self._fit_curve.setData(fx, fy)

        if result.method == "none":
            self._vertex_line.hide()
            return
        if result.is_reliable:
            self._vertex_line.setValue(result.best_position)
            self._vertex_line.show()
        else:
            self._vertex_line.hide()
