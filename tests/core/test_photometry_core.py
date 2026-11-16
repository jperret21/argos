"""Tests for the differential-photometry core (Qt-free, no hardware)."""

from __future__ import annotations

import csv
import math
from datetime import datetime, timezone

import numpy as np
import pytest

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
    zp, rms, n, rejected, zp_err = ensemble_zero_point([(-5.0, 10.0), (-5.0, 10.0)])
    assert zp == 15.0 and rms == 0.0 and n == 2 and rejected == 0
    assert zp_err == pytest.approx(0.01 / math.sqrt(2))  # the 10 mmag floor, twice
    assert ensemble_zero_point([]) == (None, None, 0, 0, None)


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
    zp, rms, n, rejected, _err = ensemble_zero_point(good + bad)
    assert rejected == 1 and n == 3
    assert abs(zp - 15.0) < 0.01  # the clean answer, not the dragged mean
    r = differential_mag(-6.0, 0.01, good + bad)
    assert r.comps_used == 3 and "1 comp(s) clipped" in r.note
    assert abs(r.mag - 9.0) < 0.01


def test_ensemble_never_clips_below_two_or_tight_pairs() -> None:
    # Two comps: no clipping possible even if they disagree.
    zp, _, n, rejected, _err = ensemble_zero_point([(-5.0, 10.0), (-5.3, 10.0)])
    assert n == 2 and rejected == 0
    # Scatter within the 10 mmag floor: nothing rejected.
    tight = [(-5.0, 10.0), (-5.004, 10.0), (-4.996, 10.0), (-5.002, 10.0)]
    _, _, n, rejected, _err = ensemble_zero_point(tight)
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


# S71: the zero point weighs each comparison by 1 / (err² + 10 mmag²).

#: XX Cyg 2026-08-29 (session 20260829T050148Z), flight-recorder frames 15 and 18: each
#: comparison's (inst_mag, VSP V, inst_mag_err); one comparison at SNR 21, the others
#: at SNR 0.6-3.1. The check 000-BJV-171 (V 10.606) is (inst_mag, inst_mag_err).
_XX_CYG_0829 = {
    15: (
        [(-5.5103, 13.397, 1.9016), (-9.454, 10.389, 0.0511), (-6.6663, 12.948, 0.6598)]
        + [(-6.7387, 14.153, 0.6142)],
        (-9.2352, 0.0632),
    ),
    18: (
        [(-7.3488, 13.397, 0.3506), (-9.4859, 10.389, 0.05), (-6.8229, 12.948, 0.57)],
        (-9.1663, 0.0668),
    ),
}


def test_zero_point_follows_the_comparisons_errors_s71() -> None:
    """XX Cyg 2026-08-29: the unweighted mean of four comparisons, three of them at SNR
    0.6-1.8, put the check 0.2-0.6 mag off its VSP V (run mean +0.28 ± 0.08). Weighted,
    the bright comparison carries the zero point and the error says how well."""
    for frame, (comps, (inst, err)) in _XX_CYG_0829.items():
        zp, _rms, n, rejected, zp_err = ensemble_zero_point(comps)
        assert n == len(comps) and rejected == 0, frame  # the bright one is not clipped
        bright = 10.389 - comps[1][0]  # 000-BJV-170, 97-99 % of the weight
        assert abs(zp - bright) < 0.02, frame  # plain mean: 0.029 and 0.052 off
        assert zp_err >= 0.05, frame
        r = differential_mag(inst, err, comps)
        assert r.zp_err == pytest.approx(zp_err, abs=1e-4)
        assert r.formal_mag_err == pytest.approx(math.hypot(err, zp_err), abs=2e-4)
        assert abs(r.mag - 10.606) <= 2 * r.formal_mag_err, frame


def test_one_bright_comparison_cannot_take_all_the_weight_s71() -> None:
    # Without the 10 mmag floor a 0.1 mmag error would weigh 40 000 times the other.
    zp, *_rest, zp_err = ensemble_zero_point([(-5.0, 10.0, 0.0001), (-5.02, 10.0, 0.02)])
    assert zp == pytest.approx(15.0 + 0.02 * 0.2 / 1.2, abs=1e-4)  # weights 1 : 0.2
    assert zp_err >= 0.01 / math.sqrt(1.2)


def test_reddish_comparison_still_clipped_s71() -> None:
    """RR Lyr 2026-09-25, recorder frame 0 (check 000-BCG-523 left out): 000-BCG-953,
    B−V 1.67, sits 0.16 mag off the ensemble; the normalised clip drops it."""
    comps = [
        (-11.8564, 7.567, 0.0089),  # 000-BJW-665
        (-11.6749, 7.924, 0.0103),  # 000-BCG-953
        (-11.5633, 7.902, 0.0111),  # 000-BJW-666
        (-11.3584, 8.099, 0.0132),  # 000-BJW-667
        (-10.9351, 8.493, 0.0188),  # 000-BJW-668
    ]
    zp, _rms, n, rejected, _err = ensemble_zero_point(comps)
    assert rejected >= 1 and n == len(comps) - rejected
    without = ensemble_zero_point(comps[:1] + comps[2:])
    assert zp == pytest.approx(without[0], abs=1e-9)  # as if 953 were not there
    assert abs(zp - ensemble_zero_point([c[:2] for c in comps])[0]) < 0.01


