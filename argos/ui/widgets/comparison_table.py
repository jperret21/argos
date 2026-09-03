"""Comparison-star ensemble table (WS7 revival).

:class:`ComparisonEnsembleTable` — the comp ensemble actually *in use* for the
night, read off the target set (role == ``comparison``), with their catalog
mags and a remove button. Lives as a tab of the Photometry window so the user
can see and prune the ensemble that forms the differential zero-point.
"""

from __future__ import annotations

from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms
from argos.ui import theme

_ENSEMBLE_HEADERS = ("Name", "AUID", "RA (J2000)", "Dec (J2000)", "Catalogue mags", "Source")


class ComparisonEnsembleTable(QWidget):
    """The comparison ensemble in use (target-set comps), with remove.

    Display only — the engine owns the ``TargetSet`` and persists/re-projects on
    the ``remove_requested`` signal (the ``TargetStar.key()`` of the dropped row).
    """

    remove_requested = pyqtSignal(str)
    star_selected = pyqtSignal(str)
    refresh_requested = pyqtSignal()
    recommend_requested = pyqtSignal()
    auto_count_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._hint = QLabel(
            "Comparison ensemble — catalogue magnitudes enable differential magnitudes; "
            "relative-flux preview only needs stable, unsaturated comparison stars."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:11px; padding:2px 0;")
        layout.addWidget(self._hint)

        proposal = QHBoxLayout()
        proposal.addWidget(QLabel("Automatically propose"))
        self._auto_count = QSpinBox()
        self._auto_count.setRange(1, 12)
        self._auto_count.setValue(5)
        self._auto_count.setSuffix(" calibrated stars")
        self._auto_count.setToolTip(
            "Number of calibrated VSP comparison stars Argos proposes when a target is selected"
        )
        self._auto_count.valueChanged.connect(self.auto_count_changed)
        proposal.addWidget(self._auto_count)
        proposal.addStretch(1)
        layout.addLayout(proposal)

        self._table = QTableWidget(0, len(_ENSEMBLE_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_ENSEMBLE_HEADERS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            len(_ENSEMBLE_HEADERS) - 1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._table, 1)

        row = QHBoxLayout()
        self._count = QLabel("")
        self._count.setStyleSheet(f"color:{theme.FG_MUTED};")
        row.addWidget(self._count)
        row.addStretch(1)
        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.clicked.connect(self._on_remove)
        row.addWidget(self._remove_btn)
        self._refresh_btn = QPushButton("Refresh catalogue")
        self._refresh_btn.setToolTip(
            "Fetch VSP comparison-star proposals again for the solved field"
        )
        self._refresh_btn.clicked.connect(self.refresh_requested)
        row.addWidget(self._refresh_btn)
        self._recommend_btn = QPushButton("Recommend from pilot")
        self._recommend_btn.setToolTip(
            "Replace VSP suggestions using SNR, saturation and brightness measured on the solved pilot image"
        )
        self._recommend_btn.clicked.connect(self.recommend_requested)
        row.addWidget(self._recommend_btn)
        copy_btn = QPushButton("Copy TSV")
        copy_btn.clicked.connect(self._on_copy)
        row.addWidget(copy_btn)
        layout.addLayout(row)
        self._keys: list[str] = []

    def set_auto_count(self, count: int) -> None:
        """Synchronise the user preference without emitting a new request."""
        blocker = QSignalBlocker(self._auto_count)
        self._auto_count.setValue(max(1, int(count)))
        del blocker

    def set_targets(self, stars) -> None:
        """Populate from a full target set — filters to the comparison stars."""
        comps = [s for s in stars if s.role == "comparison"]
        self._keys = [s.key() for s in comps]
        blocker = QSignalBlocker(self._table)
        self._table.clearSelection()
        self._table.setRowCount(len(comps))
        for r, s in enumerate(comps):
            mags = "  ".join(f"{b} {m:.2f}" for b, m in s.mags.items()) or "—"
            values = (
                s.display_name,
                s.auid or "—",
                format_ra_hms(s.ra_deg / 15.0),
                format_dec_dms(s.dec_deg),
                mags,
                s.source or "manual",
            )
            for c, v in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(v))
        del blocker
        calibrated = [s for s in comps if s.mags]
        manual = len(comps) - len(calibrated)
        if not comps:
            self._count.setText(
                "No comparison stars — refresh the catalogue after a successful solve."
            )
        elif manual:
            self._count.setText(
                f"{len(calibrated)} calibrated comparison(s) · {manual} uncalibrated manual star(s)"
            )
        else:
            self._count.setText(f"{len(calibrated)} calibrated comparison star(s)")

    def _on_remove(self) -> None:
        r = self._table.currentRow()
        if 0 <= r < len(self._keys):
            self.remove_requested.emit(self._keys[r])

    def _on_selection_changed(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._keys):
            self.star_selected.emit(self._keys[row])

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
