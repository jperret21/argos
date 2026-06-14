"""End-to-end checks for science-grade FITS output."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from seercontrol.core.imaging.fits_writer import FITSWriter, FrameContext

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _write_frame(
    tmp_path: Path,
    context: FrameContext | None = None,
    gain: int = 80,
) -> fits.Header:
    arr = np.zeros((50, 80), dtype=np.uint16)
    arr[20:30, 30:50] = 30_000
    start = datetime(2026, 5, 29, 22, 30, 0, tzinfo=timezone.utc)
    end = start + timedelta(seconds=10)

    path = tmp_path / "frame.fits"
    FITSWriter.write(arr, path, start, end, 10.0, gain, context=context)
    return fits.getheader(path)


# --------------------------------------------------------------------------- #
# Mandatory science headers                                                    #
# --------------------------------------------------------------------------- #


def test_minimal_write_still_carries_electron_gain(tmp_path: Path) -> None:
    """Even without a FrameContext, EGAIN must come from IMX585 lookup."""
    hdr = _write_frame(tmp_path)
    assert "EGAIN" in hdr
    assert "EPERDN" in hdr
    assert "GAIN_E" in hdr
    assert 0.05 < float(hdr["EGAIN"]) < 30


def test_quality_headers_written_when_metrics_present(tmp_path: Path) -> None:
    """Per-frame QA metrics (§7) land in the FITS header when provided."""
    ctx = FrameContext(hfd=3.4, star_count=42, sky_adu=812.5)
    hdr = _write_frame(tmp_path, ctx)
    assert float(hdr["HFD"]) == 3.4
    assert int(hdr["NSTARS"]) == 42
    assert float(hdr["SKYLEVEL"]) == 812.5


def test_quality_headers_absent_without_metrics(tmp_path: Path) -> None:
    hdr = _write_frame(tmp_path)
    assert "HFD" not in hdr
    assert "NSTARS" not in hdr
    assert "SKYLEVEL" not in hdr


def test_postprod_pipeline_can_extract_egain(tmp_path: Path) -> None:
    """varstar postprod's get_gain_eadu() accepts 0.05 < g < 30 — verify range."""
    hdr = _write_frame(tmp_path, gain=80)
    g = float(hdr["EGAIN"])
    # Replicates the bounds check in star_var_script/pipeline.py:706
    assert 0.05 < g < 30


def test_software_identity_headers_present(tmp_path: Path) -> None:
    ctx = FrameContext(software="SeerControl v1.2.3")
    hdr = _write_frame(tmp_path, context=ctx)
    assert hdr["SOFTWARE"] == "SeerControl v1.2.3"
    assert hdr["SWCREATE"] == "SeerControl v1.2.3"
    assert hdr["CREATOR"] == "SeerControl v1.2.3"


def test_astrometry_frame_headers(tmp_path: Path) -> None:
    hdr = _write_frame(tmp_path)
    assert hdr["EQUINOX"] == 2000.0
    assert hdr["RADESYS"] == "ICRS"
    assert hdr["BAYERPAT"] == "GRBG"


# --------------------------------------------------------------------------- #
# Optional headers — written only when data available                          #
# --------------------------------------------------------------------------- #


def test_pointing_headers_added_when_position_known(tmp_path: Path) -> None:
    ctx = FrameContext(ra=5.59, dec=-5.39, altitude=40.0, azimuth=180.0)
    hdr = _write_frame(tmp_path, context=ctx)
    assert hdr["RA"] == pytest.approx(5.59)
    assert hdr["DEC"] == pytest.approx(-5.39)
    assert hdr["ALTITUDE"] == pytest.approx(40.0)
    assert hdr["AZIMUTH"] == pytest.approx(180.0)
    assert hdr["OBJCTRA"] == "05 35 24.00"
    assert hdr["OBJCTDEC"] == "-05 23 24.0"


def test_target_distinct_from_pointing(tmp_path: Path) -> None:
    """TARGRA/TARGDEC track the requested coords even after a slight slew miss."""
    ctx = FrameContext(ra=5.59, dec=-5.39, target_ra=5.60, target_dec=-5.40)
    hdr = _write_frame(tmp_path, context=ctx)
    assert hdr["RA"] == pytest.approx(5.59)
    assert hdr["TARGRA"] == pytest.approx(5.60)


def test_airmass_only_above_horizon(tmp_path: Path) -> None:
    above = _write_frame(tmp_path, context=FrameContext(altitude=45.0))
    below = _write_frame(tmp_path, context=FrameContext(altitude=-5.0))
    assert "AIRMASS" in above
    assert above["AIRMASS"] == pytest.approx(1.41, abs=0.05)
    assert "AIRMASS" not in below


def test_camera_runtime_state_when_provided(tmp_path: Path) -> None:
    ctx = FrameContext(ccd_temp=12.5, offset=10, readout_mode="HCG", egain_driver=0.42)
    hdr = _write_frame(tmp_path, context=ctx, gain=300)
    assert hdr["CCD-TEMP"] == pytest.approx(12.5)
    assert hdr["OFFSET"] == 10
    assert hdr["READOUTM"] == "HCG"
    # Driver value should override the lookup table
    assert hdr["EGAIN"] == pytest.approx(0.42)


def test_camera_runtime_state_omitted_when_absent(tmp_path: Path) -> None:
    """Driver may not expose CCDTemperature — header simply absent, no crash."""
    hdr = _write_frame(tmp_path, context=FrameContext())
    assert "CCD-TEMP" not in hdr
    assert "OFFSET" not in hdr
    assert "READOUTM" not in hdr


def test_moon_info_when_site_and_target_provided(tmp_path: Path) -> None:
    ctx = FrameContext(
        ra=5.59,
        dec=-5.39,
        target_ra=5.59,
        target_dec=-5.39,
        site_lat=48.85,
        site_lon=2.35,
        site_elev=35.0,
    )
    hdr = _write_frame(tmp_path, context=ctx)
    assert "MOONSEP" in hdr
    assert "MOONALT" in hdr
    assert "MOONPHAS" in hdr
    assert 0.0 <= float(hdr["MOONPHAS"]) <= 1.0
