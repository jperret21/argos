"""Tests for the differential-photometry core (Qt-free, no hardware)."""

from __future__ import annotations

import csv
from datetime import datetime, timezone

import numpy as np

from argos.core.photometry.airmass import (
    airmass_from_altitude,
    bjd_tdb,
    julian_date,
    utc_from_bjd_tdb,
)
from argos.core.photometry.aperture import measure_aperture
from argos.core.photometry.differential import differential_mag, ensemble_zero_point, relative_flux
from argos.core.photometry.lightcurve import LcPoint, LightCurve, read_curves_csv, write_curves_csv


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
    zp, rms, n, rejected = ensemble_zero_point([(-5.0, 10.0), (-5.0, 10.0)])
    assert zp == 15.0 and rms == 0.0 and n == 2 and rejected == 0
    assert ensemble_zero_point([]) == (None, None, 0, 0)


def test_relative_flux_needs_no_catalogue_magnitudes() -> None:
    result = relative_flux(1000.0, 100.0, [(400.0, 50.0), (600.0, 60.0)])
    assert result.flux_ratio == 1.0
    assert result.flux_ratio_err is not None and result.flux_ratio_err > 0
    assert result.comps_used == 2


def test_ensemble_clips_a_bad_comp() -> None:
    """P3: one polluted comp (blend/cloud/bad catalog mag) must not drag the
    zero-point — median+MAD clipping drops it and reports it."""
    good = [(-5.0, 10.0), (-5.005, 10.0), (-4.995, 10.0)]
    bad = [(-5.5, 10.0)]  # 0.5 mag off
    zp, rms, n, rejected = ensemble_zero_point(good + bad)
    assert rejected == 1 and n == 3
    assert abs(zp - 15.0) < 0.01  # the clean answer, not the dragged mean
    r = differential_mag(-6.0, 0.01, good + bad)
    assert r.comps_used == 3 and "1 comp(s) clipped" in r.note
    assert abs(r.mag - 9.0) < 0.01


def test_ensemble_never_clips_below_two_or_tight_pairs() -> None:
    # Two comps: no clipping possible even if they disagree.
    zp, _, n, rejected = ensemble_zero_point([(-5.0, 10.0), (-5.3, 10.0)])
    assert n == 2 and rejected == 0
    # Scatter within the 10 mmag floor: nothing rejected.
    tight = [(-5.0, 10.0), (-5.004, 10.0), (-4.996, 10.0), (-5.002, 10.0)]
    _, _, n, rejected = ensemble_zero_point(tight)
    assert n == 4 and rejected == 0


def test_differential_mag_calibrates_target() -> None:
    comps = [(-5.0, 10.0), (-5.0, 10.0)]  # zp = 15
    r = differential_mag(-6.0, 0.01, comps)
    assert abs(r.mag - 9.0) < 1e-9
    assert r.comps_used == 2 and r.note == ""
    assert r.mag_err is not None and r.mag_err >= 0.01
    assert r.formal_mag_err == r.mag_err


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
    assert "bjd_tdb" in rows[0]
    assert len(rows) == 3  # header + 2 points
    assert rows[2][-1] == "1"  # saturated flag serialised as 1


def test_lightcurve_from_csv_round_trips(tmp_path) -> None:
    lc = LightCurve(auid="000-BBB-001", name="NU Ori")
    lc.append(
        LcPoint(
            jd_utc=2451545.0,
            mag=9.0,
            mag_err=0.02,
            formal_mag_err=0.015,
            sigma_syst=0.01,
            airmass=1.2,
            comps_used=3,
        )
    )
    lc.append(LcPoint(jd_utc=2451545.1, mag=9.1, mag_err=0.03, saturated=True))
    path = tmp_path / "photometry.csv"
    lc.to_csv(path)

    back = LightCurve.from_csv(path, auid="000-BBB-001", name="NU Ori")
    assert len(back.points) == 2
    p0, p1 = back.points
    assert p0.jd_utc == 2451545.0 and p0.mag == 9.0 and p0.mag_err == 0.02
    assert p0.airmass == 1.2 and p0.comps_used == 3
    assert p0.formal_mag_err == 0.015 and p0.sigma_syst == 0.01
    assert p0.bjd_tdb is None and p0.fwhm is None  # blank optionals → None
    assert p1.saturated is True
    # Reloaded curve re-exports to the same AAVSO data as the original.
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    lc.to_aavso(a, obscode="ABC")
    back.to_aavso(b, obscode="ABC")
    assert a.read_text() == b.read_text()


def test_lightcurve_from_csv_skips_bad_rows(tmp_path) -> None:
    path = tmp_path / "partial.csv"
    path.write_text(
        "jd_utc,bjd_tdb,mag,mag_err,airmass,fwhm,sky_adu,comps_used,saturated\n"
        "2451545.0,,9.0,0.02,,,,,0\n"
        "bogus,,oops,,,,,,\n"  # unparseable → skipped, no crash
        "2451545.2,,9.2,0.03,,,,,0\n",
        encoding="utf-8",
    )
    lc = LightCurve.from_csv(path)
    assert [p.jd_utc for p in lc.points] == [2451545.0, 2451545.2]