def test_a_heavy_comparison_its_ensemble_contradicts_flags_the_point_s71() -> None:
    """S71 (technical review): the clip is centred on the weighted median, so a comparison
    holding over half the weight is never clipped. A bright one 0.30 mag off (variable,
    blended, coloured) against two good faint ones set the zero point at +0.25 with
    nothing clipped and nothing flagged; its point is now suspect, with a note."""
    comps = [(0.0, 0.30, 0.002), (0.0, 0.0, 0.03), (0.0, 0.0, 0.03)]
    zp, _rms, _n, rejected, _err = ensemble_zero_point(comps)
    assert rejected == 0 and zp == pytest.approx(0.248, abs=0.001)
    r = differential_mag(10.0, 0.01, comps)
    assert r.suspect and "disagrees with the others" in r.note
    # the same bright comparison agreeing with them: no flag
    agreeing = [(0.0, 0.0, 0.002), (0.0, 0.02, 0.03), (0.0, -0.02, 0.03)]
    assert not differential_mag(10.0, 0.01, agreeing).suspect
    # two comparisons that disagree: no majority against the heavier one, no flag
    assert not differential_mag(10.0, 0.01, [(0.0, 0.0, 0.005), (0.0, 0.1, 0.01)]).suspect
    # no comparison over half the weight (RR Lyr-like ensemble): never flagged
    assert not differential_mag(10.0, 0.01, [(0.0, 0.0, 0.01)] * 3 + [(0.0, 0.5, 0.01)]).suspect


def test_the_xx_cyg_frames_keep_their_bright_comparison_unflagged_s71() -> None:
    """XX Cyg 2026-08-29 frames 15 and 18: 000-BJV-170 holds 97-99 % of the weight and its
    faint comparisons agree within their errors: no flag (3 of the run's 22 frames are)."""
    for frame, (comps, (inst, err)) in _XX_CYG_0829.items():
        assert not differential_mag(inst, err, comps).suspect, frame


# S72: the noise model of the (G1+G2)/2 plane, with the black level.


