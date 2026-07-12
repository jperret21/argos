"""Connection mode — connect the Seestar devices and the Stellarium server.

The user comes here once at the start of a session. The page emits intents
(``connect_requested``, ``disconnect_requested``, ``discover_requested``) and
the Shell routes them to the device session living on the Acquisition page.
State updates flow back via ``set_device_state``. The Stellarium telescope-
control server is started/stopped from the embedded ``StellariumCard``.

Public interface (used by the Shell):
    Signals: discover_requested(), connect_requested(device, host, port),
             disconnect_requested(device), connect_all_requested(host, port),
             disconnect_all_requested()
    Slots:   set_device_state(device, state, info), set_discovered_address(host, port)
    Property: stellarium_card -> StellariumCard
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from argos.core.config import Config
from argos.ui import design, theme
from argos.ui.panels.stellarium_card import StellariumCard

logger = logging.getLogger(__name__)


# (profile_id, display label) — one per network situation. "field_ap" comes
# pre-filled with the Seestar's fixed AP-mode address; the other two remember
# whatever host the user last used on that network (docs/field_connectivity.md).
_PROFILES: tuple[tuple[str, str], ...] = (
    ("home", "Home network"),
    ("field_ap", "Field — Seestar AP"),
    ("hotspot", "Field — Phone hotspot"),
)

# (device_id, display label, hint) — one row per device. Order matches the
# global status bar so connection state reads left-to-right consistently.
_DEVICES: tuple[tuple[str, str, str], ...] = (
    ("mount", "Telescope", "Mount control via ASCOM Alpaca"),
    ("camera", "Camera", "Telephoto IMX585 sensor"),
    ("filterwheel", "Filter Wheel", "Dark / IR / LP slots"),
    ("focuser", "Focuser", "Telephoto focuser"),
)


class ConnectionPage(QWidget):
    """Connection setup page — devices + Stellarium server."""

    discover_requested = pyqtSignal()
    connect_requested = pyqtSignal(str, str, int)  # device_id, host, port
    disconnect_requested = pyqtSignal(str)  # device_id
    connect_all_requested = pyqtSignal(str, int)
    disconnect_all_requested = pyqtSignal()

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._cards: dict[str, _DeviceCard] = {}
        self._loading = True  # mute form→config sync until _load_config is done
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll, body = design.scroll_page()
        root.addWidget(scroll)

        body.addWidget(design.HeadingLabel("Connection"))
        body.addWidget(self._build_address_card())

        body.addWidget(design.SectionLabel("Devices"))
        body.addLayout(self._build_devices_grid())
        body.addLayout(self._build_bulk_row())

        body.addWidget(design.SectionLabel("Planetarium"))
        host = str(self._config.get("stellarium.host", "127.0.0.1"))
        port = int(self._config.get("stellarium.port", 10001))
        self._stellarium_card = StellariumCard(host=host, tcp_port=port)
        body.addWidget(self._stellarium_card)

        body.addStretch()

    def _build_address_card(self) -> "design.Card":
        card = design.Card("Address")
        layout = design.card_layout(card)

        row = QHBoxLayout()
        row.setSpacing(design.SPACING_MD)
        self._profile_combo = QComboBox()
        for profile_id, label in _PROFILES:
            self._profile_combo.addItem(label, profile_id)
        self._profile_combo.setToolTip("Network profile — each remembers its own Seestar address")
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        row.addWidget(self._profile_combo)
        row.addWidget(design.MutedLabel("Host"))
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("192.168.x.x")
        self._host_edit.textChanged.connect(self._on_host_changed)
        row.addWidget(self._host_edit, 1)
        row.addWidget(design.MutedLabel("Port"))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setMaximumWidth(96)
        self._port_spin.valueChanged.connect(self._on_port_changed)
        row.addWidget(self._port_spin)
        self._discover_btn = design.PrimaryButton("⚡  Discover")
        self._discover_btn.setToolTip("Send an Alpaca UDP discovery broadcast")
        self._discover_btn.clicked.connect(self.discover_requested)
        row.addWidget(self._discover_btn)
        layout.addLayout(row)
        return card

    def _build_devices_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(design.SPACING_MD)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for i, (device_id, label, hint) in enumerate(_DEVICES):
            card = _DeviceCard(device_id, label, hint)
            card.connect_clicked.connect(self._on_connect_one)
            card.disconnect_clicked.connect(self.disconnect_requested)
            self._cards[device_id] = card
            grid.addWidget(card, i // 2, i % 2)
        return grid

    def _build_bulk_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(design.SPACING_MD)
        self._connect_all_btn = design.SuccessButton("▶  Connect all")
        self._connect_all_btn.clicked.connect(self._on_connect_all)
        self._disconnect_all_btn = design.DangerButton("■  Disconnect all")
        self._disconnect_all_btn.clicked.connect(self.disconnect_all_requested)
        row.addWidget(self._connect_all_btn)
        row.addWidget(self._disconnect_all_btn)
        return row

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def stellarium_card(self) -> StellariumCard:
        """Expose the card so the Shell can wire its server signals."""
        return self._stellarium_card

    def set_device_state(self, device_id: str, state: str, info: str = "") -> None:
        card = self._cards.get(device_id)
        if card is not None:
            card.set_state(state, info)

    def set_discovered_address(self, host: str, port: int) -> None:
        """Fill in the form when a discovery worker returns an address."""
        self._host_edit.setText(host)
        self._port_spin.setValue(port)

    # ------------------------------------------------------------------
    # Config + internals
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        profile = str(self._config.get("alpaca.profile", "home"))
        index = next((i for i, (pid, _) in enumerate(_PROFILES) if pid == profile), 0)
        self._loading = True
        self._profile_combo.setCurrentIndex(index)
        self._host_edit.setText(self._config.alpaca_host or "")
        self._port_spin.setValue(self._config.alpaca_port or 32323)
        self._loading = False
        # Pre-profile configs have alpaca.host but an empty profile entry —
        # adopt the current address into the active profile once.
        self._save_into_profile()

    def _on_profile_changed(self, index: int) -> None:
        if self._loading:
            return
        profile_id = _PROFILES[index][0]
        self._config.set("alpaca.profile", profile_id)
        host = str(self._config.get(f"alpaca.profiles.{profile_id}.host", ""))
        port = int(self._config.get(f"alpaca.profiles.{profile_id}.port", 32323) or 32323)
        # Filling the form re-enters _on_host/port_changed, which mirrors the
        # profile's address into alpaca.host/port for the device wrappers.
        self._host_edit.setText(host)
        self._port_spin.setValue(port)

    def _save_into_profile(self) -> None:
        profile_id = _PROFILES[self._profile_combo.currentIndex()][0]
        self._config.set(f"alpaca.profiles.{profile_id}.host", self._config.alpaca_host)
        self._config.set(f"alpaca.profiles.{profile_id}.port", self._config.alpaca_port)

    def _on_host_changed(self, text: str) -> None:
        if self._loading:
            return
        self._config.alpaca_host = text.strip()
        self._save_into_profile()

    def _on_port_changed(self, value: int) -> None:
        if self._loading:
            return
        self._config.alpaca_port = value
        self._save_into_profile()

    def _on_connect_one(self, device_id: str) -> None:
        host = self._host_edit.text().strip()
        port = int(self._port_spin.value())
        if not host:
            return
        self.connect_requested.emit(device_id, host, port)

    def _on_connect_all(self) -> None:
        host = self._host_edit.text().strip()
        port = int(self._port_spin.value())
        if not host:
            return
        self.connect_all_requested.emit(host, port)


# --------------------------------------------------------------------------- #
# Device card (one per grid cell)                                              #
# --------------------------------------------------------------------------- #


class _DeviceCard(design.Card):
    """A single device tile: glyph + name + status text + Connect button."""

    connect_clicked = pyqtSignal(str)
    disconnect_clicked = pyqtSignal(str)

    def __init__(self, device_id: str, label: str, hint: str) -> None:
        super().__init__(label)
        self._device_id = device_id
        self._state = "disconnected"
        self._build_ui(hint)
        self.set_state("disconnected")

    def _build_ui(self, hint: str) -> None:
        outer = design.card_layout(self)

        row = QHBoxLayout()
        row.setSpacing(design.SPACING_MD)

        self._glyph_lbl = QLabel("○")
        self._glyph_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:20px; background:transparent;"
        )
        self._glyph_lbl.setFixedWidth(26)
        row.addWidget(self._glyph_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._status_lbl = QLabel("Disconnected")
        self._status_lbl.setStyleSheet(
            f"color:{theme.FG}; font-size:13px; font-weight:bold;" f" background:transparent;"
        )
        self._hint_lbl = QLabel(hint)
        self._hint_lbl.setWordWrap(True)
        self._hint_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
        )
        text_col.addWidget(self._status_lbl)
        text_col.addWidget(self._hint_lbl)
        row.addLayout(text_col, 1)
        outer.addLayout(row)

        self._connect_btn = design.PrimaryButton("↗  Connect")
        self._connect_btn.clicked.connect(self._on_button)
        outer.addWidget(self._connect_btn)

    def set_state(self, state: str, info: str = "") -> None:
        self._state = state
        glyph_color = {
            "disconnected": theme.FG_MUTED,
            "connected": theme.SUCCESS,
            "busy": theme.WARNING,
            "error": theme.DANGER,
        }.get(state, theme.FG_MUTED)
        glyph_char = {
            "disconnected": "○",
            "connected": "●",
            "busy": "●",
            "error": "✗",
        }.get(state, "○")
        self._glyph_lbl.setText(glyph_char)
        self._glyph_lbl.setStyleSheet(
            f"color:{glyph_color}; font-size:20px; background:transparent;"
        )

        if state == "connected":
            self._status_lbl.setText("Connected" + (f" — {info}" if info else ""))
            self._connect_btn.setText("✗  Disconnect")
            self._connect_btn.setProperty("class", "danger")
        elif state == "busy":
            self._status_lbl.setText(f"Busy — {info}" if info else "Busy")
            self._connect_btn.setText("✗  Disconnect")
            self._connect_btn.setProperty("class", "danger")
        elif state == "error":
            self._status_lbl.setText(f"Error — {info}" if info else "Error")
            self._connect_btn.setText("↗  Retry")
            self._connect_btn.setProperty("class", "primary")
        else:
            self._status_lbl.setText("Disconnected")
            self._connect_btn.setText("↗  Connect")
            self._connect_btn.setProperty("class", "primary")
        self._connect_btn.style().unpolish(self._connect_btn)
        self._connect_btn.style().polish(self._connect_btn)

    def _on_button(self) -> None:
        if self._state in ("connected", "busy"):
            self.disconnect_clicked.emit(self._device_id)
        else:
            self.connect_clicked.emit(self._device_id)
