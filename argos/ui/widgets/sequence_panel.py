"""Sequence panel — the multi-step acquisition table, NINA-style.

Lives in the bottom dock of the Capture page (wide layout: the step table
gets the width it deserves, the plan options + run controls sit in a right
column). UI-only: builds a :class:`SequencePlan` from the editable table and
emits ``start/pause/resume/stop`` intents; the AcquisitionEngine drives the
``SequenceWorker`` and feeds progress back via the public setters.

Presets: a plan (steps + options) saves/loads as JSON via the sequencer's
``plan_to_dict`` / ``plan_from_dict`` round-trip.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from argos.core.imaging.sequencer import (
    ON_COMPLETE_CHOICES,
    SequencePlan,
    SequenceStep,
    estimated_duration_s,
    plan_from_dict,
    plan_to_dict,
)
from argos.ui import design, theme

logger = logging.getLogger(__name__)

_FRAME_TYPES = ("Light", "Dark", "Flat", "Bias")
# Seestar wheel slot names (see alpaca.filterwheel.position_names) — "IR-cut"
# never matched a wheel position, so those steps silently kept the old filter.
_DEFAULT_FILTERS = ("IR", "LP", "Dark")
_COLUMNS = ("✓", "Type", "Filter", "Exp (s)", "Gain", "Count", "Interval (s)", "Dither every")

#: Fallback limits when no camera is connected (the historical hardcodes).
_DEFAULT_GAIN_RANGE = (0, 600)
_DEFAULT_EXPOSURE_RANGE = (0.01, 600.0)


def _format_duration(seconds: float) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


class SequencePanel(QWidget):
    """Editable multi-step sequence plan + run controls (full-page layout).

    Pure UI — Steps / Plan / Presets / Run cards; the hosting SequencerPage
    wires the signals to the engine and pushes device-derived limits in.
    """

    start_requested = pyqtSignal(object)  # SequencePlan
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filters = list(_DEFAULT_FILTERS)
        self._gain_range = _DEFAULT_GAIN_RANGE
        self._exposure_range = _DEFAULT_EXPOSURE_RANGE
        self._running = False
        self._paused = False
        self._active_row = -1
        self._build_ui()
        self._add_row()  # start with one editable row
        self._refresh_estimate()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(design.SPACING_LG)

        # ── Steps card: the table + row editing (takes the width) ───────
        steps_card = design.Card("Steps")
        left = design.card_layout(steps_card)
        left.setSpacing(design.SPACING_SM)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col in range(3, len(_COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setMinimumHeight(120)
        self._table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        left.addWidget(self._table, 1)

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
        edit_row.addStretch()
        self._estimate_lbl = design.MutedLabel("")
        self._estimate_lbl.setWordWrap(True)
        self._estimate_lbl.setToolTip(
            "Exposures + intervals + per-frame overhead; autofocus passes not counted"
        )
        edit_row.addWidget(self._estimate_lbl)
        left.addLayout(edit_row)
        body.addWidget(steps_card, 1)

        # ── Right rail: Plan / Presets / Run cards ───────────────────────
        right = QVBoxLayout()
        right.setSpacing(design.SPACING_LG)

        plan_card = design.Card("Plan")
        plan_l = design.card_layout(plan_card)
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
        self._repeat_spin.valueChanged.connect(self._refresh_estimate)
        opts.addWidget(self._repeat_spin, 1, 1)
        opts.addWidget(design.MutedLabel("AF every"), 2, 0)
        self._af_spin = QSpinBox()
        self._af_spin.setRange(0, 999)
        self._af_spin.setSuffix(" frames (0=off)")
        opts.addWidget(self._af_spin, 2, 1)
        self._af_filter_chk = QCheckBox("AF on filter change")
        opts.addWidget(self._af_filter_chk, 3, 0, 1, 2)
        opts.addWidget(design.MutedLabel("When done"), 4, 0)
        self._on_complete_combo = QComboBox()
        self._on_complete_combo.addItems(ON_COMPLETE_CHOICES)
        self._on_complete_combo.setToolTip(
            "Mount action after FULL completion only — never after a stop or error"
        )
        opts.addWidget(self._on_complete_combo, 4, 1)
        plan_l.addLayout(opts)
        right.addWidget(plan_card)

        presets_card = design.Card("Presets")
        presets_l = design.card_layout(presets_card)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(design.SPACING_SM)
        save_btn = design.SecondaryButton("Save preset…")
        save_btn.clicked.connect(self._on_save_preset)
        load_btn = design.SecondaryButton("Load preset…")
        load_btn.clicked.connect(self._on_load_preset)
        preset_row.addWidget(save_btn, 1)
        preset_row.addWidget(load_btn, 1)
        presets_l.addLayout(preset_row)
        right.addWidget(presets_card)

        run_card = design.Card("Run")
        run_l = design.card_layout(run_card)
        self._start_btn = design.SuccessButton("▶  Start sequence")
        self._start_btn.clicked.connect(self._on_start)
        self._pause_btn = design.SecondaryButton("⏸  Pause")
        self._pause_btn.setToolTip("Hold after the current frame; Resume releases it")
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        self._pause_btn.setEnabled(False)
        self._stop_btn = design.DangerButton("■  Stop")
        self._stop_btn.clicked.connect(self.stop_requested)
        self._stop_btn.setEnabled(False)
        run_l.addLayout(design.button_row(self._start_btn))
        run_l.addLayout(design.button_row(self._pause_btn, self._stop_btn))

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        run_l.addWidget(self._progress)
        self._status_lbl = design.MutedLabel("")
        self._status_lbl.setWordWrap(True)
        run_l.addWidget(self._status_lbl)
        right.addWidget(run_card)

        right.addStretch()

        right_wrap = QWidget()
        right_wrap.setLayout(right)
        right_wrap.setFixedWidth(320)
        body.addWidget(right_wrap, 0)

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self, step: SequenceStep | None = None) -> None:
        step = step or SequenceStep()
        r = self._table.rowCount()
        self._table.insertRow(r)

        chk = QCheckBox()
        chk.setChecked(step.enabled)
        chk.toggled.connect(self._refresh_estimate)
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
        exp.setRange(*self._exposure_range)
        exp.setDecimals(2)
        exp.setValue(step.exposure_s)
        exp.valueChanged.connect(self._refresh_estimate)
        self._table.setCellWidget(r, 3, exp)

        gain = QSpinBox()
        gain.setRange(*self._gain_range)
        gain.setValue(step.gain)
        self._table.setCellWidget(r, 4, gain)

        count = QSpinBox()
        count.setRange(1, 9999)
        count.setValue(step.count)
        count.valueChanged.connect(self._refresh_estimate)
        self._table.setCellWidget(r, 5, count)

        interval = QDoubleSpinBox()
        interval.setRange(0.0, 3600.0)
        interval.setDecimals(1)
        interval.setValue(step.interval_s)
        interval.setToolTip("Idle delay after each frame of this step")
        interval.valueChanged.connect(self._refresh_estimate)
        self._table.setCellWidget(r, 6, interval)

        dither = QSpinBox()
        dither.setRange(0, 999)
        dither.setValue(step.dither_every)
        dither.setSpecialValueText("off")
        dither.setToolTip("Nudge the mount a few arcminutes every N frames (0 = off)")
        self._table.setCellWidget(r, 7, dither)

        self._table.selectRow(r)
        self._refresh_estimate()

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
            self._refresh_estimate()

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
            interval_s=float(self._table.cellWidget(r, 6).value()),
            dither_every=int(self._table.cellWidget(r, 7).value()),
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
        self._table.cellWidget(r, 6).setValue(step.interval_s)
        self._table.cellWidget(r, 7).setValue(step.dither_every)

    def to_plan(self) -> SequencePlan:
        steps = [self._read_step(r) for r in range(self._table.rowCount())]
        return SequencePlan(
            steps=steps,
            object_name=self._object_edit.text().strip(),
            repeat=int(self._repeat_spin.value()),
            autofocus_every_n=int(self._af_spin.value()),
            autofocus_on_filter_change=self._af_filter_chk.isChecked(),
            on_complete=self._on_complete_combo.currentText(),
        )

    def load_plan(self, plan: SequencePlan) -> None:
        """Replace the whole editor state with ``plan`` (preset load)."""
        self._table.setRowCount(0)
        for step in plan.steps or [SequenceStep()]:
            self._add_row(step)
        self._object_edit.setText(plan.object_name)
        self._repeat_spin.setValue(max(1, plan.repeat))
        self._af_spin.setValue(max(0, plan.autofocus_every_n))
        self._af_filter_chk.setChecked(plan.autofocus_on_filter_change)
        idx = self._on_complete_combo.findText(plan.on_complete)
        self._on_complete_combo.setCurrentIndex(max(0, idx))
        self._refresh_estimate()

    # ------------------------------------------------------------------
    # Presets (JSON on disk)
    # ------------------------------------------------------------------

    def _presets_dir(self) -> str:
        d = Path.home() / "Argos" / "sequences"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _on_save_preset(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save sequence preset", self._presets_dir(), "Sequence preset (*.json)"
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        try:
            Path(path).write_text(json.dumps(plan_to_dict(self.to_plan()), indent=2))
            self.set_status(f"Preset saved: {Path(path).name}")
        except OSError as exc:
            self.set_status(f"Preset save failed: {exc}")

    def _on_load_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load sequence preset", self._presets_dir(), "Sequence preset (*.json)"
        )
        if not path:
            return
        try:
            plan = plan_from_dict(json.loads(Path(path).read_text()))
        except (OSError, ValueError, TypeError) as exc:
            self.set_status(f"Preset load failed: {exc}")
            return
        self.load_plan(plan)
        self.set_status(f"Preset loaded: {Path(path).name}")

    # ------------------------------------------------------------------
    # Public API (called by ImagingPage)
    # ------------------------------------------------------------------

    def set_camera_limits(
        self,
        gain_min: int | None = None,
        gain_max: int | None = None,
        exposure_min: float | None = None,
        exposure_max: float | None = None,
    ) -> None:
        """Retarget the per-step exposure/gain spinboxes to the connected
        camera's driver-reported limits; ``None``s restore the defaults."""
        if gain_min is not None and gain_max is not None and gain_max > gain_min:
            self._gain_range = (int(gain_min), int(gain_max))
        else:
            self._gain_range = _DEFAULT_GAIN_RANGE
        if exposure_min is not None and exposure_max is not None:
            lo = max(float(exposure_min), _DEFAULT_EXPOSURE_RANGE[0])
            if exposure_max > lo:
                self._exposure_range = (lo, float(exposure_max))
            else:
                self._exposure_range = _DEFAULT_EXPOSURE_RANGE
        else:
            self._exposure_range = _DEFAULT_EXPOSURE_RANGE
        for r in range(self._table.rowCount()):
            self._table.cellWidget(r, 3).setRange(*self._exposure_range)
            self._table.cellWidget(r, 4).setRange(*self._gain_range)

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
        self._pause_btn.setEnabled(running)
        self._stop_btn.setEnabled(running)
        self._table.setEnabled(not running)
        self._progress.setVisible(running)
        if not running:
            self._status_lbl.setText("")
            self.set_paused(False)
            self.set_active_step(-1)

    def set_paused(self, paused: bool) -> None:
        """Reflect the worker's pause state on the button."""
        self._paused = paused
        self._pause_btn.setText("▶  Resume" if paused else "⏸  Pause")
        if paused:
            self._status_lbl.setText("Paused — the current frame was saved.")

    def set_active_step(self, index: int) -> None:
        """Highlight the running step's row (-1 clears)."""
        self._active_row = index
        for r in range(self._table.rowCount()):
            for col in range(self._table.columnCount()):
                w = self._table.cellWidget(r, col)
                if w is not None:
                    w.setStyleSheet(f"background:{theme.SURFACE_3};" if r == index else "")

    def set_progress(self, done: int, total: int, eta_seconds: float) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(done)
        self._progress.setFormat(f"%v / {total}")
        self._status_lbl.setText(f"Frame {done}/{total} — ETA {_format_duration(eta_seconds)}")

    def set_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refresh_estimate(self, *_args) -> None:
        try:
            est = estimated_duration_s(self.to_plan())
        except (AttributeError, RuntimeError):
            return  # a row is mid-construction
        self._estimate_lbl.setText(f"≈ {_format_duration(est)} total" if est > 0 else "")

    def _on_pause_clicked(self) -> None:
        if self._paused:
            self.resume_requested.emit()
        else:
            self.pause_requested.emit()

    def _on_start(self) -> None:
        plan = self.to_plan()
        if not any(s.enabled and s.count > 0 for s in plan.steps):
            self._status_lbl.setText("Add at least one enabled step.")
            self._status_lbl.setStyleSheet(f"color:{theme.WARNING};")
            return
        self._status_lbl.setStyleSheet("")
        self.start_requested.emit(plan)