def _cfa_frame(rng, *, egain, black, sky_e, rn_e, star_e=0.0, shape=(240, 240)):
    """A GRBG raw frame in ADU: black + (Poisson(sky + star) + read noise) / egain."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    # the star on the green plane's grid (green px = raw px / 2), sigma 1.2 green px
    gx, gy = xx / 2.0, yy / 2.0
    psf = np.exp(-((gx - 40.0) ** 2 + (gy - 40.0) ** 2) / (2 * 1.2**2)) / (2 * np.pi * 1.2**2)
    electrons = rng.poisson(sky_e + star_e * psf / 4.0) + rng.normal(0.0, rn_e, shape)
    return black + electrons / egain


def test_noise_model_is_the_green_planes_s72() -> None:
    """The model's sky sigma and a star's error match what a (G1+G2)/2 plane measures.

    Before S72 the model took the raw pixel's gain and counted the black level as sky
    photons: here 2.4 times the real sky sigma (W7: 38.3 against 20.6 ADU on RR Lyr).
    """
    from argos.core.imaging.green import green_plane
    from argos.core.photometry.aperture import sky_sigma_adu

    rng = np.random.default_rng(72)
    egain, black, sky_e, rn_e, star_e = 0.8, 1024.0, 150.0, 2.8, 60000.0
    fluxes, snrs, skies = [], [], []
    for _ in range(200):
        raw = _cfa_frame(rng, egain=egain, black=black, sky_e=sky_e, rn_e=rn_e, star_e=star_e)
        g = green_plane(raw)
        phot = measure_aperture(
            g,
            40.0,
            40.0,
            r_ap=4.0,
            r_in=12.0,
            r_out=38.0,
            egain=egain,
            read_noise_e=rn_e,
            black_adu=black,
            plane_pixels=2,
        )
        fluxes.append(phot.flux_adu)
        snrs.append(phot.snr)
        skies.append(g[85:, 85:].std())
    measured_sky = float(np.mean(skies))
    model_sky = sky_sigma_adu(
        black + sky_e / egain, egain=egain, read_noise_e=rn_e, black_adu=black, plane_pixels=2
    )
    assert model_sky == pytest.approx(measured_sky, rel=0.03)
    model_err = float(np.mean(fluxes) / np.mean(snrs))
    assert model_err == pytest.approx(float(np.std(fluxes, ddof=1)), rel=0.10)


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
    assert rows[0][0] == "jd_utc" and rows[0][-1] == "suspect"
    assert "bjd_tdb" in rows[0]
    assert "suspect" in rows[0]  # the PSF-support flag reaches the export
    assert len(rows) == 3  # header + 2 points
    sat = rows[0].index("saturated")
    assert rows[2][sat] == "1"  # saturated flag serialised as 1


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


def test_aavso_export_names_the_check_star_and_the_vsp_chart(tmp_path) -> None:
    from argos.core.photometry.lightcurve import write_aavso

    target = LightCurve(auid="000-BCK-301", name="XX Cyg", role="target")
    check = LightCurve(auid="000-BJV-171", name="106", role="check")
    for jd, mag in ((2451545.0, 11.0), (2451545.01, 11.1), (2451545.02, 11.2)):
        target.append(LcPoint(jd_utc=jd, mag=mag, mag_err=0.02))
    check.append(LcPoint(jd_utc=2451545.0, mag=10.61, mag_err=0.01))
    check.append(LcPoint(jd_utc=2451545.01, mag=float("nan"), mag_err=float("nan")))
    path = tmp_path / "aavso.txt"
    write_aavso(path, [target, check], obscode="ABC", filt="TG", chart="X42585ESI")

    rows = [ln.split(",") for ln in path.read_text().splitlines() if not ln.startswith("#")]
    assert len(rows) == 3  # the check curve is never written as an observation
    assert all(len(r) == 15 for r in rows)
    kname, kmag, chart = 9, 10, 13
    assert (rows[0][kname], rows[0][kmag], rows[0][chart]) == (
        "000-BJV-171",
        "10.6100",
        "X42585ESI",
    )
    # No usable check measurement on that frame → both check fields "na".
    assert (rows[1][kname], rows[1][kmag]) == ("na", "na")
    assert (rows[2][kname], rows[2][kmag]) == ("na", "na")


def test_aavso_export_without_check_or_chart_keeps_na(tmp_path) -> None:
    from argos.core.photometry.lightcurve import write_aavso

    target = LightCurve(name="NU Ori", role="target")
    target.append(LcPoint(jd_utc=2451545.0, mag=9.0, mag_err=0.02))
    path = tmp_path / "aavso.txt"
    write_aavso(path, [target], obscode="ABC", chart="a,b")  # a comma cannot be a field
    row = [ln for ln in path.read_text().splitlines() if not ln.startswith("#")][0].split(",")
    assert (row[9], row[10], row[13]) == ("na", "na", "na")


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


# --------------------------------------------------------------------------- #
# Regressions from the 0.4.1 documentation review
# --------------------------------------------------------------------------- #


def test_airmass_at_uses_the_target_altitude_not_the_mount() -> None:
    """A light-curve point must be timed and *placed* at the exposure midpoint.

    The mount's last reported altitude is sampled at an arbitrary instant; the
    target's airmass has to come from its own coordinates at the point's JD.
    """
    from argos.core.imaging.sky_geometry import altitude_at, compute_airmass
    from argos.core.photometry.airmass import airmass_at

    jd, ra_deg, dec_deg, lat, lon = 2460000.5, 300.0, 40.0, 37.4, -122.1
    alt = altitude_at(jd, ra_deg / 15.0, dec_deg, lat, lon)
    assert airmass_at(jd, ra_deg, dec_deg, lat, lon) == compute_airmass(alt)

    # Six hours later the same star is somewhere else entirely.
    later = airmass_at(jd + 0.25, ra_deg, dec_deg, lat, lon)
    assert later != airmass_at(jd, ra_deg, dec_deg, lat, lon)


def test_airmass_at_is_none_below_the_horizon() -> None:
    from argos.core.photometry.airmass import airmass_at

    # Deep southern target seen from the northern hemisphere: never rises.
    assert airmass_at(2460000.5, 100.0, -80.0, 50.0, 0.0) is None


def test_csv_carries_the_suspect_flag_and_both_ensemble_counts(tmp_path) -> None:
    """``suspect`` used to be measured, plotted and then dropped on export.

    ``comps_used`` counts the ensemble behind ``mag``; the flux-ratio path
    filters differently, so its own count is exported beside it rather than in
    its place.
    """
    lc = LightCurve(auid="000-BBB-002", name="XX Cyg")
    lc.append(
        LcPoint(
            jd_utc=2451545.0,
            mag=9.0,
            mag_err=0.02,
            comps_used=4,
            relative_comps_used=2,
            suspect=True,
        )
    )
    path = tmp_path / "photometry.csv"
    lc.to_csv(path)

    header, row = list(csv.reader(path.open()))
    assert row[header.index("suspect")] == "1"
    assert row[header.index("comps_used")] == "4"
    assert row[header.index("relative_comps_used")] == "2"

    point = LightCurve.from_csv(path).points[0]
    assert point.suspect is True
    assert (point.comps_used, point.relative_comps_used) == (4, 2)


def test_offline_aperture_is_wider_than_the_floor_without_a_fwhm() -> None:
    """Pins the behaviour the docstrings used to describe incorrectly.

    With no measured FWHM the aperture is ``2.5 * DEFAULT_FWHM`` = 7.5 green px,
    not the 4 px floor — a measurement that is not directly comparable with one
    taken from a frame that had a FWHM.
    """
    from argos.core.photometry.params import DEFAULT_FWHM, PhotometryParams

    params = PhotometryParams.from_config(lambda key, default=None: default)
    assert params.aperture_px(None) == params.aperture_fwhm_mult * DEFAULT_FWHM
    assert params.aperture_px(None) > params.aperture_min_px
    assert params.aperture_px(1.0) == params.aperture_min_px


def test_aavso_export_excludes_flagged_points(tmp_path) -> None:
    """S11: saturated (clipped) and suspect (cosmic ray, hot pixel) points
    went into the submission with nothing to mark them."""
    from argos.core.photometry.lightcurve import write_aavso

    target = LightCurve(name="SS Cyg", role="target")
    target.append(LcPoint(jd_utc=2461315.50, mag=12.0, mag_err=0.02))
    target.append(LcPoint(jd_utc=2461315.51, mag=9.1, mag_err=0.02, saturated=True))
    target.append(LcPoint(jd_utc=2461315.52, mag=12.1, mag_err=0.02, suspect=True))

    path = tmp_path / "aavso.txt"
    summary = write_aavso(path, [target], obscode="ABC")
    rows = [ln.split(",") for ln in path.read_text().splitlines() if not ln.startswith("#")]
    assert [row[1] for row in rows] == ["2461315.500000"]
    assert (summary.rows, summary.saturated_excluded, summary.suspect_excluded) == (1, 1, 1)

    # On explicit request they are kept, and marked in NOTES.
    summary = write_aavso(path, [target], obscode="ABC", include_flagged=True)
    rows = [ln.split(",") for ln in path.read_text().splitlines() if not ln.startswith("#")]
    assert summary.rows == 3
    assert [row[14] for row in rows] == ["na", "saturated", "suspect"]


def test_aavso_check_magnitude_ignores_flagged_check_points(tmp_path) -> None:
    from argos.core.photometry.lightcurve import write_aavso

    target = LightCurve(name="SS Cyg", role="target")
    check = LightCurve(auid="000-KKK-222", name="K1", role="check")
    for jd in (2461315.50, 2461315.51):
        target.append(LcPoint(jd_utc=jd, mag=12.0, mag_err=0.02))
    check.append(LcPoint(jd_utc=2461315.50, mag=11.5, mag_err=0.01, saturated=True))
    check.append(LcPoint(jd_utc=2461315.51, mag=11.6, mag_err=0.01))
    path = tmp_path / "aavso.txt"
    write_aavso(path, [target, check], obscode="ABC")
    rows = [ln.split(",") for ln in path.read_text().splitlines() if not ln.startswith("#")]
    assert [(row[9], row[10]) for row in rows] == [("na", "na"), ("000-KKK-222", "11.6000")]


def test_aavso_export_leaves_out_undated_points_s60(tmp_path) -> None:
    """S60: before S13 a batch re-run dated a frame without DATE-OBS at JD 0
    (``jd_utc=jd or 0.0``), and those CSVs still open in Analyze: Export AAVSO
    wrote their rows with DATE 0.000000, an observation in 4713 BC. An undated
    point (JD not finite, or before JD 2 400 000) is left out and counted."""
    from argos.core.photometry.lightcurve import write_aavso

    target = LightCurve(name="SS Cyg", role="target")
    target.append(LcPoint(jd_utc=2461315.50, mag=12.0, mag_err=0.02))
    target.append(LcPoint(jd_utc=0.0, mag=12.1, mag_err=0.02))
    target.append(LcPoint(jd_utc=float("nan"), mag=12.2, mag_err=0.02))
    target.append(LcPoint(jd_utc=0.0, mag=9.1, mag_err=0.02, saturated=True))
    csv_path = tmp_path / "target_SS_Cyg_SS_Cyg.csv"
    target.to_csv(csv_path)
    reloaded = LightCurve.from_csv(csv_path, name="SS Cyg")  # a pre-0.5.0 batch CSV, read back

    path = tmp_path / "aavso.txt"
    summary = write_aavso(path, [reloaded], obscode="TST")
    rows = [ln.split(",") for ln in path.read_text().splitlines() if not ln.startswith("#")]
    assert [row[1] for row in rows] == ["2461315.500000"]  # + 0.000000 and nan before
    assert (summary.rows, summary.undated_excluded, summary.saturated_excluded) == (1, 3, 0)
    from argos.core.photometry.lightcurve import MIN_AAVSO_JD

    assert MIN_AAVSO_JD == 2_400_000.0


def test_aavso_header_names_the_software_and_its_version_s64(tmp_path) -> None:
    """S64: every AAVSO report said ``#SOFTWARE=Argos``; the Extended File Format
    asks for the name and version of the software that wrote it. The default is
    the version stamped into the FITS headers (``argos.SOFTWARE_ID``)."""
    from argos import SOFTWARE_ID, __version__
    from argos.core.photometry.lightcurve import write_aavso

    target = LightCurve(name="SS Cyg", role="target")
    target.append(LcPoint(jd_utc=2461315.50, mag=12.0, mag_err=0.02))
    path = tmp_path / "aavso.txt"
    write_aavso(path, [target], obscode="TST")
    head = [ln for ln in path.read_text().splitlines() if ln.startswith("#SOFTWARE=")]
    assert head == [f"#SOFTWARE={SOFTWARE_ID}"] == [f"#SOFTWARE=Argos v{__version__}"]
    write_aavso(path, [target], obscode="TST", software="Other 1.0")
    assert "#SOFTWARE=Other 1.0" in path.read_text().splitlines()


_BJD_OFFLINE = """
import json, warnings
warnings.simplefilter("ignore")
import astropy.utils.data as data
calls = []
def blocked(*args, **kwargs):
    calls.append(str(args[0]) if args else "")
    raise OSError("network blocked")
