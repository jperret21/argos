"""Camera dock — single-shot capture controls for the Capture tab.

The Capture tab is where you frame and test-shoot while focusing; the full
multi-step acquisition plan lives in the Sequence tab. So this dock owns the
live/single-frame parameters (type, object, filter, exposure, gain) and a
"Shot" button. Numeric parameters use the ``SliderSpin`` composite (slider +
value box), the idiom from NINA / SharpCap; exposure runs on a log slider.

UI-only — the ImagingPage wires the signal to the camera/worker.

Public surface:
    Signals
        take_shot_clicked()
    Methods (called by ImagingPage)
        params()       -> CaptureParams
        set_enabled(connected: bool)
        set_filter_options(names: list[str])
        set_hfd(value: float | None)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from seercontrol.ui import design, theme

logger = logging.getLogger(__name__)


_FRAME_TYPES = ("Light Frame", "Dark Frame", "Flat Frame", "Bias Frame")
_DEFAULT_FILTERS = ("LP", "IR-cut", "Dark")


@dataclass(frozen=True)
class CaptureParams:
    """Snapshot of the live capture form values."""

    frame_type: str
    object_name: str
    filter_name: str
    exposure_s: float
    gain: int


class CameraDock(design.Card):
    """Single-shot capture controls for the Capture tab."""

    take_shot_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Camera", parent)
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

        outer.addLayout(grid)

        # Quality indicator — live HFD.
        hfd_row = QHBoxLayout()
        hfd_row.setSpacing(design.SPACING_MD)
        hfd_row.addWidget(design.MutedLabel("HFD"))
        self._hfd_lbl = design.MetricLabel("—")
        hfd_row.addWidget(self._hfd_lbl)
        hfd_row.addStretch()
        outer.addLayout(hfd_row)

        self._take_btn = design.PrimaryButton("◉  Take shot")
        self._take_btn.setToolTip("Expose one frame and save it (for framing / focus checks)")
        self._take_btn.clicked.connect(self.take_shot_clicked)
        outer.addLayout(design.button_row(self._take_btn))

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
        )

    def set_enabled(self, connected: bool) -> None:
        """Gate the Shot button; the form stays editable so a session can be
        planned before the camera is connected."""
        self._take_btn.setEnabled(connected)

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
