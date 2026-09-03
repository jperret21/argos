"""Left navigation sidebar — switches between the workflow phases.

Vertical toolbar pinned to the left of the Shell. Each entry is a crisp,
vector line icon above a wrapped label; clicking it emits
``mode_changed(mode_id)`` which the Shell uses to swap the central
QStackedWidget page.

Icons are inline SVG (Feather, MIT) rendered with QtSvg — no emoji, no shipped
asset files — so they stay sharp at any DPI and recolour with the theme (muted →
hover → accent) by injecting the stroke colour.

Each entry carries a small state dot (``set_mode_state``): green = the phase's
prerequisites are met, accent = the phase is actively running (e.g. a sequence
on Capture), amber = blocked (a required device is missing). No dot = neutral.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QByteArray, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QLabel, QSizePolicy, QToolBar, QVBoxLayout, QWidget

from argos.ui import design, theme

logger = logging.getLogger(__name__)


# (mode_id, label, tooltip). The icon is drawn from ``mode_id`` (see _draw_icon).
# NINA-style: the night happens in ONE screen (Capture — image, camera,
# sequencer, mount goto, focuser + V-curve, photometry overlays and the live
# curve all live there). Equipment is a 2-minute setup stop, Analyze is
# post-prod. Settings is pushed to the bottom (a destination, not a phase).
# The mode id "connect" is kept for config/back-compat; the label describes
# the observer's task rather than the underlying device protocol.
MODES: tuple[tuple[str, str, str], ...] = (
    ("connect", "Connection", "Connect the telescope equipment"),
    ("capture", "Observe", "Frame, focus and monitor the observation"),
    ("sequencer", "Plan", "Plan and run the night's capture sequence"),
    ("analyze", "Review", "Inspect the light curve and export AAVSO"),
    ("settings", "Settings", "Observer, site, paths, appearance"),
)

#: Mode that sits at the bottom of the rail, after an expanding spacer.
_FOOTER_MODE = "settings"

_ICON_PX = 24  # logical icon size

# Feather (MIT) icon bodies on a 24×24 viewBox, recoloured per state by injecting
# the stroke colour: wifi=connect, crosshair=target, disc=focus, star=photometry,
# camera=capture, trending-up=analyze, sliders=settings.
_ICON_PATHS: dict[str, str] = {
    "connect": (
        '<path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
        '<path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
        '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
        '<line x1="12" y1="20" x2="12.01" y2="20"/>'
    ),
    "capture": (
        '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
        '<circle cx="12" cy="13" r="4"/>'
    ),
    "sequencer": (  # Feather "list": the ordered plan of the night
        '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>'
        '<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>'
        '<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>'
    ),
    "analyze": (
        '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>' '<polyline points="17 6 23 6 23 12"/>'
    ),
    "settings": (
        '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
        '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
        '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
        '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
        '<line x1="17" y1="16" x2="23" y2="16"/>'
    ),
}

# Cache rendered icons by (mode, colour) so repaints don't re-rasterise the SVG.
_icon_cache: dict[tuple[str, str], QPixmap] = {}


def _draw_icon(mode: str, color: str, px: int = _ICON_PX) -> QPixmap:
    """Render the Feather icon for ``mode`` stroked in ``color`` (cached)."""
    key = (mode, color)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'{_ICON_PATHS.get(mode, "")}</svg>'
    )
    dpr = 2  # rasterise at 2× and tag the device-pixel ratio → crisp on HiDPI
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(px * dpr, px * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    # A device-pixel-ratio pixmap paints in *logical* coordinates (px), so render
    # to the logical rect — not the device rect — or the icon is drawn at 2× and
    # clipped to the top-left quarter.
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()

    _icon_cache[key] = pm
    return pm


def _state_dot_color(state: str) -> str | None:
    """Resolve state colour after the user-selected palette is active."""
    return {
        "none": None,
        "ready": theme.SUCCESS,
        "active": theme.ACCENT,
        "blocked": theme.WARNING,
    }.get(state)


class _NavButton(QWidget):
    """One sidebar entry: a recoloured line icon above a wrapped label.

    Keyboard-accessible: Tab focuses it (drawn like hover), Space/Return
    activates it — the F-key shortcuts stay available via the View menu.
    """

    clicked = pyqtSignal()

    def __init__(
        self, mode_id: str, label: str, tooltip: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._mode_id = mode_id
        self._selected = False
        self._hover = False
        self._focused = False
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(88, 66)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(label)

        lay = QVBoxLayout(self)
        # Left margin clears the 3px accent border (a QSS border on a plain
        # QWidget isn't auto-subtracted from the layout's content rect).
        lay.setContentsMargins(8, 8, 4, 8)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = QLabel()
        self._icon.setFixedHeight(_ICON_PX)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text = QLabel(label)
        self._text.setWordWrap(True)
        self._text.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._text, 0, Qt.AlignmentFlag.AlignHCenter)

        # Phase-state dot, floating in the top-right corner over the layout.
        self._dot = QLabel("●", self)
        self._dot.setStyleSheet("background:transparent; font-size:8px;")
        self._dot.adjustSize()
        self._dot.move(self.width() - self._dot.width() - 6, 5)
        self._dot.hide()

        self._refresh()

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._refresh()

    def set_state(self, state: str) -> None:
        """Show the phase-state dot: 'none' | 'ready' | 'active' | 'blocked'."""
        color = _state_dot_color(state)
        if color is None:
            self._dot.hide()
            return
        self._dot.setStyleSheet(f"background:transparent; font-size:8px; color:{color};")
        self._dot.show()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = True
        self._refresh()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = False
        self._refresh()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._focused = True
        self._refresh()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._focused = False
        self._refresh()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _refresh(self) -> None:
        if self._selected:
            fg, bg, border = theme.ACCENT, theme.SURFACE, theme.ACCENT
        elif self._hover or self._focused:
            fg, bg, border = theme.FG, theme.SURFACE, "transparent"
        else:
            fg, bg, border = theme.FG_MUTED, "transparent", "transparent"
        self.setStyleSheet(f"background:{bg}; border-left:3px solid {border};")
        self._text.setStyleSheet(
            f"color:{fg}; font-size:{design.FONT_SIZE_TINY}px; font-weight:500;"
            f" background:transparent;"
        )
        self._icon.setPixmap(_draw_icon(self._mode_id, fg))


class Sidebar(QToolBar):
    """Left navigation toolbar with the mutually-exclusive workflow phases."""

    mode_changed = pyqtSignal(str)  # mode id ('connect', 'target', 'capture', ...)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Modes", parent)
        # objectName is required by QMainWindow.saveState() to persist toolbar layout.
        self.setObjectName("ModesSidebar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setOrientation(Qt.Orientation.Vertical)
        self.setStyleSheet(self._stylesheet())
        self.setFixedWidth(92)

        self._buttons: dict[str, _NavButton] = {}
        self._current: str | None = None

        for mode_id, label, tooltip in MODES:
            if mode_id == _FOOTER_MODE:
                # Push Settings to the bottom of the rail, set off by a divider.
                spacer = QWidget()
                spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
                self.addWidget(spacer)
                self.addSeparator()
            btn = _NavButton(mode_id, label, tooltip, self)
            btn.clicked.connect(lambda m=mode_id: self.select(m))
            self.addWidget(btn)
            self._buttons[mode_id] = btn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(self, mode_id: str) -> None:
        """Switch to ``mode_id`` (highlights it and emits ``mode_changed``)."""
        if mode_id not in self._buttons or self._current == mode_id:
            return
        for mid, btn in self._buttons.items():
            btn.set_selected(mid == mode_id)
        self._current = mode_id
        self.mode_changed.emit(mode_id)

    def set_mode_state(self, mode_id: str, state: str) -> None:
        """Set the phase-state dot on a mode entry.

        Args:
            mode_id: One of the :data:`MODES` ids.
            state:   ``"none"`` | ``"ready"`` | ``"active"`` | ``"blocked"``.
        """
        btn = self._buttons.get(mode_id)
        if btn is not None:
            btn.set_state(state)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QToolBar {{
                background:{theme.BG};
                border-right:1px solid {theme.BORDER};
                padding:6px 0;
                spacing:2px;
            }}
        """
