"""FITS file writer — science-grade compliant output for Seestar S30 Pro.

Writes 16-bit unsigned FITS files with a full set of standard headers
compatible with Siril, PixInsight, AstroImageJ, and other astronomy tools.

Header set follows NINA's production header list and the mandatory headers
defined in CLAUDE.md, extended with DATE-LOC, DATE-AVG, MJD-OBS, MJD-AVG
required for accurate photometric time analysis, plus EGAIN/CCD-TEMP/OFFSET/
AIRMASS/MOONSEP/TARGRA needed by the varstar postprod pipeline.
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

from argos.core.imaging import imx585, sky_geometry

# IMX585 physical characteristics (Seestar S30 Pro)
_PIXEL_SIZE_UM = 2.9
_FOCAL_LENGTH_MM = 160
_BAYER_PATTERN = "GRBG"
_TELESCOPE_NAME = "ZWO Seestar S30 Pro"
_INSTRUMENT = "IMX585"

# ISO 8601 datetime format with millisecond precision (FITS convention).
_DATETIME_FMT = "%Y-%m-%dT%H:%M:%S.%f"

# Default SOFTWARE/CREATOR string when callers don't pass one.
_DEFAULT_SOFTWARE = "Argos"


@dataclass
class FrameContext:
    """Mount/sky/camera/site state captured at exposure time.

    Every field is optional — missing data results in a missing FITS header
    rather than a failure. ``write()`` accepts ``None`` and falls back to
    defaults so callers in tests can stay minimal.
    """

    # Pointing reported by the mount at exposure start (J2000)
    ra: float | None = None
    dec: float | None = None
    altitude: float | None = None
    azimuth: float | None = None
    pier_side: str | None = None

    # What the user asked for — may differ from actual pointing after a slew
    target_ra: float | None = None
    target_dec: float | None = None

    # Dynamic camera state read just before/after exposure
    ccd_temp: float | None = None
    egain_driver: float | None = None  # e-/ADU from driver (None → IMX585 lookup)
    offset: int | None = None
    readout_mode: str | None = None

    # Frame metadata
    object_name: str = ""
    filter_name: str = "LRGB"

    # Observer + site (from Preferences)
    observer: str = ""
    site_lat: float | None = None
    site_lon: float | None = None
    site_elev: float | None = None

    # Software identity (from MainWindow.APP_VERSION)
    software: str = _DEFAULT_SOFTWARE

    # Free-form annotation for photometry sessions (e.g. "T CrB pre-outburst")
    annotation: str = ""

    # Per-frame quality metrics (display/QA, §7) — written if present.
    hfd: float | None = None
    star_count: int | None = None
    sky_adu: float | None = None
    fwhm: float | None = None
    eccentricity: float | None = None

    # Camera metadata snapshot for diagnostics (passed through, not written)
    sensor_meta: dict = field(default_factory=dict)


logger = logging.getLogger(__name__)

# Mapping from UI image type to FITS IMAGETYP value
IMAGE_TYPE_MAP = {
    "light": "Light Frame",
    "dark": "Dark Frame",
    "flat": "Flat Frame",
    "bias": "Bias Frame",
}

# Filter name → file-safe abbreviation
FILTER_ABBREV = {
    "LRGB": "LRGB",
    "Ha": "Ha",
    "OIII": "OIII",
    "SII": "SII",
    "IR-cut": "IRc",
}


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
            image_type="Light Frame",
            context=FrameContext(ra=..., dec=..., observer="JP", ...),
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
        image_type: str = "Light Frame",
        context: FrameContext | None = None,
    ) -> None:
        """Write a single FITS frame to disk.

        Args:
            arr:            2-D numpy uint16 array, shape (height, width).
            path:           Output file path (parent directory will be created).
            exposure_start: UTC datetime of exposure start.
            exposure_end:   UTC datetime when ImageReady became True.
            exposure_time:  Commanded exposure duration in seconds.
            gain:           Camera gain value used for this frame.
            image_type:     FITS IMAGETYP string ("Light Frame", "Dark Frame", …).
            context:        Mount/sky/camera/site state. Defaults to an empty
                            FrameContext if not provided (frame still writes,
                            just with fewer headers).

        Raises:
            ValueError: If ``arr`` is not 2-D.
            OSError:    If the file cannot be written.
        """
        if arr.ndim != 2:
            raise ValueError(f"Expected 2-D array, got shape {arr.shape}")

        ctx = context or FrameContext()
        height, width = arr.shape

        start, end = _ensure_utc(exposure_start), _ensure_utc(exposure_end)
        mid = start + (end - start) / 2

        egain, egain_source = _resolve_egain(gain, ctx.egain_driver)
        airmass = sky_geometry.compute_airmass(ctx.altitude) if ctx.altitude is not None else None
        moon = sky_geometry.compute_moon_info(
            when_utc=start,
            site_lat=ctx.site_lat,
            site_lon=ctx.site_lon,
            site_elev=ctx.site_elev,
            target_ra_hours=ctx.target_ra if ctx.target_ra is not None else ctx.ra,
            target_dec_deg=ctx.target_dec if ctx.target_dec is not None else ctx.dec,
        )

        hdr = fits.Header()
        _add_structure_headers(hdr, width, height, image_type)
        _add_timing_headers(hdr, start, mid, exposure_time)
        _add_sensor_headers(hdr, gain, egain, egain_source, ctx)
        _add_instrument_headers(hdr)
        _add_target_headers(hdr, ctx)
        _add_pointing_headers(hdr, ctx)
        _add_sky_headers(hdr, airmass, moon)
        _add_observer_headers(hdr, ctx)
        _add_software_headers(hdr, ctx)
        _add_quality_headers(hdr, ctx)

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fits.PrimaryHDU(data=arr, header=hdr).writeto(str(path), overwrite=True)
        logger.info(
            "FITS saved: %s  (%dx%d  %.1fs  gain=%d  EGAIN=%.3f e-/ADU [%s])",
            path.name,
            width,
            height,
            exposure_time,
            gain,
            egain,
            egain_source,
        )

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
        filter_name: str,
    ) -> Path:
        """Return the Siril-compatible session folder for a given frame.

        Structure::

            {base_dir}/sessions/{YYYYMMDD}_{OBJECT}/{ImageType}/{Filter}/

        Args:
            base_dir:       Root output directory (from config).
            object_name:    Target name.
            exposure_start: Frame timestamp.
            image_type:     FITS IMAGETYP string.
            filter_name:    Filter name.

        Returns:
            Path to the output folder (not yet created).
        """
        obj = _sanitize(object_name) or "Unknown"
        date = exposure_start.strftime("%Y%m%d")
        typ = image_type.replace(" Frame", "") + "s"  # e.g. "Lights"
        filt = _sanitize(FILTER_ABBREV.get(filter_name, filter_name))

        return base_dir / "sessions" / f"{date}_{obj}" / typ / filt

    @staticmethod
    def session_root(base_dir: Path, object_name: str, exposure_start: datetime) -> Path:
        """Return the per-session root folder (where ``session.json`` lives).

        Structure: ``{base_dir}/sessions/{YYYYMMDD}_{OBJECT}/`` — the parent of
        every ``{ImageType}/{Filter}/`` sub-folder produced by
        :meth:`session_folder` for the same target/date.

        Args:
            base_dir:       Root output directory (from config).
            object_name:    Target name.
            exposure_start: Reference timestamp (typically the first frame).

        Returns:
            Path to the session root folder (not yet created).
        """
        obj = _sanitize(object_name) or "Unknown"
        date = exposure_start.strftime("%Y%m%d")
        return base_dir / "sessions" / f"{date}_{obj}"


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


def _ensure_utc(dt: datetime) -> datetime:
    """Return ``dt`` as a tz-aware UTC datetime."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _resolve_egain(gain_setting: int, driver_value: float | None) -> tuple[float, str]:
    """Return (e-/ADU, source) — driver if available, else IMX585 lookup."""
    if driver_value and driver_value > 0:
        return float(driver_value), "driver"
    return float(imx585.lookup_egain(gain_setting)), "IMX585 lookup"


