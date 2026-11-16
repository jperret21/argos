"""PhotometryBatchWorker — offline re-run over a folder of synthetic FITS (WS7).

Guards the batch path's contract: it uses the shared measurement core (so comps
get their catalog mags), emits progress, honours cancel, and writes the
canonical 9-column CSVs that Analyze reloads. Runs the QThread synchronously via
``run()`` to keep the test deterministic (no event loop needed).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import replace

import numpy as np
import pytest
from astropy.io import fits

from argos.core.catalog.targets import (
    ROLE_CHECK,
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    TargetStar,
)
from argos.core.photometry.lightcurve import LightCurve
from argos.core.photometry.params import PhotometryParams
from argos.workers.photometry_batch_worker import (
    BatchRequest,
    BatchResult,
    PhotometryBatchWorker,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


#: S81: a star is measured only when its 12 px sky annulus lies on the frame. The small
#: scenes keep their positions (10-50 px on a 60 px plane): their fake WCS and painted
#: frame both add this margin.
_MARGIN = 4


class _FakeWCS:
    """Maps (ra_deg, dec_deg) → a preset green-px (x, y), plus ``margin``."""

    def __init__(self, mapping, margin=0):
        self._m = mapping
        self._margin = margin

    def world_to_pixel_deg(self, ra_deg, dec_deg):
        x, y = self._m[(ra_deg, dec_deg)]
        return x + self._margin, y + self._margin


def _raw_with_green_stars(
    green_positions_peaks, sky=200.0, sigma=1.5, green_shape=(60, 60), margin=0
):
    """Build a raw GRBG frame whose green plane has stars at the given px.

    ``green_plane`` averages G1=raw[0::2,0::2] and G2=raw[1::2,1::2] → a green px
    (gx, gy) maps to raw (2*gx, 2*gy). We paint both greens with the same PSF. The
    plane is ``margin`` larger on each side, every star shifted by it (S81).
    """
    gh, gw = (n + 2 * margin for n in green_shape)
    raw = np.full((gh * 2, gw * 2), sky, dtype=np.float32)
    yy, xx = np.mgrid[0:gh, 0:gw]
    plane = np.zeros((gh, gw), dtype=np.float32)
    for (cx, cy), peak in green_positions_peaks:
        cx, cy = cx + margin, cy + margin
        plane += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2))
    raw[0::2, 0::2] += plane  # G1
    raw[1::2, 1::2] += plane  # G2
    return raw


def _write_fits(path, raw, date_obs):
    hdu = fits.PrimaryHDU(np.clip(raw, 0, 65535).astype(np.uint16))
    hdu.header["DATE-OBS"] = date_obs
    hdu.header["OBJECT"] = "TST Tau"
    hdu.writeto(path)


@pytest.fixture
def _scene(tmp_path):
    wcs = _FakeWCS(
        {
            (1.0, 1.0): (30.0, 30.0),  # target
            (2.0, 2.0): (10.0, 10.0),  # comp 1
            (3.0, 3.0): (50.0, 50.0),  # comp 2
        },
        margin=_MARGIN,
    )
    ts = TargetSet(object_name="TST Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1", mags={"V": 11.0})
    )
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=3.0, dec_deg=3.0, auid="C2", mags={"V": 11.0})
    )
    stars = [((30.0, 30.0), 20000.0), ((10.0, 10.0), 8000.0), ((50.0, 50.0), 8000.0)]
    paths = []
    for i in range(3):
        raw = _raw_with_green_stars(stars, margin=_MARGIN)
        p = tmp_path / f"sub_{i:03d}.fits"
        _write_fits(p, raw, f"2026-07-05T0{i}:00:00")
        paths.append(p)
    out_dir = tmp_path / "targets"
    params = PhotometryParams.from_config(lambda k, d: d)  # all config defaults
    req = BatchRequest(
        fits_paths=paths,
        wcs=wcs,
        target_set=ts,
        params=params,
        out_dir=out_dir,
        object_name="TST Tau",
    )
    return req, out_dir


def test_batch_measures_and_writes_uncertainty_aware_csv(_scene) -> None:
    req, out_dir = _scene
    seen = []
    worker = PhotometryBatchWorker(req)
    worker.point.connect(lambda pt: seen.append(pt))
    result_box = []
    worker.finished_batch.connect(result_box.append)
    worker.run()  # synchronous — no event loop

    assert result_box and isinstance(result_box[0], BatchResult)
    result = result_box[0]
    assert result.ok
    assert result.frames_done == 3
    # One target curve + one leave-one-out vetting curve per comparison.
    assert len(result.curves) == 3
    assert {lc.role for lc in result.curves.values()} == {"target", "comparison"}
    curve = result.curves["T@clear"]
    assert curve.role == "target" and len(curve.points) == 3
    assert len(seen) == 9  # a point signal per star per frame
    # The target is brighter than the V=11 comps → calibrated mag < 11.
    assert curve.points[0].mag < 11.0
    # Each comp vetted against the other one recovers its own catalog mag.
    comp_curve = result.curves["C1@clear"]
    assert comp_curve.role == "comparison"
    assert abs(comp_curve.points[0].mag - 11.0) < 0.1

    # Canonical uncertainty-aware CSVs written (target + comps) and reloadable.
    csvs = list(out_dir.glob("*.csv"))
    assert len(csvs) == 3
    header = csvs[0].read_text().splitlines()[0]
    assert header == (
        "jd_utc,bjd_tdb,mag,mag_err,formal_mag_err,sigma_syst,airmass,fwhm,sky_adu,"
        "comps_used,relative_flux,relative_flux_err,relative_comps_used,"
        "saturated,suspect"
    )
    reloaded = LightCurve.from_csv(csvs[0])
    assert len(reloaded.points) == 3


def test_batch_cancel_stops_early(_scene) -> None:
    req, _ = _scene
    worker = PhotometryBatchWorker(req)
    worker.cancel()  # cancel before running → no frames processed
    result_box = []
    worker.finished_batch.connect(result_box.append)
    worker.run()
    assert result_box[0].ok
    assert result_box[0].frames_done == 0
    assert result_box[0].curves == {}
    assert result_box[0].cancelled is True


def test_batch_reports_progress(_scene) -> None:
    req, _ = _scene
    worker = PhotometryBatchWorker(req)
    steps = []
    worker.progress.connect(lambda done, total: steps.append((done, total)))
    worker.run()
    assert steps == [(1, 3), (2, 3), (3, 3)]


# ── Field rotation (alt-az) — apertures must follow the rotating field ──────


def _rotate(x, y, cx, cy, deg):
    import math

    a = math.radians(deg)
    dx, dy = x - cx, y - cy
    return (
        cx + math.cos(a) * dx - math.sin(a) * dy,
        cy + math.sin(a) * dx + math.cos(a) * dy,
    )


def _rotating_scene(tmp_path, total_deg=10.0, n_frames=10, track=True):
    """Frames whose star field rotates around the green-frame centre.

    The reference WCS is exact for frame 0 only — the alt-az session case.
    """
    import dataclasses

    ref = {
        (1.0, 1.0): (30.0, 30.0),  # target
        (2.0, 2.0): (90.0, 35.0),  # comp 1
        (3.0, 3.0): (60.0, 95.0),  # comp 2
    }
    center = (60.0, 60.0)
    ts = TargetSet(object_name="ROT Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1", mags={"V": 11.0})
    )
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=3.0, dec_deg=3.0, auid="C2", mags={"V": 11.0})
    )
    paths = []
    for i in range(n_frames):
        ang = total_deg * i / (n_frames - 1)
        stars = [
            (_rotate(30.0, 30.0, *center, ang), 20000.0),
            (_rotate(90.0, 35.0, *center, ang), 8000.0),
            (_rotate(60.0, 95.0, *center, ang), 8000.0),
        ]
        raw = _raw_with_green_stars(stars, green_shape=(120, 120))
        p = tmp_path / f"rot_{i:03d}.fits"
        _write_fits(p, raw, f"2026-07-05T00:{i:02d}:00")
        paths.append(p)
    params = PhotometryParams.from_config(lambda k, d: d)
    if not track:
        params = dataclasses.replace(params, track_apertures=False)
    return BatchRequest(
        fits_paths=paths,
        wcs=_FakeWCS(ref),
        target_set=ts,
        params=params,
        out_dir=tmp_path / "targets",
        object_name="ROT Tau",
    )


def test_batch_tracks_field_rotation(tmp_path) -> None:
    req = _rotating_scene(tmp_path, total_deg=10.0, n_frames=10, track=True)
    result_box = []
    worker = PhotometryBatchWorker(req)
    worker.finished_batch.connect(result_box.append)
    worker.run()

    result = result_box[0]
    assert result.ok and result.frames_done == 10
    # The tracker measured the session's rotation…
    assert abs(result.rotation_deg - 10.0) < 0.5
    # …and the target stayed in its aperture on every frame, at a steady mag.
    curve = next(iter(result.curves.values()))
    assert len(curve.points) == 10
    mags = [p.mag for p in curve.points]
    assert max(mags) - min(mags) < 0.05


def test_batch_without_tracking_corrupts_the_rotating_curve(tmp_path) -> None:
    """Control: the same rotating scene, tracking off — the reference WCS
    alone cannot follow the field, so the apertures slide off the stars and
    the light curve acquired a spurious fade (~0.4 mag here, a plausible
    'eclipse'). This is the artefact the tracker exists to remove. Since S69
    (b) a comparison more than 1 px from its aperture centre leaves the
    ensemble, so the fade never reaches the curve: the frames whose comparisons
    are all off their apertures give no point."""
    req = _rotating_scene(tmp_path, total_deg=10.0, n_frames=10, track=False)
    result_box = []
    worker = PhotometryBatchWorker(req)
    worker.finished_batch.connect(result_box.append)
    worker.run()

    result = result_box[0]
    assert result.ok and result.rotation_deg == 0.0  # no tracker ran
    assert result.stars_off_centre >= 2 * 7  # both comparisons, from frame 2 or 3 on
    curve = next(iter(result.curves.values()))
    mags = [p.mag for p in curve.points]
    assert len(mags) <= 3 and max(mags) - min(mags) < 0.05


def test_batch_writes_diagnostics_jsonl(tmp_path) -> None:
    """P11: the flight recorder captures every comp's raw behaviour per frame,
    the ensemble zero-point and the tracker state, in parseable JSONL."""
    import json

    req = _rotating_scene(tmp_path, total_deg=10.0, n_frames=10, track=True)
    worker = PhotometryBatchWorker(req)
    result_box = []
    worker.finished_batch.connect(result_box.append)
    worker.run()

    diag_files = list((tmp_path / "targets").glob("*_diagnostics.jsonl"))
    assert len(diag_files) == 1
    docs = [json.loads(line) for line in diag_files[0].read_text().splitlines()]

    by_kind = {}
    for d in docs:
        by_kind.setdefault(d["kind"], []).append(d)

    # One star record per star (1 target + 2 comps) per frame.
    assert len(by_kind["star"]) == 3 * 10
    comp_records = [d for d in by_kind["star"] if d["role"] == "comparison"]
    assert len(comp_records) == 2 * 10
    assert all("inst_mag" in d and "x" in d and "y" in d for d in comp_records)

    # Ensemble health per calibrated star per frame — the target against the
    # full ensemble (2 comps) + each comp leave-one-out (1 comp).
    assert len(by_kind["ensemble"]) == 3 * 10
    target_records = [d for d in by_kind["ensemble"] if d["comps_used"] == 2]
    assert len(target_records) == 10
    assert len(by_kind["tracking"]) == 10
    final_rot = by_kind["tracking"][-1]["rotation_deg"]
    assert abs(final_rot - result_box[0].rotation_deg) < 1.5  # last-frame vs final
    assert len(by_kind["frame"]) == 10
    whats = [d["what"] for d in by_kind["event"]]
    assert whats[0] == "batch_start" and whats[-1] == "batch_end"


def test_batch_diagnostics_can_be_disabled(tmp_path) -> None:
    import dataclasses

    req = _rotating_scene(tmp_path, total_deg=2.0, n_frames=3, track=True)
    req = dataclasses.replace(req, diagnostics=False)
    worker = PhotometryBatchWorker(req)
    worker.run()
    assert not list((tmp_path / "targets").glob("*_diagnostics.jsonl"))


def test_batch_exports_the_check_star_curve(tmp_path) -> None:
    """P2: the K star gets its own curve + CSV and a check_rms summary event."""
    import dataclasses
    import json

    from argos.core.catalog.targets import ROLE_CHECK

    req = _rotating_scene(tmp_path, total_deg=2.0, n_frames=5, track=True)
    ts = req.target_set
    # Promote comp C2 (at green px 60,95) to check star.
    ts.set_role(TargetStar(role=ROLE_CHECK, ra_deg=3.0, dec_deg=3.0, auid="K1", mags={"V": 11.0}))
    req = dataclasses.replace(req, target_set=ts)

    worker = PhotometryBatchWorker(req)
    result_box = []
    worker.finished_batch.connect(result_box.append)
    worker.run()

    result = result_box[0]
    assert result.ok
    assert "K1@clear" in result.curves  # the K curve exists (frames without FILTER: S49)…
    k_curve = result.curves["K1@clear"]
    assert len(k_curve.points) == 5
    k_mags = [p.mag for p in k_curve.points]
    assert max(k_mags) - min(k_mags) < 0.05  # …and the constant K star is flat

    csv_names = [p.name for p in (tmp_path / "targets").glob("*.csv")]
    assert any("K1" in n for n in csv_names)

    diag_file = next((tmp_path / "targets").glob("*_diagnostics.jsonl"))
    events = [
        json.loads(line)
        for line in diag_file.read_text().splitlines()
        if json.loads(line)["kind"] == "event"
    ]
    rms_events = [e for e in events if e["what"] == "check_rms"]
    assert len(rms_events) == 1 and rms_events[0]["star"] == "K1"
    assert rms_events[0]["rms_mag"] < 0.05


def test_batch_jd_is_exposure_midpoint(tmp_path) -> None:
    """P5: DATE-OBS is exposure start; EXPTIME/2 must be added to the JD."""
    raw = _raw_with_green_stars([((30.0, 30.0), 20000.0)])
    p = tmp_path / "sub.fits"
    hdu = fits.PrimaryHDU(np.clip(raw, 0, 65535).astype(np.uint16))
    hdu.header["DATE-OBS"] = "2026-07-05T00:00:00"
    hdu.header["EXPTIME"] = 30.0
    hdu.writeto(p)

    _, jd, _ = PhotometryBatchWorker._read_frame(p)
    from argos.core.photometry.airmass import julian_date
    from datetime import datetime, timezone

    start_jd = julian_date(datetime(2026, 7, 5, 0, 0, 0, tzinfo=timezone.utc))
    assert abs(jd - (start_jd + 15.0 / 86400.0)) < 1e-9


def test_batch_points_carry_airmass_when_site_known(tmp_path) -> None:
    """P4: with a site configured, every batch point gets a Pickering airmass."""

    # Circumpolar target/comps (dec≈+89) — always above the horizon from 46°N.
    ref = {
        (10.0, 89.0): (30.0, 30.0),
        (20.0, 89.1): (10.0, 10.0),
        (30.0, 89.2): (50.0, 50.0),
    }
    ts = TargetSet(object_name="POLE")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=10.0, dec_deg=89.0, auid="T"))
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=20.0, dec_deg=89.1, auid="C1", mags={"V": 11.0})
    )
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=30.0, dec_deg=89.2, auid="C2", mags={"V": 11.0})
    )
    stars = [((30.0, 30.0), 20000.0), ((10.0, 10.0), 8000.0), ((50.0, 50.0), 8000.0)]
    paths = []
    for i in range(2):
        p = tmp_path / f"sub_{i}.fits"
        _write_fits(p, _raw_with_green_stars(stars, margin=_MARGIN), f"2026-07-05T0{i}:00:00")
        paths.append(p)
    req = BatchRequest(
        fits_paths=paths,
        wcs=_FakeWCS(ref, margin=_MARGIN),
        target_set=ts,
        params=PhotometryParams.from_config(lambda k, d: d),
        out_dir=tmp_path / "targets",
        object_name="POLE",
        site=(46.0, 6.0, 400.0),
    )
    result_box = []
    worker = PhotometryBatchWorker(req)
    worker.finished_batch.connect(result_box.append)
    worker.run()

    curve = next(iter(result_box[0].curves.values()))
    for pt in curve.points:
        assert pt.airmass is not None and 1.0 <= pt.airmass < 3.0
        assert pt.bjd_tdb is not None


def test_batch_aperture_sized_from_measured_fwhm(tmp_path) -> None:
    """P7: the series aperture comes from the first frame's measured FWHM
    (σ=1.5 px Gaussians → FWHM ≈ 3.5 px → r_ap ≈ 8.8 px), not the 4 px floor,
    and stays fixed for the whole run."""
    import json

    req = _rotating_scene(tmp_path, total_deg=2.0, n_frames=4, track=True)
    worker = PhotometryBatchWorker(req)
    worker.run()

    diag_file = next((tmp_path / "targets").glob("*_diagnostics.jsonl"))
    docs = [json.loads(line) for line in diag_file.read_text().splitlines()]
    (ap_event,) = [d for d in docs if d["kind"] == "event" and d["what"] == "aperture"]
    assert ap_event["fwhm"] is not None and 2.5 < ap_event["fwhm"] < 4.5
    assert ap_event["r_ap"] > 6.0  # 2.5 × FWHM, not the 4 px floor
    # Every frame reports the same frozen FWHM.
    frame_fwhms = {d.get("fwhm") for d in docs if d["kind"] == "frame"}
    assert frame_fwhms == {ap_event["fwhm"]}


# --------------------------------------------------------------------------- #
# Regressions from the 0.4.1 documentation review
# --------------------------------------------------------------------------- #


def _res(mag, ratio, *, diff_comps=0, rel_comps=0, suspect=False):
    """A minimal stand-in for one TargetResult, as _emit_points consumes it."""
    from types import SimpleNamespace

    return SimpleNamespace(
        star=SimpleNamespace(
            auid="000-AAA-001",
            display_name="XX Cyg",
            role=ROLE_TARGET,
            ra_deg=300.0,
            dec_deg=40.0,
        ),
        diff=(
            None
            if mag is None
            else SimpleNamespace(mag=mag, mag_err=0.02, formal_mag_err=0.02, comps_used=diff_comps)
        ),
        relative=(
            None
            if ratio is None
            else SimpleNamespace(flux_ratio=ratio, flux_ratio_err=0.001, comps_used=rel_comps)
        ),
        phot=SimpleNamespace(sky_adu=200.0, saturated=False, suspect=suspect),
    )


def _worker_for_emit(_scene):
    req, _ = _scene
    return PhotometryBatchWorker(req)


def test_batch_keeps_a_magnitude_with_no_flux_ratio(_scene) -> None:
    """The ratio path rejects suspect comparisons; the magnitude path does not.

    A frame where every comparison was flagged suspect used to lose its
    differential magnitude entirely — no row, no warning.
    """
    worker = _worker_for_emit(_scene)
    curves: dict = {}
    worker._emit_points([_res(mag=10.5, ratio=None, diff_comps=3)], 2451545.0, curves)

    assert len(curves) == 1
    point = next(iter(curves.values())).points[0]
    assert point.mag == 10.5
    assert point.relative_flux is None
    assert point.comps_used == 3


def test_batch_comps_used_counts_the_magnitude_ensemble(_scene) -> None:
    """The two ensembles are filtered differently and must be reported apart."""
    worker = _worker_for_emit(_scene)
    curves: dict = {}
    worker._emit_points([_res(mag=10.5, ratio=0.42, diff_comps=4, rel_comps=2)], 2451545.0, curves)

    point = next(iter(curves.values())).points[0]
    assert point.comps_used == 4  # behind `mag`
    assert point.relative_comps_used == 2  # behind `relative_flux`


def test_batch_records_the_suspect_flag(_scene) -> None:
    """Recorded, never acted on — the observer decides."""
    worker = _worker_for_emit(_scene)
    curves: dict = {}
    worker._emit_points([_res(mag=10.5, ratio=0.42, suspect=True)], 2451545.0, curves)

    point = next(iter(curves.values())).points[0]
    assert point.suspect is True
    assert point.mag == 10.5  # kept, not dropped


def test_batch_drops_only_a_result_with_neither_product(_scene) -> None:
    worker = _worker_for_emit(_scene)
    curves: dict = {}
    worker._emit_points([_res(mag=None, ratio=None)], 2451545.0, curves)
    assert curves == {}


def _header_only_fits(path, **header) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((4, 4), dtype=np.uint16))
    for key, value in header.items():
        hdu.header[key.replace("_", "-")] = value
    hdu.writeto(path)


def test_discover_light_frames_finds_fit_and_skips_calibration(tmp_path) -> None:
    """S12: the re-run globbed only '*.fits', and Argos writes '.fit' — it
    never found a frame of an Argos session. A wider glob alone would also
    measure the run's darks, flats and biases as light frames."""
    from argos.workers.photometry_batch_worker import discover_light_frames

    a = tmp_path / "lights" / "a.fit"
    b = tmp_path / "lights" / "b.FITS"
    c = tmp_path / "lights" / "c.fts"
    d = tmp_path / "darks" / "d.fit"
    _header_only_fits(a, IMAGETYP="Light Frame", DATE_OBS="2026-11-01T21:00:10")
    _header_only_fits(b, IMAGETYP="Light Frame", DATE_OBS="2026-11-01T21:00:00")
    _header_only_fits(c)  # no IMAGETYP, no date: kept, sorted last
    _header_only_fits(d, IMAGETYP="Dark Frame", DATE_OBS="2026-11-01T22:00:00")

    assert discover_light_frames(tmp_path) == [b, a, c]  # recursive, d excluded
    assert discover_light_frames(tmp_path / "lights") == [b, a, c]
    assert discover_light_frames(tmp_path / "darks") == []


