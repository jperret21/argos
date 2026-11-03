"""Observe capture cards (Focuser, Camera): hardware-safety states, offscreen Qt."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from argos.core.session.types import FocuserState  # noqa: E402
from argos.ui.pages.imaging_page import ImagingPage  # noqa: E402
from argos.ui.widgets.camera_dock import CameraDock  # noqa: E402
from argos.ui.widgets.focuser_dock import FocuserDock  # noqa: E402
from argos.workers.camera_service import CameraState  # noqa: E402


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


def test_camera_lock_hint_names_the_owner(qapp) -> None:
    """H15: a stand-alone autofocus locked the Camera card with the text
    "Sequence running", sending the observer looking for a sequence to stop."""
    dock = CameraDock()
    try:
        actions: list[str] = []
        page = SimpleNamespace(
            _camera_dock=dock, action_changed=SimpleNamespace(emit=actions.append)
        )

        ImagingPage._on_camera_state(page, CameraState.AUTOFOCUS)
        assert not dock._lock_hint.isHidden()
        assert "Autofocus" in dock._lock_hint.text()
        assert "Sequence" not in dock._lock_hint.text()

        ImagingPage._on_camera_state(page, CameraState.SEQUENCE)
        assert dock._lock_hint.text() == "Sequence running — the sequence owns the camera."

        ImagingPage._on_camera_state(page, CameraState.IDLE)
        assert dock._lock_hint.isHidden()
    finally:
        dock.deleteLater()
        qapp.processEvents()


def test_camera_offset_and_binning_reach_the_driver_once_typed(qapp) -> None:
    """H11: typing "35" in Offset wrote offset 3, then 35, to the camera
    (a synchronous driver PUT each time, allowed during Live)."""
    dock = CameraDock()
    try:
        offsets: list[int] = []
        bins: list[int] = []
        dock.offset_changed.connect(offsets.append)
        dock.binning_changed.connect(bins.append)
        dock.set_offset_support(0, 300, 10)
        dock.set_binning_support(4, 1)
        offsets.clear()
        bins.clear()

        dock._offset_spin.selectAll()
        QTest.keyClicks(dock._offset_spin, "35")
        assert offsets == []
        QTest.keyClick(dock._offset_spin, Qt.Key.Key_Return)
        assert offsets == [35]

        dock._bin_spin.selectAll()
        QTest.keyClicks(dock._bin_spin, "2")
        QTest.keyClick(dock._bin_spin, Qt.Key.Key_Return)
        assert bins == [2]

        # Take shot clicked with a value still typed (no Enter; a click does
        # not take the focus on macOS): the typed offset is applied first.
        events: list[object] = []
        dock.offset_changed.connect(lambda v: events.append(("offset", v)))
        dock.take_shot_clicked.connect(lambda: events.append("take"))
        dock.set_enabled(True)
        dock._offset_spin.selectAll()
        QTest.keyClicks(dock._offset_spin, "40")
        dock._take_btn.click()
        assert events == [("offset", 40), "take"]
    finally:
        dock.deleteLater()
        qapp.processEvents()
