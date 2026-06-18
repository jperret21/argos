"""Slim overlay-toggle bar under the image toolbar (docs/photometry_plan.md §5 B1).

Checkable chips — Grid · Stars · Variables · Comparisons · Targets — that show/hide
the matching viewer layers. Chips are disabled until their data exists (a solve for
Grid; a catalog fetch for Variables/Comparisons; a saved target for Targets).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from argos.ui import theme

#: chip name → human label
_CHIPS = (
    ("grid", "Grid"),
    ("stars", "Stars"),
    ("variables", "Variables"),
    ("comparisons", "Comparisons"),
    ("targets", "Targets"),
)


class OverlayBar(QWidget):
    """A row of checkable overlay chips; emits ``toggled(name, on)``."""

    toggled = pyqtSignal(str, bool)  # chip name, checked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {theme.SURFACE_3}; border-bottom: 1px solid {theme.SURFACE_4};"
        )
        self.setMaximumHeight(34)
        self._chips: dict[str, QPushButton] = {}
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(6)
        lbl = QLabel("Overlays:")
        lbl.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px; background:transparent;")
        row.addWidget(lbl)
        for name, text in _CHIPS:
            chip = QPushButton(text)
            chip.setCheckable(True)
            chip.setEnabled(False)  # armed once its data exists
            chip.setStyleSheet("font-size: 11px; padding: 1px 8px;")
            chip.toggled.connect(lambda on, n=name: self.toggled.emit(n, on))
            self._chips[name] = chip
            row.addWidget(chip)
        row.addStretch()

    def set_available(self, name: str, available: bool) -> None:
        chip = self._chips.get(name)
        if chip is not None:
            chip.setEnabled(bool(available))

    def set_checked(self, name: str, checked: bool) -> None:
        chip = self._chips.get(name)
        if chip is not None:
            chip.blockSignals(True)
            chip.setChecked(bool(checked))
            chip.blockSignals(False)

    def is_checked(self, name: str) -> bool:
        chip = self._chips.get(name)
        return bool(chip and chip.isChecked())
