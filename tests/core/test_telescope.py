"""Tests for core/alpaca/telescope.py.

Unit tests: run always, use mocked AlpacaClient — no network needed.
Integration tests: require the ASCOM Alpaca Simulator on localhost:32323.
                   Automatically skipped when the simulator is not running.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from seercontrol.core.alpaca.client import AlpacaClient, AlpacaConnectionError, AlpacaError
from seercontrol.core.alpaca.telescope import MountPosition, Telescope
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_client() -> MagicMock:
    """AlpacaClient with all methods mocked."""
    client = MagicMock(spec=AlpacaClient)
    client.host = "localhost"
    client.port = 4700
    return client


@pytest.fixture
def telescope(mock_client: MagicMock) -> Telescope:
    return Telescope(mock_client)


@pytest.fixture
def connected_telescope(mock_client: MagicMock) -> Telescope:
    """Telescope already connected (connect() pre-called)."""
    mock_client.get.return_value = "Seestar S30 Pro"
    scope = Telescope(mock_client)
    scope.connect()
    mock_client.reset_mock()
    return scope


# ===========================================================================
# Unit tests — connection
# ===========================================================================

class TestConnection:

    def test_connect_sends_put_connected_true(self, telescope, mock_client):
        mock_client.get.return_value = "Seestar S30 Pro"
        telescope.connect()
        mock_client.put.assert_called_once_with(
            "telescope", 0, "connected", Connected="True"
        )

    def test_connect_returns_device_name(self, telescope, mock_client):
        mock_client.get.return_value = "Seestar S30 Pro"
        name = telescope.connect()
        assert name == "Seestar S30 Pro"

    def test_connect_sets_is_connected(self, telescope, mock_client):
        mock_client.get.return_value = "Test Mount"
        assert not telescope.is_connected
        telescope.connect()
        assert telescope.is_connected

    def test_disconnect_sends_put_connected_false(self, connected_telescope, mock_client):
        connected_telescope.disconnect()
        mock_client.put.assert_called_once_with(
            "telescope", 0, "connected", Connected="False"
        )

    def test_disconnect_clears_is_connected(self, connected_telescope):
        connected_telescope.disconnect()
        assert not connected_telescope.is_connected

    def test_disconnect_handles_alpaca_error_gracefully(self, connected_telescope, mock_client):
        mock_client.put.side_effect = AlpacaError(1, "already disconnected")
        connected_telescope.disconnect()  # should not raise
        assert not connected_telescope.is_connected


# ===========================================================================
# Unit tests — get_position
# ===========================================================================

class TestGetPosition:

    def _setup_mock_position(self, mock_client: MagicMock) -> None:
        """Configure mock to return realistic position values."""
        def get_side_effect(device, number, attribute):
            values = {
                "rightascension": 5.5753,
                "declination": -5.3911,
                "altitude": 42.5,
                "azimuth": 178.3,
                "tracking": True,
                "slewing": False,
            }
            return values[attribute]
        mock_client.get.side_effect = get_side_effect

    def test_get_position_returns_mount_position(self, connected_telescope, mock_client):
        self._setup_mock_position(mock_client)
        pos = connected_telescope.get_position()
        assert isinstance(pos, MountPosition)

    def test_get_position_values(self, connected_telescope, mock_client):
        self._setup_mock_position(mock_client)
        pos = connected_telescope.get_position()
        assert pos.ra == pytest.approx(5.5753)
        assert pos.dec == pytest.approx(-5.3911)
        assert pos.altitude == pytest.approx(42.5)
        assert pos.azimuth == pytest.approx(178.3)
        assert pos.tracking is True
        assert pos.slewing is False

    def test_get_position_calls_all_six_attributes(self, connected_telescope, mock_client):
        self._setup_mock_position(mock_client)
        connected_telescope.get_position()
        called_attrs = [c.args[2] for c in mock_client.get.call_args_list]
        assert set(called_attrs) == {
            "rightascension", "declination", "altitude",
            "azimuth", "tracking", "slewing"
        }

    def test_get_position_raises_on_alpaca_error(self, connected_telescope, mock_client):
        mock_client.get.side_effect = AlpacaConnectionError("localhost", 4700)
        with pytest.raises(AlpacaConnectionError):
            connected_telescope.get_position()


# ===========================================================================
# Unit tests — MountPosition formatting
# ===========================================================================

class TestMountPositionFormatting:

    def _make_pos(self, ra=5.5753, dec=-5.3911, alt=42.5, az=178.3,
                  tracking=True, slewing=False) -> MountPosition:
        return MountPosition(ra=ra, dec=dec, altitude=alt, azimuth=az,
                             tracking=tracking, slewing=slewing)

    def test_ra_str_format(self):
        pos = self._make_pos(ra=5.5753)
        s = pos.ra_str()
        assert "h" in s and "m" in s and "s" in s

    def test_ra_str_zero(self):
        pos = self._make_pos(ra=0.0)
        assert pos.ra_str() == "00h 00m 00s"

    def test_dec_str_positive(self):
        pos = self._make_pos(dec=22.014)
        s = pos.dec_str()
        assert s.startswith("+")

    def test_dec_str_negative(self):
        pos = self._make_pos(dec=-5.3911)
        s = pos.dec_str()
        assert s.startswith("-")

    def test_alt_str_contains_degree(self):
        pos = self._make_pos(alt=42.5)
        assert "°" in pos.alt_str()

    def test_az_str_contains_degree(self):
        pos = self._make_pos(az=178.3)
        assert "°" in pos.az_str()


# ===========================================================================
# Unit tests — commands
# ===========================================================================

class TestCommands:

    def test_slew_to_sends_correct_put(self, connected_telescope, mock_client):
        connected_telescope.slew_to(ra=5.5753, dec=-5.3911)
        mock_client.put.assert_called_once_with(
            "telescope", 0, "slewtocoordinatesasync",
            RightAscension="5.5753",
            Declination="-5.3911",
        )

    def test_set_tracking_true(self, connected_telescope, mock_client):
        connected_telescope.set_tracking(True)
        mock_client.put.assert_called_once_with(
            "telescope", 0, "tracking", Tracking="True"
        )

    def test_set_tracking_false(self, connected_telescope, mock_client):
        connected_telescope.set_tracking(False)
        mock_client.put.assert_called_once_with(
            "telescope", 0, "tracking", Tracking="False"
        )

    def test_abort_slew(self, connected_telescope, mock_client):
        connected_telescope.abort_slew()
        mock_client.put.assert_called_once_with("telescope", 0, "abortslew")

    def test_park_when_not_parked(self, connected_telescope, mock_client):
        # atpark returns False → park is sent directly, no unpark first
        mock_client.get.return_value = False
        connected_telescope.park()
        mock_client.put.assert_called_once_with("telescope", 0, "park")

    def test_park_when_already_parked_sends_unpark_first(self, connected_telescope, mock_client):
        # atpark returns True → unpark then park (arm was opened via native app)
        mock_client.get.return_value = True
        connected_telescope.park()
        calls = mock_client.put.call_args_list
        assert calls[0] == call("telescope", 0, "unpark")
        assert calls[1] == call("telescope", 0, "park")


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
    def real_client(self) -> AlpacaClient:
        return AlpacaClient(host=SIMULATOR_HOST, port=SIMULATOR_PORT)

    @pytest.fixture
    def real_telescope(self, real_client: AlpacaClient) -> Telescope:
        scope = Telescope(real_client)
        yield scope
        try:
            scope.disconnect()
        except Exception:
            pass
        real_client.close()

    def test_connect_returns_name(self, real_telescope: Telescope):
        name = real_telescope.connect()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_get_position_after_connect(self, real_telescope: Telescope):
        real_telescope.connect()
        pos = real_telescope.get_position()
        assert isinstance(pos, MountPosition)
        assert 0.0 <= pos.ra < 24.0
        assert -90.0 <= pos.dec <= 90.0
        assert 0.0 <= pos.altitude <= 90.0
        assert 0.0 <= pos.azimuth < 360.0

    def test_set_tracking_on_off(self, real_telescope: Telescope):
        real_telescope.connect()
        real_telescope.set_tracking(True)
        pos = real_telescope.get_position()
        assert pos.tracking is True

        real_telescope.set_tracking(False)
        pos = real_telescope.get_position()
        assert pos.tracking is False

    def test_abort_slew_does_not_raise(self, real_telescope: Telescope):
        real_telescope.connect()
        real_telescope.abort_slew()  # should not raise even if not slewing
