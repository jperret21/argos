"""ASCOM Alpaca focuser wrapper — backed by alpyca.

Seestar S30 Pro focuser (device 0 = telephoto):
    Position range: 0 – MaxStep (read at connect time, typically 0–20000)
    Move() is asynchronous: IsMoving is True until the move completes.

All methods are synchronous. Run from a QThread worker only.
"""

from __future__ import annotations

import logging

from alpaca.exceptions import DriverException
from alpaca.focuser import Focuser as _AlpacaFocuser

from seercontrol.core.alpaca.client import AlpacaError

logger = logging.getLogger(__name__)


def _wrap(exc: Exception) -> AlpacaError:
    if isinstance(exc, DriverException):
        return AlpacaError(exc.number, str(exc))
    return AlpacaError(0, str(exc))


class Focuser:
    """ASCOM Alpaca focuser controller.

    Args:
        host: IP address of the Seestar.
        port: Alpaca HTTP port (32323).
    """

    def __init__(self, host: str, port: int) -> None:
        self._foc = _AlpacaFocuser(f"{host}:{port}", 0)
        self._connected = False
        self.max_step: int = 20000

    def connect(self) -> None:
        """Connect to the focuser and read hardware limits.

        Raises:
            AlpacaError: Connection or device error.
        """
        try:
            self._foc.Connected = True
            self._connected = True
            self.max_step = int(self._foc.MaxStep)
            pos = self.get_position()
            logger.info(
                "Focuser connected  position=%d  max_step=%d",
                pos, self.max_step,
            )
        except AlpacaError:
            raise
        except Exception as exc:
            raise _wrap(exc) from exc

    def disconnect(self) -> None:
        """Disconnect from the focuser."""
        try:
            self._foc.Connected = False
        except Exception as exc:
            logger.warning("Focuser disconnect error: %s", exc)
        finally:
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_position(self) -> int:
        """Return current focuser position (steps).

        Raises:
            AlpacaError: Device error.
        """
        try:
            return int(self._foc.Position)
        except Exception as exc:
            raise _wrap(exc) from exc

    def move_to(self, position: int) -> None:
        """Command an absolute move (asynchronous).

        The move starts immediately; poll :meth:`is_moving` until False.

        Args:
            position: Target position, clamped to [0, max_step].

        Raises:
            AlpacaError: Device error.
        """
        position = max(0, min(position, self.max_step))
        try:
            logger.info("Focuser moving to %d", position)
            self._foc.Move(position)
        except Exception as exc:
            raise _wrap(exc) from exc

    def halt(self) -> None:
        """Halt the focuser immediately.

        Raises:
            AlpacaError: Device error.
        """
        try:
            self._foc.Halt()
        except Exception as exc:
            raise _wrap(exc) from exc

    def is_moving(self) -> bool:
        """Return True while a move is in progress.

        Raises:
            AlpacaError: Device error.
        """
        try:
            return bool(self._foc.IsMoving)
        except Exception as exc:
            raise _wrap(exc) from exc
