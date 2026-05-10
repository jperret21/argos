"""Camera control panel — live preview + exposure/gain controls + FITS saving.

Dockable panel providing:
  - Connect / disconnect camera (Alpaca)
  - Live preview loop (repeated short exposures)
  - Exposure time and gain controls
  - FitsViewer for real-time image display
  - Camera state indicator
  - Optional FITS file saving with object name and filter selection
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
from PyQt6.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.config import Config
from seercontrol.core.imaging.fits_writer import FITSWriter
from seercontrol.ui import theme
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.workers.exposure_worker import LivePreviewWorker

logger = logging.getLogger(__name__)


class CameraPanel(QWidget):
    """Live camera preview and exposure control panel.

    Signals:
        log_message: (level, message) for the session log.
        status_changed: Short status string for the main window status bar.
    """

    log_message    = pyqtSignal(str, str)
    status_changed = pyqtSignal(str)

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config  = config
        self._camera:  Camera            | None = None
        self._worker:  LivePreviewWorker | None = None
        self._frame_index: int = 0
        self._last_start: datetime | None = None
        self._last_end:   datetime | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(self._build_connection_group())
        root.addWidget(self._build_controls_group())
        root.addWidget(self._build_save_group())
        root.addWidget(self._build_viewer(), stretch=1)

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Camera Connection")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect Camera")
        self._connect_btn.setProperty("class", "primary")
        self._connect_btn.clicked.connect(self._on_connect)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setProperty("class", "danger")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)

        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        layout.addLayout(btn_row)

        self._status_lbl = QLabel("Disconnected")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:11px; padding:3px;"
        )
        layout.addWidget(self._status_lbl)

        return group

    def _build_controls_group(self) -> QGroupBox:
        group = QGroupBox("Acquisition")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        form = QFormLayout()

        self._exposure_spin = QDoubleSpinBox()
        self._exposure_spin.setRange(0.001, 60.0)
        self._exposure_spin.setDecimals(3)
        self._exposure_spin.setValue(1.0)
        self._exposure_spin.setSuffix("  s")
        self._exposure_spin.setSingleStep(0.5)
        self._exposure_spin.setToolTip("Exposure time per frame")
        form.addRow(_muted("Exposure"), self._exposure_spin)

        self._gain_spin = QSpinBox()
        self._gain_spin.setRange(0, 100)
        self._gain_spin.setValue(80)
        self._gain_spin.setToolTip("Camera gain (0–100 by default)")
        form.addRow(_muted("Gain"), self._gain_spin)

        self._scale_combo = QComboBox()
        for label in ["1× (full res)", "2×", "4×", "8×"]:
            self._scale_combo.addItem(label)
        self._scale_combo.setCurrentIndex(2)  # 4× default — ~960×540 preview
        self._scale_combo.setToolTip(
            "Preview resolution scale.\n"
            "Download is always full resolution.\n"
            "FITS files are saved at full resolution."
        )
        form.addRow(_muted("Preview"), self._scale_combo)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self._preview_btn = QPushButton("▶  Start Preview")
        self._preview_btn.setProperty("class", "success")
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self._on_toggle_preview)

        self._state_lbl = QLabel("—")
        self._state_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")
        self._state_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        btn_row.addWidget(self._preview_btn)
        btn_row.addWidget(self._state_lbl)
        layout.addLayout(btn_row)

        return group

    def _build_save_group(self) -> QGroupBox:
        group = QGroupBox("Save Frames")
        layout = QFormLayout(group)
        layout.setSpacing(6)

        self._save_chk = QCheckBox("Save FITS files")
        self._save_chk.setToolTip("Write each frame to disk as a FITS file")
        layout.addRow(self._save_chk)

        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("e.g. M42, NGC 224")
        self._object_edit.setToolTip("Target object name written to FITS OBJECT header")
        layout.addRow(_muted("Object"), self._object_edit)

        self._filter_combo = QComboBox()
        for f in ["LRGB", "Ha", "OIII", "SII", "IR-cut"]:
            self._filter_combo.addItem(f)
        layout.addRow(_muted("Filter"), self._filter_combo)

        self._save_dir_lbl = QLabel()
        self._save_dir_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
        self._save_dir_lbl.setWordWrap(True)
        layout.addRow(_muted("Output"), self._save_dir_lbl)
        self._update_save_dir_label()

        return group

    def _build_viewer(self) -> QWidget:
        self._viewer = FitsViewer()
        return self._viewer

    def _update_save_dir_label(self) -> None:
        # FITSWriter.session_folder appends ``sessions/{date}_{obj}/...`` to its
        # base argument, so we feed it the parent of ``sessions_path`` to avoid
        # ending up with ``.../sessions/sessions/...``.
        base = self._config.sessions_path.parent
        self._save_dir_lbl.setText(str(base / "sessions" / "…"))

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _on_connect(self) -> None:
        host = self._config.alpaca_host
        port = self._config.alpaca_port

        if not host:
            self._log("ERROR", "No host configured — connect the mount first.")
            return

        self._connect_btn.setEnabled(False)
        self._log("CMD", f"Connecting camera at {host}:{port}…")

        try:
            self._camera = Camera(host=host, port=port)
            name = self._camera.connect()

            self._gain_spin.setRange(self._camera.gain_min, self._camera.gain_max)
            self._gain_spin.setValue(min(80, self._camera.gain_max))

            self._log("OK", f"Camera connected: {name}  "
                            f"{self._camera.width}×{self._camera.height}")
            self._set_connected(True)

        except AlpacaError as exc:
            self._log("ERROR", f"Camera connection failed: {exc}")
            self._camera = None
            self._connect_btn.setEnabled(True)

    def _on_disconnect(self) -> None:
        self._stop_preview()

        if self._camera:
            self._camera.disconnect()
            self._camera = None

        self._set_connected(False)
        self._frame_index = 0
        self._log("INFO", "Camera disconnected.")

    def _set_connected(self, connected: bool) -> None:
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._preview_btn.setEnabled(connected)

        color = theme.SUCCESS if connected else theme.TEXT_MUTED
        text  = "Connected" if connected else "Disconnected"
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; padding:3px;"
            + (" font-weight:bold;" if connected else "")
        )
        self.status_changed.emit(f"Camera {'connected' if connected else 'disconnected'}")

    # ------------------------------------------------------------------
    # Live preview
    # ------------------------------------------------------------------

    def _on_toggle_preview(self) -> None:
        if self._worker and self._worker.isRunning():
            self._stop_preview()
        else:
            self._start_preview()

    def _scale_value(self) -> int:
        return {0: 1, 1: 2, 2: 4, 3: 8}.get(self._scale_combo.currentIndex(), 4)

    def _start_preview(self) -> None:
        if not self._camera:
            return

        exposure = self._exposure_spin.value()
        gain     = self._gain_spin.value()
        scale    = self._scale_value()

        self._worker = LivePreviewWorker(
            self._camera, exposure=exposure, gain=gain, preview_scale=scale,
        )
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.status_updated.connect(self._state_lbl.setText)
        self._worker.error_occurred.connect(self._on_preview_error)
        self._worker.finished.connect(self._on_preview_finished)
        self._worker.start()

        self._preview_btn.setText("■  Stop Preview")
        self._preview_btn.setProperty("class", "danger")
        self._preview_btn.style().unpolish(self._preview_btn)
        self._preview_btn.style().polish(self._preview_btn)
        self._log("CMD", f"Live preview started  {exposure:.1f}s  gain {gain}")

    def _stop_preview(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(5000)
        self._worker = None
        self._preview_btn.setText("▶  Start Preview")
        self._preview_btn.setProperty("class", "success")
        self._preview_btn.style().unpolish(self._preview_btn)
        self._preview_btn.style().polish(self._preview_btn)
        self._state_lbl.setText("—")

    def _on_frame(
        self,
        preview_arr: np.ndarray,
        full_arr: np.ndarray,
        start_dt: datetime,
        end_dt: datetime,
    ) -> None:
        # Update settings for the next frame from the current spinbox values
        if self._worker:
            self._worker.update_settings(
                self._exposure_spin.value(),
                self._gain_spin.value(),
                scale=self._scale_value(),
            )

        self._last_start = start_dt
        self._last_end   = end_dt
        # Display the downsampled preview (fast render)
        self._viewer.display(preview_arr)

        # Save full-resolution FITS if requested
        if self._save_chk.isChecked():
            self._frame_index += 1
            self._save_fits_async(full_arr, start_dt, end_dt)

    def _save_fits_async(self, arr: np.ndarray, start_dt: datetime, end_dt: datetime) -> None:
        """Write the FITS file in a thread-pool thread (non-blocking)."""
        exposure   = self._exposure_spin.value()
        gain       = self._gain_spin.value()
        obj_name   = self._object_edit.text().strip() or "Unknown"
        filter_name = self._filter_combo.currentText()
        frame_idx  = self._frame_index

        # session_folder appends "sessions/..." itself — feed it sessions_path's parent.
        base = self._config.sessions_path.parent
        folder = FITSWriter.session_folder(base, obj_name, start_dt, "Light Frame", filter_name)
        filename = FITSWriter.build_filename(obj_name, "Light Frame", start_dt, exposure, filter_name, frame_idx)
        path = folder / filename

        log_fn = self._log

        class _SaveTask(QRunnable):
            def run(self) -> None:
                try:
                    FITSWriter.write(
                        arr=arr,
                        path=path,
                        exposure_start=start_dt,
                        exposure_end=end_dt,
                        exposure_time=exposure,
                        gain=gain,
                        image_type="Light Frame",
                        object_name=obj_name,
                        filter_name=filter_name,
                    )
                    log_fn("OK", f"Saved {path.name}")
                except Exception as exc:
                    log_fn("ERROR", f"FITS save failed: {exc}")

        QThreadPool.globalInstance().start(_SaveTask())

    def _on_preview_error(self, message: str) -> None:
        self._log("ERROR", f"Preview error: {message}")
        self._stop_preview()

    def _on_preview_finished(self) -> None:
        self._stop_preview()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop workers. Call before closing the application."""
        self._stop_preview()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, level: str, message: str) -> None:
        logger.debug("[%s] %s", level, message)
        self.log_message.emit(level, message)


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
    return lbl
