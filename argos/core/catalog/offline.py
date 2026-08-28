"""Embedded catalogue search used when Argos is away from the internet.

The essential catalogue is deliberately small and immutable: Messier, NGC and
IC identifiers with positions, type, magnitude where available and common
aliases.  It supports target naming and a first GoTo; it does not pretend to
be a precision astrometric or stellar-photometry catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import gzip
import json
from pathlib import Path
import sys

_RESOURCE_RELATIVE_PATH = Path("argos") / "resources" / "catalogues" / "essential-v1.json.gz"


@dataclass(frozen=True)
class OfflineCatalogueObject:
    """One name-resolvable entry from the bundled essential catalogue."""

    name: str
    aliases: tuple[str, ...]
    ra_degrees: float
    dec_degrees: float
    object_type: str = ""
    magnitude: float | None = None


def _resource_path() -> Path:
    """Find the resource in a checkout and in a PyInstaller bundle."""
    if getattr(sys, "frozen", False):  # pragma: no cover - exercised in package smoke test
        return Path(sys._MEIPASS) / _RESOURCE_RELATIVE_PATH  # type: ignore[attr-defined]
    return Path(__file__).parents[2] / "resources" / "catalogues" / "essential-v1.json.gz"


def normalise_catalogue_query(value: str) -> str:
    """Case/space/punctuation-insensitive key for common target designations."""
    return "".join(char for char in value.casefold() if char.isalnum())


@lru_cache(maxsize=1)
def _catalogue() -> tuple[dict, tuple[OfflineCatalogueObject, ...]]:
    with gzip.open(_resource_path(), "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Invalid bundled essential catalogue")
    objects: list[OfflineCatalogueObject] = []
    for row in payload.get("objects", []):
        try:
            objects.append(
                OfflineCatalogueObject(
                    name=str(row["name"]),
                    aliases=tuple(str(alias) for alias in row.get("aliases", [])),
                    ra_degrees=float(row["ra_degrees"]),
                    dec_degrees=float(row["dec_degrees"]),
                    object_type=str(row.get("object_type", "")),
                    magnitude=float(row["magnitude"]) if row.get("magnitude") is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return payload, tuple(objects)


def essential_catalogue_info() -> dict[str, str | int]:
    """Public version/provenance summary for the Settings panel and support bundle."""
    payload, objects = _catalogue()
    return {
        "name": str(payload.get("catalogue", "Argos Essential Catalogue")),
        "version": str(payload.get("version", "unknown")),
        "source": str(payload.get("source", "")),
        "source_url": str(payload.get("source_url", "")),
        "object_count": len(objects),
    }


def essential_catalogue_objects() -> tuple[OfflineCatalogueObject, ...]:
    """Return the immutable bundled records for coordinate-near matching."""
    return _catalogue()[1]


def search_essential_catalogue(query: str, *, limit: int = 8) -> list[OfflineCatalogueObject]:
    """Find matching bundled targets, with exact aliases before prefix matches."""
    needle = normalise_catalogue_query(query)
    if not needle or limit <= 0:
        return []
    ranked: list[tuple[int, str, OfflineCatalogueObject]] = []
    for item in _catalogue()[1]:
        names = (item.name, *item.aliases)
        keys = tuple(normalise_catalogue_query(name) for name in names)
        if needle in keys:
            score = 0
        elif any(key.startswith(needle) for key in keys):
            score = 1
        elif any(needle in key for key in keys):
            score = 2
        else:
            continue
        ranked.append((score, item.name, item))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [item for _score, _name, item in ranked[:limit]]


def resolve_essential_object(query: str) -> OfflineCatalogueObject | None:
    """Resolve an exact bundled designation, never guessing a prefix."""
    needle = normalise_catalogue_query(query)
    if not needle:
        return None
    for item in search_essential_catalogue(query, limit=16):
        if needle in {normalise_catalogue_query(name) for name in (item.name, *item.aliases)}:
            return item
    return None


def essential_catalogue_suggestions(query: str, *, limit: int = 8) -> list[str]:
    """Return user-facing aliases (``M 42`` before ``NGC 1976``) for completion."""
    needle = normalise_catalogue_query(query)
    suggestions: list[str] = []
    for item in search_essential_catalogue(query, limit=limit * 3):
        for name in (*item.aliases, item.name):
            key = normalise_catalogue_query(name)
            if needle in key and name not in suggestions:
                suggestions.append(name)
                if len(suggestions) >= limit:
                    return suggestions
    return suggestions
