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
import json
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

_SESAME_URL = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?"
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


def _cache_key(query: str) -> str:
    return " ".join(query.casefold().split())


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
    query = " ".join(query.split())
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
