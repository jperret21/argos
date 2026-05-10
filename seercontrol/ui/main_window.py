"""SeerControl main application window.

Layout:
  - Central area: ImageToolbar (36px) + FitsViewer (stretch)
  - Left dock:    MountPanel  (~270px)  [tabbed with FocuserPlaceholder]
  - Right dock:   CameraPanel (~280px)  [tabbed with SkyMapPanel]
  - Bottom dock:  SequencerPlaceholder  (120px)

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
    """Create a QDockWidget with a lowercase compact title."""
    dock = QDockWidget(title.lower(), None)
    dock.setObjectName(f"dock_{obj_name}")
    dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    dock.setWidget(widget)
    return dock


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

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
    # Central widget: ImageToolbar + FitsViewer
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

    # ------------------------------------------------------------------
    # Docks
    # ------------------------------------------------------------------

    def _build_docks(self) -> None:
        self._docks: dict[str, QDockWidget] = {}

        # ── Real panels ───────────────────────────────────────────────
        self._mount_panel   = MountPanel(config=self._config, parent=self)
        self._camera_panel  = CameraPanel(config=self._config, parent=self)

        # ── Dock objects ──────────────────────────────────────────────
        mount_dock   = _make_dock("Mount",    "mount",   self._mount_panel)
        camera_dock  = _make_dock("Camera",   "camera",  self._camera_panel)

        # Placeholders — replaced when PRs are merged
        focuser_dock    = _make_dock("Focuser",    "focuser",    _PlaceholderPanel("Focuser"))
        sequencer_dock  = _make_dock("Sequencer",  "sequencer",  _PlaceholderPanel("Sequencer"))
        stellarium_dock = _make_dock("Stellarium", "stellarium", _StellPlaceholder())

        # ── Add docks ─────────────────────────────────────────────────
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   mount_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   focuser_dock)
        self.tabifyDockWidget(mount_dock, focuser_dock)
        mount_dock.raise_()

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  camera_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  stellarium_dock)
        self.tabifyDockWidget(camera_dock, stellarium_dock)
        camera_dock.raise_()

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, sequencer_dock)

        # ── View menu toggles ──────────────────────────────────────────
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
        # Panel → status bar / log
        self._mount_panel.log_message.connect(self._on_log_message)
        self._mount_panel.status_changed.connect(self._on_status_changed)
        self._camera_panel.log_message.connect(self._on_log_message)
        self._camera_panel.status_changed.connect(self._on_status_changed)

        # ImageToolbar → viewer / camera
        self._image_toolbar.gamma_changed.connect(self._viewer.set_gamma)
        self._image_toolbar.auto_stretch_requested.connect(self._viewer._auto_stretch)
        self._image_toolbar.channel_changed.connect(self._camera_panel.set_channel)

        self._image_toolbar.gain_changed.connect(
            lambda g: self._camera_panel.update_acquisition_settings(
                g, self._camera_panel._exposure_spin.value()
            )
        )
        self._image_toolbar.exposure_changed.connect(
            lambda e: self._camera_panel.update_acquisition_settings(
                self._camera_panel._gain_spin.value(), e
            )
        )

        # Camera panel → viewer
        self._camera_panel.frame_display.connect(self._viewer.display)

        # position_updated_pub will wire to Stellarium panel in a future sprint

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
    # Menu actions (stubs)
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
        self._mount_panel.shutdown()
        self._camera_panel.shutdown()
        self._save_state()
        logger.info("MainWindow closed, state saved")
        super().closeEvent(event)
