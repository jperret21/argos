"""Camera dock — capture controls for the Acquisition page's Capture tab.

Owns nothing about hardware; the ImagingPage wires this widget's signals
to the Camera/Telescope/Worker objects. Keeping the dock UI-only makes it
testable headless and lets the same control surface drive a future
simulator or remote camera.

Numeric parameters (exposure, gain, frame count) use the ``SliderSpin``
composite from the design system — a slider for quick coarse changes plus a
value box for exact entry, the idiom used by NINA / SharpCap. Exposure runs on
a logarithmic slider because its range spans four orders of magnitude.

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
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QSizePolicy,
    QWidget,
)

from seercontrol.ui import design, theme

logger = logging.getLogger(__name__)


_FRAME_TYPES = ("Light Frame", "Dark Frame", "Flat Frame", "Bias Frame")
_DEFAULT_FILTERS = ("LP", "IR-cut", "Dark")


@dataclass(frozen=True)
class CaptureParams:
    """Snapshot of the form values when the user clicks ▶."""

    frame_type: str
    object_name: str
    filter_name: str
    exposure_s: float
    gain: int
    frames: int


class CameraDock(design.Card):
    """Compact camera control group for the Capture tab."""

    take_shot_clicked = pyqtSignal()
    # sequence_toggled carries True when the user starts a sequence,
    # False when they stop it mid-flight.
    sequence_toggled = pyqtSignal(bool)

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

        # Two-column grid: labels left (fixed), controls right (stretch). Every
        # control fills the same column width so the form lines up.
        grid = QGridLayout()
        grid.setHorizontalSpacing(design.SPACING_MD)
        grid.setVerticalSpacing(design.SPACING_SM)
        grid.setColumnStretch(1, 1)

        row = 0
        grid.addWidget(design.MutedLabel("Type"), row, 0)
        self._type_combo = self._combo(_FRAME_TYPES)
        grid.addWidget(self._type_combo, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Object"), row, 0)
        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("M42, T CrB…")
        grid.addWidget(self._object_edit, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Filter"), row, 0)
        self._filter_combo = self._combo(_DEFAULT_FILTERS)
        grid.addWidget(self._filter_combo, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Exposure"), row, 0)
        self._exp = design.SliderSpin(
            0.01, 600.0, 10.0, decimals=2, step=1.0, suffix=" s", logarithmic=True
        )
        grid.addWidget(self._exp, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Gain"), row, 0)
        self._gain = design.SliderSpin(0, 600, 80)
        grid.addWidget(self._gain, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Frames"), row, 0)
        self._count = design.SliderSpin(1, 1000, 10)
        grid.addWidget(self._count, row, 1)

        outer.addLayout(grid)

        # Quality indicator — live HFD.
        hfd_row = QHBoxLayout()
        hfd_row.setSpacing(design.SPACING_MD)
        hfd_row.addWidget(design.MutedLabel("HFD"))
        self._hfd_lbl = design.MetricLabel("—")
        hfd_row.addWidget(self._hfd_lbl)
        hfd_row.addStretch()
        outer.addLayout(hfd_row)

        # Action buttons side-by-side. "Sequence" is the dominant workflow.
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

    @staticmethod
    def _combo(items: tuple[str, ...]) -> QComboBox:
        """A combo that expands to the grid column so all combos match width."""
        combo = QComboBox()
        for item in items:
            combo.addItem(item)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return combo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def params(self) -> CaptureParams:
        return CaptureParams(
            frame_type=self._type_combo.currentText(),
            object_name=self._object_edit.text().strip() or "Unknown",
            filter_name=self._filter_combo.currentText(),
            exposure_s=float(self._exp.value()),
            gain=int(self._gain.value()),
            frames=int(self._count.value()),
        )

    def set_enabled(self, connected: bool) -> None:
        """Gate only the action buttons; the form stays editable always.

        Users want to plan their session (object, filter, gain, exposure)
        *before* the camera is connected — graying everything out until
        connection made the app feel broken.
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
            f"color:{color}; font-size:{design.FONT_SIZE_METRIC}px; font-weight:bold;"
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