data.download_file = blocked
from argos.core.photometry.airmass import bjd_tdb
print(json.dumps({"bjd": bjd_tdb(2461290.67, 316.0, 42.0, 48.85, 2.35, 50.0), "calls": calls}))
"""


def test_bjd_tdb_needs_no_network(tmp_path) -> None:
    """S37: astropy downloaded IERS tables on the first BJD of a session; offline
    it refused its bundled table (older than 30 days), so bjd_tdb returned None
    and no live point, CSV or AAVSO report had a BJD_TDB. Run in a fresh
    process (astropy caches its tables) with the network blocked."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    import pytest

    root = Path(__file__).resolve().parents[2]
    blocked = "http://127.0.0.1:9"
    env = dict(
        os.environ,
        PYTHONPATH=str(root),
        HOME=str(tmp_path),
        XDG_CACHE_HOME=str(tmp_path / "cache"),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        HTTP_PROXY=blocked,
        HTTPS_PROXY=blocked,
        http_proxy=blocked,
        https_proxy=blocked,
    )
    out = subprocess.run(
        [sys.executable, "-c", _BJD_OFFLINE], env=env, capture_output=True, text=True, timeout=120
    )
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["calls"] == []  # finals2000A.all and the leap seconds before the fix
    # The value an online astropy 7.2 gives for this instant, site and star.
    assert result["bjd"] == pytest.approx(2461290.6741261533, abs=2e-9)  # None before


