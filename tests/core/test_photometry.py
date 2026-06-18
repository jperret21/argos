"""Tests for comparison-star ranking (differential photometry selection)."""

from __future__ import annotations

from argos.core.catalog import (
    Band,
    ComparisonStar,
    VariableStar,
    comparisons_for_variable,
    rank_comparisons,
    separation_arcmin,
)


def _comp(auid: str, ra: float, dec: float, v: float | None) -> ComparisonStar:
    bands = (Band("V", v),) if v is not None else ()
    return ComparisonStar(
        auid=auid, ra_deg=ra, dec_deg=dec, label=str(int((v or 0) * 10)), bands=bands
    )


def test_separation_arcmin() -> None:
    assert separation_arcmin(10.0, 20.0, 10.0, 20.0) == 0.0
    # 1° of declination = 60 arcmin.
    assert abs(separation_arcmin(10.0, 20.0, 10.0, 21.0) - 60.0) < 1e-6
    # 1 arcmin of RA at the equator ≈ 1 arcmin separation.
    assert abs(separation_arcmin(0.0, 0.0, 1.0 / 60.0, 0.0) - 1.0) < 1e-3


def test_rank_orders_by_separation() -> None:
    target_ra, target_dec = 83.8, -5.4
    far = _comp("FAR", 83.8, -5.0, 12.0)  # 0.4° away
    near = _comp("NEAR", 83.81, -5.40, 12.2)  # ~0.01° away
    mid = _comp("MID", 83.8, -5.25, 11.8)  # 0.15° away
    ranked = rank_comparisons(target_ra, target_dec, [far, near, mid])
    assert [s.star.auid for s in ranked] == ["NEAR", "MID", "FAR"]
    assert ranked[0].separation_arcmin < ranked[1].separation_arcmin < ranked[2].separation_arcmin


def test_rank_mag_tolerance_filters_and_reports_delta() -> None:
    target_ra, target_dec = 0.0, 0.0
    close_mag = _comp("CLOSE", 0.02, 0.0, 12.3)  # |12.3 - 12.0| = 0.3
    far_mag = _comp("FARMAG", 0.01, 0.0, 9.0)  # |9 - 12| = 3.0, dropped by tol
    no_band = _comp("NOBAND", 0.005, 0.0, None)  # unjudgeable in V → dropped under tol
    ranked = rank_comparisons(
        target_ra, target_dec, [close_mag, far_mag, no_band], target_mag=12.0, mag_tol=1.0
    )
    assert [s.star.auid for s in ranked] == ["CLOSE"]
    assert abs(ranked[0].delta_mag - 0.3) < 1e-9


def test_rank_cap() -> None:
    comps = [_comp(f"C{i}", 0.0, i / 100.0, 12.0) for i in range(1, 6)]
    ranked = rank_comparisons(0.0, 0.0, comps, max_results=2)
    assert len(ranked) == 2
    assert ranked[0].star.auid == "C1"  # closest


def test_comparisons_for_variable_uses_brightest_mag() -> None:
    var = VariableStar(name="V", ra_deg=0.0, dec_deg=0.0, max_mag="12.0 V", min_mag="14.0 V")
    good = _comp("GOOD", 0.02, 0.0, 12.4)  # within 1 mag of 12.0
    bad = _comp("BAD", 0.01, 0.0, 15.0)  # 3 mag off → dropped
    ranked = comparisons_for_variable(var, [good, bad], mag_tol=1.0)
    assert [s.star.auid for s in ranked] == ["GOOD"]
