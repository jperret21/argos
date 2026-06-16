"""Tests for the differential-photometry core (Qt-free, no hardware)."""

from __future__ import annotations

import csv
from datetime import datetime, timezone

import numpy as np

from seercontrol.core.photometry.airmass import airmass_from_altitude, julian_date
from seercontrol.core.photometry.aperture import measure_aperture
from seercontrol.core.photometry.differential import differential_mag, ensemble_zero_point
from seercontrol.core.photometry.lightcurve import LcPoint, LightCurve


def _star(cx, cy, peak=10000.0, sky=200.0, sigma=1.5, shape=(40, 40)) -> np.ndarray:
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    g = sky + peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2))
    return g.astype(np.float32)


# --------------------------------------------------------------------------- #
# aperture                                                                     #
# --------------------------------------------------------------------------- #


def test_measure_aperture_recovers_flux_and_sky() -> None:
    g = _star(20, 20, peak=10000.0, sky=200.0)
    phot = measure_aperture(g, 20, 20, r_ap=6, r_in=8, r_out=12)
    assert phot is not None
    assert phot.flux_adu > 0
    assert abs(phot.sky_adu - 200.0) < 5.0  # annulus median ≈ sky
    assert phot.inst_mag is not None and phot.inst_mag_err is not None
    assert phot.snr > 0
    assert phot.saturated is False


def test_measure_aperture_flags_saturation() -> None:
    g = _star(20, 20, peak=70000.0, sky=200.0)
    phot = measure_aperture(g, 20, 20, r_ap=6, r_in=8, r_out=12, sat_adu=60000.0)
    assert phot is not None and phot.saturated is True


def test_measure_aperture_off_frame_returns_none() -> None:
    g = _star(20, 20)
    assert measure_aperture(g, -50, -50, r_ap=6, r_in=8, r_out=12) is None


def test_measure_aperture_no_flux_has_no_mag() -> None:
    g = np.full((40, 40), 200.0, np.float32)  # flat → background-subtracted flux ≈ 0
    phot = measure_aperture(g, 20, 20, r_ap=6, r_in=8, r_out=12)
    assert phot is not None
    assert phot.inst_mag is None and phot.inst_mag_err is None


# --------------------------------------------------------------------------- #
# differential                                                                 #
# --------------------------------------------------------------------------- #


def test_ensemble_zero_point() -> None:
    zp, rms, n = ensemble_zero_point([(-5.0, 10.0), (-5.0, 10.0)])
    assert zp == 15.0 and rms == 0.0 and n == 2
    assert ensemble_zero_point([]) == (None, None, 0)


def test_differential_mag_calibrates_target() -> None:
    comps = [(-5.0, 10.0), (-5.0, 10.0)]  # zp = 15
    r = differential_mag(-6.0, 0.01, comps)
    assert abs(r.mag - 9.0) < 1e-9
    assert r.comps_used == 2 and r.note == ""
    assert r.mag_err is not None and r.mag_err >= 0.01


def test_differential_mag_flags_too_few_comps() -> None:
    r = differential_mag(-6.0, 0.01, [(-5.0, 10.0)], min_comps=2)
    assert r.comps_used == 1 and "1 comparison" in r.note


def test_differential_mag_no_comps_or_no_flux() -> None:
    assert differential_mag(-6.0, 0.01, []).mag is None
    assert differential_mag(None, None, [(-5.0, 10.0)]).note == "no target flux"


# --------------------------------------------------------------------------- #
# airmass + JD                                                                 #
# --------------------------------------------------------------------------- #


def test_airmass_zenith_and_horizon() -> None:
    assert abs(airmass_from_altitude(90.0) - 1.0) < 0.01
    assert airmass_from_altitude(30.0) > 1.9  # ~2 airmasses at 30°
    assert airmass_from_altitude(0.0) is None
    assert airmass_from_altitude(None) is None


def test_julian_date_j2000() -> None:
    assert julian_date(datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)) == 2451545.0
    assert julian_date(datetime(2000, 1, 1, 0, 0, 0, tzinfo=timezone.utc)) == 2451544.5


# --------------------------------------------------------------------------- #
# light curve                                                                  #
# --------------------------------------------------------------------------- #


def test_lightcurve_csv_round_trip(tmp_path) -> None:
    lc = LightCurve(auid="000-BBB-001", name="NU Ori")
    lc.append(LcPoint(jd_utc=2451545.0, mag=9.0, mag_err=0.02, airmass=1.2, comps_used=3))
    lc.append(LcPoint(jd_utc=2451545.1, mag=9.1, mag_err=0.03, saturated=True))
    path = tmp_path / "sub" / "photometry.csv"
    lc.to_csv(path)
    rows = list(csv.reader(path.open()))
    assert rows[0][0] == "jd_utc" and rows[0][-1] == "saturated"
    assert len(rows) == 3  # header + 2 points
    assert rows[2][-1] == "1"  # saturated flag serialised as 1
