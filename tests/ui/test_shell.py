"""R1 + R2 — smoke tests for the new Shell and the Imaging page.

PyQt6 has poor pytest interaction: a fresh QApplication per test file aborts
on teardown, and even two consecutive widget-creating tests in the same file
can SIGABRT on cleanup. We work around this by keeping all widget-touching
checks inside a single function, and reserving the second test for a path
that needs no QWidget at all (the legacy-flag class router).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from seercontrol.core.config import Config  # noqa: E402


def test_shell_and_imaging_walkthrough() -> None:
    """Build the Shell, switch modes, exercise the Imaging page docks.

    Combined into one function on purpose — PyQt6 doesn't survive multiple
    fixture-scoped widget creations under pytest.
    """
    # Keep a strong reference to the QApplication so it's not GC'd before
    # the Shell is constructed (PyQt6 aborts otherwise).
    app = QApplication.instance() or QApplication(["test"])

    from seercontrol.ui.shell import Shell
    from seercontrol.ui.pages._placeholder import PlaceholderPage
    from seercontrol.ui.pages.imaging_page import ImagingPage
    from seercontrol.ui.widgets.camera_dock import CameraDock, CaptureParams
    from seercontrol.ui.widgets.histogram_dock import HistogramDock
    from seercontrol.ui.widgets.mount_dock import MountDock

    shell = Shell(Config({}))
    try:
        # ── R1: Shell skeleton ────────────────────────────────────────
        assert set(shell._pages.keys()) == {
            "equipment", "target", "imaging", "settings",
        }
        assert shell._stack.currentIndex() == shell._page_indices["equipment"]

        for mode in ("target", "imaging", "settings", "equipment"):
            shell.sidebar.select(mode)
            assert shell._stack.currentIndex() == shell._page_indices[mode], mode

        shell.status.set_device_state("mount", "connected")
        shell.status.set_device_state("camera", "busy", info="exposing")
        shell.status.set_device_state("filterwheel", "error")
        shell.status.set_tracking(True)
        shell.status.set_action("Slewing to T CrB")
        assert shell.status.device_state("mount") == "connected"
        assert shell.status.device_state("camera") == "busy"

        # Clicking a disconnected badge jumps to Equipment.
        shell.sidebar.select("imaging")
        shell._on_badge_clicked("focuser")    # still disconnected
        assert shell._stack.currentIndex() == shell._page_indices["equipment"]

        # ── R2: Imaging page ─────────────────────────────────────────
        page = shell._pages["imaging"]
        assert isinstance(page, ImagingPage)
        assert isinstance(page._camera_dock,    CameraDock)
        assert isinstance(page._mount_dock,     MountDock)
        assert isinstance(page._histogram_dock, HistogramDock)

        params = page._camera_dock.params()
        assert isinstance(params, CaptureParams)
        assert params.exposure_s > 0
        assert params.frames > 0

        # Sequence toggle flips the internal flag.
        page._camera_dock._set_in_sequence(True)
        assert page._camera_dock._in_sequence is True
        page._camera_dock._set_in_sequence(False)
        assert page._camera_dock._in_sequence is False

        # Camera dock signals.
        received_shots: list[bool] = []
        received_seq:   list[bool] = []
        page._camera_dock.take_shot_clicked.connect(lambda: received_shots.append(True))
        page._camera_dock.sequence_toggled.connect(received_seq.append)
        page._camera_dock.set_enabled(True)
        page._camera_dock._take_btn.click()
        page._camera_dock._seq_btn.click()   # start
        page._camera_dock._seq_btn.click()   # stop
        assert received_shots == [True]
        assert received_seq == [True, False]

        # Mount dock goto + live coords.
        captured_goto: list[tuple[float, float]] = []
        page._mount_dock.goto_clicked.connect(lambda r, d: captured_goto.append((r, d)))
        page._mount_dock.set_enabled(True)
        page._mount_dock.set_goto_fields(7.5, -12.5)
        page._mount_dock._slew_btn.click()
        assert captured_goto == [(7.5, -12.5)]
        page._mount_dock.set_position(
            ra_h=5.59, dec_d=-5.39, alt_d=42.0, az_d=180.0,
            tracking=True, slewing=False,
        )
        assert "05h" in page._mount_dock._ra_lbl.text()
        assert "42" in page._mount_dock._alt_lbl.text()

        # Imaging upward signals reach the global status bar.
        page.device_state_changed.emit("mount",  "connected", "")
        page.device_state_changed.emit("camera", "busy", "exposing")
        assert shell.status.device_state("mount")  == "connected"
        assert shell.status.device_state("camera") == "busy"

        # replace_page keeps the stack index stable across swaps.
        original_index = shell._page_indices["target"]
        replacement = PlaceholderPage("Target — replaced", sprint_name="R4 test")
        shell.replace_page("target", replacement)
        assert shell._page_indices["target"] == original_index
        assert shell._pages["target"] is replacement
    finally:
        shell.close()
        shell.deleteLater()
        app.processEvents()


def test_legacy_flag_picks_main_window_class(monkeypatch) -> None:
    """``SEERCONTROL_LEGACY=1`` must select the legacy MainWindow path.

    We assert the *class chosen* without instantiating it — the legacy window
    spins up Alpaca workers that don't survive a headless test process.
    """
    import importlib
    monkeypatch.setenv("SEERCONTROL_LEGACY", "1")
    import main as main_module
    importlib.reload(main_module)

    captured: dict[str, str] = {}

    def fake_legacy(_config):
        captured["used"] = "legacy"
        return object()

    monkeypatch.setattr(
        "seercontrol.ui.main_window.MainWindow", lambda cfg: fake_legacy(cfg)
    )
    main_module._build_window(Config({}))
    assert captured.get("used") == "legacy"
