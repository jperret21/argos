"""Binary frame encoding for ``/ws/frames`` (see ``protocol.md``).

Layout of one WebSocket binary message::

    [0, 4)              uint32 LE   N = byte length of the JSON header
    [4, 4 + N)          UTF-8 JSON  header (seq, geometry, stats, …)
    [4 + N, offset)     zero padding, so that offset % 8 == 0
    [offset, …)         width × height × channels uint16 LE, row-major,
                        channels interleaved, row 0 = top of the image

Row 0 is the top row *as displayed*, which in ARGOS is simply row 0 of the
array: the Qt viewer (``fits_viewer.py``) shows arrays row-major with the
y-axis inverted, and neither the camera download nor ``Open FITS`` flips.
The 8-byte alignment lets the browser build a ``Uint16Array`` view straight
on the message buffer, with no copy.

The statistics come from one 65 536-bin histogram of the uint16 pixels, which
gives the **exact** median and MAD (identical to ``np.median``) in a few
milliseconds — sorting two million pixels twice would cost ~45 ms.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Literal

import numpy as np

FRAME_ALIGN = 8
_PREFIX = struct.Struct("<I")

FrameSource = Literal["simulator", "alpaca", "file"]


def _histogram_median(values: np.ndarray, counts: np.ndarray, n: int) -> float:
    """Median of a sample given as sorted distinct *values* and their *counts*.

    Matches ``np.median``: the mean of the two middle elements when *n* is even.
    """
    cdf = np.cumsum(counts)
    lo = values[np.searchsorted(cdf, (n - 1) // 2 + 1)]
    hi = values[np.searchsorted(cdf, n // 2 + 1)]
    return (float(lo) + float(hi)) / 2.0


def frame_stats(pixels: np.ndarray) -> dict[str, Any]:
    """``min``/``max``/``median``/``mad``/``mean`` over every sample of *pixels*.

    *pixels* must be uint16 (any shape; colour channels are pooled). ``mad`` is
    the raw median absolute deviation — not scaled by 1.4826.
    """
    flat = np.ascontiguousarray(pixels).reshape(-1)
    n = int(flat.size)
    if n == 0:
        return {"min": 0, "max": 0, "median": 0.0, "mad": 0.0, "mean": 0.0}
    hist = np.bincount(flat, minlength=65536)
    values = np.flatnonzero(hist)  # sorted distinct pixel values
    counts = hist[values]

    median = _histogram_median(values, counts, n)
    # Deviations of the distinct values; sorting a few thousand bins instead
    # of n pixels is what makes the exact MAD cheap.
    deviations = np.abs(values.astype(np.float64) - median)
    order = np.argsort(deviations, kind="stable")
    mad = _histogram_median(deviations[order], counts[order], n)
    mean = float(np.dot(values.astype(np.float64), counts.astype(np.float64)) / n)
    return {
        "min": int(values[0]),
        "max": int(values[-1]),
        "median": median,
        "mad": mad,
        "mean": mean,
    }


def encode_frame(
    pixels: np.ndarray,
    *,
    seq: int,
    exposure_s: float,
    timestamp: str,
    source: FrameSource,
    stats: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> bytes:
    """Encode one frame as a ``/ws/frames`` binary message.

    Args:
        pixels: uint16 array, ``(height, width)`` or ``(height, width, 3)``,
            row 0 = top of the image as displayed.
        seq: Frame sequence number (monotonic per server process).
        exposure_s: Exposure time, 0.0 when unknown (opened file).
        timestamp: ISO 8601 UTC time of the frame.
        source: ``"simulator"``, ``"alpaca"`` or ``"file"``.
        stats: Precomputed :func:`frame_stats`, computed here when omitted.
        extra: Additive header fields (wave 3: ``bayer``, ``origin``, the
            frame's settings, an opened file's ``path`` / ``date_obs`` /
            ``epoch_utc``); they never replace a v1 field.

    Raises:
        ValueError: Unsupported dtype or shape.
    """
    arr = np.asarray(pixels)
    if arr.dtype != np.uint16:
        raise ValueError(f"frame pixels must be uint16, got {arr.dtype}")
    if arr.ndim == 2:
        height, width = arr.shape
        channels = 1
    elif arr.ndim == 3 and arr.shape[2] in (1, 3):
        height, width, channels = arr.shape
    else:
        raise ValueError(f"unsupported frame shape {arr.shape}")

    header: dict[str, Any] = {
        "seq": int(seq),
        "width": int(width),
        "height": int(height),
        "channels": int(channels),
        "dtype": "uint16",
        "pixel_offset": 0,
        "exposure_s": float(exposure_s),
        "timestamp": timestamp,
        "source": source,
        "stats": stats if stats is not None else frame_stats(arr),
    }
    for key, value in (extra or {}).items():
        header.setdefault(key, value)
    # pixel_offset is part of the header it positions: iterate until the
    # aligned offset is stable (at most two passes — it only grows).
    offset = 0
    while True:
        header["pixel_offset"] = offset
        blob = json.dumps(header, separators=(",", ":")).encode("utf-8")
        needed = -(-(_PREFIX.size + len(blob)) // FRAME_ALIGN) * FRAME_ALIGN
        if needed == offset:
            break
        offset = needed

    out = bytearray(offset + arr.size * 2)
    _PREFIX.pack_into(out, 0, len(blob))
    out[_PREFIX.size : _PREFIX.size + len(blob)] = blob
    # Single copy of the pixels, converted to little-endian on the way in.
    np.frombuffer(out, dtype="<u2", offset=offset, count=arr.size)[:] = arr.reshape(-1)
    return bytes(out)
