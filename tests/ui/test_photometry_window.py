"""Smoke test for the photometry window + panels (offscreen Qt)."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from types import SimpleNamespace

from argos.core.photometry.lightcurve import LcPoint, LightCurve
from argos.ui.panels.photometry_window import PhotometryWindow
from argos.ui.widgets.comparison_curve_panel import ComparisonCurvePanel
from argos.ui.widgets.comparison_table import ComparisonEnsembleTable
from argos.ui.widgets.lightcurve_panel import LightCurvePanel
from argos.ui.widgets.target_curve_panel import TargetCurvePanel
from argos.ui.widgets.variable_table import VariableTable
from argos.ui.widgets.fits_viewer import _marker_tip
from argos.ui.widgets.overlay_bar import OverlayBar
from argos.core.catalog.gaia import GaiaStar
from argos.core.catalog.field_objects import NamedFieldObject
from argos.ui.pages.imaging_page import ImagingPage


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


def test_marker_tooltip_accepts_pyqtgraph_keyword_arguments() -> None:
    """PyQtGraph 0.13 calls the tooltip callback with named x/y/data values."""
    assert _marker_tip(x=12.5, y=7.0, data="HD 189733") == "HD 189733"
    assert _marker_tip(x=12.5, y=7.0, data="<source>") == "&lt;source&gt;"


def test_field_filter_bar_keeps_zero_result_layers_clickable(qapp) -> None:
    bar = OverlayBar()
    try:
        values: list[float] = []
        bar.magnitude_changed.connect(values.append)
        bar.set_available("exoplanets", True)
        bar.set_count("exoplanets", 0)
        assert bar._chips["exoplanets"].isEnabled()
        assert bar._chips["exoplanets"].text() == "Exoplanets · 0"
        assert "named_objects" not in bar._chips
        assert {"galaxies", "nebulae_clusters", "other_objects"} <= set(bar._chips)
        bar._magnitude_slider.setValue(143)
        assert values[-1] == 14.3
        assert bar._magnitude_value.text() == "≤ 14.3"
    finally:
        bar.close()
        bar.deleteLater()


def test_identified_star_card_includes_available_gaia_magnitudes() -> None:
    star = GaiaStar("123", 300.0, 58.0, g_mag=12.3, bp_mag=12.8, rp_mag=11.7)
    identity = NamedFieldObject("HD 123", 300.0, 58.0, "*")
    text = ImagingPage._field_catalogue_body(star, identity)
    assert "HD 123" in text
    assert "Gaia G magnitude  12.300" in text
    assert "Gaia BP magnitude  12.800" in text
    assert "Gaia RP magnitude  11.700" in text


def test_simbad_galaxy_is_classified_and_shows_passband_magnitudes() -> None:
    item = NamedFieldObject(
        "2MASX J20021735+5909440",
        300.572,
        59.162,
        "G",
        mags=(("G", 20.613), ("J", 14.889), ("K", 13.639)),
    )
    assert ImagingPage._object_category(item.object_type) == "galaxy"
    text = ImagingPage._named_object_tooltip(item)
    assert "SIMBAD G magnitude  20.613" in text
    assert "SIMBAD K magnitude  13.639" in text


def test_offline_deep_sky_types_map_to_physical_filters() -> None:
    assert ImagingPage._object_category("Gx") == "galaxy"
    assert ImagingPage._object_category("Nb") == "nebula"
    assert ImagingPage._object_category("OC") == "cluster"


def test_field_catalogue_simbad_match_is_nearest_and_within_three_arcsec() -> None:
    stars = [
        GaiaStar("near", 300.0, 58.0),
        GaiaStar("far", 301.0, 58.0),
    ]
    near = NamedFieldObject("HD near", 300.0 + 1.0 / 3600.0, 58.0, "*")
    # At +58°, an RA offset is shortened by cos(dec); 7 arcsec in RA is
    # safely beyond the 3-arcsec great-circle matching radius.
    far = NamedFieldObject("HD far", 301.0 + 7.0 / 3600.0, 58.0, "*")

    matched, names = ImagingPage._match_field_catalogue_names(stars, [near, far])

    assert matched == {0}
    assert names == [near, None]


def test_photometry_measurement_controls_are_explicit_and_configurable(qapp) -> None:
    win = PhotometryWindow()
    try:
        changes: list[tuple[str, object]] = []
        win.setup.setting_changed.connect(lambda key, value: changes.append((key, value)))
        win.setup.set_values(
            lambda key, default: {
                "photometry.aperture_fwhm_mult": 2.5,
                "photometry.aperture_min_px": 4.0,
                "photometry.annulus_in_px": 8.0,
                "photometry.annulus_out_px": 12.0,
            }.get(key, default),
            (6.5, 8.0, 12.0),
        )
        assert changes == []  # loading config must not write it back
        assert "aperture 6.5 px" in win.setup._effective.text()
        assert win.setup._comparison_snr.value() == 10.0
        assert win.setup._comparison_delta.value() == 1.5
        assert win.setup._comparison_distance.value() == 25.0
        win.setup._fwhm_mult.setValue(3.0)
        assert changes == [("photometry.aperture_fwhm_mult", 3.0)]
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_comparison_proposal_count_is_a_user_preference(qapp) -> None:
    win = PhotometryWindow()
    try:
        requested: list[int] = []
        win.comparisons.auto_count_changed.connect(requested.append)
        win.comparisons.set_auto_count(7)
        assert win.comparisons._auto_count.value() == 7
        assert requested == []  # config synchronisation is not a new user request
        win.comparisons._auto_count.setValue(4)
        assert requested == [4]
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_comparison_table_surfaces_live_quality(qapp) -> None:
    from argos.core.catalog.targets import TargetStar

    table = ComparisonEnsembleTable()
    try:
        table.set_targets(
            [
                TargetStar(
                    role="comparison",
                    ra_deg=300.0,
                    dec_deg=22.0,
                    auid="000-AAA-001",
                    name="106",
                    mags={"V": 10.6},
                )
            ]
        )
        table.set_quality_report(
            {
                "comparison_stars": [
                    {
                        "auid": "000-AAA-001",
                        "name": "106",
                        "n_valid": 12,
                        "scatter_mag": 0.021,
                        "median_formal_error_mag": 0.012,
                        "status": "stable",
                    }
                ]
            }
        )
        assert table._table.item(0, 6).text() == "12"
        assert table._table.item(0, 9).text() == "Stable"
    finally:
        table.close()
        table.deleteLater()
        qapp.processEvents()


def test_variable_table_keeps_catalogue_and_overlay_source_indices_aligned(qapp) -> None:
    table = VariableTable()
    try:
        visible: list[list[int]] = []
        selected: list[int] = []
        table.visible_rows_changed.connect(visible.append)
        table.target_requested.connect(selected.append)
        table.set_variables(
            [
                ("Bright", "EA", "10.0 V", None, 1.0, False, False),
                ("Faint", "EW", "15.0 V", None, 2.0, False, False),
            ],
            source_indices=[7, 42],
        )
        assert visible[-1] == [7, 42]
        table._mag_limit.setValue(12.0)
        assert visible[-1] == [7]
        table._table.selectRow(0)
        table._on_select()
        assert selected == [7]
    finally:
        table.close()
        table.deleteLater()
        qapp.processEvents()


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
        panel._errors.setChecked(True)
        panel._series["C1"]["curve"].setVisible(False)
        assert panel._series["C1"]["errbar"].isVisible() is False
        assert panel._series["C1"]["sat"].isVisible() is False
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_lightcurve_uncertainties_have_no_horizontal_caps(qapp) -> None:
    """Photometric uncertainties are vertical intervals, independent of JD scale."""
    panel = LightCurvePanel(view="target")
    try:
        panel.add_point("Target", 2451545.0, 9.0, 0.02)
        assert panel._series["Target"]["errbar"].opts["beam"] is None
        panel.add_point("Target", 2451545.001, 9.1, 0.03)
        assert panel._series["Target"]["errbar"].opts["beam"] is None
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_lightcurve_can_render_source_and_comparisons_in_separate_panels(qapp) -> None:
    """Review may show both diagnostics at once without sharing a plot scale."""
    source = LightCurvePanel(view="target")
    comparisons = LightCurvePanel(view="comparison")
    try:
        for panel in (source, comparisons):
            panel.add_point("Target", 2451545.0, 9.0, 0.02, role="target")
            panel.add_point("C1", 2451545.0, 11.0, 0.03, role="comparison")
        assert set(source._series) == {"Target"}
        assert set(comparisons._series) == {"C1"}
        assert source._target_plot is not None
        assert source._comparison_plot is None
        assert comparisons._target_plot is None
        assert comparisons._comparison_plot is not None
    finally:
        source.close()
        comparisons.close()
        source.deleteLater()
        comparisons.deleteLater()
        qapp.processEvents()


def test_comparison_plot_selects_one_star_independently(qapp) -> None:
    panel = ComparisonCurvePanel()
    try:
        c1 = LightCurve(name="Comparison 1", role="comparison")
        c1.append(LcPoint(2451545.0, 11.0, 0.03))
        c2 = LightCurve(name="Comparison 2", role="comparison")
        c2.append(LcPoint(2451545.0, 12.0, 0.02))
        panel.set_curves({"c1": c1, "c2": c2}, preferred_key="c2")
        assert panel.selected_key() == "c2"
        assert set(panel._plot._series) == {"Comparison 2"}
        panel.set_selected_key("c1")
        assert set(panel._plot._series) == {"Comparison 1"}
        panel.set_selected_key(panel._selector.itemData(panel._selector.count() - 1))
        assert set(panel._plot._series) == {"Comparison 1", "Comparison 2"}
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_target_plot_defaults_to_one_target_and_offers_all_last(qapp) -> None:
    panel = TargetCurvePanel()
    try:
        t1 = LightCurve(name="XX Cyg", role="target")
        t1.append(LcPoint(2451545.0, 11.6, 0.02))
        t2 = LightCurve(name="V0372 Ori", role="target")
        t2.append(LcPoint(2451545.0, 12.2, 0.03))
        comp = LightCurve(name="106", role="comparison")
        comp.append(LcPoint(2451545.0, 10.6, 0.02))
        panel.set_curves({"t1": t1, "t2": t2, "c": comp}, preferred_key="t2")
        assert panel.selected_key() == "t2"
        assert set(panel._plot._series) == {"V0372 Ori"}
        assert panel._selector.itemText(panel._selector.count() - 1) == "All targets"
        panel.set_selected_key(panel._selector.itemData(panel._selector.count() - 1))
        assert set(panel._plot._series) == {"XX Cyg", "V0372 Ori"}
    finally:
        panel.close()
        panel.deleteLater()
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
            "sigma_syst,airmass,fwhm,sky_adu,comps_used,relative_flux,relative_flux_err,"
            "relative_comps_used,saturated,suspect"
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

        # Filtering keeps the engine's original row identity after the visible
        # table has shrunk or been sorted.
        win.variables._search_edit.setText("v0452vul")
        assert table.rowCount() == 1
        table.setCurrentCell(0, 1)
        win.variables._select_btn.click()
        assert picked == [1, 0]
        win.variables._search_edit.clear()
        table.horizontalHeader().sectionClicked.emit(1)  # sort by designation
        assert table.item(0, 1).text() == "NSV 24978"
        table.setCurrentCell(0, 1)
        win.variables._select_btn.click()
        assert picked == [1, 0, 1]
        win.variables._mag_limit.setValue(7.0)
        assert table.rowCount() == 1
        assert table.item(0, 1).text() == "NSV 24978"

        # Repopulating replaces rows (no stale duplicates).
        win.variables._mag_limit.setValue(0.0)
        win.variables.set_variables(rows[:1])
        assert table.rowCount() == 1
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()  # flush the deferred delete now (pyqtgraph teardown)


def test_aavso_export_names_the_check_star_and_the_vsp_chart(qapp, tmp_path, monkeypatch) -> None:
    from PyQt6.QtWidgets import QFileDialog

    from argos.core.catalog.targets import TargetStar

    import argos.ui.panels.photometry_window as pw

    out = tmp_path / "aavso.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    monkeypatch.setattr(pw, "QMessageBox", _MessageBoxRecorder(), raising=False)
    win = PhotometryWindow()
    try:
        target = LightCurve(auid="000-BCK-301", name="XX Cyg", role="target")
        target.append(LcPoint(2451545.0, 11.0, 0.02))
        check = LightCurve(auid="000-BJV-171", name="106", role="check")
        check.append(LcPoint(2451545.0, 10.61, 0.01))
        win.load_curves({"T": target, "K": check}, obscode="ABC")
        comparison = TargetStar(
            role="comparison", ra_deg=300.7, dec_deg=59.0, auid="000-BJV-170", chart_id="X42"
        )
        win.set_targets([comparison])
        win._export_aavso()

        rows = [ln.split(",") for ln in out.read_text().splitlines() if not ln.startswith("#")]
        assert len(rows) == 1  # the check star is not an observation of its own
        assert (rows[0][9], rows[0][10], rows[0][13]) == ("000-BJV-171", "10.6100", "X42")
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_target_plot_lists_check_curve(qapp) -> None:
    """S9: once Review gives check curves their role, the source-curve plot
    must still list them (the comparison plot shows comparisons only)."""
    target = LightCurve(auid="000-BCP-095", name="SS Cyg", role="target")
    target.append(LcPoint(jd_utc=2461315.5, mag=12.0, mag_err=0.02))
    check = LightCurve(auid="000-KKK-222", name="K1", role="check")
    check.append(LcPoint(jd_utc=2461315.5, mag=12.5, mag_err=0.02))
    panel = TargetCurvePanel()
    try:
        panel.set_curves({"T": target, "K": check})
        labels = {
            panel._selector.itemData(i): panel._selector.itemText(i)
            for i in range(panel._selector.count())
        }
        assert labels["K"] == "K1 (check)"
        assert labels["T"] == "SS Cyg"
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def _open_curve_csv_as_review_does(qapp, monkeypatch, csv_path):
    """Run AnalyzeScreen._open_lightcurve on a stand-in screen; return
    (window, warnings shown)."""
    from types import SimpleNamespace

    import argos.ui.pages.analyze_page as ap

    warnings: list[str] = []
    monkeypatch.setattr(
        ap.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(csv_path), ""))
    )
    monkeypatch.setattr(
        ap,
        "QMessageBox",
        SimpleNamespace(warning=lambda *args, **kwargs: warnings.append(str(args[2]))),
        raising=False,
    )
    screen = SimpleNamespace(
        _config=SimpleNamespace(sessions_path=csv_path.parent),
        _obscode=lambda: "ABC",
        _band=lambda: "TG",
        _windows=[],
    )
    ap.AnalyzeScreen._open_lightcurve(screen)
    (window,) = screen._windows
    return window, warnings


def test_open_curve_csv_never_exports_a_comparison_as_the_variable(
    qapp, tmp_path, monkeypatch
) -> None:
    """S10: a comparison_ CSV opened in Review was exported as a target row
    named COMPARISON_SS_CYG_000-AAA-111; an unidentifiable file must not
    be exportable at all."""
    import argos.ui.panels.photometry_window as pw
    from argos.core.catalog.targets import TargetSet, TargetStar

    run = tmp_path / "run"
    photometry = run / "photometry"
    photometry.mkdir(parents=True)
    TargetSet(
        object_name="SS Cyg",
        stars=[
            TargetStar("target", 325.678, 43.586, auid="000-BCP-095", name="SS Cyg"),
            TargetStar("comparison", 325.70, 43.60, auid="000-AAA-111", name="111"),
        ],
    ).save(run / "targets.json")
    csv_path = photometry / "comparison_SS_Cyg_000-AAA-111.csv"
    csv_path.write_text("jd_utc,mag,mag_err,saturated\n2461315.5,11.0,0.02,0\n")
    out = tmp_path / "aavso.txt"
    monkeypatch.setattr(
        pw.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), ""))
    )
    monkeypatch.setattr(
        pw,
        "QMessageBox",
        SimpleNamespace(warning=lambda *a, **k: None, information=lambda *a, **k: None),
        raising=False,
    )

    window, warnings = _open_curve_csv_as_review_does(qapp, monkeypatch, csv_path)
    try:
        window._export_aavso()
        rows = (
            [line for line in out.read_text().splitlines() if not line.startswith("#")]
            if out.exists()
            else []
        )
        assert not any(row.startswith("COMPARISON_") for row in rows), rows
        assert warnings == []
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()

    legacy = tmp_path / "SS_Cyg_000-BCP-095.csv"  # no prefix, no targets.json near it
    legacy.write_text("jd_utc,mag,mag_err,saturated\n2461315.5,12.0,0.02,0\n")
    window, warnings = _open_curve_csv_as_review_does(qapp, monkeypatch, legacy)
    try:
        assert warnings and "unknown" in warnings[0]
        assert not window._aavso_btn.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


class _MessageBoxRecorder:
    """Stands in for QMessageBox: records (kind, text) instead of blocking."""

    def __init__(self) -> None:
        self.shown: list[tuple[str, str]] = []

    def warning(self, _parent, _title, text, *args, **kwargs):
        self.shown.append(("warning", str(text)))

    def information(self, _parent, _title, text, *args, **kwargs):
        self.shown.append(("information", str(text)))


def _window_with_one_target(obscode: str) -> PhotometryWindow:
    target = LightCurve(name="SS Cyg", role="target")
    target.append(LcPoint(jd_utc=2461315.5, mag=12.0, mag_err=0.02))
    win = PhotometryWindow()
    win.load_curves({"T": target}, obscode=obscode)
    return win


def test_aavso_export_refuses_unset_obscode(qapp, tmp_path, monkeypatch) -> None:
    """S11: an unset observer code was exported as #OBSCODE=XXX, silently."""
    import argos.ui.panels.photometry_window as pw

    out = tmp_path / "aavso.txt"
    monkeypatch.setattr(
        pw.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), ""))
    )
    boxes = _MessageBoxRecorder()
    monkeypatch.setattr(pw, "QMessageBox", boxes, raising=False)
    for unset in ("XXX", ""):
        win = _window_with_one_target(unset)
        try:
            boxes.shown.clear()
            win._export_aavso()
            assert not out.exists()
            assert [kind for kind, _text in boxes.shown] == ["warning"]
            assert "observer code" in boxes.shown[0][1]
        finally:
            win.close()
            win.deleteLater()
            qapp.processEvents()


