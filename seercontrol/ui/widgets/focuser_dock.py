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

import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from seercontrol.ui import design, theme

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
        self._hfd_hist: list[float] = []
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        # Live status — position + temperature side-by-side
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

        outer.addWidget(design.horizontal_divider())

        # Step-size selector + In / Out buttons
        step_form = QFormLayout()
        step_form.setHorizontalSpacing(design.SPACING_MD)
        step_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._step_combo = QComboBox()
        for v in _STEP_PRESETS:
            self._step_combo.addItem(str(v))
        self._step_combo.setCurrentText("100")
        step_form.addRow(design.MutedLabel("Step"), self._step_combo)
        outer.addLayout(step_form)

        jog_row = QHBoxLayout()
        jog_row.setSpacing(design.SPACING_SM)
        self._out_btn = design.SecondaryButton("◀  Out")
        self._out_btn.setToolTip("Move focuser outward (position decreases)")
        self._out_btn.clicked.connect(self._on_step_out)
        self._in_btn = design.SecondaryButton("In  ▶")
        self._in_btn.setToolTip("Move focuser inward (position increases)")
        self._in_btn.clicked.connect(self._on_step_in)
        jog_row.addWidget(self._out_btn, 1)
        jog_row.addWidget(self._in_btn, 1)
        outer.addLayout(jog_row)

        # Manual go-to (absolute)
        goto_form = QFormLayout()
        goto_form.setHorizontalSpacing(design.SPACING_MD)
        goto_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._goto_spin = QSpinBox()
        self._goto_spin.setRange(0, 200_000)
        self._goto_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._goto_spin.setMinimumHeight(design.INPUT_HEIGHT)
        goto_form.addRow(design.MutedLabel("Go to"), self._goto_spin)
        outer.addLayout(goto_form)
        goto_btn = design.PrimaryButton("▶  Move to")
        goto_btn.clicked.connect(self._on_move_to)
        outer.addLayout(design.button_row(goto_btn))

        outer.addWidget(design.horizontal_divider())

        # Halt + autofocus
        self._halt_btn = design.DangerButton("■  Halt")
        self._halt_btn.clicked.connect(self.halt_requested)
        outer.addLayout(design.button_row(self._halt_btn))

        self._af_btn = design.SuccessButton("⚡  Autofocus")
        self._af_btn.clicked.connect(self._on_autofocus)
        outer.addLayout(design.button_row(self._af_btn))

        # Autofocus status label (hidden when idle)
        self._af_status = QLabel("")
        self._af_status.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
        )
        self._af_status.hide()
        outer.addWidget(self._af_status)

        # Focus quality — HFD trend + per-frame readouts (§5 / §7).
        outer.addWidget(design.horizontal_divider())
        outer.addWidget(design.SectionLabel("Focus quality"))
        self._trend = pg.PlotWidget()
        self._trend.setBackground(theme.BG2)
        self._trend.setMinimumHeight(90)
        self._trend.setMaximumHeight(120)
        self._trend.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._trend.showGrid(x=False, y=True, alpha=0.2)
        self._trend.getAxis("bottom").setTextPen(pg.mkPen(theme.FG_MUTED))
        self._trend.getAxis("left").setTextPen(pg.mkPen(theme.FG_MUTED))
        self._trend_curve = self._trend.plot(
            pen=pg.mkPen(theme.ACCENT, width=2),
            symbol="o",
            symbolSize=4,
            symbolBrush=theme.ACCENT,
        )
        outer.addWidget(self._trend)

        qual = QFormLayout()
        qual.setHorizontalSpacing(design.SPACING_MD)
        qual.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._hfd_q_lbl = design.MetricLabel("—")
        self._stars_lbl = design.MetricLabel("—")
        self._sky_lbl = design.MetricLabel("—")
        qual.addRow(design.MutedLabel("HFD"), self._hfd_q_lbl)
        qual.addRow(design.MutedLabel("Stars"), self._stars_lbl)
        qual.addRow(design.MutedLabel("Sky"), self._sky_lbl)
        outer.addLayout(qual)

        # Keep track of all action widgets for set_enabled
        self._action_widgets = [
            self._step_combo,
            self._out_btn,
            self._in_btn,
            self._goto_spin,
            goto_btn,
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
        else:
            self._af_status.hide()

    def set_autofocus_status(self, text: str) -> None:
        self._af_status.setText(text)
        if text:
            self._af_status.show()

    def push_metrics(self, metrics) -> None:
        """Append a frame's metrics to the HFD trend + quality readouts."""
        hfd = metrics.hfd
        if hfd is not None:
            self._hfd_hist.append(float(hfd))
            del self._hfd_hist[:-100]  # keep the last 100 frames
            self._trend_curve.setData(list(range(len(self._hfd_hist))), self._hfd_hist)
        self._hfd_q_lbl.setText(f"{hfd:.1f} px" if hfd is not None else "—")
        self._stars_lbl.setText(str(metrics.star_count))
        self._sky_lbl.setText(f"{metrics.sky_adu:.0f}")

    def clear_metrics(self) -> None:
        """Reset the HFD trend (e.g. when switching targets)."""
        self._hfd_hist.clear()
        self._trend_curve.setData([], [])

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
