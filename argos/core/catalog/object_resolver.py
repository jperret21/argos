"""Resolve astronomical object designations to ICRS coordinates.

This deliberately uses CDS Sesame rather than shipping a partial, stale copy
of the Messier/NGC/HD catalogues.  Sesame federates the major astronomical
name services and accepts the names observers actually type (``M 42``,
``NGC 7000``, ``HD 189733`` …).  Successful lookups are cached locally, so a
target used during preparation remains available at the telescope without a
network connection.

The module is Qt-free.  Call it from :mod:`argos.workers.object_resolver_worker`
when used by the UI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
from io import StringIO
import json
import math
from pathlib import Path
import re
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

_SESAME_URL = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?"
_SIMBAD_TAP_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
_CACHE_PATH = Path.home() / "Argos" / "cache" / "object_resolver.json"


class ObjectResolutionError(RuntimeError):
    """The designation could not be resolved to an astronomical position."""


@dataclass(frozen=True)
class ResolvedObject:
    """One coordinate-bearing catalogue object in ICRS/J2000."""

    name: str
    ra_degrees: float
    dec_degrees: float
    object_type: str = ""
    source: str = "CDS Sesame"

    @property
    def ra_hours(self) -> float:
        return self.ra_degrees / 15.0


@dataclass(frozen=True)
class NearbyObject:
    """A catalogue candidate near a requested ICRS coordinate."""

    object: ResolvedObject
    separation_arcsec: float


def _cache_key(query: str) -> str:
    return re.sub(r"[^a-z0-9]", "", query.casefold())


def normalize_designation(query: str) -> str:
    """Normalise common compact stellar/deep-sky designations for Sesame."""
    value = " ".join(query.strip().split())
    match = re.fullmatch(r"([A-Za-z]+)\s*(\d+)\s*([A-Za-z])?", value)
    if not match:
        return value
    prefix, number, suffix = match.groups()
    if prefix.upper() in {"HD", "HIP", "NGC", "IC", "M"}:
        return f"{prefix.upper()} {number}{(' ' + suffix.lower()) if suffix else ''}"
    return value


def _read_cache(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(path: Path, cache: dict[str, dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        # A read-only home directory must not make an otherwise valid lookup fail.
        pass


def _angular_separation_arcsec(
    ra_a_deg: float, dec_a_deg: float, ra_b_deg: float, dec_b_deg: float
) -> float:
    """Great-circle separation, robust close to the poles."""
    ra_a, dec_a, ra_b, dec_b = map(math.radians, (ra_a_deg, dec_a_deg, ra_b_deg, dec_b_deg))
    cosine = math.sin(dec_a) * math.sin(dec_b) + math.cos(dec_a) * math.cos(dec_b) * math.cos(
        ra_a - ra_b
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine)))) * 3600.0


def nearby_cached_objects(
    ra_degrees: float,
    dec_degrees: float,
    *,
    radius_arcsec: float = 90.0,
    cache_path: Path = _CACHE_PATH,
) -> list[NearbyObject]:
    """Return cached catalogue objects around a coordinate, nearest first."""
    matches: list[NearbyObject] = []
    seen: set[tuple[str, float, float]] = set()
    for row in _read_cache(cache_path).values():
        if not isinstance(row, dict):
            continue
        try:
            resolved = ResolvedObject(**row)
        except (TypeError, ValueError):
            continue
        key = (resolved.name, resolved.ra_degrees, resolved.dec_degrees)
        if key in seen:
            continue
        seen.add(key)
        separation = _angular_separation_arcsec(
            ra_degrees, dec_degrees, resolved.ra_degrees, resolved.dec_degrees
        )
        if separation <= radius_arcsec:
            matches.append(NearbyObject(resolved, separation))
    return sorted(matches, key=lambda item: item.separation_arcsec)


def _nearby_from_simbad(
    ra_degrees: float, dec_degrees: float, radius_arcsec: float, timeout_s: float
) -> list[NearbyObject]:
    """Query a small SIMBAD cone through its documented TAP service."""
    radius_deg = radius_arcsec / 3600.0
    query = (
        "SELECT TOP 12 main_id, ra, dec, otype FROM basic "
        "WHERE CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra_degrees:.9f}, {dec_degrees:.9f}, {radius_deg:.9f})) = 1"
    )
    try:
        response = requests.get(
            _SIMBAD_TAP_URL,
            params={"request": "doQuery", "lang": "adql", "format": "csv", "query": query},
            timeout=timeout_s,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ObjectResolutionError("Catalogue unavailable for target-name suggestion.") from exc

    matches: list[NearbyObject] = []
    try:
        rows = csv.DictReader(StringIO(response.text))
        for row in rows:
            name = (row.get("main_id") or "").strip()
            if not name:
                continue
            resolved = ResolvedObject(
                name=name,
                ra_degrees=float(row["ra"]),
                dec_degrees=float(row["dec"]),
                object_type=(row.get("otype") or "").strip(),
                source="SIMBAD coordinate search",
            )
            separation = _angular_separation_arcsec(
                ra_degrees, dec_degrees, resolved.ra_degrees, resolved.dec_degrees
            )
            matches.append(NearbyObject(resolved, separation))
    except (KeyError, TypeError, ValueError) as exc:
        raise ObjectResolutionError(
            "Catalogue returned an invalid target-name suggestion."
        ) from exc
    return sorted(matches, key=lambda item: item.separation_arcsec)


def resolve_nearby_objects(
    ra_degrees: float,
    dec_degrees: float,
    *,
    radius_arcsec: float = 90.0,
    allow_network: bool = True,
    timeout_s: float = 8.0,
    cache_path: Path = _CACHE_PATH,
) -> list[NearbyObject]:
    """Find names near a Stellarium target, preferring the local cache.

    The caller must show the returned candidates and let the observer choose.
    A coordinate is not a unique object designation, particularly in a dense
    stellar field.  If online lookup was not explicitly allowed, this is a
    strictly offline cache lookup.
    """
    if not (0.0 <= ra_degrees < 360.0 and -90.0 <= dec_degrees <= 90.0):
        raise ObjectResolutionError("Invalid ICRS coordinates for target-name suggestion.")
    cached = nearby_cached_objects(
        ra_degrees, dec_degrees, radius_arcsec=radius_arcsec, cache_path=cache_path
    )
    if cached or not allow_network:
        return cached
    matches = _nearby_from_simbad(ra_degrees, dec_degrees, radius_arcsec, timeout_s)
    # Preserve a successful reverse lookup for a later offline session.
    cache = _read_cache(cache_path)
    for match in matches:
        cache[_cache_key(match.object.name)] = asdict(match.object)
    if matches:
        _write_cache(cache_path, cache)
    return matches


def cached_object_suggestions(
    query: str, *, cache_path: Path = _CACHE_PATH, limit: int = 8
) -> list[str]:
    """Return offline autocomplete candidates from prior CDS resolutions."""
    needle = _cache_key(query)
    if not needle:
        return []
    names = {
        str(row.get("name", "")).strip()
        for row in _read_cache(cache_path).values()
        if isinstance(row, dict) and needle in _cache_key(str(row.get("name", "")))
    }
    return sorted(name for name in names if name)[:limit]


def _from_xml(text: str, query: str) -> ResolvedObject:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ObjectResolutionError("The catalogue returned an invalid response.") from exc

    # Sesame XML has no namespaces today, but matching by local name makes the
    # parser resilient to a future schema namespace.
    values = {
        element.tag.rsplit("}", 1)[-1]: (element.text or "").strip() for element in root.iter()
    }
    try:
        ra = float(values["jradeg"])
        dec = float(values["jdedeg"])
    except (KeyError, ValueError) as exc:
        raise ObjectResolutionError(f"No ICRS coordinates found for ‘{query}’.") from exc
    if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
        raise ObjectResolutionError(f"The catalogue returned invalid coordinates for ‘{query}’.")
    return ResolvedObject(
        name=values.get("oname") or query.strip(),
        ra_degrees=ra,
        dec_degrees=dec,
        object_type=values.get("otype", ""),
    )


def resolve_object(
    query: str,
    *,
    timeout_s: float = 8.0,
    cache_path: Path = _CACHE_PATH,
) -> ResolvedObject:
    """Resolve a catalogue designation, preferring a prior local result.

    Raises :class:`ObjectResolutionError` for an empty, unknown or temporarily
    unavailable designation.  Coordinates are J2000/ICRS decimal degrees.
    """
    query = normalize_designation(query)
    if not query:
        raise ObjectResolutionError("Enter an object designation first.")
    key = _cache_key(query)
    cached = _read_cache(cache_path).get(key)
    if isinstance(cached, dict):
        try:
            return ResolvedObject(**cached)
        except (TypeError, ValueError):
            pass

    try:
        response = requests.get(f"{_SESAME_URL}{quote(query)}", timeout=timeout_s)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ObjectResolutionError(
            "Catalogue unavailable. Connect to the internet or use a previously searched target."
        ) from exc

    result = _from_xml(response.text, query)
    cache = _read_cache(cache_path)
    cache[key] = asdict(result)
    _write_cache(cache_path, cache)
    return result
