"""Aperture tracking — rigid fit, centroid refinement, rotating-field lock.

Synthetic Gaussian star fields only (Qt-free, no hardware): the tracker must
follow a field that slowly rotates around the frame centre — the alt-az
field-rotation case a single reference solve cannot handle.
"""

from __future__ import annotations

import math

import numpy as np

from argos.core.photometry.tracking import (
    ApertureTracker,
    RigidTransform,
    TrackedWCS,
    fit_rigid,
    fit_translation,
    refine_centroid,
)


def _rotate(x, y, cx, cy, deg):
    a = math.radians(deg)
    dx, dy = x - cx, y - cy
    return (
        cx + math.cos(a) * dx - math.sin(a) * dy,
        cy + math.sin(a) * dx + math.cos(a) * dy,
    )


def _green_with_stars(positions, peak=8000.0, sky=200.0, sigma=1.5, shape=(120, 120)):
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    g = np.full(shape, sky, dtype=np.float32)
    for cx, cy in positions:
        g += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2))
    return g


# ── refine_centroid ─────────────────────────────────────────────────────────


def test_refine_centroid_finds_offset_star() -> None:
    green = _green_with_stars([(42.3, 57.8)])
    got = refine_centroid(green, 45.0, 55.0, r=6.0)
    assert got is not None
    assert abs(got[0] - 42.3) < 0.2 and abs(got[1] - 57.8) < 0.2


def test_refine_centroid_empty_sky_is_none() -> None:
    green = np.full((60, 60), 200.0, dtype=np.float32)
    assert refine_centroid(green, 30.0, 30.0, r=6.0) is None


def test_refine_centroid_off_frame_is_none() -> None:
    green = _green_with_stars([(5.0, 5.0)])
    assert refine_centroid(green, 2.0, 2.0, r=6.0) is None


# ── fit_rigid ───────────────────────────────────────────────────────────────


def test_fit_rigid_recovers_rotation_and_shift() -> None:
    cx = cy = 50.0
    src = [(20.0, 20.0), (80.0, 25.0), (50.0, 85.0), (75.0, 70.0)]
    dst = [(x + 3.0, y - 2.0) for x, y in (_rotate(sx, sy, cx, cy, 4.0) for sx, sy in src)]
    t = fit_rigid(src, dst, cx, cy)
    assert abs(t.rotation_deg - 4.0) < 1e-6
    assert abs(t.tx - 3.0) < 1e-6 and abs(t.ty + 2.0) < 1e-6
    for (sx, sy), (dx, dy) in zip(src, dst):
        ax, ay = t.apply(sx, sy)
        assert abs(ax - dx) < 1e-6 and abs(ay - dy) < 1e-6


def test_fit_rigid_single_pair_is_translation_only() -> None:
    t = fit_rigid([(10.0, 10.0)], [(12.0, 9.0)], 50.0, 50.0)
    assert t.rotation_deg == 0.0
    assert abs(t.tx - 2.0) < 1e-9 and abs(t.ty + 1.0) < 1e-9


def test_fit_translation_preserves_eq_drift_without_rotation() -> None:
    src = [(20.0, 20.0), (80.0, 25.0), (50.0, 85.0)]
    dst = [(x + 3.0, y - 2.0) for x, y in src]

    t = fit_translation(src, dst, 50.0, 50.0)

    assert t.rotation_deg == 0.0
    assert abs(t.tx - 3.0) < 1e-9 and abs(t.ty + 2.0) < 1e-9


# ── ApertureTracker over a rotating field ───────────────────────────────────

_ANCHORS = [(30.0, 30.0), (90.0, 35.0), (60.0, 95.0)]
_CENTER = (60.0, 60.0)


def test_tracker_follows_slow_field_rotation() -> None:
    total_deg = 8.0
    n_frames = 20
    tracker = ApertureTracker(_ANCHORS, _CENTER, search_r=6.0)
    for i in range(1, n_frames + 1):
        ang = total_deg * i / n_frames
        pos = [_rotate(x, y, *_CENTER, ang) for x, y in _ANCHORS]
        assert tracker.update(_green_with_stars(pos)) == len(_ANCHORS)
    assert abs(tracker.transform.rotation_deg - total_deg) < 0.1

    # A star far from the anchors is placed by the same transform.
    wcs = TrackedWCS(_FakeRefWCS({(1.0, 1.0): (95.0, 90.0)}), tracker)
    expect = _rotate(95.0, 90.0, *_CENTER, total_deg)
    got = wcs.world_to_pixel_deg(1.0, 1.0)
    assert abs(got[0] - expect[0]) < 0.3 and abs(got[1] - expect[1]) < 0.3


