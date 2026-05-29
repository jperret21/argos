"""Equipment mode — placeholder during R1. Real implementation lands in R3."""

from __future__ import annotations

from seercontrol.ui.pages._placeholder import PlaceholderPage


class EquipmentPage(PlaceholderPage):
    def __init__(self) -> None:
        super().__init__("Equipment", sprint_name="R3")