def test_discover_light_frames_keeps_the_object_s62(tmp_path) -> None:
    """S62: S12 filtered the frame type only. Pointed at a folder holding two
    objects' frames (or at the sessions folder, searched recursively), the re-run
    measured every object's lights against one target set: blank-sky points of
    another field. Frames whose OBJECT names another object are left out (case,
    spaces and underscores ignored); a frame without OBJECT is kept."""
    from argos.workers.photometry_batch_worker import discover_light_frames

    a = tmp_path / "s1" / "lights" / "a.fit"
    b = tmp_path / "s2" / "lights" / "b.fit"
    c = tmp_path / "s1" / "lights" / "c.fit"
    _header_only_fits(a, IMAGETYP="Light Frame", OBJECT="XX Cyg", DATE_OBS="2026-11-01T21:00:00")
    _header_only_fits(b, IMAGETYP="Light Frame", OBJECT="RR Lyr", DATE_OBS="2026-11-01T21:00:05")
    _header_only_fits(c, IMAGETYP="Light Frame", DATE_OBS="2026-11-01T21:00:10")

    assert discover_light_frames(tmp_path, "XX_Cyg") == [a, c]  # b measured before the fix
    assert discover_light_frames(tmp_path, "rr lyr") == [b, c]
    assert discover_light_frames(tmp_path) == [a, b, c]  # no object named: every light


