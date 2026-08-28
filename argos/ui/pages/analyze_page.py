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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
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


def _format_metric(value) -> str:
    return "—" if value is None else f"{float(value):.2f}"


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
        self._curves.point_hovered.connect(self._on_curve_point_hovered)
        self._curves.point_clicked.connect(self._on_curve_point_clicked)
        curves_page = QWidget()
        curves_layout = QVBoxLayout(curves_page)
        curves_layout.setContentsMargins(0, 0, 0, 0)
        curves_layout.addWidget(self._curves, 1)
        curve_row = QHBoxLayout()
        self._curve_point_info = design.MutedLabel(
            "Hover a point to inspect it; click to select it."
        )
        self._curve_point_info.setWordWrap(True)
        curve_row.addWidget(self._curve_point_info, 1)
        self._open_curve_frame_btn = design.SecondaryButton("Open source frame")
        self._open_curve_frame_btn.setEnabled(False)
        self._open_curve_frame_btn.clicked.connect(self._open_selected_curve_frame)
        curve_row.addWidget(self._open_curve_frame_btn)
        curves_layout.addLayout(curve_row)
        self._selected_curve_frame = None

        self._frames = QTableWidget(0, 9)
        self._frames.setHorizontalHeaderLabels(
            ["UTC", "Type", "Filter", "Exp (s)", "Gain", "FWHM", "HFD", "Temp (°C)", "File"]
        )
        self._frames.verticalHeader().setVisible(False)
        self._frames.horizontalHeader().setStretchLastSection(True)
        self._frames.cellDoubleClicked.connect(self._open_frame_from_table)
        self._metadata = QTableWidget(0, 2)
        self._metadata.setHorizontalHeaderLabels(["Field", "Value"])
        self._metadata.verticalHeader().setVisible(False)
        self._metadata.horizontalHeader().setStretchLastSection(True)
        self._review_tabs.addTab(self._quality, "Quality trends")
        self._review_tabs.addTab(curves_page, "Preview light curves")
        self._review_tabs.addTab(self._frames, "Frames")
        self._review_tabs.addTab(self._metadata, "Metadata")
        self._review_tabs.setMinimumHeight(340)
        self._review_tabs.setEnabled(False)
        layout.addWidget(self._review_tabs)

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
        self._selected_curve_frame = None
        self._open_curve_frame_btn.setEnabled(False)
        self._curve_point_info.setText(
            "Hover a point to inspect it; click to select its source frame."
        )
        self._populate_frames(review)
        self._populate_metadata(review)
        issues = review.readiness_issues()
        self._session_warnings.setText(
            " · ".join(issues) if issues else "Session structure looks complete."
        )
        self._review_tabs.setEnabled(True)

    def _populate_frames(self, review) -> None:
        self._frames.setRowCount(len(review.frames))
        for row, frame in enumerate(review.frames):
            values = (
                frame.timestamp.isoformat(timespec="seconds") if frame.timestamp else "—",
                frame.image_type,
                frame.filter_name or "—",
                f"{frame.exposure_s:g}",
                str(frame.gain),
                _format_metric(frame.fwhm),
                _format_metric(frame.hfd),
                _format_metric(frame.ccd_temp),
                frame.filename,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, frame)
                self._frames.setItem(row, column, item)

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

    def _on_curve_point_hovered(self, name: str, jd: float, mag: float, error: float) -> None:
        self._curve_point_info.setText(
            f"{name} · JD {jd:.6f} · preview value {mag:.4f} ± {error:.4f}"
        )

    def _on_curve_point_clicked(self, name: str, jd: float, mag: float, error: float) -> None:
        if self._review is None:
            return
        frame = self._review.nearest_light_frame(jd)
        self._selected_curve_frame = frame
        if frame is None:
            self._curve_point_info.setText(f"{name} · no logged light frame matches JD {jd:.6f}")
            self._open_curve_frame_btn.setEnabled(False)
            return
        self._curve_point_info.setText(
            f"{name} · {frame.filename} · {frame.timestamp.isoformat(timespec='seconds') if frame.timestamp else 'unknown UTC'} "
            f"· FWHM {_format_metric(frame.fwhm)} · HFD {_format_metric(frame.hfd)}"
        )
        self._open_curve_frame_btn.setEnabled(self._review.frame_path(frame) is not None)

    def _open_selected_curve_frame(self) -> None:
        if self._selected_curve_frame is not None:
            self._open_review_frame(self._selected_curve_frame)

    def _open_frame_from_table(self, row: int, _column: int) -> None:
        item = self._frames.item(row, 0)
        if item is not None:
            self._open_review_frame(item.data(Qt.ItemDataRole.UserRole))

    def _open_review_frame(self, frame) -> None:
        if self._review is None:
            return
        path = self._review.frame_path(frame)
        if path is None:
            QMessageBox.warning(self, "Frame unavailable", f"Could not find {frame.filename}.")
            return
        from argos.ui.analysis_window import AnalysisWindow

        window = AnalysisWindow(self._config)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        if window.load(str(path)):
            window.show()
            window.raise_()
            self._windows.append(window)

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
