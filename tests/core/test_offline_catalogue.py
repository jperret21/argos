"""The embedded deep-sky catalogue is a release asset, not an online fixture."""

from __future__ import annotations

from argos.core.catalog.offline import (
    essential_catalogue_info,
    resolve_essential_object,
    search_essential_catalogue,
)


def test_essential_catalogue_has_expected_scope_and_provenance() -> None:
    info = essential_catalogue_info()

    assert info["object_count"] == 13229
    assert info["version"] == "1.0"
    assert "CDS/VizieR VII/118" in str(info["source"])


def test_essential_catalogue_accepts_compact_designations_and_aliases() -> None:
    assert resolve_essential_object("M42").name == "NGC 1976"
    assert resolve_essential_object("ngc 224").name == "NGC 224"
    assert resolve_essential_object("IC434").name == "IC 434"

    matches = search_essential_catalogue("andromeda")

    assert matches[0].name == "NGC 224"
