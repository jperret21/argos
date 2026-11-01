"""Read a FITS file as a displayable uint16 frame for ``POST /api/camera/open-fits``.

Same orientation as the Qt app's *Open FITS*: the data array is used as is,
row 0 first — no flip, so a frame ARGOS saved comes back exactly as it was
shown live. Conversions, all display-oriented (the file is never modified):

- integer data (BZERO/BSCALE applied by astropy) is clipped to 0…65535;
- float data normalised to [0, 1] (Siril's 32-bit default) is scaled by
  65535, other float data is clipped; NaN and −inf become 0, +inf (often a
  saturated pixel) becomes 65535;
- a ``(3, H, W)`` colour cube becomes ``(H, W, 3)`` interleaved RGB.

The image size is read from the header before any pixel is loaded: a frame
larger than the viewer's GPU texture limit (:data:`MAX_SIDE` per side) or
than :data:`MAX_ELEMENTS` samples is refused, so a huge stack or mosaic can
neither exhaust the server's memory nor reach a viewer that cannot show it.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from argos.server.state import utc_iso

FITS_SUFFIXES = frozenset({".fit", ".fits", ".fts"})

#: Largest image side the web viewer can upload (WebGL MAX_TEXTURE_SIZE, 16384
#: on current GPUs).
MAX_SIDE = 16384
#: Largest number of samples (all axes): 100 M, i.e. a 200 MB uint16 frame.
MAX_ELEMENTS = 100_000_000


class FitsReadError(Exception):
    """The file is not a FITS image this server can display."""


def _to_uint16(data: np.ndarray) -> np.ndarray:
    if np.issubdtype(data.dtype, np.integer):
        if data.dtype == np.uint16:
            return data.astype(np.uint16)  # native byte order, writeable copy
        return np.clip(data, 0, 65535).astype(np.uint16)
    if not np.issubdtype(data.dtype, np.floating):
        raise FitsReadError(f"unsupported pixel type {data.dtype}")
    # One float32 working copy, converted in place (float32 holds every
    # integer of the 16-bit range exactly).
    arr = np.array(data, dtype=np.float32)
    peak = float(np.max(arr, where=np.isfinite(arr), initial=0.0)) if arr.size else 0.0
    if peak <= 1.0:
        arr *= 65535.0
    np.nan_to_num(arr, copy=False, nan=0.0, posinf=65535.0, neginf=0.0)
    np.rint(arr, out=arr)
    np.clip(arr, 0, 65535, out=arr)
    return arr.astype(np.uint16)


def _to_frame_shape(data: np.ndarray) -> np.ndarray:
    if data.ndim == 2:
        return data
    if data.ndim == 3:
        if data.shape[0] == 1:
            return data[0]
        if data.shape[0] == 3:
            return np.moveaxis(data, 0, -1)  # (3, H, W) planes → (H, W, 3)
        if data.shape[2] == 3:
            return data
    raise FitsReadError(f"expected a 2-D image or an RGB cube, got shape {data.shape}")


def _timestamp(header, path: Path) -> str:
    date_obs = header.get("DATE-OBS")
    if date_obs:
        try:
            from astropy.time import Time

            return utc_iso(Time(str(date_obs).strip(), scale="utc").to_datetime(timezone.utc))
        except Exception:
            pass
    return utc_iso(datetime.fromtimestamp(os.path.getmtime(path), timezone.utc))


def _check_size(header) -> None:
    """Refuse an image too large to show, from its header alone."""
    naxis = int(header.get("NAXIS", 0) or 0)
    axes = [int(header.get(f"NAXIS{i}", 0) or 0) for i in range(1, naxis + 1)]
    if not axes:
        return
    elements = int(np.prod(axes, dtype=np.int64))
    sides = sorted(axes)[-2:]  # width and height, whatever the colour axis
    if elements > MAX_ELEMENTS or max(sides) > MAX_SIDE:
        shape = "×".join(str(n) for n in axes)
        raise FitsReadError(
            f"image too large to display ({shape}; limits {MAX_SIDE} px per side, "
            f"{MAX_ELEMENTS // 1_000_000} M samples)"
        )


def load_fits_frame(path: Path) -> tuple[np.ndarray, float, str]:
    """Return ``(pixels, exposure_s, timestamp)`` for the first image HDU of *path*.

    Raises:
        FitsReadError: Unreadable file, no image data, or an unsupported shape.
    """
    from astropy.io import fits

    try:
        with fits.open(path, memmap=False) as hdul:
            # Choose the HDU from headers only: touching .data loads the pixels.
            hdu = next(
                (
                    h
                    for h in hdul
                    if getattr(h, "is_image", False) and int(h.header.get("NAXIS", 0) or 0) > 0
                ),
                None,
            )
            if hdu is None:
                raise FitsReadError("no image data in the file")
            _check_size(hdu.header)
            if hdu.data is None:
                raise FitsReadError("no image data in the file")
            data = np.asarray(hdu.data)
            header = hdu.header
            exposure = header.get("EXPTIME", header.get("EXPOSURE", 0.0))
            timestamp = _timestamp(header, path)
    except FitsReadError:
        raise
    except Exception as exc:
        raise FitsReadError(f"not a readable FITS file ({exc})") from exc

    pixels = _to_uint16(_to_frame_shape(data))
    try:
        exposure_s = max(0.0, float(exposure))
    except (TypeError, ValueError):
        exposure_s = 0.0
    return np.ascontiguousarray(pixels), exposure_s, timestamp
