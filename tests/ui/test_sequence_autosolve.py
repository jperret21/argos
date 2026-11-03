"""A sequence arms field identification even when no WCS exists yet (S14).

One widget test per file: the whole Shell is built offscreen, as in
tests/ui/test_shell.py.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.core.config import Config  # noqa: E402


def test_sequence_arms_auto_identification_without_prior_wcs(monkeypatch) -> None:
    """Any GoTo clears the WCS, and auto-solve was armed only when a WCS
    already existed: a run started after a GoTo measured no photometry."""
    app = QApplication.instance() or QApplication(["test"])
    from argos.ui.pages import imaging_page
    from argos.ui.shell import Shell

    shell = Shell(Config({}))
    try:
        engine = shell._engine
        logs: list[tuple[str, str]] = []
        shell._acquisition.log_message.connect(lambda level, msg: logs.append((level, msg)))
        # ASTAP is installed on some machines and not on others: decide here.
        monkeypatch.setattr(imaging_page, "find_astap", lambda _p="": "/opt/astap", raising=False)
        assert engine.astrometry.wcs is None and engine.astrometry.auto is False

        # A run with Light frames: identify the field as the frames arrive.
        engine.sequence_has_light_frames = lambda: True
        engine.sequence_running.emit(True)
        assert engine.astrometry.auto is True
        assert shell._auto_solve_action.isChecked()
        engine.sequence_running.emit(False)
        assert engine.astrometry.auto is False  # the user's choice is restored

        # A calibration-only run does not plate-solve darks.
        engine.sequence_has_light_frames = lambda: False
        engine.sequence_running.emit(True)
        assert engine.astrometry.auto is False
        engine.sequence_running.emit(False)

        # Without ASTAP: one warning, not a failed solve on every frame.
        monkeypatch.setattr(imaging_page, "find_astap", lambda _p="": None, raising=False)
        engine.sequence_has_light_frames = lambda: True
        logs.clear()
        engine.sequence_running.emit(True)
        assert engine.astrometry.auto is False
        assert [level for level, msg in logs if "ASTAP" in msg] == ["WARN"]
        engine.sequence_running.emit(False)
    finally:
        shell.close()
        shell.deleteLater()
        app.processEvents()
