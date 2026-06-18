"""Configuration mode — software settings (observer, site, paths, appearance).

Persists everything into ``Config`` (``~/.argos/config.json``). The
observer/site fields feed the FITS headers (OBSERVER, SITELAT/LONG/ELEV, and the
AIRMASS/MOON computations) written by every frame.

Public interface (used by the Shell): just the constructor ``ConfigurationPage(config)``.
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from argos.core.config import Config
from argos.core.imaging.platesolve import find_astap
from argos.ui import design

logger = logging.getLogger(__name__)

_LANGUAGES = (("English", "en"), ("Français", "fr"))
_THEMES = (("Dark", "dark"),)
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_APP_VERSION = "0.2.0-redesign"
#: ASTAP star databases (FOV-dependent). "" = let ASTAP auto-pick.
_ASTAP_DATABASES = ("Auto", "D05", "D20", "D50", "D80", "G17", "H17", "H18", "V17", "W08")
#: Downsample options (label → ASTAP -z value; 0 = auto).
_DOWNSAMPLE = (("Auto", 0), ("1×", 1), ("2×", 2), ("3×", 3), ("4×", 4))


class ConfigurationPage(QWidget):
    """Settings page. Each field writes straight back into ``Config``."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._loading = False  # guards _save_* while populating fields
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
        left.addWidget(self._build_astrometry_card())
        left.addStretch()
        right.addWidget(self._build_paths_card())
        right.addWidget(self._build_camera_card())
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

    def _build_camera_card(self) -> "design.Card":
        card = design.Card("Camera")
        layout = design.card_layout(card)
        form = QFormLayout()
        form.setHorizontalSpacing(design.SPACING_MD)
        form.setVerticalSpacing(design.SPACING_SM)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._fullwell_spin = QSpinBox()
        self._fullwell_spin.setRange(0, 65535)
        self._fullwell_spin.setSingleStep(1000)
        self._fullwell_spin.valueChanged.connect(self._save_camera)
        form.addRow(design.MutedLabel("Full-well (ADU)"), self._fullwell_spin)

        self._linmax_spin = QSpinBox()
        self._linmax_spin.setRange(0, 65535)
        self._linmax_spin.setSingleStep(1000)
        self._linmax_spin.valueChanged.connect(self._save_camera)
        form.addRow(design.MutedLabel("Linearity max (ADU)"), self._linmax_spin)

        self._adc_spin = QSpinBox()
        self._adc_spin.setRange(8, 16)
        self._adc_spin.valueChanged.connect(self._save_camera)
        form.addRow(design.MutedLabel("ADC bits"), self._adc_spin)

        layout.addLayout(form)
        layout.addWidget(
            design.MutedLabel("Full-well = the saturation/clipping threshold (Display tab).")
        )
        return card

    def _build_astrometry_card(self) -> "design.Card":
        card = design.Card("Astrometry (plate solving)")
        layout = design.card_layout(card)

        # ASTAP binary path + Browse, with a live "detected/not found" status.
        path_row = QHBoxLayout()
        path_row.setSpacing(design.SPACING_SM)
        path_row.addWidget(design.MutedLabel("ASTAP"))
        self._astap_edit = QLineEdit()
        self._astap_edit.setPlaceholderText("auto-detect (astap_cli on PATH)")
        self._astap_edit.editingFinished.connect(self._save_astrometry)
        path_row.addWidget(self._astap_edit, 1)
        browse = design.SecondaryButton("Browse…")
        browse.clicked.connect(self._browse_astap)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        self._astap_status = design.MutedLabel("")
        layout.addWidget(self._astap_status)

        form = QFormLayout()
        form.setHorizontalSpacing(design.SPACING_MD)
        form.setVerticalSpacing(design.SPACING_SM)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._catalog_combo = QComboBox()
        self._catalog_combo.addItems(_ASTAP_DATABASES)
        self._catalog_combo.setToolTip(
            "Star database ASTAP matches against. 'Auto' lets ASTAP pick by field\n"
            "of view (recommended). For the Seestar's ~1° field, D50/D80 or V17 fit."
        )
        self._catalog_combo.currentTextChanged.connect(self._save_astrometry)
        form.addRow(design.MutedLabel("Catalog"), self._catalog_combo)

        self._radius_spin = QSpinBox()
        self._radius_spin.setRange(0, 180)
        self._radius_spin.setSuffix(" °")
        self._radius_spin.setToolTip("Search radius around the hint (0 = blind, whole sky).")
        self._radius_spin.valueChanged.connect(self._save_astrometry)
        form.addRow(design.MutedLabel("Search radius"), self._radius_spin)

        self._downsample_combo = QComboBox()
        for label, _v in _DOWNSAMPLE:
            self._downsample_combo.addItem(label)
        self._downsample_combo.currentTextChanged.connect(self._save_astrometry)
        form.addRow(design.MutedLabel("Downsample"), self._downsample_combo)

        layout.addLayout(form)

        self._scale_hint_chk = QCheckBox("Use the known plate scale as a hint (faster solve)")
        self._scale_hint_chk.toggled.connect(self._save_astrometry)
        layout.addWidget(self._scale_hint_chk)

        layout.addWidget(
            design.MutedLabel(
                "Solving runs on the green channel. Install ASTAP + a star database from "
                "hnsky.org/astap.htm, then 'Solve' from a loaded FITS."
            )
        )
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
        layout.addWidget(design.MutedLabel("Argos — ZWO Seestar S30 Pro controller"))
        layout.addWidget(design.MutedLabel(f"Version {_APP_VERSION}"))
        layout.addWidget(design.MutedLabel("Science-grade acquisition · ASCOM Alpaca · FITS"))
        return card

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        self._loading = True
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
        self._fullwell_spin.setValue(int(self._config.get("camera.full_well_adu", 60000)))
        self._linmax_spin.setValue(int(self._config.get("camera.linearity_max_adu", 50000)))
        self._adc_spin.setValue(int(self._config.get("camera.adc_bits", 12)))
        # Astrometry
        self._astap_edit.setText(str(self._config.get("astrometry.astap_path", "") or ""))
        cat = str(self._config.get("astrometry.database", "") or "")
        idx = self._catalog_combo.findText(cat) if cat else 0
        self._catalog_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._radius_spin.setValue(int(self._config.get("astrometry.search_radius_deg", 30)))
        self._select_downsample(int(self._config.get("astrometry.downsample", 2)))
        self._scale_hint_chk.setChecked(bool(self._config.get("astrometry.use_scale_hint", True)))
        self._refresh_astap_status()
        self._loading = False

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _save_observer(self) -> None:
        self._config.set("observer.name", self._observer_edit.text().strip())
        self._config.save()

    def _save_site(self) -> None:
        if self._loading:
            return
        self._config.set("site.latitude", float(self._lat_spin.value()))
        self._config.set("site.longitude", float(self._lon_spin.value()))
        self._config.set("site.elevation", float(self._elev_spin.value()))
        self._config.save()

    def _save_camera(self) -> None:
        if self._loading:
            return
        self._config.set("camera.full_well_adu", int(self._fullwell_spin.value()))
        self._config.set("camera.linearity_max_adu", int(self._linmax_spin.value()))
        self._config.set("camera.adc_bits", int(self._adc_spin.value()))
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

    def _select_downsample(self, value: int) -> None:
        for i, (_label, v) in enumerate(_DOWNSAMPLE):
            if v == value:
                self._downsample_combo.setCurrentIndex(i)
                return
        self._downsample_combo.setCurrentIndex(0)

    def _save_astrometry(self) -> None:
        if self._loading:
            return
        cat = self._catalog_combo.currentText()
        self._config.set("astrometry.astap_path", self._astap_edit.text().strip())
        self._config.set("astrometry.database", "" if cat == "Auto" else cat)
        self._config.set("astrometry.search_radius_deg", int(self._radius_spin.value()))
        self._config.set(
            "astrometry.downsample", _DOWNSAMPLE[self._downsample_combo.currentIndex()][1]
        )
        self._config.set("astrometry.use_scale_hint", self._scale_hint_chk.isChecked())
        self._config.save()
        self._refresh_astap_status()

    def _browse_astap(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Locate the ASTAP executable", "/")
        if chosen:
            self._astap_edit.setText(chosen)
            self._save_astrometry()

    def _refresh_astap_status(self) -> None:
        found = find_astap(self._astap_edit.text().strip())
        if found:
            self._astap_status.setText(f"✓ ASTAP detected: {found}")
        else:
            self._astap_status.setText("✗ ASTAP not found — install it or set the path above")

    def _save_language(self) -> None:
        if self._loading:
            return
        self._config.set("ui.language", self._lang_combo.currentData())
        self._config.save()

    def _save_log_level(self, level: str) -> None:
        if self._loading:
            return
        self._config.set("ui.log_level", level)
        self._config.save()
