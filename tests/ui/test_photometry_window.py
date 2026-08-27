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


def test_lightcurve_separates_comparisons_and_keeps_error_visibility(qapp) -> None:
    """Comparison diagnostics have their own plot and honour the error toggle."""
    win = PhotometryWindow()
    try:
        panel = win.lightcurve
        panel.add_point("Target", 2451545.0, 9.0, 0.02, role="target")
        panel.add_point("C1", 2451545.0, 11.0, 0.03, role="comparison")
        panel.add_point("C1", 2451545.1, 11.2, 0.03, role="comparison")
        assert panel._series["Target"]["plot"] is panel._target_plot
        assert panel._series["C1"]["plot"] is panel._comparison_plot
        _, comparison_y = panel._series["C1"]["curve"].getData()
        assert comparison_y.tolist() == pytest.approx([-0.1, 0.1])

        panel._errors.setChecked(False)
        panel.add_point("C1", 2451545.2, 11.1, 0.03, role="comparison")
        assert panel._series["C1"]["errbar"].isVisible() is False
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_lightcurve_export_csv(tmp_path, qapp) -> None:
    """Export CSV retains every curve's identity and role."""
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
            "star_id,role,name,auid,jd_utc,bjd_tdb,mag,mag_err,formal_mag_err,"
            "sigma_syst,airmass,fwhm,sky_adu,comps_used,saturated"
        )
        assert ",target,NU Ori," in text[1]
        # The single-curve reader remains backwards compatible.
        reloaded = LightCurve.from_csv(path)
        assert len(reloaded.points) == 1
        assert reloaded.points[0].saturated is True
        assert reloaded.points[0].comps_used == 3
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()  # flush the deferred delete now (pyqtgraph teardown)


def test_measurement_export_round_trips_multiple_roles(tmp_path, qapp) -> None:
    from argos.core.photometry.lightcurve import (
        LcPoint,
        LightCurve,
        read_curves_csv,
        write_curves_csv,
    )

    win = PhotometryWindow()
    try:
        target = LightCurve(auid="T", name="NU Ori", role="target")
        target.append(LcPoint(2451545.0, 9.0, 0.02))
        comparison = LightCurve(auid="C1", name="Comp 1", role="comparison")
        comparison.append(LcPoint(2451545.0, 11.0, 0.03))
        path = tmp_path / "measurements.csv"
        write_curves_csv(path, [target, comparison])
        curves = read_curves_csv(path)
        assert {curve.role for curve in curves.values()} == {"target", "comparison"}
        assert {curve.auid for curve in curves.values()} == {"T", "C1"}
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_variables_tab_lists_and_selects(qapp) -> None:
    """W3: the Variables tab shows the field's variables (target marked ●,
    suspected muted) and emits the row index on 'Set as target'."""
    win = PhotometryWindow()
    try:
        rows = [
            ("V0452 Vul", "EP+BY", "7.67 V – (0.03) V", 2.218573, 16.9, True, False),
            ("NSV 24978", None, "6.52 Hp", None, 44.1, False, True),
        ]
        win.variables.set_variables(rows)
        table = win.variables._table
        assert table.rowCount() == 2
        assert table.item(0, 0).text() == "●"  # already a target
        assert table.item(0, 1).text() == "V0452 Vul"
        assert table.item(1, 2).text() == "?"  # unknown type
        assert table.item(0, 5).text() == "16.9"

        picked: list[int] = []
        win.variables.target_requested.connect(picked.append)
        table.setCurrentCell(1, 1)
        win.variables._select_btn.click()
        assert picked == [1]

        # Repopulating replaces rows (no stale duplicates).
        win.variables.set_variables(rows[:1])
        assert table.rowCount() == 1
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()  # flush the deferred delete now (pyqtgraph teardown)
