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
