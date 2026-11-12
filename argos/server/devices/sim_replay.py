"""Simulator replay source (wave 6a): a folder of real FITS copies played by the simulator.

``--sim-replay DIR`` (``SimOptions.replay_dir``) makes the ``simulator`` mode
serve real frames, so field identification, the aperture tracker and the
photometry of a sequence can be exercised on the simulator, which cannot be
solved or measured on its synthetic sky:

- :class:`ReplayCamera` returns, exposure after exposure, the pixels of the
  folder's FITS files in file-name order (raw 16-bit, the Open FITS rule of
  :func:`~argos.server.fits_source.load_raw_fits_frame`), starting again
  after the last one. The exposure time is still waited, and Stop interrupts
  it; exposure, gain, focus and wheel never change the pixels.
- :class:`ReplayMount` is the simulated mount, started unparked and
  tracking, whose readings carry the pointing of the file being exposed
  (``RA`` / ``DEC`` of an ARGOS frame, else ``OBJCTRA`` / ``OBJCTDEC``, and
  ``ALTITUDE`` / ``AZIMUTH`` when the header has them) whenever it tracks;
  a GoTo or a park behave as the simulator's.

Nothing is written into the folder. The subs a sequence saves are dated by
the server clock, not by the replayed headers.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from argos.server.devices.base import CameraLimits, ExposureCancelled
from argos.server.devices.sim_camera import SIM_LIMITS
from argos.server.devices.sim_mount import DEFAULT_SITE, SimMount, Site, altaz
from argos.server.fits_source import FITS_SUFFIXES, FitsReadError, load_raw_fits_frame
from argos.server.state import SensorInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayPointing:
    ra_hours: float
    dec_deg: float
    alt_deg: float | None
    az_deg: float | None


def _number(header: Any, key: str) -> float | None:
    try:
        value = float(header.get(key))
    except (TypeError, ValueError):
        return None
    return value


def header_pointing(header: Any) -> ReplayPointing | None:
    """Where the mount pointed for this frame, from its header.

    An ARGOS frame's ``RA`` is in hours (``fits_writer``); other software
    writes degrees, so for them only the sexagesimal ``OBJCTRA`` /
    ``OBJCTDEC`` are used.
    """
    from argos.server.field_solve import header_hint

    software = str(header.get("SOFTWARE") or header.get("CREATOR") or "").strip()
    ra, dec = _number(header, "RA"), _number(header, "DEC")
    if software.startswith("Argos") and ra is not None and dec is not None:
        radec: tuple[float, float] | None = (ra % 24.0, dec)
    else:
        radec = header_hint(header)
    if radec is None:
        return None
    return ReplayPointing(
        ra_hours=float(radec[0]),
        dec_deg=float(radec[1]),
        alt_deg=_number(header, "ALTITUDE"),
        az_deg=_number(header, "AZIMUTH"),
    )


class ReplaySource:
    """The folder, its order and the file being exposed (shared by camera and mount)."""

    def __init__(self, folder: Path | str) -> None:
        from astropy.io import fits

        root = Path(folder).expanduser()
        if not root.is_dir():
            raise ValueError(f"replay folder {root} does not exist")
        self.files = sorted(
            p
            for p in root.iterdir()
            if p.is_file() and p.suffix.lower() in FITS_SUFFIXES and not p.name.startswith(".")
        )
        if not self.files:
            raise ValueError(f"replay folder {root} holds no FITS image (.fit, .fits, .fts)")
        try:
            first = load_raw_fits_frame(self.files[0])
        except FitsReadError as exc:
            raise ValueError(f"replay file {self.files[0].name}: {exc}") from exc
        self.folder = root
        self.height, self.width = (int(n) for n in first.pixels.shape)
        self.bayer = first.bayer
        self._lock = threading.Lock()
        self._next = 0
        self._current = 0
        self._served = 0
        self._wrapped = False
        self._headers: dict[int, Any] = {0: fits.getheader(self.files[0])}

    def _header(self, index: int) -> Any:
        from astropy.io import fits

        with self._lock:
            cached = self._headers.get(index)
        if cached is not None:
            return cached
        header = fits.getheader(self.files[index])
        with self._lock:
            self._headers[index] = header
        return header

    def begin_exposure(self) -> int:
        """The next file's index; the mount reports its pointing from now on."""
        with self._lock:
            index = self._next
            self._next = (self._next + 1) % len(self.files)
            self._current = index
            self._served += 1
            wrapped = index == 0 and self._served > 1 and not self._wrapped
            if wrapped:
                self._wrapped = True
        if wrapped:
            logger.warning(
                "Replay: every file of %s was served — starting again from the first", self.folder
            )
        return index

    def pixels(self, index: int) -> np.ndarray:
        frame = load_raw_fits_frame(self.files[index])
        if frame.pixels.shape != (self.height, self.width):
            raise FitsReadError(
                f"replay file {self.files[index].name} is {frame.pixels.shape[1]}×"
                f"{frame.pixels.shape[0]}, not {self.width}×{self.height} like the first"
            )
        return frame.pixels

    def readings(self, index: int | None = None) -> dict[str, object]:
        header = self._header(self._current if index is None else index)
        offset = _number(header, "OFFSET")
        return {
            "ccd_temp": _number(header, "CCD-TEMP"),
            "egain_driver": None,  # EGAIN from the table or the sensor reference, as live
            "offset": int(offset) if offset is not None else None,
            "readout_mode": None,
        }

    def pointing(self) -> ReplayPointing | None:
        with self._lock:
            index = self._current
        return header_pointing(self._header(index))


