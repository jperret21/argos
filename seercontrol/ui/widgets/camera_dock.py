"""Camera dock — right-side capture controls for the Imaging mode.

Owns nothing about hardware; the ImagingPage wires this widget's signals
to the Camera/Telescope/Worker objects. Keeping the dock UI-only makes it
testable headless and lets the same control surface drive a future
simulator or remote camera.

Public surface:
    Signals
        take_shot_clicked()
        sequence_toggled(start: bool)        # True = Start, False = Stop
    Methods (called by ImagingPage)
        params()       -> CaptureParams
        set_enabled(connected: bool)
        set_filter_options(names: list[str])
        set_hfd(value: float | None)
        set_progress(current: int, total: int, eta_seconds: float)
        clear_progress()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QWidget,
)

from seercontrol.ui import design, theme

logger = logging.getLogger(__name__)


_FRAME_TYPES = ("Light Frame", "Dark Frame", "Flat Frame", "Bias Frame")
_DEFAULT_FILTERS = ("LP", "IR-cut", "Dark")


@dataclass(frozen=True)
class CaptureParams:
    """Snapshot of the form values when the user clicks ▶."""

    frame_type:  str
    object_name: str
    filter_name: str
    exposure_s:  float
    gain:        int
    frames:      int


class CameraDock(design.Card):
    """Compact camera control group for the right side of the Imaging page."""

    take_shot_clicked = pyqtSignal()
    # sequence_toggled carries True when the user starts a sequence,
    # False when they stop it mid-flight.
    sequence_toggled  = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Camera", parent)
        self._in_sequence = False
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        form = QFormLayout()
        form.setHorizontalSpacing(design.SPACING_MD)
        form.setVerticalSpacing(design.SPACING_SM)

        self._type_combo = QComboBox()
        for ft in _FRAME_TYPES:
            self._type_combo.addItem(ft)
        form.addRow(design.MutedLabel("Type"), self._type_combo)

        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("M42, T CrB…")
        form.addRow(design.MutedLabel("Object"), self._object_edit)

        self._filter_combo = QComboBox()
        for f in _DEFAULT_FILTERS:
            self._filter_combo.addItem(f)
        form.addRow(design.MutedLabel("Filter"), self._filter_combo)

        self._exp_spin = QDoubleSpinBox()
        self._exp_spin.setRange(0.001, 600.0)
        self._exp_spin.setDecimals(2)
        self._exp_spin.setValue(10.0)
        self._exp_spin.setSuffix(" s")
        self._exp_spin.setSingleStep(1.0)
        form.addRow(design.MutedLabel("Exposure"), self._exp_spin)

        self._gain_spin = QSpinBox()
        self._gain_spin.setRange(0, 600)
        self._gain_spin.setValue(80)
        form.addRow(design.MutedLabel("Gain"), self._gain_spin)

        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 9999)
        self._count_spin.setValue(10)
        form.addRow(design.MutedLabel("Frames"), self._count_spin)

        outer.addLayout(form)

        # Quality indicator — live HFD.
        hfd_row = QHBoxLayout()
        hfd_row.setSpacing(design.SPACING_MD)
        hfd_row.addWidget(design.MutedLabel("HFD"))
        self._hfd_lbl = design.MetricLabel("—")
        hfd_row.addWidget(self._hfd_lbl)
        hfd_row.addStretch()
        outer.addLayout(hfd_row)

        # Action buttons side-by-side. "Sequence" is the dominant workflow
        # (many frames) so it gets twice the stretch + the success colour.
        self._take_btn = design.SecondaryButton("◉  Shot")
        self._take_btn.setToolTip("Take one frame and save it")
        self._take_btn.clicked.connect(self.take_shot_clicked)
        self._seq_btn = design.SuccessButton("▶  Sequence")
        self._seq_btn.setToolTip("Run the configured number of frames")
        self._seq_btn.clicked.connect(self._on_sequence_clicked)
        outer.addLayout(design.button_row(self._take_btn, self._seq_btn))

        # Progress (hidden until a sequence runs).
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        outer.addWidget(self._progress)

        self._eta_lbl = design.MutedLabel("")
        self._eta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._eta_lbl.setVisible(False)
        outer.addWidget(self._eta_lbl)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def params(self) -> CaptureParams:
        return CaptureParams(
            frame_type=self._type_combo.currentText(),
            object_name=self._object_edit.text().strip() or "Unknown",
            filter_name=self._filter_combo.currentText(),
            exposure_s=float(self._exp_spin.value()),
            gain=int(self._gain_spin.value()),
            frames=int(self._count_spin.value()),
        )

    def set_enabled(self, connected: bool) -> None:
        """Gate only the action buttons; the form stays editable always.

        Users want to plan their session (set object name, filter, gain,
        exposure) *before* the camera is connected — the legacy behaviour of
        graying out everything until connection made the app feel broken.
        """
        self._take_btn.setEnabled(connected)
        self._seq_btn.setEnabled(connected)

    def set_filter_options(self, names: list[str]) -> None:
        """Refresh the filter combo from the filter wheel slots."""
        current = self._filter_combo.currentText()
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        for n in names or _DEFAULT_FILTERS:
            self._filter_combo.addItem(n)
        idx = self._filter_combo.findText(current)
        if idx >= 0:
            self._filter_combo.setCurrentIndex(idx)
        self._filter_combo.blockSignals(False)

    def set_hfd(self, value: float | None) -> None:
        if value is None:
            self._hfd_lbl.setText("—")
            color = theme.FG_MUTED
        else:
            self._hfd_lbl.setText(f"{value:.1f} px")
            color = design.stat_color(value, ok_below=5, warn_below=10)
        self._hfd_lbl.setStyleSheet(
            f"color:{color}; font-size:13px; font-weight:bold;"
            f" font-family:{theme.FONT_MONO}; background:transparent;"
        )

    def set_progress(self, current: int, total: int, eta_seconds: float) -> None:
        if not self._in_sequence:
            self._set_in_sequence(True)
        self._progress.setRange(0, max(1, total))
        self._progress.setFormat(f"%v / {total}")
        self._progress.setValue(current)
        m, s = divmod(max(0, int(eta_seconds)), 60)
        self._eta_lbl.setText(f"Frame {current}/{total} — ETA {m}m {s:02d}s")

    def clear_progress(self) -> None:
        if self._in_sequence:
            self._set_in_sequence(False)
        self._progress.setValue(0)
        self._eta_lbl.setText("")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_sequence_clicked(self) -> None:
        self._set_in_sequence(not self._in_sequence)
        self.sequence_toggled.emit(self._in_sequence)

    def _set_in_sequence(self, running: bool) -> None:
        self._in_sequence = running
        if running:
            self._seq_btn.setText("■  Stop")
            self._seq_btn.setProperty("class", "danger")
            self._progress.setVisible(True)
            self._eta_lbl.setVisible(True)
        else:
            self._seq_btn.setText("▶  Sequence")
            self._seq_btn.setProperty("class", "success")
            self._progress.setVisible(False)
            self._eta_lbl.setVisible(False)
        self._seq_btn.style().unpolish(self._seq_btn)
        self._seq_btn.style().polish(self._seq_btn)