# --------------------------------------------------------------------------- #
# Per-section header builders                                                  #
# --------------------------------------------------------------------------- #


def _add_structure_headers(hdr: fits.Header, width: int, height: int, image_type: str) -> None:
    # BZERO=32768 / BSCALE=1 are added automatically by astropy for uint16 data
    hdr["SIMPLE"] = (True, "file conforms to FITS standard")
    hdr["BITPIX"] = (16, "number of bits per data pixel")
    hdr["NAXIS"] = (2, "number of data axes")
    hdr["NAXIS1"] = (width, "length of data axis 1 (X/columns)")
    hdr["NAXIS2"] = (height, "length of data axis 2 (Y/rows)")
    hdr["EXTEND"] = (True, "FITS dataset may contain extensions")
    hdr["IMAGETYP"] = (image_type, "type of image: Light/Dark/Flat/Bias")


def _add_timing_headers(hdr: fits.Header, start: datetime, mid: datetime, exptime: float) -> None:
    date_obs = start.strftime(_DATETIME_FMT)[:-3]
    date_avg = mid.strftime(_DATETIME_FMT)[:-3]
    date_loc = start.astimezone().strftime(_DATETIME_FMT)[:-3]
    hdr["DATE-OBS"] = (date_obs, "UTC date/time of exposure start")
    hdr["DATE-LOC"] = (date_loc, "local date/time of exposure start")
    hdr["DATE-AVG"] = (date_avg, "UTC date/time of exposure midpoint")
    hdr["MJD-OBS"] = (float(Time(start).mjd), "MJD of exposure start (UTC)")
    hdr["MJD-AVG"] = (float(Time(mid).mjd), "MJD of exposure midpoint (UTC)")
    hdr["EXPTIME"] = (exptime, "[s] exposure time")
    hdr["EXPOSURE"] = (exptime, "[s] exposure time (alias)")


