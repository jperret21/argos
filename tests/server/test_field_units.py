"""Wave 4 units: frame px convention, frame WCS, grid, candidates, tracking.

No server: the conversions and the PROPOSAL §7 candidate fields are checked
against hand-computed values and against the core functions they wrap.
"""

from __future__ import annotations

import math
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from argos.core.catalog.aavso import Band, ComparisonStar, VariableStar
from argos.core.catalog.gaia import GaiaStar
from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.astrometry_session import project_points
from argos.core.imaging.metrics import measure_star_at
from argos.core.imaging.platesolve import FrameWCS, SolveSettings, _build_command, wcs_grid
from argos.server import field_catalog as fc
from argos.server.field_solve import (
    SolveCancelled,
    frame_wcs_record,
    grid_record,
    header_hint,
    solve_green,
    to_frame,
    to_green,
)

SCALE_GREEN = 7.35 / 3600.0  # deg per green px
GREEN_SHAPE = (300, 400)  # h, w


def make_wcs(rotation_deg: float = 0.0) -> FrameWCS:
    c, s = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
    cd = (-SCALE_GREEN * c, SCALE_GREEN * s, SCALE_GREEN * s, SCALE_GREEN * c)
    return FrameWCS(291.366, 42.784, 200.5, 150.5, cd)


def gaussian_frame(shape, stars, sigma=2.5, sky=500.0, seed=1):
    """A raw frame (frame px) with Gaussian stars ``(x, y, peak)``."""
    rng = np.random.default_rng(seed)
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.full(shape, sky, dtype=np.float64)
    for x, y, peak in stars:
        img += peak * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2))
    img += rng.normal(0.0, 3.0, shape)
    return np.clip(img, 0, 65535).astype(np.uint16)


# -- frame px convention (protocol.md "Positions: frame pixels") -------------------


def test_to_frame_and_back():
    assert to_frame(0.0, 0.0) == (0.5, 0.5)
    assert to_frame(10.25, 3.0) == (21.0, 6.5)
    assert to_green(*to_frame(123.4, 56.7)) == pytest.approx((123.4, 56.7))


@pytest.mark.parametrize("x0, y0", [(101.3, 77.8), (60.0, 61.0), (140.7, 40.2)])
def test_green_centroid_maps_to_the_frame_position(x0, y0):
    """A star at frame (x0, y0) is measured on the green plane at to_green(x0, y0)."""
    raw = gaussian_frame((160, 200), [(x0, y0, 20000.0)], sigma=3.0)
    gx, gy = to_green(x0, y0)
    meas = measure_star_at(raw, gx, gy, 5)
    assert meas is not None
    fx, fy = to_frame(meas.x, meas.y)
    assert fx == pytest.approx(x0, abs=0.15)
    assert fy == pytest.approx(y0, abs=0.15)


@pytest.mark.parametrize("rotation", [0.0, 37.0, -177.0])
def test_frame_wcs_record_projects_like_the_green_solution(rotation):
    from astropy.wcs import WCS

    green = make_wcs(rotation)
    record = frame_wcs_record(green, GREEN_SHAPE)
    assert record["frame_shape"] == [600, 800]
    frame = WCS(naxis=2)
    frame.wcs.ctype = record["ctype"]
    frame.wcs.crval = record["crval"]
    frame.wcs.crpix = record["crpix"]
    frame.wcs.cd = record["cd"]
    for ra, dec in [(291.366, 42.784), (291.30, 42.70), (291.45, 42.85)]:
        gx, gy = green.world_to_pixel_deg(ra, dec)
        fx, fy = frame.wcs_world2pix(ra, dec, 0)  # numpy convention: 0-based
        assert float(fx) == pytest.approx(2 * float(gx) + 0.5, abs=1e-6)
        assert float(fy) == pytest.approx(2 * float(gy) + 0.5, abs=1e-6)


def test_grid_record_splits_lines_and_converts_labels():
    wcs = make_wcs(12.0)
    overlay = wcs_grid(wcs, GREEN_SHAPE, target_radec=(291.366 / 15.0, 42.784))
    grid = grid_record(overlay)
    assert grid["lines"] and all(len(seg) > 1 for seg in grid["lines"])
    for seg in grid["lines"]:
        for x, y in seg:
            assert -10 <= x <= 810 and -10 <= y <= 610
    axes = {label["axis"] for label in grid["labels"]}
    assert axes <= {"ra", "dec"} and axes
    cx, cy = to_frame(*overlay.center)
    assert grid["centre"]["x"] == pytest.approx(cx, abs=0.01)


