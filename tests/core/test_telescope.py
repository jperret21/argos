"""Tests for core/alpaca/telescope.py.

Unit tests: always run, mock alpyca's _AlpacaTelescope — no network needed.
Integration tests: require the ASCOM Alpaca Simulator on localhost:32323.
                   Automatically skipped when the simulator is not running.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.telescope import MountPosition, Telescope
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required


# ===========================================================================
# Fixtures
# ===========================================================================

ALPYCA_PATH = "seercontrol.core.alpaca.telescope._AlpacaTelescope"


@pytest.fixture
def mock_scope() -> MagicMock:
    """Mock for alpyca's Telescope object."""
    scope = MagicMock()
    scope.Connected = False
    scope.UTCDate = MagicMock()
    scope.CanSlewAsync = True
    scope.Name = "Mock Telescope"
    scope.AtPark = False
    scope.CanPark = True
    scope.Tracking = False
    scope.Slewing = False
    scope.RightAscension = 5.5753
    scope.Declination = -5.3911
    scope.Altitude = 42.5
    scope.Azimuth = 178.3
    return scope


@pytest.fixture
def telescope(mock_scope: MagicMock) -> Telescope:
    with patch(ALPYCA_PATH, return_value=mock_scope):
        scope = Telescope("localhost", 32323)
    scope._scope = mock_scope
    return scope


@pytest.fixture
def connected_telescope(mock_scope: MagicMock) -> Telescope:
    with patch(ALPYCA_PATH, return_value=mock_scope):
        scope = Telescope("localhost", 32323)
    scope._scope = mock_scope
    scope._connected = True
    return scope


# ===========================================================================
# Unit tests — connection
# ===========================================================================

class TestConnection:

    def test_connect_sets_connected_true(self, telescope, mock_scope):
        telescope.connect()
        assert mock_scope.Connected is True
        assert telescope.is_connected

    def test_connect_returns_device_name(self, telescope, mock_scope):
        mock_scope.Name = "Seestar S30 Pro"
        name = telescope.connect()
        assert name == "Seestar S30 Pro"

    def test_connect_syncs_utc(self, telescope, mock_scope):
        telescope.connect()
        assert mock_scope.UTCDate is not None

    def test_disconnect_sets_connected_false(self, connected_telescope, mock_scope):
        connected_telescope.disconnect()
        assert mock_scope.Connected is False
        assert not connected_telescope.is_connected

    def test_disconnect_handles_error_gracefully(self, connected_telescope, mock_scope):
        type(mock_scope).Connected = property(fset=MagicMock(side_effect=Exception("err")))
        connected_telescope.disconnect()
        assert not connected_telescope.is_connected

    def test_initial_state_not_connected(self):
        with patch(ALPYCA_PATH):
            scope = Telescope("localhost", 32323)
        assert not scope.is_connected


# ===========================================================================
# Unit tests — get_position
# ===========================================================================

class TestGetPosition:

    def test_returns_mount_position(self, connected_telescope, mock_scope):
        mock_scope.RightAscension = 5.5753
        mock_scope.Declination = -5.3911
        mock_scope.Altitude = 42.5
        mock_scope.Azimuth = 178.3
        mock_scope.Tracking = True
        mock_scope.Slewing = False

        pos = connected_telescope.get_position()
        assert isinstance(pos, MountPosition)

    def test_position_values(self, connected_telescope, mock_scope):
        mock_scope.RightAscension = 5.5753
        mock_scope.Declination = -5.3911
        mock_scope.Altitude = 42.5
        mock_scope.Azimuth = 178.3
        mock_scope.Tracking = True
        mock_scope.Slewing = False

        pos = connected_telescope.get_position()
        assert pos.ra == pytest.approx(5.5753)
        assert pos.dec == pytest.approx(-5.3911)
        assert pos.altitude == pytest.approx(42.5)
        assert pos.azimuth == pytest.approx(178.3)
        assert pos.tracking is True
        assert pos.slewing is False

    def test_raises_alpaca_error_on_exception(self, connected_telescope, mock_scope):
        from alpaca.exceptions import DriverException
        mock_scope.RightAscension = property(
            fget=MagicMock(side_effect=DriverException(1032, "not implemented"))
        )
        with pytest.raises(AlpacaError):
            connected_telescope.get_position()


