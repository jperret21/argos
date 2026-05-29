"""Imaging mode — placeholder during R1. Real implementation lands in R2."""

from __future__ import annotations

from seercontrol.ui.pages._placeholder import PlaceholderPage


class ImagingPage(PlaceholderPage):
    def __init__(self) -> None:
        super().__init__("Imaging", sprint_name="R2 (next)")
