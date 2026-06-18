"""ASCOM Alpaca focuser wrapper — backed by alpyca.

The Seestar S30 Pro exposes two focusers via Alpaca (configureddevices
discovery): index 0 is the telephoto focuser used by the science camera,
index 1 is the wide-angle finder. Argos only drives the telephoto
focuser — the wide-angle is for the native Seestar app's plate-solve loop.

All methods are synchronous and must run inside a QThread worker; never
call them from the Qt main thread (network round-trips can take 200+ ms).
"""

from __future__ import annotations

import logging

from alpaca.exceptions import DriverException
from alpaca.focuser import Focuser as _AlpacaFocuser

from argos.core.alpaca.client import AlpacaError

logger = logging.getLogger(__name__)


def _wrap(exc: Exception) -> AlpacaError:
    if isinstance(exc, DriverException):
        return AlpacaError(exc.number, str(exc))
    return AlpacaError(0, str(exc))


class Focuser:
    """ASCOM Alpaca focuser controller, backed by alpyca.

    Args:
        host:        IP address of the Seestar.
        port:        Alpaca HTTP port.
        device_index: 0 = telephoto (science), 1 = wide-angle. Default 0.
    """

    def __init__(self, host: str, port: int, device_index: int = 0) -> None:
        self._focuser = _AlpacaFocuser(f"{host}:{port}", device_index)
        self._connected = False
        # Cached capability flags filled by ``connect()``.
        self.max_step:       int  = 100_000
        self.max_increment:  int  = 1_000
        self.step_size_um:   float | None = None
        self.absolute:       bool = True
        self.tempcomp_available: bool = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> str:
        """Connect and cache the focuser's capability flags."""
        try:
            self._focuser.Connected = True
        except Exception as exc:
            raise _wrap(exc) from exc
        self._connected = True

        for attr, name in (
            ("MaxStep",      "max_step"),
            ("MaxIncrement", "max_increment"),
            ("StepSize",     "step_size_um"),
            ("Absolute",     "absolute"),
            ("TempCompAvailable", "tempcomp_available"),
        ):
            try:
                value = getattr(self._focuser, attr)
                setattr(self, name, value)
            except Exception as exc:
                logger.debug("%s read failed (non-fatal): %s", attr, exc)

        try:
            display = self._focuser.Name or "Focuser"
        except Exception:
            display = "Focuser"
        logger.info(
            "Focuser connected: %s  MaxStep=%s  MaxIncrement=%s  Absolute=%s",
            display, self.max_step, self.max_increment, self.absolute,
        )
        return display

    def disconnect(self) -> None:
        try:
            self._focuser.Connected = False
        except Exception as exc:
            logger.warning("Focuser disconnect: %s", exc)
        finally:
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_position(self) -> int:
        try:
            return int(self._focuser.Position)
        except Exception as exc:
            raise _wrap(exc) from exc

    def is_moving(self) -> bool:
        try:
            return bool(self._focuser.IsMoving)
        except Exception as exc:
            raise _wrap(exc) from exc

    def get_temperature(self) -> float | None:
        """Return the focuser-reported temperature, or None if unsupported."""
        try:
            value = self._focuser.Temperature
            return None if value is None else round(float(value), 2)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def move_to(self, position: int) -> None:
        """Send an absolute Move command.

        Clamped to ``[0, max_step]`` so the caller can pass adjusted values
        from a "step by N" helper without worrying about over/underflow.
        """
        target = max(0, min(int(self.max_step), int(position)))
        try:
            self._focuser.Move(target)
            logger.debug("Focuser Move(%d)", target)
        except Exception as exc:
            raise _wrap(exc) from exc

    def step(self, delta: int) -> int:
        """Move by ``delta`` steps relative to the current position.

        Returns the target position that was commanded so the caller can
        immediately reflect it in the UI without re-polling.
        """
        current = self.get_position()
        target = max(0, min(int(self.max_step), current + int(delta)))
        self.move_to(target)
        return target

    def halt(self) -> None:
        """Stop any motion in progress. Safe to call when idle."""
        try:
            self._focuser.Halt()
        except Exception as exc:
            logger.warning("Focuser halt: %s", exc)
