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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seercontrol.ui import theme

logger = logging.getLogger(__name__)

_TRACKING_RATES = ("Sidereal", "Lunar", "Solar")


class MountDock(QGroupBox):
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 14, 8, 8)
        outer.setSpacing(8)

        # Live coordinates — 2×2 grid (RA/Alt on row 0, Dec/Az on row 1)
        coords = QGridLayout()
        coords.setSpacing(4)
        coords.setColumnStretch(1, 1)
        coords.setColumnStretch(3, 1)

        self._ra_lbl  = _value("—h —m —s")
        self._dec_lbl = _value("—° —′ —″")
        self._alt_lbl = _value("—°")
        self._az_lbl  = _value("—°")

        coords.addWidget(_muted("RA"),  0, 0)
        coords.addWidget(self._ra_lbl,  0, 1)
        coords.addWidget(_muted("Alt"), 0, 2)
        coords.addWidget(self._alt_lbl, 0, 3)
        coords.addWidget(_muted("Dec"), 1, 0)
        coords.addWidget(self._dec_lbl, 1, 1)
        coords.addWidget(_muted("Az"),  1, 2)
        coords.addWidget(self._az_lbl,  1, 3)
        outer.addLayout(coords)

        # Tracking row: status + ON/OFF + rate combo
        track_row = QHBoxLayout()
        track_row.setSpacing(6)
        self._tracking_btn = QPushButton("Tracking ON")
        self._tracking_btn.setProperty("class", "success")
        self._tracking_btn.setCheckable(True)
        self._tracking_btn.toggled.connect(self._on_tracking_toggle)
        track_row.addWidget(self._tracking_btn)
        self._rate_combo = QComboBox()
        for label in _TRACKING_RATES:
            self._rate_combo.addItem(label)
        self._rate_combo.currentIndexChanged.connect(self.tracking_rate_changed)
        track_row.addWidget(self._rate_combo)
        outer.addLayout(track_row)

        # Goto form
        goto_form = QFormLayout()
        goto_form.setHorizontalSpacing(8)
        goto_form.setVerticalSpacing(5)
        self._goto_ra = QDoubleSpinBox()
        self._goto_ra.setRange(0.0, 23.9999)
        self._goto_ra.setDecimals(4)
        self._goto_ra.setSuffix("  h")
        self._goto_dec = QDoubleSpinBox()
        self._goto_dec.setRange(-90.0, 90.0)
        self._goto_dec.setDecimals(4)
        self._goto_dec.setSuffix("  °")
        goto_form.addRow("Goto RA",  self._goto_ra)
        goto_form.addRow("Goto Dec", self._goto_dec)
        outer.addLayout(goto_form)

        # Action buttons grid
        btns = QGridLayout()
        btns.setSpacing(5)
        self._slew_btn = QPushButton("▶  Slew")
        self._slew_btn.setProperty("class", "primary")
        self._slew_btn.clicked.connect(self._on_slew)
        self._abort_btn = QPushButton("■  Abort")
        self._abort_btn.setProperty("class", "danger")
        self._abort_btn.clicked.connect(self.abort_clicked)
        self._sync_btn  = QPushButton("⟳  Sync")
        self._sync_btn.setToolTip("Sync mount pointing model to current RA/Dec")
        self._sync_btn.clicked.connect(self.sync_to_current_clicked)
        self._park_btn  = QPushButton("⊙  Park")
        self._park_btn.clicked.connect(self.park_clicked)
        self._jog_btn   = QPushButton("✥  Jog…")
        self._jog_btn.setToolTip("Open the manual jog dialog")
        self._jog_btn.clicked.connect(self.manual_control_requested)
        btns.addWidget(self._slew_btn,  0, 0)
        btns.addWidget(self._abort_btn, 0, 1)
        btns.addWidget(self._sync_btn,  1, 0)
        btns.addWidget(self._park_btn,  1, 1)
        btns.addWidget(self._jog_btn,   2, 0, 1, 2)
        outer.addLayout(btns)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_enabled(self, connected: bool) -> None:
        for w in (
            self._tracking_btn, self._rate_combo,
            self._goto_ra, self._goto_dec,
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

def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;")
    return lbl


def _value(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.ACCENT}; font-size:13px; font-weight:bold;"
        f" font-family:{theme.FONT_MONO}; background:transparent;"
    )
    return lbl


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
