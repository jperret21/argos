"""Sequencer panel — plan and run multi-frame acquisition sequences.

Dockable panel providing:
  - Frame type selector (Light / Dark / Flat / Bias)
  - Count, exposure, gain, filter, object name
  - Save folder chooser (QFileDialog) with Siril-compatible subfolder layout
  - Start / Stop / Pause controls
  - Progress bar + frame counter + estimated time remaining
  - Log of saved file paths
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.config import Config
from seercontrol.core.imaging.sequencer import FrameType, SequenceConfig
from seercontrol.ui import theme
from seercontrol.workers.sequence_worker import SequenceWorker

logger = logging.getLogger(__name__)

_FILTERS = ["LRGB", "Ha", "OIII", "SII", "IR-cut"]


class SequencerPanel(QWidget):
    """Multi-frame acquisition sequencer.

    Signals:
        log_message:   (level, message) for the session log.
        status_changed: Short status string for the main window status bar.
    """

    log_message    = pyqtSignal(str, str)
    status_changed = pyqtSignal(str)

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config    = config
        self._camera    = None
        self._telescope = None
        self._worker: SequenceWorker | None = None
        self._seq_start: datetime | None = None
        self._build_ui()
        self._load_folder()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        root.addWidget(self._build_config_group())
        root.addWidget(self._build_folder_group())
        root.addWidget(self._build_progress_group())
        root.addWidget(self._build_log_group(), stretch=1)

    def _build_config_group(self) -> QGroupBox:
        grp = QGroupBox("Sequence")
        form = QFormLayout(grp)
        form.setSpacing(8)

        # Frame type
        self._type_combo = QComboBox()
        for ft in FrameType:
            self._type_combo.addItem(ft.label, userData=ft)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Frame type:", self._type_combo)

        # Object name (Lights only)
        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("e.g. M42, NGC 7000")
        self._object_row_lbl = QLabel("Object:")
        form.addRow(self._object_row_lbl, self._object_edit)

        # Filter (Lights + Flats)
        self._filter_combo = QComboBox()
        for f in _FILTERS:
            self._filter_combo.addItem(f)
        self._filter_row_lbl = QLabel("Filter:")
        form.addRow(self._filter_row_lbl, self._filter_combo)

        # Frame count
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 9999)
        self._count_spin.setValue(10)
        form.addRow("Frames:", self._count_spin)

        # Exposure (disabled for Bias)
        self._exp_spin = QDoubleSpinBox()
        self._exp_spin.setRange(0.001, 3600.0)
        self._exp_spin.setDecimals(1)
        self._exp_spin.setValue(60.0)
        self._exp_spin.setSuffix("  s")
        self._exp_spin.setSingleStep(10.0)
        self._exp_row_lbl = QLabel("Exposure:")
        form.addRow(self._exp_row_lbl, self._exp_spin)

        # Gain
        self._gain_spin = QSpinBox()
        self._gain_spin.setRange(0, 600)
        self._gain_spin.setValue(80)
        form.addRow("Gain:", self._gain_spin)

        self._on_type_changed()   # set initial row visibility
        return grp

    def _build_folder_group(self) -> QGroupBox:
        grp = QGroupBox("Save Folder")
        lay = QVBoxLayout(grp)
        lay.setSpacing(6)

        # Folder path row
        path_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select output folder…")
        self._folder_edit.setReadOnly(True)

        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.setFixedWidth(80)
        self._browse_btn.clicked.connect(self._on_browse)

        path_row.addWidget(self._folder_edit, stretch=1)
        path_row.addWidget(self._browse_btn)
        lay.addLayout(path_row)

        # Preview of generated structure
        self._structure_lbl = QLabel()
        self._structure_lbl.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:11px; font-family:monospace;"
        )
        self._structure_lbl.setWordWrap(True)
        lay.addWidget(self._structure_lbl)

        # Wire updates
        self._type_combo.currentIndexChanged.connect(self._refresh_structure_preview)
        self._object_edit.textChanged.connect(self._refresh_structure_preview)
        self._filter_combo.currentIndexChanged.connect(self._refresh_structure_preview)

        return grp

    def _build_progress_group(self) -> QGroupBox:
        grp = QGroupBox("Progress")
        lay = QVBoxLayout(grp)
        lay.setSpacing(6)

        # Controls row
        ctrl_row = QHBoxLayout()
        self._start_btn = QPushButton("▶  Start Sequence")
        self._start_btn.setFixedHeight(30)
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_start)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setFixedHeight(30)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(f"background-color:{theme.DANGER};")
        self._stop_btn.clicked.connect(self._on_stop)

        self._status_lbl = QLabel("—")
        self._status_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")

        ctrl_row.addWidget(self._start_btn)
        ctrl_row.addWidget(self._stop_btn)
        ctrl_row.addWidget(self._status_lbl, stretch=1)
        lay.addLayout(ctrl_row)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%v / %m frames")
        self._progress_bar.setTextVisible(True)
        lay.addWidget(self._progress_bar)

        # ETA row
        eta_row = QHBoxLayout()
        self._eta_lbl = QLabel("")
        self._eta_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")
        eta_row.addWidget(self._eta_lbl)
        eta_row.addStretch()
        lay.addLayout(eta_row)

        return grp

    def _build_log_group(self) -> QGroupBox:
        grp = QGroupBox("Saved Files")
        lay = QVBoxLayout(grp)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumHeight(120)
        self._log_edit.setStyleSheet(
            f"background:{theme.SURFACE_3}; color:{theme.TEXT_MUTED}; font-size:10px; font-family:monospace;"
        )
        lay.addWidget(self._log_edit)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.setFixedHeight(20)
        clear_btn.clicked.connect(self._log_edit.clear)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(clear_btn)
        lay.addLayout(row)
        return grp

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_camera(self, camera) -> None:
        """Called by main window when camera connects/disconnects."""
        self._camera = camera
        self._refresh_start_button()

    def set_telescope(self, telescope) -> None:
        """Called by main window when telescope connects/disconnects."""
        self._telescope = telescope

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_type_changed(self) -> None:
        ft = self._current_frame_type()
        self._object_row_lbl.setVisible(ft.needs_object)
        self._object_edit.setVisible(ft.needs_object)
        self._filter_row_lbl.setVisible(ft.needs_filter)
        self._filter_combo.setVisible(ft.needs_filter)
        self._exp_row_lbl.setVisible(ft.needs_exposure)
        self._exp_spin.setVisible(ft.needs_exposure)
        self._refresh_structure_preview()

    def _on_browse(self) -> None:
        start = self._folder_edit.text() or str(Path.home() / "SeerControl")
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose save folder", start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if chosen:
            self._folder_edit.setText(chosen)
            self._config.set("sequencer.save_folder", chosen)
            self._refresh_structure_preview()
            self._refresh_start_button()

    def _on_start(self) -> None:
        if not self._camera or not self._folder_edit.text():
            return

        cfg = self._build_config()
        total = cfg.count

        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(0)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._seq_start = datetime.now(timezone.utc)
        self._status_lbl.setText("Running…")

        worker = SequenceWorker(
            camera=self._camera,
            config=cfg,
            telescope=self._telescope,
            observer=self._config.get("observer.name", ""),
            site_lat=self._config.get("observer.latitude"),
            site_lon=self._config.get("observer.longitude"),
            site_elev=self._config.get("observer.elevation"),
        )
        worker.progress.connect(self._on_progress)
        worker.frame_saved.connect(self._on_frame_saved)
        worker.status_updated.connect(self._status_lbl.setText)
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(self._on_finished)
        self._worker = worker
        worker.start()

        folder_str = str(cfg.frame_folder(self._seq_start))
        self._log("info", f"Sequence started: {total} × {cfg.frame_type.label}  → {folder_str}")
        self.status_changed.emit(f"Sequence running: 0/{total}")

    def _on_stop(self) -> None:
        if self._worker:
            self._worker.stop()
        self._status_lbl.setText("Stopping…")
        self._stop_btn.setEnabled(False)

    def _on_progress(self, done: int, total: int) -> None:
        self._progress_bar.setValue(done)
        self.status_changed.emit(f"Sequence: {done}/{total}")

        if self._seq_start and done > 0:
            elapsed = (datetime.now(timezone.utc) - self._seq_start).total_seconds()
            remaining = elapsed / done * (total - done)
            m, s = divmod(int(remaining), 60)
            self._eta_lbl.setText(f"ETA  ~{m}m {s:02d}s")

    def _on_frame_saved(self, path: str) -> None:
        self._log_edit.append(Path(path).name)

    def _on_finished(self, saved: int) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._eta_lbl.setText("")
        self._log("info", f"Sequence complete: {saved} frames saved")
        self.status_changed.emit(f"Sequence done: {saved} frames")
        self._worker = None

    def _on_error(self, msg: str) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._log("error", f"Sequence error: {msg}")
        self._worker = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_frame_type(self) -> FrameType:
        return self._type_combo.currentData() or FrameType.LIGHT

    def _build_config(self) -> SequenceConfig:
        ft = self._current_frame_type()
        return SequenceConfig(
            frame_type=ft,
            count=self._count_spin.value(),
            exposure=self._exp_spin.value(),
            gain=self._gain_spin.value(),
            filter_name=self._filter_combo.currentText() if ft.needs_filter else "NoFilter",
            object_name=self._object_edit.text().strip() if ft.needs_object else "",
            save_folder=Path(self._folder_edit.text()) if self._folder_edit.text() else Path.home() / "SeerControl",
        )

    def _refresh_structure_preview(self) -> None:
        folder = self._folder_edit.text()
        if not folder:
            self._structure_lbl.setText("")
            return

        ft = self._current_frame_type()
        obj = self._object_edit.text().strip() if ft.needs_object else ""
        date_str = datetime.now().strftime("%Y%m%d")
        session = f"{date_str}_{obj or ('calibration' if not ft.needs_object else 'Target')}"
        sub = ft.siril_folder

        self._structure_lbl.setText(
            f"{Path(folder).name}/{session}/{sub}/*.fits"
        )

    def _refresh_start_button(self) -> None:
        self._start_btn.setEnabled(
            self._camera is not None and bool(self._folder_edit.text())
        )

    def _load_folder(self) -> None:
        saved = self._config.get("sequencer.save_folder", "")
        if saved:
            self._folder_edit.setText(saved)
        self._refresh_structure_preview()
        self._refresh_start_button()

    def _log(self, level: str, msg: str) -> None:
        logger.log({"info": 20, "warning": 30, "error": 40}.get(level, 20), msg)
        self.log_message.emit(level, msg)

    def shutdown(self) -> None:
        """Call before closing the application."""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(10000)
