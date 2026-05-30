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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seercontrol.ui import theme

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


class CameraDock(QGroupBox):
    """Compact camera control group for the right side of the Imaging page."""

    take_shot_clicked = pyqtSignal()
    sequence_toggled  = pyqtSignal(bool)   # True = start, False = stop

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Camera", parent)
        self._in_sequence = False
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 14, 8, 8)
        outer.setSpacing(8)

        form = QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(5)

        self._type_combo = QComboBox()
        for ft in _FRAME_TYPES:
            self._type_combo.addItem(ft)
        form.addRow("Type", self._type_combo)

        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("M42, T CrB…")
        form.addRow("Object", self._object_edit)

        self._filter_combo = QComboBox()
        for f in _DEFAULT_FILTERS:
            self._filter_combo.addItem(f)
        form.addRow("Filter", self._filter_combo)

        self._exp_spin = QDoubleSpinBox()
        self._exp_spin.setRange(0.001, 600.0)
        self._exp_spin.setDecimals(2)
        self._exp_spin.setValue(10.0)
        self._exp_spin.setSuffix(" s")
        self._exp_spin.setSingleStep(1.0)
        form.addRow("Exposure", self._exp_spin)

        self._gain_spin = QSpinBox()
        self._gain_spin.setRange(0, 600)
        self._gain_spin.setValue(80)
        form.addRow("Gain", self._gain_spin)

        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 9999)
        self._count_spin.setValue(10)
        form.addRow("Frames", self._count_spin)

        outer.addLayout(form)

        # Quality indicator — live HFD.
        hfd_row = QHBoxLayout()
        hfd_row.addWidget(QLabel("HFD:"))
        self._hfd_lbl = QLabel("—")
        self._hfd_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:13px; font-weight:bold;"
            f" font-family:{theme.FONT_MONO};"
        )
        hfd_row.addWidget(self._hfd_lbl)
        hfd_row.addStretch()
        outer.addLayout(hfd_row)

        # Action buttons.
        self._take_btn = QPushButton("◉  Take Shot")
        self._take_btn.setProperty("class", "primary")
        self._take_btn.clicked.connect(self.take_shot_clicked)
        outer.addWidget(self._take_btn)

        self._seq_btn = QPushButton("▶  Start sequence")
        self._seq_btn.setProperty("class", "success")
        self._seq_btn.clicked.connect(self._on_sequence_clicked)
        outer.addWidget(self._seq_btn)

        # Progress (hidden until a sequence runs).
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        outer.addWidget(self._progress)

        self._eta_lbl = QLabel("")
        self._eta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._eta_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:10px; background:transparent;"
        )
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
        self._take_btn.setEnabled(connected)
        self._seq_btn.setEnabled(connected)
        # While disconnected, gate edit controls too — keeps the form honest.
        for w in (self._type_combo, self._filter_combo, self._exp_spin,
                  self._gain_spin, self._count_spin):
            w.setEnabled(connected)

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
            color = theme.SUCCESS if value < 5 else (theme.WARNING if value < 10 else theme.DANGER)
        self._hfd_lbl.setStyleSheet(
            f"color:{color}; font-size:13px; font-weight:bold;"
            f" font-family:{theme.FONT_MONO};"
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
            self._seq_btn.setText("■  Stop sequence")
            self._seq_btn.setProperty("class", "danger")
            self._progress.setVisible(True)
            self._eta_lbl.setVisible(True)
        else:
            self._seq_btn.setText("▶  Start sequence")
            self._seq_btn.setProperty("class", "success")
            self._progress.setVisible(False)
            self._eta_lbl.setVisible(False)
        self._seq_btn.style().unpolish(self._seq_btn)
        self._seq_btn.style().polish(self._seq_btn)
