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
    from argos.ui.widgets.filterwheel_dock import FilterWheelDock
    from argos.ui.widgets.histogram_dock import HistogramDock
    from argos.ui.widgets.mount_dock import MountDock

    shell = Shell(Config({}))
    try:
        # ── Shell skeleton: 7 workflow phases, default = connect ──────────
        assert set(shell._pages.keys()) == {
            "connect",
            "target",
            "focus",
            "photometry",
            "capture",
            "analyze",
            "settings",
        }
        assert shell._stack.currentIndex() == shell._page_indices["connect"]

        for mode in ("target", "focus", "photometry", "capture", "analyze", "settings", "connect"):
            shell.sidebar.select(mode)
            assert shell._stack.currentIndex() == shell._page_indices[mode], mode

        assert isinstance(shell._pages["connect"], ConnectionPage)
        assert isinstance(shell._pages["capture"], ImagingPage)
        assert isinstance(shell._pages["settings"], ConfigurationPage)

        # ── Status bar device states ─────────────────────────────────────
        shell.status.set_device_state("mount", "connected")
        shell.status.set_device_state("camera", "busy", info="exposing")
        assert shell.status.device_state("mount") == "connected"
        assert shell.status.device_state("camera") == "busy"

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

        # Sequence tab builds a plan from its step table.
        plan = page._sequence_panel.to_plan()
        assert len(plan.steps) >= 1
        assert plan.steps[0].count > 0

        # Mount dock goto.
        goto: list[tuple[float, float]] = []
        page._mount_dock.goto_clicked.connect(lambda r, d: goto.append((r, d)))
        page._mount_dock.set_enabled(True)
        page._mount_dock.set_goto_fields(7.5, -12.5)
        page._mount_dock._slew_btn.click()
        assert goto == [(7.5, -12.5)]

        # Filter wheel dock: populate + manual move emits the target slot.
        assert isinstance(page._filterwheel_dock, FilterWheelDock)
        page._filterwheel_dock.set_filters(["Dark", "IR", "LP"])
        page._filterwheel_dock.set_enabled(True)
        moves: list[int] = []
        page._filterwheel_dock.move_requested.connect(moves.append)
        page._filterwheel_dock._combo.setCurrentIndex(2)  # LP
        page._filterwheel_dock._move_btn.click()
        assert moves == [2]

        # Workflow scaffolds: the right types, and the deep-link into Capture.
        from argos.ui.pages.phase_scaffold import AnalyzeLauncher, PhaseScaffold

        assert isinstance(shell._pages["target"], PhaseScaffold)
        assert isinstance(shell._pages["analyze"], AnalyzeLauncher)
        shell._pages["focus"].open_controls.emit()
        assert shell._stack.currentIndex() == shell._page_indices["capture"]
        assert page._rail.tabText(page._rail.currentIndex()) == "Equipment"

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

                fake = _FakeCfg({"astrometry.database": "D05", "catalog.mag_limit": 14.0})
                dlg = AstrometrySettingsDialog(fake, awin)
                assert dlg._db_combo.currentText() == "D05"  # loaded from config
                assert dlg._mag_spin.value() == 14.0
                dlg._mag_spin.setValue(16.0)
                dlg._db_combo.setCurrentText("D80")
                dlg._on_save()  # persists + emits saved
                assert fake.saved
                assert fake.d["catalog.mag_limit"] == 16.0
                assert fake.d["astrometry.database"] == "D80"
            finally:
                awin.close()
                awin.deleteLater()

            # §6 catalog moved to the Photometry Setup window: VSX variables are
            # projected onto the solved frame + hit-tested for clicks there.
            from argos.core.catalog import VariableStar
            from argos.ui.panels.photometry_setup_window import (
                PhotometrySetupWindow,
            )

            psw = PhotometrySetupWindow()
            try:
                psw.load_frame(fpath)
                assert psw._green_shape == (48, 48)
                psw._wcs = frame_wcs(fields, psw._green_shape)
                on_axis = VariableStar(
                    name="TST Tau",
                    ra_deg=83.6,
                    dec_deg=22.0,
                    auid="000-XYZ-001",
                    var_type="EA",
                    category="Variable",
                    max_mag="12.0 V",
                    min_mag="14.0 V",
                    period=1.5,
                )
                off_frame = VariableStar(name="FAR", ra_deg=120.0, dec_deg=-40.0)
                psw._variables = [on_axis, off_frame]
                psw._project_variables()
                # On-axis → reference pixel (CRPIX-1 ≈ 23.5); off-frame → None.
                assert psw._var_green[0] is not None and psw._var_green[1] is None
                vx, vy = psw._var_green[0]
                assert abs(vx - 23.5) < 1.0 and abs(vy - 23.5) < 1.0
                # Markers shown on the viewer once at least one is on-frame.
                assert psw._viewer._catalog_item.isVisible()
                # Hit-test: near the on-axis marker → its index; far → None.
                assert psw._nearest_variable(vx + 1.0, vy + 1.0) == 0
                assert psw._nearest_variable(2.0, 2.0) is None
            finally:
                psw.close()
                psw.deleteLater()

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
