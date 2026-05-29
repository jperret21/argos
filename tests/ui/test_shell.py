"""Sprint R1 — smoke test for the new redesign Shell.

PyQt6 is fragile under pytest when widgets are created in many fixtures (the
Qt event-loop has to outlive every test and tests sharing a QApplication can
crash on widget cleanup). We keep the suite to one focused walk-through that
builds a single Shell, exercises every public hook, and exits cleanly.
"""

from __future__ import annotations

import os

# Headless backend MUST be set before QApplication is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from seercontrol.core.config import Config  # noqa: E402


def test_shell_walkthrough() -> None:
    """Build the Shell, switch modes, drive status setters — no crash."""
    app = QApplication.instance() or QApplication(["test"])

    from seercontrol.ui.shell import Shell
    from seercontrol.ui.pages._placeholder import PlaceholderPage

    shell = Shell(Config({}))
    try:
        # All four placeholder pages registered.
        assert set(shell._pages.keys()) == {
            "equipment", "target", "imaging", "settings",
        }

        # Default landing mode is Equipment.
        assert shell._stack.currentIndex() == shell._page_indices["equipment"]

        # Sidebar select switches the stack to the right index for every mode.
        for mode in ("target", "imaging", "settings", "equipment"):
            shell.sidebar.select(mode)
            assert shell._stack.currentIndex() == shell._page_indices[mode], mode

        # Status bar accepts state updates and round-trips them.
        shell.status.set_device_state("mount", "connected")
        shell.status.set_device_state("camera", "busy", info="exposing")
        shell.status.set_device_state("filterwheel", "error")
        shell.status.set_tracking(True)
        shell.status.set_action("Slewing to T CrB")
        assert shell.status.device_state("mount") == "connected"
        assert shell.status.device_state("camera") == "busy"

        # Click on a disconnected badge jumps back to Equipment.
        shell.sidebar.select("imaging")
        assert shell._stack.currentIndex() == shell._page_indices["imaging"]
        shell._on_badge_clicked("focuser")  # still disconnected
        assert shell._stack.currentIndex() == shell._page_indices["equipment"]

        # replace_page swaps the page widget without shifting the stack index.
        original_index = shell._page_indices["imaging"]
        replacement = PlaceholderPage("Imaging — replaced", sprint_name="R2 test")
        shell.replace_page("imaging", replacement)
        assert shell._page_indices["imaging"] == original_index
        assert shell._pages["imaging"] is replacement
        shell.sidebar.select("imaging")
        assert shell._stack.currentIndex() == original_index
    finally:
        shell.close()
        shell.deleteLater()
        app.processEvents()


def test_legacy_flag_picks_main_window_class(monkeypatch) -> None:
    """``SEERCONTROL_LEGACY=1`` must select the legacy MainWindow path.

    We assert the *class chosen* without instantiating it — the legacy window
    spins up Alpaca/Qt workers that don't survive a headless test process.
    """
    import importlib
    monkeypatch.setenv("SEERCONTROL_LEGACY", "1")
    import main as main_module
    importlib.reload(main_module)
    # Stub QApplication so _build_window doesn't try to construct widgets
    captured = {}

    def fake_legacy(_config):
        captured["used"] = "legacy"
        return object()

    monkeypatch.setattr(
        "seercontrol.ui.main_window.MainWindow", lambda cfg: fake_legacy(cfg)
    )
    main_module._build_window(Config({}))
    assert captured.get("used") == "legacy"
