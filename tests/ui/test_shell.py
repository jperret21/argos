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
        assert params.frames > 0

        # Camera dock signals.
        shots: list[bool] = []
        seq: list[bool] = []
        page._camera_dock.take_shot_clicked.connect(lambda: shots.append(True))
        page._camera_dock.sequence_toggled.connect(seq.append)
        page._camera_dock.set_enabled(True)
        page._camera_dock._take_btn.click()
        page._camera_dock._seq_btn.click()  # start
        page._camera_dock._seq_btn.click()  # stop
        assert shots == [True]
        assert seq == [True, False]

        # Mount dock goto.
        goto: list[tuple[float, float]] = []
        page._mount_dock.goto_clicked.connect(lambda r, d: goto.append((r, d)))
        page._mount_dock.set_enabled(True)
        page._mount_dock.set_goto_fields(7.5, -12.5)
        page._mount_dock._slew_btn.click()
        assert goto == [(7.5, -12.5)]

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
