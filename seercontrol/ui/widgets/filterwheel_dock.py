"""Filter wheel dock — compact right-rail control for the Imaging page.

The Seestar S30 Pro has an internal wheel (Dark / IR-cut / LP). This dock shows
the current filter and lets the user move to another slot manually; the
sequencer changes filters on its own from the plan.

Public surface:
    Signals
        move_requested(int)         # target slot index
    Methods (called by ImagingPage)
        set_enabled(connected: bool)
        set_filters(names: list[str])
        set_position(pos: int, name: str)   # pos == -1 → moving
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QGridLayout, QSizePolicy, QWidget

from seercontrol.ui import design, theme

logger = logging.getLogger(__name__)


class FilterWheelDock(design.Card):
    """Compact filter-wheel control group for the right side of the Imaging page."""

    move_requested = pyqtSignal(int)  # target slot index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Filter Wheel", parent)
        self._names: list[str] = []
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        status = QGridLayout()
        status.setSpacing(design.SPACING_SM)
        status.setColumnStretch(1, 1)
        self._current_lbl = design.MetricLabel("—")
        status.addWidget(design.MutedLabel("Current"), 0, 0)
        status.addWidget(self._current_lbl, 0, 1)
        outer.addLayout(status)

        outer.addWidget(design.horizontal_divider())

        self._combo = QComboBox()
        self._combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer.addWidget(self._combo)

        self._move_btn = design.PrimaryButton("▶  Move to")
        self._move_btn.setToolTip("Rotate the wheel to the selected filter")
        self._move_btn.clicked.connect(self._on_move)
        outer.addLayout(design.button_row(self._move_btn))

        self._action_widgets = [self._combo, self._move_btn]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_enabled(self, connected: bool) -> None:
        for w in self._action_widgets:
            w.setEnabled(connected)
        if not connected:
            self._current_lbl.setText("—")

    def set_filters(self, names: list[str]) -> None:
        self._names = list(names)
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(self._names)
        self._combo.blockSignals(False)

    def set_position(self, pos: int, name: str) -> None:
        if pos == -1:
            self._current_lbl.setText("Moving…")
            self._set_current_color(theme.WARNING)
            return
        self._current_lbl.setText(name)
        self._set_current_color(theme.ACCENT)
        if 0 <= pos < self._combo.count():
            self._combo.setCurrentIndex(pos)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_current_color(self, color: str) -> None:
        self._current_lbl.setStyleSheet(
            f"color:{color}; font-size:{design.FONT_SIZE_METRIC}px; font-weight:bold;"
            f" font-family:{theme.FONT_MONO}; background:transparent;"
        )

    def _on_move(self) -> None:
        idx = self._combo.currentIndex()
        if idx >= 0:
            self.move_requested.emit(idx)
