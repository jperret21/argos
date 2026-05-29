"""SeerControl main application window.

Layout:
  - Central area: FitsViewer (full stretch — no toolbar above it)
  - Left dock:    CapturePanel   (freely resizable)
  - Right dock:   AnalysisPanel  (freely resizable)
  - Bottom dock:  LogPanel       (freely resizable)

Window state (dock sizes, positions) is persisted in config.
"""

from __future__ import annotations

import base64
import logging

from PyQt6.QtCore import Qt, QByteArray, QObject, QRunnable, QThreadPool, pyqtSignal
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
    QToolBar,
    QWidget,
)

from seercontrol.core.config import Config
from seercontrol.core.stellarium.remote_pull import pull_selected_object
from seercontrol.ui import theme
from seercontrol.ui.panels.analysis_panel import AnalysisPanel
from seercontrol.ui.panels.capture_panel import CapturePanel
from seercontrol.ui.panels.log_panel import LogPanel
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.workers.stellarium_worker import StellariumWorker

logger = logging.getLogger(__name__)

_CFG_GEOMETRY = "ui.window_geometry"
_CFG_STATE    = "ui.window_state"


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class _PreferencesDialog(QDialog):
    """Observer and site preferences."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setFixedWidth(360)
        self._config = config

        layout = __import__("PyQt6.QtWidgets", fromlist=["QVBoxLayout"]).QVBoxLayout(self)
        layout.setSpacing(12)

        obs = QGroupBox("Observer")
        obs_form = QFormLayout(obs)
        obs_form.setSpacing(6)
        self._name_edit = QLineEdit(config.get("observer.name") or "")
        obs_form.addRow("Name:", self._name_edit)
        layout.addWidget(obs)

        site = QGroupBox("Site")
        site_form = QFormLayout(site)
        site_form.setSpacing(6)

        self._lat = QDoubleSpinBox()
        self._lat.setRange(-90, 90)
        self._lat.setDecimals(4)
        self._lat.setSuffix("°")
        self._lat.setValue(config.get("site.latitude") or 0.0)
        site_form.addRow("Latitude:", self._lat)

        self._lon = QDoubleSpinBox()
        self._lon.setRange(-180, 180)
        self._lon.setDecimals(4)
        self._lon.setSuffix("°")
        self._lon.setValue(config.get("site.longitude") or 0.0)
        site_form.addRow("Longitude:", self._lon)

        self._elev = QSpinBox()
        self._elev.setRange(-500, 9000)
        self._elev.setSuffix(" m")
        self._elev.setValue(int(config.get("site.elevation") or 0))
        site_form.addRow("Elevation:", self._elev)

        layout.addWidget(site)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self) -> None:
        self._config.set("observer.name",  self._name_edit.text().strip())
        self._config.set("site.latitude",  self._lat.value())
        self._config.set("site.longitude", self._lon.value())
        self._config.set("site.elevation", self._elev.value())
        self.accept()


# ---------------------------------------------------------------------------
# Stellarium HTTP pull runner
# ---------------------------------------------------------------------------

class _PullRunnerSignals(QObject):
    target = pyqtSignal(str, float, float)
    failed = pyqtSignal(str)


class _PullRunner(QRunnable):
    """One-shot HTTP query to Stellarium's Remote Control endpoint.

    Runs on the global QThreadPool so the ~2 s timeout never blocks the UI.
    """

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self.signals = _PullRunnerSignals()

    def run(self) -> None:
        try:
            target = pull_selected_object(host=self._host, port=self._port)
        except Exception as exc:  # network errors already swallowed by pull_selected_object
            self.signals.failed.emit(str(exc))
            return
        if target is None:
            self.signals.failed.emit("no selection or plugin not running")
            return
        self.signals.target.emit(target.name, target.ra_hours, target.dec_degrees)


# ---------------------------------------------------------------------------
# Dock factory
# ---------------------------------------------------------------------------

def _make_dock(title: str, obj_name: str, widget: QWidget) -> QDockWidget:
    dock = QDockWidget(title.upper(), None)
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
        self._stellarium_worker: StellariumWorker | None = None

        self._setup_window()
        self._build_central()
        self._build_menu()
        self._build_docks()
        self._build_toolbar()
        self._wire_signals()
        self._build_status_bar()
        self._restore_state()

        logger.info("MainWindow initialized")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(f"SeerControl  v{self.APP_VERSION}")
        self.setMinimumSize(1100, 650)
        self.resize(1440, 900)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )

    # ------------------------------------------------------------------
    # Central: pure FitsViewer — no toolbar above
    # ------------------------------------------------------------------

    def _build_central(self) -> None:
        self._viewer = FitsViewer()
        self.setCentralWidget(self._viewer)

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        bar = self.menuBar()

        # ── File ──────────────────────────────────────────────────────
        file_menu = bar.addMenu("File")

        prefs_action = QAction("Preferences…", self)
        prefs_action.setShortcut("Ctrl+,")
        prefs_action.triggered.connect(self._open_preferences)
        file_menu.addAction(prefs_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # ── Connection ────────────────────────────────────────────────
        conn_menu = bar.addMenu("Connection")

        conn_mount = QAction("Connect Mount", self)
        conn_mount.setShortcut("Ctrl+M")
        conn_mount.triggered.connect(lambda: self._capture_panel._on_connect_mount())
        conn_menu.addAction(conn_mount)

        conn_cam = QAction("Connect Camera", self)
        conn_cam.setShortcut("Ctrl+Shift+C")
        conn_cam.triggered.connect(lambda: self._capture_panel._on_connect_camera())
        conn_menu.addAction(conn_cam)

        conn_menu.addSeparator()

        discover_action = QAction("Discover Devices", self)
        discover_action.setShortcut("Ctrl+D")
        discover_action.triggered.connect(lambda: self._capture_panel._on_discover())
        conn_menu.addAction(discover_action)

        conn_menu.addSeparator()

        disconnect_action = QAction("Disconnect All", self)
        disconnect_action.triggered.connect(lambda: self._capture_panel.shutdown())
        conn_menu.addAction(disconnect_action)

        # ── Capture ───────────────────────────────────────────────────
        cap_menu = bar.addMenu("Capture")

        take_action = QAction("Take Shot", self)
        take_action.setShortcut("Ctrl+T")
        take_action.triggered.connect(lambda: self._capture_panel._on_take_shot())
        cap_menu.addAction(take_action)

        seq_action = QAction("Start / Stop Sequence", self)
        seq_action.setShortcut("Ctrl+R")
        seq_action.triggered.connect(lambda: self._capture_panel._on_toggle_sequence())
        cap_menu.addAction(seq_action)

        cap_menu.addSeparator()

        preview_action = QAction("Live Preview", self)
        preview_action.setShortcut("Ctrl+P")
        preview_action.triggered.connect(lambda: self._capture_panel._on_toggle_preview())
        cap_menu.addAction(preview_action)

        cap_menu.addSeparator()

        stretch_action = QAction("Auto Stretch", self)
        stretch_action.setShortcut("Ctrl+A")
        stretch_action.triggered.connect(self._viewer._auto_stretch)
        cap_menu.addAction(stretch_action)

        # ── View ──────────────────────────────────────────────────────
        self._view_menu = bar.addMenu("View")

        reset_action = QAction("Reset Layout", self)
        reset_action.triggered.connect(self._reset_layout)
        self._view_menu.addSeparator()
        self._view_menu.addAction(reset_action)

        # ── Help ──────────────────────────────────────────────────────
        help_menu = bar.addMenu("Help")
        about_action = QAction("About SeerControl", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Docks
    # ------------------------------------------------------------------

    def _build_docks(self) -> None:
        self._capture_panel  = CapturePanel(config=self._config, parent=self)
        self._analysis_panel = AnalysisPanel(parent=self)
        self._log_panel      = LogPanel(parent=self)

        capture_dock  = _make_dock("Capture",  "capture",  self._capture_panel)
        analysis_dock = _make_dock("Analysis", "analysis", self._analysis_panel)
        log_dock      = _make_dock("Log",      "log",      self._log_panel)

        # Left: Capture (freely resizable — no max width)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,   capture_dock)

        # Right: Analysis
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,  analysis_dock)

        # Bottom: Log
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, log_dock)

        # Reasonable initial sizes
        self.resizeDocks(
            [capture_dock, analysis_dock],
            [280, 280],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks([log_dock], [140], Qt.Orientation.Vertical)

        # View menu toggles
        self._docks: dict[str, QDockWidget] = {}
        for name, dock in [
            ("Capture",  capture_dock),
            ("Analysis", analysis_dock),
            ("Log",      log_dock),
        ]:
            self._docks[name] = dock
            toggle = dock.toggleViewAction()
            toggle.setText(name)
            self._view_menu.insertAction(
                self._view_menu.actions()[0] if self._view_menu.actions() else None,
                toggle,
            )

    # ------------------------------------------------------------------
    # Top toolbar (always visible inside the window)
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # App label — Siril-style: bold blue Helvetica, version in muted suffix
        app_lbl = QLabel(
            f"SeerControl "
            f"<span style='color:{theme.FG_MUTED};font-size:11px;font-weight:normal;'>"
            f"— ASCOM control · v{self.APP_VERSION}</span>"
        )
        app_lbl.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:15px; font-weight:bold;"
            f" padding:2px 8px; background:transparent;"
        )
        tb.addWidget(app_lbl)
        tb.addSeparator()

        # Connection status badges — updated by _wire_signals via capture_panel
        self._tb_mount_lbl  = QLabel("○  Mount")
        self._tb_camera_lbl = QLabel("○  Camera")
        for lbl in (self._tb_mount_lbl, self._tb_camera_lbl):
            lbl.setStyleSheet(
                f"color:{theme.FG_MUTED}; font-size:11px;"
                f" padding:0 8px; background:transparent;"
            )
        tb.addWidget(self._tb_mount_lbl)
        tb.addWidget(self._tb_camera_lbl)
        tb.addSeparator()

        # Quick action buttons — flat, hover-only, Siril chrome
        def _tb_btn(label: str, slot, shortcut: str | None = None) -> QPushButton:
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setStyleSheet(
                f"QPushButton {{ color:{theme.FG}; background:transparent;"
                f" border:none; padding:4px 10px; font-size:11px; min-height:0; }}"
                f"QPushButton:hover {{ background:{theme.SURFACE}; color:{theme.ACCENT};"
                f" border-radius:3px; }}"
            )
            btn.clicked.connect(slot)
            if shortcut:
                btn.setToolTip(f"{label}  ({shortcut})")
            return btn

        tb.addWidget(_tb_btn("⚡ Discover",      lambda: self._capture_panel._on_discover()))
        tb.addWidget(_tb_btn("↗ Mount",           lambda: self._capture_panel._on_connect_mount()))
        tb.addWidget(_tb_btn("↗ Camera",          lambda: self._capture_panel._on_connect_camera()))
        tb.addSeparator()
        tb.addWidget(_tb_btn("◉ Take Shot",       lambda: self._capture_panel._on_take_shot(),       "Ctrl+T"))
        tb.addWidget(_tb_btn("▶ Sequence",         lambda: self._capture_panel._on_toggle_sequence(), "Ctrl+R"))
        tb.addWidget(_tb_btn("▶ Preview",          lambda: self._capture_panel._on_toggle_preview(),  "Ctrl+P"))
        tb.addSeparator()
        tb.addWidget(_tb_btn("☀ Auto Stretch",     self._viewer._auto_stretch,                        "Ctrl+A"))

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        # Frames: CapturePanel → FitsViewer + AnalysisPanel
        self._capture_panel.frame_display.connect(self._viewer.display)
        self._capture_panel.frame_display.connect(self._analysis_panel.update_frame)

        # Log
        self._capture_panel.log_message.connect(self._log_panel.append)
        self._capture_panel.status_changed.connect(self._on_status_changed)

        # Toolbar connection badges
        self._capture_panel.mount_conn_changed.connect(self._on_mount_conn_changed)
        self._capture_panel.camera_conn_changed.connect(self._on_camera_conn_changed)

        # Analysis → FitsViewer
        self._analysis_panel.levels_changed.connect(self._viewer.set_levels)
        self._analysis_panel.gamma_changed.connect(self._viewer.set_gamma)
        self._analysis_panel.auto_stretch_requested.connect(self._viewer._auto_stretch)

        # Analysis channel combo → CapturePanel channel switch
        self._analysis_panel.channel_changed.connect(self._capture_panel.set_channel)

        # Stellarium card → MainWindow handlers
        card = self._capture_panel.stellarium_card
        card.start_server_requested.connect(self._on_stellarium_start)
        card.stop_server_requested.connect(self._on_stellarium_stop)
        card.pull_requested.connect(self._on_stellarium_pull)

    def _on_mount_conn_changed(self, connected: bool) -> None:
        dot = "●" if connected else "○"
        color = theme.SUCCESS if connected else theme.FG_MUTED
        self._tb_mount_lbl.setText(f"{dot}  Mount")
        self._tb_mount_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; padding:0 8px; background:transparent;"
        )

    def _on_camera_conn_changed(self, connected: bool) -> None:
        dot = "●" if connected else "○"
        color = theme.SUCCESS if connected else theme.FG_MUTED
        self._tb_camera_lbl.setText(f"{dot}  Camera")
        self._tb_camera_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; padding:0 8px; background:transparent;"
        )

    # ------------------------------------------------------------------
    # Stellarium integration
    # ------------------------------------------------------------------

    def _on_stellarium_start(self, host: str, port: int) -> None:
        if self._stellarium_worker is not None:
            self._stop_stellarium_worker()
        worker = StellariumWorker(host=host, port=port)
        card = self._capture_panel.stellarium_card

        worker.target_received.connect(self._on_stellarium_target)
        worker.client_count_changed.connect(card.set_client_count)
        worker.server_started.connect(lambda: card.set_server_state(True))
        worker.server_stopped.connect(lambda: card.set_server_state(False))
        worker.error_occurred.connect(self._on_stellarium_error)
        # Keep the asyncio side fed with every mount position update.
        self._capture_panel.position_updated.connect(worker.update_mount_position)

        self._stellarium_worker = worker
        worker.start()
        self._capture_panel.log_message.emit(
            "INFO", f"Stellarium server starting on {host}:{port}"
        )

    def _on_stellarium_stop(self) -> None:
        self._stop_stellarium_worker()

    def _stop_stellarium_worker(self) -> None:
        worker = self._stellarium_worker
        if worker is None:
            return
        try:
            self._capture_panel.position_updated.disconnect(worker.update_mount_position)
        except (TypeError, RuntimeError):
            pass
        worker.stop()
        worker.wait(3000)
        self._stellarium_worker = None

    def _on_stellarium_target(self, ra_hours: float, dec_degrees: float) -> None:
        self._capture_panel.stellarium_card.flash_goto(ra_hours, dec_degrees)
        self._capture_panel.goto_target(ra_hours, dec_degrees, label="goto")

    def _on_stellarium_error(self, message: str) -> None:
        self._capture_panel.log_message.emit("ERROR", f"Stellarium: {message}")
        self._capture_panel.stellarium_card.set_server_state(False, "✗  error")

    def _on_stellarium_pull(self, host: str, port: int) -> None:
        """Run the HTTP "Pull selected" call on a background thread.

        The call blocks for up to ~2 s on a timeout — we never want that on
        the UI thread.
        """
        runner = _PullRunner(host=host, port=port)
        runner.signals.target.connect(self._on_pull_target)
        runner.signals.failed.connect(
            lambda msg: self._capture_panel.log_message.emit("WARN", f"Stellarium pull: {msg}")
        )
        QThreadPool.globalInstance().start(runner)

    def _on_pull_target(self, name: str, ra_hours: float, dec_degrees: float) -> None:
        self._capture_panel.log_message.emit(
            "OK", f"Stellarium → {name}  RA {ra_hours:.4f}h  Dec {dec_degrees:+.4f}°"
        )
        self._capture_panel.goto_target(ra_hours, dec_degrees, label=f"target '{name}'")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._status_lbl = QLabel("Not connected")
        self._status_lbl.setProperty("class", "muted")
        sb.addWidget(self._status_lbl)

    def _on_status_changed(self, text: str) -> None:
        self._status_lbl.setText(text)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _restore_state(self) -> None:
        geo = self._config.get(_CFG_GEOMETRY)
        state = self._config.get(_CFG_STATE)
        if geo:
            try:
                self.restoreGeometry(QByteArray(base64.b64decode(geo)))
            except Exception as exc:
                logger.warning("Could not restore geometry: %s", exc)
        if state:
            try:
                self.restoreState(QByteArray(base64.b64decode(state)))
            except Exception as exc:
                logger.warning("Could not restore state: %s", exc)

    def _save_state(self) -> None:
        self._config.set(_CFG_GEOMETRY, base64.b64encode(bytes(self.saveGeometry())).decode())
        self._config.set(_CFG_STATE,    base64.b64encode(bytes(self.saveState())).decode())

    def _reset_layout(self) -> None:
        self._config.set(_CFG_GEOMETRY, None)
        self._config.set(_CFG_STATE, None)
        self.statusBar().showMessage("Layout will reset on next launch.", 4000)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

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
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_stellarium_worker()
        self._capture_panel.shutdown()
        self._save_state()
        logger.info("MainWindow closed")
        super().closeEvent(event)
