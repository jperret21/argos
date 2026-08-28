"""Floating Photometry window (docs/photometry_plan.md §6 C5/C6).

Hosts the live differential light curve + the session-metrics panel in tabs. A
separate top-level window (like the analysis window) so it can sit on a second
monitor during a run. Display only — the page feeds it points; this window owns no
acquisition state.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from argos.core.photometry.lightcurve import write_aavso, write_curves_csv
from argos.ui import theme
from argos.ui.widgets.comparison_table import ComparisonEnsembleTable
from argos.ui.widgets.lightcurve_panel import LightCurvePanel
from argos.ui.widgets.metrics_panel import MetricsPanel
from argos.ui.widgets.target_table import TargetTable
from argos.ui.widgets.variable_table import VariableTable


class PhotometryWindow(QWidget):
    """Light curve + metrics, in a floating window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Photometry")
        self.resize(720, 480)

        root = QVBoxLayout(self)
        banner = QLabel(
            "Preview — raw, uncalibrated subs. BJD_TDB is recorded when the site and "
            "exposure time are available. Relative flux is a live diagnostic, not a detrended "
            "transit result; publishable reduction remains in Siril."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"color:{theme.WARNING}; font-size:11px; background:transparent; padding:4px 2px;"
        )
        root.addWidget(banner)

        self.variables = VariableTable()
        self.lightcurve = LightCurvePanel()
        self.metrics = MetricsPanel()
        self.targets = TargetTable()
        self.comparisons = ComparisonEnsembleTable()
        tabs = QTabWidget()
        # Variables first: picking the target there is the workflow's entry point.
        tabs.addTab(self.variables, "Field variables")
        tabs.addTab(self.lightcurve, "Light curve")
        tabs.addTab(self.metrics, "Metrics")
        tabs.addTab(self.targets, "Targets")
        tabs.addTab(self.comparisons, "Comparisons")
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self._csv_btn = QPushButton("Export measurements…")
        self._csv_btn.setToolTip("Export target, check-star and comparison measurements")
        self._csv_btn.clicked.connect(self._export_csv)
        footer.addWidget(self._csv_btn)
        self._aavso_btn = QPushButton("Export target (AAVSO)…")
        self._aavso_btn.setToolTip("Export science targets only; comparison curves are diagnostics")
        self._aavso_btn.clicked.connect(self._export_aavso)
        footer.addWidget(self._aavso_btn)
        root.addLayout(footer)

        # Set by the page: the per-target LightCurve objects + the observer code.
        self.lightcurves: dict = {}
        self.obscode = "XXX"
        self.filt = "TG"

    # ------------------------------------------------------------------
    # Real API (WS7): feed_point / set_export_meta / load_curves
    # ------------------------------------------------------------------

    def set_export_meta(self, obscode: str, filt: str, object_name: str = "") -> None:
        """Stamp the AAVSO/CSV export metadata (observer code + band)."""
        self.obscode = obscode or "XXX"
        self.filt = filt or "TG"
        if object_name:
            self.setWindowTitle(f"Photometry — {object_name}")

    def feed_point(self, point) -> None:
        """Render one differential point (a typed ``PhotometryPoint``)."""
        self.lightcurve.add_point(
            point.name,
            point.jd,
            point.mag,
            point.mag_err,
            saturated=point.saturated,
            role=point.role,
            relative_flux=point.relative_flux,
            relative_flux_err=point.relative_flux_err,
        )

    def set_targets(self, stars) -> None:
        """Refresh the Targets + Comparisons tabs from the target set."""
        self.targets.set_targets(stars)
        self.comparisons.set_targets(stars)

    def load_curves(self, curves: dict, obscode: str = "XXX", filt: str = "TG") -> None:
        """Display finished curves (e.g. reloaded from a session CSV by Analyze).

        ``curves`` maps a key to a :class:`LightCurve`; its points are plotted
        and kept for export. Replaces any currently shown curves.
        """
        self.lightcurves = dict(curves)
        self.obscode = obscode or "XXX"
        self.filt = filt or "TG"
        self.lightcurve.set_curves(self.lightcurves)  # same path as the dock

    def _export_csv(self) -> None:
        curves = [lc for lc in self.lightcurves.values() if lc.points]
        if not curves:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export light curve", str(Path.home() / "photometry.csv"), "CSV (*.csv)"
        )
        if path:
            write_curves_csv(path, curves)  # canonical 9-column schema (+ target)

    def _export_aavso(self) -> None:
        curves = [lc for lc in self.lightcurves.values() if lc.points and lc.role == "target"]
        if not curves:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export AAVSO", str(Path.home() / "aavso.txt"), "Text (*.txt)"
        )
        if path:
            write_aavso(path, curves, obscode=self.obscode or "XXX", filt=self.filt or "TG")
