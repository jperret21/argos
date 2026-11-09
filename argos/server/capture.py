"""Take shot: capture settings, per-frame snapshots and the FITS save (rows A21-A24).

A Qt-free port of the fixed (release 0.5.0) Take-shot path of
``argos/core/session/acquisition_engine.py``:

- :class:`FrameSettings` is the per-frame snapshot of S2
  (``exposure_worker.py:139-149``, ``FrameSettings``): the exposure loop
  takes one when a frame starts, and the save uses it, never the settings
  at the time the frame arrives;
- :func:`wheel_filter_name` is ``_wheel_filter_name``
  (``acquisition_engine.py:154-180``, S3): FILTER is read back from the
  wheel when the file is written;
- :func:`save_frame` is ``_save_fits_async``'s task
  (``acquisition_engine.py:1796-1910``): folder and name of the Qt Take
  shot, never overwriting, QA headers measured on the saved array (S20),
  pointing only from a live mount (X1), the site only when one is set (X2);
- :func:`raw_adu` and :func:`fits_exposure_mid` are ``_raw_adu`` and
  ``fits_exposure_mid`` (``acquisition_engine.py:87-151``, S4), for Open
  FITS.

The decisions that need the hub's state (is the wheel on Dark, did it move
during this exposure) live in the hub; this module holds the data and the
pure steps, so the FITS parity tests can drive :func:`save_frame` directly.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np

from argos import SOFTWARE_ID
from argos.core.imaging.fits_writer import IMAGE_TYPE_MAP, FITSWriter, FrameContext
from argos.core.imaging.metrics import detect_stars, frame_metrics
from argos.core.imaging.sequencer import DARK_FILTER_NAME

logger = logging.getLogger(__name__)

FrameType = Literal["light", "dark", "flat", "bias"]
FRAME_TYPES: tuple[str, ...] = ("light", "dark", "flat", "bias")
#: The Qt Camera form's default filter (``camera_dock.py:58-61``): the first light slot.
DEFAULT_FILTER = "IR"
#: Without a camera, the v1 bounds of a capture body (``app.py``).
FALLBACK_EXPOSURE_MAX_S = 3600.0
FALLBACK_GAIN_MAX = 1000

#: ``(level, message)`` sink of the save task (the hub's log, topic camera).
LogFn = Callable[[str, str], None]


def image_type(frame_type: str) -> str:
    """FITS ``IMAGETYP`` of an API frame type (``fits_writer.IMAGE_TYPE_MAP``)."""
    return IMAGE_TYPE_MAP[frame_type]


def is_light_frame(frame_type: str) -> bool:
    """Shutter semantics sent with ``StartExposure`` (``acquisition_engine.py:81-84``)."""
    return frame_type not in ("dark", "bias")


def is_dark_slot(name: str | None) -> bool:
    return bool(name) and str(name).strip().lower() == DARK_FILTER_NAME.lower()


@dataclass(frozen=True)
class CaptureSettings:
    """What the next frame uses; server state shared by every client (Q-O13)."""

    exposure_s: float = 2.0
    gain: int = 80
    frame_type: str = "light"
    filter: str = DEFAULT_FILTER
    offset: int | None = None
    binning: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrameSettings:
    """One frame's own settings, snapshotted when its exposure starts (S2)."""

    exposure_s: float
    gain: int
    frame_type: str
    filter: str
    object_name: str
    light: bool
    origin: Literal["single", "live", "autofocus"]
    #: Set at arrival: this frame is the one a Take shot saves.
    save: bool = False
    #: DATE-OBS of the frame: taken just before ``StartExposure``.
    started_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SaveRequest:
    """A pending Take shot (``_capture_pending`` of the Qt engine)."""

    frame_type: str
    #: Live view keeps exposing after the save; single releases the camera.
    live: bool
    accepted_utc: str
    #: What the shot asked for (a live Take shot saves the frame in progress
    #: with its own values, S2; the log says when they differ).
    exposure_s: float | None = None
    gain: int | None = None


@dataclass(frozen=True)
class Pointing:
    """The mount reading a saved frame records (X1: ``None`` when no live mount)."""

    ra_hours: float
    dec_deg: float
    alt_deg: float | None
    az_deg: float | None


