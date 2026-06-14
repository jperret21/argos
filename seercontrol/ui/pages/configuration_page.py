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
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(
            design.SPACING_XL, design.SPACING_XL, design.SPACING_XL, design.SPACING_XL
        )
        layout.setSpacing(design.SPACING_LG)

        layout.addWidget(design.HeadingLabel("Configuration"))
        layout.addWidget(self._build_observer_card())
        layout.addWidget(self._build_paths_card())
        layout.addWidget(self._build_appearance_card())
        layout.addWidget(self._build_about_card())
        layout.addStretch()
        scroll.setWidget(inner)

    def _build_observer_card(self) -> "design.Card":
        card = design.Card("Observer & Site")
        layout = design.card_layout(card)
        form = QFormLayout()
        form.setHorizontalSpacing(design.SPACING_MD)
        form.setVerticalSpacing(design.SPACING_SM)

        self._observer_edit = QLineEdit()
        self._observer_edit.editingFinished.connect(self._save_observer)
        form.addRow(design.MutedLabel("Observer"), self._observer_edit)

        self._lat_spin = QDoubleSpinBox()
        self._lat_spin.setRange(-90.0, 90.0)
        self._lat_spin.setDecimals(5)
        self._lat_spin.setSuffix(" °")
        self._lat_spin.valueChanged.connect(self._save_site)
        form.addRow(design.MutedLabel("Latitude"), self._lat_spin)

        self._lon_spin = QDoubleSpinBox()
        self._lon_spin.setRange(-180.0, 180.0)
        self._lon_spin.setDecimals(5)
        self._lon_spin.setSuffix(" °")
        self._lon_spin.valueChanged.connect(self._save_site)
        form.addRow(design.MutedLabel("Longitude"), self._lon_spin)

        self._elev_spin = QDoubleSpinBox()
        self._elev_spin.setRange(-500.0, 9000.0)
        self._elev_spin.setDecimals(1)
        self._elev_spin.setSuffix(" m")
        self._elev_spin.valueChanged.connect(self._save_site)
        form.addRow(design.MutedLabel("Elevation"), self._elev_spin)

        layout.addLayout(form)
        return card

    def _build_paths_card(self) -> "design.Card":
        card = design.Card("Paths")
        layout = design.card_layout(card)

        row = QHBoxLayout()
        row.setSpacing(design.SPACING_MD)
        self._sessions_edit = QLineEdit()
        self._sessions_edit.editingFinished.connect(self._save_sessions_path)
        row.addWidget(design.MutedLabel("Sessions"))
        row.addWidget(self._sessions_edit, 1)
        browse = design.PrimaryButton("Browse…")
        browse.clicked.connect(self._browse_sessions_path)
        row.addWidget(browse)
        layout.addLayout(row)
        return card

    def _build_appearance_card(self) -> "design.Card":
        card = design.Card("Appearance")
        layout = design.card_layout(card)
        form = QFormLayout()
        form.setHorizontalSpacing(design.SPACING_MD)
        form.setVerticalSpacing(design.SPACING_SM)

        self._theme_combo = QComboBox()
        for label, value in _THEMES:
            self._theme_combo.addItem(label, value)
        form.addRow(design.MutedLabel("Theme"), self._theme_combo)

        self._lang_combo = QComboBox()
        for label, value in _LANGUAGES:
            self._lang_combo.addItem(label, value)
        self._lang_combo.currentIndexChanged.connect(self._save_language)
        form.addRow(design.MutedLabel("Language"), self._lang_combo)

        self._log_combo = QComboBox()
        for level in _LOG_LEVELS:
            self._log_combo.addItem(level)
        self._log_combo.currentTextChanged.connect(self._save_log_level)
        form.addRow(design.MutedLabel("Log level"), self._log_combo)

        layout.addLayout(form)
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