def _add_sensor_headers(
    hdr: fits.Header,
    gain: int,
    egain: float,
    egain_source: str,
    ctx: "FrameContext",
) -> None:
    rdnoise = imx585.lookup_read_noise(gain)
    full_well = imx585.full_well_capacity(gain)
    eg = round(egain, 4)
    hdr["GAIN"] = (gain, "camera gain setting")
    hdr["EGAIN"] = (eg, f"[e-/ADU] electron gain ({egain_source})")
    hdr["EPERDN"] = (eg, "[e-/ADU] electron gain (alias)")
    hdr["GAIN_E"] = (eg, "[e-/ADU] electron gain (AAVSO alias)")
    hdr["RDNOISE"] = (round(rdnoise, 3), "[e-] read noise (IMX585 lookup)")
    hdr["FULLWELL"] = (int(full_well), "[e-] full-well capacity (IMX585 lookup)")
    hdr["XBINNING"] = (1, "binning factor X")
    hdr["YBINNING"] = (1, "binning factor Y")
    if ctx.ccd_temp is not None:
        hdr["CCD-TEMP"] = (round(float(ctx.ccd_temp), 2), "[degC] CCD/sensor temperature")
    if ctx.offset is not None:
        hdr["OFFSET"] = (int(ctx.offset), "electronic offset (bias setting)")
    if ctx.readout_mode is not None:
        hdr["READOUTM"] = (str(ctx.readout_mode)[:68], "sensor readout mode")


def _add_instrument_headers(hdr: fits.Header) -> None:
    hdr["TELESCOP"] = (_TELESCOPE_NAME, "telescope name")
    hdr["INSTRUME"] = (_INSTRUMENT, "sensor / instrument name")
    hdr["FOCALLEN"] = (_FOCAL_LENGTH_MM, "[mm] telescope focal length")
    hdr["FOCRATIO"] = (round(_FOCAL_LENGTH_MM / 50.0, 1), "focal ratio (f/number)")
    hdr["XPIXSZ"] = (_PIXEL_SIZE_UM, "[um] pixel size X (unbinned)")
    hdr["YPIXSZ"] = (_PIXEL_SIZE_UM, "[um] pixel size Y (unbinned)")
    hdr["BAYERPAT"] = (_BAYER_PATTERN, "Bayer color filter pattern")
    hdr["XBAYROFF"] = (0, "Bayer X offset")
    hdr["YBAYROFF"] = (0, "Bayer Y offset")
    hdr["EQUINOX"] = (2000.0, "equinox of celestial coordinate system")
    hdr["RADESYS"] = ("ICRS", "celestial coordinate reference system")


