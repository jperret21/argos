"""Astrometry + catalog settings — a popup to tune solving & catalog queries.

A convenience dialog launched from the analysis window so the user can adjust the
plate-solve and AAVSO-catalog parameters without leaving the frame. It reads and
writes the **same config keys** as the main Configuration page, so the two stay
in sync. On save it emits :attr:`saved` — the window re-queries the catalog when a
solution already exists, so changes (e.g. a brighter magnitude limit) apply live.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

# Single source of truth for the DB list + downsample options (shared with the
# main Configuration page).
from seercontrol.ui.pages.configuration_page import _ASTAP_DATABASES, _DOWNSAMPLE


class AstrometrySettingsDialog(QDialog):
    """Edit astrometry + catalog settings; persist to the shared config.

    Signals:
        saved(): emitted after the settings are written, so callers can re-apply.
    """

    saved = pyqtSignal()

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Astrometry & catalog settings")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_astrometry_group())
        layout.addWidget(self._build_catalog_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    # ------------------------------------------------------------------

    def _build_astrometry_group(self) -> QGroupBox:
        box = QGroupBox("Plate solving (ASTAP)")
        form = QFormLayout(box)

        self._astap_edit = QLineEdit()
        self._astap_edit.setPlaceholderText("auto-detect (astap_cli / astap on PATH)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_astap)
        path_row = QHBoxLayout()
        path_row.addWidget(self._astap_edit, 1)
        path_row.addWidget(browse)
        form.addRow("ASTAP binary", path_row)

        self._db_combo = QComboBox()
        self._db_combo.addItems(_ASTAP_DATABASES)
        form.addRow("Star database", self._db_combo)

        self._radius_spin = QSpinBox()
        self._radius_spin.setRange(0, 180)
        self._radius_spin.setSuffix("°")
        self._radius_spin.setToolTip("Search radius around the pointing hint (0 = whole-sky blind)")
        form.addRow("Search radius", self._radius_spin)

        self._down_combo = QComboBox()
        for label, _v in _DOWNSAMPLE:
            self._down_combo.addItem(label)
        form.addRow("Downsample", self._down_combo)

        self._grid_spin = QSpinBox()
        self._grid_spin.setRange(0, 120)
        self._grid_spin.setSuffix("′")
        self._grid_spin.setToolTip("RA/Dec grid spacing in arcminutes (0 = auto, adaptive)")
        form.addRow("Grid spacing", self._grid_spin)

        self._scale_hint_chk = QCheckBox("Use the camera scale as a field-of-view hint")
        form.addRow("", self._scale_hint_chk)
        return box

    def _build_catalog_group(self) -> QGroupBox:
        box = QGroupBox("AAVSO catalog (VSX / VSP)")
        form = QFormLayout(box)

        self._mag_spin = QDoubleSpinBox()
        self._mag_spin.setRange(5.0, 20.0)
        self._mag_spin.setSingleStep(0.5)
        self._mag_spin.setDecimals(1)
        self._mag_spin.setToolTip("Drop catalog objects fainter than this (a dense field is huge)")
        form.addRow("Magnitude limit", self._mag_spin)

        self._max_spin = QSpinBox()
        self._max_spin.setRange(10, 2000)
        self._max_spin.setSingleStep(10)
        self._max_spin.setToolTip("Cap on variable stars drawn (brightest kept)")
        form.addRow("Max variables", self._max_spin)

        self._suspected_chk = QCheckBox("Include suspected variables")
        form.addRow("", self._suspected_chk)
        return box

    # ------------------------------------------------------------------

    def _g(self, key: str, default):
        value = self._config.get(key, default) if self._config is not None else default
        return default if value is None else value

    def _load(self) -> None:
        self._astap_edit.setText(str(self._g("astrometry.astap_path", "") or ""))
        db = str(self._g("astrometry.database", "") or "")
        self._db_combo.setCurrentText(db if db in _ASTAP_DATABASES else "Auto")
        self._radius_spin.setValue(int(self._g("astrometry.search_radius_deg", 30)))
        self._select_downsample(int(self._g("astrometry.downsample", 2)))
        self._grid_spin.setValue(int(self._g("astrometry.grid_spacing_arcmin", 0)))
        self._scale_hint_chk.setChecked(bool(self._g("astrometry.use_scale_hint", True)))
        self._mag_spin.setValue(float(self._g("catalog.mag_limit", 15.0)))
        self._max_spin.setValue(int(self._g("catalog.max_results", 250)))
        self._suspected_chk.setChecked(bool(self._g("catalog.include_suspected", True)))

    def _select_downsample(self, value: int) -> None:
        for i, (_label, v) in enumerate(_DOWNSAMPLE):
            if v == value:
                self._down_combo.setCurrentIndex(i)
                return
        self._down_combo.setCurrentIndex(0)

    def _browse_astap(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "Select ASTAP binary")
        if path:
            self._astap_edit.setText(path)

    def _on_save(self) -> None:
        if self._config is not None:
            db = self._db_combo.currentText()
            self._config.set("astrometry.astap_path", self._astap_edit.text().strip())
            self._config.set("astrometry.database", "" if db == "Auto" else db)
            self._config.set("astrometry.search_radius_deg", int(self._radius_spin.value()))
            self._config.set(
                "astrometry.downsample", _DOWNSAMPLE[self._down_combo.currentIndex()][1]
            )
            self._config.set("astrometry.use_scale_hint", self._scale_hint_chk.isChecked())
            self._config.set("astrometry.grid_spacing_arcmin", int(self._grid_spin.value()))
            self._config.set("catalog.mag_limit", float(self._mag_spin.value()))
            self._config.set("catalog.max_results", int(self._max_spin.value()))
            self._config.set("catalog.include_suspected", self._suspected_chk.isChecked())
            self._config.save()
        self.saved.emit()
        self.accept()