def test_tracker_survives_a_blank_frame() -> None:
    tracker = ApertureTracker(_ANCHORS, _CENTER, search_r=6.0)
    pos = [_rotate(x, y, *_CENTER, 2.0) for x, y in _ANCHORS]
    assert tracker.update(_green_with_stars(pos)) == 3
    before = tracker.transform

    # Clouds: no star anywhere. Transform must be kept, not reset.
    assert tracker.update(np.full((120, 120), 200.0, dtype=np.float32)) == 0
    assert tracker.frames_lost == 1
    assert tracker.transform == before

    # Sky clears on the next frame — re-acquires from where it left off.
    pos = [_rotate(x, y, *_CENTER, 2.5) for x, y in _ANCHORS]
    assert tracker.update(_green_with_stars(pos)) == 3
    assert abs(tracker.transform.rotation_deg - 2.5) < 0.1


def test_identity_transform_is_a_no_op() -> None:
    t = RigidTransform.identity(60.0, 60.0)
    x, y = t.apply(12.3, 45.6)
    assert abs(x - 12.3) < 1e-9 and abs(y - 45.6) < 1e-9
    assert t.rotation_deg == 0.0 and t.shift_px == 0.0


def test_rigid_transform_inverse_round_trips() -> None:
    t = RigidTransform(theta_rad=math.radians(4.0), tx=3.0, ty=-2.0, cx=60.0, cy=60.0)
    x, y = t.apply(95.0, 90.0)
    rx, ry = t.invert(x, y)
    assert abs(rx - 95.0) < 1e-9 and abs(ry - 90.0) < 1e-9


class _FakeRefWCS:
    """Maps (ra_deg, dec_deg) → a preset green-px (x, y)."""

    def __init__(self, mapping):
        self._m = mapping

    def world_to_pixel_deg(self, ra_deg, dec_deg):
        return self._m[(ra_deg, dec_deg)]

    def pixel_to_radec(self, x, y):
        for radec, pixel in self._m.items():
            if abs(x - pixel[0]) < 1e-8 and abs(y - pixel[1]) < 1e-8:
                return radec
        raise KeyError((x, y))


def test_project_points_through_tracked_wcs_follows_the_field() -> None:
    """W1 (field bug 2026-07-11): catalog markers are projected with
    ``project_points`` — through a TrackedWCS they must land on the rotated
    star positions, not freeze at the reference-solve position."""
    from argos.core.imaging.astrometry_session import project_points

    tracker = ApertureTracker(_ANCHORS, _CENTER, search_r=6.0)
    ang = 3.0
    pos = [_rotate(x, y, *_CENTER, ang) for x, y in _ANCHORS]
    assert tracker.update(_green_with_stars(pos)) == len(_ANCHORS)

    ref = _FakeRefWCS({(1.0, 1.0): (95.0, 90.0), (2.0, 2.0): (30.0, 40.0)})
    got = project_points(TrackedWCS(ref, tracker), (120, 120), [(1.0, 1.0), (2.0, 2.0)])
    for g, (rx, ry) in zip(got, [(95.0, 90.0), (30.0, 40.0)]):
        ex, ey = _rotate(rx, ry, *_CENTER, ang)
        assert g is not None
        assert abs(g[0] - ex) < 0.3 and abs(g[1] - ey) < 0.3


def test_tracked_wcs_inverse_uses_reference_coordinates() -> None:
    tracker = ApertureTracker(_ANCHORS, _CENTER, search_r=6.0)
    assert tracker.update(_green_with_stars([(x + 3.0, y - 2.0) for x, y in _ANCHORS])) == 3
    ref = _FakeRefWCS({(1.0, 1.0): (95.0, 90.0)})
    wcs = TrackedWCS(ref, tracker)

    current_x, current_y = wcs.world_to_pixel_deg(1.0, 1.0)

    assert wcs.pixel_to_radec(current_x, current_y) == (1.0, 1.0)


def test_tracker_rejects_a_bad_anchor() -> None:
    """P8: one anchor locked on the wrong thing (hot pixel, neighbour) must
    not skew the transform when two clean anchors plus one more agree."""
    anchors = [(30.0, 30.0), (90.0, 35.0), (60.0, 95.0), (95.0, 85.0)]
    # Wide search window: the displaced star is measured where it really is,
    # not truncated by the window edge.
    tracker = ApertureTracker(anchors, _CENTER, search_r=10.0)

    ang = 1.5
    pos = [_rotate(x, y, *_CENTER, ang) for x, y in anchors]
    pos[3] = (pos[3][0] + 4.2, pos[3][1] - 4.2)  # 4th star displaced ~6 px
    assert tracker.update(_green_with_stars(pos)) == 3  # bad anchor dropped
    assert tracker.anchors_rejected == 1
    assert tracker.rejected_anchor == 3  # S69: which one, for the S56 anchor count
    assert abs(tracker.transform.rotation_deg - ang) < 0.2
    assert tracker.residual_px < 0.5


