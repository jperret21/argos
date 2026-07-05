"""HFD History dock — the per-frame focus trend, promoted to its own panel (WS9b).

NINA's HFR History: the HFD of successive frames as a running sparkline so the
observer watches focus drift (temperature, flexure) at a glance. Here it also
overlays the detected #Stars on a twinned right axis — a sudden star drop with a
rising HFD is cloud, a rising HFD with steady stars is defocus.

Promoted out of the focuser dock (which keeps the V-curve): the "Focus quality"
section — trend + HFD / #Stars / Sky read-outs — lives here now. Fed from the
same per-frame metrics path the focuser dock used (``push_metrics``).
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QHBoxLayout, QSizePolicy, QWidget

from argos.ui import design, theme

#: How many recent frames the trend keeps (matches the old focuser sparkline).
_HISTORY = 100


class HfdHistoryDock(design.Card):
    """HFD trend over the last N frames + a #Stars overlay, with a clear button."""

    cleared = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("HFD History", parent)
        self._hfd_hist: list[float] = []
        self._stars_hist: list[int] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        # Trend plot: HFD on the left axis (accent), #Stars on a twinned right
        # axis (muted) so both share the x (frame index) without one flattening
        # the other's scale.
        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG2)
        self._plot.setMinimumHeight(110)
        self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._plot.showGrid(x=False, y=True, alpha=0.2)
        left_axis = self._plot.getAxis("left")
        left_axis.setTextPen(pg.mkPen(theme.ACCENT))
        left_axis.setLabel("HFD (px)")
        self._plot.getAxis("bottom").setTextPen(pg.mkPen(theme.FG_MUTED))
        self._hfd_curve = self._plot.plot(
            pen=pg.mkPen(theme.ACCENT, width=2),
            symbol="o",
            symbolSize=4,
            symbolBrush=theme.ACCENT,
        )

        # Twinned right axis for the #Stars overlay. A second ViewBox shares the
        # x-range of the main plot; a right AxisItem is linked to it.
        self._stars_vb = pg.ViewBox()
        self._plot.scene().addItem(self._stars_vb)
        right_axis = self._plot.getAxis("right")
        self._plot.showAxis("right")
        right_axis.linkToView(self._stars_vb)
        right_axis.setTextPen(pg.mkPen(theme.FG_MUTED))
        right_axis.setLabel("#Stars")
        self._stars_vb.setXLink(self._plot.getViewBox())
        self._plot.getViewBox().sigResized.connect(self._sync_views)
        self._stars_curve = pg.PlotCurveItem(pen=pg.mkPen(theme.FG_MUTED, width=1))
        self._stars_vb.addItem(self._stars_curve)

        outer.addWidget(self._plot, 1)

        # Latest read-outs (moved here from the focuser dock's "Focus quality").
        qual = QFormLayout()
        qual.setHorizontalSpacing(design.SPACING_MD)
        qual.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._hfd_lbl = design.MetricLabel("—")
        self._stars_lbl = design.MetricLabel("—")
        self._sky_lbl = design.MetricLabel("—")
        qual.addRow(design.MutedLabel("HFD"), self._hfd_lbl)
        qual.addRow(design.MutedLabel("Stars"), self._stars_lbl)
        qual.addRow(design.MutedLabel("Sky"), self._sky_lbl)
        outer.addLayout(qual)

        clear_btn = design.SecondaryButton("Clear")
        clear_btn.setToolTip("Reset the HFD / #Stars trend")
        clear_btn.clicked.connect(self.clear_metrics)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(clear_btn)
        outer.addLayout(row)

    def _sync_views(self) -> None:
        """Keep the twinned #Stars ViewBox glued to the main plot's geometry."""
        self._stars_vb.setGeometry(self._plot.getViewBox().sceneBoundingRect())
        self._stars_vb.linkedViewChanged(self._plot.getViewBox(), self._stars_vb.XAxis)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push_metrics(self, metrics) -> None:
        """Append a frame's metrics to the HFD/#Stars trend + the read-outs.

        Mirrors the old ``FocuserDock.push_metrics`` surface so the Imaging page
        wires it in unchanged.
        """
        hfd = metrics.hfd
        if hfd is not None:
            self._hfd_hist.append(float(hfd))
            del self._hfd_hist[:-_HISTORY]
            self._hfd_curve.setData(list(range(len(self._hfd_hist))), self._hfd_hist)
        self._stars_hist.append(int(metrics.star_count))
        del self._stars_hist[:-_HISTORY]
        self._stars_curve.setData(list(range(len(self._stars_hist))), self._stars_hist)
        self._stars_vb.autoRange()

        self._hfd_lbl.setText(f"{hfd:.1f} px" if hfd is not None else "—")
        self._stars_lbl.setText(str(metrics.star_count))
        self._sky_lbl.setText(f"{metrics.sky_adu:.0f}")

    def clear_metrics(self) -> None:
        """Reset the trend and read-outs (e.g. when switching targets)."""
        self._hfd_hist.clear()
        self._stars_hist.clear()
        self._hfd_curve.setData([], [])
        self._stars_curve.setData([], [])
        self._hfd_lbl.setText("—")
        self._stars_lbl.setText("—")
        self._sky_lbl.setText("—")
        self.cleared.emit()
