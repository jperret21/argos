"""Sequence panel — advanced multi-step acquisition table for the Sequence tab.

UI-only. Builds a :class:`SequencePlan` from an editable step table (one row per
acquisition block) plus plan-level options, and emits ``start_requested(plan)`` /
``stop_requested()``. The ImagingPage drives a ``SequenceWorker`` from those and
feeds progress back via the public setters. Inspired by NINA's sequencer table.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QWidget,
)

from argos.core.imaging.sequencer import SequencePlan, SequenceStep
from argos.ui import design, theme

logger = logging.getLogger(__name__)

_FRAME_TYPES = ("Light", "Dark", "Flat", "Bias")
_DEFAULT_FILTERS = ("LP", "IR-cut", "Dark")
_COLUMNS = ("✓", "Type", "Filter", "Exp (s)", "Gain", "Count")


class SequencePanel(design.Card):
    """Editable multi-step sequence table + run controls."""

    start_requested = pyqtSignal(object)  # SequencePlan
    stop_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Sequence", parent)
        self._filters = list(_DEFAULT_FILTERS)
        self._running = False
        self._build_ui()
        self._add_row()  # start with one editable row

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        for col in (3, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setMinimumHeight(160)
        outer.addWidget(self._table)

        # Row-editing buttons.
        edit_row = QHBoxLayout()
        edit_row.setSpacing(design.SPACING_SM)
        for label, slot, tip in (
            ("＋ Add", self._add_row, "Add a step"),
            ("⧉ Dup", self._duplicate_row, "Duplicate the selected step"),
            ("－ Remove", self._remove_row, "Remove the selected step"),
            ("↑", self._move_up, "Move step up"),
            ("↓", self._move_down, "Move step down"),
        ):
            btn = design.SecondaryButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            edit_row.addWidget(btn)
        outer.addLayout(edit_row)

        # Plan-level options.
        opts = QGridLayout()
        opts.setHorizontalSpacing(design.SPACING_MD)
        opts.setVerticalSpacing(design.SPACING_SM)
        opts.setColumnStretch(1, 1)
        opts.addWidget(design.MutedLabel("Object"), 0, 0)
        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("M42, T CrB…")
        opts.addWidget(self._object_edit, 0, 1)
        opts.addWidget(design.MutedLabel("Repeat ×"), 1, 0)
        self._repeat_spin = QSpinBox()
        self._repeat_spin.setRange(1, 999)
        opts.addWidget(self._repeat_spin, 1, 1)
        opts.addWidget(design.MutedLabel("Autofocus every"), 2, 0)
        self._af_spin = QSpinBox()
        self._af_spin.setRange(0, 999)
        self._af_spin.setSuffix(" frames (0=off)")
        opts.addWidget(self._af_spin, 2, 1)
        outer.addLayout(opts)

        # Run controls.
        self._start_btn = design.SuccessButton("▶  Start sequence")
        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn = design.DangerButton("■  Stop")
        self._stop_btn.clicked.connect(self.stop_requested)
        self._stop_btn.setEnabled(False)
        outer.addLayout(design.button_row(self._start_btn, self._stop_btn))

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        outer.addWidget(self._progress)
        self._status_lbl = design.MutedLabel("")
        outer.addWidget(self._status_lbl)

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self, step: SequenceStep | None = None) -> None:
        step = step or SequenceStep()
        r = self._table.rowCount()
        self._table.insertRow(r)

        chk = QCheckBox()
        chk.setChecked(step.enabled)
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(chk)
        self._table.setCellWidget(r, 0, wrap)

        type_combo = QComboBox()
        type_combo.addItems(_FRAME_TYPES)
        type_combo.setCurrentText(step.frame_type)
        self._table.setCellWidget(r, 1, type_combo)

        filter_combo = QComboBox()
        filter_combo.addItems(self._filters)
        idx = filter_combo.findText(step.filter_name)
        if idx >= 0:
            filter_combo.setCurrentIndex(idx)
        self._table.setCellWidget(r, 2, filter_combo)

        exp = QDoubleSpinBox()
        exp.setRange(0.01, 600.0)
        exp.setDecimals(2)
        exp.setValue(step.exposure_s)
        self._table.setCellWidget(r, 3, exp)

        gain = QSpinBox()
        gain.setRange(0, 600)
        gain.setValue(step.gain)
        self._table.setCellWidget(r, 4, gain)

        count = QSpinBox()
        count.setRange(1, 9999)
        count.setValue(step.count)
        self._table.setCellWidget(r, 5, count)

        self._table.selectRow(r)

    def _selected_row(self) -> int:
        rows = self._table.selectionModel().selectedRows()
        if rows:
            return rows[0].row()
        return self._table.rowCount() - 1

    def _duplicate_row(self) -> None:
        r = self._selected_row()
        if r < 0:
            return
        self._add_row(self._read_step(r))

    def _remove_row(self) -> None:
        r = self._selected_row()
        if r >= 0 and self._table.rowCount() > 1:
            self._table.removeRow(r)

    def _move_up(self) -> None:
        self._swap_rows(self._selected_row(), self._selected_row() - 1)

    def _move_down(self) -> None:
        self._swap_rows(self._selected_row(), self._selected_row() + 1)

    def _swap_rows(self, a: int, b: int) -> None:
        if a < 0 or b < 0 or a >= self._table.rowCount() or b >= self._table.rowCount():
            return
        step_a, step_b = self._read_step(a), self._read_step(b)
        self._write_step(a, step_b)
        self._write_step(b, step_a)
        self._table.selectRow(b)

    # ------------------------------------------------------------------
    # Read / write a row <-> SequenceStep
    # ------------------------------------------------------------------

    def _read_step(self, r: int) -> SequenceStep:
        chk = self._table.cellWidget(r, 0).findChild(QCheckBox)
        return SequenceStep(
            enabled=chk.isChecked() if chk else True,
            frame_type=self._table.cellWidget(r, 1).currentText(),
            filter_name=self._table.cellWidget(r, 2).currentText(),
            exposure_s=float(self._table.cellWidget(r, 3).value()),
            gain=int(self._table.cellWidget(r, 4).value()),
            count=int(self._table.cellWidget(r, 5).value()),
        )

    def _write_step(self, r: int, step: SequenceStep) -> None:
        chk = self._table.cellWidget(r, 0).findChild(QCheckBox)
        if chk:
            chk.setChecked(step.enabled)
        self._table.cellWidget(r, 1).setCurrentText(step.frame_type)
        self._table.cellWidget(r, 2).setCurrentText(step.filter_name)
        self._table.cellWidget(r, 3).setValue(step.exposure_s)
        self._table.cellWidget(r, 4).setValue(step.gain)
        self._table.cellWidget(r, 5).setValue(step.count)

    def to_plan(self) -> SequencePlan:
        steps = [self._read_step(r) for r in range(self._table.rowCount())]
        return SequencePlan(
            steps=steps,
            object_name=self._object_edit.text().strip(),
            repeat=int(self._repeat_spin.value()),
            autofocus_every_n=int(self._af_spin.value()),
        )

    # ------------------------------------------------------------------
    # Public API (called by ImagingPage)
    # ------------------------------------------------------------------

    def set_filter_options(self, names: list[str]) -> None:
        self._filters = list(names or _DEFAULT_FILTERS)
        for r in range(self._table.rowCount()):
            combo = self._table.cellWidget(r, 2)
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self._filters)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def set_running(self, running: bool) -> None:
        self._running = running
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._table.setEnabled(not running)
        self._progress.setVisible(running)
        if not running:
            self._status_lbl.setText("")

    def set_progress(self, done: int, total: int, eta_seconds: float) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(done)
        self._progress.setFormat(f"%v / {total}")
        m, s = divmod(max(0, int(eta_seconds)), 60)
        self._status_lbl.setText(f"Frame {done}/{total} — ETA {m}m {s:02d}s")

    def set_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        plan = self.to_plan()
        if not any(s.enabled and s.count > 0 for s in plan.steps):
            self._status_lbl.setText("Add at least one enabled step.")
            self._status_lbl.setStyleSheet(f"color:{theme.WARNING};")
            return
        self._status_lbl.setStyleSheet("")
        self.start_requested.emit(plan)

    def _label(self, text: str) -> QLabel:  # kept for parity / future use
        return design.MutedLabel(text)