def test_header_hint_reads_objctra_only():
    header = {"OBJCTRA": "19 25 26.66", "OBJCTDEC": "+42 47 07.3", "RA": 19.4}
    ra, dec = header_hint(header)
    assert ra == pytest.approx(19 + 25 / 60 + 26.66 / 3600)
    assert dec == pytest.approx(42 + 47 / 60 + 7.3 / 3600)
    assert header_hint({"OBJCTRA": "-01 30 00", "OBJCTDEC": "-12 30 00"}) is None  # RA < 0
    assert header_hint({"OBJCTDEC": "-12 30 00"}) is None
    _, dec = header_hint({"OBJCTRA": "1:30:00", "OBJCTDEC": "-12:30:00"})
    assert dec == pytest.approx(-12.5)


# -- ASTAP: the S24 command and cancel ---------------------------------------------


def test_the_command_keeps_the_database_set_with_its_folder(tmp_path):
    """S24: a database folder never drops the chosen set (platesolve.py:306-319)."""
    settings = SolveSettings(database="D50", database_dir=str(tmp_path), ra_hint_hours=19.4)
    cmd = _build_command("/x/astap_cli", tmp_path / "solve.fits", settings)
    i = cmd.index("-D")
    assert cmd[i + 1] == "D50" and cmd[cmd.index("-d") + 1] == str(tmp_path)


def test_a_missing_astap_is_a_failed_solve(tmp_path):
    settings = SolveSettings(astap_path=str(tmp_path / "none"))
    result = solve_green(np.zeros((300, 300), np.uint16), settings, threading.Event())
    if result.solved:  # pragma: no cover - an ASTAP on PATH answered
        pytest.skip("an ASTAP binary is installed; the missing-binary path is not reachable")
    assert not result.solved


def test_cancel_kills_the_process(tmp_path):
    script = tmp_path / "astap"
    script.write_text("#!/bin/sh\nsleep 30\n")
    script.chmod(0o755)
    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    settings = SolveSettings(astap_path=str(script), database_dir=str(tmp_path), timeout_s=60)
    import time

    t0 = time.monotonic()
    with pytest.raises(SolveCancelled):
        solve_green(np.zeros((300, 300), np.uint16), settings, cancel)
    assert time.monotonic() - t0 < 3.0


# -- candidates: b_minus_v and neighbours_in_aperture (PROPOSAL §7) --------------


def comp(auid, ra, dec, v=None, b=None):
    bands = tuple(Band(name, mag) for name, mag in (("V", v), ("B", b)) if mag is not None)
    return ComparisonStar(
        auid=auid, ra_deg=ra, dec_deg=dec, label="110", bands=bands, chart_id="X1"
    )


def sky(wcs, gx, gy):
    ra, dec = wcs.pixel_to_world_deg(gx, gy)
    return float(ra), float(dec)


def test_b_minus_v_needs_both_bands():
    assert fc.b_minus_v(comp("A", 1, 1, v=11.0, b=11.62)) == pytest.approx(0.62)
    assert fc.b_minus_v(comp("A", 1, 1, v=11.0)) is None
    assert fc.b_minus_v(comp("A", 1, 1, b=11.0)) is None


def test_neighbours_in_aperture_by_hand():
    """Aperture 4 green px; the counterpart (0.5″ away) is the candidate itself."""
    wcs = make_wcs()
    cx, cy = 200.0, 150.0
    c_ra, c_dec = sky(wcs, cx, cy)
    candidate = comp("000-AAA-001", c_ra, c_dec, v=11.0, b=11.5)
    stars = []

    def gaia(i, dx, dy, g):
        ra, dec = sky(wcs, cx + dx, cy + dy)
        stars.append(GaiaStar(source_id=str(i), ra_deg=ra, dec_deg=dec, g_mag=g))

    gaia(1, 0.05, 0.0, 10.9)  # the counterpart, 0.37″ away: excluded
    gaia(2, 2.0, 0.0, 12.0)  # inside, 1.1 mag fainter: counts
    gaia(3, 0.0, -3.9, 13.95)  # inside, 3.05 mag fainter than G 10.9: ignored
    gaia(4, 3.0, 0.0, 14.5)  # inside but 3.6 mag fainter: ignored
    gaia(5, 4.5, 0.0, 11.0)  # outside the aperture: ignored
    gaia(6, -2.0, 2.0, None)  # inside, no G: counts (no magnitude to compare)
    green = project_points(wcs, GREEN_SHAPE, ((s.ra_deg, s.dec_deg) for s in stars))
    count = fc.neighbours_in_aperture(candidate, (cx, cy), stars, green, 4.0, depth_g=18.0)
    assert count == 2  # stars 2 and 6
    # Without a counterpart the VSP V (11.0) is the reference: G ≤ 14.0, star 3 counts.
    assert (
        fc.neighbours_in_aperture(candidate, (cx, cy), stars[1:], green[1:], 4.0, depth_g=18.0) == 3
    )
    assert fc.neighbours_in_aperture(candidate, (cx, cy), [], [], 4.0, depth_g=18.0) is None
    # A held list complete only to G 13.5 cannot state what lies at G ≤ 13.9.
    assert fc.neighbours_in_aperture(candidate, (cx, cy), stars, green, 4.0, depth_g=13.5) is None
    assert fc.neighbours_in_aperture(candidate, (cx, cy), stars, green, 4.0) is None