def test_discover_light_frames_reads_an_object_in_simbad_form_s82(tmp_path) -> None:
    """S82: S62 compared the names letter for letter, so a light whose OBJECT is in
    SIMBAD's form ("V* XX Cyg": 20260829T034413Z_V_XX_Cyg) was another object for the
    "XX Cyg" set: 0 frames, "No frames". SIMBAD's identifier prefixes are ignored."""
    from argos.workers.photometry_batch_worker import discover_light_frames

    a = tmp_path / "s1" / "lights" / "a.fit"
    b = tmp_path / "s2" / "lights" / "b.fit"
    c = tmp_path / "s3" / "lights" / "c.fit"
    _header_only_fits(a, IMAGETYP="Light Frame", OBJECT="V* XX Cyg", DATE_OBS="2026-08-29T03:44:13")
    _header_only_fits(b, IMAGETYP="Light Frame", OBJECT="V* RR Lyr", DATE_OBS="2026-08-29T03:45:00")
    _header_only_fits(c, IMAGETYP="Light Frame", OBJECT="NAME Polaris", DATE_OBS="2026-08-29T03:46")

    assert discover_light_frames(tmp_path, "XX Cyg") == [a]  # no frame before the fix
    assert discover_light_frames(tmp_path, "V* RR Lyr") == [b]
    assert discover_light_frames(tmp_path, "V*_XX_Cyg") == [a]
    assert discover_light_frames(tmp_path, "Polaris") == [c]


def test_discover_light_frames_measures_a_session_s_lights_only_s63(tmp_path) -> None:
    """S63: pointed at a session folder, the subfolder search also found the FITS
    other programs wrote beside lights/: star_var_script's Siril ``process/`` holds
    a link to every light and a registered copy of it (same DATE-OBS, OBJECT and
    IMAGETYP). The owner's RR Lyr 2026-09-25 folder gave 585 frames for 195 lights:
    every epoch measured three times. A session folder's frames are its lights/;
    a link to a frame already listed is that frame."""
    from argos.workers.photometry_batch_worker import discover_light_frames

    session = tmp_path / "20260925T200453Z_RR_Lyr"
    a = session / "lights" / "a.fit"
    b = session / "lights" / "b.fit"
    _header_only_fits(a, IMAGETYP="Light Frame", OBJECT="RR Lyr", DATE_OBS="2026-09-25T20:04:56")
    _header_only_fits(b, IMAGETYP="Light Frame", OBJECT="RR Lyr", DATE_OBS="2026-09-25T20:06:10")
    (session / "session.json").write_text("{}")
    (session / "process").mkdir()
    (session / "process" / "light_00001.fit").symlink_to(a)
    _header_only_fits(
        session / "process" / "r_light_00001.fit",
        IMAGETYP="Light Frame",
        OBJECT="RR Lyr",
        DATE_OBS="2026-09-25T20:04:56",
    )
    assert discover_light_frames(session, "RR Lyr") == [a, b]  # + the link and the copy before
    assert discover_light_frames(tmp_path, "RR Lyr") == [a, b]  # from the sessions folder too
    loose = tmp_path / "loose"  # not a session: every FITS, each file once
    _header_only_fits(loose / "x.fit", IMAGETYP="Light Frame", DATE_OBS="2026-09-25T21:00:00")
    (loose / "y.fit").symlink_to(loose / "x.fit")
    assert discover_light_frames(loose) == [loose / "x.fit"]


def _run_batch(req, on_progress=None):
    worker = PhotometryBatchWorker(req)
    points, results = [], []
    worker.point.connect(points.append)
    worker.finished_batch.connect(results.append)
    if on_progress is not None:
        worker.progress.connect(lambda done, total: on_progress(worker, done, total))
    worker.run()
    return results[0], points


def test_batch_skips_frame_without_date_obs(_scene) -> None:
    """S13: a frame without DATE-OBS became a JD 0 point, all the way into
    the AAVSO export."""
    req, _ = _scene
    undated = req.fits_paths[1]
    with fits.open(undated, mode="update") as hdul:
        del hdul[0].header["DATE-OBS"]

    result, points = _run_batch(req)

    assert all(point.jd > 2.4e6 for point in points)
    assert all(p.jd_utc > 2.4e6 for lc in result.curves.values() for p in lc.points)
    assert (result.frames_done, result.frames_skipped) == (2, 1)


def test_batch_counts_unreadable_frame_as_skipped(_scene) -> None:
    """S13: a corrupt file was counted as a measured frame."""
    req, _ = _scene
    req.fits_paths[2].write_bytes(b"not a FITS file")

    result, _points = _run_batch(req)

    assert result.ok and len(result.curves["T@clear"].points) == 2
    assert result.frames_done == 2  # measured frames only
    assert result.frames_skipped == 1


def test_batch_cancel_mid_run_is_reported_and_writes_nothing(_scene) -> None:
    """S13: a cancelled run reported success and overwrote the CSVs."""
    req, out_dir = _scene

    def cancel_after_first(worker, done, _total):
        if done == 1:
            worker.cancel()

    result, _points = _run_batch(req, on_progress=cancel_after_first)

    assert not list(out_dir.glob("*.csv"))  # nothing replaced on disk
    assert result.ok and result.frames_done == 1
    assert result.cancelled is True


def test_batch_csv_names_carry_role_prefix(_scene) -> None:
    """S13: batch CSVs had no role prefix, so a reloaded comparison curve
    came back as a target."""
    from argos.core.catalog.targets import TargetSet as _TargetSet
    from argos.core.photometry.lightcurve import read_curves_csv
    from argos.core.session.review import identify_curve_file

    req, out_dir = _scene
    _run_batch(req)

    names = sorted(p.name for p in out_dir.glob("*.csv"))
    assert names == [
        "comparison_TST_Tau_clear_C1.csv",
        "comparison_TST_Tau_clear_C2.csv",
        "target_TST_Tau_clear_T.csv",
    ]
    targets = _TargetSet.load(out_dir / "targets.json")  # saved beside them
    assert {star.auid for star in targets.stars} == {"T", "C1", "C2"}
    path = out_dir / "comparison_TST_Tau_clear_C1.csv"
    curves, problems = identify_curve_file(path, read_curves_csv(path), targets)
    assert problems == [] and [lc.role for lc in curves.values()] == ["comparison"]


