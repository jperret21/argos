"""Permanent top status strip — devices, tracking, last action.

Sits between the toolbar and the mode workspace. Always visible across all
modes so the user never wonders "am I still connected?" or "is the mount
tracking?". Updated via slots called by the Shell from device signals.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from seercontrol.ui import theme

logger = logging.getLogger(__name__)


# (device_id, display label). Order is what the user sees, left to right.
DEVICES: tuple[tuple[str, str], ...] = (
    ("mount",       "Mount"),
    ("camera",      "Camera"),
    ("filterwheel", "Filter Wheel"),
    ("focuser",     "Focuser"),
)


class TopStatusBar(QWidget):
    """One-line summary of the observatory state.

    Layout (left → right):
        [● Mount]  [● Camera]  [● Filter Wheel]  [● Focuser]    Tracking ON   Last: …
    """

    badge_clicked = pyqtSignal(str)   # device id ('mount', 'camera', …)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            f"background:{theme.BG}; border-bottom:1px solid {theme.BORDER};"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        self._badges: dict[str, QLabel] = {}
        for device_id, label in DEVICES:
            badge = _Badge(device_id, label)
            badge.clicked.connect(lambda _e, d=device_id: self.badge_clicked.emit(d))
            self._badges[device_id] = badge
            layout.addWidget(badge)
            layout.addSpacing(8)

        layout.addStretch()

        self._tracking_lbl = QLabel("Tracking —")
        self._tracking_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
        )
        layout.addWidget(self._tracking_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{theme.BORDER};")
        layout.addSpacing(12)
        layout.addWidget(sep)
        layout.addSpacing(12)

        self._action_lbl = QLabel("Idle")
        self._action_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
            f" font-family:{theme.FONT_MONO};"
        )
        layout.addWidget(self._action_lbl)

    # ------------------------------------------------------------------
    # Slot API
    # ------------------------------------------------------------------

    def set_device_state(self, device_id: str, state: str, info: str = "") -> None:
        """Update a single device badge.

        Args:
            device_id: One of ``"mount"``, ``"camera"``, ``"filterwheel"``,
                       ``"focuser"``.
            state:     ``"disconnected"`` | ``"connected"`` | ``"busy"``
                       | ``"error"``.
            info:      Optional suffix, e.g. ``"slewing"`` or ``"Pos 2"``.
        """
        badge = self._badges.get(device_id)
        if badge is None:
            return
        badge.set_state(state, info)

    def set_tracking(self, tracking: bool | None) -> None:
        if tracking is None:
            self._tracking_lbl.setText("Tracking —")
            color = theme.FG_MUTED
        elif tracking:
            self._tracking_lbl.setText("Tracking ON")
            color = theme.SUCCESS
        else:
            self._tracking_lbl.setText("Tracking OFF")
            color = theme.WARNING
        self._tracking_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; background:transparent;"
        )

    def set_action(self, text: str) -> None:
        self._action_lbl.setText(text or "Idle")

    def device_state(self, device_id: str) -> str:
        badge = self._badges.get(device_id)
        return badge.state() if badge else "disconnected"


class _Badge(QLabel):
    """Click-aware device badge — color reflects state."""

    clicked = pyqtSignal(object)

    def __init__(self, device_id: str, label: str) -> None:
        super().__init__()
        self._device_id = device_id
        self._label = label
        self._state = "disconnected"
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMargin(0)
        self.set_state("disconnected")

    def state(self) -> str:
        return self._state

    def set_state(self, state: str, info: str = "") -> None:
        self._state = state
        glyph = {
            "disconnected": "○",
            "connected":    "●",
            "busy":         "●",
            "error":        "✗",
        }.get(state, "○")
        color = {
            "disconnected": theme.FG_MUTED,
            "connected":    theme.SUCCESS,
            "busy":         theme.WARNING,
            "error":        theme.DANGER,
        }.get(state, theme.FG_MUTED)

        text = f"{glyph}  {self._label}"
        if info:
            text += f" · {info}"
        self.setText(text)
        self.setStyleSheet(
            f"color:{color}; font-size:11px; padding:4px 8px;"
            f" background:transparent;"
        )

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(event)
        super().mousePressEvent(event)
