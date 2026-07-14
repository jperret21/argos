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
    wcs = _FakeWCS(
        {
            (1.0, 1.0): (30.0, 30.0),  # target
            (2.0, 2.0): (10.0, 10.0),  # comp 1
            (3.0, 3.0): (50.0, 50.0),  # comp 2
        }
    )
    ts = TargetSet(object_name="X")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1", mags={"V": 11.0})
    )
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=3.0, dec_deg=3.0, auid="C2", mags={"V": 11.0})
    )

    results = measure_targets(green, wcs, ts, r_ap=6, r_in=8, r_out=12)
    by_auid = {r.star.auid: r for r in results}
    # One target + one leave-one-out vetting result per comparison.
    assert set(by_auid) == {"T", "C1", "C2"}
    r = by_auid["T"]
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


def test_check_star_is_calibrated_but_not_in_the_ensemble() -> None:
    """P2: the check star gets its own calibrated result (K curve) and its
    flux never contaminates the comparison ensemble."""
    from argos.core.catalog.targets import ROLE_CHECK

    tgt = ((30.0, 30.0), 20000.0)
    chk = ((45.0, 15.0), 12000.0)
    c1 = ((10.0, 10.0), 8000.0)
    c2 = ((50.0, 50.0), 8000.0)
    green = _green_with_stars([tgt, chk, c1, c2])
    wcs = _FakeWCS(
        {
            (1.0, 1.0): (30.0, 30.0),
            (4.0, 4.0): (45.0, 15.0),
            (2.0, 2.0): (10.0, 10.0),
            (3.0, 3.0): (50.0, 50.0),
        }
    )
    ts = TargetSet(object_name="X")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    ts.set_role(TargetStar(role=ROLE_CHECK, ra_deg=4.0, dec_deg=4.0, auid="K", mags={"V": 10.5}))
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1", mags={"V": 11.0})
    )
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=3.0, dec_deg=3.0, auid="C2", mags={"V": 11.0})
    )

    results = measure_targets(green, wcs, ts, r_ap=6, r_in=8, r_out=12)
    by_auid = {r.star.auid: r for r in results}
    # Target AND check, plus the comps' leave-one-out vetting results.
    assert set(by_auid) == {"T", "K", "C1", "C2"}

    k = by_auid["K"]
    assert k.diff is not None and k.diff.mag is not None
    # Calibrated against the 2 comps only (the check never calibrates itself).
    assert k.diff.comps_used == 2
    # 12000 ADU vs the comps' 8000 at V=11 → K reads brighter than 11 but
    # fainter than the 20000-ADU target.
    assert by_auid["T"].diff.mag < k.diff.mag < 11.0


def test_comparisons_get_leave_one_out_vetting_curves() -> None:
    """Each comp is calibrated against the ensemble MINUS itself — the
    standard vetting curve; a lone comp has nothing to be vetted against."""
    c1 = ((10.0, 10.0), 8000.0)
    c2 = ((50.0, 50.0), 8000.0)
    green = _green_with_stars([c1, c2])
    wcs = _FakeWCS({(2.0, 2.0): (10.0, 10.0), (3.0, 3.0): (50.0, 50.0)})
    ts = TargetSet(object_name="X")
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1", mags={"V": 11.0})
    )
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=3.0, dec_deg=3.0, auid="C2", mags={"V": 11.5})
    )

    results = measure_targets(green, wcs, ts, r_ap=6, r_in=8, r_out=12)
    by_auid = {r.star.auid: r for r in results}
    assert set(by_auid) == {"C1", "C2"}
    # C1 vetted against C2 only: equal flux but C2 is claimed 0.5 mag fainter,
    # so C1 comes out ~11.5 — the vetting curve exposes the inconsistency.
    c1r = by_auid["C1"]
    assert c1r.diff is not None and c1r.diff.comps_used == 1
    assert abs(c1r.diff.mag - 11.5) < 0.05
    # And C2 against C1's claimed 11.0 → ~11.0.
    assert abs(by_auid["C2"].diff.mag - 11.0) < 0.05

    # A lone comp yields no vetting result at all.
    ts.remove("auid:C2")
    lone = measure_targets(green, wcs, ts, r_ap=6, r_in=8, r_out=12)
    assert lone == []
