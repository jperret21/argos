"""SeerControl visual theme — SpaceX-inspired aerospace UI.

Single source of truth for all colors and the global Qt stylesheet.
Apply once at startup via QApplication.setStyleSheet(get_stylesheet()).
Never hardcode colors in individual widgets — reference these constants.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Color palette — cold, precise, aerospace
# ---------------------------------------------------------------------------

ACCENT       = "#4fc3f7"   # cold electric blue — primary interactive
SUCCESS      = "#00e5a0"   # cyan-green — connected, OK
WARNING      = "#ffb347"   # amber — warnings
DANGER       = "#ff4444"   # clean red — errors, destructive
INFO         = "#b0bec5"   # slate — informational

SURFACE_1    = "#080a0c"   # near-black application background
SURFACE_2    = "#0e1218"   # panel / dock background
SURFACE_3    = "#141a22"   # input, card background
SURFACE_4    = "#1e2733"   # borders, separators, hover

TEXT_PRIMARY  = "#e8edf2"
TEXT_MUTED    = "#6b7a8d"
TEXT_DISABLED = "#3a4450"

# Monospace font for data values (coordinates, numbers)
FONT_MONO = '"JetBrains Mono", "Fira Code", "SF Mono", "Consolas", monospace'
# Clean sans-serif for UI chrome
FONT_UI   = '"Inter", "Helvetica Neue", "Segoe UI", "Arial", sans-serif'


# ---------------------------------------------------------------------------
# Log level colors
# ---------------------------------------------------------------------------

LOG_COLORS: dict[str, str] = {
    "DEBUG":    TEXT_MUTED,
    "INFO":     ACCENT,
    "OK":       SUCCESS,
    "WARNING":  WARNING,
    "ERROR":    DANGER,
    "CRITICAL": DANGER,
    "CMD":      "#ce93d8",
    "DISC":     WARNING,
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
    font-family: {FONT_UI};
    font-size: 12px;
}}

/* ── Main window ────────────────────────────────────────────────────────── */
QMainWindow {{
    background-color: {SURFACE_1};
}}

QMainWindow::separator {{
    background-color: {SURFACE_4};
    width: 1px;
    height: 1px;
}}

/* ── Dock widgets ───────────────────────────────────────────────────────── */
QDockWidget {{
    background-color: {SURFACE_2};
}}

QDockWidget::title {{
    background-color: {SURFACE_2};
    color: {TEXT_MUTED};
    padding: 5px 10px;
    font-size: 9px;
    font-family: {FONT_UI};
    letter-spacing: 2px;
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
    padding: 2px 4px;
    font-size: 12px;
}}

QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 2px;
}}

QMenuBar::item:selected {{
    background-color: {SURFACE_4};
}}

QMenu {{
    background-color: {SURFACE_2};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    padding: 4px 0;
}}

QMenu::item {{
    padding: 6px 24px 6px 12px;
}}

QMenu::item:selected {{
    background-color: {SURFACE_4};
    color: {ACCENT};
}}

QMenu::separator {{
    height: 1px;
    background-color: {SURFACE_4};
    margin: 4px 0;
}}

/* ── Status bar ─────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {SURFACE_2};
    color: {TEXT_MUTED};
    border-top: 1px solid {SURFACE_4};
    font-size: 11px;
    font-family: {FONT_MONO};
}}

QStatusBar::item {{
    border: none;
}}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    padding: 5px 14px;
    font-size: 11px;
    font-family: {FONT_UI};
    letter-spacing: 0.5px;
}}

QPushButton:hover {{
    background-color: {SURFACE_4};
    border-color: {ACCENT};
    color: {ACCENT};
}}

QPushButton:pressed {{
    background-color: {SURFACE_3};
}}

QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {SURFACE_3};
}}

QPushButton[class="primary"] {{
    background-color: {ACCENT};
    color: {SURFACE_1};
    font-weight: 600;
    border-color: {ACCENT};
    letter-spacing: 1px;
}}

QPushButton[class="primary"]:hover {{
    background-color: #6dcfff;
    border-color: #6dcfff;
}}

QPushButton[class="danger"] {{
    color: {DANGER};
    border-color: {DANGER};
}}

QPushButton[class="danger"]:hover {{
    background-color: rgba(255, 68, 68, 0.1);
}}

QPushButton[class="success"] {{
    color: {SUCCESS};
    border-color: {SUCCESS};
}}

QPushButton[class="success"]:hover {{
    background-color: rgba(0, 229, 160, 0.08);
}}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {SURFACE_3};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    padding: 4px 8px;
    font-family: {FONT_MONO};
    font-size: 11px;
    selection-background-color: {ACCENT};
    selection-color: {SURFACE_1};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
    background-color: {SURFACE_2};
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {TEXT_DISABLED};
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {SURFACE_4};
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
    background-color: {SURFACE_3};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    padding: 4px 8px;
    font-size: 11px;
}}

QComboBox:focus {{
    border-color: {ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QComboBox QAbstractItemView {{
    background-color: {SURFACE_2};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    selection-background-color: {SURFACE_4};
    selection-color: {ACCENT};
}}

/* ── Slider ─────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background-color: {SURFACE_4};
    height: 2px;
    border-radius: 1px;
}}

QSlider::handle:horizontal {{
    background-color: {ACCENT};
    width: 10px;
    height: 10px;
    border-radius: 5px;
    margin: -4px 0;
}}

QSlider::sub-page:horizontal {{
    background-color: {ACCENT};
    height: 2px;
    border-radius: 1px;
}}

/* ── CheckBox ───────────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    font-size: 11px;
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    background-color: {SURFACE_3};
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
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QLabel[class="muted"] {{
    color: {TEXT_MUTED};
    font-size: 10px;
}}

QLabel[class="value"] {{
    font-family: {FONT_MONO};
    font-size: 16px;
    font-weight: bold;
    color: {ACCENT};
}}

QLabel[class="section"] {{
    color: {TEXT_MUTED};
    font-size: 9px;
    letter-spacing: 2px;
    text-transform: uppercase;
}}

/* ── GroupBox ───────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {SURFACE_2};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    margin-top: 10px;
    padding-top: 8px;
    font-size: 9px;
    font-family: {FONT_UI};
    color: {TEXT_MUTED};
    letter-spacing: 2px;
    text-transform: uppercase;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}

/* ── Dialogs ────────────────────────────────────────────────────────────── */
QDialog {{
    background-color: {SURFACE_2};
    border: 1px solid {SURFACE_4};
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
    background: {SURFACE_2};
    width: 6px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: {SURFACE_4};
    border-radius: 3px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {SURFACE_2};
    height: 6px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background: {SURFACE_4};
    border-radius: 3px;
    min-width: 20px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Splitter ───────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {SURFACE_4};
}}

/* ── Tab bar (dock tabs) ────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {SURFACE_4};
    background: {SURFACE_2};
}}

QTabBar::tab {{
    background: {SURFACE_3};
    color: {TEXT_MUTED};
    border: 1px solid {SURFACE_4};
    padding: 5px 14px;
    font-size: 9px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}

QTabBar::tab:selected {{
    background: {SURFACE_2};
    color: {ACCENT};
    border-bottom-color: {SURFACE_2};
}}

QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}

/* ── Progress bar ───────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {SURFACE_3};
    border: 1px solid {SURFACE_4};
    border-radius: 1px;
    text-align: center;
    color: {TEXT_PRIMARY};
    font-size: 10px;
    height: 10px;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 1px;
}}

/* ── Tooltips ───────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {SURFACE_3};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    padding: 4px 8px;
    font-size: 11px;
}}

/* ── Text edit (log panel) ──────────────────────────────────────────────── */
QTextEdit, QPlainTextEdit {{
    background-color: {SURFACE_1};
    color: {TEXT_PRIMARY};
    border: 1px solid {SURFACE_4};
    border-radius: 2px;
    font-family: {FONT_MONO};
    font-size: 11px;
    selection-background-color: {ACCENT};
    selection-color: {SURFACE_1};
}}
"""
