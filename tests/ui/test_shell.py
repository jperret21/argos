"""Smoke tests for the 3-mode Shell and the Acquisition (Imaging) page.

PyQt6 has poor pytest interaction: multiple widget-creating tests can SIGABRT
on teardown, so all widget-touching checks live inside a single function.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.core.config import Config  # noqa: E402


def test_shell_three_mode_walkthrough() -> None:
    """Build the Shell, switch the 3 modes, exercise the key pages/docks."""
    # Strong reference to the QApplication so it isn't GC'd before the Shell.
    app = QApplication.instance() or QApplication(["test"])

    from argos.ui.pages.configuration_page import ConfigurationPage
    from argos.ui.pages.connection_page import ConnectionPage
    from argos.ui.pages.imaging_page import ImagingPage
    from argos.ui.panels.stellarium_card import StellariumCard
    from argos.ui.shell import Shell
    from argos.ui.widgets.camera_dock import CameraDock, CaptureParams
    from argos.ui.widgets.histogram_dock import HistogramDock
    from argos.ui.widgets.mount_dock import MountDock

    shell = Shell(Config({}))
    try:
        # ── Shell skeleton: 5 modes (NINA-style), default = connect ───────
        assert set(shell._pages.keys()) == {
            "connect",
            "capture",
            "sequencer",
            "analyze",
            "settings",
        }
        assert shell._stack.currentIndex() == shell._page_indices["connect"]

        for mode in ("capture", "sequencer", "analyze", "settings", "connect"):
            shell.sidebar.select(mode)
            assert shell._stack.currentIndex() == shell._page_indices[mode], mode

        assert isinstance(shell._pages["connect"], ConnectionPage)
        assert isinstance(shell._pages["capture"], ImagingPage)
        assert isinstance(shell._pages["settings"], ConfigurationPage)

        # ── Menu bar: Astrometry menu opens the shared settings dialog ────
        from argos.ui.widgets import astrometry_settings as _astro_mod

        menus = {a.menu().title(): a.menu() for a in shell.menuBar().actions() if a.menu()}
        assert "Astrometry" in menus and "Photometry" in menus
        astro_actions = {act.text(): act for act in menus["Astrometry"].actions()}
        assert {"Solve frame", "Auto-solve", "Plate solving…", "Catalog…"} <= set(astro_actions)
        phot_labels = [act.text() for act in menus["Photometry"].actions()]
        assert "Light curve…" in phot_labels and "Re-run subs…" in phot_labels

        # The checkable Auto-solve action is the single UI for the policy: the
        # page's sequence-arming signal routes through it into the controller.
        shell._pages["capture"].auto_solve_armed.emit(True)
        assert shell._auto_solve_action.isChecked()
        assert shell._engine.astrometry.auto is True
        shell._pages["capture"].auto_solve_armed.emit(False)
        assert shell._engine.astrometry.auto is False

        # Triggering "Catalog…" builds the dialog on its tab (exec() stubbed so
        # the offscreen test never blocks on a modal loop).
        opened: list = []
        orig_exec = _astro_mod.AstrometrySettingsDialog.exec
        _astro_mod.AstrometrySettingsDialog.exec = lambda self: (opened.append(self), 0)[1]
        try:
            astro_actions["Catalog…"].trigger()
        finally:
            _astro_mod.AstrometrySettingsDialog.exec = orig_exec
        assert len(opened) == 1
        catalog_dlg = opened[0]
        assert catalog_dlg._tabs.currentIndex() == 1  # opened on the Catalog tab

        # Saving the dialog drops the engine's per-field catalog cache so the new
        # query parameters take effect on the live field (unsolved here → the
        # refetch clears state and no-ops on the network side).
        shell._engine._catalog_centre = (10.0, 20.0)
        shell._engine._variables = [object()]
        shell._engine._comparisons = [object()]
        catalog_dlg.saved.emit()  # wired to engine.refetch_catalog in the Shell
        assert shell._engine._catalog_centre is None
        assert shell._engine._variables == [] and shell._engine._comparisons == []
        catalog_dlg.deleteLater()

        # A target assigned while the field's VSP comps were still unknown left
        # the set comp-less ("no valid comparisons" on every frame); the catalog
        # arriving later backfills the auto-selected ensemble.
        import tempfile as _tempfile
        from pathlib import Path as _Path

        from argos.core.catalog.aavso import Band, ComparisonStar
        from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetStar
        from argos.workers.catalog_worker import CatalogResult

        with _tempfile.TemporaryDirectory() as _td:
            shell._config.set("sessions_path", str(_Path(_td) / "sessions"))
            engine = shell._engine
            engine.set_target_role(
                TargetStar(role=ROLE_TARGET, ra_deg=300.0, dec_deg=22.5, name="Var X")
            )
            tset = engine.target_set()
            assert not tset.by_role(ROLE_COMPARISON)  # no comps known yet
            engine._on_catalog(
                CatalogResult(
                    comparisons=[
                        ComparisonStar("000-AAA-001", 300.1, 22.4, "114", (Band("V", 11.4),)),
                        ComparisonStar("000-AAA-002", 299.9, 22.6, "121", (Band("V", 12.1),)),
                    ]
                )
            )
            comps = engine.target_set().by_role(ROLE_COMPARISON)
            assert len(comps) == 2 and comps[0].mags.get("V") is not None
            # The persisted set carries the backfilled ensemble too.
            reloaded = type(tset).load(engine._target_path(tset.object_name))
            assert len(reloaded.by_role(ROLE_COMPARISON)) == 2
            engine._target_set = None  # drop the tempdir-backed set

        # ── Status bar device states ─────────────────────────────────────
        shell.status.set_device_state("mount", "connected")
        shell.status.set_device_state("camera", "busy", info="exposing")
        assert shell.status.device_state("mount") == "connected"
        assert shell.status.device_state("camera") == "busy"

        # Mount geometry label — shown while the mount reports a mode,
        # hidden again on disconnect (None).
        shell.status.set_mount_mode("Alt-Az")
        assert shell.status._mode_lbl.text() == "Alt-Az"
        assert not shell.status._mode_lbl.isHidden()
        shell.status.set_mount_mode(None)
        assert shell.status._mode_lbl.isHidden()

        # Clicking a disconnected badge jumps to Connect.
        shell.sidebar.select("capture")
        shell._on_badge_clicked("focuser")  # still disconnected
        assert shell._stack.currentIndex() == shell._page_indices["connect"]

        # ── Capture page docks ───────────────────────────────────────────
        page = shell._pages["capture"]
        assert isinstance(page._camera_dock, CameraDock)
        assert isinstance(page._mount_dock, MountDock)
        assert isinstance(page._histogram_dock, HistogramDock)

        params = page._camera_dock.params()
        assert isinstance(params, CaptureParams)
        assert params.exposure_s > 0

        # Capture dock take-shot signal.
        shots: list[bool] = []
        page._camera_dock.take_shot_clicked.connect(lambda: shots.append(True))
        page._camera_dock.set_enabled(True)
        page._camera_dock._take_btn.click()
        assert shots == [True]

        # The Sequencer mode owns the plan editor; it builds a plan offline
        # and a run lights the strip + sidebar dot through the engine signals.
        seq_page = shell._pages["sequencer"]
        plan = seq_page.panel.to_plan()
        assert len(plan.steps) >= 1
        assert plan.steps[0].count > 0
        shell._engine.sequence_running.emit(True)
        assert shell._sequence_active is True and shell.status._seq_running is True
        shell._engine.sequence_running.emit(False)
        assert shell._sequence_active is False and shell.status._seq_running is False
        # Starting without a camera is refused and the button snaps back.
        seq_page.panel.set_running(True)
        seq_page._on_start(plan)
        assert seq_page.panel._running is False

        # Mount dock goto.
        goto: list[tuple[float, float]] = []
        page._mount_dock.goto_clicked.connect(lambda r, d: goto.append((r, d)))
        page._mount_dock.set_enabled(True)
        page._mount_dock.set_goto_fields(7.5, -12.5)
        page._mount_dock._slew_btn.click()
        assert goto == [(7.5, -12.5)]

        # Filter control lives in the Camera dock (no separate wheel dock):
        # a user pick emits filter_selected, and the moving cue greys the combo.
        filters: list[str] = []
        page._camera_dock.filter_selected.connect(filters.append)
        page._camera_dock.set_filter_options(["Dark", "IR", "LP"])
        page._camera_dock._filter_combo.setCurrentIndex(2)  # LP
        page._camera_dock._filter_combo.activated.emit(2)  # user pick
        assert filters == ["LP"]
        page._camera_dock.set_filter_moving(True)
        assert not page._camera_dock._filter_combo.isEnabled()
        page._camera_dock.set_filter_moving(False)
        assert page._camera_dock._filter_combo.isEnabled()
        assert "filterwheel" not in page._docks

        # Analyze is a first-class mode.
        from argos.ui.pages.analyze_page import AnalyzeScreen

        assert isinstance(shell._pages["analyze"], AnalyzeScreen)

        # Focuser dock V-curve: a sweep's live samples drive the fit + summary
        # right on the Capture page (the AF signals route through the page).
        dock = page._focuser_dock
        dock.set_autofocus_running(True)  # resets + shows the curve
        for i, (pos, hfd) in enumerate(
            [(3800, 4.0), (3900, 2.6), (4000, 1.8), (4100, 2.0), (4200, 3.1)]
        ):
            page._on_af_step(i + 1, 5, pos, hfd)
        res = dock.vcurve.result()
        assert res.method == "parabola"
        assert 3900 <= res.best_position <= 4100
        page._on_af_done(res.best_position, res.best_hfd)
        assert "Best focus" in dock.vcurve._summary.text()
        dock.set_autofocus_running(False)

        # Analyze screen: the export card surfaces the observer code (warns unset)
        # and reflects Settings once a code is configured.
        analyze = shell._pages["analyze"]
        assert "unset" in analyze._obscode_value.text()  # no code in Config({})
        shell._config.set("observer.obscode", "ABC")  # as Settings stores it (upper)
        analyze._refresh_export_info()
        assert analyze._obscode_value.text() == "ABC"
        assert analyze._band_value.text() == "TG"

        # Analyze → PhotometryWindow: a reloaded curve plots and carries the stamp.
        from argos.core.photometry.lightcurve import LcPoint, LightCurve
        from argos.ui.panels.photometry_window import PhotometryWindow

        lc = LightCurve(name="NU Ori")
        lc.append(LcPoint(jd_utc=2451545.0, mag=9.0, mag_err=0.02))
        pw = PhotometryWindow()
        try:
            pw.load_curves({"t": lc}, obscode="ABC", filt="TG")
            assert pw.lightcurve.has_data()
            assert pw.obscode == "ABC" and pw.filt == "TG"
        finally:
            pw.close()
            pw.deleteLater()

        # Open FITS → a floating analysis window (the live viewer is untouched).
        import tempfile

        import numpy as np
        from astropy.io import fits

        from argos.ui.analysis_window import AnalysisWindow

        with tempfile.TemporaryDirectory() as d:
            yy, xx = np.mgrid[0:96, 0:96]
            arr = np.full((96, 96), 500, np.float32)
            arr += 30000 * np.exp(-((xx - 40) ** 2 + (yy - 40) ** 2) / 8.0)
            arr = np.clip(arr, 0, 65535).astype(np.uint16)
            fpath = os.path.join(d, "frame.fits")
            fits.PrimaryHDU(arr).writeto(fpath)
            awin = AnalysisWindow()
            try:
                assert awin.load(fpath) is True
                assert awin._green_shape == (48, 48)
                awin._on_star_clicked(40.0, 40.0)  # click the star → measured
                assert awin._selected_green is not None

                # §6 astrometry: a synthetic WCS drives the grid + per-star RA/Dec.
                from argos.core.imaging.platesolve import frame_wcs, wcs_grid

                fields = {
                    "CRVAL1": "83.6",
                    "CRVAL2": "22.0",
                    "CRPIX1": "24.5",
                    "CRPIX2": "24.5",
                    "CD1_1": "-0.002",
                    "CD1_2": "0.0",
                    "CD2_1": "0.0",
                    "CD2_2": "0.002",
                }
                awin._wcs = frame_wcs(fields, awin._green_shape)
                assert awin._wcs is not None
                assert wcs_grid(awin._wcs, awin._green_shape).lines  # grid crosses frame
                # Apply the overlay the way a real ASTAP solve (_on_solved) does.
                from argos.core.imaging.astrometry_session import overlay_for

                awin._viewer.set_astrometry_overlay(
                    overlay_for(awin._wcs, awin._green_shape, awin._cfg),
                    awin._green_shape,
                )
                # R1: the bar "Grid" button toggles the RA/Dec grid overlay.
                awin._grid_btn.setEnabled(True)
                awin._grid_btn.setChecked(True)
                assert awin._viewer._wcs_on  # grid shown via the button
                awin._grid_btn.setChecked(False)
                assert not awin._viewer._wcs_on  # and hidden again
                awin._grid_btn.setChecked(True)
                awin._remeasure_selection()  # clicked star now reports RA/Dec
                assert "RA" in awin._viewer._sel_label.text()

                # Astrometry settings popup loads from + writes to the (shared) config.
                # (Standalone widget — exercised here with the viewer as a parent.)
                from argos.ui.widgets.astrometry_settings import (
                    AstrometrySettingsDialog,
                )

                class _FakeCfg:
                    def __init__(self, d):
                        self.d = dict(d)
                        self.saved = False

                    def get(self, k, default=None):
                        return self.d.get(k, default)

                    def set(self, k, v):
                        self.d[k] = v

                    def save(self):
                        self.saved = True

                from argos.ui.widgets.astrometry_settings import SECTION_CATALOG

                fake = _FakeCfg({"astrometry.database": "D05", "catalog.mag_limit": 14.0})
                dlg = AstrometrySettingsDialog(fake, awin, section=SECTION_CATALOG)
                assert dlg._tabs.currentIndex() == 1  # opened on the Catalog tab
                assert dlg._db_combo.currentText() == "D05"  # loaded from config
                assert dlg._mag_spin.value() == 14.0
                assert dlg._autocomp_spin.value() == 5  # default when unset in config
                dlg._mag_spin.setValue(16.0)
                dlg._db_combo.setCurrentText("D80")
                dlg._autocomp_spin.setValue(8)
                dlg._on_save()  # persists every key + emits saved
                assert fake.saved
                assert fake.d["catalog.mag_limit"] == 16.0
                assert fake.d["astrometry.database"] == "D80"
                assert fake.d["photometry.auto_comparisons"] == 8
            finally:
                awin.close()
                awin.deleteLater()

        # WS7: the live light curve is a dock in the workspace (not a floating
        # setup window). It is registered, hidden by default, and survives the
        # default layout so photometry_point can render into it during capture.
        assert "lightcurve" in page._docks
        assert ("lightcurve", "Light curve") in page._PANEL_ORDER
        assert not page._docks["lightcurve"].isVisible()  # hidden by default
        from argos.core.session.types import PhotometryPoint

        page._on_photometry_point(
            PhotometryPoint(
                key="V1", name="V1 Tau", jd=2451545.0, mag=12.3, mag_err=0.02, saturated=False
            )
        )
        assert page._lightcurve_panel.has_data()

        # §6 live-frame astrometry overlay path (controller solved → grid on viewer).
        from argos.core.imaging.astrometry_session import overlay_for
        from argos.core.imaging.platesolve import frame_wcs as _frame_wcs

        page._green_shape = (48, 48)
        page._viewer.display(np.zeros((48, 48), np.uint16))
        wcs = _frame_wcs(
            {
                "CRVAL1": "83.6",
                "CRVAL2": "22.0",
                "CRPIX1": "24.5",
                "CRPIX2": "24.5",
                "CD1_1": "-0.002",
                "CD1_2": "0.0",
                "CD2_1": "0.0",
                "CD2_2": "0.002",
            },
            (48, 48),
        )
        assert wcs is not None
        # Simulate a controller solve: seed its last-good WCS and apply the overlay
        # the way the AstrometryController.solved signal does on the page.
        page._astrometry._wcs = wcs
        page._on_astrometry_solved(wcs, overlay_for(wcs, (48, 48), page._cfg), "Solved — test")
        assert page._astrometry.wcs is not None
        page._clear_astrometry()  # a goto/slew invalidates the solve
        assert page._astrometry.wcs is None

        # Imaging upward signals reach the global status bar.
        page.device_state_changed.emit("camera", "busy", "exposing")
        assert shell.status.device_state("camera") == "busy"

        # ── Connection page: Stellarium card + connect intents ───────────
        conn = shell._pages["connect"]
        assert isinstance(conn.stellarium_card, StellariumCard)

        intents: list[tuple[str, str, int]] = []
        conn.connect_requested.connect(lambda d, h, p: intents.append((d, h, p)))
        conn._host_edit.setText("127.0.0.1")
        conn._port_spin.setValue(32323)
        conn._cards["mount"]._connect_btn.click()
        assert intents == [("mount", "127.0.0.1", 32323)]
    finally:
        shell.close()
        shell.deleteLater()
        app.processEvents()
