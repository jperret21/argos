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
    """Config stub — the page only reads and writes through get/set.

    ``writes`` records every ``set`` (the real Config rewrites its JSON file
    on each one).
    """

    def __init__(self):
        self._values = {}
        self.writes = []

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value
        self.writes.append((key, value))

    def save(self):
        pass

    @property
    def sessions_path(self):
        return "/tmp/sessions"

    # Read and written by the Connection page, through set() as in Config.
    @property
    def alpaca_host(self):
        return self.get("alpaca.host", "")

    @alpaca_host.setter
    def alpaca_host(self, value):
        self.set("alpaca.host", value)

    @property
    def alpaca_port(self):
        return self.get("alpaca.port", 32323)

    @alpaca_port.setter
    def alpaca_port(self, value):
        self.set("alpaca.port", value)

    def written(self, key):
        return [value for k, value in self.writes if k == key]


#: The one unvalidated-profile warning (Q-C2), on both pages.
_NOT_VALIDATED = "Not validated on this hardware: do not use it for scientific photometry."


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
        # S29: Settings said "never run on this hardware", which contradicted
        # both the profile docs (usable, but flagged) and the Connection page.
        warning = page._scope_warning.text()
        assert warning.startswith(_NOT_VALIDATED)
        assert "never run" not in warning
        assert "Bayer" in warning

        # The Connection page says the same, with the same picker labels, and
        # its camera card names the active profile's sensor (it was hard-coded
        # to the S30 Pro's IMX585).
        from argos.ui.pages.connection_page import ConnectionPage

        connection = ConnectionPage(config)
        assert connection._telescope_warning.text().startswith(_NOT_VALIDATED)
        combo = connection._telescope_combo
        assert {combo.itemData(i): combo.itemText(i) for i in range(combo.count())} == labels
        assert catalog.get("s50").sensor == "IMX462"
        assert connection._cards["camera"]._hint_lbl.text() == "Telephoto IMX462 sensor"
        assert connection.apply_telescope_profile("s30pro")
        assert connection._cards["camera"]._hint_lbl.text() == "Telephoto IMX585 sensor"
        connection.deleteLater()

        # Back to the validated profile: the warning clears.
        page._scope_combo.setCurrentIndex(page._scope_combo.findData("s30pro"))
        assert page._scope_warning.text() == ""
        assert active.profile().key == "s30pro"

        # A saved observing site is separate from the observer name and can
        # become the active/default site in one explicit action.
        page._site_name_edit.setText("Berkeley roof")
        page._lat_spin.setValue(37.8715)
        page._lon_spin.setValue(-122.2730)
        page._elev_spin.setValue(52.0)
        page._favorite_name_edit.setText("Berkeley roof")
        page._save_current_favorite()
        assert page._favorites_combo.count() == 1
        page._site_name_edit.setText("Elsewhere")
        page._lat_spin.setValue(0.0)
        page._use_selected_favorite()
        assert page._site_name_edit.text() == "Berkeley roof"
        assert page._lat_spin.value() == 37.8715

        # Local diagnostics are off by default and remain an explicit opt-in;
        # ASTAP's local database directory is persisted separately from its
        # database set.
        assert page._diagnostics_chk.isChecked() is False
        page._diagnostics_chk.setChecked(True)
        assert config.get("diagnostics.enabled") is True
        assert config.get("diagnostics.local_opt_in_v1") is True
        page._diagnostics_chk.setChecked(False)
        assert config.get("diagnostics.enabled") is False
        page._astap_db_edit.setText("/Volumes/Astro/astap")
        page._save_astrometry()
        assert config.get("astrometry.database_path") == "/Volumes/Astro/astap"

        # H11: a typed value is committed when the edit is done (Enter or
        # focus out), not on every keystroke: "48" wrote latitude 4, then 48.
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        config.writes.clear()
        page._lat_spin.selectAll()
        QTest.keyClicks(page._lat_spin, "48")
        assert config.written("site.latitude") == []
        QTest.keyClick(page._lat_spin, Qt.Key.Key_Return)
        assert config.written("site.latitude") == [48.0]
        # A button click does not take the focus on macOS: a value typed
        # without Enter must still be the one a click uses.
        page._lon_spin.selectAll()
        QTest.keyClicks(page._lon_spin, "2")
        page._favorite_name_edit.setText("Typed")
        page._save_current_favorite()
        typed = next(f for f in config.get("site.favorites") if f["name"] == "Typed")
        assert (typed["latitude"], typed["longitude"]) == (48.0, 2.0)

        # The Alpaca address was saved, and probed by the network monitor,
        # one keystroke at a time ("1", "19", "192", …).
        connection = ConnectionPage(config)
        config.writes.clear()
        QTest.keyClicks(connection._host_edit, "192.168.1.5")
        assert config.written("alpaca.host") == []
        QTest.keyClick(connection._host_edit, Qt.Key.Key_Return)
        assert config.written("alpaca.host") == ["192.168.1.5"]
        connection._port_spin.selectAll()
        QTest.keyClicks(connection._port_spin, "4700")
        QTest.keyClick(connection._port_spin, Qt.Key.Key_Return)
        assert config.written("alpaca.port") == [4700]
        endpoints: list[tuple[str, int]] = []
        connection.connect_all_requested.connect(lambda h, p: endpoints.append((h, p)))
        connection._port_spin.selectAll()
        QTest.keyClicks(connection._port_spin, "11111")
        connection._start_connect_btn.click()  # no Enter first
        assert endpoints == [("192.168.1.5", 11111)]
        # A discovered address is saved without any edit.
        connection.set_discovered_address("10.0.0.7", 32323)
        assert config.alpaca_host == "10.0.0.7"

        # H12: Connect with no address said nothing; an error showed only
        # its first 48 characters, on the card and in the status bar.
        endpoints.clear()
        connection._host_edit.clear()
        connection._start_connect_btn.click()
        assert endpoints == []
        assert not connection._endpoint_hint.isHidden()
        assert "IP address" in connection._endpoint_hint.text()
        connection._host_edit.setText("10.0.0.7")
        assert connection._endpoint_hint.isHidden()
        reason = "Alpaca error 0: Cannot connect to 192.168.1.20:32323 — connection refused"
        connection.set_device_state("camera", "error", reason)
        card_status = connection._cards["camera"]._status_lbl
        assert reason in card_status.text() and card_status.wordWrap()
        connection.deleteLater()

        from argos.ui.statusbar import TopStatusBar

        bar = TopStatusBar()
        bar.set_device_state("camera", "error", reason)
        badge = bar._badges["camera"]
        assert len(badge.text()) < len(reason)  # the bar stays one line
        assert badge.toolTip() == reason
        bar.set_device_state("camera", "connected", "")
        assert badge.toolTip() == ""
        bar.deleteLater()
    finally:
        active.set_profile(before)
