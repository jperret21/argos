"""Manual mount control dialog — native scope_speed_move API.

Uses the Seestar's native JSON-RPC TCP API (port 4700) rather than
ASCOM Alpaca, because:
  - MoveAxis  → error 1032 (not implemented)
  - SlewToAltAzAsync → error 1024 (not implemented)
  - SlewToCoordinatesAsync → GOTO only, not suitable for jogging
  - PulseGuide → guide-rate only (~arcsec/s), invisible to the eye

Native command ``scope_speed_move``:
  { "method": "scope_speed_move",
    "params": { "speed": <int>, "angle": <int>, "dur_sec": <int> } }

  angle: compass degrees — 0=North, 90=East, 180=South, 270=West
  speed: 500–8000 (empirical)
  dur_sec: mount moves for this many seconds then auto-stops

Stop command:  { "method": "iscope_stop_view", "params": {} }

Behaviour:
  - Button pressed   → send scope_speed_move(dur_sec=DUR)
  - Timer fires every TICK_MS (< DUR*1000) → resend to extend movement
  - Button released  → send iscope_stop_view immediately
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.seestar.native_client import (
    ANGLE_EAST,
    ANGLE_NORTH,
    ANGLE_SOUTH,
    ANGLE_WEST,
    SeestarNativeClient,
    SeestarNativeError,
)
from seercontrol.ui import theme

logger = logging.getLogger(__name__)

# Each scope_speed_move command moves the mount for DUR_SEC seconds.
# TICK_MS is the interval at which we resend (must be < DUR_SEC * 1000
# so the scope never stops between ticks).
DUR_SEC  = 2
TICK_MS  = 1500

# Speed levels (scope_speed_move "speed" parameter).
# seestar_alp documents speed=4000 as the default for a normal move.
# Do NOT exceed 10000 until we know the motor limits — the firmware
# likely clamps values internally but this is not confirmed.
SPEEDS: dict[str, int] = {
    "Slow":   1000,
    "Normal": 4000,
    "Fast":   8000,
}


class _JogButton(QPushButton):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setFixedSize(64, 64)
        f = QFont()
        f.setPointSize(18)
        self.setFont(f)
        self.setAutoRepeat(False)


class ManualControlDialog(QDialog):
    """Floating dialog for manual mount jogging via native scope_speed_move.

    Signals:
        log_message: (level, message) forwarded to the session log.
    """

    log_message = pyqtSignal(str, str)

    def __init__(
        self,
        native: SeestarNativeClient,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._native = native
        self._speed: int = list(SPEEDS.values())[0]
        self._angle: int | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._setup_window()
        self._build_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("Manual Control")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedSize(280, 340)
        self.setModal(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        lbl = QLabel("Speed")
        lbl.setStyleSheet(f"color:{theme.TEXT_MUTED};font-size:10px;letter-spacing:1px;")
        self._speed_combo = QComboBox()
        for name in SPEEDS:
            self._speed_combo.addItem(name)
        self._speed_combo.currentTextChanged.connect(
            lambda t: setattr(self, "_speed", SPEEDS.get(t, 500))
        )
        root.addWidget(lbl)
        root.addWidget(self._speed_combo)

        hint = QLabel("Hold to move · Release to stop")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color:{theme.TEXT_MUTED};font-size:10px;")
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

        buttons = [
            (0, 1, "↑", "North",  ANGLE_NORTH),
            (2, 1, "↓", "South",  ANGLE_SOUTH),
            (1, 0, "←", "West",   ANGLE_WEST),
            (1, 2, "→", "East",   ANGLE_EAST),
        ]
        for row, col, icon, tip, angle in buttons:
            btn = _JogButton(icon)
            btn.setToolTip(tip)
            btn.pressed.connect(lambda a=angle: self._start(a))
            btn.released.connect(self._stop)
            grid.addWidget(btn, row, col)

        stop_btn = _JogButton("■")
        stop_btn.setToolTip("Stop")
        stop_btn.setStyleSheet(f"color:{theme.DANGER};")
        stop_btn.clicked.connect(self._stop)
        grid.addWidget(stop_btn, 1, 1)

        root.addLayout(grid)

        kb = QLabel("Arrow keys work when this window is focused")
        kb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kb.setWordWrap(True)
        kb.setStyleSheet(f"color:{theme.TEXT_MUTED};font-size:10px;")
        root.addWidget(kb)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def _start(self, angle: int) -> None:
        self._angle = angle
        self._send_move()
        self._timer.start()

    def _stop(self) -> None:
        self._timer.stop()
        self._angle = None
        logger.debug("_stop called — native.is_connected=%s socket=%s",
                     self._native.is_connected,
                     "ok" if self._native._socket else "NONE")
        try:
            self._native.stop()
        except SeestarNativeError as exc:
            logger.warning("Stop failed: %s (native connected=%s)",
                           exc, self._native.is_connected)
            self._log("WARN", f"Stop failed: {exc}")

    def _tick(self) -> None:
        if self._angle is None:
            self._timer.stop()
        else:
            self._send_move()

    def _send_move(self) -> None:
        if self._angle is None:
            return
        logger.debug("_send_move angle=%d speed=%d — native.is_connected=%s socket=%s",
                     self._angle, self._speed,
                     self._native.is_connected,
                     "ok" if self._native._socket else "NONE")
        try:
            self._native.move(self._angle, self._speed, DUR_SEC)
        except SeestarNativeError as exc:
            self._timer.stop()
            self._angle = None
            logger.error("Move failed: %s (native connected=%s)",
                         exc, self._native.is_connected)
            self._log("ERROR", f"Move failed: {exc}")

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if event.isAutoRepeat():
            return
        mapping = {
            Qt.Key.Key_Up:    ANGLE_NORTH,
            Qt.Key.Key_Down:  ANGLE_SOUTH,
            Qt.Key.Key_Left:  ANGLE_WEST,
            Qt.Key.Key_Right: ANGLE_EAST,
        }
        angle = mapping.get(event.key())
        if angle is not None:
            self._start(angle)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.isAutoRepeat():
            return
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                            Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._stop()
        else:
            super().keyReleaseEvent(event)

    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._stop()
        super().closeEvent(event)

    def _log(self, level: str, message: str) -> None:
        logger.debug("[%s] %s", level, message)
        self.log_message.emit(level, message)
