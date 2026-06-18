"""Shared "coming soon" page used during R1 — replaced as each mode lands."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from argos.ui import theme


class PlaceholderPage(QWidget):
    """Minimal placeholder used during the redesign sprints.

    Each real mode page replaces this in turn (Imaging in R2, Equipment in
    R3, Target in R4).
    """

    def __init__(self, title: str, sprint_name: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        head = QLabel(title.upper())
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:24px; font-weight:bold;"
            f" background:transparent;"
        )
        layout.addWidget(head)

        sub = QLabel(
            f"Coming in sprint {sprint_name}." if sprint_name else "Coming soon."
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:12px; background:transparent;"
        )
        layout.addWidget(sub)