def test_rerun_output_dir_is_a_new_folder_in_the_session(tmp_path) -> None:
    """S13: every re-run wrote <sessions>/../targets/, outside any session,
    overwriting the previous one."""
    from datetime import datetime, timezone

    from argos.workers.photometry_batch_worker import rerun_output_dir

    now = datetime(2026, 11, 1, 21, 5, 9, tzinfo=timezone.utc)
    run = tmp_path / "20261101T200000Z_SS_Cyg"
    (run / "lights").mkdir(parents=True)
    (run / "session.json").write_text("{}")
    expected = run / "photometry_rerun_20261101T210509Z"
    assert rerun_output_dir(run / "lights", now) == expected
    assert rerun_output_dir(run, now) == expected
    loose = tmp_path / "other_frames"
    loose.mkdir()
    assert rerun_output_dir(loose, now) == loose / "photometry_rerun_20261101T210509Z"


def test_batch_errors_use_each_frames_own_gain(_scene, monkeypatch) -> None:
    """S41: a batch re-run used the Camera form's e-/ADU for every saved sub; each
    frame now uses its own (gain table at its GAIN, then its EGAIN), the request's
    value only for a frame that records none."""
    import argos.workers.photometry_batch_worker as bw

    req, _out_dir = _scene
    for path, header in zip(req.fits_paths, ({"GAIN": 200, "EGAIN": 0.31}, {"EGAIN": 0.42}, {})):
        with fits.open(path, mode="update") as hdul:
            hdul[0].header.update(header)
    req.egain_table = {"200": 0.29}
    seen: list[float] = []
    real = bw.measure_frame
    monkeypatch.setattr(
        bw,
        "measure_frame",
        lambda green, wcs, ts, params, **kw: seen.append(params.egain)
        or real(green, wcs, ts, params, **kw),
    )
    worker = PhotometryBatchWorker(req)
    worker.run()

    assert seen == [pytest.approx(0.29), pytest.approx(0.42), pytest.approx(req.params.egain)]


def test_batch_uses_the_cameras_measured_egain_and_scintillation_s73_s74(
    _scene, monkeypatch
) -> None:
    """S73: an S30 Pro sub at gain 80 says EGAIN 0.8 (0.4.2) or 1.723 (0.4.1); the
    re-run took that (S41, S70) where the camera's photon transfer gives 0.228. The
    recorder names the source; S74's exposure, airmass and height come from the
    sub's header."""
    import json

    import argos.workers.photometry_batch_worker as bw

    req, out_dir = _scene
    s30pro = {"TELESCOP": "ZWO Seestar S30 Pro", "GAIN": 80, "EXPTIME": 10.0}
    headers = (
        dict(s30pro, EGAIN=0.8, AIRMASS=1.03, SITEELEV=100.0),
        dict(s30pro, EGAIN=1.723, AIRMASS=1.5),
        {"GAIN": 80, "EGAIN": 0.42},  # no TELESCOP: its own EGAIN
    )
    for path, header in zip(req.fits_paths, headers):
        with fits.open(path, mode="update") as hdul:
            hdul[0].header.update(header)
    seen: list = []
    real = bw.measure_frame
    monkeypatch.setattr(
        bw,
        "measure_frame",
        lambda green, wcs, ts, params, **kw: seen.append(params)
        or real(green, wcs, ts, params, **kw),
    )
    req.diagnostics = True
    PhotometryBatchWorker(req).run()

    assert [float(p.egain) for p in seen] == [
        pytest.approx(0.228),  # 0.8 before the fix
        pytest.approx(0.228),  # 1.723 before the fix
        pytest.approx(0.42),
    ]
    assert [(p.airmass, p.site_height_m) for p in seen[:2]] == [(1.03, 100.0), (1.5, None)]
    assert seen[0].scint_frac() > seen[0].scint_frac(1.0) > 0
    records = [
        json.loads(line)
        for f in out_dir.glob("*_diagnostics.jsonl")
        for line in f.read_text().splitlines()
    ]
    frames = [r for r in records if r.get("kind") == "frame"]
    assert [r["egain_source"] for r in frames] == ["S30 Pro PTC", "S30 Pro PTC", "header EGAIN"]


# ── S43: a field jump during a batch re-run ────────────────────────────────


