"""Manual mount control dialog — Alpaca MoveAxis jogging.

Uses ASCOM Alpaca MoveAxis (port 32323) which is confirmed working on
Seestar S30 Pro firmware 7.18+.

Axis mapping (Alt-Az mount):
  Axis 0 (Primary)   = Azimuth   → East/West
  Axis 1 (Secondary) = Altitude  → North/South

The mount keeps moving at the commanded rate until Rate=0 is sent.
Button pressed → MoveAxis(rate), button released → MoveAxis(0).
No periodic resend needed (unlike native scope_speed_move).

Each axis is tracked on its own (a diagonal jog moves both), and a released
key or button stops its own axis. The ■ button stops both axes; closing,
hiding or leaving the window stops every axis still moving, since a key
released in another window never reaches this one.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
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
    "Slow": 0.5,
    "Normal": 2.0,
    "Fast": 5.0,
}

# Axis/rate for each direction
# axis 0 = Az (E/W), axis 1 = Alt (N/S)
# Positive rate on axis 1 → altitude increases → North
# Positive rate on axis 0 → azimuth increases → East
_DIRECTIONS: dict[str, tuple[int, float]] = {
    "North": (1, 1.0),
    "South": (1, -1.0),
    "East": (0, 1.0),
    "West": (0, -1.0),
}

_KEY_DIRECTIONS: dict[Qt.Key, str] = {
    Qt.Key.Key_Up: "North",
    Qt.Key.Key_Down: "South",
    Qt.Key.Key_Left: "West",
    Qt.Key.Key_Right: "East",
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
        self._active_axes: set[int] = set()
        # Failed StopAxis calls per axis since it was last started or stopped.
        self._stop_failures: dict[int, int] = {}

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
            btn.released.connect(lambda d=direction: self._stop_axis(_DIRECTIONS[d][0]))
            grid.addWidget(btn, row, col)

        stop_btn = _JogButton("■")
        stop_btn.setToolTip("Stop both axes")
        stop_btn.setStyleSheet(f"color:{theme.DANGER};")
        stop_btn.clicked.connect(self._stop_all)
        grid.addWidget(stop_btn, 1, 1)

        root.addLayout(grid)

        kb = QLabel("Arrow keys work when this window is focused")
        kb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kb.setWordWrap(True)
        kb.setStyleSheet(f"color:{theme.TEXT_MUTED};font-size:10px;")
        root.addWidget(kb)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_telescope(self, telescope: Telescope) -> None:
        """Drive *telescope* from now on (a reconnect creates a new handle)."""
        self._telescope = telescope

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def _start(self, direction: str) -> None:
        axis, sign = _DIRECTIONS[direction]
        rate = sign * self._speed
        # Marked before the call and kept on failure: a MoveAxis that raised
        # may still have reached the mount, and a stop is harmless.
        self._active_axes.add(axis)
        self._stop_failures.pop(axis, None)
        logger.info("ManualControl: %s  axis=%d rate=%.2f", direction, axis, rate)
        try:
            self._telescope.move_axis(axis, rate)
        except AlpacaError as exc:
            logger.error("MoveAxis failed: %s", exc)
            self._log("ERROR", f"Move failed: {exc}")

    #: StopAxis attempts per axis before the dialog stops retrying.
    _STOP_ATTEMPTS = 2

    def _stop_axis(self, axis: int) -> None:
        """Stop *axis* if this dialog moved it (key or button released).

        A failed stop keeps the axis marked: it may still be moving, so the
        next close, hide, focus loss or ■ tries again, once. Each attempt is a
        blocking call, so a mount that stays unreachable is not retried on
        every event.
        """
        if axis not in self._active_axes:
            return
        try:
            self._telescope.stop_axis(axis)
        except AlpacaError as exc:
            failures = self._stop_failures.get(axis, 0) + 1
            logger.warning("Stop axis %d failed (%d): %s", axis, failures, exc)
            if failures < self._STOP_ATTEMPTS:
                self._stop_failures[axis] = failures
                self._log(
                    "WARN",
                    f"Stop failed: {exc} — tried again when this window closes or loses focus.",
                )
            else:
                self._active_axes.discard(axis)
                self._stop_failures.pop(axis, None)
                self._log(
                    "ERROR",
                    f"Stop failed again: {exc} — the mount may still be moving; "
                    "use Abort on the Mount card.",
                )
            return
        self._active_axes.discard(axis)
        self._stop_failures.pop(axis, None)
        logger.info("ManualControl: stopped axis %d", axis)

    def _stop_active(self) -> None:
        """Stop every axis this dialog still moves (close, hide, focus lost)."""
        for axis in sorted(self._active_axes):
            self._stop_axis(axis)

    def _stop_all(self) -> None:
        """The ■ button: stop both axes, whatever the dialog believes."""
        self._active_axes.update((0, 1))
        self._stop_active()

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if event.isAutoRepeat():
            return
        direction = _KEY_DIRECTIONS.get(event.key())
        if direction is not None:
            self._start(direction)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.isAutoRepeat():
            return
        direction = _KEY_DIRECTIONS.get(event.key())
        if direction is not None:
            self._stop_axis(_DIRECTIONS[direction][0])
        else:
            super().keyReleaseEvent(event)

    # ------------------------------------------------------------------

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate:
            # A key held while the window loses focus is released elsewhere.
            self._stop_active()
        return super().event(event)

    def hideEvent(self, event) -> None:
        self._stop_active()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._stop_active()
        super().closeEvent(event)

    def _log(self, level: str, message: str) -> None:
        logger.debug("[%s] %s", level, message)
        self.log_message.emit(level, message)
