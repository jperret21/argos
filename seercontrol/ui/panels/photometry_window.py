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

from seercontrol.ui import theme
from seercontrol.ui.widgets.lightcurve_panel import LightCurvePanel
from seercontrol.ui.widgets.metrics_panel import MetricsPanel


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
        tabs = QTabWidget()
        tabs.addTab(self.lightcurve, "Light curve")
        tabs.addTab(self.metrics, "Metrics")
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self._export_btn = QPushButton("Export light curve CSV…")
        self._export_btn.clicked.connect(self._export)
        footer.addWidget(self._export_btn)
        root.addLayout(footer)

    def _export(self) -> None:
        if not self.lightcurve.has_data():
            return
        start = str(Path.home() / "photometry.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export light curve", start, "CSV (*.csv)")
        if path:
            self.lightcurve.export_csv(path)