def _jump_scene(tmp_path, *, n_before=4, n_after=4, jump=(26.0, 12.0)):
    """Frames whose field jumps by more than the tracker's search radius
    (15 green px) after ``n_before`` frames, as on the owner's RR Lyr run of
    2026-09-25 (frame 52: 22.8 green px, frame 175: 140 px).

    A field star that is not in the set lands, after the jump, where comparison
    C1 was: the tracker's window for C1 locks on it and reports an anchor, as
    the windows locked on noise on the real frames. The reference solve is
    exact for the frames before the jump only.
    """
    ref = {
        (1.0, 1.0): (60.0, 60.0),  # target
        (2.0, 2.0): (100.0, 40.0),  # comp 1
        (3.0, 3.0): (40.0, 110.0),  # comp 2
        (4.0, 4.0): (110.0, 105.0),  # comp 3
    }
    jumped = {k: (x + jump[0], y + jump[1]) for k, (x, y) in ref.items()}
    neighbour = (100.0 - jump[0], 40.0 - jump[1])  # lands on C1's old place
    ts = TargetSet(object_name="JMP Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    for i in (2, 3, 4):
        ts.set_role(
            TargetStar(
                role=ROLE_COMPARISON,
                ra_deg=float(i),
                dec_deg=float(i),
                auid=f"C{i - 1}",
                mags={"V": 11.0},
            )
        )
    rng = np.random.default_rng(43)
    paths = []
    for i in range(n_before + n_after):
        pos = ref if i < n_before else jumped
        shift = (0.0, 0.0) if i < n_before else jump
        stars = [(pos[(1.0, 1.0)], 20000.0)]
        stars += [(pos[(float(k), float(k))], 8000.0) for k in (2, 3, 4)]
        stars.append(((neighbour[0] + shift[0], neighbour[1] + shift[1]), 8000.0))
        raw = _raw_with_green_stars(stars, green_shape=(160, 160))
        raw += rng.normal(0.0, 3.0, raw.shape).astype(np.float32)
        p = tmp_path / f"jmp_{i:03d}.fits"
        _write_fits(p, raw, f"2026-09-25T21:{i:02d}:00")
        paths.append(p)
    req = BatchRequest(
        fits_paths=paths,
        wcs=_FakeWCS(ref),
        target_set=ts,
        params=PhotometryParams.from_config(lambda k, d: d),
        out_dir=tmp_path / "out",
        object_name="JMP Tau",
    )
    return req, _FakeWCS(jumped)


def test_batch_re_solves_a_frame_on_which_the_field_jumped(tmp_path) -> None:
    """S43: after a pointing jump larger than the tracker's search radius, the
    batch kept measuring through the stale transform: unflagged blank-sky
    points (RR Lyr 2026-09-25 frames 52-79, apertures 20-130 px off), and a
    summary that said the field was tracked. The frame on which the lock is
    lost is now re-solved and the apertures re-anchored on its solution."""
    req, jumped_solution = _jump_scene(tmp_path)
    calls: list = []

    def solver(green):
        calls.append(green.shape)
        return jumped_solution

    req.solver = solver
    result, _points = _run_batch(req)

    assert result.ok and result.frames_done == 8
    curve = result.curves["T@clear"]
    assert len(curve.points) == 8
    assert not any(p.suspect for p in curve.points)
    mags = [p.mag for p in curve.points]
    assert max(mags) - min(mags) < 0.05, mags  # never a blank-sky value
    assert calls == [(160, 160)]  # one re-solve, on the frame of the jump
    assert result.frames_resolved == 1
    assert result.frames_unanchored == 0


def test_batch_flags_points_until_the_field_is_re_anchored(tmp_path) -> None:
    """S43: without a solve (no ASTAP, or it fails), the frames after a lost
    lock are flagged suspect — they used to be written as good points — they
    stay out of the run's systematic floor, and the result says so."""
    req, _jumped = _jump_scene(tmp_path)
    req.solver = lambda green: None  # the re-solve fails
    result, _points = _run_batch(req)

    assert result.ok and result.frames_done == 8
    by_frame = {round(p.jd_utc, 6): p for p in result.curves["T@clear"].points}
    jds = sorted(by_frame)
    assert len(jds) > 4  # blank-sky points are kept, flagged
    assert all(not by_frame[jd].suspect for jd in jds[:4])
    assert all(by_frame[jd].suspect for jd in jds[4:])  # unflagged before the fix
    good = [by_frame[jd] for jd in jds[:4]]
    assert all(p.sigma_syst is None or p.sigma_syst < 0.05 for p in good)
    assert result.frames_resolved == 0
    assert result.frames_unanchored == 4


@pytest.mark.skipif(
    not os.environ.get("ARGOS_S43_SESSION"),
    reason="set ARGOS_S43_SESSION to a COPY of the RR Lyr 2026-09-25 session (lights/, targets.json)",
)
def test_batch_follows_the_real_rr_lyr_jump_with_astap(tmp_path) -> None:
    """S43 on the owner's frames (a copy): RR Lyr 2026-09-25, frames 0-79,
    measured through frame 0's solve. Frame 52 jumped 22.8 green px; every
    target aperture must sit on the star (checked against each frame's own
    ASTAP solve), with no point flagged and no frame lost."""
    import json
    import math
    from pathlib import Path

    from argos.core.imaging.astrometry_session import batch_frame_solver
    from argos.core.imaging.green import green_plane
    from argos.core.imaging.platesolve import find_astap
    from argos.workers.photometry_batch_worker import discover_light_frames

    if find_astap() is None:
        pytest.skip("ASTAP not installed")
    session = Path(os.environ["ARGOS_S43_SESSION"])
    paths = discover_light_frames(session / "lights")[:80]
    tset = TargetSet.load(session / "targets.json")
    target = tset.by_role(ROLE_TARGET)[0]
    cfg = lambda key, default: default  # noqa: E731 - the shipped defaults
    solver = batch_frame_solver(cfg, (target.ra_deg / 15.0, target.dec_deg))

    def solve(path):
        raw, _jd, _gain = PhotometryBatchWorker._read_frame(path)
        return solver(green_plane(raw))

    reference = solve(paths[0])
    assert reference is not None
    req = BatchRequest(
        fits_paths=paths,
        wcs=reference,
        target_set=tset,
        params=PhotometryParams.from_config(cfg),
        out_dir=tmp_path / "out",
        object_name="RR Lyr",
        diagnostics=True,
        # As the page does: re-solves near the reference solve's centre.
        solver=batch_frame_solver(cfg, (reference.crval1 / 15.0 % 24.0, reference.crval2)),
    )
    result, _points = _run_batch(req)

    assert result.frames_done == 80
    assert result.frames_resolved >= 1  # frame 52
    assert result.frames_unanchored == 0
    diag = next((tmp_path / "out").glob("*_diagnostics.jsonl"))
    placed = {
        d["frame"]: (d["x"], d["y"])
        for d in map(json.loads, diag.read_text().splitlines())
        if d["kind"] == "star" and d.get("role") == ROLE_TARGET
    }
    for frame in range(48, 80):
        truth = solve(paths[frame])
        assert truth is not None, frame
        tx, ty = truth.world_to_pixel_deg(target.ra_deg, target.dec_deg)
        x, y = placed[frame]
        assert math.hypot(x - float(tx), y - float(ty)) < 2.0, frame


def test_a_re_run_keeps_one_curve_per_star_and_filter_s49(_scene) -> None:
    """S49: a re-run of frames taken through two filters put every frame's
    point of a star in one curve and one CSV."""
    req, out_dir = _scene
    for path, filt in zip(req.fits_paths, ("V", "B", "V")):
        with fits.open(path, mode="update") as hdul:
            hdul[0].header["FILTER"] = filt

    result, points = _run_batch(req)

    assert sorted(k for k in result.curves if k.startswith("T@")) == ["T@b", "T@v"]
    assert len(result.curves["T@v"].points) == 2 and len(result.curves["T@b"].points) == 1
    names = sorted(p.name for p in out_dir.glob("*.csv"))
    assert "target_TST_Tau_v_T.csv" in names and "target_TST_Tau_b_T.csv" in names
    assert "target_TST_Tau_T.csv" not in names  # the one mixed file before the fix
    assert {p.name for p in points if p.key == "T@b"} == {"T [b]"}


def _two_anchor_scene(tmp_path, *, n=6, jump_at=None, jump=(26.0, 12.0)):
    """Target and two comparisons (a tracker of 2 anchors), still or jumping at
    frame ``jump_at``; after the jump a field star lands where comparison C1 was,
    so the S43 check (1 of 2 anchors seen) passes on blank-sky apertures."""
    ref = {(1.0, 1.0): (60.0, 60.0), (2.0, 2.0): (100.0, 40.0), (3.0, 3.0): (40.0, 110.0)}
    jumped = {k: (x + jump[0], y + jump[1]) for k, (x, y) in ref.items()}
    neighbour = (100.0, 40.0)  # where C1 was
    ts = TargetSet(object_name="TWO Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    for i in (2, 3):
        ts.set_role(
            TargetStar(
                role=ROLE_COMPARISON,
                ra_deg=float(i),
                dec_deg=float(i),
                auid=f"C{i - 1}",
                mags={"V": 11.0},
            )
        )
    rng = np.random.default_rng(58)
    paths = []
    for i in range(n):
        after = jump_at is not None and i >= jump_at
        pos = jumped if after else ref
        stars = [(pos[(1.0, 1.0)], 20000.0), (pos[(2.0, 2.0)], 8000.0), (pos[(3.0, 3.0)], 8000.0)]
        if after:
            stars.append((neighbour, 8000.0))
        raw = _raw_with_green_stars(stars, green_shape=(160, 160))
        raw += rng.normal(0.0, 3.0, raw.shape).astype(np.float32)
        p = tmp_path / f"two_{i:03d}.fits"
        _write_fits(p, raw, f"2026-08-29T05:{i:02d}:00")
        paths.append(p)
    req = BatchRequest(
        fits_paths=paths,
        wcs=_FakeWCS(ref),
        target_set=ts,
        params=PhotometryParams.from_config(lambda k, d: d),
        out_dir=tmp_path / "out",
        object_name="TWO Tau",
    )
    return req, _FakeWCS(ref), _FakeWCS(jumped)


def test_a_re_run_flags_a_lock_on_two_anchors_without_a_fresh_solution_s58(tmp_path) -> None:
    """S58: with 1 or 2 anchors the S43 check (ceil(n/2) seen) is met by the very
    anchor that moved the apertures, so it verifies nothing (S56 in the live path).
    Without a solver, a re-run's frames measured through the reference solve (of
    no frame of the series) are flagged suspect; they were good points before."""
    req, _ref, _jumped = _two_anchor_scene(tmp_path)
    result, _points = _run_batch(req)

    assert result.ok and result.frames_done == 6
    points = result.curves["T@clear"].points
    assert len(points) == 6 and all(p.suspect for p in points)  # unflagged before the fix
    assert result.frames_unverified == 6
    assert result.frames_unanchored == 0  # S43's lock holds: 1 of 2 seen


def test_a_re_run_verifies_two_anchors_on_a_fresh_solution_s58(tmp_path) -> None:
    """S58: a frame measured through its own solution or the previous frame's,
    within 10 px of it, is verified: a solver re-solves every other frame and no
    point is flagged. After a jump onto a neighbour (the S43 check passes) the
    tracker moved the apertures 28 px: the frame is re-solved, never measured on
    blank sky."""
    req, ref, _jumped = _two_anchor_scene(tmp_path)
    calls: list = []
    req.solver = lambda green: calls.append(green.shape) or ref
    result, _points = _run_batch(req)
    assert not any(p.suspect for p in result.curves["T@clear"].points)
    assert len(calls) == 3  # frames 0, 2 and 4: 1 and 3 use the previous frame's
    assert result.frames_unverified == 0

    (tmp_path / "jump").mkdir()
    req, ref, jumped = _two_anchor_scene(tmp_path / "jump", n=4, jump_at=2)
    solved: list = []

    def solver(green):
        solved.append(len(solved))
        return ref if len(solved) == 1 else jumped

    req.solver = solver
    result, _points = _run_batch(req)
    points = result.curves["T@clear"].points
    assert len(points) == 4 and not any(p.suspect for p in points)
    mags = [p.mag for p in points]
    assert max(mags) - min(mags) < 0.05, mags  # never a blank-sky value
    assert len(solved) == 2  # frame 0 (no fresh solve) and frame 2 (the jump)


def test_a_field_moving_6_px_per_frame_is_verified_on_the_previous_solution_s56(
    tmp_path,
) -> None:
    """S56 as amended on 2026-11-16 (S58 in the re-run): a frame measured through the
    previous frame's solution is verified when the tracker moved no aperture 10 px or
    more from it. The converged tracker (S69) sees the owner's fields move 4-7.5 px
    between subs; with the 2 px threshold every such frame was re-solved (6 solves in
    6 frames here), with 10 px every other frame is (3), and no point is flagged."""
    drift = (5.0, 3.0)  # 5.8 px per frame
    base = {(1.0, 1.0): (40.0, 50.0), (2.0, 2.0): (80.0, 30.0), (3.0, 3.0): (30.0, 100.0)}
    ts = TargetSet(object_name="TWO Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    for i in (2, 3):
        ts.set_role(
            TargetStar(ROLE_COMPARISON, float(i), float(i), auid=f"C{i - 1}", mags={"V": 11.0})
        )
    rng = np.random.default_rng(56)
    paths, solutions = [], []
    for i in range(6):
        pos = {k: (x + i * drift[0], y + i * drift[1]) for k, (x, y) in base.items()}
        solutions.append(_FakeWCS(pos))
        stars = [(pos[(1.0, 1.0)], 20000.0), (pos[(2.0, 2.0)], 8000.0), (pos[(3.0, 3.0)], 8000.0)]
        raw = _raw_with_green_stars(stars, green_shape=(160, 160))
        raw += rng.normal(0.0, 3.0, raw.shape).astype(np.float32)
        p = tmp_path / f"drift_{i:03d}.fits"
        _write_fits(p, raw, f"2026-08-29T05:{i:02d}:00")
        paths.append(p)
    calls: list[int] = []

    def solver(green):
        y, x = np.unravel_index(int(np.argmax(green)), green.shape)  # the target, brightest
        frame = min(
            range(6),
            key=lambda i: math.hypot(x - (40.0 + i * drift[0]), y - (50.0 + i * drift[1])),
        )
        calls.append(frame)
        return solutions[frame]

    req = BatchRequest(
        fits_paths=paths,
        wcs=_FakeWCS(base),
        target_set=ts,
        params=PhotometryParams.from_config(lambda k, d: d),
        out_dir=tmp_path / "out",
        object_name="TWO Tau",
        solver=solver,
    )
    result, _points = _run_batch(req)
    assert not any(p.suspect for p in result.curves["T@clear"].points)
    assert result.frames_unverified == 0
    assert calls == [0, 2, 4]  # [0, 1, 2, 3, 4, 5] with the 2 px threshold


def _site_scene(tmp_path, site, *, n=3, software="Argos v0.4.2", step_min=10):
    """S66: frames whose headers say where the mount pointed from a synthetic site.

    The mount (true site 30°N 100°E) puts the field on its meridian at 80°; the
    request's Settings site is ``site``; ``software`` None: frames Argos did not write.
    """
    from datetime import datetime, timedelta, timezone

    from argos.core.imaging.sky_geometry import compute_airmass, horizontal_at
    from argos.core.photometry.airmass import julian_date

    start = datetime(2026, 3, 1, 15, 0, 0, tzinfo=timezone.utc)
    jd0 = julian_date(start)
    ra_h = ((18.697374558 + 24.06570982441908 * (jd0 - 2451545.0)) % 24.0 + 100.0 / 15.0) % 24.0
    coords = [(ra_h * 15.0, 40.0), (ra_h * 15.0 + 0.1, 40.1), (ra_h * 15.0 - 0.1, 39.9)]
    wcs = _FakeWCS(dict(zip(coords, [(30.0, 30.0), (10.0, 10.0), (50.0, 50.0)])), margin=_MARGIN)
    ts = TargetSet(object_name="SITE")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=coords[0][0], dec_deg=40.0, auid="T"))
    for auid, (ra, dec) in zip(("C1", "C2"), coords[1:]):
        ts.set_role(
            TargetStar(role=ROLE_COMPARISON, ra_deg=ra, dec_deg=dec, auid=auid, mags={"V": 11.0})
        )
    stars = [((30.0, 30.0), 20000.0), ((10.0, 10.0), 8000.0), ((50.0, 50.0), 8000.0)]
    paths, header_airmass = [], []
    for i in range(n):
        when = start + timedelta(minutes=step_min * i)
        alt, az = horizontal_at(julian_date(when), ra_h, 40.0, 30.0, 100.0)
        hdu = fits.PrimaryHDU(
            np.clip(_raw_with_green_stars(stars, margin=_MARGIN), 0, 65535).astype(np.uint16)
        )
        h = hdu.header
        h["DATE-OBS"] = when.strftime("%Y-%m-%dT%H:%M:%S")
        h["EXPTIME"] = 10.0
        h["RA"], h["DEC"] = ra_h, 40.0
        h["ALTITUDE"], h["AZIMUTH"] = round(alt, 4), round(az, 4)
        h["AIRMASS"] = round(compute_airmass(alt), 4)
        h["SITELAT"], h["SITELONG"] = site
        if software:
            h["SOFTWARE"] = software
        p = tmp_path / f"sub_{i}.fit"
        hdu.writeto(p)
        paths.append(p)
        header_airmass.append(h["AIRMASS"])
    req = BatchRequest(
        fits_paths=paths,
        wcs=wcs,
        target_set=ts,
        params=PhotometryParams.from_config(lambda k, d: d),
        out_dir=tmp_path / "out",
        object_name="SITE",
        site=(site[0], site[1], 0.0),
    )
    return req, header_airmass


def test_a_re_run_takes_the_header_airmass_when_the_site_is_wrong_s66(tmp_path, caplog) -> None:
    """S66: a re-run computed every point's airmass for the Settings site, even when
    the frames' headers show the telescope was elsewhere (X3): 1.5 instead of 1.015."""
    req, header_airmass = _site_scene(tmp_path, (30.0, 40.0))

    with caplog.at_level("WARNING"):
        result, _points = _run_batch(req)

    _assert_target_header_and_comparisons_own_airmass(req, result, header_airmass)
    warns = [r for r in caplog.records if "not where the telescope was" in r.getMessage()]
    assert len(warns) == 1


def _assert_target_header_and_comparisons_own_airmass(req, result, header_airmass) -> None:
    """S66: the target's airmass is the header AIRMASS (the field centre's). S78: a
    comparison's is its own, for the site fitted to the headers' pointing (the mount's,
    30°N 100°E), where it took the target's header AIRMASS before."""
    from argos.core.photometry.airmass import airmass_at

    stars = {s.auid: s for s in req.target_set.stars}
    for curve in result.curves.values():
        star = stars[curve.auid]
        if curve.role == ROLE_TARGET:
            assert [p.airmass for p in curve.points] == header_airmass
            continue
        own = [airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, 30.0, 100.0) for p in curve.points]
        assert [p.airmass for p in curve.points] == own
        assert own != header_airmass


