"""Permanent top status strip — devices, capture progress, tracking, last action.

Sits between the toolbar and the mode workspace. Always visible across all
modes so the user never wonders "am I still connected?" or "is the mount
tracking?" — and, during a run, never loses sight of the sequence. Updated via
slots called by the Shell from device/sequence signals.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from argos.ui import design, theme

logger = logging.getLogger(__name__)


# (device_id, display label). Order is what the user sees, left to right.
DEVICES: tuple[tuple[str, str], ...] = (
    ("mount", "Mount"),
    ("camera", "Camera"),
    ("filterwheel", "Filter Wheel"),
    ("focuser", "Focuser"),
)


class TopStatusBar(QWidget):
    """One-line summary of the observatory state.

    Layout (left → right):
        [● Mount] [● Camera] [● Filter Wheel] [● Focuser]   ●REC M42 · 34/120 · ETA 12m · HFD 2.1   Tracking ON   Last: …

    The capture strip (middle) is hidden while idle; during a sequence it stays
    visible on every screen and clicking it jumps to the Capture mode. A LIVE
    chip appears while the user preview loop owns the camera.
    """

    badge_clicked = pyqtSignal(str)  # device id ('mount', 'camera', …)
    capture_clicked = pyqtSignal()  # click on the capture strip → Capture mode

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(f"background:{theme.BG}; border-bottom:1px solid {theme.BORDER};")
        # Capture-strip state (rendered together by _render_capture).
        self._seq_object = ""
        self._seq_done = 0
        self._seq_total = 0
        self._seq_eta_s = 0.0
        self._seq_running = False
        self._live = False
        self._hfd: float | None = None
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

        # Capture strip — sequence progress + LIVE chip, hidden while idle.
        self._capture_lbl = _ClickLabel()
        self._capture_lbl.setToolTip("Capture in progress — click to open the Capture screen")
        self._capture_lbl.clicked.connect(self.capture_clicked)
        self._capture_lbl.hide()
        layout.addWidget(self._capture_lbl)

        layout.addStretch()

        # Network dots — quiet reachability summary (fed by NetworkMonitor).
        # ● up / ○ down; muted grey until the first check lands.
        self._network_lbl = QLabel("")
        self._network_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent;"
        )
        self._network_lbl.setToolTip(
            "Seestar: the configured address answers on the Alpaca port.\n"
            "Net: internet is reachable (AAVSO catalogs available)."
        )
        layout.addWidget(self._network_lbl)
        layout.addSpacing(12)

        # Mount geometry — "Alt-Az" or "EQ", hidden until the mount says.
        # Alt-az means the field rotates during a session; EQ means it doesn't.
        self._mode_lbl = QLabel("")
        self._mode_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent;"
        )
        self._mode_lbl.setToolTip(
            "Mount geometry reported by the firmware.\n"
            "Alt-Az: the field rotates during a session (apertures drift on long runs).\n"
            "EQ (wedge): no field rotation."
        )
        self._mode_lbl.hide()
        layout.addWidget(self._mode_lbl)
        layout.addSpacing(12)

        self._tracking_lbl = QLabel("Tracking —")
        self._tracking_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent;"
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
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_SMALL}px;"
            f" background:transparent; font-family:{theme.FONT_MONO};"
        )
        layout.addWidget(self._action_lbl)

    # ------------------------------------------------------------------
    # Slot API — devices
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

    def set_network(self, seestar_ok: object, internet_ok: bool) -> None:
        """Update the network dots.

        Args:
            seestar_ok: True/False reachability, or None when no host is
                        configured yet (dot stays muted).
            internet_ok: Internet reachability.
        """

        def dot(ok: object) -> str:
            if ok:
                return f'<span style="color:{theme.SUCCESS};">●</span>'
            return "○"  # down/unknown — stays in the label's muted grey

        self._network_lbl.setText(
            f"Seestar {dot(seestar_ok)}&nbsp;&nbsp;&nbsp;Net {dot(internet_ok)}"
        )

    def set_mount_mode(self, mode: object) -> None:
        """Show the mount geometry ("Alt-Az" / "EQ" / "EQ (GEM)"); hide on None."""
        if mode:
            self._mode_lbl.setText(str(mode))
            self._mode_lbl.show()
        else:
            self._mode_lbl.clear()
            self._mode_lbl.hide()

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
            f"color:{color}; font-size:{design.FONT_SIZE_SMALL}px; background:transparent;"
        )

    def set_action(self, text: str) -> None:
        self._action_lbl.setText(text or "Idle")

    def device_state(self, device_id: str) -> str:
        badge = self._badges.get(device_id)
        return badge.state() if badge else "disconnected"

    # ------------------------------------------------------------------
    # Slot API — capture strip
    # ------------------------------------------------------------------

    def set_sequence_running(self, running: bool) -> None:
        """Show/clear the sequence part of the capture strip."""
        self._seq_running = bool(running)
        if not running:
            self._seq_object = ""
            self._seq_done = self._seq_total = 0
            self._seq_eta_s = 0.0
        self._render_capture()

    def set_sequence_progress(
        self, object_name: str, done: int, total: int, eta_seconds: float
    ) -> None:
        self._seq_object = object_name
        self._seq_done = done
        self._seq_total = total
        self._seq_eta_s = eta_seconds
        self._render_capture()

    def set_live(self, live: bool) -> None:
        """LIVE chip — the user preview loop owns the camera."""
        self._live = bool(live)
        self._render_capture()

    def set_hfd(self, hfd: float | None) -> None:
        """Latest per-frame HFD — shown inside the strip during a run."""
        self._hfd = hfd
        if self._seq_running or self._live:
            self._render_capture()

    def _render_capture(self) -> None:
        if not (self._seq_running or self._live):
            self._capture_lbl.hide()
            return
        if self._seq_running:
            parts = ["●REC"]
            if self._seq_object:
                parts.append(self._seq_object)
            if self._seq_total:
                parts.append(f"{self._seq_done}/{self._seq_total}")
                m, s = divmod(max(0, int(self._seq_eta_s)), 60)
                parts.append(f"ETA {m}m{s:02d}s")
            if self._hfd is not None:
                parts.append(f"HFD {self._hfd:.1f}")
            color = theme.DANGER
        else:  # LIVE only
            parts = ["LIVE"]
            if self._hfd is not None:
                parts.append(f"HFD {self._hfd:.1f}")
            color = theme.SUCCESS
        self._capture_lbl.setText("  ·  ".join(parts))
        self._capture_lbl.setStyleSheet(
            f"color:{color}; font-size:{design.FONT_SIZE_SMALL}px; font-weight:600;"
            f" background:transparent; font-family:{theme.FONT_MONO}; padding:0 8px;"
        )
        self._capture_lbl.show()


class _ClickLabel(QLabel):
    """QLabel that emits ``clicked`` on left-button press."""

    clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _Badge(QLabel):
    """Click-aware device badge — shape + color reflect state (the shape
    distinction keeps busy/connected readable under red-light or CVD)."""

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
            "connected": "●",
            "busy": "◐",
            "error": "✗",
        }.get(state, "○")
        color = {
            "disconnected": theme.FG_MUTED,
            "connected": theme.SUCCESS,
            "busy": theme.WARNING,
            "error": theme.DANGER,
        }.get(state, theme.FG_MUTED)

        text = f"{glyph}  {self._label}"
        if info:
            text += f" · {info}"
        self.setText(text)
        self.setStyleSheet(
            f"color:{color}; font-size:{design.FONT_SIZE_SMALL}px; padding:4px 8px;"
            f" background:transparent;"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.clicked.emit(event)
        super().mousePressEvent(event)
