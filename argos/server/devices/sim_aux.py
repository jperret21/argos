"""Simulated filter wheel and focuser, and the optics they share with the camera.

API 2 wave 1 had connect-only stand-ins; wave 3 drives them, so they behave
like the Alpaca devices the hub talks to:

- the **filter wheel** takes time to turn (``SimOptions.wheel_slot_s`` per
  slot) and reads position −1 meanwhile, as ``FilterWheel.get_position``
  does on a Seestar (``filterwheel.py:88-98``);
- the **focuser** moves at ``SimOptions.focuser_speed_steps_s``, reports
  ``IsMoving``, stops where it is on ``Halt`` and clamps a move to
  ``0…MaxStep`` (``focuser.py:127-139``).

Both write into a :class:`SimOptics` the simulated camera reads, so the
pixels follow the hardware: stars blur away from best focus (a V-curve
autofocus can find), and the wheel's Dark slot blocks the light (the only
thing that does on a Seestar, which has no shutter). The motion is
evaluated lazily from the clock, like ``SimMount``: no thread.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable

from argos.core.hardware import active

#: Defocus scale of the simulated optics (focuser steps): the FWHM grows as
#: ``√(1 + (Δ/scale)²)`` with ``Δ`` the distance to best focus.
DEFOCUS_SCALE_STEPS = 450.0
#: Where the simulated focuser starts (and stays, between connections).
FOCUSER_START = 5_000
FOCUSER_MAX_STEP = 10_000
#: Transmission of each simulated slot; unknown names pass all the light.
_TRANSMISSION = {"dark": 0.0, "ir": 1.0, "lp": 0.8}
#: Transmission while the wheel turns (part of the exposure through the edge).
_TRANSMISSION_MOVING = 0.5


class SimOptics:
    """What the simulated camera sees: focus and filter, shared across devices.

    The hub creates one per server and hands it to the simulated camera,
    focuser and wheel. The physical state survives a disconnect (the
    focuser stays where it was, the wheel on its slot), as on a telescope.
    """

    def __init__(self, best_focus: int = 5_300, defocus_scale: float = DEFOCUS_SCALE_STEPS) -> None:
        self.best_focus = int(best_focus)
        self.defocus_scale = float(defocus_scale)
        self._lock = threading.Lock()
        self.focuser: "SimFocuser | None" = None
        self.wheel: "SimFilterWheel | None" = None
        self.focus_position: float = float(FOCUSER_START)
        self.wheel_index: int | None = None

    def fwhm_factor(self) -> float:
        """Star FWHM relative to the seeing-limited one (1.0 at best focus)."""
        with self._lock:
            focuser = self.focuser
            position = self.focus_position
        if focuser is not None:
            position = focuser.true_position()
        delta = (position - self.best_focus) / self.defocus_scale
        return math.sqrt(1.0 + delta * delta)

    def transmission(self) -> float:
        """Fraction of the sky light reaching the sensor (0 on the Dark slot)."""
        with self._lock:
            wheel = self.wheel
        if wheel is None:
            return 1.0
        return wheel.transmission()


class SimFilterWheel:
    """Implements :class:`~argos.server.devices.base.FilterWheelDevice`."""

    name = "ARGOS Simulator filter wheel"

    def __init__(
        self,
        optics: SimOptics | None = None,
        slot_s: float = 0.6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        #: The active profile's internal slots (``Dark``, ``IR``, ``LP`` on a Seestar).
        self.slots: tuple[str, ...] = tuple(active.profile().filter_names)
        self._optics = optics
        self._slot_s = max(0.0, float(slot_s))
        self._clock = clock
        self._lock = threading.Lock()
        start = None if optics is None else optics.wheel_index
        if start is None or not 0 <= start < len(self.slots):
            # The first slot that lets light through, as the Qt form's default (IR).
            start = next((i for i, n in enumerate(self.slots) if n.lower() != "dark"), 0)
        self._index = start
        self._target = start
        self._arrive_at = 0.0
        if optics is not None:
            with optics._lock:
                optics.wheel = self
                optics.wheel_index = start

    # -- motion ------------------------------------------------------------

    def _settle(self) -> None:
        """Lock held: finish a move whose time is up."""
        if self._target != self._index and self._clock() >= self._arrive_at:
            self._index = self._target
            if self._optics is not None:
                self._optics.wheel_index = self._index

    def _moving(self) -> bool:
        self._settle()
        return self._target != self._index

    def transmission(self) -> float:
        with self._lock:
            if self._moving():
                return _TRANSMISSION_MOVING
            name = self.slots[self._index] if self.slots else ""
        return _TRANSMISSION.get(name.lower(), 1.0)

    # -- FilterWheelDevice ---------------------------------------------------

    def get_position(self) -> int:
        with self._lock:
            return -1 if self._moving() else self._index

    def set_position(self, index: int) -> None:
        from argos.server.devices.base import DeviceError

        if not 0 <= int(index) < len(self.slots):
            valid = ", ".join(str(i) for i in range(len(self.slots))) or "none"
            raise DeviceError(f"Invalid filter position {index} — must be {valid}")
        with self._lock:
            if self._moving():
                raise DeviceError("The filter wheel is still moving")
            if int(index) == self._index:
                return
            slots = abs(int(index) - self._index)
            self._target = int(index)
            self._arrive_at = self._clock() + self._slot_s * slots

    def position_name(self) -> str:
        position = self.get_position()
        if position == -1:
            return "Moving…"
        return self.slots[position] if position < len(self.slots) else f"Pos {position}"

    def info(self) -> str:
        if not self.slots:
            return "no slots in this profile"
        return self.position_name()

    def close(self) -> None:
        pass


class SimFocuser:
    """Implements :class:`~argos.server.devices.base.FocuserDevice`."""

    name = "ARGOS Simulator focuser"
    max_step = FOCUSER_MAX_STEP
    max_increment = FOCUSER_MAX_STEP
    absolute = True
    step_size_um: float | None = None
    temperature_c = 12.5

    def __init__(
        self,
        optics: SimOptics | None = None,
        speed_steps_s: float = 2_000.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._optics = optics
        self._speed = max(1e-6, float(speed_steps_s))
        self._clock = clock
        self._lock = threading.Lock()
        start = float(FOCUSER_START) if optics is None else float(optics.focus_position)
        self._p0 = start
        self._target = start
        self._t0 = clock()
        if optics is not None:
            with optics._lock:
                optics.focuser = self

    # -- motion ------------------------------------------------------------

    def _at(self, now: float) -> float:
        """Lock held: the exact position at *now* (a float between steps)."""
        travel = self._speed * max(0.0, now - self._t0)
        distance = self._target - self._p0
        if abs(distance) <= travel:
            return self._target
        return self._p0 + math.copysign(travel, distance)

    def true_position(self) -> float:
        with self._lock:
            return self._at(self._clock())

    @property
    def position(self) -> int:
        """The connect log's ``pos=`` (``hub._connect_device``)."""
        return self.get_position()

    # -- FocuserDevice -------------------------------------------------------

    def get_position(self) -> int:
        return int(round(self.true_position()))

    def is_moving(self) -> bool:
        with self._lock:
            return self._at(self._clock()) != self._target

    def move_to(self, position: int) -> None:
        target = float(max(0, min(self.max_step, int(position))))  # focuser.py:132
        with self._lock:
            now = self._clock()
            self._p0 = self._at(now)
            self._t0 = now
            self._target = target

    def halt(self) -> None:
        with self._lock:
            now = self._clock()
            here = float(round(self._at(now)))
            self._p0 = self._target = here
            self._t0 = now

    def get_temperature(self) -> float | None:
        return self.temperature_c

    def info(self) -> str:
        return self.name

    def close(self) -> None:
        optics = self._optics
        if optics is None:
            return
        with optics._lock:
            if optics.focuser is self:
                optics.focuser = None
            optics.focus_position = self.true_position()