@dataclass
class SaveJob:
    """Everything the save thread needs; collected when the frame arrives."""

    arr: np.ndarray
    start: datetime
    end: datetime
    frame: FrameSettings
    frame_seq: int
    sessions_path: Path
    pointing: Pointing | None
    target: tuple[float, float] | None
    site: tuple[float, float, float] | None
    observer: str
    #: The camera handle (``fits_readings``), or ``None``.
    camera: Any = None
    #: The filter wheel handle (FILTER read-back), or ``None`` without a wheel.
    wheel: Any = None
    software: str = SOFTWARE_ID
    extra: dict[str, Any] = field(default_factory=dict)
    #: ``camera.egain_table``: its entry for the frame's gain is the header EGAIN (S42).
    egain_table: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SaveResult:
    path: Path
    filter_name: str
    record: dict[str, Any]


def wheel_filter_name(wheel: Any, requested: str, log: LogFn) -> str:
    """Filter the wheel actually sits on, for a Take-shot header (S3).

    Port of ``_wheel_filter_name`` (``acquisition_engine.py:154-180``):
    without a wheel the frame's filter stands; an unreadable or still-turning
    wheel keeps it with a warning; a readable wheel that differs wins. A
    device read: runs on the save thread.
    """
    if wheel is None:
        return requested
    try:
        actual = wheel.position_name()
    except Exception as exc:
        log("warning", f"Filter read-back failed ({exc}) — FITS FILTER is the form's '{requested}'")
        return requested
    if not actual or actual == "Moving…":
        log("warning", f"Filter wheel still moving — FITS FILTER is the form's '{requested}'")
        return requested
    if actual.lower() != requested.lower():
        log(
            "warning",
            f"The wheel is on '{actual}', not on the form's '{requested}' — "
            f"FITS FILTER records '{actual}'.",
        )
    return actual


def frame_context(job: SaveJob, filter_name: str, readings: dict[str, Any]) -> FrameContext:
    """The ``FrameContext`` of ``_save_fits_async`` (``acquisition_engine.py:1811-1873``)."""
    pos = job.pointing
    target = job.target
    site = job.site or (None, None, None)
    object_name = job.frame.object_name.strip() or "Unknown"  # camera_dock.py:243
    return FrameContext(
        ra=pos.ra_hours if pos else None,
        dec=pos.dec_deg if pos else None,
        altitude=pos.alt_deg if pos else None,
        azimuth=pos.az_deg if pos else None,
        target_ra=target[0] if target else None,
        target_dec=target[1] if target else None,
        object_name=object_name,
        observer=job.observer,
        site_lat=site[0],
        site_lon=site[1],
        site_elev=site[2],
        software=job.software,
        ccd_temp=readings.get("ccd_temp"),
        egain_driver=readings.get("egain_driver"),
        egain_table=job.egain_table,
        offset=readings.get("offset"),
        readout_mode=readings.get("readout_mode"),
        filter_name=filter_name,
    )


def save_frame(job: SaveJob, log: LogFn) -> SaveResult:
    """Write one Take-shot frame (the body of ``_save_fits_async._Task.run``).

    Raises the writer's exception (``OSError``…); the caller logs
    "FITS save failed: …" as the Qt task does.
    """
    frame = job.frame
    image = image_type(frame.frame_type)
    object_name = frame.object_name.strip() or "Unknown"
    # Header truthfulness: FILTER (and the folder/file name) from the wheel.
    filter_name = wheel_filter_name(job.wheel, frame.filter, log)
    folder = FITSWriter.session_folder(
        job.sessions_path, object_name, job.start, image, filter_name
    )
    index = 1
    while True:
        name = FITSWriter.build_filename(
            object_name, image, job.start, frame.exposure_s, filter_name, index, frame.gain
        )
        path = folder / name
        if not path.exists():
            break
        index += 1

    readings: dict[str, Any] = {}
    if job.camera is not None and hasattr(job.camera, "fits_readings"):
        try:
            readings = dict(job.camera.fits_readings())
        except Exception as exc:  # reads are best-effort, as the Qt ones
            logger.warning("Camera reads for the FITS header failed: %s", exc)
    ctx = frame_context(job, filter_name, readings)
    # QA headers measured on THIS array (S20), best-effort as in Qt.
    record: dict[str, Any] = {
        "hfd": None,
        "fwhm": None,
        "star_count": None,
        "sky_adu": None,
        "peak_adu": None,
        "eccentricity": None,
    }
    try:
        metrics = frame_metrics(job.arr)
        field_ = detect_stars(job.arr)
        ctx.hfd = metrics.hfd
        ctx.star_count = metrics.star_count
        ctx.sky_adu = metrics.sky_adu
        ctx.fwhm = field_.mean_fwhm
        ctx.eccentricity = field_.mean_eccentricity
        record.update(
            hfd=metrics.hfd,
            fwhm=field_.mean_fwhm,
            star_count=metrics.star_count,
            sky_adu=_finite(metrics.sky_adu),
            peak_adu=int(metrics.peak_adu),
            eccentricity=field_.mean_eccentricity,
        )
    except Exception:  # pragma: no cover - metrics are best-effort
        logger.warning("Frame metrics failed — saving without QA", exc_info=True)
    FITSWriter.write(
        arr=job.arr,
        path=path,
        exposure_start=job.start,
        exposure_end=job.end,
        exposure_time=frame.exposure_s,
        gain=frame.gain,
        image_type=image,
        context=ctx,
        overwrite=False,
    )
    return SaveResult(path=path, filter_name=filter_name, record=record)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# ---------------------------------------------------------------------------
