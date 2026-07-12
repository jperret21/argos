"""Field variable-star table — pick the photometry target from a list.

Every VSX variable of the solved field, one row each (same order as the
engine's cached list, brightest first), with a ● marking stars already in
the target set. Clicking a variable on the image and picking it here are
the same action: the page routes ``target_requested`` through the exact
code path as the star-card's Target button (auto-comparisons included).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from argos.ui import theme

_HEADERS = ("", "Name", "Type", "Mag", "Period (d)", "Sep (′)")


class VariableTable(QWidget):
    """Table of the field's variables, with select-as-target."""

    target_requested = pyqtSignal(int)  # row = index into the engine's list

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnWidth(0, 18)
        self._table.doubleClicked.connect(lambda _i: self._on_select())
        layout.addWidget(self._table)

        row = QHBoxLayout()
        self._select_btn = QPushButton("Set as target")
        self._select_btn.setToolTip(
            "Make this variable a photometry target (comparison stars are\n"
            "picked automatically when none are chosen yet). Same action as\n"
            "clicking its diamond on the image."
        )
        self._select_btn.clicked.connect(self._on_select)
        row.addWidget(self._select_btn)
        row.addStretch()
        layout.addLayout(row)

    def set_variables(self, rows: list[tuple]) -> None:
        """Populate from ``(name, var_type, mag, period_d, sep_arcmin,
        is_target, is_suspected)`` tuples, one per engine variable, in order."""
        self._table.setRowCount(len(rows))
        for r, (name, var_type, mag, period, sep, is_target, suspected) in enumerate(rows):
            values = (
                "●" if is_target else "",
                str(name),
                str(var_type or "?"),
                str(mag or "?"),
                f"{period:g}" if period else "",
                f"{sep:.1f}" if sep is not None else "",
            )
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if suspected:  # same quiet convention as the dashed diamonds
                    item.setForeground(QColor(theme.FG_MUTED))
                self._table.setItem(r, c, item)

    def _on_select(self) -> None:
        r = self._table.currentRow()
        if r >= 0:
            self.target_requested.emit(r)