def test_multi_curve_csv_preserves_star_identity_and_roles(tmp_path) -> None:
    target = LightCurve(auid="T", name="NU Ori", role="target")
    target.append(LcPoint(jd_utc=2451545.0, mag=9.0, mag_err=0.02))
    comparison = LightCurve(auid="C1", name="Comp 1", role="comparison")
    comparison.append(LcPoint(jd_utc=2451545.0, mag=11.0, mag_err=0.03))
    path = tmp_path / "measurements.csv"
    write_curves_csv(path, [target, comparison])
    restored = read_curves_csv(path)
    assert set(restored) == {"T", "C1"}
    assert restored["T"].role == "target"
    assert restored["C1"].role == "comparison"


def test_lightcurve_aavso_export(tmp_path) -> None:
    lc = LightCurve(name="NU Ori")
    lc.append(LcPoint(jd_utc=2451545.0, mag=9.0, mag_err=0.02, airmass=1.2))
    path = tmp_path / "aavso.txt"
    lc.to_aavso(path, obscode="ABC", filt="TG")
    text = path.read_text().splitlines()
    assert "#TYPE=EXTENDED" in text and "#OBSCODE=ABC" in text
    data = [ln for ln in text if not ln.startswith("#")]
    assert data and data[0].startswith("NU ORI,2451545.0")
    assert ",TG,NO,STD,ENSEMBLE," in data[0]


def test_aavso_export_ignores_comparison_diagnostics(tmp_path) -> None:
    target = LightCurve(name="NU Ori", role="target")
    target.append(LcPoint(jd_utc=2451545.0, mag=9.0, mag_err=0.02))
    comparison = LightCurve(name="C1", role="comparison")
    comparison.append(LcPoint(jd_utc=2451545.0, mag=11.0, mag_err=0.03))
    path = tmp_path / "aavso.txt"
    from argos.core.photometry.lightcurve import write_aavso

    write_aavso(path, [target, comparison], obscode="ABC", filt="TG")
    data = [ln for ln in path.read_text().splitlines() if not ln.startswith("#")]
    assert len(data) == 1
    assert data[0].startswith("NU ORI,")


def test_bjd_tdb_close_to_jd() -> None:
    # BJD−JD is at most ~8.3 min (0.0058 d); just check the correction is sane.
    bjd = bjd_tdb(2451545.0, ra_deg=83.6, dec_deg=22.0, lat_deg=43.6, lon_deg=1.4, elev_m=150.0)
    assert bjd is not None
    assert abs(bjd - 2451545.0) < 0.01


def test_bjd_tdb_to_local_utc_round_trip() -> None:
    original = datetime(2026, 8, 28, 5, 30, tzinfo=timezone.utc)
    jd = julian_date(original)
    bjd = bjd_tdb(jd, ra_deg=300.1821, dec_deg=22.7099, lat_deg=43.6, lon_deg=1.4)
    assert bjd is not None
    recovered = utc_from_bjd_tdb(bjd, 300.1821, 22.7099, 43.6, 1.4)
    assert recovered is not None
    assert abs((recovered - original).total_seconds()) < 0.1


# --------------------------------------------------------------------------- #
# hot-pixel suspect flag (P9)                                                  #
# --------------------------------------------------------------------------- #


def _noisy_sky(shape=(60, 60), sky=200.0, sigma=3.0, seed=7):
    rng = np.random.default_rng(seed)
    return rng.normal(sky, sigma, shape).astype(np.float32)


def test_hot_pixel_is_flagged_suspect() -> None:
    from argos.core.photometry.aperture import measure_aperture

    g = _noisy_sky()
    g[30, 30] = 5000.0  # single hot pixel, no PSF
    phot = measure_aperture(g, 30.0, 30.0, r_ap=5, r_in=8, r_out=12)
    assert phot is not None and phot.suspect is True


def test_real_star_is_not_suspect() -> None:
    from argos.core.photometry.aperture import measure_aperture

    g = _noisy_sky()
    yy, xx = np.mgrid[0:60, 0:60]
    g += 5000.0 * np.exp(-((xx - 30.0) ** 2 + (yy - 30.0) ** 2) / (2 * 1.5**2))
    phot = measure_aperture(g, 30.0, 30.0, r_ap=5, r_in=8, r_out=12)
    assert phot is not None and phot.suspect is False


def test_faint_signal_is_not_accused() -> None:
    from argos.core.photometry.aperture import measure_aperture

    g = _noisy_sky()  # nothing but sky noise — peak is not significant
    phot = measure_aperture(g, 30.0, 30.0, r_ap=5, r_in=8, r_out=12)
    assert phot is not None and phot.suspect is False
