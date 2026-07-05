"""Argos visual theme — parameterized around :class:`~argos.ui.palettes.Palette`.

Single source of truth for all colors and the global Qt stylesheet.

Usage
-----
At startup, call :func:`apply_palette` with the desired preset::

    from argos.ui import theme
    from argos.ui.palettes import EQUILUX
    theme.apply_palette(EQUILUX)           # or load from config

All module-level constants (``theme.BG``, ``theme.ACCENT``, …) are rebound by
:func:`apply_palette` so every consumer that does ``theme.BG`` at *call time*
(not import time) picks up the new value automatically.  Widgets that embedded
a color string into a local stylesheet at *construction time* (sidebar icons,
dock_host QSS, statusbar) are **not** retroactively updated — see live-vs-restart
note in the WS9c spec.

:data:`get_stylesheet` returns a freshly generated QSS from the current palette.
Call it after :func:`apply_palette` to regenerate the global stylesheet.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argos.ui.palettes import Palette

# ---------------------------------------------------------------------------
# Active palette reference — replaced by apply_palette()
# ---------------------------------------------------------------------------

_active_palette: "Palette | None" = None


def _bootstrap() -> None:
    """Initialise module-level constants from EQUILUX without circular imports."""
    from argos.ui.palettes import EQUILUX
    apply_palette(EQUILUX)


def apply_palette(palette: "Palette") -> None:
    """Rebind every module-level color constant to the new *palette* values.

    Also regenerates :data:`LOG_COLORS` from the new palette so log-panel
    rendering picks up the change at the next message.  The caller is
    responsible for calling ``app.setStyleSheet(get_stylesheet())`` afterwards.
    """
    global _active_palette
    _active_palette = palette

    m = sys.modules[__name__]

    # ---- Backgrounds / surfaces ----
    m.BG = palette.bg
    m.BG2 = palette.bg2
    m.SURFACE = palette.surface
    m.BORDER = palette.border
    m.BORDER_SOFT = palette.border_soft

    # ---- Text ----
    m.FG = palette.fg
    m.FG_MUTED = palette.fg_muted
    m.FG_DISABLED = palette.fg_disabled

    # ---- Accent ----
    m.ACCENT = palette.accent
    m.ACCENT_HOVER = palette.accent_hover
    m.ACCENT_DEEP = palette.accent_deep
    m.CYAN = palette.cyan

    # ---- Semantic ----
    m.SUCCESS = palette.success
    m.WARNING = palette.warning
    m.DANGER = palette.danger
    m.VARIABLE = palette.variable

    # ---- Back-compat aliases ----
    m.SURFACE_1 = palette.bg
    m.SURFACE_2 = palette.bg
    m.SURFACE_3 = palette.bg2
    m.SURFACE_4 = palette.border
    m.TEXT_PRIMARY = palette.fg
    m.TEXT_MUTED = palette.fg_muted
    m.TEXT_DISABLED = palette.fg_disabled
    m.INFO = palette.cyan

    # ---- Fonts ----
    m.FONT_UI = palette.font_ui
    m.FONT_MONO = palette.font_mono

    # ---- Derived dicts ----
    m.LOG_COLORS = {
        "DEBUG": palette.fg_muted,
        "INFO": palette.accent,
        "OK": palette.success,
        "WARNING": palette.warning,
        "ERROR": palette.danger,
        "CRITICAL": palette.danger,
        "CMD": palette.cyan,
        "DISC": palette.warning,
    }


# ---------------------------------------------------------------------------
# Module-level constants — initialised to empty strings here, then
# immediately populated by _bootstrap() below.  apply_palette() rebinds them
# on every subsequent palette switch.  Keeping real assignments (not just bare
# annotations) means ruff/pyflakes can resolve these names inside get_stylesheet().
# ---------------------------------------------------------------------------

BG = ""
BG2 = ""
SURFACE = ""
BORDER = ""
BORDER_SOFT = ""

FG = ""
FG_MUTED = ""
FG_DISABLED = ""

ACCENT = ""
ACCENT_HOVER = ""
ACCENT_DEEP = ""
CYAN = ""

SUCCESS = ""
WARNING = ""
DANGER = ""
VARIABLE = ""

# Back-compat aliases (some panels reference the old SpaceX names)
SURFACE_1 = ""
SURFACE_2 = ""
SURFACE_3 = ""
SURFACE_4 = ""
TEXT_PRIMARY = ""
TEXT_MUTED = ""
TEXT_DISABLED = ""
INFO = ""

FONT_UI = ""
FONT_MONO = ""

LOG_COLORS: dict[str, str] = {}

# Bootstrap with the default palette immediately so that any module that does
# ``from argos.ui import theme`` at import time finds valid constants.
_bootstrap()


# ---------------------------------------------------------------------------
# Global Qt stylesheet — generated from the current palette
# ---------------------------------------------------------------------------


def get_stylesheet() -> str:
    """Return the global Qt stylesheet for the application.

    Always reads the current module-level constants, so calling this after
    :func:`apply_palette` yields a stylesheet for the new theme.
    """
    return f"""
