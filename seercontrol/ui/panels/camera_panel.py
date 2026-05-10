"""Camera control panel — live preview + exposure/gain controls + FITS saving.

Compact dockable panel providing:
  - Connect / disconnect camera and filter wheel (Alpaca)
  - Live preview loop (short exposures via ImageBytes)
  - HFD (Half-Flux Diameter) focus metric on every frame
  - FITS file saving with full headers

The FitsViewer is NOT embedded here — frames are emitted via frame_display
for the central viewer to display.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

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
from seercontrol.core.alpaca.filterwheel import FilterWheel, POSITION_NAMES
from seercontrol.core.config import Config
from seercontrol.core.imaging.debayer import compute_hfd, extract_channel
from seercontrol.core.imaging.fits_writer import FITSWriter
from seercontrol.ui import theme
from seercontrol.workers.exposure_worker import LivePreviewWorker

logger = logging.getLogger(__name__)

_IMAGE_TYPE = "Light Frame"


class CameraPanel(QWidget):
    """Compact camera control panel (no embedded viewer).

    Signals:
        log_message:      (level, message) for the session log.
        status_changed:   Short status string for the main window status bar.
        frame_display:    np.ndarray to display in the central FitsViewer.
        camera_connected: Camera instance on connect, None on disconnect.
    """

    log_message      = pyqtSignal(str, str)
    status_changed   = pyqtSignal(str)
    frame_display    = pyqtSignal(object)   # np.ndarray
    camera_connected = pyqtSignal(object)   # Camera | None

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config        = config
        self._camera:       Camera      | None = None
        self._filterwheel:  FilterWheel | None = None
        self._worker:       LivePreviewWorker | None = None
        self._frame_index:  int = 0
        self._channel:      str = "Raw"
        self._last_raw_frame: np.ndarray | None = None

        self._build_ui()
        self.setMaximumWidth(280)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_connection_group())
        root.addWidget(self._build_controls_group())
        root.addWidget(self._build_filter_group())
        root.addWidget(self._build_save_group())
        root.addStretch()

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Camera")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedHeight(24)
        self._connect_btn.setProperty("class", "primary")
        self._connect_btn.clicked.connect(self._on_connect)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setFixedHeight(24)
        self._disconnect_btn.setProperty("class", "danger")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)

        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        layout.addLayout(btn_row)

        self._status_lbl = QLabel("Disconnected")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:11px; padding:2px;"
        )
        layout.addWidget(self._status_lbl)
        return group

    def _build_controls_group(self) -> QGroupBox:
        group = QGroupBox("Acquisition")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        form = QFormLayout()
        form.setSpacing(4)

        self._exposure_spin = QDoubleSpinBox()
        self._exposure_spin.setFixedHeight(24)
        self._exposure_spin.setRange(0.001, 60.0)
        self._exposure_spin.setDecimals(3)
        self._exposure_spin.setValue(1.0)
        self._exposure_spin.setSuffix("  s")
        self._exposure_spin.setSingleStep(0.5)
        form.addRow(_muted("Exposure"), self._exposure_spin)

        self._gain_spin = QSpinBox()
        self._gain_spin.setFixedHeight(24)
        self._gain_spin.setRange(0, 600)
        self._gain_spin.setValue(80)
        form.addRow(_muted("Gain"), self._gain_spin)

        layout.addLayout(form)

        # HFD display
        hfd_row = QHBoxLayout()
        hfd_row.addWidget(_muted("HFD"))
        self._hfd_lbl = QLabel("—")
        self._hfd_lbl.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:12px; font-weight:bold;"
        )
        self._hfd_lbl.setToolTip(
            "Half-Flux Diameter — focus metric.\n"
            "Lower = sharper. Typical range: 2–20 px."
        )
        hfd_row.addWidget(self._hfd_lbl)
        hfd_row.addStretch()
        layout.addLayout(hfd_row)

        btn_row = QHBoxLayout()
        self._preview_btn = QPushButton("▶  Start Preview")
        self._preview_btn.setFixedHeight(26)
        self._preview_btn.setProperty("class", "success")
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self._on_toggle_preview)

        self._state_lbl = QLabel("—")
        self._state_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
        self._state_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        btn_row.addWidget(self._preview_btn)
        btn_row.addWidget(self._state_lbl)
        layout.addLayout(btn_row)

        return group

    def _build_filter_group(self) -> QGroupBox:
        group = QGroupBox("Filter Wheel")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._fw_combo = QComboBox()
        self._fw_combo.setFixedHeight(24)
        for pos, name in POSITION_NAMES.items():
            self._fw_combo.addItem(f"{pos} — {name}")
        self._fw_combo.setEnabled(False)
        self._fw_combo.currentIndexChanged.connect(self._on_filter_changed)

        row = QHBoxLayout()
        self._fw_connect_btn = QPushButton("Connect FW")
        self._fw_connect_btn.setFixedHeight(24)
        self._fw_connect_btn.clicked.connect(self._on_fw_connect)

        self._fw_status_lbl = QLabel("—")
        self._fw_status_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")

        row.addWidget(self._fw_combo, stretch=1)
        row.addWidget(self._fw_status_lbl)
        layout.addLayout(row)
        layout.addWidget(self._fw_connect_btn)
        return group

    def _build_save_group(self) -> QGroupBox:
        group = QGroupBox("Save Frames")
        layout = QFormLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._save_chk = QCheckBox("Save FITS files")
        layout.addRow(self._save_chk)

        self._object_edit = QLineEdit()
        self._object_edit.setFixedHeight(24)
        self._object_edit.setPlaceholderText("e.g. M42, NGC 224")
        layout.addRow(_muted("Object"), self._object_edit)

        self._fits_filter_combo = QComboBox()
        self._fits_filter_combo.setFixedHeight(24)
        for f in ["LRGB", "Ha", "OIII", "SII", "IR-cut"]:
            self._fits_filter_combo.addItem(f)
        layout.addRow(_muted("Filter"), self._fits_filter_combo)

        self._save_dir_lbl = QLabel()
        self._save_dir_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
        self._save_dir_lbl.setWordWrap(True)
        layout.addRow(_muted("Output"), self._save_dir_lbl)
        self._update_save_dir_label()

        return group

    def _update_save_dir_label(self) -> None:
        try:
            base = self._config.sessions_path.parent
        except AttributeError:
            base = Path.home() / "SeerControl"
        self._save_dir_lbl.setText(str(base / "sessions" / "…"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_channel(self, channel: str) -> None:
        """Update the active channel and re-emit the last frame.

        Args:
            channel: One of Raw, R, G, B, RGB.
        """
        self._channel = channel
        if self._last_raw_frame is not None:
            display_arr = extract_channel(self._last_raw_frame, self._channel)
            self.frame_display.emit(display_arr)

    def update_acquisition_settings(self, gain: int, exposure: float) -> None:
        """Sync spinboxes from the toolbar (no preview restart needed).

        Args:
            gain:     New gain value.
            exposure: New exposure value in seconds.
        """
        self._gain_spin.blockSignals(True)
        self._gain_spin.setValue(gain)
        self._gain_spin.blockSignals(False)

        self._exposure_spin.blockSignals(True)
        self._exposure_spin.setValue(exposure)
        self._exposure_spin.blockSignals(False)

    # ------------------------------------------------------------------
    # Camera connection
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

            self._log(
                "OK",
                f"Camera connected: {name}  "
                f"{self._camera.width}×{self._camera.height}  "
                f"gain {self._camera.gain_min}–{self._camera.gain_max}",
            )
            self._set_connected(True)
            self.camera_connected.emit(self._camera)

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
        self._last_raw_frame = None
        self._hfd_lbl.setText("—")
        self._log("INFO", "Camera disconnected.")
        self.camera_connected.emit(None)

    def _set_connected(self, connected: bool) -> None:
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._preview_btn.setEnabled(connected)

        color = theme.SUCCESS if connected else theme.TEXT_MUTED
        text  = "Connected" if connected else "Disconnected"
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; padding:2px;"
            + (" font-weight:bold;" if connected else "")
        )
        self.status_changed.emit(f"Camera {'connected' if connected else 'disconnected'}")

    # ------------------------------------------------------------------
    # Filter wheel
    # ------------------------------------------------------------------

    def _on_fw_connect(self) -> None:
        host = self._config.alpaca_host
        port = self._config.alpaca_port
        if not host:
            self._log("ERROR", "No host configured.")
            return
        try:
            self._filterwheel = FilterWheel(host=host, port=port)
            self._filterwheel.connect()
            pos = self._filterwheel.get_position()
            self._fw_combo.setCurrentIndex(max(0, pos))
            self._fw_combo.setEnabled(True)
            self._fw_status_lbl.setText(POSITION_NAMES.get(pos, "?"))
            self._fw_status_lbl.setStyleSheet(f"color:{theme.SUCCESS}; font-size:11px;")
            self._fw_connect_btn.setEnabled(False)
            self._log("OK", f"Filter wheel connected — position {pos} ({POSITION_NAMES.get(pos)})")
        except AlpacaError as exc:
            self._log("WARN", f"Filter wheel unavailable: {exc}")
            self._filterwheel = None

    def _on_filter_changed(self, index: int) -> None:
        if not self._filterwheel or not self._filterwheel.is_connected:
            return
        try:
            self._filterwheel.set_position(index)
            self._fw_status_lbl.setText("Moving…")
            self._fw_status_lbl.setStyleSheet(f"color:{theme.WARNING}; font-size:11px;")
            self._log("CMD", f"Filter wheel → {POSITION_NAMES.get(index)}")
        except AlpacaError as exc:
            self._log("ERROR", f"Filter change failed: {exc}")

    # ------------------------------------------------------------------
    # Live preview
    # ------------------------------------------------------------------

    def _on_toggle_preview(self) -> None:
        if self._worker and self._worker.isRunning():
            self._stop_preview()
        else:
            self._start_preview()

    def _start_preview(self) -> None:
        if not self._camera:
            return

        self._worker = LivePreviewWorker(
            self._camera,
            exposure=self._exposure_spin.value(),
            gain=self._gain_spin.value(),
            preview_scale=1,
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
        self._log(
            "CMD",
            f"Preview started  {self._exposure_spin.value():.1f}s  "
            f"gain {self._gain_spin.value()}  "
            f"channel {self._channel}",
        )

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
        if self._worker:
            self._worker.update_settings(
                self._exposure_spin.value(),
                self._gain_spin.value(),
                scale=1,
            )

        self._last_raw_frame = full_arr

        # HFD on raw green channel
        hfd = compute_hfd(full_arr)
        if hfd is not None:
            self._hfd_lbl.setText(f"{hfd:.1f} px")
            if hfd < 5:
                color = theme.SUCCESS
            elif hfd < 10:
                color = theme.WARNING
            else:
                color = theme.DANGER
            self._hfd_lbl.setStyleSheet(
                f"color:{color}; font-size:12px; font-weight:bold;"
            )
        else:
            self._hfd_lbl.setText("—")

        # Emit display array for central viewer
        display_arr = extract_channel(full_arr, self._channel)
        self.frame_display.emit(display_arr)

        # Save full-resolution raw FITS if requested
        if self._save_chk.isChecked():
            self._frame_index += 1
            self._save_fits_async(full_arr, start_dt, end_dt)

    # ------------------------------------------------------------------
    # FITS save
    # ------------------------------------------------------------------

    def _save_fits_async(
        self, arr: np.ndarray, start_dt: datetime, end_dt: datetime
    ) -> None:
        exposure    = self._exposure_spin.value()
        gain        = self._gain_spin.value()
        obj_name    = self._object_edit.text().strip() or "Unknown"
        filter_name = self._fits_filter_combo.currentText()
        frame_idx   = self._frame_index
        log_fn      = self._log

        try:
            base = self._config.sessions_path.parent
        except AttributeError:
            base = Path.home() / "SeerControl"

        folder   = FITSWriter.session_folder(base, obj_name, start_dt, _IMAGE_TYPE, filter_name)
        filename = FITSWriter.build_filename(
            obj_name, _IMAGE_TYPE, start_dt, exposure, filter_name, frame_idx
        )
        path = folder / filename

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
                        image_type=_IMAGE_TYPE,
                        object_name=obj_name,
                        filter_name=filter_name,
                    )
                    log_fn("OK", f"Saved {path.name}")
                except Exception as exc:
                    log_fn("ERROR", f"FITS save failed: {exc}")

        QThreadPool.globalInstance().start(_SaveTask())

    # ------------------------------------------------------------------
    # Error / lifecycle
    # ------------------------------------------------------------------

    def _on_preview_error(self, message: str) -> None:
        self._log("ERROR", f"Preview error: {message}")
        self._stop_preview()

    def _on_preview_finished(self) -> None:
        self._stop_preview()

    def shutdown(self) -> None:
        """Stop workers. Call before closing the application."""
        self._stop_preview()
        if self._filterwheel:
            try:
                self._filterwheel.disconnect()
            except Exception:
                pass

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
