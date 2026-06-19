"""Shell — the Argos main window built around the workflow phases.

A NINA-inspired structure: a left sidebar of phases (the chronology of a
photometry night, see docs/ui_design.md), a permanent status bar across the
top, and a single workspace area that swaps content per phase.

    Connect     — connect the Seestar devices + the Stellarium server
    Target      — point, plate-solve and centre the field
    Focus       — reach and lock best focus
    Photometry  — pick target, comparison and check stars
    Capture     — run the sequence and monitor frame health (where time is spent)
    Analyze     — inspect the light curve and export AAVSO
    Settings    — observer, site, paths, appearance

The Capture page (``ImagingPage``) is the live engine: it owns the device
handles and workers. Target / Focus / Photometry are design scaffolds that
deep-link into the Capture controls until the per-phase split lands; Analyze
launches its own companion window. The Connect page emits connect/disconnect
intents that the Shell routes to the Capture page; device-state updates flow
back to the status bar and the Connect page. Targeting is driven entirely by
Stellarium (select an object, Ctrl+1) over the TCP telescope-control protocol —
there is no in-app search.
"""

from __future__ import annotations

import base64
import logging

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from argos.core.config import Config
from argos.ui import theme
from argos.ui.pages.configuration_page import ConfigurationPage
from argos.ui.pages.connection_page import ConnectionPage
from argos.ui.pages.imaging_page import ImagingPage
from argos.ui.pages.focus_page import FocusScreen
from argos.ui.pages.phase_scaffold import (
    AnalyzeLauncher,
    photometry_scaffold,
)
from argos.ui.pages.target_page import TargetScreen
from argos.ui.sidebar import Sidebar
from argos.ui.statusbar import TopStatusBar
from argos.workers.stellarium_worker import StellariumWorker

logger = logging.getLogger(__name__)

_CFG_GEOMETRY = "ui.shell.geometry"
_CFG_STATE = "ui.shell.state"
_CFG_MODE = "ui.shell.mode"