def test_a_failed_csv_rewrite_leaves_the_previous_file(tmp_path, monkeypatch) -> None:
    """S38: to_csv truncated the live CSV and rewrote it in place after every
    point, so a reader saw a partial or empty file (1 778 of 2 097 reads in a
    concurrent test) and a crash mid-write left the night's curve truncated."""
    import pytest

    import argos.core.photometry.lightcurve as lcmod

    lc = LightCurve(auid="000-BBB-001", name="NU Ori")
    for i in range(3):
        lc.append(LcPoint(jd_utc=2451545.0 + i, mag=9.0, mag_err=0.02))
    path = tmp_path / "target.csv"
    lc.to_csv(path)
    before = path.read_bytes()
    lc.append(LcPoint(jd_utc=2451549.0, mag=9.1, mag_err=0.02))
    row = lcmod._row

    def fail_mid_file(p):
        if p.jd_utc == 2451546.0:
            raise OSError("disk full")
        return row(p)

    monkeypatch.setattr(lcmod, "_row", fail_mid_file)
    with pytest.raises(OSError):
        lc.to_csv(path)
    assert path.read_bytes() == before  # the header and 1 of 3 rows before the fix
    assert [p.name for p in tmp_path.iterdir()] == ["target.csv"]
    monkeypatch.setattr(lcmod, "_row", row)
    lc.to_csv(path)
    assert len(path.read_text().splitlines()) == 5


def test_frame_egain_is_the_frames_own_gain() -> None:
    """S41: a saved frame's e-/ADU: the gain table at its GAIN setting, then its
    EGAIN; None (the caller's live chain) when neither is usable."""
    from argos.core.photometry.params import frame_egain

    table = {"200": 0.29}
    assert frame_egain({"GAIN": 200, "EGAIN": 0.31}, table) == 0.29
    assert frame_egain({"GAIN": 200.0, "EGAIN": 0.31}, table) == 0.29
    assert frame_egain({"GAIN": 80, "EGAIN": 0.31}, table) == 0.31  # no table entry
    assert frame_egain({"GAIN": 200, "EGAIN": 0.31}) == 0.31  # no table
    assert frame_egain({"GAIN": 1.5, "EGAIN": 0.31}, {"1": 9.0}) == 0.31  # not a gain setting
    assert frame_egain({"GAIN": True, "EGAIN": 0.31}, {"1": 9.0}) == 0.31
    assert frame_egain({"GAIN": 200}, {"200": "bad"}) is None
    for bad in (0, -1.0, 150.0, float("nan"), "x", True, None):
        assert frame_egain({"EGAIN": bad}) is None, bad
    assert frame_egain({}) is None


def test_black_level_comes_from_the_profile_s72() -> None:
    """``photometry.noise_model = green_plane`` (S72) brings the S30 Pro's measured
    black level and the two-pixel plane to every aperture the params drive; a profile
    without one (S30, S50) subtracts nothing. Since S73 it is the default; ``pixel``
    keeps the 0.4.x model."""
    from argos.core.config import _DEFAULTS
    from argos.core.hardware import catalog
    from argos.core.photometry.params import PhotometryParams

    assert catalog.get("s30pro").black_level_adu == 1024.0
    assert _DEFAULTS["photometry"]["noise_model"] == "green_plane"
    defaults = PhotometryParams.from_config(lambda key, default=None: default, egain=0.8)
    assert (defaults.black_adu, defaults.plane_pixels) == (1024.0, 2)

    def model(name, profile=None):
        def cfg(key, default=None):
            if key == "photometry.noise_model":
                return name
            return profile if key == "hardware.profile" and profile else default

        return PhotometryParams.from_config(cfg, egain=0.8)

    pixel = model("pixel")
    assert (pixel.black_adu, pixel.plane_pixels, pixel.scint_cy, pixel.aperture_mm) == (
        0.0,
        1,
        0.0,
        0.0,
    )
    assert (model("green_plane").black_adu, model("green_plane").plane_pixels) == (1024.0, 2)
    assert (model("green_plane", "s50").black_adu, model("green_plane", "s50").plane_pixels) == (
        0.0,
        2,
    )
    g = _star(20, 20, peak=2000.0, sky=1100.0)
    with_black = measure_aperture(g, 20, 20, 6, 8, 12, egain=0.8, black_adu=1024.0)
    without = measure_aperture(g, 20, 20, 6, 8, 12, egain=0.8)
    assert with_black.flux_adu == without.flux_adu  # the magnitude is unchanged
    assert with_black.snr > without.snr  # 76 ADU of sky photons, not 1100


