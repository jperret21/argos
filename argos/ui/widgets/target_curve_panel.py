"""Selectable target light curve for the Review workspace."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from argos.ui import theme
from argos.ui.widgets.lightcurve_panel import LightCurvePanel

_ALL_TARGETS = "__all_targets__"


class TargetCurvePanel(QWidget):
    """One Review plot whose selector can show one target or all targets.

    Review creates one instance per scientific target by default.  The selector
    still makes each dock reusable when the observer wants a different layout.
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
        label = QLabel("Target")
        label.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:12px; font-weight:600; background:transparent;"
        )
        row.addWidget(label)
        self._selector = QComboBox()
        self._selector.setToolTip("Choose the target shown in this source light curve")
        self._selector.currentIndexChanged.connect(self._refresh_plot)
        row.addWidget(self._selector, 1)
        layout.addLayout(row)

        self._plot = LightCurvePanel(view="target")
        self._plot.point_hovered.connect(self.point_hovered.emit)
        self._plot.point_clicked.connect(self.point_clicked.emit)
        layout.addWidget(self._plot, 1)

    def selected_key(self) -> str:
        return str(self._selector.currentData() or "")

    def set_curves(self, curves: dict, *, preferred_key: str = "") -> None:
        """Populate the selector from target curves; ``All targets`` is last."""
        previous = preferred_key or self.selected_key()
        targets = {
            str(key): curve
            for key, curve in curves.items()
            if getattr(curve, "role", "target") == "target"
        }
        self._curves = targets
        self._selector.blockSignals(True)
        self._selector.clear()
        for key, curve in targets.items():
            label = str(getattr(curve, "name", "") or getattr(curve, "auid", "") or key)
            self._selector.addItem(label, key)
        if targets:
            self._selector.addItem("All targets", _ALL_TARGETS)
        index = self._selector.findData(previous)
        self._selector.setCurrentIndex(index if index >= 0 else (0 if targets else -1))
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
            if key == _ALL_TARGETS
            else {key: self._curves[key]} if key in self._curves else {}
        )
        self._plot.set_curves(curves)