def test_tracker_keeps_all_clean_anchors() -> None:
    tracker = ApertureTracker(_ANCHORS, _CENTER, search_r=6.0)
    pos = [_rotate(x, y, *_CENTER, 1.0) for x, y in _ANCHORS]
    assert tracker.update(_green_with_stars(pos)) == 3
    assert tracker.anchors_rejected == 0
    assert tracker.residual_px < 0.3


def test_tracker_rejects_anchor_that_fades_to_noise() -> None:
    """A lost guide star must not be re-centred on a weak background feature."""
    anchors = [(30.0, 30.0), (90.0, 35.0), (60.0, 95.0), (95.0, 85.0)]
    tracker = ApertureTracker(anchors, _CENTER, search_r=8.0)
    assert tracker.update(_green_with_stars(anchors, peak=8000.0)) == 4

    angle = 1.0
    positions = [_rotate(x, y, *_CENTER, angle) for x, y in anchors]
    # The last source is replaced by a feature with 5% of its guide signal:
    # it remains centroidable but is not a reliable anchor.
    frame = _green_with_stars(positions[:3], peak=8000.0)
    frame += _green_with_stars([positions[3]], peak=400.0, sky=0.0)
    assert tracker.update(frame) == 3
    assert tracker.anchors_signal_rejected == 1
    assert abs(tracker.transform.rotation_deg - angle) < 0.2


# ── S69: the tracker on a fast-rotating alt-az field ─────────────────────────


def _noisy_field(positions, peaks, rng, *, shape=(420, 420), sky=1000.0, noise=20.0):
    """Stars of FWHM 2.2 green px (the owner's) on a sky with Gaussian noise."""
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    g = np.full(shape, sky, dtype=np.float32)
    for (cx, cy), peak in zip(positions, peaks):
        g += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 0.93**2))
    return g + rng.normal(0.0, noise, shape).astype(np.float32)


#: Six anchors 60-190 px from the pivot, peaks 380-2000 ADU over a noise of 20 (aperture
#: SNR about 10-55, the anchors' SNR >= 10, as XX Cyg 2026-09-07's comparisons).
_S69_CENTER = (210.0, 210.0)
_S69_ANCHORS = [
    (270.0, 210.0),
    (210.0, 100.0),
    (110.0, 260.0),
    (330.0, 330.0),
    (90.0, 90.0),
    (300.0, 60.0),
]
_S69_PEAKS = [2000.0, 900.0, 500.0, 400.0, 380.0, 600.0]


def test_the_tracker_keeps_up_with_a_field_rotating_0_7_deg_per_sub_s69() -> None:
    """S69: XX Cyg 2026-09-07 turned 0.7° per sub; the tracker, one centroid per window
    centred on its prediction, found 15.37° of ASTAP's 16.49°: the clipped sky noise
    and the truncated wings kept the centroid 30-80 % of the way to the window's
    centre, a lag of about 1° (here 1.7° after 24 subs on the code before the fix)."""
    rng = np.random.default_rng(69)
    tracker = ApertureTracker(_S69_ANCHORS, _S69_CENTER, search_r=15.0)
    worst = 0.0
    for i in range(1, 25):
        angle = -0.7 * i
        pos = [_rotate(x, y, *_S69_CENTER, angle) for x, y in _S69_ANCHORS]
        tracker.update(_noisy_field(pos, _S69_PEAKS, rng))
        assert tracker.anchors_used == len(_S69_ANCHORS)
        for ref, true in zip(_S69_ANCHORS, pos):
            fx, fy = tracker.transform.apply(*ref)
            worst = max(worst, math.hypot(fx - true[0], fy - true[1]))
    assert abs(tracker.transform.rotation_deg - angle) < 0.1
    assert worst < 0.5


def test_refine_centroid_finds_a_star_away_from_the_window_centre_s69() -> None:
    """S69: a star 9 px from the centre of a 15 px window, on a noisy sky, is found
    within 0.2 px (one centroid stopped 7.7 px short of it)."""
    rng = np.random.default_rng(7)
    green = _noisy_field([(219.0, 205.0)], [400.0], rng)
    got = refine_centroid(green, 210.0, 210.0, r=15.0)
    assert got is not None
    assert math.hypot(got[0] - 219.0, got[1] - 205.0) < 0.2