# --------------------------------------------------------------------------- #
# S73: the camera's measured e-/ADU; S72 on; S74 scintillation; S75 sky term   #
# --------------------------------------------------------------------------- #


class _Header(dict):
    """A FITS-header-like mapping with comments (``header.comments[key]``)."""

    def __init__(self, cards: dict, comments: dict | None = None) -> None:
        super().__init__(cards)
        self.comments = comments or {}


def _s30pro_header(gain=80, egain=0.8, comment="driver") -> _Header:
    return _Header(
        {"TELESCOP": "ZWO Seestar S30 Pro", "GAIN": gain, "EGAIN": egain},
        {"EGAIN": f"[e-/ADU] electron gain ({comment})"},
    )


def test_an_s30_pro_frame_at_gain_80_uses_the_measured_egain_s73() -> None:
    """The S30 Pro's frames at gain 80 say 0.8 (0.4.2, the driver) or 1.723 (0.4.1, the
    IMX585 reference) e-/ADU; their photon transfer gives 0.228. The re-run of such a
    frame (S41, S70) took the header's value: 0.8 and 1.723 before the fix."""
    from argos.core.photometry.params import frame_egain

    for written, comment in ((0.8, "driver"), (1.723, "IMX585 ref")):
        value = frame_egain(_s30pro_header(80, written, comment))
        assert value == pytest.approx(0.228)
        assert value.source == "S30 Pro PTC"  # the chain records where it came from
        assert value.read_noise_e == pytest.approx(2.6)
    # the observer's own table still comes first; an EGAIN that table wrote is kept
    assert frame_egain(_s30pro_header(80, 0.8), {"80": 0.25}) == 0.25
    kept = frame_egain(_s30pro_header(80, 0.31, "egain_table"))
    assert kept == 0.31 and "egain_table" in kept.source
    # another camera's frame keeps its header; so does one with no TELESCOP
    other = _Header({"TELESCOP": "Other scope", "GAIN": 80, "EGAIN": 0.8})
    assert frame_egain(other) == 0.8 and frame_egain(other).source == "header EGAIN"
    assert frame_egain({"GAIN": 80, "EGAIN": 0.8}) == 0.8


def test_other_gains_scale_by_the_sensors_0p1_db_steps_s73() -> None:
    """Gain 100 measures 0.183 e-/ADU where 0.228 x 10^(-20/200) gives 0.181; above
    251 (the IMX585's high-conversion-gain mode) nothing is measured: the frame's
    header, else the driver, else the reference, logged as unverified."""
    from argos.core.hardware import catalog
    from argos.core.hardware import egain as camera_egain
    from argos.core.photometry.params import frame_egain

    s30pro = catalog.get("s30pro")
    m, scaled = s30pro.measured_gain(100)
    assert scaled and m.e_per_adu == pytest.approx(0.228 * 10 ** (-0.1))
    assert m.e_per_adu == pytest.approx(0.183, abs=0.003)
    assert s30pro.measured_gain(0)[0].e_per_adu * 4095 * 16 == pytest.approx(38000, rel=0.02)
    assert s30pro.measured_gain(300) is None
    at_100 = frame_egain(_s30pro_header(100, 1.5, "IMX585 ref"))
    assert at_100 == pytest.approx(0.181, abs=0.001)
    # the read noise measured at gain 80 (the owner's decision, S73 amended: the
    # 1.5 e- Settings default gave the gain-65 light 0.79 of its measured sky sigma)
    assert at_100.source == "S30 Pro PTC scaled" and at_100.read_noise_e == pytest.approx(2.6)
    assert frame_egain(_s30pro_header(300, 0.4, "IMX585 ref")) == 0.4
    live = camera_egain.live(300, driver=0.42, profile=s30pro)
    assert live == 0.42 and live.source == "driver"
    assert camera_egain.live(80, driver=0.42, profile=s30pro) == pytest.approx(0.228)
    asked = []
    camera_egain.live(80, driver=lambda: asked.append(1), profile=s30pro)
    assert not asked  # the driver is not read when the profile has the value
    assert camera_egain.live(80, table={"80": 0.3}, profile=s30pro).source == "egain_table"
    # unvalidated profiles have no measurement: the driver, then their reference
    assert camera_egain.live(80, driver=0.5, profile=catalog.get("s50")).source == "driver"


def test_a_scaled_gain_is_logged_scaled_not_measured_except_where_checked_s73(caplog) -> None:
    """S73 amended (the owner's call on validation F2): every gain other than 80
    (measured) and 100 (the scaling checked by its own photon transfer) is logged once
    as "e-/ADU scaled, not measured"."""
    from argos.core.hardware import catalog
    from argos.core.hardware import egain as camera_egain

    s30pro = catalog.get("s30pro")
    camera_egain._warned.clear()
    with caplog.at_level("WARNING", logger="argos.core.hardware.egain"):
        for gain in (80, 100, 65, 65, 120):
            camera_egain.live(gain, profile=s30pro)

    lines = [r.getMessage() for r in caplog.records if "scaled, not measured" in r.getMessage()]
    assert [line.split()[3] for line in lines] == ["65", "120"]


