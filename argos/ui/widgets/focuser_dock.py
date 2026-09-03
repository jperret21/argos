"""Focuser dock — compact right-rail focuser control for the Imaging page.

Public surface:
    Signals
        step_requested(int)         # ±N steps
        halt_requested()
        autofocus_requested()
        move_to_requested(int)      # absolute position
    Methods (called by ImagingPage)
        set_enabled(connected: bool)
        set_position(pos: int)
        set_temperature(temp: float | None)
        set_moving(moving: bool)
        set_autofocus_running(running: bool)
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from argos.ui import design, theme
from argos.ui.widgets.vcurve import VCurveWidget

logger = logging.getLogger(__name__)

_STEP_PRESETS = (1, 10, 50, 100, 500, 1000)


class FocuserDock(design.Card):
    """Compact focuser control group for the right side of the Imaging page."""

    step_requested = pyqtSignal(int)  # positive = inward / increase pos
    halt_requested = pyqtSignal()
    autofocus_requested = pyqtSignal()
    move_to_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Focuser", parent)
        self._autofocus_running = False
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)
        outer.setSpacing(design.SPACING_SM)

        # Live status — compact, immediately useful context.
        status = QGridLayout()
        status.setSpacing(design.SPACING_SM)
        status.setColumnStretch(1, 1)
        status.setColumnStretch(3, 1)

        self._pos_lbl = design.MetricLabel("—")
        self._temp_lbl = design.MetricLabel("—")

        status.addWidget(design.MutedLabel("Position"), 0, 0)
        status.addWidget(self._pos_lbl, 0, 1)
        status.addWidget(design.MutedLabel("Temp"), 0, 2)
        status.addWidget(self._temp_lbl, 0, 3)
        outer.addLayout(status)

        # Manual adjustment is one compact grid rather than three full-width
        # form rows.  It reads left-to-right in the order an observer uses it.
        manual = QGridLayout()
        manual.setHorizontalSpacing(design.SPACING_SM)
        manual.setVerticalSpacing(design.SPACING_SM)
        manual.setColumnStretch(1, 1)
        manual.setColumnStretch(2, 1)
        manual.setColumnStretch(3, 1)
        self._step_combo = QComboBox()
        for v in _STEP_PRESETS:
            self._step_combo.addItem(str(v))
        self._step_combo.setCurrentText("100")
        self._step_combo.setToolTip("Increment used for each manual focus movement")
        self._out_btn = design.SecondaryButton("◀ Out")
        self._out_btn.setToolTip("Move focuser outward (position decreases)")
        self._out_btn.clicked.connect(self._on_step_out)
        self._in_btn = design.SecondaryButton("In ▶")
        self._in_btn.setToolTip("Move focuser inward (position increases)")
        self._in_btn.clicked.connect(self._on_step_in)
        manual.addWidget(design.MutedLabel("Step"), 0, 0)
        manual.addWidget(self._step_combo, 0, 1)
        manual.addWidget(self._out_btn, 0, 2)
        manual.addWidget(self._in_btn, 0, 3)

        self._goto_spin = QSpinBox()
        self._goto_spin.setRange(0, 200_000)
        self._goto_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._goto_spin.setMinimumHeight(design.INPUT_HEIGHT)
        move_btn = design.SecondaryButton("Move")
        move_btn.setToolTip("Move to the specified absolute focuser position")
        move_btn.clicked.connect(self._on_move_to)
        manual.addWidget(design.MutedLabel("Go to"), 1, 0)
        manual.addWidget(self._goto_spin, 1, 1, 1, 2)
        manual.addWidget(move_btn, 1, 3)
        outer.addLayout(manual)

        outer.addWidget(design.horizontal_divider())

        # Focus actions share a row: autofocus is the ordinary operation;
        # Halt is visible beside it as the emergency interruption, without
        # creating two equally heavy full-width button rows.
        self._halt_btn = design.DangerButton("■  Halt")
        self._halt_btn.clicked.connect(self.halt_requested)
        self._af_btn = design.SuccessButton("⚡  Autofocus")
        self._af_btn.clicked.connect(self._on_autofocus)
        outer.addLayout(design.button_row(self._af_btn, self._halt_btn))

        # Autofocus status label (hidden when idle)
        self._af_status = QLabel("")
        self._af_status.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent;"
        )
        self._af_status.hide()
        outer.addWidget(self._af_status)

        # The V-curve — watch the sweep converge right where you capture.
        # Hidden until the first sweep so the rail stays compact. The per-frame
        # HFD trend + focus-quality read-outs moved to the HFD History dock
        # (WS9b); this dock keeps only the V-curve.
        self.vcurve = VCurveWidget()
        self.vcurve.hide()
        outer.addWidget(self.vcurve)

        # Keep track of all action widgets for set_enabled
        self._action_widgets = [
            self._step_combo,
            self._out_btn,
            self._in_btn,
            self._goto_spin,
            move_btn,
            self._halt_btn,
            self._af_btn,
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_enabled(self, connected: bool) -> None:
        for w in self._action_widgets:
            w.setEnabled(connected)

    def set_position(self, pos: int) -> None:
        self._pos_lbl.setText(f"{pos:,}")
        self._goto_spin.setValue(pos)

    def set_temperature(self, temp: float | None) -> None:
        if temp is None:
            self._temp_lbl.setText("—")
        else:
            self._temp_lbl.setText(f"{temp:.1f}°C")

    def set_moving(self, moving: bool) -> None:
        color = theme.WARNING if moving else theme.ACCENT
        self._pos_lbl.setStyleSheet(
            f"color:{color}; font-size:{design.FONT_SIZE_METRIC}px;"
            f" font-weight:bold; font-family:{theme.FONT_MONO};"
            f" background:transparent;"
        )

    def set_autofocus_running(self, running: bool) -> None:
        self._autofocus_running = running
        self._af_btn.setText("■  Stop AF" if running else "⚡  Autofocus")
        self._af_btn.setProperty("class", "danger" if running else "success")
        self._af_btn.style().unpolish(self._af_btn)
        self._af_btn.style().polish(self._af_btn)
        self._out_btn.setEnabled(not running)
        self._in_btn.setEnabled(not running)
        self._halt_btn.setEnabled(not running)
        if running:
            self._af_status.setText("Autofocus in progress…")
            self._af_status.show()
            self.vcurve.start_sweep()
            self.vcurve.show()  # stays visible after the sweep for read-back
        else:
            self._af_status.hide()

    def set_autofocus_status(self, text: str) -> None:
        self._af_status.setText(text)
        if text:
            self._af_status.show()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _step_value(self) -> int:
        try:
            return int(self._step_combo.currentText())
        except ValueError:
            return 100

    def _on_step_out(self) -> None:
        self.step_requested.emit(-self._step_value())

    def _on_step_in(self) -> None:
        self.step_requested.emit(self._step_value())

    def _on_move_to(self) -> None:
        self.move_to_requested.emit(self._goto_spin.value())

    def _on_autofocus(self) -> None:
        if self._autofocus_running:
            self.halt_requested.emit()
        else:
            self.autofocus_requested.emit()
