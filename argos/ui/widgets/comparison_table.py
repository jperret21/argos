"""Comparison-star tables (WS7 revival + the ranked-comparison popup).

Two widgets:

* :class:`ComparisonEnsembleTable` — the comp ensemble actually *in use* for the
  night, read off the target set (role == ``comparison``), with their catalog
  mags and a remove button. Lives as a tab of the Photometry window so the user
  can see and prune the ensemble that forms the differential zero-point.
* :class:`ComparisonTableDialog` — the older ranked-VSP popup (nearest first)
  for a selected variable, opened from the analysis window.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms

_COLUMNS = ["AUID", "RA (J2000)", "Dec (J2000)", "V", "B", "Label", "Sep′", "Comments"]

_ENSEMBLE_HEADERS = ("Name / AUID", "RA (J2000)", "Dec (J2000)", "Mags")


class ComparisonEnsembleTable(QWidget):
    """The comparison ensemble in use (target-set comps), with remove.

    Display only — the engine owns the ``TargetSet`` and persists/re-projects on
    the ``remove_requested`` signal (the ``TargetStar.key()`` of the dropped row).
    """

    remove_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._hint = QLabel(
            "Comparison ensemble — these stars' catalog mags form the "
            "differential zero-point. Need ≥ min_comparisons with a mag."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#9a9a9a; font-size:11px; padding:2px 0;")
        layout.addWidget(self._hint)

        self._table = QTableWidget(0, len(_ENSEMBLE_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_ENSEMBLE_HEADERS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            len(_ENSEMBLE_HEADERS) - 1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._table, 1)

        row = QHBoxLayout()
        self._count = QLabel("")
        self._count.setStyleSheet("color:#9a9a9a;")
        row.addWidget(self._count)
        row.addStretch(1)
        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.clicked.connect(self._on_remove)
        row.addWidget(self._remove_btn)
        copy_btn = QPushButton("Copy TSV")
        copy_btn.clicked.connect(self._on_copy)
        row.addWidget(copy_btn)
        layout.addLayout(row)
        self._keys: list[str] = []

    def set_targets(self, stars) -> None:
        """Populate from a full target set — filters to the comparison stars."""
        comps = [s for s in stars if s.role == "comparison"]
        self._keys = [s.key() for s in comps]
        self._table.setRowCount(len(comps))
        for r, s in enumerate(comps):
            mags = "  ".join(f"{b} {m:.2f}" for b, m in s.mags.items()) or "—"
            values = (
                s.display_name,
                format_ra_hms(s.ra_deg / 15.0),
                format_dec_dms(s.dec_deg),
                mags,
            )
            for c, v in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(v))
        self._count.setText(f"{len(comps)} comparison star(s)")

    def _on_remove(self) -> None:
        r = self._table.currentRow()
        if 0 <= r < len(self._keys):
            self.remove_requested.emit(self._keys[r])

    def _on_copy(self) -> None:
        lines = ["\t".join(_ENSEMBLE_HEADERS)]
        for r in range(self._table.rowCount()):
            lines.append(
                "\t".join(
                    (self._table.item(r, c).text() if self._table.item(r, c) else "")
                    for c in range(len(_ENSEMBLE_HEADERS))
                )
            )
        QApplication.clipboard().setText("\n".join(lines))


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
