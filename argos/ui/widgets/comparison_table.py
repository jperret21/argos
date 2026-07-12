"""Comparison-star ensemble table (WS7 revival).

:class:`ComparisonEnsembleTable` — the comp ensemble actually *in use* for the
night, read off the target set (role == ``comparison``), with their catalog
mags and a remove button. Lives as a tab of the Photometry window so the user
can see and prune the ensemble that forms the differential zero-point.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
