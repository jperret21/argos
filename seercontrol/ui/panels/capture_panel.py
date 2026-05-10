"""Capture panel — unified acquisition + mount control for left dock.

Sections:
  - Connection: mount + camera status badges, connect/discover buttons
  - Capture: frame type, object, filter, exposure, gain, count,
             TAKE SHOT + START/STOP SEQUENCE buttons, progress + ETA
  - Mount: live RA/Dec/Alt/Az/tracking, compact goto, HFD

All blocking work runs in QThread workers. The panel emits frames for the
central FitsViewer via frame_display, and logs via log_message.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.filterwheel import FilterWheel, POSITION_NAMES
from seercontrol.core.alpaca.telescope import MountPosition, Telescope
from seercontrol.core.config import Config
from seercontrol.core.imaging.debayer import compute_hfd, extract_channel
from seercontrol.core.imaging.fits_writer import FITSWriter
from seercontrol.ui import theme
from seercontrol.workers.discovery_worker import DiscoveryWorker
from seercontrol.workers.exposure_worker import LivePreviewWorker
from seercontrol.workers.polling_worker import MountPollingWorker

logger = logging.getLogger(__name__)

_FRAME_TYPES = ["Light Frame", "Dark Frame", "Flat Frame", "Bias Frame"]
_FILTERS     = ["LRGB", "Ha", "OIII", "SII", "IR-cut"]


class CapturePanel(QWidget):
    """Unified capture + mount control panel.

    Signals:
        log_message:    (level, message)
        status_changed: Short status string for the main window status bar.
        frame_display:  np.ndarray ready to display in the central FitsViewer.
    """

    log_message    = pyqtSignal(str, str)
    status_changed = pyqtSignal(str)
    frame_display  = pyqtSignal(object)   # np.ndarray

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config

        # Devices
        self._telescope:  Telescope  | None = None
        self._camera:     Camera     | None = None
        self._filterwheel: FilterWheel | None = None

        # Workers
        self._discovery_worker: DiscoveryWorker     | None = None
        self._polling_worker:   MountPollingWorker  | None = None
        self._preview_worker:   LivePreviewWorker   | None = None

        # Acquisition state
        self._channel:         str   = "Raw"
        self._last_raw_frame:  np.ndarray | None = None
        self._capture_pending: int   = 0      # frames still to save
        self._in_sequence:     bool  = False
        self._seq_total:       int   = 0
        self._seq_saved:       int   = 0
        self._seq_start:       float = 0.0

        self._build_ui()
        self._load_config()
        self.setMinimumWidth(240)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Scrollable container so narrow docks don't clip content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none; background:transparent;}")

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(10)

        inner_layout.addWidget(self._build_connection_group())
        inner_layout.addWidget(self._build_capture_group())
        inner_layout.addWidget(self._build_mount_group())
        inner_layout.addStretch()

        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ------------------------------------------------------------------

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Connection")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(6)

        # Host row
        host_row = QHBoxLayout()
        host_row.addWidget(_muted("Host"))
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("192.168.x.x")
        self._host_edit.textChanged.connect(self._on_host_changed)
        host_row.addWidget(self._host_edit)
        layout.addLayout(host_row)

        port_row = QHBoxLayout()
        port_row.addWidget(_muted("Port"))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.valueChanged.connect(self._on_port_changed)
        port_row.addWidget(self._port_spin)
        layout.addLayout(port_row)

        # Discover
        self._discover_btn = QPushButton("Discover")
        self._discover_btn.clicked.connect(self._on_discover)
        layout.addWidget(self._discover_btn)

        # Status badges
        badges = QHBoxLayout()
        self._mount_badge  = _badge("Mount",  connected=False)
        self._camera_badge = _badge("Camera", connected=False)
        badges.addWidget(self._mount_badge)
        badges.addWidget(self._camera_badge)
        layout.addLayout(badges)

        # Connect/Disconnect buttons
        btn_row = QHBoxLayout()
        self._connect_mount_btn = QPushButton("Connect Mount")
        self._connect_mount_btn.setProperty("class", "primary")
        self._connect_mount_btn.clicked.connect(self._on_connect_mount)

        self._connect_camera_btn = QPushButton("Connect Camera")
        self._connect_camera_btn.setProperty("class", "primary")
        self._connect_camera_btn.clicked.connect(self._on_connect_camera)

        btn_row.addWidget(self._connect_mount_btn)
        btn_row.addWidget(self._connect_camera_btn)
        layout.addLayout(btn_row)

        return group

    # ------------------------------------------------------------------

    def _build_capture_group(self) -> QGroupBox:
        group = QGroupBox("Capture")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        # ── Settings form — 2-column grid ─────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(5)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._type_combo = QComboBox()
        for ft in _FRAME_TYPES:
            self._type_combo.addItem(ft)
        self._type_combo.currentTextChanged.connect(self._on_frame_type_changed)
        grid.addWidget(_muted("Type"),   0, 0)
        grid.addWidget(self._type_combo, 0, 1, 1, 3)  # span full width

        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("M42, NGC 224…")
        grid.addWidget(_muted("Object"),    1, 0)
        grid.addWidget(self._object_edit,   1, 1, 1, 3)

        self._filter_combo = QComboBox()
        for f in _FILTERS:
            self._filter_combo.addItem(f)
        grid.addWidget(_muted("Filter"),    2, 0)
        grid.addWidget(self._filter_combo,  2, 1, 1, 3)

        # Exp + Gain on the same row
        self._exp_spin = QDoubleSpinBox()
        self._exp_spin.setRange(0.001, 600.0)
        self._exp_spin.setDecimals(2)
        self._exp_spin.setValue(1.0)
        self._exp_spin.setSuffix(" s")
        self._exp_spin.setSingleStep(0.5)

        self._gain_spin = QSpinBox()
        self._gain_spin.setRange(0, 600)
        self._gain_spin.setValue(80)

        grid.addWidget(_muted("Exp"),    3, 0)
        grid.addWidget(self._exp_spin,   3, 1)
        grid.addWidget(_muted("Gain"),   3, 2)
        grid.addWidget(self._gain_spin,  3, 3)

        # Count + HFD on same row
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 9999)
        self._count_spin.setValue(10)

        self._hfd_lbl = QLabel("—")
        self._hfd_lbl.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:13px; font-weight:bold;"
            f"font-family:{theme.FONT_MONO};"
        )

        grid.addWidget(_muted("Count"), 4, 0)
        grid.addWidget(self._count_spin, 4, 1)
        grid.addWidget(_muted("HFD"),   4, 2)
        grid.addWidget(self._hfd_lbl,   4, 3)

        layout.addLayout(grid)

        # ── Action buttons — 2-column grid ────────────────────────────
        btn_grid = QGridLayout()
        btn_grid.setSpacing(6)

        self._take_btn = QPushButton("◉  Take Shot")
        self._take_btn.setProperty("class", "primary")
        self._take_btn.setEnabled(False)
        self._take_btn.clicked.connect(self._on_take_shot)

        self._seq_btn = QPushButton("▶  Sequence")
        self._seq_btn.setProperty("class", "success")
        self._seq_btn.setEnabled(False)
        self._seq_btn.clicked.connect(self._on_toggle_sequence)

        self._preview_btn = QPushButton("▶  Live Preview")
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self._on_toggle_preview)

        btn_grid.addWidget(self._take_btn,    0, 0)
        btn_grid.addWidget(self._seq_btn,     0, 1)
        btn_grid.addWidget(self._preview_btn, 1, 0, 1, 2)  # full width

        layout.addLayout(btn_grid)

        # ── Progress ──────────────────────────────────────────────────
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%v / %m")
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._eta_lbl = QLabel("")
        self._eta_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
        self._eta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._eta_lbl.setVisible(False)
        layout.addWidget(self._eta_lbl)

        self._state_lbl = QLabel("—")
        self._state_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
        layout.addWidget(self._state_lbl)

        return group

    # ------------------------------------------------------------------

    def _build_mount_group(self) -> QGroupBox:
        group = QGroupBox("Mount")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(4)

        self._ra_lbl  = _coord_label("— h — m — s")
        self._dec_lbl = _coord_label("—° —′ —″")
        self._alt_lbl = _coord_label("—°")
        self._az_lbl  = _coord_label("—°")

        form.addRow(_muted("RA"),  self._ra_lbl)
        form.addRow(_muted("Dec"), self._dec_lbl)
        form.addRow(_muted("Alt"), self._alt_lbl)
        form.addRow(_muted("Az"),  self._az_lbl)
        layout.addLayout(form)

        track_row = QHBoxLayout()
        track_row.addWidget(_muted("Track"))
        self._track_lbl = QLabel("—")
        self._track_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")
        track_row.addWidget(self._track_lbl)

        self._track_btn = QPushButton("Track ON")
        self._track_btn.setProperty("class", "success")
        self._track_btn.setCheckable(True)
        self._track_btn.setEnabled(False)
        self._track_btn.toggled.connect(self._on_tracking_toggled)
        track_row.addStretch()
        track_row.addWidget(self._track_btn)
        layout.addLayout(track_row)

        # Goto form
        goto_group = QGroupBox("Goto")
        goto_layout = QVBoxLayout(goto_group)
        goto_layout.setContentsMargins(6, 10, 6, 6)
        goto_layout.setSpacing(4)

        gform = QFormLayout()
        gform.setSpacing(4)
        self._goto_ra = QDoubleSpinBox()
        self._goto_ra.setRange(0.0, 23.9999)
        self._goto_ra.setDecimals(4)
        self._goto_ra.setSuffix("  h")

        self._goto_dec = QDoubleSpinBox()
        self._goto_dec.setRange(-90.0, 90.0)
        self._goto_dec.setDecimals(4)
        self._goto_dec.setSuffix("  °")

        gform.addRow(_muted("RA"), self._goto_ra)
        gform.addRow(_muted("Dec"), self._goto_dec)
        goto_layout.addLayout(gform)

        goto_btns = QHBoxLayout()
        self._slew_btn = QPushButton("▶  Slew")
        self._slew_btn.setProperty("class", "primary")
        self._slew_btn.setEnabled(False)
        self._slew_btn.clicked.connect(self._on_goto)

        self._abort_btn = QPushButton("■  Abort")
        self._abort_btn.setProperty("class", "danger")
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._on_abort)

        self._park_btn = QPushButton("⊙  Park")
        self._park_btn.setEnabled(False)
        self._park_btn.clicked.connect(self._on_park)

        goto_btns.addWidget(self._slew_btn)
        goto_btns.addWidget(self._abort_btn)
        goto_btns.addWidget(self._park_btn)
        goto_layout.addLayout(goto_btns)
        layout.addWidget(goto_group)

        return group

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        self._host_edit.setText(self._config.alpaca_host or "")
        self._port_spin.setValue(self._config.alpaca_port or 11111)

    def _on_host_changed(self, text: str) -> None:
        self._config.alpaca_host = text.strip()

    def _on_port_changed(self, value: int) -> None:
        self._config.alpaca_port = value

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _on_discover(self) -> None:
        if self._discovery_worker and self._discovery_worker.isRunning():
            return
        self._discover_btn.setEnabled(False)
        self._discover_btn.setText("Scanning…")
        self._log("INFO", "Starting Alpaca UDP discovery…")

        self._discovery_worker = DiscoveryWorker(timeout=8.0, parent=self)
        self._discovery_worker.devices_found.connect(self._on_devices_found)
        self._discovery_worker.error_occurred.connect(
            lambda m: self._log("ERROR", f"Discovery: {m}")
        )
        self._discovery_worker.finished.connect(self._on_discovery_finished)
        self._discovery_worker.start()

    def _on_devices_found(self, devices: list) -> None:
        if not devices:
            self._log("WARN", "No Alpaca devices found.")
            return
        first = devices[0]
        self._host_edit.setText(first.host)
        self._port_spin.setValue(first.port)
        self._log("OK", f"Found {len(devices)} device(s) — auto-selected {first.host}:{first.port}")

    def _on_discovery_finished(self) -> None:
        self._discover_btn.setEnabled(True)
        self._discover_btn.setText("Discover")

    # ------------------------------------------------------------------
    # Mount connection
    # ------------------------------------------------------------------

    def _on_connect_mount(self) -> None:
        host = self._host_edit.text().strip()
        port = self._port_spin.value()
        if not host:
            self._log("ERROR", "Enter a host address first.")
            return

        self._connect_mount_btn.setEnabled(False)
        self._log("CMD", f"Connecting mount at {host}:{port}…")
        try:
            self._telescope = Telescope(host=host, port=port)
            name = self._telescope.connect()
            self._log("OK", f"Mount connected: {name}")
            self._mount_badge.setText("● Mount")
            self._mount_badge.setStyleSheet(_badge_style(True))
            self._track_btn.setEnabled(True)
            self._slew_btn.setEnabled(True)
            self._abort_btn.setEnabled(True)
            self._park_btn.setEnabled(True)
            self._start_polling()
            self.status_changed.emit(f"Mount connected — {host}:{port}")
        except AlpacaError as exc:
            self._log("ERROR", f"Mount connection failed: {exc}")
            self._telescope = None
            self._connect_mount_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Camera connection
    # ------------------------------------------------------------------

    def _on_connect_camera(self) -> None:
        host = self._host_edit.text().strip()
        port = self._port_spin.value()
        if not host:
            self._log("ERROR", "Enter a host address first.")
            return

        self._connect_camera_btn.setEnabled(False)
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
            self._camera_badge.setText("● Camera")
            self._camera_badge.setStyleSheet(_badge_style(True))
            self._take_btn.setEnabled(True)
            self._seq_btn.setEnabled(True)
            self._preview_btn.setEnabled(True)
            self.status_changed.emit("Camera connected")
        except AlpacaError as exc:
            self._log("ERROR", f"Camera connection failed: {exc}")
            self._camera = None
            self._connect_camera_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def set_channel(self, channel: str) -> None:
        """Switch display channel and re-emit the last frame."""
        self._channel = channel
        if self._last_raw_frame is not None:
            self.frame_display.emit(
                extract_channel(self._last_raw_frame, self._channel)
            )

    # ------------------------------------------------------------------
    # Frame type visibility
    # ------------------------------------------------------------------

    def _on_frame_type_changed(self, frame_type: str) -> None:
        needs_object = frame_type == "Light Frame"
        needs_filter = frame_type in ("Light Frame", "Flat Frame")
        # Show/hide object and filter rows in the form
        self._object_edit.setEnabled(needs_object)
        self._filter_combo.setEnabled(needs_filter)

    # ------------------------------------------------------------------
    # Capture actions
    # ------------------------------------------------------------------

    def _on_take_shot(self) -> None:
        self._capture_pending = 1
        if not (self._preview_worker and self._preview_worker.isRunning()):
            self._start_preview()
        self._log("CMD", "Take shot — saving next frame…")

    def _on_toggle_sequence(self) -> None:
        if self._in_sequence:
            self._stop_sequence()
        else:
            self._start_sequence()

    def _start_sequence(self) -> None:
        self._seq_total    = self._count_spin.value()
        self._seq_saved    = 0
        self._seq_start    = time.time()
        self._in_sequence  = True
        self._capture_pending = 0   # sequence loop handles saving itself

        self._progress_bar.setRange(0, self._seq_total)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat(f"%v / {self._seq_total}")
        self._progress_bar.setVisible(True)
        self._eta_lbl.setVisible(True)

        self._seq_btn.setText("■  STOP SEQUENCE")
        self._seq_btn.setProperty("class", "danger")
        self._seq_btn.style().unpolish(self._seq_btn)
        self._seq_btn.style().polish(self._seq_btn)

        if not (self._preview_worker and self._preview_worker.isRunning()):
            self._start_preview()
        self._log("CMD", f"Sequence started: {self._seq_total}× {self._exp_spin.value():.1f}s")

    def _stop_sequence(self) -> None:
        self._in_sequence = False
        self._stop_preview()
        self._progress_bar.setVisible(False)
        self._eta_lbl.setVisible(False)
        self._seq_btn.setText("▶  START SEQUENCE")
        self._seq_btn.setProperty("class", "success")
        self._seq_btn.style().unpolish(self._seq_btn)
        self._seq_btn.style().polish(self._seq_btn)
        self._log("INFO", f"Sequence stopped — {self._seq_saved}/{self._seq_total} frames saved.")

    # ------------------------------------------------------------------
    # Preview worker
    # ------------------------------------------------------------------

    def _on_toggle_preview(self) -> None:
        if self._preview_worker and self._preview_worker.isRunning():
            self._stop_preview()
        else:
            self._start_preview()

    def _start_preview(self) -> None:
        if not self._camera:
            return
        self._preview_worker = LivePreviewWorker(
            self._camera,
            exposure=self._exp_spin.value(),
            gain=self._gain_spin.value(),
            preview_scale=1,
        )
        self._preview_worker.frame_ready.connect(self._on_frame)
        self._preview_worker.status_updated.connect(self._state_lbl.setText)
        self._preview_worker.error_occurred.connect(self._on_preview_error)
        self._preview_worker.finished.connect(self._on_preview_finished)
        self._preview_worker.start()

        self._preview_btn.setText("■  Stop Preview")
        self._preview_btn.setProperty("class", "danger")
        self._preview_btn.style().unpolish(self._preview_btn)
        self._preview_btn.style().polish(self._preview_btn)

    def _stop_preview(self) -> None:
        if self._preview_worker and self._preview_worker.isRunning():
            self._preview_worker.stop()
            self._preview_worker.wait(5000)
        self._preview_worker = None
        self._preview_btn.setText("▶  Live Preview")
        self._preview_btn.setProperty("class", "")
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
        # Update worker settings for next frame
        if self._preview_worker:
            self._preview_worker.update_settings(
                self._exp_spin.value(),
                self._gain_spin.value(),
                scale=1,
            )

        self._last_raw_frame = full_arr

        # HFD
        hfd = compute_hfd(full_arr)
        if hfd is not None:
            self._hfd_lbl.setText(f"{hfd:.1f} px")
            color = theme.SUCCESS if hfd < 5 else (theme.WARNING if hfd < 10 else theme.DANGER)
            self._hfd_lbl.setStyleSheet(
                f"color:{color}; font-size:13px; font-weight:bold;"
                f"font-family:{theme.FONT_MONO};"
            )

        # Emit display frame
        display_arr = extract_channel(full_arr, self._channel)
        self.frame_display.emit(display_arr)

        # Save logic
        should_save = False
        if self._capture_pending > 0:
            self._capture_pending -= 1
            should_save = True
            if self._capture_pending == 0 and not self._in_sequence:
                self._stop_preview()   # single shot done

        elif self._in_sequence:
            should_save = True
            self._seq_saved += 1
            self._update_progress()
            if self._seq_saved >= self._seq_total:
                self._stop_sequence()
                self._log("OK", f"Sequence complete — {self._seq_saved} frames saved.")

        if should_save:
            self._save_fits_async(full_arr, start_dt, end_dt)

    def _update_progress(self) -> None:
        self._progress_bar.setValue(self._seq_saved)
        if self._seq_saved > 0:
            elapsed = time.time() - self._seq_start
            fps = self._seq_saved / elapsed
            remaining = self._seq_total - self._seq_saved
            eta = remaining / fps
            self._eta_lbl.setText(
                f"Frame {self._seq_saved}/{self._seq_total}  —  "
                f"ETA {int(eta // 60)}m {int(eta % 60)}s"
            )

    def _on_preview_error(self, message: str) -> None:
        self._log("ERROR", f"Preview error: {message}")
        self._stop_preview()
        if self._in_sequence:
            self._stop_sequence()

    def _on_preview_finished(self) -> None:
        if self._in_sequence:
            return  # sequence stop already called from _on_frame
        self._stop_preview()

    # ------------------------------------------------------------------
    # FITS save
    # ------------------------------------------------------------------

    def _save_fits_async(
        self, arr: np.ndarray, start_dt: datetime, end_dt: datetime
    ) -> None:
        frame_type  = self._type_combo.currentText()
        exposure    = self._exp_spin.value()
        gain        = self._gain_spin.value()
        obj_name    = self._object_edit.text().strip() or "Unknown"
        filter_name = self._filter_combo.currentText()
        frame_idx   = self._seq_saved if self._in_sequence else 1
        log_fn      = self._log

        try:
            base = self._config.sessions_path.parent
        except AttributeError:
            base = Path.home() / "SeerControl"

        folder   = FITSWriter.session_folder(base, obj_name, start_dt, frame_type, filter_name)
        filename = FITSWriter.build_filename(
            obj_name, frame_type, start_dt, exposure, filter_name, frame_idx
        )
        path = folder / filename

        class _Task(QRunnable):
            def run(self) -> None:
                try:
                    FITSWriter.write(
                        arr=arr, path=path,
                        exposure_start=start_dt, exposure_end=end_dt,
                        exposure_time=exposure, gain=gain,
                        image_type=frame_type, object_name=obj_name,
                        filter_name=filter_name,
                    )
                    log_fn("OK", f"Saved {path.name}")
                except Exception as exc:
                    log_fn("ERROR", f"FITS save failed: {exc}")

        QThreadPool.globalInstance().start(_Task())

    # ------------------------------------------------------------------
    # Mount polling
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        if not self._telescope:
            return
        self._polling_worker = MountPollingWorker(self._telescope, parent=self)
        self._polling_worker.position_updated.connect(self._on_position_updated)
        self._polling_worker.error_occurred.connect(
            lambda m: self._log("WARN", f"Poll error: {m}")
        )
        self._polling_worker.connection_lost.connect(self._on_mount_lost)
        self._polling_worker.start()

    def _stop_polling(self) -> None:
        if self._polling_worker and self._polling_worker.isRunning():
            self._polling_worker.stop()
            self._polling_worker.wait(3000)

    @pyqtSlot(object)
    def _on_position_updated(self, pos: MountPosition) -> None:
        self._ra_lbl.setText(pos.ra_str())
        self._dec_lbl.setText(pos.dec_str())
        self._alt_lbl.setText(pos.alt_str())
        self._az_lbl.setText(pos.az_str())

        color = theme.SUCCESS if pos.tracking else theme.WARNING
        self._track_lbl.setText("ON" if pos.tracking else "OFF")
        self._track_lbl.setStyleSheet(f"color:{color}; font-size:11px; font-weight:bold;")

        self._track_btn.blockSignals(True)
        self._track_btn.setChecked(pos.tracking)
        self._track_btn.setText("Track ON" if pos.tracking else "Track OFF")
        self._track_btn.blockSignals(False)

        self.status_changed.emit(
            f"RA {pos.ra_str()}  Dec {pos.dec_str()}  Alt {pos.alt_str()}"
        )

    def _on_mount_lost(self) -> None:
        self._log("ERROR", "Mount connection lost.")
        self._stop_polling()
        self._telescope = None
        self._mount_badge.setText("○ Mount")
        self._mount_badge.setStyleSheet(_badge_style(False))
        self._track_btn.setEnabled(False)
        self._slew_btn.setEnabled(False)
        self._abort_btn.setEnabled(False)
        self._park_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Mount commands
    # ------------------------------------------------------------------

    def _on_tracking_toggled(self, checked: bool) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.set_tracking(checked)
            self._log("CMD", f"Tracking {'ON' if checked else 'OFF'}")
        except AlpacaError as exc:
            self._log("ERROR", f"Tracking failed: {exc}")

    def _on_goto(self) -> None:
        if not self._telescope:
            return
        ra, dec = self._goto_ra.value(), self._goto_dec.value()
        try:
            self._telescope.set_tracking(True)
            self._telescope.slew_to(ra, dec)
            self._log("CMD", f"Slewing → RA {ra:.4f}h  Dec {dec:+.4f}°")
        except AlpacaError as exc:
            self._log("ERROR", f"Goto failed: {exc}")

    def _on_abort(self) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.abort_slew()
            self._log("CMD", "Slew aborted.")
        except AlpacaError as exc:
            self._log("ERROR", f"Abort failed: {exc}")

    def _on_park(self) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.park()
            self._log("CMD", "Park: arm closing.")
        except AlpacaError as exc:
            self._log("ERROR", f"Park failed: {exc}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop all workers. Call before closing the application."""
        self._stop_preview()
        self._stop_polling()
        if self._in_sequence:
            self._stop_sequence()
        if self._discovery_worker and self._discovery_worker.isRunning():
            self._discovery_worker.quit()
            self._discovery_worker.wait(2000)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, level: str, message: str) -> None:
        logger.debug("[%s] %s", level, message)
        self.log_message.emit(level, message)


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------

def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:10px;")
    return lbl


def _coord_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.ACCENT}; font-size:12px; font-weight:bold;"
        f"font-family:{theme.FONT_MONO};"
    )
    return lbl


def _badge_style(connected: bool) -> str:
    color = theme.SUCCESS if connected else theme.TEXT_MUTED
    return f"color:{color}; font-size:11px; font-weight:bold;"


def _badge(name: str, connected: bool) -> QLabel:
    lbl = QLabel(f"{'●' if connected else '○'} {name}")
    lbl.setStyleSheet(_badge_style(connected))
    return lbl
