"""Target mode — placeholder during R1. Real implementation lands in R4."""

from __future__ import annotations

from seercontrol.ui.pages._placeholder import PlaceholderPage


class TargetPage(PlaceholderPage):
    def __init__(self) -> None:
        super().__init__("Target", sprint_name="R4")
