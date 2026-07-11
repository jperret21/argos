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


class _FakeRefWCS:
    """Maps (ra_deg, dec_deg) → a preset green-px (x, y)."""

    def __init__(self, mapping):
        self._m = mapping

    def world_to_pixel_deg(self, ra_deg, dec_deg):
        return self._m[(ra_deg, dec_deg)]
