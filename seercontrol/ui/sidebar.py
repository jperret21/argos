"""Left navigation sidebar — switches between the 3 modes.

Vertical toolbar pinned to the left of the Shell. Each entry is a fixed-width
icon + label; clicking it emits ``mode_changed(mode_id)`` which the Shell uses
to swap the central QStackedWidget page.

The sidebar exposes a ``pulse(mode_id)`` slot for guidance: when the user
finishes connecting their devices, the Shell pulses ``"acquisition"`` to hint
that the next step is to start imaging.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QToolBar, QWidget

from seercontrol.ui import theme

logger = logging.getLogger(__name__)


# (mode_id, glyph, label, tooltip). Glyphs are plain unicode — avoids shipping
# icon assets and keeps the file self-contained.
MODES: tuple[tuple[str, str, str, str], ...] = (
    ("connection", "🔌", "Connection", "Connect the Seestar devices and Stellarium"),
    ("acquisition", "📷", "Acquisition", "Live preview, focus, capture and sequencing"),
    ("configuration", "⚙", "Configuration", "Theme, language, paths, observer, credits"),
)


class Sidebar(QToolBar):
    """Left navigation toolbar with 3 mutually-exclusive mode buttons."""

    mode_changed = pyqtSignal(str)  # mode id ('connection', 'acquisition', ...)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Modes", parent)
        # objectName is required by QMainWindow.saveState() to persist toolbar layout.
        self.setObjectName("ModesSidebar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setOrientation(Qt.Orientation.Vertical)
        self.setIconSize(self.iconSize())
        self.setStyleSheet(self._stylesheet())
        self.setFixedWidth(72)

        self._actions: dict[str, QAction] = {}
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(600)
        self._pulse_timer.timeout.connect(self._toggle_pulse)
        self._pulse_target: str | None = None
        self._pulse_on = False

        group = QActionGroup(self)
        group.setExclusive(True)
        for mode_id, glyph, label, tooltip in MODES:
            action = QAction(f"{glyph}\n{label}", self)
            action.setCheckable(True)
            action.setToolTip(tooltip)
            action.triggered.connect(lambda _checked, m=mode_id: self._select(m))
            group.addAction(action)
            self.addAction(action)
            self._actions[mode_id] = action

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(self, mode_id: str) -> None:
        """Programmatically switch to ``mode_id`` (also emits ``mode_changed``)."""
        action = self._actions.get(mode_id)
        if action is None or action.isChecked():
            return
        action.setChecked(True)
        self._select(mode_id)

    def pulse(self, mode_id: str | None) -> None:
        """Highlight ``mode_id`` with a slow blink to attract attention.

        Call with ``None`` (or a different mode) to stop pulsing.
        """
        if self._pulse_target == mode_id:
            return
        self._pulse_target = mode_id
        self._pulse_on = False
        self._apply_pulse_style()
        if mode_id is None:
            self._pulse_timer.stop()
        else:
            self._pulse_timer.start()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _select(self, mode_id: str) -> None:
        self.mode_changed.emit(mode_id)
        # Stop pulsing the mode the user just landed on.
        if self._pulse_target == mode_id:
            self.pulse(None)

    def _toggle_pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        self._apply_pulse_style()

    def _apply_pulse_style(self) -> None:
        for mode_id, action in self._actions.items():
            if mode_id == self._pulse_target and self._pulse_on:
                action.setText(action.text())  # force redraw
                widget = self.widgetForAction(action)
                if widget is not None:
                    widget.setStyleSheet(f"background:{theme.ACCENT}; color:white;")
            else:
                widget = self.widgetForAction(action)
                if widget is not None:
                    widget.setStyleSheet("")

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QToolBar {{
                background:{theme.BG};
                border-right:1px solid {theme.BORDER};
                padding:4px 0;
                spacing:2px;
            }}
            QToolButton {{
                color:{theme.FG_MUTED};
                background:transparent;
                border:none;
                padding:10px 4px;
                min-width:60px;
                min-height:54px;
                font-size:10px;
            }}
            QToolButton:hover {{
                background:{theme.SURFACE};
                color:{theme.FG};
            }}
            QToolButton:checked {{
                background:{theme.SURFACE};
                color:{theme.ACCENT};
                border-left:2px solid {theme.ACCENT};
            }}
        """
