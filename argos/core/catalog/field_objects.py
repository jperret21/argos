"""Cache-backed SIMBAD field identification for a solved Argos frame.

Gaia identifies sources but most Gaia IDs do not have a human-facing stellar
name.  SIMBAD is the complementary *identifier and object-type* service.  A
field query is intentionally bounded and cached: it is made when the observer
asks Argos to identify a field, never for telemetry or background tracking.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
from io import StringIO
import json
import math
from pathlib import Path
import re
import time
from typing import Any

import requests

from argos.core.catalog.object_resolver import display_designation

_SIMBAD_TAP_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
_CACHE_DIR = Path.home() / ".argos" / "cache" / "field_catalogue" / "simbad"
_CACHE_FRESH_S = 30 * 86400.0


class FieldObjectLookupError(RuntimeError):
    """A named-object field lookup could not be completed."""


@dataclass(frozen=True)
class NamedFieldObject:
    """One SIMBAD object with a stable identity in a solved image."""

    name: str
    ra_deg: float
    dec_deg: float
    object_type: str = ""
    source: str = "SIMBAD"
    # Passband-labelled SIMBAD flux/magnitude values.  Never collapse these
    # into one unqualified "magnitude": G, V and near-IR K are not equivalent.
    mags: tuple[tuple[str, float], ...] = ()


def configure_cache_directory(path: Path | str) -> None:
    """Set the folder used for cached SIMBAD field responses."""
    global _CACHE_DIR
    _CACHE_DIR = Path(path).expanduser() / "simbad"


def _cache_path(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    maximum: int,
    include_ordinary_stars: bool,
) -> Path:
    key = (
        f"v3-fluxes:{ra_deg:.6f}:{dec_deg:.6f}:{radius_deg:.6f}:{maximum}:"
        f"ordinary={int(include_ordinary_stars)}"
    )
    return _CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def _load(path: Path) -> tuple[list[NamedFieldObject], float] | None:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        values = [
            NamedFieldObject(
                **{
                    **row,
                    "mags": tuple((str(band), float(value)) for band, value in row.get("mags", ())),
                }
            )
            for row in rows
            if isinstance(row, dict)
        ]
        return values, time.time() - path.stat().st_mtime
    except (OSError, ValueError, TypeError):
        return None


def _store(path: Path, objects: list[NamedFieldObject]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([asdict(item) for item in objects], indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        pass


def _parse_csv(body: str) -> list[NamedFieldObject]:
    out: list[NamedFieldObject] = []
    try:
        for row in csv.DictReader(StringIO(body)):
            name = display_designation(row.get("main_id") or "")
            name = re.sub(r"^(?:\*|NAME)\s+", "", name, flags=re.IGNORECASE)
            if not name:
                continue
            magnitudes = []
            for column, label in (
                ("U", "U"),
                ("B", "B"),
                ("V", "V"),
                ("G", "G"),
                ("R", "R"),
                ("I", "I"),
                ("J", "J"),
                ("H", "H"),
                ("K", "K"),
                ("u_", "u"),
                ("g_", "g"),
                ("r_", "r"),
                ("i_", "i"),
                ("z_", "z"),
            ):
                raw = row.get(column)
                if raw not in (None, ""):
                    magnitudes.append((label, float(raw)))
            out.append(
                NamedFieldObject(
                    name=name,
                    ra_deg=float(row["ra"]),
                    dec_deg=float(row["dec"]),
                    object_type=(row.get("otype") or "").strip(),
                    mags=tuple(magnitudes),
                )
            )
    except (csv.Error, KeyError, TypeError, ValueError) as exc:
        raise FieldObjectLookupError("SIMBAD returned an invalid field catalogue.") from exc
    return out


def _spatially_uniform(
    objects: list[NamedFieldObject], maximum: int, ra_deg: float, dec_deg: float, radius_deg: float
) -> list[NamedFieldObject]:
    """Limit a dense field without filling only one corner of the image.

    TAP ``TOP`` has no useful sky-order guarantee.  We fetch a larger,
    semantically filtered set then round-robin an 8×8 sky grid so every part
    of the solved field receives identifiers before a crowded cell gets more.
    """
    if len(objects) <= maximum:
        return objects
    cells: dict[tuple[int, int], list[NamedFieldObject]] = {}
    cos_dec = max(0.05, math.cos(math.radians(dec_deg)))
    for item in objects:
        dra = ((item.ra_deg - ra_deg + 180.0) % 360.0) - 180.0
        nx = 0.5 + (dra * cos_dec) / (2.0 * radius_deg)
        ny = 0.5 + (item.dec_deg - dec_deg) / (2.0 * radius_deg)
        cell = (max(0, min(7, int(nx * 8))), max(0, min(7, int(ny * 8))))
        cells.setdefault(cell, []).append(item)
    for values in cells.values():
        values.sort(key=lambda item: item.name.casefold())
    selected: list[NamedFieldObject] = []
    active = sorted(cells)
    while active and len(selected) < maximum:
        next_active = []
        for cell in active:
            values = cells[cell]
            if values and len(selected) < maximum:
                selected.append(values.pop(0))
            if values:
                next_active.append(cell)
        active = next_active
    return selected


def simbad_field_objects(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    *,
    max_results: int = 500,
    allow_network: bool = True,
    include_ordinary_stars: bool = False,
    timeout_s: float = 15.0,
    session: Any = None,
) -> list[NamedFieldObject]:
    """Return named SIMBAD objects in a cone, preferring its local cache.

    SIMBAD is not a complete stellar catalogue: Gaia remains the layer for all
    sources.  This result supplies conventional identifiers and object types
    where SIMBAD has an entry.
    """
    if not (0.0 <= ra_deg < 360.0 and -90.0 <= dec_deg <= 90.0 and radius_deg > 0):
        raise FieldObjectLookupError("Invalid solved-field coordinates.")
    if not math.isfinite(radius_deg):
        raise FieldObjectLookupError("Invalid solved-field radius.")
    maximum = max(1, min(2000, int(max_results)))
    radius = min(5.0, float(radius_deg))
    path = _cache_path(ra_deg, dec_deg, radius, maximum, include_ordinary_stars)
    cached = _load(path)
    if cached is not None and (cached[1] < _CACHE_FRESH_S or not allow_network):
        return cached[0]
    if not allow_network:
        return []
    fetch_maximum = min(5000, max(maximum, maximum * 4))
    semantic_filter = (
        ""
        if include_ordinary_stars
        else (
            "AND (b.otype <> '*' OR b.main_id LIKE 'HD %' OR b.main_id LIKE 'HIP %' "
            "OR b.main_id LIKE '* %')"
        )
    )
    query = (
        f"SELECT TOP {fetch_maximum} b.main_id, b.ra, b.dec, b.otype, "
        "f.U, f.B, f.V, f.G, f.R, f.I, f.J, f.H, f.K, "
        "f.u_, f.g_, f.r_, f.i_, f.z_ "
        "FROM basic AS b LEFT OUTER JOIN allfluxes AS f ON b.oid = f.oidref "
        "WHERE CONTAINS(POINT('ICRS', b.ra, b.dec), "
        f"CIRCLE('ICRS', {ra_deg:.8f}, {dec_deg:.8f}, {radius:.8f})) = 1 "
        f"{semantic_filter}"
    )
    sender = session.get if session is not None else requests.get
    try:
        response = sender(
            _SIMBAD_TAP_URL,
            params={"request": "doQuery", "lang": "adql", "format": "csv", "query": query},
            timeout=timeout_s,
        )
        response.raise_for_status()
        objects = _spatially_uniform(_parse_csv(response.text), maximum, ra_deg, dec_deg, radius)
    except (requests.RequestException, FieldObjectLookupError) as exc:
        if cached is not None:
            return cached[0]
        if isinstance(exc, FieldObjectLookupError):
            raise
        raise FieldObjectLookupError("SIMBAD field catalogue is unavailable.") from exc
    _store(path, objects)
    return objects