def test_refine_centroid_is_not_dragged_by_a_neighbour_7_px_away_s69() -> None:
    """S69: XX Cyg's check 000-BJV-169 has 000-BJV-173 (1.5 mag fainter) 6.9 green px
    away; the search window blends them (0.9 px off), the 4 px window does not."""
    rng = np.random.default_rng(8)
    green = _noisy_field([(200.0, 200.0), (204.9, 204.9)], [1600.0, 400.0], rng)
    got = refine_centroid(green, 201.0, 199.0, r=15.0)
    assert got is not None
    assert math.hypot(got[0] - 200.0, got[1] - 200.0) < 0.3


class _Params:
    """The PhotometryParams fields the S69 helpers read."""

    aperture_min_px = 4.0
    annulus_in_px = 8.0
    annulus_out_px = 12.0
    egain = 1.0
    read_noise_e = 1.5
    sat_adu = 60000.0
    black_adu = 0.0
    plane_pixels = 1

    def aperture_px(self, fwhm):
        return max(self.aperture_min_px, 2.5 * (fwhm or 3.0))


class _Star:
    def __init__(self, key, ra):
        self._key, self.ra_deg, self.dec_deg = key, ra, 0.0

    def key(self):
        return self._key


def test_centring_offsets_find_a_star_off_its_aperture_s69() -> None:
    """S69 (b): an aperture 2.5 px from its star is reported off-centre; one on its
    star, and one on a star too faint to tell (SNR < 5), are not."""
    from argos.core.photometry.tracking import centring_offsets, off_centre

    rng = np.random.default_rng(9)
    stars = [(100.0, 100.0), (300.0, 120.0), (200.0, 300.0)]
    green = _noisy_field(stars, [800.0, 800.0, 25.0], rng)
    wcs = _FakeRefWCS(
        {(1.0, 0.0): (100.2, 99.9), (2.0, 0.0): (302.0, 121.5), (3.0, 0.0): (202.0, 301.5)}
    )
    offsets = centring_offsets(
        green, wcs, [_Star("a", 1.0), _Star("b", 2.0), _Star("c", 3.0)], _Params(), fwhm=2.2
    )
    assert set(offsets) == {"a", "b"}  # "c" is not seen: not tested
    assert offsets["a"] < 0.4
    assert 2.0 < offsets["b"] < 3.0
    assert off_centre(offsets) == {"b"}


def test_a_faint_star_beside_a_brighter_one_is_centred_on_its_aperture_s69() -> None:
    """S69 (b): 000-BJV-173 (XX Cyg 2026-09-07) is 6.9 green px from 000-BJV-169, 4.9
    times brighter; its centroid, taken in the aperture radius, climbed onto 169 and
    the star was reported off-centre (and left out of the ensemble) on 7 of 24 frames
    while 0.03-0.20 px from its aperture centre. The centroid of a star with a
    neighbour is taken within 0.45 of their distance (here inf on the code before)."""
    from argos.core.photometry.tracking import centring_offsets, off_centre

    for seed in range(8):
        rng = np.random.default_rng(seed)
        green = _noisy_field([(200.0, 200.0), (204.9, 204.9)], [1600.0, 400.0], rng)
        wcs = _FakeRefWCS({(1.0, 0.0): (200.0, 200.0), (2.0, 0.0): (204.9, 204.9)})
        stars = [_Star("bright", 1.0), _Star("faint", 2.0)]
        offsets = centring_offsets(green, wcs, stars, _Params(), fwhm=2.2)
        assert offsets["faint"] < 0.5, seed
        assert offsets["bright"] < 0.5, seed
        assert not off_centre(offsets)


def test_an_uncatalogued_star_in_the_aperture_does_not_move_the_centroid_s69() -> None:
    """S69 (b): re-centred in the aperture radius, the window of a star near SNR 5
    wandered onto noise or a fainter star the set does not list (XX Cyg 2026-08-29
    000-BJV-178, frame 5: 2.68 px off for the centring test, 0.08 px for a Gaussian
    fit). Here a star half as bright 4.5 px away: 14 of 20 seeds flagged before; the
    centroid is now re-centred in 3 px."""
    from argos.core.photometry.tracking import centring_offsets

    for seed in range(8):
        rng = np.random.default_rng(seed)
        green = _noisy_field([(200.0, 200.0), (204.5, 200.0)], [300.0, 150.0], rng)
        wcs = _FakeRefWCS({(1.0, 0.0): (200.0, 200.0)})
        offsets = centring_offsets(green, wcs, [_Star("a", 1.0)], _Params(), fwhm=2.2, min_snr=0)
        assert offsets["a"] < 1.0, seed


