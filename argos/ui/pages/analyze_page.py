"""Analyze phase — vet the light curve and export AAVSO; inspect frames.

Two companion windows do the work (second-monitor friendly, so a finished night
can be vetted while a new run continues on Capture):

* **Light curve** — reload a session's ``photometry.csv`` (the pure, tested
  ``LightCurve.from_csv``) into the :class:`PhotometryWindow`, then export AAVSO
  Extended Format stamped with the observer code + band from Settings.
* **Frame inspector** — open any FITS in the :class:`AnalysisWindow`.

The screen surfaces the observer code so it is obvious what an export will carry,
and warns when it is unset (AAVSO submissions need a real code).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from argos.core.config import Config
from argos.core.photometry.lightcurve import LightCurve
from argos.ui import design, theme

logger = logging.getLogger(__name__)


class AnalyzeScreen(QWidget):
    """The Analyze phase: light-curve review + AAVSO export, and frame inspection."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        # Hold references so the spawned companion windows aren't garbage-collected.
        self._windows: list[QWidget] = []

        self.setStyleSheet(f"background:{theme.BG};")
        scroll, content = design.scroll_page()

        content.addWidget(design.HeadingLabel("Analyze"))
        intro = QLabel(
            "Vet the result. Reload a finished session's light curve to reject bad "
            "points and export AAVSO Extended Format, or open a single frame in the "
            "inspector. Both open as companion windows so last night can be analysed "
            "while tonight's run continues."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color:{theme.FG}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
        )
        content.addWidget(intro)

        content.addWidget(self._build_export_card())

        lc_btn = design.PrimaryButton("Open light curve from session...")
        lc_btn.clicked.connect(self._open_lightcurve)
        frame_btn = design.SecondaryButton("Inspect a frame...")
        frame_btn.clicked.connect(self._open_frame)
        content.addLayout(design.button_row(lc_btn, frame_btn))

        note = QLabel(
            "Preview photometry — raw subs, no dark/flat/bias. The publishable "
            "curve comes from post-processing (calibration + BJD_TDB)."
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

        self._refresh_export_info()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_export_card(self) -> design.Card:
        card = design.Card("AAVSO export")
        form = QFormLayout()
        form.setContentsMargins(
            design.SPACING_MD, design.SPACING_LG, design.SPACING_MD, design.SPACING_MD
        )
        form.setHorizontalSpacing(design.SPACING_LG)
        form.setVerticalSpacing(design.SPACING_SM)
        self._obscode_value = design.MetricLabel("—")
        self._band_value = design.MetricLabel("—")
        form.addRow(design.MutedLabel("Observer code"), self._obscode_value)
        form.addRow(design.MutedLabel("Band / filter"), self._band_value)
        card.setLayout(form)
        return card

    # ------------------------------------------------------------------
    # Config-driven info
    # ------------------------------------------------------------------

    def _obscode(self) -> str:
        return str(self._config.get("observer.obscode", "") or "").strip()

    def _band(self) -> str:
        return str(self._config.get("photometry.default_band", "TG") or "TG").strip()

    def _refresh_export_info(self) -> None:
        code = self._obscode()
        if code:
            self._obscode_value.setText(code)
            self._obscode_value.setStyleSheet(
                f"color:{theme.ACCENT}; font-size:{design.FONT_SIZE_METRIC}px;"
                f" font-weight:bold; background:transparent;"
            )
        else:
            self._obscode_value.setText("unset — add it in Settings")
            self._obscode_value.setStyleSheet(
                f"color:{theme.WARNING}; font-size:{design.FONT_SIZE_METRIC}px;"
                f" font-weight:bold; background:transparent;"
            )
        self._band_value.setText(self._band())

    def showEvent(self, event: QShowEvent) -> None:
        self._refresh_export_info()  # observer code may have changed in Settings
        super().showEvent(event)

    # ------------------------------------------------------------------
    # Companion windows
    # ------------------------------------------------------------------

    def _open_lightcurve(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open session light curve",
            str(self._config.sessions_path),
            "CSV (*.csv);;All files (*)",
        )
        if not path:
            return
        curve = LightCurve.from_csv(path, name=Path(path).parent.name or Path(path).stem)
        from argos.ui.panels.photometry_window import PhotometryWindow

        window = PhotometryWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        window.load_curves(
            {curve.name or "target": curve},
            obscode=self._obscode() or "XXX",
            filt=self._band(),
        )
        window.show()
        window.raise_()
        self._windows.append(window)

    def _open_frame(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open FITS frame",
            str(self._config.sessions_path),
            "FITS (*.fits *.fit *.fts);;All files (*)",
        )
        if not path:
            return
        from argos.ui.analysis_window import AnalysisWindow

        window = AnalysisWindow(self._config)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        window.load(path)
        window.show()
        self._windows.append(window)
