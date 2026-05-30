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

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.config import Config
from seercontrol.ui import theme
from seercontrol.ui.pages.equipment_page import EquipmentPage
from seercontrol.ui.pages.imaging_page import ImagingPage
from seercontrol.ui.pages.settings_page import SettingsPage
from seercontrol.ui.pages.target_page import TargetPage
from seercontrol.ui.sidebar import Sidebar
from seercontrol.ui.statusbar import TopStatusBar

# Pages that need the application Config receive it via constructor; the rest
# stay parameter-less so swapping them in/out across sprints stays cheap.
_PAGES_NEEDING_CONFIG = {"imaging"}

logger = logging.getLogger(__name__)

_CFG_GEOMETRY = "ui.shell.geometry"
_CFG_STATE    = "ui.shell.state"
_CFG_MODE     = "ui.shell.mode"


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
            "equipment": EquipmentPage(),
            "target":    TargetPage(),
            "imaging":   ImagingPage(self._config),
            "settings":  SettingsPage(),
        }
        self._page_indices: dict[str, int] = {
            mode_id: self._stack.addWidget(page)
            for mode_id, page in self._pages.items()
        }
        self._wire_imaging_page()

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
        """Connect ImagingPage upward signals to the global status bar."""
        page = self._pages.get("imaging")
        if not isinstance(page, ImagingPage):
            return
        page.device_state_changed.connect(self._status.set_device_state)
        page.tracking_changed.connect(self._status.set_tracking)
        page.action_changed.connect(self._status.set_action)

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
        page = self._pages.get("imaging")
        if isinstance(page, ImagingPage):
            page.shutdown()
        self._save_state()
        logger.info("Shell closed")
        super().closeEvent(event)
