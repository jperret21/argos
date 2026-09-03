"""Field variable-star table — pick the photometry target from a list.

Every VSX variable of the solved field, one row each (same order as the
engine's cached list, brightest first), with a ● marking stars already in
the target set. Clicking a variable on the image and picking it here are
the same action: the page routes ``target_requested`` through the exact
code path as the star-card's Target button (auto-comparisons included).
"""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from argos.ui import theme

_HEADERS = ("", "Name", "Type", "Mag", "Period (d)", "Sep (′)")


class _SortableItem(QTableWidgetItem):
    """Table item with a semantic sort key (magnitudes are not strings)."""

    def __init__(self, text: str, sort_key=None) -> None:
        super().__init__(text)
        self._sort_key = text.casefold() if sort_key is None else sort_key

    def __lt__(self, other) -> bool:
        if isinstance(other, _SortableItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)


def _normalised_text(value: str) -> str:
    """Forgiving designation matching: ``XX Cyg`` matches ``xxcyg``."""
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _brightest_magnitude(value: str) -> float | None:
    """Extract the bright-end magnitude from a VSX display value."""
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group()) if match else None


class VariableTable(QWidget):
    """Table of the field's variables, with select-as-target."""

    target_requested = pyqtSignal(int)  # row = index into the engine's list
    visible_rows_changed = pyqtSignal(object)  # list[int] = engine-variable indices

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._rows: list[tuple] = []
        self._source_indices: list[int] = []
        self._sort_column: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter by designation or type…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setToolTip("Case- and space-insensitive; for example, XX Cyg or xxcyg")
        self._search_edit.textChanged.connect(self._apply_filters)
        filters.addWidget(self._search_edit, 1)
        filters.addWidget(QLabel("Brightest mag ≤"))
        self._mag_limit = QDoubleSpinBox()
        self._mag_limit.setRange(0.0, 20.0)
        self._mag_limit.setSpecialValueText("Any")
        self._mag_limit.setSingleStep(0.5)
        self._mag_limit.setDecimals(1)
        self._mag_limit.setToolTip(
            "Show variables whose brightest catalogued magnitude is at or brighter than this limit"
        )
        self._mag_limit.valueChanged.connect(self._apply_filters)
        filters.addWidget(self._mag_limit)
        self._count_lbl = QLabel("0 stars")
        filters.addWidget(self._count_lbl)
        layout.addLayout(filters)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnWidth(0, 18)
        # Populate in catalogue order (brightest-first) and sort only after
        # an explicit header click. Qt otherwise sorts while rows are inserted.
        self._table.setSortingEnabled(False)
        self._table.horizontalHeader().sectionClicked.connect(self._sort_by_column)
        self._table.doubleClicked.connect(lambda _i: self._on_select())
        layout.addWidget(self._table)

        row = QHBoxLayout()
        self._select_btn = QPushButton("Set as target")
        self._select_btn.setToolTip(
            "Make this variable a photometry target (comparison stars are\n"
            "picked automatically when none are chosen yet). Same action as\n"
            "clicking its circle on the image."
        )
        self._select_btn.clicked.connect(self._on_select)
        row.addWidget(self._select_btn)
        row.addStretch()
        layout.addLayout(row)

    def set_variables(self, rows: list[tuple], *, source_indices: list[int] | None = None) -> None:
        """Populate from ``(name, var_type, mag, period_d, sep_arcmin,
        is_target, is_suspected)`` tuples.

        ``source_indices`` preserves the matching engine index when a cone
        result includes catalogue objects outside the rectangular image.
        """
        self._rows = list(rows)
        self._source_indices = (
            list(source_indices) if source_indices is not None else list(range(len(self._rows)))
        )
        if len(self._source_indices) != len(self._rows):
            raise ValueError("source_indices must match variable rows")
        self._apply_filters()

    def _apply_filters(self, *_args) -> None:
        """Apply local filters; no field-catalogue request is required."""
        needle = _normalised_text(self._search_edit.text())
        mag_limit = float(self._mag_limit.value())
        kept: list[tuple[int, tuple]] = []
        for row_index, row in enumerate(self._rows):
            source_index = self._source_indices[row_index]
            name, var_type, mag, _period, _sep, _is_target, _suspected = row
            haystack = _normalised_text(f"{name} {var_type or ''}")
            brightest = _brightest_magnitude(mag)
            if needle and needle not in haystack:
                continue
            if mag_limit > 0 and (brightest is None or brightest > mag_limit):
                continue
            kept.append((source_index, row))

        self._table.setRowCount(len(kept))
        for table_row, (source_index, row) in enumerate(kept):
            name, var_type, mag, period, sep, is_target, suspected = row
            brightest = _brightest_magnitude(mag)
            values = (
                "●" if is_target else "",
                str(name),
                str(var_type or "?"),
                str(mag or "?"),
                f"{period:g}" if period else "",
                f"{sep:.1f}" if sep is not None else "",
            )
            for c, v in enumerate(values):
                sort_key = {
                    0: 0 if is_target else 1,
                    1: str(name).casefold(),
                    2: str(var_type or "").casefold(),
                    3: brightest if brightest is not None else float("inf"),
                    4: float(period) if period is not None else float("inf"),
                    5: float(sep) if sep is not None else float("inf"),
                }[c]
                item = _SortableItem(v, sort_key)
                # The visible row changes when filtered/sorted. Persist the
                # original engine-variable index on every cell so selecting a
                # row always assigns the intended catalogue star.
                item.setData(Qt.ItemDataRole.UserRole, source_index)
                if suspected:  # same quiet convention as the dashed circles
                    item.setForeground(QColor(theme.FG_MUTED))
                self._table.setItem(table_row, c, item)
        if self._sort_column is not None:
            self._table.sortItems(self._sort_column, self._sort_order)
        total = len(self._rows)
        self._count_lbl.setText(f"{len(kept)} of {total} star{'s' if total != 1 else ''}")
        self.visible_rows_changed.emit([source_index for source_index, _row in kept])

    def _sort_by_column(self, column: int) -> None:
        """Toggle a user-requested sort without changing target identities."""
        if self._sort_column == column:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder
        self._table.sortItems(column, self._sort_order)

    def _on_select(self) -> None:
        r = self._table.currentRow()
        if r >= 0:
            item = self._table.item(r, 0)
            source_index = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(source_index, int):
                self.target_requested.emit(source_index)
