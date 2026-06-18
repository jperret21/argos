"""Manual mount control dialog — Alpaca MoveAxis jogging.

Uses ASCOM Alpaca MoveAxis (port 32323) which is confirmed working on
Seestar S30 Pro firmware 7.18+.

Axis mapping (Alt-Az mount):
  Axis 0 (Primary)   = Azimuth   → East/West
  Axis 1 (Secondary) = Altitude  → North/South

The mount keeps moving at the commanded rate until Rate=0 is sent.
Button pressed → MoveAxis(rate), button released → MoveAxis(0).
No periodic resend needed (unlike native scope_speed_move).
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
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

from argos.core.alpaca.client import AlpacaError
from argos.core.alpaca.telescope import Telescope
from argos.ui import theme

logger = logging.getLogger(__name__)

# Jog speed levels in deg/s
SPEEDS: dict[str, float] = {
    "Slow":   0.5,
    "Normal": 2.0,
    "Fast":   5.0,
}

# Axis/rate for each direction
# axis 0 = Az (E/W), axis 1 = Alt (N/S)
# Positive rate on axis 1 → altitude increases → North
# Positive rate on axis 0 → azimuth increases → East
_DIRECTIONS: dict[str, tuple[int, float]] = {
    "North": (1,  1.0),
    "South": (1, -1.0),
    "East":  (0,  1.0),
    "West":  (0, -1.0),
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
    """Floating dialog for manual mount jogging via Alpaca MoveAxis.

    Signals:
        log_message: (level, message) forwarded to the session log.
    """

    log_message = pyqtSignal(str, str)

    def __init__(
        self,
        telescope: Telescope,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._telescope = telescope
        self._speed: float = list(SPEEDS.values())[1]
        self._active_axis: int | None = None

        self._setup_window()
        self._build_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("Manual Control")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedSize(280, 320)
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
        self._speed_combo.setCurrentIndex(1)  # Normal default
        self._speed_combo.currentTextChanged.connect(
            lambda t: setattr(self, "_speed", SPEEDS.get(t, 2.0))
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
            (0, 1, "↑", "North"),
            (2, 1, "↓", "South"),
            (1, 0, "←", "West"),
            (1, 2, "→", "East"),
        ]
        for row, col, icon, direction in buttons:
            btn = _JogButton(icon)
            btn.setToolTip(direction)
            btn.pressed.connect(lambda d=direction: self._start(d))
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

    def _start(self, direction: str) -> None:
        axis, sign = _DIRECTIONS[direction]
        rate = sign * self._speed
        self._active_axis = axis
        logger.info("ManualControl: %s  axis=%d rate=%.2f", direction, axis, rate)
        try:
            self._telescope.move_axis(axis, rate)
        except AlpacaError as exc:
            self._active_axis = None
            logger.error("MoveAxis failed: %s", exc)
            self._log("ERROR", f"Move failed: {exc}")

    def _stop(self) -> None:
        axis = self._active_axis
        self._active_axis = None
        if axis is not None:
            try:
                self._telescope.stop_axis(axis)
                logger.info("ManualControl: stopped axis %d", axis)
            except AlpacaError as exc:
                logger.warning("Stop axis %d failed: %s", axis, exc)
                self._log("WARN", f"Stop failed: {exc}")

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if event.isAutoRepeat():
            return
        mapping = {
            Qt.Key.Key_Up:    "North",
            Qt.Key.Key_Down:  "South",
            Qt.Key.Key_Left:  "West",
            Qt.Key.Key_Right: "East",
        }
        direction = mapping.get(event.key())
        if direction is not None:
            self._start(direction)
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
