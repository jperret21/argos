"""SeerControl main application window.

Layout:
  - Central area: ImageToolbar (36px) + FitsViewer (stretch)
  - Left dock:    MountPanel  (~270px)  [tabbed with FocuserPlaceholder]
  - Right dock:   CameraPanel (~280px)  [tabbed with StellPlaceholder]
  - Bottom dock:  SequencerPlaceholder  (120px)

Window state (dock positions, sizes) is persisted in config.
"""

from __future__ import annotations

import base64
import logging

from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.config import Config
from seercontrol.ui import theme
from seercontrol.ui.panels.camera_panel import CameraPanel
from seercontrol.ui.panels.mount_panel import MountPanel
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.ui.widgets.image_toolbar import ImageToolbar

logger = logging.getLogger(__name__)

_CFG_GEOMETRY = "ui.window_geometry"
_CFG_STATE    = "ui.window_state"


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class _ConnectDialog(QDialog):
    """Generic host/port connection dialog."""

    def __init__(self, title: str, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(320)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(6)

        self._host_edit = QLineEdit()
        self._host_edit.setFixedHeight(26)
        self._host_edit.setPlaceholderText("192.168.1.x")
        self._host_edit.setText(config.alpaca_host or "")
        form.addRow("Host:", self._host_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setFixedHeight(26)
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(config.alpaca_port or 11111)
        form.addRow("Port:", self._port_spin)

        layout.addLayout(form)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        host = self._host_edit.text().strip()
        port = self._port_spin.value()
        if not host:
            self._status_lbl.setText("Host cannot be empty.")
            self._status_lbl.setStyleSheet(f"color:{theme.DANGER}; font-size:11px;")
            return
        self._config.set("alpaca.host", host)
        self._config.set("alpaca.port", port)
        self.accept()

    @property
    def host(self) -> str:
        return self._host_edit.text().strip()

    @property
    def port(self) -> int:
        return self._port_spin.value()


class _PreferencesDialog(QDialog):
    """Observer and site preferences dialog."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setFixedWidth(360)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Observer group
        obs_group = QGroupBox("Observer")
        obs_form = QFormLayout(obs_group)
        obs_form.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(26)
        self._name_edit.setText(config.get("observer.name") or "")
        obs_form.addRow("Name:", self._name_edit)

        layout.addWidget(obs_group)

        # Site group
        site_group = QGroupBox("Site")
        site_form = QFormLayout(site_group)
        site_form.setSpacing(6)

        self._lat_spin = QDoubleSpinBox()
        self._lat_spin.setFixedHeight(26)
        self._lat_spin.setRange(-90.0, 90.0)
        self._lat_spin.setDecimals(4)
        self._lat_spin.setSuffix("°")
        self._lat_spin.setValue(config.get("site.latitude") or 0.0)
        site_form.addRow("Latitude:", self._lat_spin)

        self._lon_spin = QDoubleSpinBox()
        self._lon_spin.setFixedHeight(26)
        self._lon_spin.setRange(-180.0, 180.0)
        self._lon_spin.setDecimals(4)
        self._lon_spin.setSuffix("°")
        self._lon_spin.setValue(config.get("site.longitude") or 0.0)
        site_form.addRow("Longitude:", self._lon_spin)

        self._elev_spin = QSpinBox()
        self._elev_spin.setFixedHeight(26)
        self._elev_spin.setRange(-500, 9000)
        self._elev_spin.setSuffix(" m")
        self._elev_spin.setValue(int(config.get("site.elevation") or 0))
        site_form.addRow("Elevation:", self._elev_spin)

        layout.addWidget(site_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self._config.set("observer.name",    self._name_edit.text().strip())
        self._config.set("site.latitude",    self._lat_spin.value())
        self._config.set("site.longitude",   self._lon_spin.value())
        self._config.set("site.elevation",   self._elev_spin.value())
        self.accept()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _PlaceholderPanel(QWidget):
    """Temporary placeholder panel."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(f"{name}\n(coming soon)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("class", "muted")
        layout.addWidget(label)


class _StellPlaceholder(QWidget):
    """Placeholder for the Stellarium integration panel (Sprint 5)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        title = QLabel("Stellarium")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{theme.ACCENT}; font-size:14px; font-weight:bold;")
        desc = QLabel(
            "Connexion via Remote Control Plugin\n"
            "(port 8090)\n\n"
            "Coming in Sprint 5"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")
        lay.addWidget(title)
        lay.addWidget(desc)


def _make_dock(title: str, obj_name: str, widget: QWidget) -> QDockWidget:
    dock = QDockWidget(title.lower(), None)
    dock.setObjectName(f"dock_{obj_name}")
    dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    dock.setWidget(widget)
    return dock


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Main application window."""

    APP_VERSION = "0.1.0-dev"

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

        self._setup_window()
        self._build_central()
        self._build_menu()
        self._build_docks()
        self._wire_signals()
        self._build_status_bar()
        self._restore_state()

        logger.info("MainWindow initialized")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(f"SeerControl  v{self.APP_VERSION}")
        self.setMinimumSize(1200, 700)
        self.resize(1440, 900)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _build_central(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._image_toolbar = ImageToolbar()
        self._viewer        = FitsViewer()

        layout.addWidget(self._image_toolbar)
        layout.addWidget(self._viewer, stretch=1)

        self.setCentralWidget(container)

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        # ── Connection ────────────────────────────────────────────────
        conn_menu = menu_bar.addMenu("Connection")

        connect_mount_action = QAction("Connect Mount…", self)
        connect_mount_action.setShortcut("Ctrl+M")
        connect_mount_action.triggered.connect(self._open_connect_mount)
        conn_menu.addAction(connect_mount_action)

        connect_camera_action = QAction("Connect Camera…", self)
        connect_camera_action.setShortcut("Ctrl+Shift+C")
        connect_camera_action.triggered.connect(self._open_connect_camera)
        conn_menu.addAction(connect_camera_action)

        conn_menu.addSeparator()

        disconnect_all_action = QAction("Disconnect All", self)
        disconnect_all_action.triggered.connect(self._disconnect_all)
        conn_menu.addAction(disconnect_all_action)

        # ── Preferences ───────────────────────────────────────────────
        prefs_action = QAction("Preferences…", self)
        prefs_action.setShortcut("Ctrl+,")
        prefs_action.triggered.connect(self._open_preferences)
        menu_bar.addAction(prefs_action)

        # ── View ──────────────────────────────────────────────────────
        self._view_menu = menu_bar.addMenu("View")

        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        self._view_menu.addSeparator()
        self._view_menu.addAction(reset_layout_action)

        # ── Help ──────────────────────────────────────────────────────
        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("About SeerControl", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Docks
    # ------------------------------------------------------------------

    def _build_docks(self) -> None:
        self._docks: dict[str, QDockWidget] = {}

        self._mount_panel   = MountPanel(config=self._config, parent=self)
        self._camera_panel  = CameraPanel(config=self._config, parent=self)

        mount_dock   = _make_dock("Mount",    "mount",   self._mount_panel)
        camera_dock  = _make_dock("Camera",   "camera",  self._camera_panel)

        focuser_dock    = _make_dock("Focuser",    "focuser",    _PlaceholderPanel("Focuser"))
        sequencer_dock  = _make_dock("Sequencer",  "sequencer",  _PlaceholderPanel("Sequencer"))
        stellarium_dock = _make_dock("Stellarium", "stellarium", _StellPlaceholder())

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   mount_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   focuser_dock)
        self.tabifyDockWidget(mount_dock, focuser_dock)
        mount_dock.raise_()

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  camera_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  stellarium_dock)
        self.tabifyDockWidget(camera_dock, stellarium_dock)
        camera_dock.raise_()

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, sequencer_dock)

        for name, dock in [
            ("Mount", mount_dock),
            ("Camera", camera_dock),
            ("Stellarium", stellarium_dock),
            ("Focuser", focuser_dock),
            ("Sequencer", sequencer_dock),
        ]:
            self._docks[name] = dock
            toggle = dock.toggleViewAction()
            toggle.setText(name)
            self._view_menu.insertAction(
                self._view_menu.actions()[0] if self._view_menu.actions() else None,
                toggle,
            )

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        self._mount_panel.log_message.connect(self._on_log_message)
        self._mount_panel.status_changed.connect(self._on_status_changed)
        self._camera_panel.log_message.connect(self._on_log_message)
        self._camera_panel.status_changed.connect(self._on_status_changed)

        self._image_toolbar.gamma_changed.connect(self._viewer.set_gamma)
        self._image_toolbar.auto_stretch_requested.connect(self._viewer._auto_stretch)
        self._image_toolbar.channel_changed.connect(self._camera_panel.set_channel)

        self._camera_panel.frame_display.connect(self._viewer.display)

    # ------------------------------------------------------------------
    # Log / status
    # ------------------------------------------------------------------

    def _on_log_message(self, level: str, message: str) -> None:
        self.statusBar().showMessage(f"[{level}] {message}", 5000)

    def _on_status_changed(self, text: str) -> None:
        self.set_connection_status(text)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self._status_connection = QLabel("Not connected")
        self._status_connection.setProperty("class", "muted")

        self._status_coords = QLabel("")
        self._status_coords.setProperty("class", "muted")

        status_bar.addWidget(self._status_connection)
        status_bar.addPermanentWidget(self._status_coords)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _restore_state(self) -> None:
        geometry_b64 = self._config.get(_CFG_GEOMETRY)
        state_b64    = self._config.get(_CFG_STATE)

        if geometry_b64:
            try:
                self.restoreGeometry(QByteArray(base64.b64decode(geometry_b64)))
            except Exception as exc:
                logger.warning("Could not restore window geometry: %s", exc)

        if state_b64:
            try:
                self.restoreState(QByteArray(base64.b64decode(state_b64)))
            except Exception as exc:
                logger.warning("Could not restore window state: %s", exc)

    def _save_state(self) -> None:
        geometry_b64 = base64.b64encode(bytes(self.saveGeometry())).decode()
        state_b64    = base64.b64encode(bytes(self.saveState())).decode()
        self._config.set(_CFG_GEOMETRY, geometry_b64)
        self._config.set(_CFG_STATE, state_b64)

    def _reset_layout(self) -> None:
        self._config.set(_CFG_GEOMETRY, None)
        self._config.set(_CFG_STATE, None)
        logger.info("Layout reset — restart to apply")
        self.statusBar().showMessage("Layout will reset on next launch.", 4000)

    # ------------------------------------------------------------------
    # Public status bar helpers
    # ------------------------------------------------------------------

    def set_connection_status(self, text: str) -> None:
        self._status_connection.setText(text)

    def set_coords_status(self, text: str) -> None:
        self._status_coords.setText(text)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _open_connect_mount(self) -> None:
        dlg = _ConnectDialog("Connect Mount", self._config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage(
                f"Host set to {dlg.host}:{dlg.port} — use the Mount panel to connect.", 5000
            )

    def _open_connect_camera(self) -> None:
        dlg = _ConnectDialog("Connect Camera", self._config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage(
                f"Host set to {dlg.host}:{dlg.port} — use the Camera panel to connect.", 5000
            )

    def _disconnect_all(self) -> None:
        self._mount_panel.shutdown()
        self._camera_panel.shutdown()
        self.statusBar().showMessage("All devices disconnected.", 3000)

    def _open_preferences(self) -> None:
        dlg = _PreferencesDialog(self._config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Preferences saved.", 3000)

    def _show_about(self) -> None:
        self.statusBar().showMessage(
            f"SeerControl v{self.APP_VERSION} — ASCOM Alpaca controller for ZWO Seestar S30 Pro",
            5000,
        )

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._mount_panel.shutdown()
        self._camera_panel.shutdown()
        self._save_state()
        logger.info("MainWindow closed, state saved")
        super().closeEvent(event)
