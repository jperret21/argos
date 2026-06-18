"""Tests for per-frame target-set measurement (Qt-free, no hardware)."""

from __future__ import annotations

import numpy as np

from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar
from argos.core.photometry.session import measure_targets


class _FakeWCS:
    """Maps each (ra_deg, dec_deg) to a preset green-px (x, y)."""

    def __init__(self, mapping):
        self._m = mapping

    def world_to_pixel_deg(self, ra_deg, dec_deg):
        return self._m[(ra_deg, dec_deg)]


def _green_with_stars(positions_peaks, sky=200.0, sigma=1.5, shape=(60, 60)):
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    g = np.full(shape, sky, dtype=np.float32)
    for (cx, cy), peak in positions_peaks:
        g += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2))
    return g


def test_measure_targets_calibrates_against_comps() -> None:
    # target brighter than the two comps; comps have known V mags.
    tgt = ((30.0, 30.0), 20000.0)
    c1 = ((10.0, 10.0), 8000.0)
    c2 = ((50.0, 50.0), 8000.0)
    green = _green_with_stars([tgt, c1, c2])
    wcs = _FakeWCS({
        (1.0, 1.0): (30.0, 30.0),  # target
        (2.0, 2.0): (10.0, 10.0),  # comp 1
        (3.0, 3.0): (50.0, 50.0),  # comp 2
    })
    ts = TargetSet(object_name="X")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    ts.set_role(TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1", mags={"V": 11.0}))
    ts.set_role(TargetStar(role=ROLE_COMPARISON, ra_deg=3.0, dec_deg=3.0, auid="C2", mags={"V": 11.0}))

    results = measure_targets(green, wcs, ts, r_ap=6, r_in=8, r_out=12)
    assert len(results) == 1  # one target
    r = results[0]
    assert r.diff is not None and r.diff.mag is not None
    assert r.diff.comps_used == 2 and r.diff.note == ""
    # The target is brighter than the comps (V=11) → it should read brighter.
    assert r.diff.mag < 11.0


def test_measure_targets_without_comps_is_provisional() -> None:
    green = _green_with_stars([((30.0, 30.0), 20000.0)])
    wcs = _FakeWCS({(1.0, 1.0): (30.0, 30.0)})
    ts = TargetSet()
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    r = measure_targets(green, wcs, ts, r_ap=6, r_in=8, r_out=12)[0]
    assert r.diff is not None and r.diff.mag is None  # no comps → uncalibrated
