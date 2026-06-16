"""Smoke test for the photometry window + panels (offscreen Qt)."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from seercontrol.ui.panels.photometry_window import PhotometryWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_photometry_window_accepts_points_and_metrics(qapp) -> None:
    win = PhotometryWindow()
    try:
        assert not win.lightcurve.has_data()
        # Feed two points to one target (exercises curve + ErrorBarItem update).
        win.lightcurve.add_point("NU Ori", 2451545.0, 9.0, 0.02)
        win.lightcurve.add_point("NU Ori", 2451545.1, 9.1, 0.03, saturated=True)
        # A second target → a second series/colour.
        win.lightcurve.add_point("V Ori", 2451545.0, 8.0, 0.05)
        assert win.lightcurve.has_data()

        # Metrics: independent series fed at their own cadence.
        win.metrics.add_sample(0.0, sky=480.0, fwhm=3.2, airmass=1.2, stars=42)
        win.metrics.add_sample(20.0, sky=495.0, fwhm=3.4, temp=12.5)
        win.metrics.clear()
        win.lightcurve.clear()
        assert not win.lightcurve.has_data()
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()  # flush the deferred delete now (pyqtgraph teardown)


def test_lightcurve_export_csv(tmp_path, qapp) -> None:
    win = PhotometryWindow()
    try:
        win.lightcurve.add_point("NU Ori", 2451545.0, 9.0, 0.02)
        path = tmp_path / "lc.csv"
        win.lightcurve.export_csv(path)
        text = path.read_text().splitlines()
        assert text[0] == "target,jd_utc,mag,mag_err"
        assert text[1].startswith("NU Ori,")
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()  # flush the deferred delete now (pyqtgraph teardown)
