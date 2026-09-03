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
from PyQt6.QtWidgets import QDockWidget, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from argos.ui import design, theme


#: All docks share this hairline-bordered, small-title look.  This must be a
#: function (not a module-level f-string): the theme palette is selected after
#: the UI modules are imported during application startup.
def _dock_qss() -> str:
    return f"""
QDockWidget {{
    color: {theme.FG};
    font-size: {design.FONT_SIZE_SMALL}px;
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
    dock.setStyleSheet(_dock_qss())

    # The dock title is already the panel's visible heading.  Most Imaging
    # controls are Cards too; keeping their QGroupBox title produced a second
    # heading (``Focusing`` / ``Focuser``, ``Acquisition`` / ``Camera``) and a
    # second layer of padding.  Preserve the card frame, but make dock content
    # use the compact panel inset.
    if isinstance(content, design.Card):
        content.setTitle("")
        if content.layout() is not None:
            content.layout().setContentsMargins(
                design.SPACING_MD,
                design.SPACING_SM,
                design.SPACING_MD,
                design.SPACING_SM,
            )

    if scroll:
        policy = content.sizePolicy()
        content.setSizePolicy(policy.horizontalPolicy(), QSizePolicy.Policy.Maximum)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(
            design.SPACING_MD, design.SPACING_MD, design.SPACING_MD, design.SPACING_MD
        )
        layout.setSpacing(design.SPACING_MD)
        layout.addWidget(content, 0, Qt.AlignmentFlag.AlignTop)
        # A control panel should keep its natural height.  The dock's spare
        # room belongs below it; when the dock is shorter, QScrollArea still
        # uses the inner widget's size hint and supplies vertical scrolling.
        layout.addStretch(1)

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


def panel_toolbar_qss() -> str:
    """Return the shared, neutral toolbar treatment for dock workspaces.

    A visible dock is not an active command.  Styling every checked
    ``toggleViewAction`` with the primary accent made a normal default layout
    look as if every control were simultaneously selected.  Keep these buttons
    neutral; reserve Argos brass for focus, deliberate actions and real state.
    Menu arrows are rendered as text by the caller, avoiding platform-native
    indicators which were vertically misplaced on compact toolbars.
    """
    return f"""
QToolBar {{
    background-color: {theme.SURFACE_3};
    border-bottom: 1px solid {theme.SURFACE_4};
    padding: 3px 6px;
    spacing: 5px;
}}
QToolBar QToolButton {{
    color: {theme.FG_MUTED};
    background: transparent;
    border: 1px solid {theme.BORDER_SOFT};
    border-radius: 2px;
    min-height: 26px;
    padding: 2px 10px;
    font-family: {theme.FONT_UI};
    font-size: 12px;
}}
QToolBar QToolButton:hover {{
    color: {theme.FG};
    background-color: {theme.SURFACE};
    border-color: {theme.BORDER};
}}
QToolBar QToolButton:checked {{
    color: {theme.FG};
    background-color: {theme.SURFACE};
    border-color: {theme.BORDER};
}}
QToolBar QToolButton::menu-indicator {{
    image: none;
    width: 0;
}}
QToolBar::separator {{
    width: 1px;
    background-color: {theme.BORDER};
    margin: 5px 6px;
}}
"""
