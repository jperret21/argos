"""Simulated filter wheel and focuser: connect-only stand-ins (API 2).

The v1 simulator had a camera and a mount only. The Connection screen
shows four device rows, so the simulator gains the other two, enough to
connect, describe and disconnect them; moving them belongs to wave 3.
"""

from __future__ import annotations

from argos.core.hardware import active


class SimFilterWheel:
    """Implements :class:`~argos.server.devices.base.AuxDevice`."""

    name = "ARGOS Simulator filter wheel"

    def __init__(self) -> None:
        #: The active profile's internal slots (``Dark``, ``IR``, ``LP`` on a Seestar).
        self.slots: tuple[str, ...] = tuple(active.profile().filter_names)
        self.position = 0

    def info(self) -> str:
        if not self.slots:
            return "no slots in this profile"
        return self.slots[self.position]

    def close(self) -> None:
        pass


class SimFocuser:
    """Implements :class:`~argos.server.devices.base.AuxDevice`."""

    name = "ARGOS Simulator focuser"
    max_step = 10_000

    def __init__(self) -> None:
        self.position = 5_000

    def info(self) -> str:
        return self.name

    def close(self) -> None:
        pass
