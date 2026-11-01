from __future__ import annotations

from argos.core import location_resolver
from argos.core.location_resolver import LocationResolutionError, search_locations


def test_search_locations_combines_geocode_and_elevation(monkeypatch) -> None:
    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self) -> None:
            pass

        def json(self):
            return self._payload

    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        if url == location_resolver._NOMINATIM_URL:
            return Response(
                [{"display_name": "Berkeley, California", "lat": "37.8715", "lon": "-122.2730"}]
            )
        return Response({"elevation": [52.0]})

    monkeypatch.setattr(location_resolver.requests, "get", fake_get)
    results = search_locations("Berkeley")

    assert len(results) == 1
    assert results[0].latitude == 37.8715
    assert results[0].longitude == -122.273
    assert results[0].elevation_m == 52.0
    assert calls == [location_resolver._NOMINATIM_URL, location_resolver._ELEVATION_URL]


def test_search_locations_requires_text() -> None:
    try:
        search_locations("  ")
    except LocationResolutionError as exc:
        assert "Enter" in str(exc)
    else:
        raise AssertionError("empty query must be rejected")


def test_search_requests_identify_this_release(monkeypatch) -> None:
    """H17: Nominatim's usage policy asks for an identifying User-Agent. The
    published 0.4.2 sent the hard-coded "Argos/0.4.1"; it must follow
    argos.__version__ (the one place a release changes)."""
    import argos

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self) -> None:
            pass

        def json(self):
            return self._payload

    agents: dict[str, str] = {}

    def fake_get(url, **kwargs):
        agents[url] = kwargs["headers"]["User-Agent"]
        if url == location_resolver._NOMINATIM_URL:
            return Response([{"display_name": "Paris, France", "lat": "48.8589", "lon": "2.32"}])
        return Response({"elevation": [35.0]})

    monkeypatch.setattr(location_resolver.requests, "get", fake_get)
    search_locations("Paris")

    expected = f"Argos/{argos.__version__} (astronomical observing-site search)"
    assert agents == {
        location_resolver._NOMINATIM_URL: expected,
        location_resolver._ELEVATION_URL: expected,
    }