/* ── Base ──────────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {BG};
    color: {FG};
    font-family: {FONT_UI};
    font-size: 13px;
}}

QMainWindow {{
    background-color: {BG};
}}

QMainWindow::separator {{
    background-color: {BORDER};
    width: 1px;
    height: 1px;
}}

/* ── Dock widgets ───────────────────────────────────────────────────────── */
QDockWidget {{
    background-color: {BG};
    color: {FG};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background-color: {BG};
    color: {ACCENT};
    padding: 6px 10px;
    font-size: 11px;
    font-family: {FONT_UI};
    font-weight: bold;
    border-bottom: 1px solid {BORDER};
}}

QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
    padding: 2px;
}}

/* ── Menu bar ───────────────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {BG};
    color: {FG};
    border-bottom: 1px solid {BORDER};
    padding: 2px 4px;
    font-size: 12px;
}}

QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 2px;
    background: transparent;
}}

QMenuBar::item:selected {{
    background-color: {SURFACE};
    color: {ACCENT};
}}

QMenu {{
    background-color: {BG};
    color: {FG};
    border: 1px solid {BORDER};
    padding: 4px 0;
}}

QMenu::item {{
    padding: 6px 24px 6px 12px;
}}

QMenu::item:selected {{
    background-color: {SURFACE};
    color: {ACCENT};
}}

QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 4px 0;
}}

/* ── Status bar ─────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {BG};
    color: {FG_MUTED};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}

QStatusBar::item {{
    border: none;
}}

/* ── Buttons — flat Siril-like ─────────────────────────────────────────── */
QPushButton {{
    background-color: {SURFACE};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 7px 14px;
    min-height: 26px;
    font-size: 13px;
    font-family: {FONT_UI};
}}

QPushButton:hover {{
    background-color: {BORDER};
    color: {FG};
    border-color: {BORDER};
}}

QPushButton:pressed {{
    background-color: {BG2};
}}

QPushButton:disabled {{
    color: {FG_DISABLED};
    background-color: {SURFACE};
    border-color: {BORDER_SOFT};
}}

QPushButton[class="primary"] {{
    background-color: {ACCENT_DEEP};
    color: white;
    border-color: {ACCENT_DEEP};
    font-weight: bold;
}}

QPushButton[class="primary"]:hover {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QPushButton[class="primary"]:disabled {{
    background-color: {SURFACE};
    color: {FG_DISABLED};
    border-color: {BORDER_SOFT};
}}

QPushButton[class="danger"] {{
    color: {DANGER};
    border-color: {DANGER};
    background-color: {SURFACE};
}}

QPushButton[class="danger"]:hover {{
    background-color: {DANGER};
    color: white;
}}

QPushButton[class="success"] {{
    color: {SUCCESS};
    border-color: {SUCCESS};
    background-color: {SURFACE};
}}

QPushButton[class="success"]:hover {{
    background-color: {SUCCESS};
    color: white;
}}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {BG2};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 6px 8px;
    min-height: 26px;
    font-family: {FONT_UI};
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {FG_DISABLED};
    background-color: {BG};
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {SURFACE};
    border: none;
    width: 14px;
    border-radius: 1px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {ACCENT};
}}

