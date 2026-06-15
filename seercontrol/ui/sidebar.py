"""Left navigation sidebar — switches between the 3 modes.

Vertical toolbar pinned to the left of the Shell. Each entry is a crisp,
vector line icon above a wrapped label; clicking it emits
``mode_changed(mode_id)`` which the Shell uses to swap the central
QStackedWidget page.

Icons are inline SVG (Feather, MIT) rendered with QtSvg — no emoji, no shipped
asset files — so they stay sharp at any DPI and recolour with the theme (muted →
hover → accent) by injecting the stroke colour.

``pulse(mode_id)`` is kept as a no-op for API compatibility (the Shell calls it
as a guidance hint); the attention blink was removed as visually distracting.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QByteArray, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QLabel, QToolBar, QVBoxLayout, QWidget

from seercontrol.ui import theme

logger = logging.getLogger(__name__)


# (mode_id, label, tooltip). The icon is drawn from ``mode_id`` (see _draw_icon).
MODES: tuple[tuple[str, str, str], ...] = (
    ("connection", "Connection", "Connect the Seestar devices and Stellarium"),
    ("acquisition", "Acquisition", "Live preview, focus, capture and sequencing"),
    ("configuration", "Configuration", "Theme, language, paths, observer, credits"),
)

_ICON_PX = 24  # logical icon size

# Feather (MIT) icon bodies on a 24×24 viewBox: wifi=connect, camera=capture,
# sliders=settings. Recoloured per state by injecting the stroke colour.
_ICON_PATHS: dict[str, str] = {
    "connection": (
        '<path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
        '<path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
        '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
        '<line x1="12" y1="20" x2="12.01" y2="20"/>'
    ),
    "acquisition": (
        '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>'
        '<circle cx="12" cy="13" r="4"/>'
    ),
    "configuration": (
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


class _NavButton(QWidget):
    """One sidebar entry: a recoloured line icon above a wrapped label."""

    clicked = pyqtSignal()

    def __init__(
        self, mode_id: str, label: str, tooltip: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._mode_id = mode_id
        self._selected = False
        self._hover = False
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(88, 66)

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
        self._refresh()

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._refresh()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = True
        self._refresh()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = False
        self._refresh()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _refresh(self) -> None:
        if self._selected:
            fg, bg, border = theme.ACCENT, theme.SURFACE, theme.ACCENT
        elif self._hover:
            fg, bg, border = theme.FG, theme.SURFACE, "transparent"
        else:
            fg, bg, border = theme.FG_MUTED, "transparent", "transparent"
        self.setStyleSheet(f"background:{bg}; border-left:3px solid {border};")
        self._text.setStyleSheet(
            f"color:{fg}; font-size:10px; font-weight:500; background:transparent;"
        )
        self._icon.setPixmap(_draw_icon(self._mode_id, fg))


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
        self.setStyleSheet(self._stylesheet())
        self.setFixedWidth(92)

        self._buttons: dict[str, _NavButton] = {}
        self._current: str | None = None

        for mode_id, label, tooltip in MODES:
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

    def pulse(self, mode_id: str | None) -> None:  # noqa: ARG002 (kept for API compat)
        """No-op. The attention blink was removed (visually distracting)."""
        return

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
