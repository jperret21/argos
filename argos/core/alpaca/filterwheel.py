"""ASCOM Alpaca filter wheel wrapper — backed by alpyca.

Seestar S30 Pro filter wheel (device 0):
    Position 0 — Dark   (closed / calibration)
    Position 1 — IR     (infrared pass)
    Position 2 — LP     (light pollution filter)

All methods are synchronous. Run from a QThread worker only.
"""

from __future__ import annotations

import logging

from alpaca.exceptions import DriverException
from alpaca.filterwheel import FilterWheel as _AlpacaFilterWheel

from argos.core.alpaca.client import AlpacaError

logger = logging.getLogger(__name__)

POSITION_NAMES = {0: "Dark", 1: "IR", 2: "LP"}
POSITION_COUNT = 3


def _wrap(exc: Exception) -> AlpacaError:
    if isinstance(exc, DriverException):
        return AlpacaError(exc.number, str(exc))
    return AlpacaError(0, str(exc))


class FilterWheel:
    """ASCOM Alpaca filter wheel controller.

    Args:
        host: IP address of the Seestar.
        port: Alpaca HTTP port (32323).
    """

    def __init__(self, host: str, port: int) -> None:
        self._fw = _AlpacaFilterWheel(f"{host}:{port}", 0)
        self._connected = False

    def connect(self) -> None:
        """Connect to the filter wheel.

        Raises:
            AlpacaError: Connection or device error.
        """
        try:
            self._fw.Connected = True
            self._connected = True
            pos = self.get_position()
            logger.info(
                "FilterWheel connected  current position=%d (%s)",
                pos, POSITION_NAMES.get(pos, "?"),
            )
        except AlpacaError:
            raise
        except Exception as exc:
            raise _wrap(exc) from exc

    def disconnect(self) -> None:
        """Disconnect from the filter wheel."""
        try:
            self._fw.Connected = False
        except Exception as exc:
            logger.warning("FilterWheel disconnect error: %s", exc)
        finally:
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_position(self) -> int:
        """Return the current filter position (0–2).

        Returns -1 while the wheel is moving.

        Raises:
            AlpacaError: Device error.
        """
        try:
            return int(self._fw.Position)
        except Exception as exc:
            raise _wrap(exc) from exc

    def set_position(self, position: int) -> None:
        """Command a filter change.

        The move is asynchronous — the wheel returns immediately and
        ``get_position()`` returns -1 while moving.

        Args:
            position: Target position (0=Dark, 1=IR, 2=LP).

        Raises:
            AlpacaError: Invalid position or device error.
        """
        if position not in POSITION_NAMES:
            raise AlpacaError(0, f"Invalid filter position {position} — must be 0, 1, or 2")
        try:
            logger.info(
                "FilterWheel moving to position %d (%s)",
                position, POSITION_NAMES[position],
            )
            self._fw.Position = position
        except Exception as exc:
            raise _wrap(exc) from exc

    def position_name(self) -> str:
        """Return the name of the current filter position."""
        pos = self.get_position()
        if pos == -1:
            return "Moving…"
        return POSITION_NAMES.get(pos, f"Pos {pos}")
