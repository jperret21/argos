"""Observe capture cards (Focuser, Camera): hardware-safety states, offscreen Qt."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from argos.core.session.types import FocuserState  # noqa: E402
from argos.ui.pages.imaging_page import ImagingPage  # noqa: E402
from argos.ui.widgets.focuser_dock import FocuserDock  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(["test"])
    yield app


def _button(widget, text: str) -> QPushButton:
    return next(b for b in widget.findChildren(QPushButton) if b.text() == text)


def test_focuser_card_refuses_manual_moves_during_autofocus_and_follows_max_step(qapp) -> None:
    """H10: a manual Move sent mid-sweep samples a position the autofocus
    worker did not command; the Go to range ignored the focuser's MaxStep."""
    dock = FocuserDock()
    try:
        move_btn = _button(dock, "Move")
        requested: list[int] = []
        dock.move_to_requested.connect(requested.append)
        dock.set_enabled(True)
        assert dock._goto_spin.isEnabled() and move_btn.isEnabled()

        dock.set_autofocus_running(True)
        assert not dock._goto_spin.isEnabled()
        assert not move_btn.isEnabled()
        dock._goto_spin.setValue(12_345)
        move_btn.click()
        assert requested == []  # no manual move reaches the focuser mid-sweep

        dock.set_autofocus_running(False)
        assert dock._goto_spin.isEnabled() and move_btn.isEnabled()
        # A sweep that ends after the focuser went away leaves the card disabled.
        dock.set_autofocus_running(True)
        dock.set_enabled(False)
        dock.set_autofocus_running(False)
        assert not dock._goto_spin.isEnabled() and not move_btn.isEnabled()

        # The page gives the card the focuser's MaxStep at connect: Go to
        # cannot ask for a position the driver would clamp.
        page = SimpleNamespace(_focuser_dock=dock)
        ImagingPage._on_focuser_state(
            page,
            FocuserState(
                name="Focuser", position=24_500, max_step=60_000, max_increment=1_000, absolute=True
            ),
        )
        assert dock._goto_spin.maximum() == 60_000
        assert dock._goto_spin.value() == 24_500
    finally:
        dock.deleteLater()
        qapp.processEvents()
