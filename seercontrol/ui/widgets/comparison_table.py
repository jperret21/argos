"""Comparison-star table — a popup with the full photometry table for a variable.

Opened from the analysis window's "Comparison stars" button once a variable is
selected. Lists the field's VSP comparison stars ranked for that target, with
their coordinates (J2000), AUID, calibrated magnitudes and chart info. Selecting
a row asks the parent to locate/ring that star on the image.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from seercontrol.core.imaging.platesolve import format_dec_dms, format_ra_hms

_COLUMNS = ["AUID", "RA (J2000)", "Dec (J2000)", "V", "B", "Label", "Sep′", "Comments"]


class ComparisonTableDialog(QDialog):
    """Non-modal table of comparison stars for the selected variable.

    Signals:
        row_activated(object): the :class:`ScoredComparison` of a clicked row.
    """

    row_activated = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Comparison stars")
        self.setMinimumSize(680, 380)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self._rows: list = []

        layout = QVBoxLayout(self)
        self._title = QLabel("No variable selected")
        self._title.setStyleSheet("font-weight: bold; padding: 2px 0;")
        layout.addWidget(self._title)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            len(_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch  # stretch the Comments column
        )
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table, 1)

        row = QHBoxLayout()
        self._count = QLabel("")
        self._count.setStyleSheet("color: #9a9a9a;")
        row.addWidget(self._count)
        row.addStretch(1)
        copy_btn = QPushButton("Copy table")
        copy_btn.setToolTip("Copy the whole table as TSV (paste into a sheet / report)")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        row.addWidget(copy_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        row.addWidget(close_btn)
        layout.addLayout(row)

    # ------------------------------------------------------------------

    def set_data(self, variable_name: str, scored: list) -> None:
        """Populate the table for ``variable_name`` with ranked comparisons."""
        self._rows = list(scored)
        self._title.setText(f"Comparison stars for  {variable_name}")
        self._count.setText(f"{len(scored)} comparison star(s), nearest first")
        self._table.setRowCount(len(scored))
        for r, s in enumerate(scored):
            c = s.star
            v, b = c.mag("V"), c.mag("B")
            values = [
                c.auid,
                format_ra_hms(c.ra_deg / 15.0),
                format_dec_dms(c.dec_deg),
                f"{v:.3f}" if v is not None else "—",
                f"{b:.3f}" if b is not None else "—",
                c.label or "—",
                f"{s.separation_arcmin:.1f}",
                (c.comments or "").strip(),
            ]
            for col, txt in enumerate(values):
                self._table.setItem(r, col, QTableWidgetItem(txt))
        self._table.resizeColumnsToContents()

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._rows):
            self.row_activated.emit(self._rows[row])

    def _copy_to_clipboard(self) -> None:
        from PyQt6.QtWidgets import QApplication

        lines = ["\t".join(_COLUMNS)]
        for r in range(self._table.rowCount()):
            cells = [
                (self._table.item(r, c).text() if self._table.item(r, c) else "")
                for c in range(self._table.columnCount())
            ]
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
