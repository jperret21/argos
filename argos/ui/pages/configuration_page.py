"""Configuration mode — software settings (observer, site, paths, appearance).

Persists everything into ``Config`` (``~/.argos/config.json``). The
observer/site fields feed the FITS headers (OBSERVER, SITELAT/LONG/ELEV, and the
AIRMASS/MOON computations) written by every frame.

Public interface (used by the Shell): just the constructor ``ConfigurationPage(config)``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from argos import __version__
from argos.core.config import Config
from argos.core.hardware import active, catalog
from argos.core.imaging.platesolve import find_astap, find_astap_db
from argos.ui import design, theme
from argos.ui.palettes import EQUILUX, PALETTES
from argos.workers.location_resolver_worker import LocationResolverWorker

logger = logging.getLogger(__name__)

_LANGUAGES = (("English", "en"), ("Français", "fr"))
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_APP_VERSION = __version__
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
        self._location_worker: LocationResolverWorker | None = None
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
        right.addWidget(self._build_telescope_card())
        right.addWidget(self._build_paths_card())
        right.addWidget(self._build_data_card())
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
        grid.addWidget(self._observer_edit, 0, 1)
        self._obscode_edit = QLineEdit()
        self._obscode_edit.setPlaceholderText("e.g. ABC")
        self._obscode_edit.setToolTip("Your AAVSO observer code — stamped on every AAVSO export")
        self._obscode_edit.editingFinished.connect(self._save_observer)
        grid.addWidget(design.MutedLabel("AAVSO code"), 0, 2)
        grid.addWidget(self._obscode_edit, 0, 3)

        self._site_name_edit = QLineEdit()
        self._site_name_edit.setPlaceholderText("Home observatory")
        self._site_name_edit.setToolTip("Name recorded with the current default observing site")
        self._site_name_edit.editingFinished.connect(self._save_site)
        grid.addWidget(design.MutedLabel("Default site"), 1, 0)
        grid.addWidget(self._site_name_edit, 1, 1, 1, 3)

        self._lat_spin = self._make_deg_spin(-90.0, 90.0)
        self._lat_spin.valueChanged.connect(self._save_site)
        self._lon_spin = self._make_deg_spin(-180.0, 180.0)
        self._lon_spin.valueChanged.connect(self._save_site)
        grid.addWidget(design.MutedLabel("Latitude"), 2, 0)
        grid.addWidget(self._lat_spin, 2, 1)
        grid.addWidget(design.MutedLabel("Longitude"), 2, 2)
        grid.addWidget(self._lon_spin, 2, 3)

        self._elev_spin = QDoubleSpinBox()
        self._elev_spin.setRange(-500.0, 9000.0)
        self._elev_spin.setDecimals(1)
        self._elev_spin.setSuffix(" m")
        self._elev_spin.valueChanged.connect(self._save_site)
        grid.addWidget(design.MutedLabel("Elevation"), 3, 0)
        grid.addWidget(self._elev_spin, 3, 1)

        self._site_search_edit = QLineEdit()
        self._site_search_edit.setPlaceholderText("Berkeley, France, Mauna Kea…")
        self._site_search_edit.setToolTip(
            "Search a place online to fill latitude, longitude and terrain elevation"
        )
        self._site_search_edit.returnPressed.connect(self._search_site)
        search_row = QHBoxLayout()
        search_row.setSpacing(design.SPACING_SM)
        search_row.addWidget(self._site_search_edit, 1)
        self._site_search_btn = design.SecondaryButton("Search")
        self._site_search_btn.clicked.connect(self._search_site)
        search_row.addWidget(self._site_search_btn)
        search_wrap = QWidget()
        search_wrap.setLayout(search_row)
        grid.addWidget(design.MutedLabel("Find location"), 4, 0)
        grid.addWidget(search_wrap, 4, 1, 1, 3)

        self._site_results_combo = QComboBox()
        self._site_results_combo.setEnabled(False)
        self._site_results_combo.setToolTip(
            "Choose the intended place before applying its coordinates"
        )
        self._apply_location_btn = design.SecondaryButton("Use selected")
        self._apply_location_btn.setEnabled(False)
        self._apply_location_btn.clicked.connect(self._apply_location_result)
        result_row = QHBoxLayout()
        result_row.setSpacing(design.SPACING_SM)
        result_row.addWidget(self._site_results_combo, 1)
        result_row.addWidget(self._apply_location_btn)
        result_wrap = QWidget()
        result_wrap.setLayout(result_row)
        grid.addWidget(design.MutedLabel("Matches"), 5, 0)
        grid.addWidget(result_wrap, 5, 1, 1, 3)

        self._site_search_status = design.MutedLabel(
            "Search is optional. Verify the terrain elevation for a permanent observatory."
        )
        self._site_search_status.setWordWrap(True)
        grid.addWidget(self._site_search_status, 6, 1, 1, 3)

        self._favorites_combo = QComboBox()
        self._favorites_combo.setEnabled(False)
        self._use_favorite_btn = design.SecondaryButton("Set default")
        self._use_favorite_btn.setEnabled(False)
        self._use_favorite_btn.clicked.connect(self._use_selected_favorite)
        self._remove_favorite_btn = design.SecondaryButton("Remove")
        self._remove_favorite_btn.setEnabled(False)
        self._remove_favorite_btn.clicked.connect(self._remove_selected_favorite)
        favorite_row = QHBoxLayout()
        favorite_row.setSpacing(design.SPACING_SM)
        favorite_row.addWidget(self._favorites_combo, 1)
        favorite_row.addWidget(self._use_favorite_btn)
        favorite_row.addWidget(self._remove_favorite_btn)
        favorite_wrap = QWidget()
        favorite_wrap.setLayout(favorite_row)
        grid.addWidget(design.MutedLabel("Saved sites"), 7, 0)
        grid.addWidget(favorite_wrap, 7, 1, 1, 3)

        self._favorite_name_edit = QLineEdit()
        self._favorite_name_edit.setPlaceholderText("Favourite name")
        self._favorite_name_edit.returnPressed.connect(self._save_current_favorite)
        self._save_favorite_btn = design.SecondaryButton("Save current")
        self._save_favorite_btn.clicked.connect(self._save_current_favorite)
        save_row = QHBoxLayout()
        save_row.setSpacing(design.SPACING_SM)
        save_row.addWidget(self._favorite_name_edit, 1)
        save_row.addWidget(self._save_favorite_btn)
        save_wrap = QWidget()
        save_wrap.setLayout(save_row)
        grid.addWidget(design.MutedLabel("Add favourite"), 8, 0)
        grid.addWidget(save_wrap, 8, 1, 1, 3)

        layout.addLayout(grid)
        layout.addWidget(
            design.MutedLabel(
                "Default site is written to every FITS header (SITELAT/LONG/ELEV) and used for "
                "airmass, Moon geometry and target visibility."
            )
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

    def _build_data_card(self) -> "design.Card":
        """Controls for the small, durable data products of an observing run."""
        card = design.Card("Local diagnostics")
        layout = design.card_layout(card)

        self._diagnostics_chk = QCheckBox("Save per-frame diagnostic records")
        self._diagnostics_chk.setToolTip(
            "Writes a compact JSONL file beside each session: exposure, mount, "
            "focus and photometry-quality measurements. Nothing is uploaded."
        )
        self._diagnostics_chk.toggled.connect(self._save_diagnostics)
        layout.addWidget(self._diagnostics_chk)
        layout.addWidget(
            design.MutedLabel(
                "Optional. Saved only in the session's diagnostics folder; no data is "
                "sent to Argos or any third party. Enable it when investigating a problem."
            )
        )
        layout.addWidget(
            design.MutedLabel(
                "Catalogue availability: CDS Sesame names and NASA exoplanet ephemerides are online "
                "on first search, then cached locally under ~/Argos/cache. AAVSO VSX/VSP field "
                "catalogues are cached under ~/.argos/cache/catalog. No catalogue refreshes or "
                "uploads happen automatically; repeat a search while online to refresh it. "
                "The optional Stellarium target-name lookup is configured in Connection."
            )
        )
        return card

    def _build_telescope_card(self) -> "design.Card":
        """Which instrument Argos is driving — the source of every hardware spec."""
        card = design.Card("Telescope")
        layout = design.card_layout(card)

        self._scope_combo = QComboBox()
        for key in catalog.keys():
            entry = catalog.PROFILES[key]
            label = entry.name if entry.validated else f"{entry.name}  (unvalidated)"
            self._scope_combo.addItem(label, key)
        self._scope_combo.currentIndexChanged.connect(self._save_telescope)

        form = QFormLayout()
        form.setHorizontalSpacing(design.SPACING_MD)
        form.setVerticalSpacing(design.SPACING_SM)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow(design.MutedLabel("Model"), self._scope_combo)
        layout.addLayout(form)

        # Specs are derived, so this line is the profile telling the truth
        # about itself rather than a second copy of the numbers.
        self._scope_specs = design.MutedLabel("")
        layout.addWidget(self._scope_specs)

        self._scope_warning = design.MutedLabel("")
        self._scope_warning.setWordWrap(True)
        self._scope_warning.setStyleSheet(f"color:{theme.WARNING};")
        layout.addWidget(self._scope_warning)

        layout.addWidget(
            design.MutedLabel(
                "Applies immediately — every spec below comes from this choice. "
                "Do not change it mid-series: the plate scale would move under "
                "a running light curve."
            )
        )
        return card

    def _refresh_telescope_card(self) -> None:
        """Show the active profile's derived specs and any caveats it carries."""
        scope = active.profile()
        idx = self._scope_combo.findData(scope.key)
        if idx >= 0:
            self._scope_combo.blockSignals(True)
            self._scope_combo.setCurrentIndex(idx)
            self._scope_combo.blockSignals(False)

        w, h = scope.fov_deg
        self._scope_specs.setText(
            f"{scope.aperture_mm:g} mm f/{scope.focal_ratio:.1f} · {scope.sensor} · "
            f"{scope.pixel_size_um:g} µm · {scope.arcsec_per_full_px:.2f}″/px · "
            f"{w:.2f}° × {h:.2f}° · {scope.bayer_pattern}"
        )

        if scope.validated:
            self._scope_warning.setText("")
            self._scope_warning.setVisible(False)
        else:
            self._scope_warning.setVisible(True)
            self._scope_warning.setText(
                "Unvalidated profile — never run on this hardware. " + " · ".join(scope.caveats)
            )

    def _save_telescope(self) -> None:
        key = self._scope_combo.currentData()
        if not key:
            return
        self._config.set(active.CFG_PROFILE, key)
        entry = catalog.get(key)
        if entry is not None:
            overrides = self._config.get(active.CFG_OVERRIDES, {})
            active.set_profile(active.apply_overrides(entry, overrides))
        self._refresh_telescope_card()

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

        db_path_row = QHBoxLayout()
        db_path_row.setSpacing(design.SPACING_SM)
        db_path_row.addWidget(design.MutedLabel("Database folder"))
        self._astap_db_edit = QLineEdit()
        self._astap_db_edit.setPlaceholderText("auto-detect (ASTAP default locations)")
        self._astap_db_edit.setToolTip(
            "Folder containing the downloaded ASTAP star databases. Leave empty "
            "to use ASTAP's normal locations."
        )
        self._astap_db_edit.editingFinished.connect(self._save_astrometry)
        db_path_row.addWidget(self._astap_db_edit, 1)
        db_browse = design.SecondaryButton("Browse…")
        db_browse.clicked.connect(self._browse_astap_database)
        db_path_row.addWidget(db_browse)
        layout.addLayout(db_path_row)

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
        form.addRow(design.MutedLabel("Database set"), self._catalog_combo)

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

        # Palette / theme preset picker
        self._palette_combo = QComboBox()
        for palette_name in PALETTES:
            self._palette_combo.addItem(palette_name)
        self._palette_combo.currentTextChanged.connect(self._save_palette)
        grid.addWidget(design.MutedLabel("Color preset"), 0, 0)
        grid.addWidget(self._palette_combo, 0, 1)

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

        # Restart notice — shown after a palette change so users know the full
        # effect requires a restart (widgets with baked-in local stylesheets
        # won't repaint live: see WS9c live-vs-restart note).
        self._palette_notice = QLabel(
            "Restart to fully apply — global colors update live, "
            "but some widgets (sidebar, status bar) take effect on next launch."
        )
        self._palette_notice.setWordWrap(True)
        self._palette_notice.setStyleSheet(
            f"color:{theme.WARNING}; font-size:11px; background:transparent;"
        )
        self._palette_notice.setVisible(False)
        layout.addWidget(self._palette_notice)

        layout.addWidget(design.MutedLabel("Language change applies after restart."))
        return card

    def _build_about_card(self) -> "design.Card":
        card = design.Card("About")
        layout = design.card_layout(card)
        layout.addWidget(design.MutedLabel("Argos — ZWO Seestar controller"))
        layout.addWidget(design.MutedLabel(f"Version {_APP_VERSION}"))
        layout.addWidget(design.MutedLabel("Science-grade acquisition · ASCOM Alpaca · FITS"))
        layout.addWidget(design.MutedLabel("GNU GPL v3 · linked against PyQt6 (GPL v3)"))
        return card

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        self._loading = True
        self._observer_edit.setText(str(self._config.get("observer.name", "") or ""))
        self._obscode_edit.setText(str(self._config.get("observer.obscode", "") or ""))
        self._site_name_edit.setText(str(self._config.get("site.name", "") or ""))
        self._lat_spin.setValue(float(self._config.get("site.latitude", 0.0) or 0.0))
        self._lon_spin.setValue(float(self._config.get("site.longitude", 0.0) or 0.0))
        self._elev_spin.setValue(float(self._config.get("site.elevation", 0.0) or 0.0))
        self._refresh_favorites()
        self._sessions_edit.setText(str(self._config.sessions_path))
        self._refresh_telescope_card()
        preset_name: str = self._config.get("ui.theme.preset", EQUILUX.name)  # type: ignore[assignment]
        idx = self._palette_combo.findText(preset_name)
        if idx >= 0:
            self._palette_combo.setCurrentIndex(idx)
        self._select_combo_data(self._lang_combo, self._config.get("ui.language", "en"))
        idx = self._log_combo.findText(self._config.get("ui.log_level", "INFO"))
        if idx >= 0:
            self._log_combo.setCurrentIndex(idx)
        self._fullwell_spin.setValue(int(self._config.get("camera.full_well_adu", 60000)))
        self._linmax_spin.setValue(int(self._config.get("camera.linearity_max_adu", 50000)))
        self._adc_spin.setValue(int(self._config.get("camera.adc_bits", 12)))
        # Astrometry
        self._astap_edit.setText(str(self._config.get("astrometry.astap_path", "") or ""))
        self._astap_db_edit.setText(str(self._config.get("astrometry.database_path", "") or ""))
        cat = str(self._config.get("astrometry.database", "") or "")
        idx = self._catalog_combo.findText(cat) if cat else 0
        self._catalog_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._radius_spin.setValue(int(self._config.get("astrometry.search_radius_deg", 30)))
        self._select_downsample(int(self._config.get("astrometry.downsample", 2)))
        self._scale_hint_chk.setChecked(bool(self._config.get("astrometry.use_scale_hint", True)))
        self._diagnostics_chk.setChecked(bool(self._config.get("diagnostics.enabled", False)))
        self._refresh_astap_status()
        self._loading = False

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _save_observer(self) -> None:
        self._config.set("observer.name", self._observer_edit.text().strip())
        self._config.set("observer.obscode", self._obscode_edit.text().strip().upper())
        self._config.save()

    def _save_site(self) -> None:
        if self._loading:
            return
        self._config.set("site.name", self._site_name_edit.text().strip())
        self._config.set("site.latitude", float(self._lat_spin.value()))
        self._config.set("site.longitude", float(self._lon_spin.value()))
        self._config.set("site.elevation", float(self._elev_spin.value()))
        self._config.save()

    def _search_site(self) -> None:
        if self._location_worker is not None:
            return
        self._site_search_edit.setEnabled(False)
        self._site_search_btn.setEnabled(False)
        self._site_search_status.setText("Searching location and terrain elevation…")
        worker = LocationResolverWorker(self._site_search_edit.text().strip(), self)
        self._location_worker = worker
        worker.resolved.connect(self._on_locations_resolved)
        worker.failed.connect(self._on_location_search_failed)
        worker.finished.connect(self._finish_location_search)
        worker.start()

    def _on_locations_resolved(self, results) -> None:
        self._site_results_combo.clear()
        for result in results:
            label = result.label
            self._site_results_combo.addItem(label, result)
            self._site_results_combo.setItemData(
                self._site_results_combo.count() - 1, label, Qt.ItemDataRole.ToolTipRole
            )
        available = self._site_results_combo.count() > 0
        self._site_results_combo.setEnabled(available)
        self._apply_location_btn.setEnabled(available)
        self._site_search_status.setText(
            "Choose a match, then use it. Elevation is terrain-modelled; edit it for a surveyed site."
        )

    def _on_location_search_failed(self, message: str) -> None:
        self._site_results_combo.clear()
        self._site_results_combo.setEnabled(False)
        self._apply_location_btn.setEnabled(False)
        self._site_search_status.setText(message)

    def _finish_location_search(self) -> None:
        self._site_search_edit.setEnabled(True)
        self._site_search_btn.setEnabled(True)
        worker = self._location_worker
        self._location_worker = None
        if worker is not None:
            worker.deleteLater()

    def _apply_location_result(self) -> None:
        result = self._site_results_combo.currentData()
        if result is None:
            return
        self._loading = True
        self._site_name_edit.setText(result.label.split(",", 1)[0])
        self._lat_spin.setValue(result.latitude)
        self._lon_spin.setValue(result.longitude)
        if result.elevation_m is not None:
            self._elev_spin.setValue(result.elevation_m)
        self._loading = False
        self._save_site()
        elevation = (
            f"{result.elevation_m:.0f} m" if result.elevation_m is not None else "not available"
        )
        self._site_search_status.setText(
            f"Default site set: {result.latitude:.5f}°, {result.longitude:.5f}°, elevation {elevation}."
        )

    def _favorites(self) -> list[dict]:
        raw = self._config.get("site.favorites", []) or []
        return [item for item in raw if isinstance(item, dict) and item.get("name")]

    def _refresh_favorites(self, selected_name: str = "") -> None:
        self._favorites_combo.blockSignals(True)
        self._favorites_combo.clear()
        for favorite in self._favorites():
            self._favorites_combo.addItem(str(favorite["name"]), favorite)
        if selected_name:
            index = self._favorites_combo.findText(selected_name)
            if index >= 0:
                self._favorites_combo.setCurrentIndex(index)
        self._favorites_combo.blockSignals(False)
        enabled = self._favorites_combo.count() > 0
        self._favorites_combo.setEnabled(enabled)
        self._use_favorite_btn.setEnabled(enabled)
        self._remove_favorite_btn.setEnabled(enabled)

    def _save_current_favorite(self) -> None:
        name = self._favorite_name_edit.text().strip() or self._site_name_edit.text().strip()
        if not name:
            self._site_search_status.setText("Name the site before saving it as a favourite.")
            return
        favorite = {
            "name": name,
            "latitude": float(self._lat_spin.value()),
            "longitude": float(self._lon_spin.value()),
            "elevation": float(self._elev_spin.value()),
        }
        favorites = [
            item for item in self._favorites() if str(item["name"]).casefold() != name.casefold()
        ]
        favorites.append(favorite)
        self._config.set("site.favorites", favorites)
        self._refresh_favorites(name)
        self._favorite_name_edit.clear()
        self._site_search_status.setText(f"Saved favourite site: {name}.")

    def _use_selected_favorite(self) -> None:
        favorite = self._favorites_combo.currentData()
        if not isinstance(favorite, dict):
            return
        self._loading = True
        self._site_name_edit.setText(str(favorite["name"]))
        self._lat_spin.setValue(float(favorite["latitude"]))
        self._lon_spin.setValue(float(favorite["longitude"]))
        self._elev_spin.setValue(float(favorite["elevation"]))
        self._loading = False
        self._save_site()
        self._site_search_status.setText(f"Default site set to saved site: {favorite['name']}.")

    def _remove_selected_favorite(self) -> None:
        favorite = self._favorites_combo.currentData()
        if not isinstance(favorite, dict):
            return
        name = str(favorite["name"])
        self._config.set(
            "site.favorites",
            [item for item in self._favorites() if str(item["name"]).casefold() != name.casefold()],
        )
        self._refresh_favorites()
        self._site_search_status.setText(f"Removed saved site: {name}.")

    def shutdown(self) -> None:
        """Let an in-flight public geocoding request finish before Qt teardown."""
        if self._location_worker is not None:
            self._location_worker.wait(9000)  # both requests use an 8 second timeout
            self._location_worker = None

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
        self._config.set("astrometry.database_path", self._astap_db_edit.text().strip())
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

    def _browse_astap_database(self) -> None:
        start = self._astap_db_edit.text().strip() or "/"
        chosen = QFileDialog.getExistingDirectory(self, "Locate ASTAP star databases", start)
        if chosen:
            self._astap_db_edit.setText(chosen)
            self._save_astrometry()

    def _save_diagnostics(self, enabled: bool) -> None:
        if self._loading:
            return
        # Existing configs predate the privacy-first opt-in policy.  Mark the
        # user's first interaction so the migration never overrides it again.
        self._config.set("diagnostics.local_opt_in_v1", True)
        self._config.set("diagnostics.enabled", bool(enabled))

    def _refresh_astap_status(self) -> None:
        found = find_astap(self._astap_edit.text().strip())
        if found:
            configured_db = self._astap_db_edit.text().strip()
            if configured_db:
                folder = Path(configured_db).expanduser()
                contains_database = folder.is_dir() and any(
                    any(folder.glob(pattern)) for pattern in ("*.1476", "*.290", "*.101")
                )
                database = (
                    f" · Star database: {folder}"
                    if contains_database
                    else f" · Star database not found in: {folder}"
                )
            else:
                detected_db = find_astap_db(found)
                database = (
                    f" · Star database: {detected_db}"
                    if detected_db
                    else " · Star database not detected"
                )
            self._astap_status.setText(f"✓ ASTAP detected: {found}{database}")
        else:
            self._astap_status.setText("✗ ASTAP not found — install it or set the path above")

    def _save_palette(self, preset_name: str) -> None:
        """Apply *preset_name* live (best-effort) and persist it in config.

        Live-vs-restart behaviour
        -------------------------
        - **Live (immediate)**: the global QSS is regenerated and applied via
          ``QApplication.setStyleSheet``.  All QSS-driven colors (backgrounds,
          buttons, inputs, labels, dock headers from the global sheet, …) update
          immediately.
        - **On restart only**: widgets that captured a color string in a local
          ``setStyleSheet`` call *at construction time* — the dock_host
          ``_DOCK_QSS`` f-string, sidebar icon cache, statusbar self-stylesheet —
          are not retroactively repainted by a global QSS change.  They take the
          new palette on the next application launch.
        """
        if self._loading:
            return
        palette = PALETTES.get(preset_name, EQUILUX)
        theme.apply_palette(palette)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.get_stylesheet())
        self._config.set("ui.theme.preset", preset_name)
        self._config.save()
        self._palette_notice.setVisible(True)

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
