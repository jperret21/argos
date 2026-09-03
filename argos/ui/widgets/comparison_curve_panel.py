"""Selectable single-comparison diagnostic for the Review workspace."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from argos.ui import theme
from argos.ui.widgets.lightcurve_panel import LightCurvePanel

_ALL_COMPARISONS = "__all_comparisons__"


class ComparisonCurvePanel(QWidget):
    """One independently selectable comparison-star light curve.

    A session can contain several comparison stars.  Keeping one selector per
    plot lets an observer display any subset simultaneously, each on its own
    stable diagnostic scale.
    """

    point_hovered = pyqtSignal(str, float, float, float)
    point_clicked = pyqtSignal(str, float, float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._curves: dict = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        row = QHBoxLayout()
        label = QLabel("Comparison star")
        label.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:12px; font-weight:600; background:transparent;"
        )
        row.addWidget(label)
        self._selector = QComboBox()
        self._selector.setToolTip("Choose the comparison star shown in this diagnostic")
        self._selector.currentIndexChanged.connect(self._refresh_plot)
        row.addWidget(self._selector, 1)
        layout.addLayout(row)

        self._plot = LightCurvePanel(view="comparison")
        self._plot.point_hovered.connect(self.point_hovered.emit)
        self._plot.point_clicked.connect(self.point_clicked.emit)
        layout.addWidget(self._plot, 1)

    def selected_key(self) -> str:
        return str(self._selector.currentData() or "")

    def set_curves(self, curves: dict, *, preferred_key: str = "") -> None:
        """Populate this panel from all comparison curves in *curves*."""
        previous = preferred_key or self.selected_key()
        comparisons = {
            str(key): curve
            for key, curve in curves.items()
            if getattr(curve, "role", "target") == "comparison"
        }
        self._curves = comparisons
        self._selector.blockSignals(True)
        self._selector.clear()
        for key, curve in comparisons.items():
            label = str(getattr(curve, "name", "") or getattr(curve, "auid", "") or key)
            self._selector.addItem(label, key)
        if comparisons:
            self._selector.addItem("All comparison stars", _ALL_COMPARISONS)
        index = self._selector.findData(previous)
        self._selector.setCurrentIndex(index if index >= 0 else (0 if comparisons else -1))
        self._selector.blockSignals(False)
        self._refresh_plot()

    def set_selected_key(self, key: str) -> None:
        index = self._selector.findData(key)
        if index >= 0:
            self._selector.setCurrentIndex(index)

    def _refresh_plot(self) -> None:
        key = self.selected_key()
        curves = (
            self._curves
            if key == _ALL_COMPARISONS
            else {key: self._curves[key]} if key in self._curves else {}
        )
        self._plot.set_curves(curves)