def test_the_counterpart_is_matched_with_the_seeing_and_the_magnitude():
    """A star is never its own neighbour (the science review's 000-BJW-666)."""
    wcs = make_wcs()  # 7.35″ per green px
    cx, cy = 200.0, 150.0
    candidate = comp("000-BJW-666", *sky(wcs, cx, cy), v=7.90, b=8.6)
    own_ra, own_dec = sky(wcs, cx + 0.7, cy)  # 5.1″ away, G 7.70: its counterpart
    near_ra, near_dec = sky(wcs, cx - 0.3, cy)  # within 1 frame px: the candidate itself
    far_ra, far_dec = sky(wcs, cx, cy + 0.7)  # 5.1″ but 2.5 mag off V: a neighbour
    stars = [
        GaiaStar(source_id="own", ra_deg=own_ra, dec_deg=own_dec, g_mag=7.70),
        GaiaStar(source_id="self", ra_deg=near_ra, dec_deg=near_dec, g_mag=9.9),
        GaiaStar(source_id="other", ra_deg=far_ra, dec_deg=far_dec, g_mag=10.4),
    ]
    green = project_points(wcs, GREEN_SHAPE, ((s.ra_deg, s.dec_deg) for s in stars))
    args = (candidate, (cx, cy), stars, green, 4.0)
    # A 3″ window misses the counterpart (V is the reference): "own" and "other" count.
    assert fc.neighbours_in_aperture(*args, depth_g=12.0) == 2
    # max(3″, FWHM/2) with a 12″ FWHM finds it; "other" is 2.5 mag off V: a neighbour.
    assert fc.neighbours_in_aperture(*args, depth_g=12.0, counterpart_arcsec=6.0) == 1


def test_gaia_depth_is_the_faintest_source_when_the_budget_truncated_the_list():
    stars = [GaiaStar(source_id=str(i), ra_deg=0, dec_deg=0, g_mag=5.3 + i) for i in range(5)]
    full = fc.CatalogResult(field_stars=stars, field_star_limit=5, field_star_mag_limit=14.0)
    assert fc.gaia_depth(full) == pytest.approx(9.3)
    room = fc.CatalogResult(field_stars=stars, field_star_limit=10, field_star_mag_limit=14.0)
    assert fc.gaia_depth(room) == 14.0
    assert fc.gaia_depth(fc.CatalogResult()) is None


def test_candidates_rows():
    wcs = make_wcs()
    a = comp("000-AAA-001", *sky(wcs, 200.0, 150.0), v=11.0, b=11.62)
    b = comp("000-AAA-002", *sky(wcs, 100.0, 50.0), v=12.0)
    off = comp("000-AAA-003", *sky(wcs, -500.0, 50.0), v=12.0, b=12.4)
    result = fc.CatalogResult(comparisons=[a, b, off])
    ctx = fc.FieldContext(
        wcs=wcs, green_shape=GREEN_SHAPE, detected=[(200.2, 150.1)], result=result
    )
    target = TargetStar(role="target", ra_deg=a.ra_deg + 0.01, dec_deg=a.dec_deg, name="T", mags={})
    tset = TargetSet("T", [target, TargetStar(role="comparison", **_args(b))])
    rows = fc.candidates(
        ctx, tset, aperture_green_px=4.0, quality=None, measured_seq=None, target_b_minus_v=0.5
    )
    assert [r["auid"] for r in rows] == ["000-AAA-001", "000-AAA-002"]  # off-frame dropped
    first, second = rows
    assert first["b_minus_v"] == pytest.approx(0.62)
    assert first["delta_b_minus_v"] == pytest.approx(0.12)
    assert first["neighbours_in_aperture"] is None  # no Gaia sources fetched
    assert (first["x"], first["y"]) == pytest.approx(to_frame(200.0, 150.0), abs=0.01)
    assert first["detected"] is True and second["detected"] is False
    assert second["role"] == "comparison" and first["role"] is None
    assert second["b_minus_v"] is None and second["delta_b_minus_v"] is None
    expected_sep = fc.separation_arcmin(target.ra_deg, target.dec_deg, a.ra_deg, a.dec_deg)
    assert first["sep_arcmin"] == pytest.approx(expected_sep)
    assert first["pending_star"]["mags"] == {"V": 11.0, "B": 11.62}
    assert first["vsx"] is None


