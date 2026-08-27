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
        live_start_requested()       # user pressed ▶ Live
        live_stop_requested()        # user pressed ■ Stop live
        filter_selected(name: str)   # user picked a filter → move the wheel
        offset_changed(value: int)   # user edited the (driver-backed) offset
        binning_changed(value: int)  # user edited the (driver-backed) binning
        preview_scale_changed(scale: int)  # preview quality: 1 = full, 2 = half
    Methods (called by ImagingPage)
        params()       -> CaptureParams
        preview_scale() -> int
        set_enabled(connected: bool)
        set_live_running(running: bool)
        set_gain_range(lo: int, hi: int)
        set_exposure_range(lo: float, hi: float)
        set_offset_support(lo: int, hi: int, value: int)
        set_binning_support(max_bin: int, value: int)
        reset_camera_limits()        # back to defaults, hide optional rows
        set_filter_options(names: list[str])
        set_current_filter(name: str)
        set_hfd(value: float | None)
        set_temperature(temp: float | None)
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
    QSpinBox,
    QWidget,
)

from argos.ui import design, theme

logger = logging.getLogger(__name__)


_FRAME_TYPES = ("Light Frame", "Dark Frame", "Flat Frame", "Bias Frame")
# Seestar wheel slot names (see alpaca.filterwheel.position_names), light
# filters first so the pre-connect default is shootable. "IR-cut" was wrong:
# no wheel position matched it, so picking it silently never moved the wheel.
_DEFAULT_FILTERS = ("IR", "LP", "Dark")

#: Fallback limits when no camera is connected (the historical hardcodes).
DEFAULT_GAIN_RANGE = (0, 600)
DEFAULT_EXPOSURE_RANGE = (0.01, 600.0)

