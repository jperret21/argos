"""Target phase screen — point, frame and vet the field.

Shows the live target-observing summary (altitude, airmass, transit time, Moon
separation, mount mode) computed from the current target coordinates plus the
observer site. This is the first real workflow-phase screen (it replaces the
Target scaffold) and deliberately avoids the device-connection path so it stays
verifiable headless.

The live field image lives on Capture for now; it migrates here once the
device/session layer is extracted (see docs/ui_design.md). Mount-mode
(alt-az / equatorial) auto-detection is planned, not yet implemented — the field
is shown so the design accounts for it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from argos.core.config import Config
from argos.core.imaging.sky_geometry import compute_target_geometry
from argos.ui import design, theme


def _fmt_ra(hours: float) -> str:
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:  # carry rounding
        h, m = h + 1, 0
    return f"{h:02d}h {m:02d}m"


def _fmt_dec(deg: float) -> str:
    sign = "+" if deg >= 0 else "-"
    a = abs(deg)
    d = int(a)
    m = int(round((a - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{sign}{d:02d} {m:02d}'"


class TargetScreen(QWidget):
    """The Target phase: observing summary + slew, for the current target."""

    slew_requested = pyqtSignal(float, float)  # ra_hours, dec_degrees
    open_controls = pyqtSignal()  # deep-link to the Capture controls

    _REFRESH_MS = 30_000  # the summary drifts slowly; 30 s is plenty

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._ra: float | None = None
        self._dec: float | None = None
        self._label = ""

        self.setStyleSheet(f"background:{theme.BG};")
        scroll, content = design.scroll_page()

        content.addWidget(design.HeadingLabel("Target"))
        intro = QLabel(
            "Put the right star in the centre of the frame and check it is worth "
            "observing tonight."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color:{theme.FG}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
        )
        content.addWidget(intro)

        card = design.Card("Observing summary")
        form = QFormLayout()
        form.setContentsMargins(
            design.SPACING_MD, design.SPACING_LG, design.SPACING_MD, design.SPACING_MD
        )
        form.setHorizontalSpacing(design.SPACING_LG)
        form.setVerticalSpacing(design.SPACING_SM)
        self._values: dict[str, QLabel] = {}
        for key, label in (
            ("name", "Target"),
            ("radec", "RA / Dec"),
            ("altitude", "Altitude"),
            ("airmass", "Airmass"),
            ("transit", "Transit"),
            ("moon", "Moon sep"),
            ("mode", "Mount mode"),
        ):
            value = design.MetricLabel("—")
            self._values[key] = value
            form.addRow(design.MutedLabel(label), value)
        card.setLayout(form)
        content.addWidget(card)

        self._slew_btn = design.PrimaryButton("Slew to target")
        self._slew_btn.setEnabled(False)
        self._slew_btn.clicked.connect(self._on_slew)
        capture_btn = design.SecondaryButton("Open field & solve in Capture")
        capture_btn.clicked.connect(self.open_controls.emit)
        content.addLayout(design.button_row(self._slew_btn, capture_btn))

        note = QLabel(
            "The live field image is on Capture for now; it moves here once the "
            "session layer is extracted. Mount-mode (alt-az / equatorial) "
            "auto-detection is planned."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_LABEL}px;"
            f" background:transparent;"
        )
        content.addWidget(note)
        content.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self._timer = QTimer(self)
        self._timer.setInterval(self._REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    # ------------------------------------------------------------------

    def set_target(self, ra_hours: float, dec_degrees: float, label: str = "") -> None:
        """Set the active target (e.g. from a Stellarium goto) and refresh."""
        self._ra = float(ra_hours)
        self._dec = float(dec_degrees)
        self._label = label or "target"
        self._slew_btn.setEnabled(True)
        self.refresh()

    def _on_slew(self) -> None:
        if self._ra is not None and self._dec is not None:
            self.slew_requested.emit(self._ra, self._dec)

    def refresh(self) -> None:
        """Recompute the observing summary for the current target, now."""
        self._values["mode"].setText(str(self._config.get("mount.mode", "—")))
        if self._ra is None or self._dec is None:
            return

        self._values["name"].setText(self._label)
        self._values["radec"].setText(f"{_fmt_ra(self._ra)}  {_fmt_dec(self._dec)}")

        geo = compute_target_geometry(
            datetime.now(timezone.utc),
            self._config.get("observer.latitude"),
            self._config.get("observer.longitude"),
            self._config.get("observer.elevation"),
            self._ra,
            self._dec,
        )
        alt = geo.get("altitude")
        self._values["altitude"].setText(f"{alt:.1f} deg" if alt is not None else "—")
        airmass = geo.get("airmass")
        self._values["airmass"].setText(
            f"{airmass:.2f}" if airmass is not None else "— (below horizon)"
        )
        transit_utc = geo.get("transit_utc")
        transit_in = geo.get("transit_in")
        if transit_utc is not None and transit_in is not None:
            self._values["transit"].setText(
                f"{transit_utc.strftime('%H:%M')} UTC  (in {transit_in:.1f} h)"
            )
        else:
            self._values["transit"].setText("—")
        moon_sep = geo.get("moon_sep")
        self._values["moon"].setText(f"{moon_sep:.0f} deg" if moon_sep is not None else "—")
