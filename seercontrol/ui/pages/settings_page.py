"""Settings mode — placeholder during R1. Real implementation lands in R5."""

from __future__ import annotations

from seercontrol.ui.pages._placeholder import PlaceholderPage


class SettingsPage(PlaceholderPage):
    def __init__(self) -> None:
        super().__init__("Settings", sprint_name="R5")
