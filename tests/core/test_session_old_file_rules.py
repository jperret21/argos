"""Review applies the release notes' old-file rules to a run's curves (S66, S67).

S66 (owner's option b): the CSV airmass was computed for the Settings site, wrong on
some runs (X3) and off by up to 0.015 under the 5° tolerance; Review and its exports
take each Argos frame's header ``AIRMASS`` (the mount's) unless its pointing is frozen
(X1), and the site check only warns. S67: the points the flight recorder shows without
a detection (S35's rule: a zero-point outlier flags the frame, a target below SNR 3
its own points) are flagged suspect, left out of the AAVSO export, and the run's
``sigma_syst`` is recomputed without them. S71: faint comparisons are warned about.

The sites below are synthetic (no observer's site).
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.sky_geometry import compute_airmass, horizontal_at
from argos.core.photometry.airmass import airmass_at, julian_date
from argos.core.photometry.lightcurve import LcPoint, LightCurve, write_aavso
from argos.core.photometry.uncertainty import apply_systematic_floor, estimate_systematic_floor
from argos.core.session.diagnostics import SessionDiagnostics
from argos.core.session.review import load_session, load_session_curves

#: Where the mount was (synthetic), and a Settings site 60° of longitude away.
TRUE_SITE = (30.0, 100.0)
WRONG_SITE = (30.0, 40.0)
#: A Settings site 3° of longitude off: under X3's 5° tolerance, its airmass still off.
NEAR_SITE = (30.0, 97.0)
START = datetime(2026, 3, 1, 15, 0, 0, tzinfo=timezone.utc)
EXPTIME = 10.0
N = 14
BLANK = 7  # the frame measured on blank sky


def _meridian_ra_hours(when: datetime, lon: float) -> float:
    jd = julian_date(when)
    gmst = (18.697374558 + 24.06570982441908 * (jd - 2451545.0)) % 24.0
    return (gmst + lon / 15.0) % 24.0


def _session(
    tmp_path: Path,
    *,
    settings_site=WRONG_SITE,
    manual_floor: float | None = None,
    cadence_s: float = 60.0,
    frozen_after: int | None = None,
    faint_frame: int | None = None,
    second_target: bool = False,
    comp_snr: float = 90.0,
):
    """A 0.4.x-like run: N lights, per-star CSVs, a flight recorder with one blank frame.

    ``frozen_after``: the lights after that one keep its pointing keys and AIRMASS (X1,
    a lost mount's last poll); ``header_airmass`` stays the true one. ``faint_frame``:
    the target is recorded at SNR 2 there, its zero point normal (a faint target, not a
    lost field); ``second_target``: a bright second target; ``comp_snr``: the
    comparison's recorded SNR."""
    root = tmp_path / "20260301T150000Z_Var_X"
    lights = root / "lights"
    lights.mkdir(parents=True)
    (root / "photometry").mkdir()
    ra_h = _meridian_ra_hours(START, TRUE_SITE[1])
    dec = 40.0
    target = TargetStar("target", ra_h * 15.0, dec, auid="000-AAA-000", name="Var X")
    comp = TargetStar("comparison", ra_h * 15.0 + 0.1, dec, auid="000-AAA-111", mags={"V": 10.0})
    second = TargetStar("target", ra_h * 15.0 - 0.1, dec, auid="000-AAA-222", name="Var Y")
    stars = [target, comp] + ([second] if second_target else [])
    TargetSet(object_name="Var X", stars=stars).save(root / "targets.json")
    frames = []
    curves = {"t": LightCurve(auid=target.auid, role="target"), "c": LightCurve(role="comparison")}
    if second_target:
        curves["t2"] = LightCurve(auid=second.auid, role="target")
    header_airmass = []
    diag = SessionDiagnostics(root / "diagnostics" / "Var_X_live_diagnostics.jsonl")
    polled = None
    for i in range(N):
        start = START + timedelta(seconds=cadence_s * i)
        name = f"Var_X_{i + 1:05d}.fit"
        jd_start = julian_date(start)
        alt, az = horizontal_at(jd_start, ra_h, dec, *TRUE_SITE)
        am = round(compute_airmass(alt), 4)
        header_airmass.append(am)
        if frozen_after is None or i <= frozen_after:
            polled = (round(alt, 4), round(az, 4), am)
        hdu = fits.PrimaryHDU(np.zeros((4, 4), dtype=np.uint16))
        h = hdu.header
        h["DATE-OBS"] = start.strftime("%Y-%m-%dT%H:%M:%S.%f")
        h["EXPTIME"] = EXPTIME
        h["RA"], h["DEC"] = ra_h, dec
        h["ALTITUDE"], h["AZIMUTH"], h["AIRMASS"] = polled
        h["SITELAT"], h["SITELONG"] = settings_site
        h["SOFTWARE"] = "Argos v0.4.2"
        hdu.writeto(lights / name)
        frames.append(
            {
                "filename": name,
                "image_type": "Light Frame",
                "filter_name": "IR",
                "exposure_s": EXPTIME,
                "gain": 80,
                "timestamp": start.isoformat(),
            }
        )
        jd = julian_date(start + timedelta(seconds=EXPTIME / 2))
        blank = i == BLANK
        mag = 7.5 + 0.01 * i + (1.4 if blank else 0.003 * (-1) ** i)
        csv_airmass = airmass_at(jd, target.ra_deg, target.dec_deg, *settings_site)
        rows = [("t", mag, 0.7 if blank else 0.008), ("c", 10.0, 0.01)]
        if second_target:
            rows.append(("t2", 8.0 + 0.002 * (-1) ** i, 0.006))
        for key, star_mag, err in rows:
            curves[key].append(
                LcPoint(
                    jd_utc=jd, mag=star_mag, mag_err=err, formal_mag_err=err, airmass=csv_airmass
                )
            )
        snr = 1.6 if blank else 2.0 if i == faint_frame else 140.0
        diag.record("star", frame=i, auid=target.auid, role="target", snr=snr)
        if second_target:
            diag.record(
                "star", frame=i, auid=second.auid, role="target", snr=2.0 if blank else 160.0
            )
        diag.record(
            "star", frame=i, auid=comp.auid, role="comparison", snr=2.0 if blank else comp_snr
        )
        diag.record("frame", frame=i, jd_utc=jd, airmass=csv_airmass)
        diag.record("ensemble", frame=i, target=target.auid, zp=21.0 + (1.5 if blank else 0.0))
        if second_target:
            diag.record("ensemble", frame=i, target=second.auid, zp=21.0 + (1.5 if blank else 0.0))
    diag.close()
    for lc in curves.values():  # the live path's floor: every point (manual when set)
        floor = estimate_systematic_floor(
            [(p.jd_utc, p.mag, p.formal_mag_err) for p in lc.points], manual_floor=manual_floor
        )
        for p in lc.points:
            p.mag_err = apply_systematic_floor(p.formal_mag_err, floor)
            p.sigma_syst = floor.sigma_systematic
    curves["t"].to_csv(root / "photometry" / "target_Var_X_000-AAA-000.csv")
    curves["c"].to_csv(root / "photometry" / "comparison_Var_X_000-AAA-111.csv")
    if second_target:
        curves["t2"].to_csv(root / "photometry" / "target_Var_X_000-AAA-222.csv")
    (root / "session.json").write_text(json.dumps({"object": "Var X", "frames": frames}))
    return root, header_airmass, curves


def _loaded(root):
    review = load_session(root, read_temperature=False)
    curves = load_session_curves(review)
    target = next(lc for lc in curves.values() if lc.auid == "000-AAA-000")
    comp = next(lc for lc in curves.values() if lc.role == "comparison")
    return review, target, comp


def _site_warned(review) -> bool:
    return any("not where the telescope was" in line for line in review.warnings)


def test_review_takes_the_header_airmass_when_the_site_was_wrong_s66(tmp_path) -> None:
    """S66: the CSV airmass of a wrong Settings site reached Review and AMASS."""
    root, header_airmass, written = _session(tmp_path)
    assert abs(written["t"].points[0].airmass - header_airmass[0]) > 0.3  # the wrong site's

    review, target, comp = _loaded(root)

    assert [p.airmass for p in target.points] == header_airmass
    assert [p.airmass for p in comp.points] == header_airmass
    assert _site_warned(review)
    out = tmp_path / "aavso.txt"
    write_aavso(out, [target], obscode="TST01")
    first = out.read_text().splitlines()[7].split(",")
    assert first[11] == f"{header_airmass[0]:.3f}"


def test_review_takes_the_header_airmass_when_the_site_was_right_too_s66(tmp_path) -> None:
    """S66 as decided (option b): the header AIRMASS whenever a frame has one, whatever
    the site check says. Under the 5° tolerance the Settings site still erred (XX Cyg
    2026-08-29 re-run: 0.013-0.015 too high; the header within 0.0004 of astropy)."""
    root, header_airmass, written = _session(tmp_path, settings_site=NEAR_SITE)
    assert [p.airmass for p in written["t"].points] != header_airmass  # the near site's

    review, target, _comp = _loaded(root)

    assert [p.airmass for p in target.points] == header_airmass
    assert not _site_warned(review)


def test_a_point_without_a_frame_keeps_its_computed_airmass_s66(tmp_path) -> None:
    root, _header_airmass, written = _session(tmp_path)
    path = root / "photometry" / "target_Var_X_000-AAA-000.csv"
    late = written["t"].points[-1]
    lc = written["t"]
    lc.append(LcPoint(jd_utc=late.jd_utc + 30.0 / 86400.0, mag=7.6, mag_err=0.02, airmass=1.9))
    lc.to_csv(path)

    review, target, _comp = _loaded(root)

    assert target.points[-1].airmass == 1.9
    assert any("1 point(s) without one" in line for line in review.warnings)
    out = tmp_path / "aavso.txt"
    write_aavso(out, [target], obscode="TST01")
    assert out.read_text().splitlines()[-1].split(",")[11] == "1.900"


def test_a_frozen_pointing_is_not_a_wrong_site_s66(tmp_path) -> None:
    """S66 with X1 (science and technical reviews): a 0.3.0-0.4.x frame saved after the
    mount was lost keeps its last poll's RA, DEC, ALTITUDE, AZIMUTH and AIRMASS; from
    half an hour after the freeze its direction is over 5° from the one computed for the
    right site. Here 13 of 14 lights 5 min apart are frozen: the median said "wrong
    site" and every point took the stale AIRMASS (1.0151 where the truth reaches 1.0417).
    A frozen light is not checked, and its stale AIRMASS is not used: its points keep
    the CSV airmass of the right site."""
    root, header_airmass, written = _session(
        tmp_path, settings_site=TRUE_SITE, cadence_s=300.0, frozen_after=0
    )

    review, target, _comp = _loaded(root)

    assert target.points[0].airmass == header_airmass[0]  # polled before the freeze
    assert [p.airmass for p in target.points[1:]] == [p.airmass for p in written["t"].points[1:]]
    assert abs(target.points[-1].airmass - header_airmass[0]) > 0.02
    assert not _site_warned(review)


def test_a_frozen_light_keeps_its_computed_airmass_on_a_wrong_site_s66(tmp_path) -> None:
    """S66 with X1: on a wrong-site run, a frozen light's AIRMASS is the last poll's, not
    its own: its points keep the CSV airmass (computed for the Settings site, as the
    warning says); the lights before the freeze take theirs."""
    root, header_airmass, written = _session(tmp_path, cadence_s=300.0, frozen_after=2)

    review, target, _comp = _loaded(root)

    assert [p.airmass for p in target.points[:3]] == header_airmass[:3]
    assert [p.airmass for p in target.points[3:]] == [p.airmass for p in written["t"].points[3:]]
    assert any("X1" in line and "22 point(s) without one" in line for line in review.warnings)


def test_review_flags_every_point_of_a_frame_without_a_detection_s67(tmp_path) -> None:
    """S67: the blank-sky frame's points were unflagged and raised every row's sigma_syst."""
    root, _header_airmass, written = _session(tmp_path, settings_site=TRUE_SITE)
    before = written["t"].points[0].sigma_syst

    review, target, comp = _loaded(root)

    assert [i for i, p in enumerate(target.points) if p.suspect] == [BLANK]
    assert [i for i, p in enumerate(comp.points) if p.suspect] == [BLANK]
    assert target.points[BLANK].no_detection and comp.points[BLANK].no_detection
    expected = estimate_systematic_floor(
        [(p.jd_utc, p.mag, p.formal_mag_err) for i, p in enumerate(target.points) if i != BLANK]
    ).sigma_systematic
    assert expected < before
    assert {p.sigma_syst for p in target.points} == {expected}
    for p in target.points:
        assert p.mag_err == pytest.approx(math.hypot(p.formal_mag_err, expected), abs=1e-15)
    assert any("S67" in line for line in review.warnings)


def test_a_faint_target_flags_its_own_points_only_s67(tmp_path) -> None:
    """S67 as decided (option b): the SNR rule is per target. A faint variable at minimum
    (SNR 2 on frame 3, its zero point normal) no longer takes out a bright second
    target's point or the comparisons'; the zero-point outlier still flags the frame."""
    root, _header_airmass, _written = _session(
        tmp_path, settings_site=TRUE_SITE, faint_frame=3, second_target=True
    )

    review = load_session(root, read_temperature=False)
    curves = {lc.auid: lc for lc in load_session_curves(review).values()}

    def flagged(auid):
        return [i for i, p in enumerate(curves[auid].points) if p.no_detection]

    assert flagged("000-AAA-000") == [3, BLANK]
    assert flagged("000-AAA-222") == [BLANK]
    assert flagged("000-AAA-111") == [BLANK]


def test_review_warns_about_faint_comparisons_s71(tmp_path) -> None:
    """S71, Qt first (technical review): Review warns when the comparisons' median SNR in
    the flight recorder is below 10 (XX Cyg 2026-08-29: 1.7), as the server does."""
    faint, _h, _w = _session(tmp_path / "faint", settings_site=TRUE_SITE, comp_snr=4.0)
    bright, _h, _w = _session(tmp_path / "bright", settings_site=TRUE_SITE)

    assert any("S71" in line and "4.0" in line for line in _loaded(faint)[0].warnings)
    assert not any("S71" in line for line in _loaded(bright)[0].warnings)


def test_aavso_export_leaves_out_and_counts_no_detection_points_s67(tmp_path) -> None:
    root, _header_airmass, _written = _session(tmp_path, settings_site=TRUE_SITE)
    _review, target, _comp = _loaded(root)

    summary = write_aavso(tmp_path / "aavso.txt", [target], obscode="TST01")

    assert summary.rows == N - 1
    assert summary.no_detection_excluded == 1 and summary.suspect_excluded == 0


def test_a_manual_floor_is_kept_when_no_detection_points_are_flagged_s67(tmp_path) -> None:
    root, _header_airmass, _written = _session(tmp_path, settings_site=TRUE_SITE, manual_floor=0.02)

    _review, target, _comp = _loaded(root)

    assert target.points[BLANK].suspect
    assert {p.sigma_syst for p in target.points} == {0.02}


def test_open_curve_csv_applies_the_rules_to_a_run_s_own_csv_only(tmp_path) -> None:
    """Analyze's Open curve CSV in a session folder does the same (S66, S67)."""
    from argos.core.photometry.lightcurve import read_curves_csv
    from argos.core.session.review import apply_old_file_rules_to_file, session_of_curve_file

    root, header_airmass, _written = _session(tmp_path)
    path = root / "photometry" / "target_Var_X_000-AAA-000.csv"
    curves = read_curves_csv(path)

    rules = apply_old_file_rules_to_file(path, curves)

    lc = next(iter(curves.values()))
    assert rules.site_mismatch and rules.no_detection_points == 1
    assert [p.airmass for p in lc.points] == header_airmass
    assert lc.points[BLANK].suspect
    rerun = root / "photometry_rerun_20260302T000000Z" / "target_Var_X_000-AAA-000.csv"
    assert session_of_curve_file(rerun) is None  # a re-run has its own flags and site check
    assert session_of_curve_file(tmp_path / "targets" / "Var_X_000-AAA-000.csv") is None


@pytest.mark.skipif(
    not os.environ.get("ARGOS_S66_SESSION"),
    reason="set ARGOS_S66_SESSION to a copy of the RR Lyr 2026-09-25 session",
)
def test_real_rr_lyr_session_gives_the_header_airmass_and_drops_two_frames(tmp_path) -> None:
    """The owner's RR Lyr 2026-09-25 run: AMASS 1.033 on row 1 (1.033-1.364 by astropy at
    the site fitted to the mount; 4.088 before), and frames _00053 and _00176 left out."""
    root = Path(os.environ["ARGOS_S66_SESSION"])

    _review, target, _comp = _loaded(root)

    out = tmp_path / "aavso.txt"
    summary = write_aavso(out, [target], obscode="TST01")
    rows = [line.split(",") for line in out.read_text().splitlines() if not line.startswith("#")]
    assert rows[0][11] == "1.033"
    assert 1.033 <= min(float(r[11]) for r in rows) and max(float(r[11]) for r in rows) <= 1.365
    assert summary.no_detection_excluded == 2 and summary.rows == 193
    assert target.points[0].sigma_syst == pytest.approx(0.01497, abs=5e-5)
