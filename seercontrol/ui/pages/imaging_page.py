"""Imaging mode — the work surface where 80% of session time is spent.

Layout::

    ┌─ ImageToolbar (channel / γ / auto-stretch) ────────────────────┐
    ├──────────────────────────────────────────────┬─ Camera dock ──┤
    │                                              │ Mount  dock    │
    │           FitsViewer (PyQtGraph)             │ Histogram dock │
    │                                              │                │
    ├──────────────────────────────────────────────┴───────────────-─┤
    ├─ Log panel (4-6 lines visible) ────────────────────────────────┤
    └────────────────────────────────────────────────────────────────┘

The page owns the device handles (Telescope, Camera) and orchestrates the
existing workers (Discovery, MountPolling, LivePreview). Connection is
driven from EquipmentPage via the public ``connect_mount(host, port)`` /
``connect_camera(host, port)`` / ``start_discovery()`` / ``disconnect_all()``
methods, routed through the Shell.

The page emits four upward signals that the Shell wires into the global
status bar and forwards to the Equipment page:

    device_state_changed(device, state, info)
    tracking_changed(bool | None)
    action_changed(text)
    log_message(level, message)
    discovered_address(host, port)              # for EquipmentPage to pre-fill
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QRunnable, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.telescope import MountPosition, Telescope
from seercontrol.core.config import Config
from seercontrol.core.imaging.debayer import compute_hfd, extract_channel
from seercontrol.core.imaging.fits_writer import FITSWriter, FrameContext
from seercontrol.ui import design
from seercontrol.ui.panels.log_panel import LogPanel
from seercontrol.ui.panels.manual_control_dialog import ManualControlDialog
from seercontrol.ui.widgets.camera_dock import CameraDock
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.ui.widgets.histogram_dock import HistogramDock
from seercontrol.ui.widgets.image_toolbar import ImageToolbar
from seercontrol.ui.widgets.mount_dock import MountDock
from seercontrol.workers.discovery_worker import DiscoveryWorker
from seercontrol.workers.exposure_worker import LivePreviewWorker
from seercontrol.workers.polling_worker import MountPollingWorker

logger = logging.getLogger(__name__)

_SOFTWARE = "SeerControl v0.2.0-redesign"


class ImagingPage(QWidget):
    """The Imaging-mode workspace."""

    device_state_changed = pyqtSignal(str, str, str)   # device, state, info
    tracking_changed     = pyqtSignal(object)          # bool | None
    action_changed       = pyqtSignal(str)
    log_message          = pyqtSignal(str, str)        # level, message
    discovered_address   = pyqtSignal(str, int)        # host, port

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config

        self._telescope: Telescope | None = None
        self._camera:    Camera    | None = None
        self._discovery: DiscoveryWorker     | None = None
        self._polling:   MountPollingWorker  | None = None
        self._preview:   LivePreviewWorker   | None = None
        self._jog_dialog: ManualControlDialog | None = None

        self._channel = "Raw"
        self._last_position: MountPosition | None = None
        self._target_ra:  float | None = None
        self._target_dec: float | None = None

        # Sequence state
        self._capture_pending = 0
        self._in_sequence = False
        self._seq_total = 0
        self._seq_saved = 0
        self._seq_start = 0.0

        self._build_ui()
        self._wire_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Image toolbar — channel, gamma, auto stretch.
        self._toolbar = ImageToolbar()
        root.addWidget(self._toolbar)

        # Center splitter: FitsViewer on the left, vertical right rail on the right.
        center = QSplitter(Qt.Orientation.Horizontal)
        center.setChildrenCollapsible(False)

        self._viewer = FitsViewer()
        center.addWidget(self._viewer)

        self._camera_dock    = CameraDock()
        self._mount_dock     = MountDock()
        self._histogram_dock = HistogramDock()

        # Right rail wrapped in a scroll area so the stacked docks never get
        # squished into widget overlap when the window is short.
        right_inner = QWidget()
        right_layout = QVBoxLayout(right_inner)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(8)
        right_layout.addWidget(self._camera_dock)
        right_layout.addWidget(self._mount_dock)
        right_layout.addWidget(self._histogram_dock)
        right_layout.addStretch()

        right_scroll = QScrollArea()
        right_scroll.setWidget(right_inner)
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll.setMinimumWidth(design.RIGHT_RAIL_MIN_WIDTH)
        right_scroll.setMaximumWidth(design.RIGHT_RAIL_MAX_WIDTH)
        center.addWidget(right_scroll)

        center.setStretchFactor(0, 1)
        center.setStretchFactor(1, 0)
        center.setSizes([900, design.RIGHT_RAIL_MIN_WIDTH])
        root.addWidget(center, 1)

        # Bottom: log panel.
        self._log_panel = LogPanel()
        self._log_panel.setMinimumHeight(96)
        self._log_panel.setMaximumHeight(180)
        root.addWidget(self._log_panel)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        # Toolbar
        self._toolbar.channel_changed.connect(self._on_channel_changed)
        self._toolbar.gamma_changed.connect(self._viewer.set_gamma)
        self._toolbar.auto_stretch_requested.connect(self._viewer._auto_stretch)

        # Camera dock
        self._camera_dock.take_shot_clicked.connect(self._on_take_shot)
        self._camera_dock.sequence_toggled.connect(self._on_sequence_toggled)

        # Mount dock
        self._mount_dock.goto_clicked.connect(self._on_goto)
        self._mount_dock.sync_to_current_clicked.connect(self._on_sync)
        self._mount_dock.tracking_toggled.connect(self._on_tracking_toggle)
        self._mount_dock.tracking_rate_changed.connect(self._on_tracking_rate)
        self._mount_dock.abort_clicked.connect(self._on_abort)
        self._mount_dock.park_clicked.connect(self._on_park)
        self._mount_dock.manual_control_requested.connect(self._open_jog)

        # Logs reach the bottom log panel locally + propagate up to the Shell.
        self.log_message.connect(self._log_panel.append)

    # ------------------------------------------------------------------
    # Public connection API — driven by EquipmentPage via the Shell
    # ------------------------------------------------------------------

    def start_discovery(self) -> None:
        if self._discovery and self._discovery.isRunning():
            return
        self.log_message.emit("INFO", "Starting Alpaca discovery…")
        self._discovery = DiscoveryWorker(timeout=8.0, parent=self)
        self._discovery.devices_found.connect(self._on_devices_found)
        self._discovery.error_occurred.connect(
            lambda m: self.log_message.emit("ERROR", f"Discovery: {m}")
        )
        self._discovery.start()

    def _on_devices_found(self, devices) -> None:
        if not devices:
            self.log_message.emit("WARN", "No Alpaca devices found.")
            return
        first = devices[0]
        host, port = first.get("address", ""), int(first.get("port", 32323))
        self.log_message.emit("OK", f"Found {host}:{port}")
        self.discovered_address.emit(host, port)

    def connect_mount(self, host: str, port: int) -> None:
        self._config.alpaca_host = host
        self._config.alpaca_port = port
        self.action_changed.emit(f"Connecting mount {host}:{port}…")
        try:
            scope = Telescope(host=host, port=port)
            name = scope.connect()
            self._telescope = scope
            self.log_message.emit("OK", f"Mount connected: {name}")
            self.device_state_changed.emit("mount", "connected", name)
            self._start_polling()
            self._mount_dock.set_enabled(True)
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Mount: {exc}")
            self.device_state_changed.emit("mount", "error", str(exc)[:48])

    def connect_camera(self, host: str, port: int) -> None:
        self._config.alpaca_host = host
        self._config.alpaca_port = port
        self.action_changed.emit(f"Connecting camera {host}:{port}…")
        try:
            cam = Camera(host=host, port=port)
            name = cam.connect()
            self._camera = cam
            self._camera_dock.set_enabled(True)
            self.log_message.emit("OK", f"Camera connected: {name}")
            self.device_state_changed.emit("camera", "connected", name)
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Camera: {exc}")
            self.device_state_changed.emit("camera", "error", str(exc)[:48])

    def disconnect_mount(self) -> None:
        self._stop_polling()
        if self._telescope:
            try:
                self._telescope.disconnect()
            except AlpacaError:
                pass
            self._telescope = None
        self._mount_dock.set_enabled(False)
        self.device_state_changed.emit("mount", "disconnected", "")
        self.tracking_changed.emit(None)
        self.log_message.emit("INFO", "Mount disconnected.")

    def disconnect_camera(self) -> None:
        self._stop_preview()
        if self._camera:
            try:
                self._camera.disconnect()
            except AlpacaError:
                pass
            self._camera = None
        self._camera_dock.set_enabled(False)
        self.device_state_changed.emit("camera", "disconnected", "")
        self.log_message.emit("INFO", "Camera disconnected.")

    def disconnect_all(self) -> None:
        self.disconnect_camera()
        self.disconnect_mount()
        self.action_changed.emit("Disconnected")

    # ------------------------------------------------------------------
    # Camera actions
    # ------------------------------------------------------------------

    def _on_channel_changed(self, channel: str) -> None:
        self._channel = channel
        if self._preview and self._preview.isRunning():
            return  # next frame will use the new channel anyway

    def _on_take_shot(self) -> None:
        self._capture_pending = 1
        if not (self._preview and self._preview.isRunning()):
            self._start_preview()
        self.log_message.emit("CMD", "Take shot — saving next frame…")

    def _on_sequence_toggled(self, start: bool) -> None:
        if start:
            self._start_sequence()
        else:
            self._stop_sequence()

    def _start_sequence(self) -> None:
        params = self._camera_dock.params()
        self._seq_total = params.frames
        self._seq_saved = 0
        self._seq_start = time.time()
        self._in_sequence = True
        self._capture_pending = 0
        self._camera_dock.set_progress(0, self._seq_total, 0.0)
        if not (self._preview and self._preview.isRunning()):
            self._start_preview()
        self.log_message.emit(
            "CMD", f"Sequence started: {self._seq_total}× {params.exposure_s:.1f}s"
        )
        self.action_changed.emit(f"Sequence {self._seq_total}× {params.exposure_s:.0f}s")

    def _stop_sequence(self) -> None:
        self._in_sequence = False
        self._stop_preview()
        self._camera_dock.clear_progress()
        self.log_message.emit(
            "INFO", f"Sequence stopped — {self._seq_saved}/{self._seq_total} saved."
        )
        self.action_changed.emit("Idle")

    def _start_preview(self) -> None:
        if not self._camera:
            self.log_message.emit("WARN", "Camera not connected.")
            return
        params = self._camera_dock.params()
        self._preview = LivePreviewWorker(
            camera=self._camera, exposure=params.exposure_s, gain=params.gain,
        )
        self._preview.frame_ready.connect(self._on_frame)
        self._preview.status_updated.connect(self.action_changed)
        self._preview.error_occurred.connect(
            lambda m: self.log_message.emit("ERROR", f"Preview: {m}")
        )
        self._preview.finished.connect(self._on_preview_finished)
        self._preview.start()
        self.device_state_changed.emit("camera", "busy", "exposing")

    def _stop_preview(self) -> None:
        if self._preview and self._preview.isRunning():
            self._preview.stop()
            self._preview.wait(5000)
        self._preview = None
        if self._camera:
            self.device_state_changed.emit("camera", "connected", "")

    def _on_preview_finished(self) -> None:
        if self._in_sequence:
            return
        self._stop_preview()

    @pyqtSlot(object, object, object, object)
    def _on_frame(self, preview_arr, full_arr, start_dt, end_dt) -> None:
        # Update worker settings for the next frame from the dock form.
        params = self._camera_dock.params()
        if self._preview:
            self._preview.update_settings(params.exposure_s, params.gain, scale=1)

        # HFD on the full frame.
        hfd = compute_hfd(full_arr)
        self._camera_dock.set_hfd(hfd)

        # Display channel.
        display = extract_channel(full_arr, self._channel)
        self._viewer.display(display)
        self._histogram_dock.update_frame(full_arr)

        # Save logic.
        should_save = False
        if self._capture_pending > 0:
            self._capture_pending -= 1
            should_save = True
            if self._capture_pending == 0 and not self._in_sequence:
                self._stop_preview()
        elif self._in_sequence:
            should_save = True
            self._seq_saved += 1
            elapsed = max(0.001, time.time() - self._seq_start)
            fps = self._seq_saved / elapsed
            remaining = self._seq_total - self._seq_saved
            eta = remaining / fps if fps > 0 else 0
            self._camera_dock.set_progress(self._seq_saved, self._seq_total, eta)
            if self._seq_saved >= self._seq_total:
                self._stop_sequence()
                self.log_message.emit("OK", f"Sequence done — {self._seq_saved} frames.")

        if should_save:
            self._save_fits_async(full_arr, start_dt, end_dt)

    # ------------------------------------------------------------------
    # Mount actions
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        if not self._telescope:
            return
        self._polling = MountPollingWorker(self._telescope, parent=self)
        self._polling.position_updated.connect(self._on_position)
        self._polling.error_occurred.connect(
            lambda m: self.log_message.emit("WARN", f"Poll: {m}")
        )
        self._polling.connection_lost.connect(self._on_mount_lost)
        self._polling.start()

    def _stop_polling(self) -> None:
        if self._polling and self._polling.isRunning():
            self._polling.stop()
            self._polling.wait(3000)
        self._polling = None

    @pyqtSlot(object)
    def _on_position(self, pos: MountPosition) -> None:
        self._last_position = pos
        self._mount_dock.set_position(
            pos.ra, pos.dec, pos.altitude, pos.azimuth,
            pos.tracking, pos.slewing,
        )
        self.tracking_changed.emit(pos.tracking)
        if pos.slewing:
            self.device_state_changed.emit("mount", "busy", "slewing")
        else:
            self.device_state_changed.emit("mount", "connected", "")

    def _on_mount_lost(self) -> None:
        self.log_message.emit("ERROR", "Mount connection lost.")
        self._stop_polling()
        self._telescope = None
        self._mount_dock.set_enabled(False)
        self.device_state_changed.emit("mount", "error", "")
        self.tracking_changed.emit(None)

    def _on_goto(self, ra_h: float, dec_d: float) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.set_tracking(True)
            self._telescope.slew_to(ra_h, dec_d)
            self._target_ra, self._target_dec = ra_h, dec_d
            self.log_message.emit("CMD", f"Slewing → RA {ra_h:.4f}h Dec {dec_d:+.4f}°")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Goto: {exc}")

    def _on_sync(self) -> None:
        if not (self._telescope and self._last_position):
            return
        ra, dec = self._last_position.ra, self._last_position.dec
        try:
            self._telescope.sync_to(ra, dec)
            self.log_message.emit("CMD", f"Sync at RA {ra:.4f}h Dec {dec:+.4f}°")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Sync: {exc}")

    def _on_tracking_toggle(self, enabled: bool) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.set_tracking(enabled)
            self.log_message.emit("CMD", f"Tracking {'ON' if enabled else 'OFF'}")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Tracking: {exc}")

    def _on_tracking_rate(self, idx: int) -> None:
        if not self._telescope:
            return
        names = ("Sidereal", "Lunar", "Solar")
        try:
            self._telescope.set_tracking_rate(idx)
            self.log_message.emit("CMD", f"Tracking rate → {names[idx]}")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Tracking rate: {exc}")

    def _on_abort(self) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.abort_slew()
            self.log_message.emit("CMD", "Slew aborted")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Abort: {exc}")

    def _on_park(self) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.park()
            self.log_message.emit("CMD", "Park — arm closing.")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Park: {exc}")

    def _open_jog(self) -> None:
        if not self._telescope:
            return
        if self._jog_dialog is None:
            self._jog_dialog = ManualControlDialog(self._telescope, parent=self)
            self._jog_dialog.log_message.connect(self.log_message)
        self._jog_dialog.show()
        self._jog_dialog.raise_()

    # ------------------------------------------------------------------
    # FITS save
    # ------------------------------------------------------------------

    def _save_fits_async(self, arr: np.ndarray, start_dt: datetime, end_dt: datetime) -> None:
        params = self._camera_dock.params()
        frame_idx = self._seq_saved if self._in_sequence else 1

        pos = self._last_position
        ctx_kwargs = {
            "ra":       pos.ra        if pos else None,
            "dec":      pos.dec       if pos else None,
            "altitude": pos.altitude  if pos else None,
            "azimuth":  pos.azimuth   if pos else None,
            "target_ra":  self._target_ra,
            "target_dec": self._target_dec,
            "object_name": params.object_name,
            "filter_name": params.filter_name,
            "observer":  (self._config.get("observer.name") or "").strip(),
            "site_lat":  self._config.get("site.latitude"),
            "site_lon":  self._config.get("site.longitude"),
            "site_elev": self._config.get("site.elevation"),
            "software":  _SOFTWARE,
        }

        camera = self._camera
        try:
            base = self._config.sessions_path.parent
        except AttributeError:
            base = Path.home() / "SeerControl"
        folder = FITSWriter.session_folder(
            base, params.object_name, start_dt, params.frame_type, params.filter_name,
        )
        filename = FITSWriter.build_filename(
            params.object_name, params.frame_type, start_dt,
            params.exposure_s, params.filter_name, frame_idx,
        )
        path = folder / filename
        log_emit = self.log_message.emit

        gain = params.gain
        exposure = params.exposure_s
        frame_type = params.frame_type

        class _Task(QRunnable):
            def run(self) -> None:
                ccd_temp = camera.get_ccd_temperature() if camera else None
                egain_d  = camera.get_electrons_per_adu() if camera else None
                offset_v = camera.get_offset() if camera else None
                readout  = camera.get_readout_mode_name() if camera else None

                ctx = FrameContext(
                    ccd_temp=ccd_temp, egain_driver=egain_d,
                    offset=offset_v, readout_mode=readout,
                    **ctx_kwargs,
                )
                try:
                    FITSWriter.write(
                        arr=arr, path=path,
                        exposure_start=start_dt, exposure_end=end_dt,
                        exposure_time=exposure, gain=gain,
                        image_type=frame_type, context=ctx,
                    )
                    log_emit("OK", f"Saved {path.name}")
                except Exception as exc:
                    log_emit("ERROR", f"FITS save failed: {exc}")

        QThreadPool.globalInstance().start(_Task())

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        self._stop_preview()
        self._stop_polling()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)