/* ── ComboBox ───────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {BG2};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 6px 8px;
    min-height: 26px;
    font-size: 13px;
}}

QComboBox:focus {{
    border-color: {ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG2};
    color: {FG};
    border: 1px solid {BORDER};
    selection-background-color: {SURFACE};
    selection-color: {ACCENT};
}}

/* ── Slider ─────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background-color: {BORDER};
    height: 3px;
    border-radius: 1px;
}}

QSlider::handle:horizontal {{
    background-color: {ACCENT};
    width: 12px;
    height: 12px;
    border-radius: 6px;
    margin: -5px 0;
}}

QSlider::sub-page:horizontal {{
    background-color: {ACCENT};
    height: 3px;
    border-radius: 1px;
}}

/* ── CheckBox ───────────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    font-size: 11px;
    color: {FG};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 2px;
    background-color: {BG2};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}

/* ── Labels ─────────────────────────────────────────────────────────────── */
QLabel {{
    color: {FG};
    background: transparent;
}}

QLabel[class="muted"] {{
    color: {FG_MUTED};
    font-size: 11px;
}}

QLabel[class="value"] {{
    font-family: {FONT_MONO};
    font-size: 14px;
    font-weight: bold;
    color: {ACCENT};
}}

QLabel[class="section"] {{
    color: {ACCENT};
    font-size: 12px;
    font-weight: bold;
}}

QLabel[class="field"] {{
    color: {WARNING};
    font-size: 11px;
}}

QLabel[class="title"] {{
    color: {ACCENT};
    font-size: 15px;
    font-weight: bold;
}}

QLabel[class="target"] {{
    color: {DANGER};
    font-size: 15px;
    font-weight: bold;
}}

/* ── GroupBox — Siril-style card (thin border, blue title) ─────────────── */
QGroupBox {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    margin-top: 14px;
    padding-top: 10px;
    font-size: 13px;
    font-family: {FONT_UI};
    font-weight: bold;
    color: {ACCENT};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    background-color: {BG};
    color: {ACCENT};
}}

/* ── Dialogs ────────────────────────────────────────────────────────────── */
QDialog {{
    background-color: {BG};
    border: 1px solid {BORDER};
}}

QDialogButtonBox QPushButton {{
    min-width: 80px;
}}

/* ── Scroll areas ───────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: {BG};
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {FG_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {BG};
    height: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 4px;
    min-width: 20px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Splitter ───────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {BORDER};
}}

QSplitter::handle:horizontal {{
    width: 4px;
}}

QSplitter::handle:vertical {{
    height: 4px;
}}

/* ── Tab bar (dock tabs) ────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG};
}}

QTabBar::tab {{
    background: {SURFACE};
    color: {FG_MUTED};
    border: 1px solid {BORDER};
    padding: 5px 14px;
    font-size: 11px;
}}

QTabBar::tab:selected {{
    background: {BG};
    color: {ACCENT};
    border-bottom-color: {BG};
    font-weight: bold;
}}

QTabBar::tab:hover {{
    color: {FG};
}}

/* ── Progress bar ───────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {BG2};
    border: 1px solid {BORDER};
    border-radius: 2px;
    text-align: center;
    color: {FG};
    font-size: 10px;
    height: 14px;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 1px;
}}

/* ── Tooltips ───────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {BG2};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 2px;
    padding: 4px 8px;
    font-size: 11px;
}}

/* ── Text edit (log panel) ──────────────────────────────────────────────── */
QTextEdit, QPlainTextEdit {{
    background-color: {BG2};
    color: {FG_MUTED};
    border: 1px solid {BORDER};
    border-radius: 2px;
    font-family: {FONT_MONO};
    font-size: 11px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}

/* ── Toolbar (top app bar) ─────────────────────────────────────────────── */
QToolBar {{
    background-color: {BG};
    border-bottom: 1px solid {BORDER};
    spacing: 6px;
    padding: 4px 8px;
}}

QToolBar QLabel {{
    color: {FG_MUTED};
    font-size: 11px;
}}

QToolBar::separator {{
    background-color: {BORDER};
    width: 1px;
    margin: 4px 6px;
}}

/* ── TreeView / TableView (for future star tables) ─────────────────────── */
QTreeView, QTableView, QHeaderView::section {{
    background-color: {BG2};
    color: {FG};
    border: none;
    gridline-color: {BORDER};
    selection-background-color: {SURFACE};
    selection-color: {ACCENT};
    alternate-background-color: {BG};
    font-size: 11px;
}}

QHeaderView::section {{
    background-color: {SURFACE};
    color: {ACCENT};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {BORDER};
    font-weight: bold;
}}
"""