def test_a_candidate_listed_by_vsx_carries_it():
    wcs = make_wcs()
    a = comp("000-BCG-953", *sky(wcs, 200.0, 150.0), v=7.85, b=8.9)
    nsv = VariableStar(
        name="NSV 24798",
        ra_deg=a.ra_deg,
        dec_deg=a.dec_deg + 0.3 / 3600.0,
        var_type="VAR",
        category="Suspected",
        max_mag="7.82 Hp",
        min_mag="7.88 Hp",
    )
    result = fc.CatalogResult(comparisons=[a], variables=[nsv])
    ctx = fc.FieldContext(wcs=wcs, green_shape=GREEN_SHAPE, detected=[], result=result)
    (row,) = fc.candidates(
        ctx,
        TargetSet("T", []),
        aperture_green_px=4.0,
        quality=None,
        measured_seq=None,
        target_b_minus_v=None,
    )
    assert row["vsx"]["name"] == "NSV 24798" and row["vsx"]["suspected"] is True
    assert row["vsx"]["sep_arcsec"] == pytest.approx(0.3, abs=0.05)


def _args(c):
    return dict(
        ra_deg=c.ra_deg,
        dec_deg=c.dec_deg,
        auid=c.auid,
        name=c.auid,
        source="vsp",
        mags={x.band: x.mag for x in c.bands},
        chart_id=c.chart_id,
    )


# -- layers: positions through the core projection --------------------------------


def test_layers_follow_the_core_projection_and_qt_rules():
    from argos.core.catalog.aavso import VariableStar
    from argos.core.catalog.field_objects import NamedFieldObject

    wcs = make_wcs()
    gaia = [
        GaiaStar("11", *sky(wcs, 50.0, 60.0), g_mag=12.0),
        GaiaStar("12", *sky(wcs, 300.0, 200.0), g_mag=19.5),  # fainter than the display limit
        GaiaStar("13", *sky(wcs, 302.0, 202.0), g_mag=13.0),
    ]
    named = [
        NamedFieldObject("HD 1", *sky(wcs, 50.0, 60.0), object_type="*"),  # on Gaia 11
        NamedFieldObject("NGC 1", *sky(wcs, 120.0, 220.0), object_type="Galaxy"),
        NamedFieldObject("Gaia DR3 99", *sky(wcs, 10.0, 10.0), object_type="*"),
    ]
    variables = [
        VariableStar("RR Lyr", *sky(wcs, 200.0, 150.0), auid="000-BCD-123", var_type="RRAB")
    ]
    result = fc.CatalogResult(variables=variables, field_stars=gaia, named_objects=named)
    ctx = fc.FieldContext(wcs=wcs, green_shape=GREEN_SHAPE, detected=[], result=result)
    cfg = {
        "catalog.show_essential_objects": False,
        "catalog.show_cached_exoplanets": False,
    }.get
    projection = fc.project_field(
        ctx, lambda k, d: cfg(k, d), TargetSet("RR Lyr"), display_mag_limit=18.0
    )
    layers = projection.layers
    stars = layers["stars"]
    # Gaia 11 carries the SIMBAD name (matched ≤ 3″); Gaia 12 is past the display limit;
    # Gaia 13 has no name; an unmatched SIMBAD star keeps its name as label (Qt 1593).
    labels = sorted(m["label"] for m in stars)
    assert labels == ["", "Gaia DR3 99", "HD 1"]
    by_id = {m["id"]: m for m in stars}
    expected = project_points(wcs, GREEN_SHAPE, [(gaia[0].ra_deg, gaia[0].dec_deg)])[0]
    assert (by_id["gaia:0"]["x"], by_id["gaia:0"]["y"]) == pytest.approx(
        to_frame(*expected), abs=0.01
    )
    assert "gaia:1" not in by_id
    assert [m["label"] for m in layers["galaxies"]] == ["NGC 1"]
    var = layers["variables"][0]
    assert var["key"] == "auid:000-BCD-123" and var["tooltip"].startswith("Variable star\nRR Lyr")
    assert projection.counts["variables"] == 1


