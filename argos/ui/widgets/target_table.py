"""Target-set management table (docs/photometry_plan.md §5 B4, P5).

Review the night's saved stars (role / name / RA / Dec / mags), remove one, or
copy the lot as TSV. Display only — the page owns the ``TargetSet`` and handles
removal (persist + re-project) on the ``remove_requested`` signal.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms

_HEADERS = ("Role", "Name", "RA", "Dec", "Mags")


class TargetTable(QWidget):
    """Table of the saved target set, with remove + copy-TSV."""

    remove_requested = pyqtSignal(str)  # the TargetStar.key() of the row to drop

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.clicked.connect(self._on_remove)
        self._copy_btn = QPushButton("Copy TSV")
        self._copy_btn.clicked.connect(self._on_copy)
        row.addWidget(self._remove_btn)
        row.addWidget(self._copy_btn)
        row.addStretch()
        layout.addLayout(row)
        self._keys: list[str] = []

    def set_targets(self, stars) -> None:
        self._keys = [s.key() for s in stars]
        self._table.setRowCount(len(stars))
        for r, s in enumerate(stars):
            mags = "  ".join(f"{b} {m:.2f}" for b, m in s.mags.items())
            values = (
                s.role,
                s.display_name,
                format_ra_hms(s.ra_deg / 15.0),
                format_dec_dms(s.dec_deg),
                mags,
            )
            for c, v in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(v))

    def _on_remove(self) -> None:
        r = self._table.currentRow()
        if 0 <= r < len(self._keys):
            self.remove_requested.emit(self._keys[r])

    def _on_copy(self) -> None:
        lines = ["\t".join(_HEADERS)]
        for r in range(self._table.rowCount()):
            lines.append(
                "\t".join(
                    (self._table.item(r, c).text() if self._table.item(r, c) else "")
                    for c in range(len(_HEADERS))
                )
            )
        QApplication.clipboard().setText("\n".join(lines))
