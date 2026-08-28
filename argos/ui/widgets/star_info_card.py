"""On-image star-info card (docs/photometry_plan.md §5 B2, confirmed UX).

A compact overlay card that shows what the user clicked — catalog identity +
RA/Dec + mags + measured FWHM/SNR — and offers role buttons to build the
night's target set. It starts bottom-left but can be dragged by its title and
resized from its lower-right corner. The page owns the hit-test and TargetSet;
this widget is display + buttons only.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, ROLE_TARGET
from argos.ui import theme

_BTN_STYLE = "font-size: 11px; padding: 2px 8px;"


class StarInfoCard(QFrame):
    """Floating info card with role-assignment buttons."""

    role_selected = pyqtSignal(str)  # ROLE_TARGET | ROLE_COMPARISON | ROLE_CHECK
    remove_selected = pyqtSignal()  # drop the shown star from the target set
    cleared = pyqtSignal()  # dismiss the card (never touches the set)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dragging = False
        self._resizing = False
        self._user_positioned = False
        self._user_resized = False
        self._press_global = None
        self._origin_pos = None
        self._origin_size = None
        self.setMinimumSize(240, 120)
        self.setMouseTracking(True)
        self.setToolTip(
            "Drag the title to move this panel. Drag its lower-right corner to resize it."
        )
        self.setStyleSheet(
            f"QFrame {{ background: rgba(13,17,23,225); border: 1px solid {theme.ACCENT};"
            f" border-radius: 4px; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self._title = QLabel("")
        self._title.setCursor(Qt.CursorShape.SizeAllCursor)
        self._title.setToolTip("Drag to move this panel")
        self._title.installEventFilter(self)
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
        self._body.setWordWrap(True)
        self._body.setStyleSheet(
            f"color:{theme.FG}; font-family:{theme.FONT_MONO}; font-size:11px;"
            f" background:transparent;"
        )
        root.addWidget(self._body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._role_btns: dict[str, QPushButton] = {}
        for role, text, tip in (
            (ROLE_TARGET, "Target", "Variable star whose brightness you are measuring"),
            (
                ROLE_COMPARISON,
                "Comparison star",
                "Reference star used to calibrate differential magnitudes",
            ),
            (
                ROLE_CHECK,
                "Check star",
                "Expected-constant star measured against the comparison ensemble to verify it",
            ),
        ):
            b = QPushButton(text)
            b.setStyleSheet(_BTN_STYLE)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c, r=role: self.role_selected.emit(r))
            self._role_btns[role] = b
            btn_row.addWidget(b)
        # Remove: symmetric with the role buttons — a star added from the
        # image must be removable from the image (only shown for saved stars).
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setStyleSheet(_BTN_STYLE)
        self._remove_btn.setToolTip("Drop this star from the target set")
        self._remove_btn.clicked.connect(self.remove_selected)
        btn_row.addWidget(self._remove_btn)
        self._clear_btn = QPushButton("Dismiss")
        self._clear_btn.setStyleSheet(_BTN_STYLE)
        self._clear_btn.setToolTip("Close this card (keeps the target set as is)")
        self._clear_btn.clicked.connect(self.cleared)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)
        self.hide()

    def show_star(
        self, title: str, body: str, *, roles_enabled: bool, removable: bool = False
    ) -> None:
        """Populate + show the card. ``roles_enabled`` gates the role buttons
        (off until a plate-solve gives the star a real RA/Dec); ``removable``
        shows Remove when the clicked star is already in the target set."""
        self._title.setText(title)
        self._body.setText(body)
        for b in self._role_btns.values():
            b.setEnabled(roles_enabled)
        self._remove_btn.setVisible(removable)
        if not self._user_resized:
            self.adjustSize()
        self.show()
        self.raise_()

    def reposition(self) -> None:
        """Anchor initially, then keep a manually placed card inside its parent."""
        parent = self.parentWidget()
        if parent is not None and not self._user_positioned:
            self.move(12, max(12, parent.height() - self.height() - 12))
        elif parent is not None:
            self.move(self._clamp_position(self.pos()))

    # ------------------------------------------------------------------
    # Pointer interaction — a small, direct overlay window within the viewer.
    # ------------------------------------------------------------------

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt override)
        if watched is self._title:
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._begin_drag(event)
                return True
            if event.type() == QEvent.Type.MouseMove and self._dragging:
                self._update_pointer(event)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._dragging:
                self._end_pointer()
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self._in_resize_corner(event.pos()):
            self._begin_resize(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._dragging or self._resizing:
            self._update_pointer(event)
            event.accept()
            return
        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor
            if self._in_resize_corner(event.pos())
            else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and (self._dragging or self._resizing):
            self._end_pointer()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _begin_drag(self, event) -> None:
        self._dragging = True
        self._resizing = False
        self._press_global = event.globalPosition().toPoint()
        self._origin_pos = self.pos()
        self.grabMouse()

    def _begin_resize(self, event) -> None:
        self._resizing = True
        self._dragging = False
        self._press_global = event.globalPosition().toPoint()
        self._origin_size = self.size()
        self.grabMouse()

    def _update_pointer(self, event) -> None:
        if self._press_global is None:
            return
        delta = event.globalPosition().toPoint() - self._press_global
        parent = self.parentWidget()
        if self._dragging and self._origin_pos is not None:
            self.move(self._clamp_position(self._origin_pos + delta))
            self._user_positioned = True
        elif self._resizing and self._origin_size is not None:
            width = max(self.minimumWidth(), self._origin_size.width() + delta.x())
            height = max(self.minimumHeight(), self._origin_size.height() + delta.y())
            if parent is not None:
                width = min(width, max(self.minimumWidth(), parent.width() - self.x()))
                height = min(height, max(self.minimumHeight(), parent.height() - self.y()))
            self.resize(width, height)
            self._user_resized = True

    def _end_pointer(self) -> None:
        self._dragging = self._resizing = False
        self._press_global = self._origin_pos = self._origin_size = None
        self.releaseMouse()

    def _in_resize_corner(self, pos) -> bool:
        grip = 16
        return pos.x() >= self.width() - grip and pos.y() >= self.height() - grip

    def _clamp_position(self, pos):
        parent = self.parentWidget()
        if parent is None:
            return pos
        return pos.__class__(
            min(max(0, pos.x()), max(0, parent.width() - self.width())),
            min(max(0, pos.y()), max(0, parent.height() - self.height())),
        )

    def _on_close(self) -> None:
        self.hide()
        self.cleared.emit()