# Opened files (A27, S4): acquisition_engine.py:87-151
# ---------------------------------------------------------------------------


def _fits_utc(value: Any) -> datetime | None:
    """A FITS ISO date-time keyword as an aware UTC datetime, else None.

    ``acquisition_engine.py:87-100``: a value without a time part (an old
    ``DATE-OBS`` with a separate ``TIME-OBS``) is refused, not read as midnight.
    """
    text = str(value or "").strip()
    if "T" not in text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _late_date_avg(header: Any) -> bool:
    """``_late_date_avg`` (S39): a frame written by Argos before 0.5.0, whose
    sequence ``DATE-AVG`` is late by half the image download (S36)."""
    text = str(header.get("SOFTWARE") or header.get("SWCREATE") or "").strip()
    match = re.fullmatch(r"Argos(?: v(\d+)\.(\d+)\S*)?", text)
    if match is None:
        return False
    if match.group(1) is None:
        return True
    return (int(match.group(1)), int(match.group(2))) < (0, 5)


def fits_exposure_mid(header: Any) -> datetime | None:
    """Exposure midpoint (UTC) of a saved frame, from its header, or None.

    ``fits_exposure_mid`` of ``acquisition_engine.py``: ``DATE-AVG``, else
    ``DATE-OBS`` + ``EXPTIME``/2 (``EXPOSURE`` accepted); a frame of Argos
    before 0.5.0 always by ``DATE-OBS`` + ``EXPTIME``/2 (S39); never guessed.
    """
    mid = None if _late_date_avg(header) else _fits_utc(header.get("DATE-AVG"))
    if mid is not None:
        return mid
    start = _fits_utc(header.get("DATE-OBS"))
    exposure = header.get("EXPTIME", header.get("EXPOSURE"))
    try:
        exposure_s = float(exposure)
    except (TypeError, ValueError):
        return None
    if start is None or not math.isfinite(exposure_s) or exposure_s < 0:
        return None
    return start + timedelta(seconds=exposure_s / 2.0)


def raw_adu(data: Any) -> np.ndarray:
    """An opened frame as the sensor's 16-bit ADU, or ``ValueError``.

    ``_raw_adu`` (``acquisition_engine.py:125-151``): integer values in
    0..65535 are accepted whatever the stored type; non-integral or
    non-finite floats, negative values and values above 65535 are refused
    (a plain cast would wrap them).
    """
    arr = np.asarray(data)
    if arr.dtype.kind not in "uif":
        raise ValueError(f"unsupported pixel type {arr.dtype}")
    if arr.size == 0:
        raise ValueError("the image has no pixels")
    if arr.dtype.kind == "f" and not (
        np.isfinite(arr).all() and np.array_equal(arr, np.floor(arr))
    ):
        raise ValueError(
            "floating-point pixels (a calibrated or stacked frame?) are not raw "
            "16-bit camera counts — open the raw .fit frame instead"
        )
    low, high = arr.min(), arr.max()
    if low < 0 or high > 65535:
        raise ValueError(
            f"pixel values {low:g} to {high:g} do not fit raw 16-bit camera counts "
            "(0 to 65535) — open the raw .fit frame instead"
        )
    return np.ascontiguousarray(arr, dtype=np.uint16)