def test_a_re_run_takes_the_header_airmass_when_the_site_is_right_too_s66(tmp_path, caplog) -> None:
    """S66 as decided (option b): an Argos frame's header AIRMASS, the mount's, is used
    whatever the Settings site. A Settings site under the 5° tolerance still erred (XX
    Cyg 2026-08-29: 0.013-0.015 too high at 67-71°, where the header is within 0.0004
    of astropy); the site check only warns."""
    req, header_airmass = _site_scene(tmp_path, (30.0, 100.0))

    with caplog.at_level("WARNING"):
        result, _points = _run_batch(req)

    _assert_target_header_and_comparisons_own_airmass(req, result, header_airmass)
    assert result.frames_header_airmass == 3 and result.frames_site_wrong == 0
    assert not [r for r in caplog.records if "not where the telescope was" in r.getMessage()]


@pytest.mark.parametrize("site", [(30.0, 40.0), (32.0, 100.0)])
def test_a_short_re_run_at_a_wrong_site_gives_comparisons_the_header_airmass_s78(
    tmp_path, site
) -> None:
    """S78 amended (validation F1): 3 frames over 4 minutes fit no site, and the
    Settings site does not reproduce the mount's pointing (60° off, or 2° off as XX Cyg
    2026-08-29's). Every star keeps the frame's header AIRMASS, within 0.002 of a
    comparison's own; the comparisons took the airmass computed for that site (RR Lyr
    2026-09-25 195307Z: 4.0-4.9 for 1.03)."""
    from argos.core.photometry.airmass import airmass_at

    req, header_airmass = _site_scene(tmp_path, site, step_min=2)

    result, _points = _run_batch(req)

    stars = {s.auid: s for s in req.target_set.stars}
    for curve in result.curves.values():
        star = stars[curve.auid]
        own = [airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, 30.0, 100.0) for p in curve.points]
        assert [p.airmass for p in curve.points] == header_airmass
        assert max(abs(a - b) for a, b in zip(own, header_airmass)) < 0.002


def test_a_short_re_run_at_a_right_site_gives_comparisons_their_own_airmass_s78(tmp_path) -> None:
    """S78: without a fitted site, a Settings site that reproduces the mount's pointing
    gives each comparison its own airmass."""
    from argos.core.photometry.airmass import airmass_at

    req, header_airmass = _site_scene(tmp_path, (30.0, 100.0), step_min=2)

    result, _points = _run_batch(req)

    for star in req.target_set.stars[1:]:
        points = result.curves[f"{star.auid}@clear"].points
        own = [airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, 30.0, 100.0) for p in points]
        assert [p.airmass for p in points] == own != header_airmass


def test_a_re_run_computes_the_airmass_of_frames_argos_did_not_write_s66(tmp_path) -> None:
    from argos.core.photometry.airmass import airmass_at

    req, _header_airmass = _site_scene(tmp_path, (30.0, 100.0), software=None)

    result, _points = _run_batch(req)

    for star in req.target_set.stars:  # each star's own, for the Settings site
        points = result.curves[f"{star.auid}@clear"].points
        expected = [airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, 30.0, 100.0) for p in points]
        assert [p.airmass for p in points] == expected
    assert result.frames_header_airmass == 0


def _freeze_pointing(req, after: int) -> None:
    """X1: the lights after ``after`` keep its RA, DEC, ALTITUDE, AZIMUTH and AIRMASS."""
    with fits.open(req.fits_paths[after]) as hdul:
        polled = {k: hdul[0].header[k] for k in ("RA", "DEC", "ALTITUDE", "AZIMUTH", "AIRMASS")}
    for path in req.fits_paths[after + 1 :]:
        with fits.open(path, mode="update") as hdul:
            hdul[0].header.update(polled)


def test_a_re_run_computes_the_airmass_of_frozen_frames_at_a_right_site_s66(tmp_path) -> None:
    """S66 with X1 (technical review): a frame whose pointing is a lost mount's last
    poll keeps that poll's AIRMASS (and drifts from the direction computed for the right
    site by about 0.2° per minute: 30 min after the freeze the per-frame check said
    "wrong site", with a false WARN). Such a frame's airmass is computed, as before."""
    from argos.core.photometry.airmass import airmass_at

    req, header_airmass = _site_scene(tmp_path, (30.0, 100.0), n=6)  # 0-50 min
    _freeze_pointing(req, 0)

    result, _points = _run_batch(req)

    target = result.curves["T@clear"].points
    star = req.target_set.stars[0]
    expected = [airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, 30.0, 100.0) for p in target]
    assert target[0].airmass == header_airmass[0]  # polled before the freeze
    assert [p.airmass for p in target[1:]] == expected[1:]
    assert abs(target[-1].airmass - header_airmass[0]) > 0.01  # not the frozen value
    assert result.frames_header_airmass == 1 and result.frames_site_wrong == 0


def test_a_frozen_frames_scintillation_takes_its_rows_airmass_s74(tmp_path, monkeypatch) -> None:
    """S74 amended (science and technical reviews): each frame's scintillation took the
    header AIRMASS, even a frozen pointing's stale one (X1: 2.0 here, where the star is
    at 1.02), and the same for every star. Each star's now takes the airmass its row
    gets (S66: computed for a frozen frame; S78: a comparison's own)."""
    import argos.workers.photometry_batch_worker as bw
    from argos.core.photometry.airmass import airmass_at

    req, _header_airmass = _site_scene(tmp_path, (30.0, 100.0), n=3)
    with fits.open(req.fits_paths[0], mode="update") as hdul:
        hdul[0].header["AIRMASS"] = 2.0  # a lost mount's stale value
    _freeze_pointing(req, 0)
    got = []
    real = bw.measure_frame

    def spy(*args, **kwargs):
        star_airmass = kwargs.get("star_airmass")
        tset = args[2]
        got.append([star_airmass(s) if star_airmass else None for s in tset.stars])
        return real(*args, **kwargs)

    monkeypatch.setattr(bw, "measure_frame", spy)
    result, _points = _run_batch(req)

    assert result.frames_done == 3
    target = req.target_set.stars[0]
    jds = [p.jd_utc for p in result.curves["T@clear"].points]
    for jd, airmasses in zip(jds[1:], got[1:]):  # the frozen frames
        assert airmasses[0] == pytest.approx(
            airmass_at(jd, target.ra_deg, target.dec_deg, 30.0, 100.0)
        )  # None before: the frame's stale 2.0 for every star
        assert airmasses[0] < 1.1


