"""Session log panel — colored, timestamped, scrollable log display."""

from __future__ import annotations

import html
import logging
from datetime import datetime

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seercontrol.ui import theme

logger = logging.getLogger(__name__)


class LogPanel(QWidget):
    """Scrollable session log with per-level color coding.

    Receives (level, message) tuples and appends them as colored HTML rows
    with a timestamp prefix.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.setMinimumHeight(80)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Toolbar row
        bar = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self._text.clear if hasattr(self, "_text") else lambda: None)
        bar.addStretch()
        bar.addWidget(clear_btn)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._text.setStyleSheet(
            f"background:{theme.BG2}; color:{theme.FG_MUTED}; border:1px solid {theme.BORDER};"
            f"font-family:{theme.FONT_MONO}; font-size:11px;"
        )

        # Re-connect clear button now that _text exists
        clear_btn.clicked.disconnect()
        clear_btn.clicked.connect(self._text.clear)

        root.addLayout(bar)
        root.addWidget(self._text)

    @pyqtSlot(str, str)
    def append(self, level: str, message: str) -> None:
        """Append a timestamped, colored log entry.

        Args:
            level:   Log level string (OK, INFO, ERROR, CMD, …).
            message: Human-readable message.
        """
        color = theme.LOG_COLORS.get(level.upper(), theme.TEXT_PRIMARY)
        ts = datetime.now().strftime("%H:%M:%S")
        safe_msg = html.escape(message)

        line = (
            f'<span style="color:{theme.TEXT_MUTED}">{ts}</span>'
            f'&nbsp;<span style="color:{color};font-weight:bold">[{level}]</span>'
            f'&nbsp;<span style="color:{theme.TEXT_PRIMARY}">{safe_msg}</span>'
        )
        self._text.append(line)

        # Auto-scroll to bottom
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())