def test_the_read_noise_follows_the_frames_egain_whatever_the_path_s73() -> None:
    """S73 amended (technical review): ``with_frame`` kept the base params' read noise
    when the frame's e-/ADU carried none, so one frame at a gain above 251 had 2.6 e- in
    a re-run with the Camera form at 80 and the Settings 1.5 e- with the form at 300.
    The frame's e-/ADU now brings its measured read noise, else the Settings one."""
    from argos.core.hardware import catalog
    from argos.core.hardware import egain as camera_egain
    from argos.core.photometry.params import PhotometryParams

    s30pro = catalog.get("s30pro")
    cfg = {"photometry.noise_model": "green_plane", "photometry.read_noise_e": 1.5}.get
    at_80 = camera_egain.live(80, profile=s30pro)
    at_100 = camera_egain.live(100, profile=s30pro)
    at_300 = camera_egain.live(300, driver=0.42, profile=s30pro)

    for base in (at_80, at_100, at_300):
        params = PhotometryParams.from_config(cfg, egain=base)
        assert params.with_frame(egain=at_300).read_noise_e == 1.5
        assert params.with_frame(egain=at_100).read_noise_e == pytest.approx(2.6)
    assert PhotometryParams.from_config(cfg, egain=at_300).read_noise_e == 1.5
    assert PhotometryParams.from_config(cfg, egain=at_100).read_noise_e == pytest.approx(2.6)


def test_the_model_sky_sigma_is_the_measured_one_s72_s73() -> None:
    """S72's test: the model's sky sigma within 10 % of the green-plane sigma measured
    in the annuli of the first light of RR Lyr 2026-09-25 (sky 1176 ADU: 20.5 ADU), XX
    Cyg 2026-09-07 (1368: 29.7) and 2026-08-29 (1400: 31.2), W7 science review. With
    the frames' EGAIN (0.8, 1.723, 1.723) it gave 9.8, 10.0 and 10.5 (-52 to -66 %)."""
    from argos.core.hardware import catalog
    from argos.core.photometry.aperture import sky_sigma_adu
    from argos.core.photometry.params import PhotometryParams, frame_egain

    for level, measured, written in (
        (1176.0, 20.5, 0.8),
        (1368.0, 29.7, 1.723),
        (1400.0, 31.2, 1.723),
    ):
        egain = frame_egain(_s30pro_header(80, written))
        params = PhotometryParams.from_config(lambda key, default=None: default, egain=egain)
        assert params.read_noise_e == pytest.approx(2.6)  # measured with the e-/ADU
        model = sky_sigma_adu(
            level,
            egain=params.egain,
            read_noise_e=params.read_noise_e,
            black_adu=params.black_adu,
            plane_pixels=params.plane_pixels,
        )
        assert model == pytest.approx(measured, rel=0.10), (level, model)
    assert catalog.get("s30pro").gain_measurements[0].e_per_adu_err == pytest.approx(0.005)


def test_scintillation_follows_young_and_osborn_s74() -> None:
    """Young (1967) with Osborn et al. (2015)'s C_Y = 1.5: 0.0155 relative through
    30 mm in 10 s at airmass 1, sea level; X^1.5, t^-1/2, D^-2/3, exp(-h / 8000 m)."""
    from argos.core.photometry.uncertainty import scintillation_sigma

    base = scintillation_sigma(30.0, 10.0, 1.0, 0.0)
    assert base == pytest.approx(math.sqrt(1e-5 * 2.25 * 0.03 ** (-4 / 3) / 10.0))
    assert base == pytest.approx(0.0155, abs=0.0002)
    assert scintillation_sigma(30.0, 40.0, 1.0) == pytest.approx(base / 2)
    assert scintillation_sigma(30.0, 10.0, 2.0) == pytest.approx(base * 2**1.5)
    assert scintillation_sigma(60.0, 10.0, 1.0) == pytest.approx(base * 2 ** (-2 / 3))
    assert scintillation_sigma(30.0, 10.0, 1.0, 8000.0) == pytest.approx(base / math.e)
    for missing in ((0.0, 10.0, 1.0), (30.0, None, 1.0), (30.0, 10.0, None), (30.0, 0.0, 1.0)):
        assert scintillation_sigma(*missing) == 0.0


