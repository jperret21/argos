"""On-image star-info card (docs/photometry_plan.md §5 B2, confirmed UX).

A compact, corner-anchored overlay card (bottom-left of the image, semi-transparent)
that shows what the user clicked — catalog identity + RA/Dec + mags + measured
FWHM/SNR — and offers role buttons to build the night's target set. It never follows
the cursor, so it stays put under zoom/pan. The page owns the hit-test and the
TargetSet; this widget is display + buttons only.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from seercontrol.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, ROLE_TARGET
from seercontrol.ui import theme


class StarInfoCard(QFrame):
    """Floating info card with role-assignment buttons."""

    role_selected = pyqtSignal(str)  # ROLE_TARGET | ROLE_COMPARISON | ROLE_CHECK
    cleared = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: rgba(13,17,23,225); border: 1px solid {theme.ACCENT};"
            f" border-radius: 4px; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self._title = QLabel("")
        self._title.setStyleSheet(
            f"color:{theme.FG}; font-size:12px; font-weight:600; background:transparent;"
        )
        top.addWidget(self._title, 1)
        close = QPushButton("×")
        close.setFixedSize(18, 18)
        close.setStyleSheet("font-size: 13px; padding: 0;")
        close.setToolTip("Dismiss")
        close.clicked.connect(self._on_close)
        top.addWidget(close)
        root.addLayout(top)

        self._body = QLabel("")
        self._body.setTextFormat(Qt.TextFormat.PlainText)
        self._body.setStyleSheet(
            f"color:{theme.FG}; font-family:{theme.FONT_MONO}; font-size:11px;"
            f" background:transparent;"
        )
        root.addWidget(self._body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._role_btns: dict[str, QPushButton] = {}
        for role, text in (
            (ROLE_TARGET, "Target"),
            (ROLE_COMPARISON, "Comparison"),
            (ROLE_CHECK, "Check"),
        ):
            b = QPushButton(text)
            b.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            b.clicked.connect(lambda _c, r=role: self.role_selected.emit(r))
            self._role_btns[role] = b
            btn_row.addWidget(b)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self._clear_btn.clicked.connect(self.cleared)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)
        self.hide()

    def show_star(self, title: str, body: str, *, roles_enabled: bool) -> None:
        """Populate + show the card. ``roles_enabled`` gates the role buttons
        (off until a plate-solve gives the star a real RA/Dec)."""
        self._title.setText(title)
        self._body.setText(body)
        for b in self._role_btns.values():
            b.setEnabled(roles_enabled)
        self.adjustSize()
        self.show()
        self.raise_()

    def reposition(self) -> None:
        """Anchor bottom-left of the parent (call on show + on resize)."""
        parent = self.parentWidget()
        if parent is not None:
            self.move(12, max(12, parent.height() - self.height() - 12))

    def _on_close(self) -> None:
        self.hide()
        self.cleared.emit()
