"""Mount dock — right-side mount control for the Imaging mode.

UI-only. ImagingPage wires this widget's signals to ``Telescope`` and feeds
back live coordinates via ``set_position()``. Manual jog stays in the
existing ``ManualControlDialog`` which is launched from here.

Public surface:
    Signals
        goto_clicked(ra_hours, dec_degrees)
        sync_to_current_clicked()
        tracking_toggled(enabled: bool)
        tracking_rate_changed(rate: int)        # 0=Sidereal, 1=Lunar, 2=Solar
        abort_clicked()
        park_clicked()
        manual_control_requested()
    Methods (called by ImagingPage)
        set_enabled(connected: bool)
        set_position(ra_h, dec_d, alt_d, az_d, tracking, slewing)
        set_goto_fields(ra_h, dec_d)            # so an external pull can pre-fill
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QWidget,
)

from seercontrol.ui import design

logger = logging.getLogger(__name__)

_TRACKING_RATES = ("Sidereal", "Lunar", "Solar")


class MountDock(design.Card):
    """Compact mount control group for the right side of the Imaging page."""

    goto_clicked              = pyqtSignal(float, float)   # ra_hours, dec_degrees
    sync_to_current_clicked   = pyqtSignal()
    tracking_toggled          = pyqtSignal(bool)
    tracking_rate_changed     = pyqtSignal(int)
    abort_clicked             = pyqtSignal()
    park_clicked              = pyqtSignal()
    manual_control_requested  = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Mount", parent)
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = design.card_layout(self)

        # Live coordinates — 2×2 grid (RA/Alt on row 0, Dec/Az on row 1)
        coords = QGridLayout()
        coords.setSpacing(design.SPACING_SM)
        coords.setColumnStretch(1, 1)
        coords.setColumnStretch(3, 1)

        self._ra_lbl  = design.MetricLabel("—h —m —s")
        self._dec_lbl = design.MetricLabel("—° —′ —″")
        self._alt_lbl = design.MetricLabel("—°")
        self._az_lbl  = design.MetricLabel("—°")

        coords.addWidget(design.MutedLabel("RA"),  0, 0)
        coords.addWidget(self._ra_lbl,             0, 1)
        coords.addWidget(design.MutedLabel("Alt"), 0, 2)
        coords.addWidget(self._alt_lbl,            0, 3)
        coords.addWidget(design.MutedLabel("Dec"), 1, 0)
        coords.addWidget(self._dec_lbl,            1, 1)
        coords.addWidget(design.MutedLabel("Az"),  1, 2)
        coords.addWidget(self._az_lbl,             1, 3)
        outer.addLayout(coords)

        outer.addWidget(design.horizontal_divider())

        # Tracking row — toggle + rate combo
        self._tracking_btn = design.SuccessButton("Tracking ON")
        self._tracking_btn.setCheckable(True)
        self._tracking_btn.toggled.connect(self._on_tracking_toggle)
        self._rate_combo = QComboBox()
        for label in _TRACKING_RATES:
            self._rate_combo.addItem(label)
        self._rate_combo.currentIndexChanged.connect(self.tracking_rate_changed)
        outer.addLayout(design.button_row(self._tracking_btn))
        rate_form = QFormLayout()
        rate_form.setHorizontalSpacing(design.SPACING_MD)
        rate_form.addRow(design.MutedLabel("Rate"), self._rate_combo)
        outer.addLayout(rate_form)

        outer.addWidget(design.horizontal_divider())

        # Goto form
        goto_form = QFormLayout()
        goto_form.setHorizontalSpacing(design.SPACING_MD)
        goto_form.setVerticalSpacing(design.SPACING_SM)
        self._goto_ra = QDoubleSpinBox()
        self._goto_ra.setRange(0.0, 23.9999)
        self._goto_ra.setDecimals(4)
        self._goto_ra.setSuffix("  h")
        self._goto_dec = QDoubleSpinBox()
        self._goto_dec.setRange(-90.0, 90.0)
        self._goto_dec.setDecimals(4)
        self._goto_dec.setSuffix("  °")
        goto_form.addRow(design.MutedLabel("Goto RA"),  self._goto_ra)
        goto_form.addRow(design.MutedLabel("Goto Dec"), self._goto_dec)
        outer.addLayout(goto_form)

        # Action buttons — two rows of two, plus the full-width Jog launcher.
        self._slew_btn  = design.PrimaryButton("▶  Slew")
        self._slew_btn.clicked.connect(self._on_slew)
        self._abort_btn = design.DangerButton("■  Abort")
        self._abort_btn.clicked.connect(self.abort_clicked)
        self._sync_btn  = design.SecondaryButton("⟳  Sync")
        self._sync_btn.setToolTip("Sync mount pointing model to current RA/Dec")
        self._sync_btn.clicked.connect(self.sync_to_current_clicked)
        self._park_btn  = design.SecondaryButton("⊙  Park")
        self._park_btn.clicked.connect(self.park_clicked)
        self._jog_btn   = design.SecondaryButton("✥  Jog…")
        self._jog_btn.setToolTip("Open the manual jog dialog")
        self._jog_btn.clicked.connect(self.manual_control_requested)
        outer.addLayout(design.button_row(self._slew_btn, self._abort_btn))
        outer.addLayout(design.button_row(self._sync_btn, self._park_btn))
        outer.addLayout(design.button_row(self._jog_btn))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_enabled(self, connected: bool) -> None:
        """Gate only the action buttons; goto coords stay editable always."""
        for w in (
            self._tracking_btn, self._rate_combo,
            self._slew_btn, self._abort_btn, self._sync_btn,
            self._park_btn, self._jog_btn,
        ):
            w.setEnabled(connected)

    def set_position(
        self,
        ra_h: float, dec_d: float, alt_d: float, az_d: float,
        tracking: bool, slewing: bool,
    ) -> None:
        self._ra_lbl.setText(_format_ra(ra_h))
        self._dec_lbl.setText(_format_dec(dec_d))
        self._alt_lbl.setText(f"{alt_d:.2f}°")
        self._az_lbl.setText(f"{az_d:.2f}°")
        self._tracking_btn.blockSignals(True)
        self._tracking_btn.setChecked(tracking)
        self._tracking_btn.setText("Tracking ON" if tracking else "Tracking OFF")
        self._tracking_btn.setProperty("class", "success" if tracking else "")
        self._tracking_btn.style().unpolish(self._tracking_btn)
        self._tracking_btn.style().polish(self._tracking_btn)
        self._tracking_btn.blockSignals(False)
        # Cosmetic: slew-in-progress highlights the abort button.
        self._abort_btn.setProperty("class", "danger" if slewing else "")
        self._abort_btn.style().unpolish(self._abort_btn)
        self._abort_btn.style().polish(self._abort_btn)

    def set_goto_fields(self, ra_h: float, dec_d: float) -> None:
        self._goto_ra.setValue(float(ra_h))
        self._goto_dec.setValue(float(dec_d))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_slew(self) -> None:
        self.goto_clicked.emit(self._goto_ra.value(), self._goto_dec.value())

    def _on_tracking_toggle(self, checked: bool) -> None:
        self.tracking_toggled.emit(checked)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _format_ra(hours: float) -> str:
    total = int(round(hours * 3600))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"


def _format_dec(degrees: float) -> str:
    sign = "+" if degrees >= 0 else "-"
    d = abs(degrees)
    deg = int(d)
    rest = (d - deg) * 60
    minutes = int(rest)
    seconds = int((rest - minutes) * 60)
    return f"{sign}{deg:02d}° {minutes:02d}′ {seconds:02d}″"