def test_scintillation_is_in_each_stars_error_not_its_snr_s74() -> None:
    """A bright star's error was its photon error alone (a few mmag here, while the RR
    Lyr bright pairs scatter 2.2-2.4 times their formal errors): with S74 the frame's
    exposure and airmass add 1.0857 x 0.0155 mag in quadrature to every star, hence to
    the zero point's weights and the target's error; the SNR the gates read is kept.
    Before the fix the target's photon error, 0.0031 mag, was all of it."""
    from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar
    from argos.core.photometry.params import PhotometryParams, measure_frame

    class _WCS:  # every annulus on the frame (S81)
        def world_to_pixel_deg(self, ra_deg, dec_deg):
            return {1.0: (34.0, 34.0), 2.0: (14.0, 14.0), 3.0: (54.0, 54.0)}[ra_deg]

    yy, xx = np.mgrid[0:68, 0:68]
    green = np.full((68, 68), 1100.0, dtype=np.float32)
    for cx, cy in ((34, 34), (14, 14), (54, 54)):
        green += 20000.0 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 1.5**2))
    ts = TargetSet(object_name="X")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    for ra, auid in ((2.0, "C1"), (3.0, "C2")):
        ts.set_role(
            TargetStar(role=ROLE_COMPARISON, ra_deg=ra, dec_deg=1.0, auid=auid, mags={"V": 11.0})
        )
    params = PhotometryParams.from_config(lambda key, default=None: default, egain=0.228)
    assert (params.aperture_mm, params.scint_cy) == (30.0, 1.5)
    plain = {r.star.auid: r for r in measure_frame(green, _WCS(), ts, params, fwhm=2.0)}
    frame = params.with_frame(exposure_s=10.0, airmass=1.0, site_height_m=0.0)
    scint = {r.star.auid: r for r in measure_frame(green, _WCS(), ts, frame, fwhm=2.0)}
    photon = plain["T"].phot.inst_mag_err
    expected = math.hypot(photon, 1.0857 * 0.015536)
    assert scint["T"].phot.inst_mag_err == pytest.approx(expected, abs=1e-4)
    assert scint["T"].phot.snr == plain["T"].phot.snr  # the gates' SNR is unchanged
    assert scint["T"].diff.mag_err > 0.02 > plain["T"].diff.mag_err
    # each star at its own airmass (S78's per-star airmass): X^1.5
    per_star = measure_frame(
        green, _WCS(), ts, frame, fwhm=2.0, star_airmass=lambda s: 2.0 if s.auid == "T" else None
    )
    t = next(r for r in per_star if r.star.auid == "T")
    assert t.phot.inst_mag_err == pytest.approx(
        math.hypot(photon, 1.0857 * 0.015536 * 2**1.5), abs=1e-4
    )
    # the 0.4.x model has no such term
    pixel = PhotometryParams.from_config(
        lambda key, default=None: "pixel" if key == "photometry.noise_model" else default,
        egain=0.228,
    ).with_frame(exposure_s=10.0, airmass=1.0)
    assert pixel.scint_frac() == 0.0


def test_the_sky_estimates_own_error_is_counted_s75() -> None:
    """The sky under the aperture is the median of n_sky annulus pixels, whose error
    the CCD equation counts as n_ap (1 + n_ap / n_sky) with the median's pi/2. Without
    it the model's error of a faint star measured with a small annulus is 25 % below
    the scatter of its flux over 400 noise realisations (0.75 before the fix, 1.04 with it)."""
    from argos.core.photometry.aperture import sky_sigma_adu

    rng = np.random.default_rng(75)
    egain, black, level = 0.228, 1024.0, 1176.0
    sigma = sky_sigma_adu(level, egain=egain, read_noise_e=2.6, black_adu=black, plane_pixels=2)
    star = _star(20, 20, peak=60.0, sky=0.0, sigma=1.5).astype(np.float64)
    fluxes, errs = [], []
    for _ in range(400):
        g = (level + star + rng.normal(0.0, sigma, star.shape)).astype(np.float32)
        phot = measure_aperture(
            g, 20, 20, 5, 6, 9, egain=egain, read_noise_e=2.6, black_adu=black, plane_pixels=2
        )
        fluxes.append(phot.flux_adu)
        errs.append(phot.flux_adu / phot.snr if phot.snr > 0 else np.nan)
    measured = float(np.std(fluxes, ddof=1))
    model = float(np.nanmedian(errs))
    assert model == pytest.approx(measured, rel=0.08)
    # the 0.4.x model (one pixel, no black level) keeps its arithmetic: no such term
    g = (level + star).astype(np.float32)
    old = measure_aperture(g, 20, 20, 5, 6, 9, egain=egain, read_noise_e=2.6)
    n_pix = int(
        ((np.mgrid[0:40, 0:40][0] - 20) ** 2 + (np.mgrid[0:40, 0:40][1] - 20) ** 2 <= 25).sum()
    )
    var = old.flux_adu * egain + n_pix * (level * egain + 2.6**2)
    assert old.snr == pytest.approx(round(old.flux_adu * egain / math.sqrt(var), 2), abs=0.01)


def test_an_aperture_or_annulus_off_the_frame_is_not_measured_s81() -> None:
    """S81: the box was clipped at the frame's edge and a truncated aperture or annulus
    measured, the row written as a good point (RR Lyr 2026-09-25 200453Z: 000-BJW-667
    at y = -2.4 read 4.98 mag faint, at 1.5 px from the edge 0.10 mag; a truncated
    annulus alone 0.014-0.061 mag). Now nothing is measured unless every pixel within
    the annulus' outer radius lies on the frame."""
    yy, xx = np.mgrid[0:60, 0:80]
    green = np.full((60, 80), 1100.0, dtype=np.float32)

    def star(x, y):
        return green + 20000.0 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5**2))

    def phot(x, y):
        return measure_aperture(star(x, y), x, y, 5, 6, 9, egain=0.228)

    for x, y in ((40.0, -2.4), (40.0, 1.5), (40.0, 5.0), (3.0, 30.0), (75.0, 30.0), (40.0, 52.0)):
        assert phot(x, y) is None, (x, y)
    for x, y in ((40.0, 9.0), (9.0, 30.0), (70.0, 30.0), (40.0, 50.0)):
        assert phot(x, y) is not None, (x, y)
    assert measure_aperture(green, float("nan"), 30.0, 5, 6, 9) is None
