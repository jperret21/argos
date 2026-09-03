"""Compact controls for scientific overlays on a solved image.

The first row is organised by physical object type. Catalogue providers are
data-provenance details and live in the catalogue settings instead of being
presented as object types in the observer's primary workflow.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from argos.ui import theme

_OBJECT_CHIPS = (
    ("catalogue", "Stars"),
    ("variables", "Variables"),
    ("galaxies", "Galaxies"),
    ("nebulae_clusters", "Nebulae + clusters"),
    ("exoplanets", "Exoplanets"),
    ("other_objects", "Other objects"),
)
_DISPLAY_CHIPS = (
    ("grid", "Coordinate grid"),
    ("comparisons", "VSP references"),
    ("targets", "Selected stars"),
    ("labels", "Labels"),
)
_CHIP_LABELS = dict(_OBJECT_CHIPS + _DISPLAY_CHIPS)
_TOOLTIPS = {
    "catalogue": "Gaia DR3 stars, enriched with conventional SIMBAD identities when available.",
    "variables": "Variable stars from the AAVSO VSX catalogue.",
    "galaxies": "Galaxies identified by SIMBAD or the bundled Messier/NGC/IC catalogue.",
    "nebulae_clusters": (
        "Nebulae and stellar clusters identified by SIMBAD or the bundled "
        "Messier/NGC/IC catalogue."
    ),
    "exoplanets": "Confirmed exoplanet hosts returned by NASA (cache first).",
    "other_objects": "Other physically classified SIMBAD sources, such as radio or X-ray sources.",
    "comparisons": "AAVSO VSP reference candidates; not necessarily the selected ensemble.",
    "targets": "The target, selected comparison stars and check stars for this observation.",
    "labels": "Show compact non-overlapping labels; hover a marker for its full identity.",
}


class OverlayBar(QWidget):
    """Two compact, semantically grouped rows of solved-field controls."""

    toggled = pyqtSignal(str, bool)
    configure_requested = pyqtSignal()
    magnitude_changed = pyqtSignal(float)
    magnitude_committed = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {theme.SURFACE_3}; border-bottom: 1px solid {theme.SURFACE_4};"
        )
        self.setMaximumHeight(76)
        self._chips: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 3, 8, 3)
        root.setSpacing(3)

        objects = QHBoxLayout()
        objects.setSpacing(6)
        objects.addWidget(self._section_label("Objects"))
        for name, label in _OBJECT_CHIPS:
            objects.addWidget(self._make_chip(name, label))
        objects.addStretch(1)
        root.addLayout(objects)

        display = QHBoxLayout()
        display.setSpacing(6)
        display.addWidget(self._section_label("Display"))
        for name, label in _DISPLAY_CHIPS:
            display.addWidget(self._make_chip(name, label))
        display.addSpacing(8)

        magnitude_caption = QLabel("Gaia G limit")
        magnitude_caption.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:11px; background:transparent;"
        )
        magnitude_caption.setToolTip(
            "Stellar display limit in the Gaia G passband. It does not filter galaxies "
            "or nebulae whose integrated magnitudes use different passbands."
        )
        display.addWidget(magnitude_caption)
        self._magnitude_slider = QSlider(Qt.Orientation.Horizontal)
        self._magnitude_slider.setRange(50, 200)
        self._magnitude_slider.setValue(180)
        self._magnitude_slider.setMinimumWidth(130)
        self._magnitude_slider.setMaximumWidth(220)
        self._magnitude_slider.setToolTip(
            "Faint-end Gaia G display limit. Move left to declutter; move right to reveal "
            "fainter Gaia stars already cached for this field."
        )
        self._magnitude_slider.valueChanged.connect(self._on_magnitude_changed)
        self._magnitude_slider.sliderReleased.connect(
            lambda: self.magnitude_committed.emit(self._magnitude_slider.value() / 10.0)
        )
        display.addWidget(self._magnitude_slider, 1)
        self._magnitude_value = QLabel("≤ 18.0")
        self._magnitude_value.setMinimumWidth(42)
        self._magnitude_value.setStyleSheet(
            f"color:{theme.FG}; font-family:{theme.FONT_MONO}; font-size:11px; "
            "background:transparent;"
        )
        display.addWidget(self._magnitude_value)

        configure = QToolButton()
        configure.setText("Catalogues / depth…")
        configure.setToolTip(
            "Choose Gaia, VSX, SIMBAD, NASA and offline catalogue sources, query depth, "
            "cache folders and refresh behaviour."
        )
        configure.clicked.connect(self.configure_requested)
        display.addWidget(configure)
        display.addStretch(1)
        root.addLayout(display)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setMinimumWidth(48)
        label.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:10px; font-weight:600; "
            "background:transparent; border:0;"
        )
        return label

    def _make_chip(self, name: str, text: str) -> QPushButton:
        chip = QPushButton(text)
        chip.setCheckable(True)
        chip.setEnabled(False)
        chip.setStyleSheet("font-size: 11px; padding: 1px 8px;")
        chip.setToolTip(_TOOLTIPS.get(name, "Show or hide this overlay."))
        chip.toggled.connect(lambda on, n=name: self.toggled.emit(n, on))
        self._chips[name] = chip
        return chip

    def _on_magnitude_changed(self, raw: int) -> None:
        value = raw / 10.0
        self._magnitude_value.setText(f"≤ {value:.1f}")
        self.magnitude_changed.emit(value)

    def set_magnitude_limit(self, value: float) -> None:
        self._magnitude_slider.blockSignals(True)
        self._magnitude_slider.setValue(round(float(value) * 10.0))
        self._magnitude_slider.blockSignals(False)
        self._magnitude_value.setText(f"≤ {self._magnitude_slider.value() / 10.0:.1f}")

    def set_magnitude_range(self, maximum: float) -> None:
        """Limit the live slider to the Gaia depth actually requested."""
        self._magnitude_slider.setMaximum(max(50, round(float(maximum) * 10.0)))

    def set_count(self, name: str, count: int) -> None:
        chip = self._chips.get(name)
        if chip is not None:
            chip.setText(f"{_CHIP_LABELS.get(name, name)} · {max(0, int(count))}")

    def set_available(self, name: str, available: bool) -> None:
        chip = self._chips.get(name)
        if chip is not None:
            chip.setEnabled(bool(available))
            chip.setToolTip(
                _TOOLTIPS.get(name, "Show or hide this overlay.")
                if available
                else "Solve and identify the field to enable this layer."
            )

    def set_checked(self, name: str, checked: bool) -> None:
        chip = self._chips.get(name)
        if chip is not None:
            chip.blockSignals(True)
            chip.setChecked(bool(checked))
            chip.blockSignals(False)

    def is_checked(self, name: str) -> bool:
        chip = self._chips.get(name)
        return bool(chip and chip.isChecked())

    def control(self, name: str) -> QPushButton:
        """Return one named chip for compatibility with compact host toolbars."""
        return self._chips[name]
