"""FITS file writer — science-grade compliant output for Seestar S30 Pro.

Writes 16-bit unsigned FITS files with a full set of standard headers
compatible with Siril, PixInsight, AstroImageJ, and other astronomy tools.

Header set follows NINA's production header list and the mandatory headers
defined in CLAUDE.md, extended with DATE-LOC, DATE-AVG, MJD-OBS, MJD-AVG
required for accurate photometric time analysis.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time

# IMX585 physical characteristics (Seestar S30 Pro)
_PIXEL_SIZE_UM = 2.9
_FOCAL_LENGTH_MM = 160
_BAYER_PATTERN = "GRBG"
_TELESCOPE_NAME = "ZWO Seestar S30 Pro"
_INSTRUMENT = "IMX585"

logger = logging.getLogger(__name__)

LIGHT_FRAME = "Light Frame"

# Mapping from UI image type to FITS IMAGETYP value
IMAGE_TYPE_MAP = {
    "light": LIGHT_FRAME,
    "dark":  "Dark Frame",
    "flat":  "Flat Frame",
    "bias":  "Bias Frame",
}

# Filter name → file-safe abbreviation
FILTER_ABBREV = {
    "LRGB":   "LRGB",
    "Ha":     "Ha",
    "OIII":   "OIII",
    "SII":    "SII",
    "IR-cut": "IRc",
}

# Siril OSC script expected lowercase folder names per image type
_SIRIL_FOLDER: dict[str, str] = {
    LIGHT_FRAME: "lights",
    "Dark Frame":  "darks",
    "Flat Frame":  "flats",
    "Bias Frame":  "biases",
}

_DT_FMT = "%Y-%m-%dT%H:%M:%S.%f"


@dataclass
class FITSMeta:
    """Optional metadata written to FITS headers.

    Group pointing, target, filter, observer, and site info into one object
    so that FITSWriter.write() stays under the linter's parameter limit.
    """

    image_type:  str            = LIGHT_FRAME
    object_name: str            = ""
    filter_name: str            = "LRGB"
    ra:          float | None   = None   # decimal hours J2000
    dec:         float | None   = None   # decimal degrees J2000
    altitude:    float | None   = None
    azimuth:     float | None   = None
    observer:    str            = ""
    site_lat:    float | None   = None
    site_lon:    float | None   = None
    site_elev:   float | None   = None


class FITSWriter:
    """Writes science-grade FITS files for Seestar S30 Pro.

    Usage::

        FITSWriter.write(
            arr=numpy_uint16_array,
            path=Path("/path/to/output.fits"),
            exposure_start=datetime_utc,
            exposure_end=datetime_utc,
            exposure_time=10.0,
            gain=80,
            image_type=LIGHT_FRAME,
        )
    """

    @staticmethod
    def write(
        arr: np.ndarray,
        path: Path,
        exposure_start: datetime,
        exposure_end: datetime,
        exposure_time: float,
        gain: int,
        image_type: str = LIGHT_FRAME,
        ra: float | None = None,
        dec: float | None = None,
        altitude: float | None = None,
        azimuth: float | None = None,
        object_name: str = "",
        filter_name: str = "LRGB",
        observer: str = "",
        site_lat: float | None = None,
        site_lon: float | None = None,
        site_elev: float | None = None,
    ) -> None:
        """Write a single FITS frame to disk.

        Args:
            arr:            2-D numpy uint16 array, shape (height, width).
            path:           Output file path (parent directory must exist).
            exposure_start: UTC datetime of exposure start.
            exposure_end:   UTC datetime when ImageReady became True.
            exposure_time:  Commanded exposure duration in seconds.
            gain:           Camera gain value used for this frame.
            image_type:     FITS IMAGETYP string (LIGHT_FRAME, "Dark Frame", …).
            ra:             Target RA in decimal hours (J2000), or None.
            dec:            Target Dec in decimal degrees (J2000), or None.
            altitude:       Mount altitude in degrees at exposure start, or None.
            azimuth:        Mount azimuth in degrees at exposure start, or None.
            object_name:    Target name (e.g. "M42", "NGC 224").
            filter_name:    Filter name (e.g. "LRGB", "Ha").
            observer:       Observer name from config.
            site_lat:       Observer latitude in degrees.
            site_lon:       Observer longitude in degrees.
            site_elev:      Observer elevation in metres.

        Raises:
            OSError: If the file cannot be written.
        """
        if arr.ndim != 2:
            raise ValueError(f"Expected 2-D array, got shape {arr.shape}")

        height, width = arr.shape

        # Pass uint16 directly — astropy sets BZERO=32768 / BSCALE=1 automatically.
        # Manually converting to int16 then setting BZERO causes astropy to strip BZERO.

        # ------------------------------------------------------------------ #
        # Timing                                                               #
        # ------------------------------------------------------------------ #
        # Ensure aware datetimes (UTC)
        if exposure_start.tzinfo is None:
            exposure_start = exposure_start.replace(tzinfo=timezone.utc)
        if exposure_end.tzinfo is None:
            exposure_end = exposure_end.replace(tzinfo=timezone.utc)

        mid = exposure_start + (exposure_end - exposure_start) / 2

        t_start = Time(exposure_start)
        t_mid   = Time(mid)

        date_obs = exposure_start.strftime(_DT_FMT)[:-3]
        date_avg = mid.strftime(_DT_FMT)[:-3]
        date_loc = exposure_start.astimezone().strftime(_DT_FMT)[:-3]

        # ------------------------------------------------------------------ #
        # Build header                                                         #
        # ------------------------------------------------------------------ #
        hdr = fits.Header()

        # Primary structure
        hdr["SIMPLE"]   = (True,  "file conforms to FITS standard")
        hdr["BITPIX"]   = (16,    "number of bits per data pixel")
        hdr["NAXIS"]    = (2,     "number of data axes")
        hdr["NAXIS1"]   = (width, "length of data axis 1 (X/columns)")
        hdr["NAXIS2"]   = (height,"length of data axis 2 (Y/rows)")
        hdr["EXTEND"]   = (True,  "FITS dataset may contain extensions")
        # BZERO=32768 and BSCALE=1 are written automatically by astropy for uint16 data

        # Image type
        hdr["IMAGETYP"] = (image_type, "type of image: Light/Dark/Flat/Bias")

        # Acquisition timing
        hdr["DATE-OBS"] = (date_obs, "UTC date/time of exposure start")
        hdr["DATE-LOC"] = (date_loc, "local date/time of exposure start")
        hdr["DATE-AVG"] = (date_avg, "UTC date/time of exposure midpoint")
        hdr["MJD-OBS"]  = (float(t_start.mjd), "MJD of exposure start (UTC)")
        hdr["MJD-AVG"]  = (float(t_mid.mjd),   "MJD of exposure midpoint (UTC)")
        hdr["EXPTIME"]  = (exposure_time, "[s] exposure time")
        hdr["EXPOSURE"] = (exposure_time, "[s] exposure time (alias)")

        # Sensor configuration
        hdr["GAIN"]     = (gain, "camera gain")
        hdr["XBINNING"] = (1,    "binning factor X")
        hdr["YBINNING"] = (1,    "binning factor Y")

        # Instrument
        hdr["TELESCOP"] = (_TELESCOPE_NAME, "telescope name")
        hdr["INSTRUME"] = (_INSTRUMENT,     "sensor / instrument name")
        hdr["FOCALLEN"] = (_FOCAL_LENGTH_MM,"[mm] telescope focal length")
        hdr["FOCRATIO"] = (round(_FOCAL_LENGTH_MM / 50.0, 1), "focal ratio (f/number)")
        hdr["XPIXSZ"]   = (_PIXEL_SIZE_UM,  "[um] pixel size X (unbinned)")
        hdr["YPIXSZ"]   = (_PIXEL_SIZE_UM,  "[um] pixel size Y (unbinned)")
        hdr["BAYERPAT"] = (_BAYER_PATTERN,  "Bayer color filter pattern")
        hdr["XBAYROFF"] = (0, "Bayer X offset")
        hdr["YBAYROFF"] = (0, "Bayer Y offset")

        # Target object
        if object_name:
            hdr["OBJECT"] = (object_name[:68], "target object name")
        hdr["FILTER"] = (filter_name, "filter name")

        # Pointing (from mount, optional)
        if ra is not None:
            hdr["RA"]      = (ra,  "[h] right ascension of pointing (J2000)")
            hdr["OBJCTRA"] = (_decimal_to_hms(ra), "right ascension of pointing (J2000)")
        if dec is not None:
            hdr["DEC"]     = (dec, "[deg] declination of pointing (J2000)")
            hdr["OBJCTDEC"]= (_decimal_to_dms(dec), "declination of pointing (J2000)")
        if altitude is not None:
            hdr["ALTITUDE"] = (altitude, "[deg] telescope altitude")
        if azimuth is not None:
            hdr["AZIMUTH"]  = (azimuth,  "[deg] telescope azimuth")

        # Observer / site
        if observer:
            hdr["OBSERVER"] = (observer[:68], "observer name")
        if site_lat is not None:
            hdr["SITELAT"]  = (site_lat,  "[deg] site latitude")
        if site_lon is not None:
            hdr["SITELONG"] = (site_lon,  "[deg] site longitude (east positive)")
        if site_elev is not None:
            hdr["SITEELEV"] = (site_elev, "[m] site elevation")

        # ------------------------------------------------------------------ #
        # Write file                                                           #
        # ------------------------------------------------------------------ #
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        hdu = fits.PrimaryHDU(data=arr, header=hdr)
        hdu.writeto(str(path), overwrite=True)
        logger.info("FITS saved: %s  (%dx%d  %.1fs  gain=%d)", path.name, width, height, exposure_time, gain)

    @staticmethod
    def build_filename(
        object_name: str,
        image_type: str,
        exposure_start: datetime,
        exposure_time: float,
        filter_name: str,
        frame_index: int,
    ) -> str:
        """Build a filename following the project naming convention.

        Format: ``{OBJECT}_{IMAGETYP}_{DATE}_{TIME}_{EXPTIME}s_{FILTER}_{FRAME:04d}.fits``

        Args:
            object_name:    Target name (e.g. "M42"). Sanitized for filesystem.
            image_type:     FITS IMAGETYP string.
            exposure_start: UTC datetime of exposure start.
            exposure_time:  Exposure duration in seconds.
            filter_name:    Filter name.
            frame_index:    1-based frame counter.

        Returns:
            Filename string (no directory component).
        """
        obj = _sanitize(object_name) or "Unknown"
        typ = _sanitize(image_type.replace(" Frame", ""))
        date = exposure_start.strftime("%Y%m%d")
        tstr = exposure_start.strftime("%H%M%S")
        filt = _sanitize(FILTER_ABBREV.get(filter_name, filter_name))
        # Use integer seconds when whole number, else one decimal with "p" instead of "."
        if exposure_time == int(exposure_time):
            exp = str(int(exposure_time))
        else:
            exp = f"{exposure_time:.1f}".replace(".", "p")

        return f"{obj}_{typ}_{date}_{tstr}_{exp}s_{filt}_{frame_index:04d}.fits"

    @staticmethod
    def session_folder(
        base_dir: Path,
        object_name: str,
        exposure_start: datetime,
        image_type: str,
        filter_name: str = "",
    ) -> Path:
        """Return the Siril-compatible session folder for a given frame.

        Structure (lowercase folder names as expected by Siril's built-in scripts)::

            {base_dir}/{YYYYMMDD}_{OBJECT}/{frame_type}/

        Args:
            base_dir:       Root output directory chosen by the user.
            object_name:    Target name (used for Lights; "calibration" otherwise).
            exposure_start: Frame timestamp.
            image_type:     FITS IMAGETYP string (LIGHT_FRAME, "Dark Frame", …).
            filter_name:    Unused (kept for backward compatibility).

        Returns:
            Path to the output folder (not yet created).
        """
        obj  = _sanitize(object_name) if object_name else "calibration"
        date = exposure_start.strftime("%Y%m%d")
        typ  = _SIRIL_FOLDER.get(image_type, "misc")

        return base_dir / f"{date}_{obj}" / typ


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _sanitize(s: str) -> str:
    """Remove characters that are unsafe in filenames."""
    return re.sub(r"[^\w\-]", "", s.replace(" ", "_"))


def _decimal_to_hms(ra_hours: float) -> str:
    """Convert decimal RA hours to sexagesimal string ``HH MM SS.ss``."""
    total = abs(ra_hours) * 3600.0
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = total % 60
    return f"{h:02d} {m:02d} {s:05.2f}"


def _decimal_to_dms(dec_deg: float) -> str:
    """Convert decimal Dec degrees to sexagesimal string ``±DD MM SS.s``."""
    sign = "+" if dec_deg >= 0 else "-"
    total = abs(dec_deg) * 3600.0
    d = int(total // 3600)
    m = int((total % 3600) // 60)
    s = total % 60
    return f"{sign}{d:02d} {m:02d} {s:04.1f}"