# -- tracking (A48): the rigid transform in frame px ------------------------------


def test_tracker_transform_in_frame_px():
    from argos.core.imaging.green import green_plane
    from argos.core.photometry.tracking import ApertureTracker

    stars = [(60.0, 50.0, 15000), (300.0, 80.0, 12000), (150.0, 250.0, 18000), (330, 260, 9000)]
    ref = gaussian_frame((320, 400), stars)
    shift = (3.0, -2.0)  # frame px
    moved = gaussian_frame((320, 400), [(x + shift[0], y + shift[1], p) for x, y, p in stars])
    anchors = [to_green(x, y) for x, y, _ in stars]
    tracker = ApertureTracker(anchors, frame_center=(100.0, 80.0), search_r=8.0)
    tracker.update(green_plane(ref), allow_rotation=False)
    tracker.update(green_plane(moved), allow_rotation=False)
    t = tracker.transform
    assert 2.0 * t.tx == pytest.approx(shift[0], abs=0.25)
    assert 2.0 * t.ty == pytest.approx(shift[1], abs=0.25)


def test_selection_rows_target_card():
    from argos.server.field import _catalogue_card

    star = TargetStar(
        role="comparison",
        ra_deg=291.0,
        dec_deg=42.0,
        auid="000-X",
        name="000-X",
        source="vsp",
        mags={"V": 11.234},
    )
    hub = SimpleNamespace()
    title, rows, pending = _catalogue_card("target", star, hub, TargetSet())
    assert title == "Target · 000-X"
    assert {"key": "Magnitudes", "value": "V 11.234"} in rows
    assert pending["ra_deg"] == 291.0 and pending["source"] == "vsp"


def test_frame_measurer_gives_the_core_measurement():
    """The batched measurement is ``measure_star_at``, number for number."""
    from argos.server.field_measure import FrameMeasurer

    stars = [(40.0, 30.0, 12000), (120.3, 70.6, 30000), (150.0, 20.0, 800)]
    raw = gaussian_frame((120, 180), stars, sigma=2.2)
    measurer = FrameMeasurer(raw)
    for x, y, _ in stars + [(90.0, 90.0, 0)]:
        gx, gy = to_green(x, y)
        for radius, search in ((5, None), (4, 3), (7, 2)):
            assert measurer.measure_star_at(gx, gy, radius, search) == measure_star_at(
                raw, gx, gy, radius, search
            )


# -- the web tracker (field_track) ----------------------------------------------------


def _green(frame: np.ndarray) -> np.ndarray:
    from argos.core.imaging.green import green_plane

    return green_plane(frame)


def test_one_window_on_another_star_is_not_a_lock():
    """With 3+ anchors, an update needs two anchors that agree with the reference."""
    from argos.server.field_track import FieldTracker, consistent_pairs

    refs = [(10.0, 10.0), (60.0, 15.0), (30.0, 50.0)]
    good = [(x + 2.0, y - 1.0) for x, y in refs]
    assert consistent_pairs(refs, good) == [0, 1, 2]
    wrong = [good[0], (good[1][0] + 6.0, good[1][1]), good[2]]
    assert consistent_pairs(refs, wrong) == [0, 2]
    # Only one star left in the frame: refused (lost), the pose is kept.
    stars = [(2 * x + 0.5, 2 * y + 0.5, 15000) for x, y in refs]
    reference = gaussian_frame((140, 180), stars, sigma=2.0)
    tracker = FieldTracker(refs, (45.0, 35.0), 6.0, reference_green=_green(reference))
    alone = gaussian_frame((140, 180), stars[:1], sigma=2.0, seed=2)
    assert tracker.update(_green(alone)) == 0
    assert tracker.health == "lost" and tracker.frames_lost == 1
    assert tracker.update(_green(reference)) == 3 and tracker.health == "ok"


def test_the_vote_finds_a_jump_beyond_the_windows():
    from argos.core.photometry.tracking import RigidTransform
    from argos.server.field_track import vote_transform

    rng = np.random.default_rng(4)
    ref = [(float(x), float(y), float(f)) for x, y, f in rng.uniform(0, 500, (40, 3))]
    cur = [(x + 37.5, y - 21.25, f) for x, y, f in ref[5:]] + [(5.0, 5.0, 900.0)]
    found = vote_transform(ref, cur, RigidTransform.identity(250.0, 250.0))
    assert found is not None
    transform, matches = found
    assert matches >= 30
    assert (transform.tx, transform.ty) == pytest.approx((37.5, -21.25), abs=0.05)
    assert vote_transform(ref[:3], cur[:3], RigidTransform.identity(0, 0)) is None
