"""Smoke test for the photometry window + panels (offscreen Qt)."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from argos.ui.panels.photometry_window import PhotometryWindow


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
    """Export CSV writes the canonical 9-column schema (+ target), round-trippable."""
    from argos.core.photometry.lightcurve import LcPoint, LightCurve

    win = PhotometryWindow()
    try:
        lc = LightCurve(name="NU Ori")
        lc.append(
            LcPoint(
                jd_utc=2451545.0,
                mag=9.0,
                mag_err=0.02,
                bjd_tdb=2451545.001,
                airmass=1.2,
                comps_used=3,
                saturated=True,
            )
        )
        win.load_curves({"t": lc})
        path = tmp_path / "lc.csv"
        # Directly exercise the writer (bypass the file dialog).
        from argos.core.photometry.lightcurve import write_curves_csv

        write_curves_csv(path, list(win.lightcurves.values()))
        text = path.read_text().splitlines()
        assert text[0] == (
            "target,jd_utc,bjd_tdb,mag,mag_err,airmass,fwhm,sky_adu,comps_used,saturated"
        )
        assert text[1].startswith("NU Ori,")
        # Round-trips back through the canonical reader (extra target column ignored).
        reloaded = LightCurve.from_csv(path)
        assert len(reloaded.points) == 1
        assert reloaded.points[0].saturated is True
        assert reloaded.points[0].comps_used == 3
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()  # flush the deferred delete now (pyqtgraph teardown)