class Shell(QMainWindow):
    """Three-mode workspace shell."""

    APP_VERSION = "0.2.1"

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._stellarium_worker: StellariumWorker | None = None

        self.setWindowTitle(f"Argos  v{self.APP_VERSION}")
        self.setMinimumSize(1100, 700)
        self.resize(1440, 900)

        self._build_layout()
        self._build_menu()
        self._wire_signals()
        self._restore_state()

        last_mode = self._config.get(_CFG_MODE) or "connect"
        if last_mode not in self._pages:
            last_mode = "connect"
        self._sidebar.select(last_mode)

        logger.info("Shell initialised (mode=%s)", last_mode)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        central = QWidget()
        central.setStyleSheet(f"background:{theme.BG};")
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._status = TopStatusBar()
        v.addWidget(self._status)

        self._stack = QStackedWidget()
        v.addWidget(self._stack, 1)

        self.setCentralWidget(central)

        self._sidebar = Sidebar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._sidebar)

        self._connection = ConnectionPage(self._config)
        self._acquisition = ImagingPage(self._config)  # the Capture engine
        self._configuration = ConfigurationPage(self._config)
        self._target = TargetScreen(self._config)
        self._focus = FocusScreen()
        self._photometry = photometry_scaffold()
        self._analyze = AnalyzeLauncher()

        # Workflow-ordered pages (docs/ui_design.md). Connect / Capture / Settings
        # are live; Target / Focus / Photometry are design scaffolds that deep-link
        # into the still-shared Capture controls; Analyze launches its window.
        self._pages: dict[str, QWidget] = {
            "connect": self._connection,
            "target": self._target,
            "focus": self._focus,
            "photometry": self._photometry,
            "capture": self._acquisition,
            "analyze": self._analyze,
            "settings": self._configuration,
        }
        self._page_indices: dict[str, int] = {
            mode_id: self._stack.addWidget(page) for mode_id, page in self._pages.items()
        }

        # Scaffolds deep-link to the live controls hosted on the Capture page.
        self._target.open_controls.connect(lambda: self._open_capture_tab("Session"))
        self._target.slew_requested.connect(
            lambda ra, dec: self._acquisition.goto_target(ra, dec, "target")
        )
        self._focus.open_controls.connect(lambda: self._open_capture_tab("Equipment"))
        self._focus.autofocus_requested.connect(self._acquisition.request_autofocus)
        self._focus.nudge_requested.connect(self._acquisition.nudge_focuser)
        self._acquisition.autofocus_step.connect(self._focus.add_sample)
        self._acquisition.autofocus_best.connect(self._focus.set_best)
        self._acquisition.autofocus_state.connect(self._focus.set_running)
        self._photometry.open_controls.connect(lambda: self._open_capture_tab("Session"))

        # Track connection state to know when to pulse the next-step hint.
        self._conn_state: dict[str, str] = dict.fromkeys(
            ("mount", "camera", "filterwheel", "focuser"), "disconnected"
        )

        self._wire_pages()

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        bar = self.menuBar()

        view = bar.addMenu("View")
        for i, (mode_id, label) in enumerate(
            (
                ("connect", "Connect"),
                ("target", "Target"),
                ("focus", "Focus"),
                ("photometry", "Photometry"),
                ("capture", "Capture"),
                ("analyze", "Analyze"),
                ("settings", "Settings"),
            )
        ):
            action = QAction(label, self)
            action.setShortcut(QKeySequence(f"F{i + 1}"))
            action.triggered.connect(lambda _c, m=mode_id: self._sidebar.select(m))
            view.addAction(action)

        view.addSeparator()
        reset = QAction("Reset Window Layout", self)
        reset.triggered.connect(self._reset_layout)
        view.addAction(reset)

        help_menu = bar.addMenu("Help")
        about = QAction("About Argos", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        self._sidebar.mode_changed.connect(self._on_mode_changed)
        self._status.badge_clicked.connect(self._on_badge_clicked)

    def _wire_pages(self) -> None:
        # Acquisition page → global status bar.
        self._acquisition.device_state_changed.connect(self._on_device_state_changed)
        self._acquisition.tracking_changed.connect(self._status.set_tracking)
        self._acquisition.action_changed.connect(self._status.set_action)

        # Connection intents → acquisition session.
        self._connection.discover_requested.connect(self._acquisition.start_discovery)
        self._connection.connect_requested.connect(self._on_connect_device)
        self._connection.disconnect_requested.connect(self._on_disconnect_device)
        self._connection.connect_all_requested.connect(self._on_connect_all)
        self._connection.disconnect_all_requested.connect(self._acquisition.disconnect_all)
        self._acquisition.discovered_address.connect(self._connection.set_discovered_address)

        # Stellarium card (on the Connection page).
        card = self._connection.stellarium_card
        card.start_server_requested.connect(self._on_stellarium_start)
        card.stop_server_requested.connect(self._on_stellarium_stop)

    # ------------------------------------------------------------------
    # Device connection routing
    # ------------------------------------------------------------------

    def _on_connect_device(self, device_id: str, host: str, port: int) -> None:
        if device_id == "mount":
            self._acquisition.connect_mount(host, port)
        elif device_id == "camera":
            self._acquisition.connect_camera(host, port)
        elif device_id == "filterwheel":
            self._acquisition.connect_filterwheel(host, port)
        elif device_id == "focuser":
            self._acquisition.connect_focuser(host, port)
        else:
            self._status.set_action(f"{device_id.title()} connect — not implemented yet")

    def _on_disconnect_device(self, device_id: str) -> None:
        if device_id == "mount":
            self._acquisition.disconnect_mount()
        elif device_id == "camera":
            self._acquisition.disconnect_camera()
        elif device_id == "filterwheel":
            self._acquisition.disconnect_filterwheel()
        elif device_id == "focuser":
            self._acquisition.disconnect_focuser()

    def _on_connect_all(self, host: str, port: int) -> None:
        self._acquisition.connect_mount(host, port)
        self._acquisition.connect_camera(host, port)
        self._acquisition.connect_filterwheel(host, port)
        self._acquisition.connect_focuser(host, port)

    # ------------------------------------------------------------------
    # Stellarium integration (TCP telescope-control server only)
    # ------------------------------------------------------------------

    def _on_stellarium_start(self, host: str, port: int) -> None:
        if self._stellarium_worker is not None:
            self._stop_stellarium_worker()
        card = self._connection.stellarium_card

        worker = StellariumWorker(host=host, port=port)
        worker.target_received.connect(self._on_stellarium_target)
        worker.client_count_changed.connect(card.set_client_count)
        worker.server_started.connect(lambda: card.set_server_state(True))
        worker.server_stopped.connect(lambda: card.set_server_state(False))
        worker.error_occurred.connect(self._on_stellarium_error)
        # Feed every mount position update so the Stellarium reticle follows.
        self._acquisition.position_updated.connect(worker.update_mount_position)

        self._config.set("stellarium.host", host)
        self._config.set("stellarium.port", port)

        self._stellarium_worker = worker
        worker.start()
        self._acquisition.log_message.emit("INFO", f"Stellarium server starting on {host}:{port}")

    def _on_stellarium_stop(self) -> None:
        self._stop_stellarium_worker()

    def _stop_stellarium_worker(self) -> None:
        worker = self._stellarium_worker
        if worker is None:
            return
        try:
            self._acquisition.position_updated.disconnect(worker.update_mount_position)
        except (TypeError, RuntimeError):
            pass
        worker.stop()
        worker.wait(3000)
        self._stellarium_worker = None

    def _on_stellarium_target(self, ra_hours: float, dec_degrees: float) -> None:
        self._connection.stellarium_card.flash_goto(ra_hours, dec_degrees)
        self._acquisition.goto_target(ra_hours, dec_degrees, label="goto")
        self._target.set_target(ra_hours, dec_degrees, "Stellarium target")

    def _on_stellarium_error(self, message: str) -> None:
        self._acquisition.log_message.emit("ERROR", f"Stellarium: {message}")
        self._connection.stellarium_card.set_server_state(False, "✗  error")

    # ------------------------------------------------------------------
    # Status fan-out
    # ------------------------------------------------------------------

    def _on_device_state_changed(self, device_id: str, state: str, info: str) -> None:
        self._status.set_device_state(device_id, state, info)
        self._connection.set_device_state(device_id, state, info)

        self._conn_state[device_id] = state
        if self._conn_state["mount"] == "connected" and self._conn_state["camera"] == "connected":
            self._sidebar.pulse("capture")

    def _on_mode_changed(self, mode_id: str) -> None:
        index = self._page_indices.get(mode_id)
        if index is None:
            return
        self._stack.setCurrentIndex(index)
        self._config.set(_CFG_MODE, mode_id)
        logger.debug("Switched to mode: %s", mode_id)

    def _on_badge_clicked(self, device_id: str) -> None:
        if self._status.device_state(device_id) == "disconnected":
            self._sidebar.select("connect")

    def _open_capture_tab(self, tab_label: str) -> None:
        """Switch to Capture and select one of its right-rail control tabs.

        Used by the Target / Focus / Photometry scaffolds to deep-link into the
        controls that still live on the shared Capture page (transitional, until
        the per-phase split lands).
        """
        self._sidebar.select("capture")
        self._acquisition.select_rail_tab(tab_label)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def status(self) -> TopStatusBar:
        return self._status

    @property
    def sidebar(self) -> Sidebar:
        return self._sidebar

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
                logger.warning("restoreGeometry failed: %s", exc)
        if state:
            try:
                self.restoreState(QByteArray(base64.b64decode(state)))
            except Exception as exc:
                logger.warning("restoreState failed: %s", exc)

    def _save_state(self) -> None:
        self._config.set(_CFG_GEOMETRY, base64.b64encode(bytes(self.saveGeometry())).decode())
        self._config.set(_CFG_STATE, base64.b64encode(bytes(self.saveState())).decode())

    def _reset_layout(self) -> None:
        self._config.set(_CFG_GEOMETRY, None)
        self._config.set(_CFG_STATE, None)
        self.statusBar().showMessage("Window layout will reset on next launch.", 4000)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        self.statusBar().showMessage(
            f"Argos v{self.APP_VERSION} — Seestar S30 Pro controller",
            4000,
        )

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_stellarium_worker()
        self._acquisition.shutdown()
        self._save_state()
        self._config.save()
        logger.info("Shell closed")
        super().closeEvent(event)
