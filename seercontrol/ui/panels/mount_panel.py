"""Mount control panel.

Dockable panel providing:
- Device discovery (UDP broadcast)
- Host / port configuration
- Connect / disconnect
- Live RA / Dec / Alt / Az / Tracking / Slewing display (polled every 2s)
- Goto RA + Dec (with auto-enable tracking)
- Tracking toggle
- Abort slew
- Park
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.discovery import AlpacaDevice
from seercontrol.core.alpaca.telescope import MountPosition, Telescope
from seercontrol.core.config import Config
from seercontrol.core.seestar.native_client import SeestarNativeClient, SeestarNativeError
from seercontrol.workers.discovery_worker import DiscoveryWorker
from seercontrol.workers.polling_worker import MountPollingWorker
from seercontrol.ui import theme

logger = logging.getLogger(__name__)


class MountPanel(QWidget):
    """Full mount control panel.

    Signals:
        log_message: Emitted with (level, message) for the session log panel.
        status_changed: Emitted with a short status string for the main window status bar.
    """

    log_message = pyqtSignal(str, str)       # (level, message)
    status_changed = pyqtSignal(str)

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._telescope: Telescope | None = None
        self._native: SeestarNativeClient | None = None
        self._discovery_worker: DiscoveryWorker | None = None
        self._polling_worker: MountPollingWorker | None = None

        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        root.addWidget(self._build_alignment_warning())
        root.addWidget(self._build_connection_group())
        root.addWidget(self._build_position_group())
        root.addWidget(self._build_controls_group())
        root.addWidget(self._build_goto_group())
        root.addStretch()

    def _build_alignment_warning(self) -> QLabel:
        warning = QLabel(
            "⚠  Start the Seestar native app first and let it complete its sky alignment "
            "before connecting here. Keep the app running in the background."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            f"background: rgba(240,136,62,0.12);"
            f"border: 1px solid {theme.WARNING};"
            f"border-radius: 6px;"
            f"color: {theme.WARNING};"
            f"font-size: 11px;"
            f"padding: 8px 10px;"
        )
        return warning

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("Connection")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Host / port row
        host_row = QHBoxLayout()
        host_label = QLabel("Host")
        host_label.setProperty("class", "muted")
        host_label.setFixedWidth(36)
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("192.168.x.x")
        self._host_input.textChanged.connect(self._on_host_changed)
        host_row.addWidget(host_label)
        host_row.addWidget(self._host_input)
        layout.addLayout(host_row)

        port_row = QHBoxLayout()
        port_label = QLabel("Port")
        port_label.setProperty("class", "muted")
        port_label.setFixedWidth(36)
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(4700)
        self._port_input.valueChanged.connect(self._on_port_changed)
        port_row.addWidget(port_label)
        port_row.addWidget(self._port_input)
        layout.addLayout(port_row)

        # Action buttons
        btn_row = QHBoxLayout()
        self._discover_btn = QPushButton("Discover")
        self._discover_btn.setToolTip("Scan the local network for Alpaca devices (UDP)")
        self._discover_btn.clicked.connect(self._on_discover)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setProperty("class", "primary")
        self._connect_btn.setToolTip("Connect to the mount at the specified host:port")
        self._connect_btn.clicked.connect(self._on_connect)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setProperty("class", "danger")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)

        btn_row.addWidget(self._discover_btn)
        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        layout.addLayout(btn_row)

        # Connection status badge
        self._conn_status = QLabel("Disconnected")
        self._conn_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._conn_status.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; padding: 3px;"
        )
        layout.addWidget(self._conn_status)

        return group

    def _build_position_group(self) -> QGroupBox:
        group = QGroupBox("Live Position")
        form = QFormLayout(group)
        form.setSpacing(8)

        self._ra_label = self._make_value_label("--h --m --s")
        self._dec_label = self._make_value_label("--° --' --\"")
        self._alt_label = self._make_value_label("--°")
        self._az_label = self._make_value_label("--°")
        self._tracking_label = QLabel("--")
        self._slewing_label = QLabel("--")

        form.addRow(self._section_label("RA"), self._ra_label)
        form.addRow(self._section_label("Dec"), self._dec_label)
        form.addRow(self._section_label("Alt"), self._alt_label)
        form.addRow(self._section_label("Az"), self._az_label)
        form.addRow(self._section_label("Tracking"), self._tracking_label)
        form.addRow(self._section_label("Slewing"), self._slewing_label)

        return group

    def _build_controls_group(self) -> QGroupBox:
        group = QGroupBox("Controls")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Row 1 — Tracking + Abort
        row1 = QHBoxLayout()
        self._tracking_btn = QPushButton("Tracking ON")
        self._tracking_btn.setProperty("class", "success")
        self._tracking_btn.setEnabled(False)
        self._tracking_btn.setCheckable(True)
        self._tracking_btn.toggled.connect(self._on_tracking_toggled)

        self._abort_btn = QPushButton("Abort Slew")
        self._abort_btn.setProperty("class", "danger")
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._on_abort)

        row1.addWidget(self._tracking_btn)
        row1.addWidget(self._abort_btn)

        # Row 2 — Park / Manual control
        row2 = QHBoxLayout()
        self._park_btn = QPushButton("Close Arm")
        self._park_btn.setEnabled(False)
        self._park_btn.setToolTip(
            "Park: closes the mechanical arm.\n"
            "To open the arm, use the Seestar native app."
        )
        self._park_btn.clicked.connect(self._on_park)

        # Row 3 — Manual control
        self._manual_btn = QPushButton("Manual Control…")
        self._manual_btn.setEnabled(False)
        self._manual_btn.setToolTip("Open the manual joystick control window")
        self._manual_btn.clicked.connect(self._on_open_manual_control)

        row2.addWidget(self._park_btn)
        row2.addWidget(self._manual_btn)

        layout.addLayout(row1)
        layout.addLayout(row2)

        return group

    def _build_goto_group(self) -> QGroupBox:
        group = QGroupBox("Goto")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        form = QFormLayout()

        self._goto_ra = QDoubleSpinBox()
        self._goto_ra.setRange(0.0, 23.9999)
        self._goto_ra.setDecimals(6)
        self._goto_ra.setSuffix("  h")
        self._goto_ra.setSingleStep(0.001)
        self._goto_ra.setToolTip("Right Ascension in decimal hours (J2000)")

        self._goto_dec = QDoubleSpinBox()
        self._goto_dec.setRange(-90.0, 90.0)
        self._goto_dec.setDecimals(6)
        self._goto_dec.setSuffix("  °")
        self._goto_dec.setSingleStep(0.001)
        self._goto_dec.setToolTip("Declination in decimal degrees (J2000)")

        form.addRow(self._section_label("RA"), self._goto_ra)
        form.addRow(self._section_label("Dec"), self._goto_dec)
        layout.addLayout(form)

        self._goto_btn = QPushButton("Slew to Coordinates")
        self._goto_btn.setProperty("class", "primary")
        self._goto_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._goto_btn.setEnabled(False)
        self._goto_btn.clicked.connect(self._on_goto)
        layout.addWidget(self._goto_btn)

        return group

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_value_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("class", "value")
        label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {theme.ACCENT};"
        )
        return label

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("class", "muted")
        label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
        return label

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        self._host_input.setText(self._config.alpaca_host)
        self._port_input.setValue(self._config.alpaca_port)

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
        self._discovery_worker.error_occurred.connect(self._on_discovery_error)
        self._discovery_worker.finished.connect(self._on_discovery_finished)
        self._discovery_worker.start()

    def _on_devices_found(self, devices: list[AlpacaDevice]) -> None:
        if not devices:
            self._log("WARN", "No Alpaca devices found on the network.")
            return

        self._log("OK", f"{len(devices)} device(s) found:")
        for device in devices:
            self._log("DISC", f"  → {device.host}:{device.port}")

        # Auto-select the first device
        first = devices[0]
        self._host_input.setText(first.host)
        self._port_input.setValue(first.port)
        self._log("INFO", f"Auto-selected {first.host}:{first.port}")

    def _on_discovery_error(self, message: str) -> None:
        self._log("ERROR", f"Discovery error: {message}")

    def _on_discovery_finished(self) -> None:
        self._discover_btn.setEnabled(True)
        self._discover_btn.setText("Discover")

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------

    def _on_connect(self) -> None:
        host = self._host_input.text().strip()
        port = self._port_input.value()

        if not host:
            self._log("ERROR", "Please enter a host address or run Discovery first.")
            return

        self._log("CMD", f"Connecting to {host}:{port}…")
        self._connect_btn.setEnabled(False)

        try:
            self._telescope = Telescope(host=host, port=port)
            name = self._telescope.connect()

            self._log("OK", f"Connected: {name}")

            # Native JSON-RPC client for scope_speed_move (manual jogging).
            # Connects to port 4700 regardless of the Alpaca port.
            self._native = SeestarNativeClient(host=host)
            try:
                self._native.connect()
                self._log("OK", "Native API connected (manual control ready)")
            except SeestarNativeError as exc:
                self._native = None
                self._log("WARN", f"Native API unavailable — manual jogging disabled: {exc}")

            self._set_connected_state(True)
            self._start_polling()

        except AlpacaError as exc:
            self._log("ERROR", f"Connection failed: {exc}")
            self._telescope = None
            self._connect_btn.setEnabled(True)

    def _on_disconnect(self) -> None:
        self._stop_polling()

        if self._native:
            self._native.disconnect()
            self._native = None

        if self._telescope:
            self._telescope.disconnect()
            self._telescope = None

        self._set_connected_state(False)
        self._clear_position()
        self._log("INFO", "Disconnected from mount.")

    def _set_connected_state(self, connected: bool) -> None:
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._tracking_btn.setEnabled(connected)
        self._abort_btn.setEnabled(connected)
        self._park_btn.setEnabled(connected)
        self._manual_btn.setEnabled(connected)
        self._goto_btn.setEnabled(connected)

        if connected:
            self._conn_status.setText("Connected")
            self._conn_status.setStyleSheet(
                f"color: {theme.SUCCESS}; font-size: 11px; padding: 3px; font-weight: bold;"
            )
            self.status_changed.emit(
                f"Mount connected — {self._host_input.text()}:{self._port_input.value()}"
            )
        else:
            self._conn_status.setText("Disconnected")
            self._conn_status.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 11px; padding: 3px;"
            )
            self.status_changed.emit("Mount disconnected")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        if not self._telescope:
            return

        self._polling_worker = MountPollingWorker(self._telescope, parent=self)
        self._polling_worker.position_updated.connect(self._on_position_updated)
        self._polling_worker.error_occurred.connect(self._on_poll_error)
        self._polling_worker.connection_lost.connect(self._on_connection_lost)
        self._polling_worker.start()

    def _stop_polling(self) -> None:
        if self._polling_worker and self._polling_worker.isRunning():
            self._polling_worker.stop()
            self._polling_worker.wait(3000)

    def shutdown(self) -> None:
        """Stop all background workers and connections. Call before closing."""
        self._stop_polling()
        if self._native:
            self._native.disconnect()
            self._native = None
        if self._discovery_worker and self._discovery_worker.isRunning():
            self._discovery_worker.quit()
            self._discovery_worker.wait(2000)

    def _on_position_updated(self, position: MountPosition) -> None:
        self._ra_label.setText(position.ra_str())
        self._dec_label.setText(position.dec_str())
        self._alt_label.setText(position.alt_str())
        self._az_label.setText(position.az_str())

        tracking_text = "ON" if position.tracking else "OFF"
        tracking_color = theme.SUCCESS if position.tracking else theme.WARNING
        self._tracking_label.setText(tracking_text)
        self._tracking_label.setStyleSheet(f"color: {tracking_color}; font-weight: bold;")

        slewing_text = "YES" if position.slewing else "no"
        slewing_color = theme.WARNING if position.slewing else theme.TEXT_MUTED
        self._slewing_label.setText(slewing_text)
        self._slewing_label.setStyleSheet(f"color: {slewing_color};")

        # Keep tracking button state in sync (block signal to avoid triggering command)
        self._tracking_btn.blockSignals(True)
        self._tracking_btn.setChecked(position.tracking)
        self._tracking_btn.setText("Tracking ON" if position.tracking else "Tracking OFF")
        self._tracking_btn.blockSignals(False)

        self._status_coords(position)

    def _status_coords(self, pos: MountPosition) -> None:
        self.status_changed.emit(
            f"RA {pos.ra_str()}  Dec {pos.dec_str()}  Alt {pos.alt_str()}  Az {pos.az_str()}"
        )

    def _on_poll_error(self, message: str) -> None:
        self._log("WARN", f"Poll error: {message}")

    def _on_connection_lost(self) -> None:
        self._log("ERROR", "Connection to mount lost.")
        self._stop_polling()
        self._set_connected_state(False)
        self._clear_position()
        self._telescope = None
        if self._native:
            self._native.disconnect()
            self._native = None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _on_tracking_toggled(self, checked: bool) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.set_tracking(checked)
            state = "ON" if checked else "OFF"
            self._log("CMD", f"Tracking set to {state}")
        except AlpacaError as exc:
            self._log("ERROR", f"Tracking command failed: {exc}")

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

    def _on_open_manual_control(self) -> None:
        if not self._native:
            self._log("WARN", "Native API not connected — manual control unavailable.")
            return
        if not hasattr(self, "_manual_dialog") or self._manual_dialog is None:
            from seercontrol.ui.panels.manual_control_dialog import ManualControlDialog
            self._manual_dialog = ManualControlDialog(self._native, parent=self)
            self._manual_dialog.log_message.connect(self.log_message)
            self._manual_dialog.finished.connect(self._on_manual_dialog_closed)
        self._manual_dialog.show()
        self._manual_dialog.raise_()
        self._manual_dialog.activateWindow()
        self._manual_dialog.setFocus()  # ensure keyboard events go to the dialog

    def _on_manual_dialog_closed(self) -> None:
        self._manual_dialog = None

    def _on_goto(self) -> None:
        if not self._telescope:
            return

        ra = self._goto_ra.value()
        dec = self._goto_dec.value()

        try:
            # Enable tracking before slewing
            self._telescope.set_tracking(True)
            self._telescope.slew_to(ra, dec)
            self._log("CMD", f"Slewing to RA={ra:.6f}h Dec={dec:+.6f}°")
        except AlpacaError as exc:
            self._log("ERROR", f"Goto failed: {exc}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_position(self) -> None:
        self._ra_label.setText("--h --m --s")
        self._dec_label.setText("--° --' --\"")
        self._alt_label.setText("--°")
        self._az_label.setText("--°")
        self._tracking_label.setText("--")
        self._slewing_label.setText("--")

    def _log(self, level: str, message: str) -> None:
        logger.debug("[%s] %s", level, message)
        self.log_message.emit(level, message)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._stop_polling()
        if self._telescope:
            self._telescope.disconnect()
        if self._native:
            self._native.disconnect()
        super().closeEvent(event)