def test_a_neighbour_outside_the_tested_stars_counts_too_s69() -> None:
    """S69 (b): the set's other stars (a target beside a comparison) are neighbours
    too (``neighbours``): the comparison's window stays clear of a target 4 times
    brighter 4.7 px away (alone, it ends on the target); two stars 3 px apart are
    blended: neither is tested."""
    from argos.core.photometry.tracking import centring_offsets

    rng = np.random.default_rng(11)
    green = _noisy_field([(200.0, 200.0), (204.7, 200.0)], [1600.0, 400.0], rng)
    wcs = _FakeRefWCS({(1.0, 0.0): (200.0, 200.0), (2.0, 0.0): (204.7, 200.0)})
    comp = _Star("comp", 2.0)
    target = _Star("target", 1.0)
    alone = centring_offsets(green, wcs, [comp], _Params(), fwhm=2.2)
    with_set = centring_offsets(green, wcs, [comp], _Params(), fwhm=2.2, neighbours=[target, comp])
    assert alone["comp"] > 1.0  # its window ends on the target, not in the set it tests
    assert with_set["comp"] < 0.5
    blended = _noisy_field([(300.0, 300.0), (303.0, 300.0)], [1600.0, 1600.0], rng)
    wcs = _FakeRefWCS({(1.0, 0.0): (300.0, 300.0), (2.0, 0.0): (303.0, 300.0)})
    stars = [_Star("a", 1.0), _Star("b", 2.0)]
    assert centring_offsets(blended, wcs, stars, _Params(), fwhm=2.2) == {}


def test_a_star_beside_a_brighter_one_is_no_anchor_s69() -> None:
    """S69: the tracker's window (15 px, re-centred until it converges) on 000-BJV-173
    ended on 000-BJV-169 every frame (7.0 px off); the fit spent its one rejection on
    it, so a second bad anchor broke the fit (XX Cyg 2026-09-07 sub _00020: 2.8 px).
    A candidate with a set star of at least a quarter of its flux within the search
    radius plus 8 px is no anchor; the brighter star of the pair stays one."""
    from argos.core.photometry.tracking import select_tracking_anchors

    rng = np.random.default_rng(12)
    positions = list(_S69_ANCHORS) + [(274.9, 214.9)]  # 6.9 px from the 2000-ADU anchor
    peaks = list(_S69_PEAKS) + [410.0]
    green = _noisy_field(positions, peaks, rng)
    wcs = _FakeRefWCS({(float(i), 0.0): xy for i, xy in enumerate(positions)})
    stars = [_Star(f"s{i}", float(i)) for i in range(len(positions))]
    params = _Params()
    params.egain = 10.0  # every anchor at SNR >= 10, the faint one too (its aperture
    # holds part of its neighbour's light)
    assert len(select_tracking_anchors(green, wcs, stars[6:], params)) == 1
    anchors = select_tracking_anchors(green, wcs, stars, params, max_anchors=7)
    keys = {star.key() for star in anchors}
    assert "s6" not in keys  # the faint one of the pair
    assert keys == {f"s{i}" for i in range(6)}
    # Its window from a 5 px prediction error ends on the brighter star (7 px off):
    # tracked on the selected anchors, no anchor is rejected over a turning field.
    tracker = ApertureTracker(
        [wcs.world_to_pixel_deg(s.ra_deg, 0.0) for s in anchors], _S69_CENTER, search_r=15.0
    )
    for i in range(1, 13):
        pos = [_rotate(x, y, *_S69_CENTER, -0.7 * i) for x, y in positions]
        tracker.update(_noisy_field(pos, peaks, rng))
        assert tracker.anchors_rejected == 0
        assert tracker.anchors_used == 6
    assert abs(tracker.transform.rotation_deg + 0.7 * 12) < 0.1


def test_a_re_solve_is_due_past_2_deg_of_rotation_and_retried_per_2_deg_s69() -> None:
    """S69 (a): due past 2° since the solution; after a failed attempt at 2.1°, the
    next one waits for 4.1° (a failing solver costs one attempt per 2°)."""
    from argos.core.photometry.tracking import rotation_resolve_due

    assert not rotation_resolve_due(1.9)
    assert rotation_resolve_due(-2.1)
    assert not rotation_resolve_due(-3.9, attempted_deg=-2.1)
    assert rotation_resolve_due(-4.2, attempted_deg=-2.1)
