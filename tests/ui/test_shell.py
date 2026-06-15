"""Smoke tests for the 3-mode Shell and the Acquisition (Imaging) page.

PyQt6 has poor pytest interaction: multiple widget-creating tests can SIGABRT
on teardown, so all widget-touching checks live inside a single function.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from seercontrol.core.config import Config  # noqa: E402


def test_shell_three_mode_walkthrough() -> None:
    """Build the Shell, switch the 3 modes, exercise the key pages/docks."""
    # Strong reference to the QApplication so it isn't GC'd before the Shell.
    app = QApplication.instance() or QApplication(["test"])

    from seercontrol.ui.pages.configuration_page import ConfigurationPage
    from seercontrol.ui.pages.connection_page import ConnectionPage
    from seercontrol.ui.pages.imaging_page import ImagingPage
    from seercontrol.ui.panels.stellarium_card import StellariumCard
    from seercontrol.ui.shell import Shell
    from seercontrol.ui.widgets.camera_dock import CameraDock, CaptureParams
    from seercontrol.ui.widgets.filterwheel_dock import FilterWheelDock
    from seercontrol.ui.widgets.histogram_dock import HistogramDock
    from seercontrol.ui.widgets.mount_dock import MountDock

    shell = Shell(Config({}))
    try:
        # ── Shell skeleton: 3 modes, default = connection ────────────────
        assert set(shell._pages.keys()) == {"connection", "acquisition", "configuration"}
        assert shell._stack.currentIndex() == shell._page_indices["connection"]

        for mode in ("acquisition", "configuration", "connection"):
            shell.sidebar.select(mode)
            assert shell._stack.currentIndex() == shell._page_indices[mode], mode

        assert isinstance(shell._pages["connection"], ConnectionPage)
        assert isinstance(shell._pages["acquisition"], ImagingPage)
        assert isinstance(shell._pages["configuration"], ConfigurationPage)

        # ── Status bar device states ─────────────────────────────────────
        shell.status.set_device_state("mount", "connected")
        shell.status.set_device_state("camera", "busy", info="exposing")
        assert shell.status.device_state("mount") == "connected"
        assert shell.status.device_state("camera") == "busy"

        # Clicking a disconnected badge jumps to Connection.
        shell.sidebar.select("acquisition")
        shell._on_badge_clicked("focuser")  # still disconnected
        assert shell._stack.currentIndex() == shell._page_indices["connection"]

        # ── Acquisition page docks ───────────────────────────────────────
        page = shell._pages["acquisition"]
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

        # Open FITS → a floating analysis window (the live viewer is untouched).
        import tempfile

        import numpy as np
        from astropy.io import fits

        from seercontrol.ui.analysis_window import AnalysisWindow

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
                from seercontrol.core.imaging.platesolve import frame_wcs, wcs_grid

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
                awin._update_astrometry_overlay()
                awin._viewer.set_astrometry_enabled(True)
                awin._histogram.set_astrometry_available(True)
                awin._histogram.set_astrometry_checked(True)
                awin._remeasure_selection()  # clicked star now reports RA/Dec
                assert "RA" in awin._viewer._sel_label.text()
            finally:
                awin.close()
                awin.deleteLater()

        # §6 live-frame astrometry overlay path (toolbar Solve → grid on viewer).
        from seercontrol.core.imaging.platesolve import frame_wcs as _frame_wcs

        page._green_shape = (48, 48)
        page._viewer.display(np.zeros((48, 48), np.uint16))
        page._wcs = _frame_wcs(
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
        assert page._wcs is not None
        page._update_astrometry_overlay()
        page._viewer.set_astrometry_enabled(True)
        page._clear_astrometry()  # a goto/slew invalidates the solve
        assert page._wcs is None

        # Imaging upward signals reach the global status bar.
        page.device_state_changed.emit("camera", "busy", "exposing")
        assert shell.status.device_state("camera") == "busy"

        # ── Connection page: Stellarium card + connect intents ───────────
        conn = shell._pages["connection"]
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