#: Preview-quality combo entries → LivePreviewWorker decimation factor.
_PREVIEW_QUALITIES = (("Full res", 1), ("Half res", 2))


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
    live_start_requested = pyqtSignal()
    live_stop_requested = pyqtSignal()
    filter_selected = pyqtSignal(str)  # user picked a filter in the combo
    object_changed = pyqtSignal()  # the Object field was edited (focus-out/return)
    object_name_changed = pyqtSignal(str)  # shared observation identity changed
    offset_changed = pyqtSignal(int)
    binning_changed = pyqtSignal(int)
    preview_scale_changed = pyqtSignal(int)  # 1 = full res, 2 = half res

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Camera", parent)
        self._live_running = False
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
        # The object name keys the target set / curves / FITS OBJECT — an edit
        # must re-sync every view, or they keep showing the previous object's
        # stars while the engine measures the new (empty) set.
        self._object_edit.editingFinished.connect(self._on_object_edited)
        grid.addWidget(self._object_edit, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Filter"), row, 0)
        self._filter_combo = self._combo(_DEFAULT_FILTERS)
        # ``activated`` fires only on user interaction — programmatic syncs
        # (set_current_filter / set_filter_options) never trigger a wheel move.
        self._filter_combo.activated.connect(
            lambda _i: self.filter_selected.emit(self._filter_combo.currentText())
        )
        grid.addWidget(self._filter_combo, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Exposure"), row, 0)
        self._exp = design.SliderSpin(
            *DEFAULT_EXPOSURE_RANGE, 10.0, decimals=2, step=1.0, suffix=" s", logarithmic=True
        )
        grid.addWidget(self._exp, row, 1)

        row += 1
        grid.addWidget(design.MutedLabel("Gain"), row, 0)
        self._gain = design.SliderSpin(*DEFAULT_GAIN_RANGE, 80)
        grid.addWidget(self._gain, row, 1)

        # Optional driver-backed parameters — hidden until the connected
        # camera proves it supports them (set_offset_support / set_binning_support).
        row += 1
        self._offset_lbl = design.MutedLabel("Offset")
        self._offset_spin = QSpinBox()
        self._offset_spin.setMinimumHeight(design.INPUT_HEIGHT)
        self._offset_spin.valueChanged.connect(self.offset_changed)
        grid.addWidget(self._offset_lbl, row, 0)
        grid.addWidget(self._offset_spin, row, 1)
        self._offset_lbl.hide()
        self._offset_spin.hide()

        row += 1
        self._bin_lbl = design.MutedLabel("Binning")
        self._bin_spin = QSpinBox()
        self._bin_spin.setRange(1, 1)
        self._bin_spin.setSuffix("×")
        self._bin_spin.setMinimumHeight(design.INPUT_HEIGHT)
        self._bin_spin.valueChanged.connect(self.binning_changed)
        grid.addWidget(self._bin_lbl, row, 0)
        grid.addWidget(self._bin_spin, row, 1)
        self._bin_lbl.hide()
        self._bin_spin.hide()

        # Preview quality — display pipeline only, the saved FITS is always
        # the full sensor readout.
        row += 1
        grid.addWidget(design.MutedLabel("Preview"), row, 0)
        self._quality_combo = self._combo(tuple(label for label, _s in _PREVIEW_QUALITIES))
        self._quality_combo.setToolTip(
            "Preview decimation for display only — saved FITS stay full resolution"
        )
        self._quality_combo.activated.connect(
            lambda _i: self.preview_scale_changed.emit(self.preview_scale())
        )
        grid.addWidget(self._quality_combo, row, 1)

        outer.addLayout(grid)

        # Quality indicators — live HFD + sensor temperature.
        hfd_row = QHBoxLayout()
        hfd_row.setSpacing(design.SPACING_MD)
        hfd_row.addWidget(design.MutedLabel("HFD"))
        self._hfd_lbl = design.MetricLabel("—")
        hfd_row.addWidget(self._hfd_lbl)
        hfd_row.addSpacing(design.SPACING_LG)
        hfd_row.addWidget(design.MutedLabel("Temp"))
        self._temp_lbl = design.MetricLabel("—")
        hfd_row.addWidget(self._temp_lbl)
        hfd_row.addStretch()
        outer.addLayout(hfd_row)

        self._live_btn = design.SuccessButton("▶  Live")
        self._live_btn.setToolTip("Continuous preview loop for framing and manual focusing")
        self._live_btn.clicked.connect(self._on_live_clicked)
        self._take_btn = design.PrimaryButton("◉  Take shot")
        self._take_btn.setToolTip("Expose one frame and save it (for framing / focus checks)")
        self._take_btn.clicked.connect(self.take_shot_clicked)
        outer.addLayout(design.button_row(self._live_btn, self._take_btn))

        # Shown while a sequence owns the camera (set_sequence_lock).
        self._lock_hint = design.MutedLabel("Sequence running — the sequence owns the camera.")
        self._lock_hint.setWordWrap(True)
        self._lock_hint.hide()
        outer.addWidget(self._lock_hint)

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

    def preview_scale(self) -> int:
        """Current preview decimation factor (1 = full res, 2 = half res)."""
        return _PREVIEW_QUALITIES[self._quality_combo.currentIndex()][1]

    def set_enabled(self, connected: bool) -> None:
        """Gate the Shot/Live buttons; the form stays editable so a session
        can be planned before the camera is connected."""
        self._take_btn.setEnabled(connected)
        self._live_btn.setEnabled(connected)

    def set_sequence_lock(self, locked: bool) -> None:
        """Freeze the capture form while a sequence owns the camera (WS8).

        The running SequenceWorker reads its own plan — edits here would only
        desynchronise what the user sees from what the camera does. Take
        shot / Live are already refused by the CameraService; this makes the
        ownership visible instead of letting dead-looking clicks explain it.
        """
        for w in (
            self._type_combo,
            self._object_edit,
            self._filter_combo,
            self._exp,
            self._gain,
            self._offset_spin,
            self._bin_spin,
            self._quality_combo,
        ):
            w.setEnabled(not locked)
        self._lock_hint.setVisible(locked)

    def set_live_running(self, running: bool) -> None:
        """Reflect the live-loop state (the ImagingPage owns the worker)."""
        self._live_running = running
        self._live_btn.setText("■  Stop live" if running else "▶  Live")
        self._live_btn.setProperty("class", "danger" if running else "success")
        self._live_btn.style().unpolish(self._live_btn)
        self._live_btn.style().polish(self._live_btn)

    # -- driver-derived limits (fallbacks when disconnected) ------------

    def set_gain_range(self, lo: int, hi: int) -> None:
        """Retarget the gain slider to the connected camera's GainMin/GainMax."""
        if hi > lo:
            self._gain.setRange(int(lo), int(hi))

    def set_exposure_range(self, lo: float, hi: float) -> None:
        """Retarget the exposure slider to the driver's ExposureMin/ExposureMax.
        The floor is clamped to 0.01 s (the spin's 2-decimal display)."""
        lo = max(float(lo), DEFAULT_EXPOSURE_RANGE[0])
        if hi > lo:
            self._exp.setRange(lo, float(hi))

    def set_offset_support(self, lo: int, hi: int, value: int) -> None:
        """Show the offset spinbox — the driver proved it supports Offset."""
        self._offset_spin.blockSignals(True)
        self._offset_spin.setRange(int(lo), int(hi))
        self._offset_spin.setValue(int(value))
        self._offset_spin.blockSignals(False)
        self._offset_lbl.show()
        self._offset_spin.show()

    def set_binning_support(self, max_bin: int, value: int) -> None:
        """Show the binning spinbox — the driver reports MaxBin > 1."""
        self._bin_spin.blockSignals(True)
        self._bin_spin.setRange(1, max(1, int(max_bin)))
        self._bin_spin.setValue(max(1, int(value)))
        self._bin_spin.blockSignals(False)
        self._bin_lbl.show()
        self._bin_spin.show()

    def reset_camera_limits(self) -> None:
        """Back to the disconnected defaults; hide driver-backed extras."""
        self.set_gain_range(*DEFAULT_GAIN_RANGE)
        self.set_exposure_range(*DEFAULT_EXPOSURE_RANGE)
        self._offset_lbl.hide()
        self._offset_spin.hide()
        self._bin_lbl.hide()
        self._bin_spin.hide()
        self.set_temperature(None)

    def set_object_name_if_empty(self, name: str) -> None:
        """Prefill Object from a picked target while the field is still empty.

        The object name keys the persistent target set and lands in the FITS
        ``OBJECT`` header — left empty it becomes "Unknown", orphaning both.
        A name the user already typed is never overwritten.
        """
        if name and not self._object_edit.text().strip():
            self.set_object_name(name, emit=True)

    def set_object_name(self, name: str, *, emit: bool = False) -> None:
        """Set the shared observation object without creating a signal loop."""
        value = (name or "").strip()
        if self._object_edit.text() == value:
            return
        self._object_edit.setText(value)
        if emit:
            self._on_object_edited()

    def _on_object_edited(self) -> None:
        self.object_changed.emit()
        self.object_name_changed.emit(self._object_edit.text().strip())

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

    def set_current_filter(self, name: str) -> None:
        """Sync the combo to the wheel's real position (no signal emitted)."""
        idx = self._filter_combo.findText(name)
        if idx >= 0:
            self._filter_combo.setCurrentIndex(idx)

    def set_filter_moving(self, moving: bool) -> None:
        """Grey the filter combo while the wheel turns (quiet busy cue)."""
        self._filter_combo.setEnabled(not moving)

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

    def set_temperature(self, temp: float | None) -> None:
        """Sensor (CCD/heat-sink) temperature readout, refreshed by polling."""
        self._temp_lbl.setText("—" if temp is None else f"{temp:.1f}°C")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_live_clicked(self) -> None:
        if self._live_running:
            self.live_stop_requested.emit()
        else:
            self.live_start_requested.emit()