class ReplayCamera:
    """Implements :class:`~argos.server.devices.base.CameraDevice` over a replay folder."""

    source = "simulator"
    name = "ARGOS camera simulator (replay)"

    def __init__(self, replay: ReplaySource) -> None:
        self._replay = replay
        self.width = replay.width
        self.height = replay.height
        self._lock = threading.Lock()
        self._offset: int | None = None
        self.light_flags: list[bool] = []
        #: The exposure wait is ``exposure × time_scale`` (1: really waited). A
        #: test hook: the parity runs replay 10 s subs without waiting 10 s.
        self.time_scale = 1.0

    def sensor(self) -> SensorInfo:
        return SensorInfo(width=self.width, height=self.height, bitpix=16, bayer=self._replay.bayer)

    def expose(
        self,
        exposure_s: float,
        gain: int,
        cancel: threading.Event,
        on_readout: Callable[[], None],
        *,
        light: bool = True,
        on_start: Callable[[], None] | None = None,
    ) -> np.ndarray:
        with self._lock:
            self.light_flags = (self.light_flags + [bool(light)])[-64:]
        index = self._replay.begin_exposure()
        if on_start is not None:
            on_start()
        if cancel.wait(max(0.0, float(exposure_s) * self.time_scale)):
            raise ExposureCancelled()
        on_readout()
        pixels = self._replay.pixels(index)
        if cancel.is_set():
            raise ExposureCancelled()
        return pixels

    def abort(self) -> None:
        pass  # expose() watches its cancel event

    def close(self) -> None:
        pass

    def limits(self) -> CameraLimits:
        return SIM_LIMITS

    def get_offset(self) -> int | None:
        with self._lock:
            if self._offset is not None:
                return self._offset
        return self._replay.readings().get("offset")  # type: ignore[return-value]

    def set_offset(self, value: int) -> None:
        low, high = SIM_LIMITS.offset_range or (0, 0)
        with self._lock:
            self._offset = max(low, min(high, int(value)))

    def set_binning(self, value: int) -> None:
        if int(value) != 1:
            from argos.server.devices.base import DeviceError

            raise DeviceError("The simulated camera does not bin")

    def temperature(self) -> float | None:
        value = self._replay.readings().get("ccd_temp")
        return float(value) if value is not None else None  # type: ignore[arg-type]

    def fits_readings(self) -> dict[str, object]:
        readings = dict(self._replay.readings())
        with self._lock:
            if self._offset is not None:
                readings["offset"] = self._offset
        return readings


class ReplayMount(SimMount):
    """The simulated mount, reporting the replayed frames' pointing while it tracks.

    Alt-az, as the Seestar that took the frames: the photometry tracker then
    allows the field rotation (``_wcs_for_frame``) and no pier side is reported.
    """

    alignment = "altaz"

    def __init__(
        self,
        replay: ReplaySource,
        slew_rate_deg_s: float = 4.0,
        site: Site = DEFAULT_SITE,
        poll_interval_s: float = 0.25,
    ) -> None:
        super().__init__(
            slew_rate_deg_s=slew_rate_deg_s, site=site, poll_interval_s=poll_interval_s
        )
        self._replay = replay
        first = replay.pointing()
        with self._lock:
            # Unparked and tracking where the replayed night pointed.
            self._parked = False
            self._tracking = True
            if first is not None:
                self._ra0, self._dec0 = first.ra_hours, first.dec_deg
            self._t0 = self._clock()

    def read(self):
        reading = super().read()
        if reading.state != "tracking":
            return reading
        pointing = self._replay.pointing()
        if pointing is None:
            return reading
        alt, az = pointing.alt_deg, pointing.az_deg
        if alt is None or az is None:
            alt, az = altaz(pointing.ra_hours, pointing.dec_deg, self._clock(), self._site)
        return type(reading)(
            state=reading.state,
            ra_hours=pointing.ra_hours,
            dec_deg=pointing.dec_deg,
            alt_deg=alt,
            az_deg=az,
            tracking=reading.tracking,
            pier_side=None,
        )


__all__ = ["ReplayCamera", "ReplayMount", "ReplayPointing", "ReplaySource", "header_pointing"]
