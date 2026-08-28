"""Connection mode — connect the Seestar devices and the Stellarium server.

The user comes here once at the start of a session. The page emits intents
(``connect_requested``, ``disconnect_requested``, ``discover_requested``) and
the Shell routes them to the device session living on the Acquisition page.
State updates flow back via ``set_device_state``. The Stellarium telescope-
control server is started/stopped from the embedded ``StellariumCard``.

The Shell uses its discovery/connect/disconnect signals, the
``set_device_state`` and ``set_discovered_address`` slots, and the
``stellarium_card`` property.
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
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from argos.core.config import Config
from argos.core.hardware import active, catalog
from argos.ui import design, theme
from argos.ui.panels.stellarium_card import StellariumCard

logger = logging.getLogger(__name__)


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
    telescope_profile_requested = pyqtSignal(str)

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
        intro = QLabel(
            "Enter the Seestar Alpaca IP address, connect the equipment, then move on to framing "
            "and observing."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
        )
        body.addWidget(intro)
        body.addWidget(self._build_start_card())

        self._advanced_toggle = QPushButton("Show connection and device details")
        self._advanced_toggle.setProperty("class", "secondary")
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        body.addWidget(self._advanced_toggle)

        self._advanced = QWidget()
        advanced = QVBoxLayout(self._advanced)
        advanced.setContentsMargins(0, design.SPACING_SM, 0, 0)
        advanced.setSpacing(design.SPACING_MD)
        advanced.addWidget(design.SectionLabel("Individual devices"))
        advanced.addLayout(self._build_devices_grid())
        advanced.addLayout(self._build_bulk_row())
        advanced.addWidget(design.SectionLabel("Planetarium"))
        host = str(self._config.get("stellarium.host", "127.0.0.1"))
        port = int(self._config.get("stellarium.port", 10001))
        online_target_lookup = bool(self._config.get("stellarium.online_target_lookup", False))
        self._stellarium_card = StellariumCard(
            host=host,
            tcp_port=port,
            online_target_lookup=online_target_lookup,
        )
        advanced.addWidget(self._stellarium_card)
        self._advanced.hide()
        body.addWidget(self._advanced)

        body.addStretch()

    def _build_start_card(self) -> "design.Card":
        """Build the normal observer-facing equipment entry point."""
        card = design.Card("Telescope & equipment")
        layout = design.card_layout(card)

        # This is deliberately part of Connection, not hidden under Settings:
        # the model sets plate scale, sensor geometry and FITS identity before
        # the first device call. A wrong profile is a science error, not merely
        # a cosmetic preference.
        scope_row = QHBoxLayout()
        scope_row.setSpacing(design.SPACING_MD)
        scope_row.addWidget(design.MutedLabel("Telescope"))
        self._telescope_combo = QComboBox()
        for key in catalog.keys():
            profile = catalog.PROFILES[key]
            suffix = " (unvalidated)" if not profile.validated else ""
            self._telescope_combo.addItem(f"{profile.name}{suffix}", key)
        current = self._telescope_combo.findData(active.profile().key)
        self._telescope_combo.setCurrentIndex(max(0, current))
        self._telescope_combo.currentIndexChanged.connect(self._on_telescope_changed)
        scope_row.addWidget(self._telescope_combo, 1)
        layout.addLayout(scope_row)
        self._telescope_specs = design.MutedLabel("")
        self._telescope_specs.setWordWrap(True)
        layout.addWidget(self._telescope_specs)
        self._telescope_warning = design.MutedLabel("")
        self._telescope_warning.setWordWrap(True)
        self._telescope_warning.setStyleSheet(f"color:{theme.WARNING};")
        layout.addWidget(self._telescope_warning)
        self._refresh_telescope_summary()

        layout.addWidget(design.horizontal_divider())
        layout.addLayout(self._build_endpoint_row())
        layout.addWidget(
            design.MutedLabel(
                "Use Discover on a new network; Argos remembers the last successful address."
            )
        )
        layout.addWidget(design.horizontal_divider())
        self._summary_labels: dict[str, QLabel] = {}
        for device_id, label, _hint in _DEVICES:
            status = QLabel()
            status.setStyleSheet(
                f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_BODY}px; "
                "background:transparent;"
            )
            self._summary_labels[device_id] = status
            layout.addWidget(status)
        self._start_connect_btn = design.SuccessButton("Connect equipment")
        self._start_connect_btn.setToolTip("Connect telescope, camera, filter wheel and focuser")
        self._start_connect_btn.clicked.connect(self._on_connect_all)
        layout.addWidget(self._start_connect_btn)
        self._refresh_summary()
        return card

    def _build_endpoint_row(self) -> QHBoxLayout:
        """The only network setting an observer needs: Alpaca IP + port."""
        row = QHBoxLayout()
        row.setSpacing(design.SPACING_MD)
        row.addWidget(design.MutedLabel("IP address"))
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("192.168.x.x")
        self._host_edit.setToolTip("IPv4 address of the Seestar on the current network")
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
        return row

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
        self._refresh_summary()

    def set_discovered_address(self, host: str, port: int) -> None:
        """Fill in the form when a discovery worker returns an address."""
        self._host_edit.setText(host)
        self._port_spin.setValue(port)

    def apply_telescope_profile(self, key: str) -> bool:
        """Make *key* the one active instrument, if equipment is idle.

        Both Connection and Settings request a change through the Shell.  This
        is the only mutation path so their controls cannot silently diverge.
        """
        profile = catalog.get(key)
        if profile is None:
            return False
        if key != active.profile().key and any(
            card._state in {"connected", "busy"} for card in self._cards.values()
        ):
            self._set_telescope_combo(active.profile().key)
            logger.warning("Refused telescope profile change while equipment is connected")
            return False

        self._set_telescope_combo(key)
        self._config.set(active.CFG_PROFILE, key)
        overrides = self._config.get(active.CFG_OVERRIDES, {})
        active.set_profile(active.apply_overrides(profile, overrides))
        self._refresh_telescope_summary()
        return True

    def _toggle_advanced(self) -> None:
        visible = not self._advanced.isVisible()
        self._advanced.setVisible(visible)
        self._advanced_toggle.setText(
            "Hide connection and device details"
            if visible
            else "Show connection and device details"
        )

    def _refresh_summary(self) -> None:
        """Mirror detailed device state into the compact nightly checklist."""
        states = {device_id: card._state for device_id, card in self._cards.items()}
        for device_id, label, _hint in _DEVICES:
            status = self._summary_labels.get(device_id)
            if status is None:
                continue
            state = states.get(device_id, "disconnected")
            connected = state in {"connected", "busy"}
            icon = "●" if connected else "○"
            text = "Ready" if state == "connected" else state.capitalize()
            color = {
                "connected": theme.SUCCESS,
                "busy": theme.WARNING,
                "error": theme.DANGER,
            }.get(state, theme.FG_MUTED)
            status.setText(f"{icon}  {label} — {text}")
            status.setStyleSheet(
                f"color:{color}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
            )
        all_ready = len(states) == len(_DEVICES) and all(
            state == "connected" for state in states.values()
        )
        if hasattr(self, "_start_connect_btn"):
            self._start_connect_btn.setText("Equipment ready" if all_ready else "Connect equipment")
            self._start_connect_btn.setEnabled(not all_ready)
        if hasattr(self, "_telescope_combo"):
            any_connected = any(state in {"connected", "busy"} for state in states.values())
            self._telescope_combo.setEnabled(not any_connected)
            self._telescope_combo.setToolTip(
                "Disconnect equipment before changing telescope model. The model controls "
                "plate scale, sensor geometry and FITS metadata."
                if any_connected
                else "Select the physical telescope before connecting equipment."
            )

    def _on_telescope_changed(self) -> None:
        """Ask the Shell to apply the shared physical-instrument selection."""
        if self._loading:
            return
        key = self._telescope_combo.currentData()
        if not key:
            return
        self.telescope_profile_requested.emit(str(key))

    def _set_telescope_combo(self, key: str) -> None:
        """Reflect the active profile without feeding the shared-change signal."""
        index = self._telescope_combo.findData(key)
        if index < 0:
            return
        self._telescope_combo.blockSignals(True)
        self._telescope_combo.setCurrentIndex(index)
        self._telescope_combo.blockSignals(False)

    def _refresh_telescope_summary(self) -> None:
        """Show the scientific consequences of the selected instrument."""
        profile = active.profile()
        width, height = profile.fov_deg
        self._telescope_specs.setText(
            f"{profile.aperture_mm:g} mm  ·  f/{profile.focal_ratio:.1f}  ·  "
            f"{profile.sensor}  ·  {profile.arcsec_per_full_px:.2f}″/px  ·  "
            f"{width:.2f}° × {height:.2f}°"
        )
        if profile.validated:
            self._telescope_warning.hide()
        else:
            self._telescope_warning.setText(
                "Unvalidated profile — do not use it for scientific photometry: "
                + " · ".join(profile.caveats)
            )
            self._telescope_warning.show()

    # ------------------------------------------------------------------
    # Config + internals
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        self._loading = True
        self._host_edit.setText(self._config.alpaca_host or "")
        self._port_spin.setValue(self._config.alpaca_port or 32323)
        self._loading = False

    def _on_host_changed(self, text: str) -> None:
        if self._loading:
            return
        self._config.alpaca_host = text.strip()

    def _on_port_changed(self, value: int) -> None:
        if self._loading:
            return
        self._config.alpaca_port = value

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