def _add_target_headers(hdr: fits.Header, ctx: "FrameContext") -> None:
    if ctx.object_name:
        hdr["OBJECT"] = (ctx.object_name[:68], "target object name")
    hdr["FILTER"] = (ctx.filter_name, "filter name")
    if ctx.target_ra is not None:
        hdr["TARGRA"] = (ctx.target_ra, "[h] requested target RA (J2000)")
    if ctx.target_dec is not None:
        hdr["TARGDEC"] = (ctx.target_dec, "[deg] requested target Dec (J2000)")


def _add_pointing_headers(hdr: fits.Header, ctx: "FrameContext") -> None:
    if ctx.ra is not None:
        hdr["RA"] = (ctx.ra, "[h] right ascension of pointing (J2000)")
        hdr["OBJCTRA"] = (_decimal_to_hms(ctx.ra), "right ascension of pointing (J2000)")
    if ctx.dec is not None:
        hdr["DEC"] = (ctx.dec, "[deg] declination of pointing (J2000)")
        hdr["OBJCTDEC"] = (_decimal_to_dms(ctx.dec), "declination of pointing (J2000)")
    if ctx.altitude is not None:
        hdr["ALTITUDE"] = (ctx.altitude, "[deg] telescope altitude")
    if ctx.azimuth is not None:
        hdr["AZIMUTH"] = (ctx.azimuth, "[deg] telescope azimuth")
    if ctx.pier_side:
        hdr["PIERSIDE"] = (str(ctx.pier_side)[:8], "side of pier")


def _add_sky_headers(hdr: fits.Header, airmass: float | None, moon: dict) -> None:
    if airmass is not None:
        hdr["AIRMASS"] = (airmass, "airmass at exposure start (Pickering)")
    if "moon_sep" in moon:
        hdr["MOONSEP"] = (moon["moon_sep"], "[deg] angular separation target-Moon")
    if "moon_alt" in moon:
        hdr["MOONALT"] = (moon["moon_alt"], "[deg] Moon altitude at site")
    if "moon_phase" in moon:
        hdr["MOONPHAS"] = (moon["moon_phase"], "Moon illuminated fraction (0-1)")


def _add_observer_headers(hdr: fits.Header, ctx: "FrameContext") -> None:
    if ctx.observer:
        hdr["OBSERVER"] = (ctx.observer[:68], "observer name")
    if ctx.site_lat is not None:
        hdr["SITELAT"] = (ctx.site_lat, "[deg] site latitude")
    if ctx.site_lon is not None:
        hdr["SITELONG"] = (ctx.site_lon, "[deg] site longitude (east positive)")
    if ctx.site_elev is not None:
        hdr["SITEELEV"] = (ctx.site_elev, "[m] site elevation")


def _add_software_headers(hdr: fits.Header, ctx: "FrameContext") -> None:
    sw = (ctx.software or _DEFAULT_SOFTWARE)[:68]
    hdr["SOFTWARE"] = (sw, "acquisition software")
    hdr["SWCREATE"] = (sw, "acquisition software (alias)")
    hdr["CREATOR"] = (sw, "acquisition software (alias)")
    if ctx.annotation:
        hdr["ANNOTATE"] = (ctx.annotation[:68], "session annotation")


def _add_quality_headers(hdr: fits.Header, ctx: "FrameContext") -> None:
    """Per-frame quality metrics (HFD, FWHM, star count, sky level) when available."""
    if ctx.hfd is not None:
        hdr["HFD"] = (round(float(ctx.hfd), 2), "[px] half-flux diameter (subsampled)")
    if ctx.fwhm is not None:
        hdr["FWHM"] = (round(float(ctx.fwhm), 2), "[px] mean star FWHM (green plane)")
    if ctx.star_count is not None:
        hdr["NSTARS"] = (int(ctx.star_count), "detected stars")
    if ctx.sky_adu is not None:
        hdr["SKYLEVEL"] = (round(float(ctx.sky_adu), 1), "[ADU] median sky background")
    if ctx.eccentricity is not None:
        hdr["ECCENTR"] = (round(float(ctx.eccentricity), 3), "mean star eccentricity (0=round)")
