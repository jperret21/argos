"""Startup splash (offscreen Qt, no hardware).

The splash makes two promises worth testing: the progress it shows corresponds
to checkpoints that actually exist in ``main.main``, and it never becomes a
frameless always-on-top window that outlives a failed startup and hides the
traceback.

House style from ``test_shell.py``: one widget-touching function with its own
QApplication, because pytest-qt is disabled project-wide.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos import __version__  # noqa: E402
from argos.ui import splash as splash_mod  # noqa: E402


def test_stage_fractions_are_monotonic_and_end_at_one() -> None:
    """A bar that goes backwards is worse than no bar."""
    fractions = [fraction for _key, _label, fraction in splash_mod.STAGES]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
    assert all(0.0 <= f <= 1.0 for f in fractions)


def test_every_stage_main_reports_is_declared() -> None:
    """The splash and main.py must agree on the checkpoint names.

    Reading them out of main.py's source keeps this honest: renaming a stage
    in one place and not the other would otherwise silently stall the bar.
    """
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "main.py").read_text()
    used = set(re.findall(r'stage\("([a-z]+)"\)', source))
    declared = {key for key, _label, _fraction in splash_mod.STAGES}
    assert used, "no stage() calls found in main.py — did the startup path change?"
    assert used <= declared, f"main.py reports undeclared stages: {sorted(used - declared)}"


def test_splash_walkthrough() -> None:
    """Build the splash, drive it through the stages, and close it."""
    app = QApplication.instance() or QApplication(["test"])  # noqa: F841

    widget = splash_mod.Splash()
    try:
        assert widget._progress == 0.0

        widget.stage("config")
        assert widget._progress == 0.05
        assert widget._status == "Reading configuration…"

        widget.stage("shell")
        assert widget._progress == 0.90

        # An unknown key advances the text but must not invent a number.
        widget.stage("mystery-step")
        assert widget._progress == 0.90
        assert widget._status == "mystery-step"

        widget.stage("layout")
        assert widget._progress == 1.0

        # The logo is a real asset, not a placeholder.
        assert not widget._logo.isNull()

        # fail() must close the window — otherwise a startup crash hides
        # behind a frameless, always-on-top, undismissable splash.
        widget.fail("boom")
        assert not widget.isVisible()
    finally:
        widget.close()


def test_version_is_the_package_version() -> None:
    """The splash must not carry its own copy of the version string."""
    import inspect

    assert "__version__" in inspect.getsource(splash_mod.Splash.drawContents)
    assert __version__  # and it resolves
