from __future__ import annotations

from pathlib import Path

import pytest

from argos.core.catalog import gaia
from argos.core.catalog.aavso import CatalogError


class _Response:
    def __init__(self, body: str) -> None:
        self.text = body

    def raise_for_status(self) -> None:
        return None


class _Session:
    def __init__(self, body: str) -> None:
        self.body = body
        self.calls: list[dict] = []

    def post(self, _url: str, *, data: dict, timeout: float):
        self.calls.append(data)
        return _Response(self.body)


def test_gaia_cone_search_parses_and_caches_lightweight_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gaia, "_CACHE_DIR", tmp_path)
    session = _Session(
        "source_id,ra,dec,phot_g_mean_mag,phot_bp_mean_mag,phot_rp_mean_mag\n"
        "2050045432198760192,299.5902,35.2016,4.68,4.80,4.52\n"
        "bad,not-a-number,35.2,8.0,8.1,7.9\n"
    )
    stars = gaia.gaia_cone_search(299.59, 35.2, 0.5, mag_limit=12, max_results=20, session=session)
    assert [(star.display_name, star.g_mag) for star in stars] == [
        ("Gaia DR3 2050045432198760192", 4.68)
    ]
    assert stars[0].bp_mag == 4.80 and stars[0].rp_mag == 4.52
    assert "gaiadr3.gaia_source" in session.calls[0]["QUERY"]
    assert "TOP 20" in session.calls[0]["QUERY"]

    # The exact same field is served offline from the local cache.
    assert (
        gaia.gaia_cone_search(299.59, 35.2, 0.5, mag_limit=12, max_results=20, session=session)
        == stars
    )
    assert len(session.calls) == 1


def test_gaia_rejects_invalid_coordinates() -> None:
    with pytest.raises(CatalogError, match="coordinates"):
        gaia.gaia_cone_search(1.0, 95.0, 0.5)


def test_gaia_point_lookup_can_be_strictly_cache_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(gaia, "_CACHE_DIR", tmp_path)

    class NoNetwork:
        def post(self, *_args, **_kwargs):
            raise AssertionError("cache-only lookup must not contact Gaia")

    assert (
        gaia.gaia_cone_search(
            299.59,
            35.2,
            10.0 / 3600.0,
            allow_network=False,
            session=NoNetwork(),
        )
        == []
    )


def test_gaia_rows_carry_proper_motions_and_old_caches_still_serve_offline_s77(
    tmp_path: Path, monkeypatch
) -> None:
    """S77: the query asks for pmra/pmdec (Gaia DR3, 2016.0); a response cached before
    0.5.0 (without them) still identifies the field offline, its stars without motion."""
    monkeypatch.setattr(gaia, "_CACHE_DIR", tmp_path)
    session = _Session(
        "source_id,ra,dec,phot_g_mean_mag,phot_bp_mean_mag,phot_rp_mean_mag,pmra,pmdec\n"
        "2125982599343482624,291.3656403,42.7834888,7.62,7.9,7.2,-109.5987,-195.8507\n"
        "2125982599341232000,291.3560838,42.7870588,16.76,17.1,16.2,,\n"
    )
    stars = gaia.gaia_cone_search(291.366, 42.784, 0.01, session=session)
    assert "pmra, pmdec" in session.calls[0]["QUERY"]
    assert (stars[0].pmra_mas_yr, stars[0].pmdec_mas_yr, stars[0].epoch) == (
        -109.5987,
        -195.8507,
        2016.0,
    )
    assert stars[1].pmra_mas_yr is None  # a two-parameter solution
    old_dir = tmp_path / "before_0_5_0"
    monkeypatch.setattr(gaia, "_CACHE_DIR", old_dir)
    legacy_query = session.calls[0]["QUERY"].replace(", pmra, pmdec", "")
    legacy = dict(session.calls[0], QUERY=legacy_query)
    old_dir.mkdir()
    gaia._cache_path(legacy).write_text(
        "source_id,ra,dec,phot_g_mean_mag,phot_bp_mean_mag,phot_rp_mean_mag\n"
        "2125982599343482624,291.3656403,42.7834888,7.62,7.9,7.2\n",
        encoding="utf-8",
    )
    old = gaia.gaia_cone_search(291.366, 42.784, 0.01, allow_network=False)
    assert [(s.source_id, s.pmra_mas_yr) for s in old] == [("2125982599343482624", None)]


def test_a_set_lookup_stops_asking_the_archive_after_a_failure_s77(monkeypatch) -> None:
    """S77 amended (technical review): one cone per VSX/VSP star, each waiting 20 s on an
    archive that does not answer (RR Lyr's set: 140 s at "measuring 0/N", no cancel).
    After the first failure the other stars are read from the cache only, the timeout
    is 5 s, and a cancel stops the lookup between stars."""
    from argos.core.catalog import gaia
    from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar

    tset = TargetSet(
        object_name="X",
        stars=[TargetStar(ROLE_TARGET, 10.0, 20.0, source="vsx")]
        + [TargetStar(ROLE_COMPARISON, 10.0 + i, 20.0, source="vsp") for i in range(1, 7)],
    )
    asked = []

    def cone(ra, dec, radius, *, allow_network, timeout_s, **kw):
        asked.append((allow_network, timeout_s))
        raise gaia.CatalogError("timed out")

    monkeypatch.setattr(gaia, "gaia_cone_search", cone)
    with pytest.raises(gaia.CatalogError):
        gaia.gaia_sources_for_set(tset)
    assert asked == [(True, 5.0)] + [(False, 5.0)] * 6  # 7 network queries of 20 s before

    asked.clear()
    assert gaia.gaia_sources_for_set(tset, cancel=lambda: len(asked) >= 2) == []
    assert len(asked) == 2
