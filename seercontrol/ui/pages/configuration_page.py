"""Configuration mode — software settings (observer, site, paths, appearance).

Persists everything into ``Config`` (``~/.seercontrol/config.json``). The
observer/site fields feed the FITS headers (OBSERVER, SITELAT/LONG/ELEV, and the
AIRMASS/MOON computations) written by every frame.

Public interface (used by the Shell): just the constructor ``ConfigurationPage(config)``.
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.config import Config
from seercontrol.ui import design

logger = logging.getLogger(__name__)

_LANGUAGES = (("English", "en"), ("Français", "fr"))
_THEMES = (("Dark", "dark"),)
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_APP_VERSION = "0.2.0-redesign"


class ConfigurationPage(QWidget):
    """Settings page. Each field writes straight back into ``Config``."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll, body = design.scroll_page(max_width=940)
        root.addWidget(scroll)

        body.addWidget(design.HeadingLabel("Configuration"))

        # Two responsive columns: observer/site on the left, the rest stacked
        # on the right. Both columns share width 1:1 and reflow on resize.
        row, left, right = design.two_columns()
        left.addWidget(self._build_observer_card())
        left.addStretch()
        right.addWidget(self._build_paths_card())
        right.addWidget(self._build_appearance_card())
        right.addWidget(self._build_about_card())
        right.addStretch()
        body.addLayout(row)
        body.addStretch()

    def _build_observer_card(self) -> "design.Card":
        card = design.Card("Observer & Site")
        layout = design.card_layout(card)

        grid = QGridLayout()
        grid.setHorizontalSpacing(design.SPACING_MD)
        grid.setVerticalSpacing(design.SPACING_SM)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._observer_edit = QLineEdit()
        self._observer_edit.editingFinished.connect(self._save_observer)
        grid.addWidget(design.MutedLabel("Observer"), 0, 0)
        grid.addWidget(self._observer_edit, 0, 1, 1, 3)

        self._lat_spin = self._make_deg_spin(-90.0, 90.0)
        self._lat_spin.valueChanged.connect(self._save_site)
        self._lon_spin = self._make_deg_spin(-180.0, 180.0)
        self._lon_spin.valueChanged.connect(self._save_site)
        grid.addWidget(design.MutedLabel("Latitude"), 1, 0)
        grid.addWidget(self._lat_spin, 1, 1)
        grid.addWidget(design.MutedLabel("Longitude"), 1, 2)
        grid.addWidget(self._lon_spin, 1, 3)

        self._elev_spin = QDoubleSpinBox()
        self._elev_spin.setRange(-500.0, 9000.0)
        self._elev_spin.setDecimals(1)
        self._elev_spin.setSuffix(" m")
        self._elev_spin.valueChanged.connect(self._save_site)
        grid.addWidget(design.MutedLabel("Elevation"), 2, 0)
        grid.addWidget(self._elev_spin, 2, 1)

        layout.addLayout(grid)
        layout.addWidget(
            design.MutedLabel("Written to every FITS header (OBSERVER, SITELAT/LONG/ELEV).")
        )
        return card

    @staticmethod
    def _make_deg_spin(low: float, high: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(5)
        spin.setSuffix(" °")
        return spin

    def _build_paths_card(self) -> "design.Card":
        card = design.Card("Paths")
        layout = design.card_layout(card)

        row = QHBoxLayout()
        row.setSpacing(design.SPACING_MD)
        row.addWidget(design.MutedLabel("Sessions"))
        self._sessions_edit = QLineEdit()
        self._sessions_edit.editingFinished.connect(self._save_sessions_path)
        row.addWidget(self._sessions_edit, 1)
        browse = design.PrimaryButton("Browse…")
        browse.clicked.connect(self._browse_sessions_path)
        row.addWidget(browse)
        layout.addLayout(row)
        return card

    def _build_appearance_card(self) -> "design.Card":
        card = design.Card("Appearance")
        layout = design.card_layout(card)

        grid = QGridLayout()
        grid.setHorizontalSpacing(design.SPACING_MD)
        grid.setVerticalSpacing(design.SPACING_SM)
        grid.setColumnStretch(1, 1)

        self._theme_combo = QComboBox()
        for label, value in _THEMES:
            self._theme_combo.addItem(label, value)
        grid.addWidget(design.MutedLabel("Theme"), 0, 0)
        grid.addWidget(self._theme_combo, 0, 1)

        self._lang_combo = QComboBox()
        for label, value in _LANGUAGES:
            self._lang_combo.addItem(label, value)
        self._lang_combo.currentIndexChanged.connect(self._save_language)
        grid.addWidget(design.MutedLabel("Language"), 1, 0)
        grid.addWidget(self._lang_combo, 1, 1)

        self._log_combo = QComboBox()
        for level in _LOG_LEVELS:
            self._log_combo.addItem(level)
        self._log_combo.currentTextChanged.connect(self._save_log_level)
        grid.addWidget(design.MutedLabel("Log level"), 2, 0)
        grid.addWidget(self._log_combo, 2, 1)

        layout.addLayout(grid)
        layout.addWidget(design.MutedLabel("Language change applies after restart."))
        return card

    def _build_about_card(self) -> "design.Card":
        card = design.Card("About")
        layout = design.card_layout(card)
        layout.addWidget(design.MutedLabel("SeerControl — ZWO Seestar S30 Pro controller"))
        layout.addWidget(design.MutedLabel(f"Version {_APP_VERSION}"))
        layout.addWidget(design.MutedLabel("Science-grade acquisition · ASCOM Alpaca · FITS"))
        return card

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        self._observer_edit.setText(str(self._config.get("observer.name", "") or ""))
        self._lat_spin.setValue(float(self._config.get("site.latitude", 0.0) or 0.0))
        self._lon_spin.setValue(float(self._config.get("site.longitude", 0.0) or 0.0))
        self._elev_spin.setValue(float(self._config.get("site.elevation", 0.0) or 0.0))
        self._sessions_edit.setText(str(self._config.sessions_path))
        self._select_combo_data(self._theme_combo, self._config.get("ui.theme", "dark"))
        self._select_combo_data(self._lang_combo, self._config.get("ui.language", "en"))
        idx = self._log_combo.findText(self._config.get("ui.log_level", "INFO"))
        if idx >= 0:
            self._log_combo.setCurrentIndex(idx)

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _save_observer(self) -> None:
        self._config.set("observer.name", self._observer_edit.text().strip())
        self._config.save()

    def _save_site(self) -> None:
        self._config.set("site.latitude", float(self._lat_spin.value()))
        self._config.set("site.longitude", float(self._lon_spin.value()))
        self._config.set("site.elevation", float(self._elev_spin.value()))
        self._config.save()

    def _save_sessions_path(self) -> None:
        text = self._sessions_edit.text().strip()
        if text:
            self._config.sessions_path = text
            self._config.save()

    def _browse_sessions_path(self) -> None:
        start = str(self._config.sessions_path)
        chosen = QFileDialog.getExistingDirectory(self, "Choose sessions folder", start)
        if chosen:
            self._sessions_edit.setText(chosen)
            self._config.sessions_path = chosen
            self._config.save()

    def _save_language(self) -> None:
        self._config.set("ui.language", self._lang_combo.currentData())
        self._config.save()

    def _save_log_level(self, level: str) -> None:
        self._config.set("ui.log_level", level)
        self._config.save()