def test_aavso_export_reports_write_error(qapp, tmp_path, monkeypatch) -> None:
    """S11: a failed write raised out of the slot (crash report only) and
    looked like a success to the observer."""
    import argos.ui.panels.photometry_window as pw

    blocker = tmp_path / "not_a_folder"
    blocker.write_text("")
    monkeypatch.setattr(
        pw.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(blocker / "aavso.txt"), "")),
    )
    boxes = _MessageBoxRecorder()
    monkeypatch.setattr(pw, "QMessageBox", boxes, raising=False)
    win = _window_with_one_target("ABC")
    try:
        win._export_aavso()  # must not raise
        assert [kind for kind, _text in boxes.shown] == ["warning"]
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_aavso_export_reports_rows_and_excluded_points(qapp, tmp_path, monkeypatch) -> None:
    import argos.ui.panels.photometry_window as pw

    out = tmp_path / "aavso.txt"
    seen_dirs: list[str] = []

    def save_dialog(_parent, _title, start, *_a, **_k):
        seen_dirs.append(start)
        return str(out), ""

    monkeypatch.setattr(pw.QFileDialog, "getSaveFileName", staticmethod(save_dialog))
    boxes = _MessageBoxRecorder()
    monkeypatch.setattr(pw, "QMessageBox", boxes, raising=False)
    win = _window_with_one_target("ABC")
    try:
        win.lightcurves["T"].append(
            LcPoint(jd_utc=2461315.6, mag=9.0, mag_err=0.02, saturated=True)
        )
        win.default_dir = tmp_path
        win._export_aavso()
        assert seen_dirs and seen_dirs[0].startswith(str(tmp_path))
        ((kind, text),) = boxes.shown
        assert kind == "information" and "1 observation" in text and "saturated" in text
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_aperture_geometry_locked_during_sequence(qapp) -> None:
    """S15: one touch of a geometry spin during a run silently changed the
    aperture or annulus mid-curve (applied from the next sub)."""
    from argos.core.config import Config

    config = Config({})
    logs: list[tuple[str, str]] = []
    win = PhotometryWindow()
    page = SimpleNamespace(
        _astrometry=SimpleNamespace(auto=True, wcs=None),
        _engine=SimpleNamespace(
            sequence_has_light_frames=lambda: False,
            photometry_geometry=lambda: (6.0, 8.0, 12.0),
        ),
        _config=config,
        _cfg=lambda key, default: config.get(key, default),
        auto_solve_armed=SimpleNamespace(emit=lambda armed: None),
        log_message=SimpleNamespace(emit=lambda level, msg: logs.append((level, msg))),
        _sequence_context_lbl=SimpleNamespace(clear=lambda: None),
        _photometry_window=win,
        _pending_green=None,
    )
    page._sync_photometry_setup = lambda: ImagingPage._sync_photometry_setup(page)
    setup = win.setup
    geometry = (setup._fwhm_mult, setup._minimum, setup._annulus_in, setup._annulus_out)
    try:
        ImagingPage._on_sequence_running(page, True)
        assert not any(spin.isEnabled() for spin in geometry)
        assert setup._comparison_snr.isEnabled()  # comparison selection stays free

        # Even if a change gets through (keyboard, a queued signal), it is refused.
        before = config.get("photometry.aperture_fwhm_mult", None)
        ImagingPage._on_photometry_setting_changed(page, "photometry.aperture_fwhm_mult", 3.0)
        assert config.get("photometry.aperture_fwhm_mult", None) == before
        assert any(level == "WARN" for level, _msg in logs)

        ImagingPage._on_sequence_running(page, False)
        assert all(spin.isEnabled() for spin in geometry)
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()


