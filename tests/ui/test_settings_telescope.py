"""The Settings telescope picker (offscreen Qt, no hardware).

The picker is the only place an observer declares what Argos is driving, so it
has to be honest about two things: the specs it shows must come from the
profile rather than a second copy of the numbers, and an unvalidated profile
must say so before anyone trusts a magnitude computed with it.

Like ``test_shell.py``, every widget-touching check lives in one function:
pytest-qt is disabled project-wide (``-p no:qt``) because PyQt6 can SIGABRT
when several tests each build and tear down widgets.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.core.hardware import active, catalog  # noqa: E402


class _FakeConfig:
    """Config stub — the page only reads and writes through get/set."""

    def __init__(self):
        self._values = {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value

    @property
    def sessions_path(self):
        return "/tmp/sessions"


def test_telescope_picker_walkthrough() -> None:
    """Build the Settings page and exercise the telescope card end to end."""
    app = QApplication.instance() or QApplication(["test"])  # noqa: F841

    from argos.ui.pages.configuration_page import ConfigurationPage

    before = active.profile()
    try:
        config = _FakeConfig()
        page = ConfigurationPage(config)

        # Every registered profile is offered, and the unvalidated ones say so.
        offered = {page._scope_combo.itemData(i) for i in range(page._scope_combo.count())}
        assert offered == set(catalog.keys())
        labels = {
            page._scope_combo.itemData(i): page._scope_combo.itemText(i)
            for i in range(page._scope_combo.count())
        }
        assert "unvalidated" in labels["s50"]
        assert "unvalidated" not in labels["s30pro"]

        # The specs line is derived from the profile: f/5.3, not the f/3.2 the
        # FITS writer used to claim, and the documented 3.74″/px.
        assert "f/5.3" in page._scope_specs.text()
        assert "3.74″/px" in page._scope_specs.text()
        assert page._scope_warning.text() == ""

        # Picking another model persists it, applies it, and re-derives the specs.
        page._scope_combo.setCurrentIndex(page._scope_combo.findData("s50"))
        assert config.get(active.CFG_PROFILE) == "s50"
        assert active.profile().key == "s50"
        assert "f/5.0" in page._scope_specs.text()

        # …and it warns, naming the caveat that matters most for photometry.
        warning = page._scope_warning.text()
        assert "Unvalidated" in warning
        assert "Bayer" in warning

        # Back to the validated profile: the warning clears.
        page._scope_combo.setCurrentIndex(page._scope_combo.findData("s30pro"))
        assert page._scope_warning.text() == ""
        assert active.profile().key == "s30pro"
    finally:
        active.set_profile(before)
