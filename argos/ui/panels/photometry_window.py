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

from argos.core.photometry.lightcurve import write_aavso
from argos.ui import theme
from argos.ui.widgets.lightcurve_panel import LightCurvePanel
from argos.ui.widgets.metrics_panel import MetricsPanel
from argos.ui.widgets.target_table import TargetTable


class PhotometryWindow(QWidget):
    """Light curve + metrics, in a floating window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Photometry")
        self.resize(720, 480)

        root = QVBoxLayout(self)
        banner = QLabel(
            "Preview — raw subs, no dark/flat/bias. The publishable light curve is "
            "produced in post-processing (with calibration + BJD_TDB)."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"color:{theme.WARNING}; font-size:11px; background:transparent; padding:4px 2px;"
        )
        root.addWidget(banner)

        self.lightcurve = LightCurvePanel()
        self.metrics = MetricsPanel()
        self.targets = TargetTable()
        tabs = QTabWidget()
        tabs.addTab(self.lightcurve, "Light curve")
        tabs.addTab(self.metrics, "Metrics")
        tabs.addTab(self.targets, "Targets")
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self._csv_btn = QPushButton("Export CSV…")
        self._csv_btn.clicked.connect(self._export_csv)
        footer.addWidget(self._csv_btn)
        self._aavso_btn = QPushButton("Export AAVSO…")
        self._aavso_btn.clicked.connect(self._export_aavso)
        footer.addWidget(self._aavso_btn)
        root.addLayout(footer)

        # Set by the page: the per-target LightCurve objects + the observer code.
        self.lightcurves: dict = {}
        self.obscode = "XXX"
        self.filt = "TG"

    def load_curves(self, curves: dict, obscode: str = "XXX", filt: str = "TG") -> None:
        """Display finished curves (e.g. reloaded from a session CSV by Analyze).

        ``curves`` maps a key to a :class:`LightCurve`; its points are plotted
        and kept for export. Replaces any currently shown curves.
        """
        self.lightcurves = dict(curves)
        self.obscode = obscode or "XXX"
        self.filt = filt or "TG"
        self.lightcurve.clear()
        for lc in self.lightcurves.values():
            label = lc.name or lc.auid or "TARGET"
            for p in lc.points:
                self.lightcurve.add_point(label, p.jd_utc, p.mag, p.mag_err, p.saturated)

    def _export_csv(self) -> None:
        if not self.lightcurve.has_data():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export light curve", str(Path.home() / "photometry.csv"), "CSV (*.csv)"
        )
        if path:
            self.lightcurve.export_csv(path)

    def _export_aavso(self) -> None:
        curves = [lc for lc in self.lightcurves.values() if lc.points]
        if not curves:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export AAVSO", str(Path.home() / "aavso.txt"), "Text (*.txt)"
        )
        if path:
            write_aavso(path, curves, obscode=self.obscode or "XXX", filt=self.filt or "TG")
