"""Shell — the Argos main window. NINA-style: the night happens in ONE screen.

    Equipment — connect the Seestar devices + the Stellarium server
                (a 2-minute setup stop; mode id "connect" for back-compat)
    Capture   — THE screen: hero image, camera + sequencer, mount goto,
                focuser + V-curve, photometry overlays and the live curve
    Analyze   — post-prod: reload curves, vetting, AAVSO export
    Settings  — observer, site, paths, appearance

The session layer owns the hardware (WS5): ``DeviceSession`` holds the device
handles, pollers and the Stellarium server; ``AcquisitionEngine`` holds the
camera-ownership state machine and the capture/solve/photometry workers. The
Capture page (``ImagingPage``) is a view over the two. The Equipment page
emits connect/disconnect intents that the Shell routes to the DeviceSession;
device-state updates flow back to the status bar and the Equipment page.
Targeting is driven by Stellarium (select an object, Ctrl+1) over the TCP
telescope-control protocol, or by the mount dock's goto fields.
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
from argos.core.session.acquisition_engine import AcquisitionEngine
from argos.core.session.device_session import DeviceSession
from argos.ui import theme
from argos.ui.pages.configuration_page import ConfigurationPage
from argos.ui.pages.connection_page import ConnectionPage
from argos.ui.pages.imaging_page import ImagingPage
from argos.ui.pages.analyze_page import AnalyzeScreen
from argos.ui.sidebar import MODES, Sidebar
from argos.ui.statusbar import TopStatusBar
from argos.workers.camera_service import CameraState
from argos.workers.network_monitor import NetworkMonitor

logger = logging.getLogger(__name__)

_CFG_GEOMETRY = "ui.shell.geometry"
_CFG_STATE = "ui.shell.state"
_CFG_MODE = "ui.shell.mode"

#: Modes that need hardware to be useful. Devices are never connected at
#: startup, so restoring one of these would land the user on a dead screen —
#: we land on Equipment instead (the persisted mode is kept for the session).
_HARDWARE_MODES = frozenset({"capture"})


class Shell(QMainWindow):
    """Three-mode workspace shell."""

    APP_VERSION = "0.3.1"

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

        self.setWindowTitle(f"Argos  v{self.APP_VERSION}")
        self.setMinimumSize(1100, 700)
        self.resize(1440, 900)

        self._build_layout()
        self._build_menu()
        self._wire_signals()
        self._restore_state()

        last_mode = self._config.get(_CFG_MODE) or "connect"
        if last_mode not in self._pages or last_mode in _HARDWARE_MODES:
            last_mode = "connect"
        self._sidebar.select(last_mode)
        self._refresh_sidebar_states()

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

        # The session layer: DeviceSession owns the device handles/pollers
        # and the Stellarium server; AcquisitionEngine owns the camera
        # ownership state machine + capture/solve/photometry workers. The
        # pages are views over the two.
        self._session = DeviceSession(self._config, parent=self)
        self._engine = AcquisitionEngine(self._config, self._session, parent=self)

        # Quiet background reachability checks → the status-bar network dots.
        self._network_monitor = NetworkMonitor(self._config, parent=self)
        self._network_monitor.state_changed.connect(self._status.set_network)
        self._network_monitor.start()

        self._connection = ConnectionPage(self._config)
        self._acquisition = ImagingPage(self._config, self._session, self._engine)
        self._configuration = ConfigurationPage(self._config)
        self._analyze = AnalyzeScreen(self._config)

        # NINA-style: the night happens in Capture; Equipment is setup,
        # Analyze is post-prod. (Mode id "connect" kept for config back-compat.)
        self._pages: dict[str, QWidget] = {
            "connect": self._connection,
            "capture": self._acquisition,
            "analyze": self._analyze,
            "settings": self._configuration,
        }
        self._page_indices: dict[str, int] = {
            mode_id: self._stack.addWidget(page) for mode_id, page in self._pages.items()
        }

        # Connection/activity state feeding the sidebar phase dots.
        self._conn_state: dict[str, str] = dict.fromkeys(
            ("mount", "camera", "filterwheel", "focuser"), "disconnected"
        )
        self._sequence_active = False
        self._autofocus_active = False

        self._wire_pages()

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        bar = self.menuBar()

        view = bar.addMenu("View")
        # Derived from the sidebar's MODES tuple — one source of truth, so a
        # phase insertion can't silently desynchronise the F-key bindings.
        for i, (mode_id, label, _tooltip) in enumerate(MODES):
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

        # Capture visibility on every screen: sequence progress + LIVE chip in
        # the top strip, activity dots on the sidebar (WS4).
        self._acquisition.sequence_running.connect(self._on_sequence_running)
        self._acquisition.sequence_progress.connect(self._status.set_sequence_progress)
        self._acquisition.hfd_updated.connect(self._status.set_hfd)
        self._acquisition.camera_state_changed.connect(self._on_camera_state)
        self._acquisition.autofocus_state.connect(self._on_autofocus_state)
        self._status.capture_clicked.connect(lambda: self._sidebar.select("capture"))

        # Connection intents → device session (dict-dispatched per device).
        self._connection.discover_requested.connect(self._session.discover)
        self._connection.connect_requested.connect(self._session.connect_device)
        self._connection.disconnect_requested.connect(self._session.disconnect_device)
        self._connection.connect_all_requested.connect(self._session.connect_all)
        self._connection.disconnect_all_requested.connect(self._session.disconnect_all)
        self._session.discovered_address.connect(self._connection.set_discovered_address)

        # Stellarium card (on the Connection page) ↔ the session-owned server.
        card = self._connection.stellarium_card
        card.start_server_requested.connect(self._session.start_stellarium)
        card.stop_server_requested.connect(self._session.stop_stellarium)
        self._session.stellarium_state.connect(card.set_server_state)
        self._session.stellarium_clients.connect(card.set_client_count)
        self._session.stellarium_target.connect(self._on_stellarium_target)
        self._session.stellarium_error.connect(self._on_stellarium_error)

    # ------------------------------------------------------------------
    # Stellarium fan-out (the session owns the server worker)
    # ------------------------------------------------------------------

    def _on_stellarium_target(self, ra_hours: float, dec_degrees: float) -> None:
        self._connection.stellarium_card.flash_goto(ra_hours, dec_degrees)
        self._acquisition.goto_target(ra_hours, dec_degrees, label="goto")

    def _on_stellarium_error(self, message: str) -> None:
        self._connection.stellarium_card.set_server_state(False, "✗  error")

    # ------------------------------------------------------------------
    # Status fan-out
    # ------------------------------------------------------------------

    def _on_device_state_changed(self, device_id: str, state: str, info: str) -> None:
        self._status.set_device_state(device_id, state, info)
        self._connection.set_device_state(device_id, state, info)

        self._conn_state[device_id] = state
        self._refresh_sidebar_states()

    def _on_sequence_running(self, running: bool) -> None:
        self._sequence_active = running
        self._status.set_sequence_running(running)
        self._refresh_sidebar_states()

    def _on_autofocus_state(self, running: bool) -> None:
        self._autofocus_active = running
        self._refresh_sidebar_states()

    def _on_camera_state(self, state: CameraState) -> None:
        self._status.set_live(state is CameraState.LIVE)

    def _refresh_sidebar_states(self) -> None:
        """Recompute the sidebar mode dots from device + activity state.

        ready = prerequisites met, active = running now, blocked = a required
        device is missing. Equipment/Analyze/Settings stay neutral — they are
        always usable.
        """
        camera_up = self._conn_state["camera"] in ("connected", "busy")
        if self._sequence_active or self._autofocus_active:
            self._sidebar.set_mode_state("capture", "active")
        else:
            self._sidebar.set_mode_state("capture", "ready" if camera_up else "blocked")

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
        # The Capture page owns its own dockable workspace (WS9a) — persist it
        # alongside the shell's own dock state.
        self._acquisition.save_layout()

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
        # Order matters: stop the capture workers first (they hold device
        # references), then the session's pollers + Stellarium server.
        self._acquisition.shutdown()
        self._session.shutdown()
        self._network_monitor.stop()
        # A check in flight can hold the thread for up to three connect
        # timeouts (host + two internet targets) — wait long enough.
        self._network_monitor.wait(6000)
        self._save_state()
        self._config.save()
        logger.info("Shell closed")
        super().closeEvent(event)
