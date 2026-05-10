"""SeerControl main application window.

QMainWindow with dockable panels. Each panel is a QDockWidget that can be
moved, resized, floated, or hidden independently by the user.
Window state (dock positions, sizes) is persisted in config.
"""

from __future__ import annotations

import base64
import logging

from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QStatusBar,
    QWidget,
    QVBoxLayout,
)

from seercontrol.core.config import Config
from seercontrol.ui import theme
from seercontrol.ui.panels.camera_panel import CameraPanel
from seercontrol.ui.panels.focuser_panel import FocuserPanel
from seercontrol.ui.panels.mount_panel import MountPanel

logger = logging.getLogger(__name__)


class _PlaceholderPanel(QWidget):
    """Temporary placeholder shown until a real panel is implemented."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(f"{name}\n(coming soon)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("class", "muted")
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """Main application window.

    Args:
        config: Application configuration instance.
    """

    APP_VERSION = "0.1.0-dev"

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

        self._setup_window()
        self._build_menu()
        self._build_docks()
        self._build_status_bar()
        self._restore_state()

        logger.info("MainWindow initialized")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(f"SeerControl  v{self.APP_VERSION}")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 900)

        # Allow all dock areas
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        # ── File ──────────────────────────────────────────────────────
        file_menu = menu_bar.addMenu("File")

        settings_action = QAction("Settings…", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # ── View ──────────────────────────────────────────────────────
        self._view_menu = menu_bar.addMenu("View")
        # Dock toggle actions are added dynamically in _build_docks()

        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        self._view_menu.addSeparator()
        self._view_menu.addAction(reset_layout_action)

        # ── Telescope ─────────────────────────────────────────────────
        scope_menu = menu_bar.addMenu("Telescope")

        connect_action = QAction("Connect…", self)
        connect_action.setShortcut("Ctrl+K")
        connect_action.triggered.connect(self._connect_telescope)
        scope_menu.addAction(connect_action)

        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self._disconnect_telescope)
        scope_menu.addAction(disconnect_action)

        # ── Help ──────────────────────────────────────────────────────
        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("About SeerControl", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_docks(self) -> None:
        """Create all dockable panels and register them in the View menu."""
        self._docks: dict[str, QDockWidget] = {}

        # Mount panel
        self._mount_panel = MountPanel(config=self._config, parent=self)
        self._mount_panel.log_message.connect(self._on_log_message)
        self._mount_panel.status_changed.connect(self._on_status_changed)

        # Camera panel
        self._camera_panel = CameraPanel(config=self._config, parent=self)
        self._camera_panel.log_message.connect(self._on_log_message)
        self._camera_panel.status_changed.connect(self._on_status_changed)

        # Focuser panel
        self._focuser_panel = FocuserPanel(config=self._config, parent=self)
        self._focuser_panel.log_message.connect(self._on_log_message)
        self._focuser_panel.status_changed.connect(self._on_status_changed)
        self._camera_panel.camera_connected.connect(self._focuser_panel.set_camera)

        real_panels: list[tuple[str, Qt.DockWidgetArea, QWidget]] = [
            ("Mount",   Qt.DockWidgetArea.LeftDockWidgetArea,  self._mount_panel),
            ("Camera",  Qt.DockWidgetArea.RightDockWidgetArea, self._camera_panel),
            ("Focuser", Qt.DockWidgetArea.LeftDockWidgetArea,  self._focuser_panel),
        ]

        placeholder_panels: list[tuple[str, Qt.DockWidgetArea]] = [
            ("Sequencer",    Qt.DockWidgetArea.RightDockWidgetArea),
            ("Filter Wheel", Qt.DockWidgetArea.LeftDockWidgetArea),
            ("Sky Map",      Qt.DockWidgetArea.BottomDockWidgetArea),
            ("Session Log",  Qt.DockWidgetArea.BottomDockWidgetArea),
        ]

        first_right: QDockWidget | None = None
        first_bottom: QDockWidget | None = None

        all_panels: list[tuple[str, Qt.DockWidgetArea, QWidget]] = (
            real_panels
            + [(name, area, _PlaceholderPanel(name)) for name, area in placeholder_panels]
        )

        for name, area, widget in all_panels:
            dock = QDockWidget(name.upper(), self)
            dock.setObjectName(f"dock_{name.replace(' ', '_').lower()}")
            dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
            dock.setWidget(widget)

            self.addDockWidget(area, dock)

            if area == Qt.DockWidgetArea.RightDockWidgetArea:
                if first_right is None:
                    first_right = dock
                else:
                    self.tabifyDockWidget(first_right, dock)
            elif area == Qt.DockWidgetArea.BottomDockWidgetArea:
                if first_bottom is None:
                    first_bottom = dock
                else:
                    self.tabifyDockWidget(first_bottom, dock)

            self._docks[name] = dock

            toggle = dock.toggleViewAction()
            toggle.setText(name)
            self._view_menu.insertAction(
                self._view_menu.actions()[0] if self._view_menu.actions() else None,
                toggle,
            )

        if first_right:
            first_right.raise_()
        if first_bottom:
            first_bottom.raise_()

    def _on_log_message(self, level: str, message: str) -> None:
        """Relay log messages from panels to the status bar (until LogPanel is built)."""
        self.statusBar().showMessage(f"[{level}] {message}", 5000)

    def _on_status_changed(self, text: str) -> None:
        self.set_connection_status(text)

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
        geometry_b64 = self._config.get("ui.window_geometry")
        state_b64 = self._config.get("ui.window_state")

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
        state_b64 = base64.b64encode(bytes(self.saveState())).decode()
        self._config.set("ui.window_geometry", geometry_b64)
        self._config.set("ui.window_state", state_b64)

    def _reset_layout(self) -> None:
        """Reset all docks to their default positions."""
        self._config.set("ui.window_geometry", None)
        self._config.set("ui.window_state", None)
        logger.info("Layout reset — restart to apply")
        self.statusBar().showMessage("Layout will reset on next launch.", 4000)

    # ------------------------------------------------------------------
    # Status bar helpers (called by workers via signals)
    # ------------------------------------------------------------------

    def set_connection_status(self, text: str) -> None:
        self._status_connection.setText(text)

    def set_coords_status(self, text: str) -> None:
        self._status_coords.setText(text)

    # ------------------------------------------------------------------
    # Menu actions (stubs — wired up when panels are implemented)
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        self.statusBar().showMessage("Settings — coming soon", 3000)

    def _connect_telescope(self) -> None:
        self.statusBar().showMessage("Connect — coming soon", 3000)

    def _disconnect_telescope(self) -> None:
        self.statusBar().showMessage("Disconnect — coming soon", 3000)

    def _show_about(self) -> None:
        self.statusBar().showMessage(
            f"SeerControl v{self.APP_VERSION} — ASCOM Alpaca controller for ZWO Seestar S30 Pro",
            5000,
        )

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        # Stop all workers before widgets are destroyed — prevents Qt fatal crash
        self._mount_panel.shutdown()
        self._camera_panel.shutdown()
        self._focuser_panel.shutdown()
        self._save_state()
        logger.info("MainWindow closed, state saved")
        super().closeEvent(event)