def test_relative_flux_baseline_ignores_saturated_points(qapp) -> None:
    """S16: the relative-flux median (and the comparison Δmag median)
    included saturated (clipped) points."""
    panel = LightCurvePanel(view="both")
    try:
        jd = 2461315.5
        for i in range(3):
            panel.add_point("V1", jd + i * 0.01, 11.0, 0.02, relative_flux=1.0)
            panel.add_point("C1", jd + i * 0.01, 12.0, 0.02, role="comparison")
        for i in range(4):  # clipped flux recorded on saturated frames
            t = jd + (3 + i) * 0.01
            panel.add_point("V1", t, 10.0, 0.02, saturated=True, relative_flux=2.0)
            panel.add_point("C1", t, 11.0, 0.02, saturated=True, role="comparison")
        _x, dmag = panel._series["C1"]["curve"].getData()
        assert list(dmag[:3]) == pytest.approx([0.0, 0.0, 0.0])  # +1.0 on 0.4.2
        panel._relative_flux.setChecked(True)
        _x, y = panel._series["V1"]["curve"].getData()
        assert list(y[:3]) == pytest.approx([1.0, 1.0, 1.0])  # 0.5 on 0.4.2
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()


def test_nonpositive_flux_baseline_clears_series(qapp) -> None:
    """S16: with no positive baseline the magnitudes stayed on screen under
    the relative-flux axis."""
    panel = LightCurvePanel(view="target")
    try:
        for i in range(3):
            panel.add_point("V1", 2461315.5 + i * 0.01, 14.0, 0.2, relative_flux=-0.1)
        panel._relative_flux.setChecked(True)
        x, y = panel._series["V1"]["curve"].getData()
        assert x is None or len(x) == 0
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
