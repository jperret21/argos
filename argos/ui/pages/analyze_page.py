"""Analyze phase — vet the light curve and export AAVSO; inspect frames.

Two companion windows do the work (second-monitor friendly, so a finished night
can be vetted while a new run continues on Capture):

* **Light curve** — reload a session's measurements into the
  :class:`PhotometryWindow`, then export target-only AAVSO
  Extended Format stamped with the observer code + band from Settings.
* **Frame inspector** — open any FITS in the :class:`AnalysisWindow`.

The screen surfaces the observer code so it is obvious what an export will carry,
and warns when it is unset (AAVSO submissions need a real code).
"""

from __future__ import annotations

import logging
import shlex
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from argos.core.config import Config
from argos.core.photometry.lightcurve import read_curves_csv
from argos.core.session.review import SessionReviewError, load_session, load_session_curves
from argos.ui import design, theme
from argos.ui.widgets.lightcurve_panel import LightCurvePanel
from argos.ui.widgets.session_review import SessionQualityPlot

logger = logging.getLogger(__name__)


class AnalyzeScreen(QWidget):
    """Review a completed session before handing raw frames to post-processing."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        # Hold references so the spawned companion windows aren't garbage-collected.
        self._windows: list[QWidget] = []
        self._review = None

        self.setStyleSheet(f"background:{theme.BG};")
        scroll, content = design.scroll_page()

        content.addWidget(design.HeadingLabel("Review"))
        intro = QLabel(
            "Open a completed Argos session to see what happened overnight: frames, filters, "
            "quality trends, temperature, preview curves and the scientific hand-off. "
            "Review never changes raw FITS."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color:{theme.FG}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
        )
        content.addWidget(intro)

        content.addWidget(self._build_session_card())
        content.addWidget(self._build_export_card())

        session_btn = design.PrimaryButton("Open session folder…")
        session_btn.clicked.connect(self._open_session)
        lc_btn = design.SecondaryButton("Open a light-curve CSV…")
        lc_btn.clicked.connect(self._open_lightcurve)
        frame_btn = design.SecondaryButton("Inspect a frame...")
        frame_btn.clicked.connect(self._open_frame)
        content.addLayout(design.button_row(session_btn, lc_btn, frame_btn))

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

    def _build_session_card(self) -> design.Card:
        card = design.Card("Selected session")
        layout = design.card_layout(card)
        self._session_title = design.MetricLabel("No session selected")
        layout.addWidget(self._session_title)
        self._session_summary = design.MutedLabel("Choose a folder containing session.json.")
        self._session_summary.setWordWrap(True)
        layout.addWidget(self._session_summary)
        self._session_warnings = design.MutedLabel("")
        self._session_warnings.setWordWrap(True)
        self._session_warnings.setStyleSheet(f"color:{theme.WARNING};")
        layout.addWidget(self._session_warnings)

        self._review_tabs = QTabWidget()
        self._quality = SessionQualityPlot()
        self._curves = LightCurvePanel()
        self._metadata = QTableWidget(0, 2)
        self._metadata.setHorizontalHeaderLabels(["Field", "Value"])
        self._metadata.verticalHeader().setVisible(False)
        self._metadata.horizontalHeader().setStretchLastSection(True)
        self._review_tabs.addTab(self._quality, "Quality trends")
        self._review_tabs.addTab(self._curves, "Preview light curves")
        self._review_tabs.addTab(self._metadata, "Metadata")
        self._review_tabs.setMinimumHeight(340)
        self._review_tabs.setEnabled(False)
        layout.addWidget(self._review_tabs)

        self._postprod_btn = design.PrimaryButton("Ready for post-processing…")
        self._postprod_btn.setEnabled(False)
        self._postprod_btn.setToolTip(
            "Launches the local star_var_script command configured in Settings. Raw FITS are not changed."
        )
        self._postprod_btn.clicked.connect(self._launch_postprocessing)
        layout.addWidget(self._postprod_btn)
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
        self._update_postprocessing_state()
        super().showEvent(event)

    # ------------------------------------------------------------------
    # Companion windows
    # ------------------------------------------------------------------

    def open_session_photometry(self) -> None:
        """Open saved measurements from the application File menu."""
        self._open_lightcurve()

    def _open_session(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Open Argos session folder", str(self._config.sessions_path)
        )
        if not folder:
            return
        try:
            review = load_session(folder)
        except SessionReviewError as exc:
            QMessageBox.warning(self, "Could not open session", str(exc))
            return
        self._review = review
        self._session_title.setText(f"{review.object_name} · {review.root.name}")
        types = ", ".join(f"{count} {name}" for name, count in review.image_type_counts.items())
        filters = ", ".join(f"{name}: {count}" for name, count in review.filter_counts.items())
        self._session_summary.setText(
            f"Started {review.started_utc or 'unknown'} · {len(review.frames)} frames ({types}) · "
            f"Filters: {filters or '—'} · {review.software}"
        )
        self._quality.set_session(review)
        self._curves.set_curves(load_session_curves(review))
        self._populate_metadata(review)
        issues = review.readiness_issues()
        self._session_warnings.setText(
            " · ".join(issues) if issues else "Session structure looks complete."
        )
        self._review_tabs.setEnabled(True)
        self._update_postprocessing_state()

    def _populate_metadata(self, review) -> None:
        values = [
            ("Session folder", str(review.root)),
            ("Object", review.object_name),
            ("Started UTC", review.started_utc or "—"),
            ("Software", review.software),
            ("Observer", review.observer or "—"),
            ("Frame count", str(len(review.frames))),
        ]
        values.extend((str(key), str(value)) for key, value in sorted(review.metadata.items()))
        self._metadata.setRowCount(len(values))
        for row, (key, value) in enumerate(values):
            self._metadata.setItem(row, 0, QTableWidgetItem(key))
            self._metadata.setItem(row, 1, QTableWidgetItem(value))

    def _update_postprocessing_state(self) -> None:
        configured = bool(
            str(self._config.get("postprocessing.star_var_command", "") or "").strip()
        )
        self._postprod_btn.setEnabled(self._review is not None and configured)
        if self._review is not None and not configured:
            self._postprod_btn.setToolTip(
                "Set the local star_var_script command in Settings → Files & application first."
            )

    def _launch_postprocessing(self) -> None:
        if self._review is None:
            return
        template = str(self._config.get("postprocessing.star_var_command", "") or "").strip()
        if not template:
            return
        try:
            command = shlex.split(
                template.format(
                    session=str(self._review.root), lights=str(self._review.root / "lights")
                )
            )
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Invalid post-processing command", str(exc))
            return
        if not command:
            return
        answer = QMessageBox.question(
            self,
            "Start post-processing",
            "Launch the configured local star_var_script command for this session?\n\n"
            + " ".join(command),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            subprocess.Popen(command, cwd=self._review.root, start_new_session=True)
        except OSError as exc:
            QMessageBox.warning(self, "Could not start post-processing", str(exc))

    def _open_lightcurve(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open session light curve",
            str(self._config.sessions_path),
            "CSV (*.csv);;All files (*)",
        )
        if not path:
            return
        curves = read_curves_csv(path)
        if not curves:
            logger.warning("No valid photometry rows in %s", path)
            return
        from argos.ui.panels.photometry_window import PhotometryWindow

        window = PhotometryWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        window.load_curves(
            curves,
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
