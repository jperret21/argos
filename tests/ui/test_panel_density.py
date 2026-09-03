"""Offscreen checks for compact, non-stretched control panels."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow, QSizePolicy, QWidget  # noqa: E402

from argos.core.config import Config  # noqa: E402
from argos.ui import design  # noqa: E402
from argos.ui.pages.configuration_page import ConfigurationPage  # noqa: E402
from argos.ui.widgets.dock_host import make_dock  # noqa: E402
from argos.ui.widgets.focuser_dock import FocuserDock  # noqa: E402
from argos.ui.widgets.sequence_panel import SequencePanel  # noqa: E402


def test_control_panels_keep_their_natural_height() -> None:
    app = QApplication.instance() or QApplication(["test"])

    host = QMainWindow()
    host.setCentralWidget(QWidget())
    focus = FocuserDock()
    dock = make_dock("Focusing", focus, object_name="test.focus")
    host.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    host.resize(720, 760)
    host.show()
    app.processEvents()
    plan = None
    settings = None

    try:
        assert focus.title() == ""  # the QDockWidget already carries the heading
        assert focus.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
        assert focus.height() < dock.widget().viewport().height() // 2

        plan = SequencePanel()
        assert plan._table.maximumHeight() == 120
        for _ in range(11):
            plan._add_row()
        assert 120 < plan._table.maximumHeight() <= 420
        assert plan._docks["source"].minimumHeight() >= 118
        assert plan._docks["plan"].minimumHeight() >= 215

        settings = ConfigurationPage(Config({}))
        settings.show()
        app.processEvents()
        page_height = settings._settings_sections.currentWidget().sizeHint().height()
        header_height = settings._settings_sections.count() * design.INPUT_HEIGHT
        assert settings._settings_sections.height() >= page_height + header_height
    finally:
        host.close()
        if plan is not None:
            plan.close()
        if settings is not None:
            settings.close()
        app.processEvents()
