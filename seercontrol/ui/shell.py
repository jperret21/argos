"""Shell — the new SeerControl main window built around 4 modes.

Replaces the old ``MainWindow`` (the dockable layout) with a NINA-inspired
structure: a left sidebar of modes, a permanent status bar across the top,
and a single workspace area that swaps content per mode.

Until the real mode pages land in sprints R2-R5, the Imaging/Target/Equipment/
Settings pages are placeholders. The Shell already wires the sidebar -> stack
switch and exposes the slots that the future pages will plug into for status
updates (mount/camera/etc. connection, tracking, last action).

Activate via ``main.py``; ``SEERCONTROL_LEGACY=1`` falls back to the old
``MainWindow`` while the redesign is in flight.
"""

from __future__ import annotations

import base64
import logging

from PyQt6.QtCore import QByteArray, QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.config import Config
from seercontrol.core.stellarium.remote_pull import pull_selected_object
from seercontrol.ui import theme
from seercontrol.ui.pages.equipment_page import EquipmentPage
from seercontrol.ui.pages.imaging_page import ImagingPage
from seercontrol.ui.pages.settings_page import SettingsPage
from seercontrol.ui.pages.target_page import TargetPage
from seercontrol.ui.sidebar import Sidebar
from seercontrol.ui.statusbar import TopStatusBar
from seercontrol.workers.stellarium_worker import StellariumWorker

logger = logging.getLogger(__name__)

_CFG_GEOMETRY = "ui.shell.geometry"
_CFG_STATE    = "ui.shell.state"
_CFG_MODE     = "ui.shell.mode"


# --------------------------------------------------------------------------- #
# Stellarium HTTP pull runner (one-shot, off-thread)                           #
# --------------------------------------------------------------------------- #

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
        except Exception as exc:  # network errors already swallowed inside
            self.signals.failed.emit(str(exc))
            return
        if target is None:
            self.signals.failed.emit("no selection or plugin not running")
            return
        self.signals.target.emit(target.name, target.ra_hours, target.dec_degrees)