def test_a_re_run_computes_the_airmass_of_frozen_frames_at_a_wrong_site_s66(tmp_path) -> None:
    """S66 with X1: a frozen frame's header AIRMASS is stale; its airmass is computed for
    the Settings site (wrong here, as the WARN says), as before S66."""
    from argos.core.photometry.airmass import airmass_at

    req, header_airmass = _site_scene(tmp_path, (30.0, 40.0), n=4)
    _freeze_pointing(req, 1)

    result, _points = _run_batch(req)

    target = result.curves["T@clear"].points
    star = req.target_set.stars[0]
    assert [p.airmass for p in target[:2]] == header_airmass[:2]
    assert [p.airmass for p in target[2:]] == [
        airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, 30.0, 40.0) for p in target[2:]
    ]
    assert result.frames_header_airmass == 2 and result.frames_site_wrong == 2


def test_a_re_run_flags_the_points_of_a_frame_without_a_detection_s67(tmp_path) -> None:
    """S67 in the batch re-run (science review): a frame on which the target is measured
    below SNR 3 (XX Cyg 2026-09-07 _00021: SNR 1.6, 13.29 ± 0.75 among 11.7-12.2) was
    written unflagged and reached the AAVSO export of the re-run, which S67 now drops
    from the live run's own file. Its points are flagged suspect, left out of the
    run's sigma_syst and of the AAVSO export, and counted. The SNR rule is per target
    (owner's decision): a second, bright target and the comparisons keep their points."""
    from argos.core.photometry.lightcurve import write_aavso

    wcs = _FakeWCS(
        {
            (1.0, 1.0): (60.0, 60.0),
            (2.0, 2.0): (35.0, 35.0),
            (3.0, 3.0): (85.0, 85.0),
            (4.0, 4.0): (35.0, 85.0),
        }
    )
    ts = TargetSet(object_name="TST Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=4.0, dec_deg=4.0, auid="T2"))
    for i, auid in ((2, "C1"), (3, "C2")):
        ts.set_role(
            TargetStar(
                role=ROLE_COMPARISON, ra_deg=float(i), dec_deg=float(i), auid=auid, mags={"V": 11.0}
            )
        )
    rng = np.random.default_rng(67)
    paths = []
    for i in range(12):
        target_peak = 0.0 if i == 5 else 3000.0 * (1.0 + 0.01 * rng.normal())
        stars = [
            ((60.0, 60.0), target_peak),
            ((35.0, 35.0), 8000.0),
            ((85.0, 85.0), 8000.0),
            ((35.0, 85.0), 6000.0),
        ]
        raw = _raw_with_green_stars(stars, green_shape=(120, 120))
        raw += rng.normal(0.0, 3.0, raw.shape).astype(np.float32)
        p = tmp_path / f"sub_{i:03d}.fits"
        _write_fits(p, raw, f"2026-07-05T01:{i:02d}:00")
        paths.append(p)
    req = BatchRequest(
        fits_paths=paths,
        wcs=wcs,
        target_set=ts,
        # tracking off: the reference solve as chosen (2 anchors would be S58's case)
        params=replace(PhotometryParams.from_config(lambda k, d: d), track_apertures=False),
        out_dir=tmp_path / "out",
        object_name="TST Tau",
    )

    result, _points = _run_batch(req)

    assert result.frames_no_detection == 1
    for key, curve in result.curves.items():
        flagged = [i for i, p in enumerate(curve.points) if p.suspect]
        assert flagged == ([5] if key == "T@clear" else []), key
    target = result.curves["T@clear"]
    floors = {p.sigma_syst for p in target.points}
    assert len(floors) == 1 and floors.pop() < 0.05  # the blank frame did not set it
    summary = write_aavso(tmp_path / "aavso.txt", [target], obscode="TST01")
    assert summary.rows == 11
    records = [json.loads(line) for line in next(req.out_dir.glob("*.jsonl")).open()]
    events = [r for r in records if r.get("what") == "no_detection"]
    assert [(r["frame"], r["low_snr"]) for r in events] == [(5, ["T"])]


# ── S69, S70: the tracker on an alt-az run, the frame's gain in the frame loop ──


class _RotWCS:
    """The rotating scene's stars, ``deg`` degrees about the green-frame centre."""

    def __init__(self, ref, deg, center=(80.0, 80.0)):
        self._ref, self._deg, self._center = ref, deg, center

    def world_to_pixel_deg(self, ra_deg, dec_deg):
        return _rotate(*self._ref[(ra_deg, dec_deg)], *self._center, self._deg)


def _turning_scene(tmp_path, *, deg_per_frame, n_frames, check_offset=(0.0, 0.0)):
    """A field turning ``deg_per_frame`` per frame about the centre of a 160 px green
    plane (an alt-az run): target, 4 comparisons, a check star whose catalogue place
    is ``check_offset`` green px from the star, and a light sky noise."""
    ref = {
        (1.0, 1.0): (80.0, 40.0),  # target
        (2.0, 2.0): (125.0, 75.0),
        (3.0, 3.0): (40.0, 100.0),
        (4.0, 4.0): (110.0, 130.0),
        (5.0, 5.0): (30.0, 45.0),
        (6.0, 6.0): (70.0, 120.0),  # check
    }
    ts = TargetSet(object_name="ALT Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    for i in (2, 3, 4, 5):
        ts.set_role(
            TargetStar(
                role=ROLE_COMPARISON,
                ra_deg=float(i),
                dec_deg=float(i),
                auid=f"C{i - 1}",
                mags={"V": 11.0},
            )
        )
    ts.set_role(TargetStar(role=ROLE_CHECK, ra_deg=6.0, dec_deg=6.0, auid="K", mags={"V": 11.0}))
    star_at = dict(ref)
    star_at[(6.0, 6.0)] = (70.0 + check_offset[0], 120.0 + check_offset[1])
    rng = np.random.default_rng(69)
    paths = []
    for i in range(n_frames):
        deg = deg_per_frame * i
        stars = [(_rotate(*star_at[k], 80.0, 80.0, deg), 8000.0) for k in sorted(star_at)]
        raw = _raw_with_green_stars(stars, green_shape=(160, 160))
        raw += rng.normal(0.0, 3.0, raw.shape).astype(np.float32)
        p = tmp_path / f"alt_{i:03d}.fits"
        _write_fits(p, raw, f"2026-09-07T04:{i:02d}:00")
        paths.append(p)
    req = BatchRequest(
        fits_paths=paths,
        wcs=_RotWCS(ref, 0.0),
        target_set=ts,
        params=PhotometryParams.from_config(lambda k, d: d),
        out_dir=tmp_path / "out",
        object_name="ALT Tau",
    )
    return req, ref


def _frame_angle(green, ref):
    """The scene's rotation on a green plane, from the target's centroid (a 'solve')."""
    import math

    from argos.core.photometry.tracking import refine_centroid

    best = None
    for deg10 in range(-300, 301):
        x, y = _rotate(*ref[(1.0, 1.0)], 80.0, 80.0, deg10 / 10.0)
        if best is None or green[int(round(y)), int(round(x))] > best[0]:
            best = (green[int(round(y)), int(round(x))], x, y)
    cx, cy = refine_centroid(green, best[1], best[2], 4.0)
    tx, ty = ref[(1.0, 1.0)]
    return math.degrees(math.atan2(cy - 80.0, cx - 80.0) - math.atan2(ty - 80.0, tx - 80.0))


def test_a_re_run_re_solves_once_the_field_turned_2_deg_s69(tmp_path, caplog) -> None:
    """S69 (a): the tracker carried the request's solution over XX Cyg 2026-09-07's
    whole 16.5° of rotation (no re-solve: the lock held). A frame is now re-solved
    once the tracked rotation since its solution exceeds 2°; a solver that fails is
    tried again only after 2° more, never on every frame."""
    req, ref = _turning_scene(tmp_path, deg_per_frame=0.75, n_frames=10)
    calls: list[int] = []

    def solver(green):
        calls.append(1)
        return _RotWCS(ref, _frame_angle(green, ref))

    req.solver = solver
    result, _points = _run_batch(req)
    assert result.ok and result.frames_done == 10
    assert len(calls) == 3  # at 2.25° (frame 3), frames 6 and 9; none before the fix
    assert result.frames_rotation_solved == 3
    assert not any(p.suspect for p in result.curves["T@clear"].points)
    assert abs(result.rotation_deg) < 0.1  # frame 9 is its own solution

    (tmp_path / "fail").mkdir()
    req, ref = _turning_scene(tmp_path / "fail", deg_per_frame=0.75, n_frames=10)
    failed: list[int] = []
    req.solver = lambda green: failed.append(1)
    with caplog.at_level("WARNING"):
        result, _points = _run_batch(req)
    assert result.ok and result.frames_done == 10 and result.frames_rotation_solved == 0
    assert len(failed) == 3  # 2.25°, then 4.5° and 6.75°: 2° apart, of 7 frames past 2°
    assert not any(p.suspect for p in result.curves["T@clear"].points)
    # Technical review: counted, and never worded as flagging the points.
    assert result.frames_rotation_unsolved == 3
    assert not any("its points are flagged" in r.getMessage() for r in caplog.records)


def test_a_re_run_leaves_an_off_centre_star_out_of_the_ensemble_s69(tmp_path) -> None:
    """S69 (b): a comparison or check star whose centroid is more than 1 px from its
    aperture centre is left out of the frame's ensemble, its own row flagged suspect,
    and counted; the target keeps its point from the other comparisons. Here the
    check star's catalogue place is 2.5 px off its star, comparison C4 sits 1.8 px
    off it (its star moved), every frame; tracking off, so that the apertures are
    the solution's own."""
    import dataclasses

    req, _ref = _turning_scene(tmp_path, deg_per_frame=0.0, n_frames=4, check_offset=(2.5, 0.0))
    req.params = dataclasses.replace(req.params, track_apertures=False)
    # C4's star 1.8 px from its catalogue place: patch the frames, not the set.
    for path in req.fits_paths:
        with fits.open(path, mode="update") as hdul:
            green_add = _raw_with_green_stars(
                [((31.8, 45.0), 8000.0)], sky=0.0, green_shape=(160, 160)
            )
            green_sub = _raw_with_green_stars(
                [((30.0, 45.0), 8000.0)], sky=0.0, green_shape=(160, 160)
            )
            data = hdul[0].data.astype(np.float32) + green_add - green_sub
            hdul[0].data = np.clip(data, 0, 65535).astype(np.uint16)
    result, _points = _run_batch(req)
    assert result.ok and result.frames_done == 4
    target = result.curves["T@clear"].points
    assert all(p.comps_used == 3 for p in target)  # C4 left out (4 before the fix)
    assert not any(p.suspect for p in target)
    assert all(p.suspect for p in result.curves["K@clear"].points)
    assert all(p.suspect for p in result.curves["C4@clear"].points)
    assert result.stars_off_centre == 8  # K and C4 on each of the 4 frames


def test_off_centre_anchors_leaving_fewer_than_3_make_a_re_solve_due_s69(
    tmp_path, monkeypatch
) -> None:
    """S69 (b): when off-centre anchors leave fewer than 3 centred, the lock is
    S56/S58's case: verified only near a fresh solution, else the frame is re-solved
    now, and without a solution its points are flagged suspect. Three of the five
    anchors (C1-C4, K) off: 2 centred."""
    import argos.workers.photometry_batch_worker as bw

    req, _ref = _turning_scene(tmp_path, deg_per_frame=0.0, n_frames=4)

    def three_off(green, wcs, stars, params, **kw):
        return {"auid:C1": 1.6, "auid:C2": 1.6, "auid:C3": 1.6}  # C4 and K: centred

    monkeypatch.setattr(bw, "centring_offsets", three_off, raising=False)
    result, _points = _run_batch(req)  # no solver
    assert result.frames_unverified == 4
    assert all(p.suspect for p in result.curves["T@clear"].points)

    (tmp_path / "solved").mkdir()
    req, ref = _turning_scene(tmp_path / "solved", deg_per_frame=0.0, n_frames=4)
    calls: list[int] = []
    req.solver = lambda green: calls.append(1) or _RotWCS(ref, 0.0)
    result, _points = _run_batch(req)
    assert len(calls) == 2  # frames 0 and 2; 1 and 3 are fresh (the previous frame's)
    assert result.frames_unverified == 0
    assert not any(p.suspect for p in result.curves["T@clear"].points)


def test_a_frame_whose_comparisons_are_all_off_centre_is_counted_s69(tmp_path, monkeypatch) -> None:
    """S69 (b), technical review: with every comparison off-centre the frame has no
    ensemble and its target no point; the epoch left the CSV with no count or note."""
    import dataclasses

    import argos.workers.photometry_batch_worker as bw

    req, _ref = _turning_scene(tmp_path, deg_per_frame=0.0, n_frames=3)
    req.params = dataclasses.replace(req.params, track_apertures=False)
    monkeypatch.setattr(
        bw,
        "centring_offsets",
        lambda green, wcs, stars, params, **kw: {f"auid:C{i}": 1.6 for i in (1, 2, 3, 4)},
    )
    result, _points = _run_batch(req)
    assert "T@clear" not in result.curves
    assert result.frames_no_target_point == 3


def test_the_tracker_and_lock_use_the_frames_own_gain_s70(tmp_path, monkeypatch) -> None:
    """S70 (S41's residue): the anchors (SNR >= 10) and the S43 lock check (SNR >= 5)
    used the request's e-/ADU while the measurement used the frame's; every SNR of
    the frame now uses the frame's EGAIN."""
    import argos.workers.photometry_batch_worker as bw

    req, _ref = _turning_scene(tmp_path, deg_per_frame=0.0, n_frames=3)
    for path in req.fits_paths:
        with fits.open(path, mode="update") as hdul:
            hdul[0].header["EGAIN"] = 0.42
    seen: dict[str, list[float]] = {"anchors": [], "lock": []}
    real_select, real_seen = bw.select_tracking_anchors, bw.anchors_seen
    monkeypatch.setattr(
        bw,
        "select_tracking_anchors",
        lambda g, w, c, params, **kw: seen["anchors"].append(params.egain)
        or real_select(g, w, c, params, **kw),
    )
    monkeypatch.setattr(
        bw,
        "anchors_seen",
        lambda g, w, s, params, **kw: seen["lock"].append(params.egain)
        or real_seen(g, w, s, params, **kw),
    )
    _run_batch(req)
    assert req.params.egain != pytest.approx(0.42)
    assert seen["anchors"] and all(g == pytest.approx(0.42) for g in seen["anchors"])
    assert seen["lock"] and all(g == pytest.approx(0.42) for g in seen["lock"])


def test_a_cancel_during_the_proper_motion_lookup_ends_the_run_before_frame_1_s77(
    _scene,
) -> None:
    """S77 amended (technical review): the lookup ran before the frame loop without the
    cancel: an archive that did not answer held the run at "measuring 0/N" for up to
    20 s per star. The lookup now gets the cancel, and a cancelled run measures no
    frame."""
    from dataclasses import replace as dc_replace

    req, _ = _scene
    tset = TargetSet(
        object_name=req.target_set.object_name,
        stars=[dc_replace(s, source="vsx") for s in req.target_set.stars],
    )
    worker = PhotometryBatchWorker(dc_replace(req, target_set=tset))
    seen = []

    def lookup(_ts, cancel=None):
        worker.cancel()  # the observer presses Cancel while the archive is asked
        seen.append(cancel())
        return []

    worker._req = dc_replace(worker._req, proper_motions=lookup)
    results = []
    worker.finished_batch.connect(results.append)
    worker.run()

    assert seen == [True]  # the lookup sees the cancel (no cancel argument before)
    assert results[0].frames_done == 0


def test_a_re_run_places_a_high_proper_motion_target_at_the_frames_date_s77(tmp_path) -> None:
    """S77: the re-run placed RR Lyr's aperture at its J2000.0 position, 6" (1.0 green
    px on the S30 Pro) from the star in 2026. With the Gaia DR3 proper motion from the
    request's lookup, every frame places it at its date: here 3.0 px (2"/px) from the
    J2000.0 position, the aperture now on the star. The set saved with the CSVs carries
    the motion."""
    from argos.core.catalog.gaia import GaiaStar
    from argos.core.imaging.platesolve import FrameWCS

    rr = dict(
        source_id="2125982599343482624",
        ra_deg=291.36564029422567,
        dec_deg=42.783488792618705,
        g_mag=7.62,
        pmra_mas_yr=-109.59872730873641,
        pmdec_mas_yr=-195.85073064533083,
    )
    scale = 2.0 / 3600.0
    wcs = FrameWCS(291.366, 42.784, 60.0, 60.0, (-scale, 0.0, 0.0, scale))
    ts = TargetSet(object_name="RR Lyr")
    ts.set_role(TargetStar(ROLE_TARGET, 291.36629, 42.78436, auid="000-BCG-719", source="vsx"))
    comps = [(291.3600, 42.7800), (291.3720, 42.7790), (291.3620, 42.7905)]
    for i, (ra, dec) in enumerate(comps):
        ts.set_role(TargetStar(ROLE_COMPARISON, ra, dec, auid=f"C{i}", mags={"V": 8.0}))
    moved = ts.stars[0]
    probe = TargetSet(object_name="RR Lyr", stars=[moved])
    probe.backfill_proper_motions([GaiaStar(**rr)])
    jd = 2461309.337  # 2026-09-25T20:05 UTC
    star_now = probe.at_jd(jd).stars[0]
    tx, ty = (float(v) for v in wcs.world_to_pixel_deg(star_now.ra_deg, star_now.dec_deg))
    jx, jy = (float(v) for v in wcs.world_to_pixel_deg(291.36629, 42.78436))
    assert 2.8 < math.hypot(tx - jx, ty - jy) < 3.2
    stars = [((tx, ty), 20000.0)] + [
        (tuple(float(v) for v in wcs.world_to_pixel_deg(ra, dec)), 9000.0) for ra, dec in comps
    ]
    paths = []
    for i in range(3):
        raw = _raw_with_green_stars(stars, green_shape=(120, 120))
        p = tmp_path / f"rr_{i}.fit"
        _write_fits(p, raw, f"2026-09-25T20:0{5 + i}:00")
        paths.append(p)
    req = BatchRequest(
        fits_paths=paths,
        wcs=wcs,
        target_set=ts,
        params=PhotometryParams.from_config(lambda k, d: d),
        out_dir=tmp_path / "out",
        object_name="RR Lyr",
        proper_motions=lambda _ts: [GaiaStar(**rr)],
    )
    result, _points = _run_batch(req)
    assert result.ok and result.frames_done == 3
    records = [
        json.loads(line) for line in next((tmp_path / "out").glob("*_diagnostics.jsonl")).open()
    ]
    placed = [
        (r["x"], r["y"]) for r in records if r["kind"] == "star" and r.get("role") == "target"
    ]
    assert len(placed) == 3
    for x, y in placed:
        assert math.hypot(x - tx, y - ty) < 0.05  # 3.0 px off before (the J2000.0 position)
    saved = TargetSet.load(tmp_path / "out" / "targets.json")
    assert saved.by_role(ROLE_TARGET)[0].pm_source == "Gaia DR3 2125982599343482624"
    assert ts.stars[0].pm_source is None  # the request's set is never changed
