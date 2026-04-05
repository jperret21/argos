"""SeerControl visual theme.

Single source of truth for all colors and the global Qt stylesheet.
Apply once at startup via QApplication.setStyleSheet(get_stylesheet()).
Never hardcode colors in individual widgets — reference these constants.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Color palette — dark observatory theme
# ---------------------------------------------------------------------------

ACCENT = "#58a6ff"        # blue — primary accents, interactive elements
SUCCESS = "#3fb950"       # green — connected, OK, success states
WARNING = "#f0883e"       # orange — warnings, non-critical issues
DANGER = "#f85149"        # red — errors, destructive actions
INFO = "#79c0ff"          # light blue — informational highlights

SURFACE_1 = "#0d1117"    # application background
SURFACE_2 = "#161b22"    # panel / dock background
SURFACE_3 = "#21262d"    # input, card background
SURFACE_4 = "#30363d"    # borders, separators, hover

TEXT_PRIMARY = "#e6edf3"
TEXT_MUTED = "#8b949e"
TEXT_DISABLED = "#484f58"


# ---------------------------------------------------------------------------
# Log level colors (used in LogPanel)
# ---------------------------------------------------------------------------

LOG_COLORS: dict[str, str] = {
    "DEBUG":    TEXT_MUTED,
    "INFO":     ACCENT,
    "OK":       SUCCESS,
    "WARNING":  WARNING,
    "ERROR":    DANGER,
    "CRITICAL": DANGER,
    "CMD":      "#d2a8ff",   # purple — user commands
    "DISC":     WARNING,     # discovery events
}


# ---------------------------------------------------------------------------
# Global Qt stylesheet
# ---------------------------------------------------------------------------

def get_stylesheet() -> str:
    """Return the global Qt stylesheet for the application."""
    return f"""
/* ── Base ──────────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {SURFACE_1};
    color: {TEXT_PRIMARY};
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 12px;
}}

/* ── Main window ────────────────────────────────────────────────────────── */
QMainWindow {{
    background-color: {SURFACE_1};
}}

QMainWindow::separator {{
    background-color: {SURFACE_4};
    width: 2px;
    height: 2px;
}}

/* ── Dock widgets ───────────────────────────────────────────────────────── */
QDockWidget {{
    background-color: {SURFACE_2};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background-color: {SURFACE_2};
    color: {TEXT_MUTED};
    padding: 6px 10px;
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    border-bottom: 1px solid {SURFACE_4};
}}

QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
    padding: 2px;
}}

/* ── Menu bar ───────────────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {SURFACE_2};
    color: {TEXT_PRIMARY};
    border-bottom: 1px solid {SURFACE_4};
    padding: 2px 0;
}}

QMenuBar::item:selected {{
    background-color: {SURFACE_4};
    border-radius: 4px;
}}

QMenu {{
    background-color: {SURFACE_2};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 5px 20px 5px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {SURFACE_4};
}}

QMenu::separator {{
    height: 1px;
    background-color: {SURFACE_4};
    margin: 4px 8px;
}}

/* ── Status bar ─────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {SURFACE_2};
    color: {TEXT_MUTED};
    border-top: 1px solid {SURFACE_4};
    font-size: 11px;
}}

QStatusBar::item {{
    border: none;
}}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {SURFACE_3};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}}

QPushButton:hover {{
    background-color: {SURFACE_4};
    border-color: {ACCENT};
}}

QPushButton:pressed {{
    background-color: {SURFACE_4};
}}

QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {SURFACE_4};
}}

QPushButton[class="primary"] {{
    background-color: {ACCENT};
    color: {SURFACE_1};
    font-weight: bold;
    border-color: {ACCENT};
}}

QPushButton[class="primary"]:hover {{
    opacity: 0.85;
}}

QPushButton[class="danger"] {{
    color: {DANGER};
    border-color: {DANGER};
}}

QPushButton[class="danger"]:hover {{
    background-color: rgba(248, 81, 73, 0.1);
}}

QPushButton[class="success"] {{
    color: {SUCCESS};
    border-color: {SUCCESS};
}}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {SURFACE_3};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}

QLineEdit:disabled, QSpinBox:disabled {{
    color: {TEXT_DISABLED};
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {SURFACE_4};
    border: none;
    width: 16px;
    border-radius: 3px;
}}

/* ── ComboBox ───────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {SURFACE_3};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 6px;
    padding: 5px 8px;
}}

QComboBox:focus {{
    border-color: {ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {SURFACE_2};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    selection-background-color: {SURFACE_4};
}}

/* ── Labels ─────────────────────────────────────────────────────────────── */
QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QLabel[class="muted"] {{
    color: {TEXT_MUTED};
    font-size: 10px;
}}

QLabel[class="value"] {{
    font-size: 16px;
    font-weight: bold;
    color: {ACCENT};
}}

QLabel[class="section"] {{
    color: {TEXT_MUTED};
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}

/* ── GroupBox ───────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {SURFACE_2};
    border: 1px solid {SURFACE_4};
    border-radius: 8px;
    margin-top: 8px;
    padding-top: 8px;
    font-size: 10px;
    color: {TEXT_MUTED};
    letter-spacing: 1px;
    text-transform: uppercase;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}

/* ── Scroll areas ───────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: {SURFACE_2};
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {SURFACE_4};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Splitter ───────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {SURFACE_4};
}}

/* ── Tab widget ─────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {SURFACE_4};
    border-radius: 6px;
    background: {SURFACE_2};
}}

QTabBar::tab {{
    background: {SURFACE_3};
    color: {TEXT_MUTED};
    border: 1px solid {SURFACE_4};
    padding: 6px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

QTabBar::tab:selected {{
    background: {SURFACE_2};
    color: {TEXT_PRIMARY};
    border-bottom-color: {SURFACE_2};
}}

QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}

/* ── Progress bar ───────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {SURFACE_3};
    border: 1px solid {SURFACE_4};
    border-radius: 4px;
    text-align: center;
    color: {TEXT_PRIMARY};
    font-size: 11px;
    height: 12px;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}

/* ── Tooltips ───────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {SURFACE_3};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}}
"""
