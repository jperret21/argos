"""Mount card tracking button (H6), offscreen Qt. One test function."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.ui.widgets.mount_dock import MountDock  # noqa: E402


def test_tracking_button_never_claims_tracking_without_a_poll() -> None:
    """H6: the disabled button read "Tracking ON" before the first poll and
    after a disconnect, unchecked."""
    app = QApplication.instance() or QApplication(["test"])
    dock = MountDock()
    try:
        btn = dock._tracking_btn
        sent: list[bool] = []
        dock.tracking_toggled.connect(sent.append)

        assert btn.text() == "Tracking"  # no state known yet
        assert not btn.isChecked() and not btn.isEnabled()

        dock.set_enabled(True)
        dock.set_position(5.5, -5.4, 40.0, 180.0, tracking=True, slewing=False)
        assert btn.text() == "Tracking ON" and btn.isChecked()

        dock.set_enabled(False)  # disconnect: the last poll is no longer the state
        assert btn.text() == "Tracking"
        assert not btn.isChecked()
        assert sent == []  # the reset sends no tracking command
    finally:
        dock.deleteLater()
        app.processEvents()
