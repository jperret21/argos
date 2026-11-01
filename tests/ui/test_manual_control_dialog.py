"""Manual Control (jog) dialog: every moving axis is stopped (H3), offscreen Qt.

One test function: the dialog is a top-level widget (repo rule for Qt tests).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock, call  # noqa: E402

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from argos.ui.pages.imaging_page import ImagingPage  # noqa: E402
from argos.ui.panels.manual_control_dialog import ManualControlDialog  # noqa: E402


def test_jog_dialog_stops_every_moving_axis() -> None:
    """H3: one _active_axis was tracked. Holding Up then Right and releasing
    Up stopped azimuth and left altitude slewing; focus loss stopped nothing;
    a reconnect left the dialog driving the old Telescope."""
    app = QApplication.instance() or QApplication(["test"])
    scope = MagicMock()
    dlg = ManualControlDialog(scope)
    try:
        dlg.show()

        # Diagonal jog: each released key stops its own axis.
        QTest.keyPress(dlg, Qt.Key.Key_Up)
        QTest.keyPress(dlg, Qt.Key.Key_Right)
        assert scope.move_axis.call_args_list == [call(1, 2.0), call(0, 2.0)]
        QTest.keyRelease(dlg, Qt.Key.Key_Up)
        assert scope.stop_axis.call_args_list == [call(1)]  # altitude, not azimuth
        QTest.keyRelease(dlg, Qt.Key.Key_Right)
        assert scope.stop_axis.call_args_list == [call(1), call(0)]

        # The window loses focus while a key is held: the key release goes to
        # another window, so the axis is stopped now.
        scope.reset_mock()
        QTest.keyPress(dlg, Qt.Key.Key_Left)
        QApplication.sendEvent(dlg, QEvent(QEvent.Type.WindowDeactivate))
        assert scope.stop_axis.call_args_list == [call(0)]

        # The stop button stops both axes, whatever the dialog believes.
        scope.reset_mock()
        stop_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "■")
        stop_btn.click()
        assert sorted(c.args for c in scope.stop_axis.call_args_list) == [(0,), (1,)]

        # Reopening after a reconnect drives the new Telescope.
        new_scope = MagicMock()
        page = SimpleNamespace(
            _session=SimpleNamespace(telescope=new_scope),
            _jog_dialog=dlg,
            log_message=MagicMock(),
        )
        ImagingPage._open_jog(page)
        scope.reset_mock()
        QTest.keyPress(dlg, Qt.Key.Key_Down)
        new_scope.move_axis.assert_called_once_with(1, -2.0)
        scope.move_axis.assert_not_called()

        # The mount goes away while an axis moves: the page closes the dialog,
        # which stops that axis.
        page._mount_dock = MagicMock()
        page.device_state_changed = MagicMock()
        ImagingPage._on_session_device_state(page, "mount", "disconnected", "")
        assert not dlg.isVisible()
        new_scope.stop_axis.assert_called_once_with(1)
    finally:
        dlg.deleteLater()
        app.processEvents()