# ===========================================================================
# Unit tests — MountPosition formatting
# ===========================================================================

class TestMountPositionFormatting:

    def _pos(self, ra=5.5753, dec=-5.3911, alt=42.5, az=178.3,
             tracking=True, slewing=False) -> MountPosition:
        return MountPosition(ra=ra, dec=dec, altitude=alt, azimuth=az,
                             tracking=tracking, slewing=slewing)

    def test_ra_str_format(self):
        pos = self._pos(ra=5.5753)
        s = pos.ra_str()
        assert "h" in s and "m" in s and "s" in s

    def test_ra_str_zero(self):
        assert self._pos(ra=0.0).ra_str() == "00h 00m 00s"

    def test_dec_str_positive(self):
        assert self._pos(dec=22.014).dec_str().startswith("+")

    def test_dec_str_negative(self):
        assert self._pos(dec=-5.391).dec_str().startswith("-")

    def test_alt_str_contains_degree_symbol(self):
        assert "°" in self._pos(alt=42.5).alt_str()

    def test_az_str_contains_degree_symbol(self):
        assert "°" in self._pos(az=178.3).az_str()


# ===========================================================================
# Unit tests — commands
# ===========================================================================

class TestCommands:

    def test_set_tracking_true(self, connected_telescope, mock_scope):
        connected_telescope.set_tracking(True)
        assert mock_scope.Tracking is True

    def test_set_tracking_false(self, connected_telescope, mock_scope):
        connected_telescope.set_tracking(False)
        assert mock_scope.Tracking is False

    def test_abort_slew_calls_abort(self, connected_telescope, mock_scope):
        connected_telescope.abort_slew()
        mock_scope.AbortSlew.assert_called_once()

    def test_park_when_not_parked(self, connected_telescope, mock_scope):
        mock_scope.AtPark = False
        connected_telescope.park()
        mock_scope.Park.assert_called_once()
        mock_scope.Unpark.assert_not_called()

    def test_park_when_already_parked_unparks_first(self, connected_telescope, mock_scope):
        mock_scope.AtPark = True
        connected_telescope.park()
        mock_scope.Unpark.assert_called_once()
        mock_scope.Park.assert_called_once()

    def test_unpark_calls_unpark(self, connected_telescope, mock_scope):
        connected_telescope.unpark()
        mock_scope.Unpark.assert_called_once()

    def test_is_parked(self, connected_telescope, mock_scope):
        mock_scope.AtPark = True
        assert connected_telescope.is_parked() is True
        mock_scope.AtPark = False
        assert connected_telescope.is_parked() is False


# ===========================================================================
# Integration tests — ASCOM Alpaca Simulator
# ===========================================================================

@simulator_required
class TestTelescopeIntegration:
    """Integration tests against the ASCOM Alpaca Simulator.

    Run the simulator first:
        https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases
    It starts on localhost:32323 by default.
    """

    @pytest.fixture
    def real_telescope(self) -> Telescope:
        scope = Telescope(SIMULATOR_HOST, SIMULATOR_PORT)
        yield scope
        try:
            scope.disconnect()
        except Exception:
            pass

    def test_connect_returns_name(self, real_telescope):
        name = real_telescope.connect()
        assert isinstance(name, str) and len(name) > 0

    def test_get_position_after_connect(self, real_telescope):
        real_telescope.connect()
        pos = real_telescope.get_position()
        assert isinstance(pos, MountPosition)
        assert 0.0 <= pos.ra < 24.0
        assert -90.0 <= pos.dec <= 90.0
        assert 0.0 <= pos.altitude <= 90.0
        assert 0.0 <= pos.azimuth < 360.0

    def test_set_tracking_on_off(self, real_telescope):
        real_telescope.connect()
        real_telescope.set_tracking(True)
        assert real_telescope.get_position().tracking is True
        real_telescope.set_tracking(False)
        assert real_telescope.get_position().tracking is False

    def test_abort_slew_does_not_raise(self, real_telescope):
        real_telescope.connect()
        real_telescope.abort_slew()
