"""Themed :class:`QDockWidget` factory for the dockable Imaging workspace (WS9a).

NINA-inspired docking: every control panel becomes a real ``QDockWidget`` the
user can move, resize, close and float to a second monitor. This module keeps
the title bars consistent — a small title, a hairline border, the equilux
palette — so the docks read as one sober cockpit rather than a pile of windows.

``make_dock`` wraps a content widget in a scroll area (so a stacked rail of
Fixed-height cards scrolls instead of stretching) and returns a styled dock.
``style_toggle_action`` restyles the toolbar chips driven by
``QDockWidget.toggleViewAction()`` (which — unlike ``visibilityChanged`` — is
already immune to tab-switch spurious toggles).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDockWidget, QScrollArea, QVBoxLayout, QWidget

from argos.ui import design, theme

#: All docks share this hairline-bordered, small-title look.
_DOCK_QSS = f"""
QDockWidget {{
    color: {theme.FG};
    font-size: {design.FONT_SIZE_SMALL}px;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: {theme.SURFACE_3};
    color: {theme.FG_MUTED};
    padding: 3px 8px;
    border-bottom: 1px solid {theme.BORDER};
    text-align: left;
}}
QDockWidget > QWidget {{
    background-color: {theme.BG};
    border: 1px solid {theme.BORDER};
    border-top: none;
}}
"""


def make_dock(
    title: str,
    content: QWidget,
    *,
    object_name: str,
    scroll: bool = True,
    features: QDockWidget.DockWidgetFeature | None = None,
) -> QDockWidget:
    """Wrap ``content`` in a themed, movable/closable/floatable dock.

    ``object_name`` is required — ``QMainWindow.saveState()``/``restoreState()``
    identify docks by it, so it must be stable across launches.

    When ``scroll`` is true the content is placed in a top-aligned, no-frame
    scroll area (the right-rail control cards keep their natural height and the
    dock scrolls if shorter than the stack). Wide panels that manage their own
    scrolling (Sequence, Log) pass ``scroll=False``.
    """
    dock = QDockWidget(title)
    dock.setObjectName(object_name)
    if features is None:
        features = (
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
    dock.setFeatures(features)
    dock.setStyleSheet(_DOCK_QSS)

    if scroll:
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(
            design.SPACING_MD, design.SPACING_MD, design.SPACING_MD, design.SPACING_MD
        )
        layout.setSpacing(design.SPACING_MD)
        layout.addWidget(content)
        # No addStretch(): stretch fights scroll when dock < content

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(inner)
        dock.setWidget(area)
    else:
        dock.setWidget(content)
    return dock


#: Chip look for the panel-toggle strip — matches the OverlayBar chips.
_TOGGLE_QSS = "font-size: 11px; padding: 1px 8px;"


def style_toggle_action(action: QAction, label: str) -> QAction:
    """Restyle a dock's ``toggleViewAction()`` for the panel-toggle toolbar.

    ``toggleViewAction()`` already keeps the checkbox in sync with the dock's
    real visibility (and, unlike ``visibilityChanged``, does not fire on tab
    switches). We only override the label so the strip reads compactly.
    """
    action.setText(label)
    action.setCheckable(True)
    return action
