from __future__ import annotations

import pytest

from argos.core.catalog.field_objects import NamedFieldObject
from argos.core.catalog.gaia import GaiaStar
from argos.core.catalog import point_identity


def test_point_identity_uses_gaia_position_and_matching_simbad_name(monkeypatch) -> None:
    monkeypatch.setattr(
        point_identity,
        "gaia_cone_search",
        lambda *_args, **_kwargs: [
            GaiaStar("123", 300.0001, 58.0, g_mag=15.2, bp_mag=15.7, rp_mag=14.6)
        ],
    )
    monkeypatch.setattr(
        point_identity,
        "simbad_field_objects",
        lambda *_args, **_kwargs: [
            NamedFieldObject(
                "HD 999",
                300.00012,
                58.0,
                "*",
                mags=(("V", 15.4),),
            )
        ],
    )

    identity = point_identity.identify_point_source(300.0, 58.0)

    assert identity is not None
    assert identity.name == "HD 999"
    assert identity.gaia_source_id == "123"
    assert identity.ra_deg == 300.0001  # Gaia remains the astrometric source of truth
    assert dict(identity.mags) == {
        "Gaia G": 15.2,
        "Gaia BP": 15.7,
        "Gaia RP": 14.6,
        "SIMBAD V": 15.4,
    }


def test_unrelated_simbad_neighbour_cannot_name_a_gaia_star(monkeypatch) -> None:
    monkeypatch.setattr(
        point_identity,
        "gaia_cone_search",
        lambda *_args, **_kwargs: [GaiaStar("123", 300.0, 58.0, g_mag=16.0)],
    )
    # Roughly 5.3 arcsec away at this declination: inside the 10 arcsec query,
    # but outside the conservative 3 arcsec cross-match.
    monkeypatch.setattr(
        point_identity,
        "simbad_field_objects",
        lambda *_args, **_kwargs: [NamedFieldObject("Radio source", 300.0028, 58.0, "Rad")],
    )

    identity = point_identity.identify_point_source(300.0, 58.0)

    assert identity is not None
    assert identity.name == "Gaia DR3 123"
    assert identity.source == "Gaia DR3"


def test_point_identity_returns_none_when_no_source_matches(monkeypatch) -> None:
    monkeypatch.setattr(point_identity, "gaia_cone_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(point_identity, "simbad_field_objects", lambda *_args, **_kwargs: [])
    assert point_identity.identify_point_source(300.0, 58.0) is None


def test_blended_gaia_pair_is_not_given_an_arbitrary_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        point_identity,
        "gaia_cone_search",
        lambda *_args, **_kwargs: [
            GaiaStar("one", 300.00010, 58.0, g_mag=16.0),
            GaiaStar("two", 299.99990, 58.0, g_mag=16.2),
        ],
    )
    monkeypatch.setattr(point_identity, "simbad_field_objects", lambda *_args, **_kwargs: [])
    assert point_identity.identify_point_source(300.0, 58.0) is None


def test_point_identity_rejects_an_invalid_wcs_coordinate() -> None:
    with pytest.raises(point_identity.PointIdentityLookupError, match="Invalid WCS"):
        point_identity.identify_point_source(300.0, 95.0)