class Shell(QMainWindow):
    """Three-mode workspace shell.

    Top-level layout::

        ┌─────────────────────────────────────────┐
        │ TopStatusBar (device badges + tracking) │
        ├──┬──────────────────────────────────────┤
        │S │                                      │
        │i │      QStackedWidget (current page)   │
        │d │                                      │
        │e │                                      │
        └──┴──────────────────────────────────────┘
    """

    APP_VERSION = "0.2.0-redesign"

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._stellarium_worker: StellariumWorker | None = None

        self.setWindowTitle(f"SeerControl  v{self.APP_VERSION}")
        self.setMinimumSize(1100, 700)
        self.resize(1440, 900)

        self._build_layout()
        self._build_menu()
        self._wire_signals()
        self._restore_state()

        # Default landing mode: equipment when nothing is connected, else
        # whatever the user was on last.
        last_mode = self._config.get(_CFG_MODE) or "equipment"
        self._sidebar.select(last_mode)

        logger.info("Shell initialised (mode=%s)", last_mode)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        # Central widget = status bar on top + stacked workspace below.
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

        # Left sidebar — added as a Qt toolbar so it docks to the side cleanly.
        self._sidebar = Sidebar(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._sidebar)

        # Page registry — keep references so we can swap them in later sprints.
        self._pages: dict[str, QWidget] = {
            "equipment": EquipmentPage(self._config),
            "target":    TargetPage(self._config),
            "imaging":   ImagingPage(self._config),
            "settings":  SettingsPage(),
        }
        self._page_indices: dict[str, int] = {
            mode_id: self._stack.addWidget(page)
            for mode_id, page in self._pages.items()
        }
        # Track connection state to know when to pulse the next-step hint.
        self._connection: dict[str, str] = dict.fromkeys(
            ("mount", "camera", "filterwheel", "focuser"), "disconnected"
        )
        self._wire_imaging_page()
        self._wire_equipment_page()
        self._wire_target_page()

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        bar = self.menuBar()

        view = bar.addMenu("View")
        for i, (mode_id, label) in enumerate(
            (("equipment", "Equipment"), ("target", "Target"),
             ("imaging", "Imaging"),     ("settings", "Settings"))
        ):
            action = QAction(label, self)
            action.setShortcut(QKeySequence(f"F{i + 1}"))
            action.triggered.connect(lambda _c, m=mode_id: self._sidebar.select(m))
            view.addAction(action)

        view.addSeparator()
        reset = QAction("Reset Window Layout", self)
        reset.triggered.connect(self._reset_layout)
        view.addAction(reset)

        # Help
        help_menu = bar.addMenu("Help")
        about = QAction("About SeerControl", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        self._sidebar.mode_changed.connect(self._on_mode_changed)
        self._status.badge_clicked.connect(self._on_badge_clicked)

    def _wire_imaging_page(self) -> None:
        """Connect ImagingPage upward signals to the global status bar +
        forward device state to the Equipment page + Stellarium card."""
        page = self._pages.get("imaging")
        if not isinstance(page, ImagingPage):
            return
        page.device_state_changed.connect(self._on_device_state_changed)
        page.tracking_changed.connect(self._status.set_tracking)
        page.action_changed.connect(self._status.set_action)

        card = page.stellarium_card
        card.start_server_requested.connect(self._on_stellarium_start)
        card.stop_server_requested.connect(self._on_stellarium_stop)
        card.pull_requested.connect(self._on_stellarium_pull)

    def _wire_target_page(self) -> None:
        """Connect TargetPage's slew-and-start signal to ImagingPage + sidebar."""
        target = self._pages.get("target")
        if not isinstance(target, TargetPage):
            return
        target.slew_and_start_requested.connect(self._on_slew_and_start)

    def _on_slew_and_start(
        self, ra_h: float, dec_d: float, profile, object_name: str
    ) -> None:
        """Switch to Imaging mode, then trigger the slew + sequence."""
        self._sidebar.select("imaging")
        imaging = self._pages.get("imaging")
        if not isinstance(imaging, ImagingPage):
            return
        imaging.slew_and_start(ra_h, dec_d, profile, object_name)

    def _wire_equipment_page(self) -> None:
        """Route EquipmentPage intents into ImagingPage's public API."""
        equip = self._pages.get("equipment")
        imaging = self._pages.get("imaging")
        if not isinstance(equip, EquipmentPage) or not isinstance(imaging, ImagingPage):
            return
        equip.discover_requested.connect(imaging.start_discovery)
        equip.connect_requested.connect(self._on_connect_device)
        equip.disconnect_requested.connect(self._on_disconnect_device)
        equip.connect_all_requested.connect(self._on_connect_all)
        equip.disconnect_all_requested.connect(imaging.disconnect_all)
        # Discovery → fill the form on EquipmentPage.
        imaging.discovered_address.connect(equip.set_discovered_address)

    def _on_connect_device(self, device_id: str, host: str, port: int) -> None:
        imaging = self._pages["imaging"]
        if not isinstance(imaging, ImagingPage):
            return
        if device_id == "mount":
            imaging.connect_mount(host, port)
        elif device_id == "camera":
            imaging.connect_camera(host, port)
        elif device_id == "focuser":
            imaging.connect_focuser(host, port)
        else:
            # Filter wheel not yet wired — show a friendly message.
            self._status.set_action(
                f"{device_id.title()} connect — not implemented yet (R5)"
            )

    def _on_disconnect_device(self, device_id: str) -> None:
        imaging = self._pages["imaging"]
        if not isinstance(imaging, ImagingPage):
            return
        if device_id == "mount":
            imaging.disconnect_mount()
        elif device_id == "camera":
            imaging.disconnect_camera()
        elif device_id == "focuser":
            imaging.disconnect_focuser()

    def _on_connect_all(self, host: str, port: int) -> None:
        imaging = self._pages["imaging"]
        if not isinstance(imaging, ImagingPage):
            return
        imaging.connect_mount(host, port)
        imaging.connect_camera(host, port)
        imaging.connect_focuser(host, port)

    # ------------------------------------------------------------------
    # Stellarium integration
    # ------------------------------------------------------------------

    def _on_stellarium_start(self, host: str, port: int) -> None:
        if self._stellarium_worker is not None:
            self._stop_stellarium_worker()
        imaging = self._pages["imaging"]
        if not isinstance(imaging, ImagingPage):
            return
        card = imaging.stellarium_card

        worker = StellariumWorker(host=host, port=port)
        worker.target_received.connect(self._on_stellarium_target)
        worker.client_count_changed.connect(card.set_client_count)
        worker.server_started.connect(lambda: card.set_server_state(True))
        worker.server_stopped.connect(lambda: card.set_server_state(False))
        worker.error_occurred.connect(self._on_stellarium_error)
        # Keep the asyncio side fed with every mount position update so the
        # Stellarium on-screen reticle follows the mount in real time.
        imaging.position_updated.connect(worker.update_mount_position)

        self._stellarium_worker = worker
        worker.start()
        imaging.log_message.emit(
            "INFO", f"Stellarium server starting on {host}:{port}"
        )

    def _on_stellarium_stop(self) -> None:
        self._stop_stellarium_worker()

    def _stop_stellarium_worker(self) -> None:
        worker = self._stellarium_worker
        if worker is None:
            return
        imaging = self._pages.get("imaging")
        if isinstance(imaging, ImagingPage):
            try:
                imaging.position_updated.disconnect(worker.update_mount_position)
            except (TypeError, RuntimeError):
                pass
        worker.stop()
        worker.wait(3000)
        self._stellarium_worker = None

    def _on_stellarium_target(self, ra_hours: float, dec_degrees: float) -> None:
        imaging = self._pages["imaging"]
        if not isinstance(imaging, ImagingPage):
            return
        imaging.stellarium_card.flash_goto(ra_hours, dec_degrees)
        imaging.goto_target(ra_hours, dec_degrees, label="goto")

    def _on_stellarium_error(self, message: str) -> None:
        imaging = self._pages.get("imaging")
        if isinstance(imaging, ImagingPage):
            imaging.log_message.emit("ERROR", f"Stellarium: {message}")
            imaging.stellarium_card.set_server_state(False, "✗  error")

    def _on_stellarium_pull(self, host: str, port: int) -> None:
        """Run the HTTP 'Pull selected' call on a background thread."""
        runner = _PullRunner(host=host, port=port)
        runner.signals.target.connect(self._on_stellarium_pull_target)
        runner.signals.failed.connect(self._on_stellarium_pull_failed)
        QThreadPool.globalInstance().start(runner)

    def _on_stellarium_pull_target(
        self, name: str, ra_hours: float, dec_degrees: float
    ) -> None:
        imaging = self._pages["imaging"]
        if not isinstance(imaging, ImagingPage):
            return
        imaging.log_message.emit(
            "OK", f"Stellarium → {name}  RA {ra_hours:.4f}h Dec {dec_degrees:+.4f}°"
        )
        imaging.goto_target(ra_hours, dec_degrees, label=f"target '{name}'")

    def _on_stellarium_pull_failed(self, msg: str) -> None:
        imaging = self._pages.get("imaging")
        if isinstance(imaging, ImagingPage):
            imaging.log_message.emit("WARN", f"Stellarium pull: {msg}")

    # ------------------------------------------------------------------

    def _on_device_state_changed(self, device_id: str, state: str, info: str) -> None:
        """Fan one device-state event out to the status bar + Equipment page."""
        self._status.set_device_state(device_id, state, info)
        equip = self._pages.get("equipment")
        if isinstance(equip, EquipmentPage):
            equip.set_device_state(device_id, state, info)

        # Once Mount + Camera both land, pulse Target as the next step.
        self._connection[device_id] = state
        if (
            self._connection["mount"] == "connected"
            and self._connection["camera"] == "connected"
        ):
            self._sidebar.pulse("target")

    def _on_mode_changed(self, mode_id: str) -> None:
        index = self._page_indices.get(mode_id)
        if index is None:
            return
        self._stack.setCurrentIndex(index)
        self._config.set(_CFG_MODE, mode_id)
        logger.debug("Switched to mode: %s", mode_id)

    def _on_badge_clicked(self, device_id: str) -> None:
        # Clicking a disconnected badge jumps the user to Equipment to fix it.
        state = self._status.device_state(device_id)
        if state == "disconnected":
            self._sidebar.select("equipment")

    # ------------------------------------------------------------------
    # Public façade for future page wiring
    # ------------------------------------------------------------------

    @property
    def status(self) -> TopStatusBar:
        return self._status

    @property
    def sidebar(self) -> Sidebar:
        return self._sidebar

    def page(self, mode_id: str) -> QWidget | None:
        return self._pages.get(mode_id)

    def replace_page(self, mode_id: str, widget: QWidget) -> None:
        """Swap out a page (e.g. when R2-R5 land their real implementations).

        Keeps the sidebar action and stack index stable so user-visible state
        (current tab, geometry) survives the swap.
        """
        old = self._pages.get(mode_id)
        if old is None:
            return
        index = self._page_indices[mode_id]
        self._stack.removeWidget(old)
        self._stack.insertWidget(index, widget)
        self._pages[mode_id] = widget
        old.deleteLater()

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
        self._config.set(_CFG_STATE,    base64.b64encode(bytes(self.saveState())).decode())

    def _reset_layout(self) -> None:
        self._config.set(_CFG_GEOMETRY, None)
        self._config.set(_CFG_STATE, None)
        self.statusBar().showMessage("Window layout will reset on next launch.", 4000)

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        self.statusBar().showMessage(
            f"SeerControl v{self.APP_VERSION} — Seestar S30 Pro controller", 4000,
        )

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_stellarium_worker()
        page = self._pages.get("imaging")
        if isinstance(page, ImagingPage):
            page.shutdown()
        self._save_state()
        logger.info("Shell closed")
        super().closeEvent(event)
