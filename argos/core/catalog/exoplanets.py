"""Exoplanet ephemerides from the NASA Exoplanet Archive.

Argos uses this catalogue only to prepare an observing run.  The download is
explicitly requested by the observer and successful results are cached locally
so a prepared target remains usable away from the internet.  Transit fitting
and the science-grade light curve remain post-processing work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

import requests

_TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
_CACHE_PATH = Path.home() / "Argos" / "cache" / "exoplanets.json"
_FIELD_CACHE_DIR = Path.home() / ".argos" / "cache" / "field_catalogue" / "nasa"
_FIELD_CACHE_FRESH_S = 30 * 86400.0


def configure_cache_path(path: Path | str) -> None:
    """Set the persistent NASA ephemeris cache location for future lookups."""
    global _CACHE_PATH
    _CACHE_PATH = Path(path).expanduser()


def configure_field_cache_directory(path: Path | str) -> None:
    """Set the cache folder used by NASA solved-field host queries."""
    global _FIELD_CACHE_DIR
    _FIELD_CACHE_DIR = Path(path).expanduser() / "nasa"


class ExoplanetLookupError(RuntimeError):
    """The requested planet has no usable published transit ephemeris."""


@dataclass(frozen=True)
class ExoplanetTarget:
    """Published host-star coordinates and a transit ephemeris.

    ``epoch_bjd_tdb`` is deliberately retained in BJD_TDB: silently treating
    a published HJD/UTC epoch as BJD_TDB can shift a predicted transit by
    minutes.  The source table's time-system reference is shown to the user
    before an acquisition plan is generated.
    """

    planet_name: str
    host_name: str
    ra_degrees: float
    dec_degrees: float
    period_days: float
    epoch_bjd_tdb: float
    duration_hours: float | None = None
    depth_percent: float | None = None
    period_error_days: float | None = None
    epoch_error_days: float | None = None
    epoch_system: str = "BJD_TDB"
    source: str = "NASA Exoplanet Archive / PSCompPars"
    retrieved_utc: str = ""

    @property
    def ra_hours(self) -> float:
        return self.ra_degrees / 15.0


@dataclass(frozen=True)
class CachedExoplanetHost:
    """A host star represented by an already cached transit ephemeris.

    This deliberately has no online fallback.  It lets a solved image show
    previously prepared exoplanet systems while keeping field enrichment an
    explicit, privacy-respecting action.
    """

    host_name: str
    ra_degrees: float
    dec_degrees: float
    planet_names: tuple[str, ...]
    mags: tuple[tuple[str, float], ...] = ()


def _field_cache_path(ra_deg: float, dec_deg: float, radius_deg: float) -> Path:
    key = f"{ra_deg:.6f}:{dec_deg:.6f}:{radius_deg:.6f}"
    return _FIELD_CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def _read_field_cache(path: Path) -> tuple[list[CachedExoplanetHost], float] | None:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        hosts = [
            CachedExoplanetHost(
                host_name=str(row["host_name"]),
                ra_degrees=float(row["ra_degrees"]),
                dec_degrees=float(row["dec_degrees"]),
                planet_names=tuple(str(name) for name in row.get("planet_names", ())),
                mags=tuple(
                    (str(band), float(magnitude)) for band, magnitude in row.get("mags", ())
                ),
            )
            for row in rows
            if isinstance(row, dict)
        ]
        return hosts, time.time() - path.stat().st_mtime
    except (OSError, KeyError, ValueError, TypeError):
        return None


def _write_field_cache(path: Path, hosts: list[CachedExoplanetHost]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([asdict(host) for host in hosts], indent=2, sort_keys=True), encoding="utf-8"
        )
    except OSError:
        pass


def _angular_separation_deg(
    ra_a_deg: float, dec_a_deg: float, ra_b_deg: float, dec_b_deg: float
) -> float:
    """Great-circle separation in degrees, safe around the RA wrap."""
    import math

    ra_a, dec_a, ra_b, dec_b = map(math.radians, (ra_a_deg, dec_a_deg, ra_b_deg, dec_b_deg))
    cosine = math.sin(dec_a) * math.sin(dec_b) + math.cos(dec_a) * math.cos(dec_b) * math.cos(
        ra_a - ra_b
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def cached_exoplanet_hosts_in_cone(
    ra_degrees: float,
    dec_degrees: float,
    radius_deg: float,
    *,
    cache_path: Path | None = None,
) -> list[CachedExoplanetHost]:
    """Return unique cached transiting-planet hosts inside a solved field.

    The small local ephemeris cache is not a complete planet catalogue.  This
    function therefore never claims that an empty result means there are no
    exoplanets in the field; it only exposes objects the observer has already
    downloaded or prepared.
    """
    if not (0.0 <= ra_degrees < 360.0 and -90.0 <= dec_degrees <= 90.0 and radius_deg > 0):
        return []
    hosts: dict[tuple[str, float, float], tuple[str, list[str]]] = {}
    for row in _read_cache(cache_path or _CACHE_PATH).values():
        try:
            target = ExoplanetTarget(**row)
        except (TypeError, ValueError):
            continue
        if (
            _angular_separation_deg(ra_degrees, dec_degrees, target.ra_degrees, target.dec_degrees)
            > radius_deg
        ):
            continue
        key = (target.host_name.casefold(), target.ra_degrees, target.dec_degrees)
        if key not in hosts:
            hosts[key] = (target.host_name, [])
        hosts[key][1].append(target.planet_name)
    return [
        CachedExoplanetHost(
            host_name=host_name,
            ra_degrees=names_key[1],
            dec_degrees=names_key[2],
            planet_names=tuple(sorted(set(names))),
        )
        for names_key, (host_name, names) in hosts.items()
    ]


def exoplanet_hosts_in_cone(
    ra_degrees: float,
    dec_degrees: float,
    radius_deg: float,
    *,
    allow_network: bool = True,
    timeout_s: float = 15.0,
    session=None,
) -> list[CachedExoplanetHost]:
    """Find confirmed exoplanet hosts in a solved field, with local caching.

    A field lookup uses NASA's ``pscomppars`` table and groups its one-row-per-
    planet results by host.  It is intentionally separate from
    :func:`lookup_exoplanet`: a field inspection should tell the observer what
    is there, while a prepared target needs a full transit ephemeris.
    """
    if not (
        0.0 <= ra_degrees < 360.0
        and -90.0 <= dec_degrees <= 90.0
        and radius_deg > 0
        and math.isfinite(radius_deg)
    ):
        raise ExoplanetLookupError("Invalid solved-field coordinates.")
    radius = min(5.0, float(radius_deg))
    path = _field_cache_path(ra_degrees, dec_degrees, radius)
    cached = _read_field_cache(path)
    if cached is not None and (cached[1] < _FIELD_CACHE_FRESH_S or not allow_network):
        return cached[0]
    if not allow_network:
        return cached_exoplanet_hosts_in_cone(ra_degrees, dec_degrees, radius)
    query = (
        "select pl_name,hostname,ra,dec,sy_vmag,sy_gaiamag,sy_jmag from pscomppars where "
        "contains(point('icrs',ra,dec),"
        f"circle('icrs',{ra_degrees:.8f},{dec_degrees:.8f},{radius:.8f}))=1"
    )
    sender = session.get if session is not None else requests.get
    try:
        response = sender(_TAP_URL, params={"query": query, "format": "json"}, timeout=timeout_s)
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError) as exc:
        if cached is not None:
            return cached[0]
        raise ExoplanetLookupError("NASA field catalogue is unavailable.") from exc
    hosts: dict[tuple[str, float, float], tuple[str, list[str], dict[str, float]]] = {}
    if not isinstance(rows, list):
        raise ExoplanetLookupError("NASA returned an invalid field catalogue.")
    for row in rows:
        try:
            host = str(row["hostname"]).strip()
            planet = str(row["pl_name"]).strip()
            ra = float(row["ra"])
            dec = float(row["dec"])
        except (KeyError, TypeError, ValueError):
            continue
        if not host or not planet:
            continue
        key = (host.casefold(), ra, dec)
        if key not in hosts:
            mags: dict[str, float] = {}
            for band, column in (("V", "sy_vmag"), ("Gaia G", "sy_gaiamag"), ("J", "sy_jmag")):
                try:
                    value = float(row[column])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(value):
                    mags[band] = value
            hosts[key] = (host, [], mags)
        hosts[key][1].append(planet)
    result = [
        CachedExoplanetHost(
            host,
            key[1],
            key[2],
            tuple(sorted(set(planets))),
            tuple(sorted(mags.items())),
        )
        for key, (host, planets, mags) in hosts.items()
    ]
    _write_field_cache(path, result)
    return result


def _cache_key(query: str) -> str:
    return re.sub(r"[^a-z0-9]", "", query.casefold())


def normalize_exoplanet_designation(query: str) -> str:
    """Accept common compact/case-insensitive planet designations.

    ``hd189733b``, ``HD 189733 B`` and ``hd 189733 b`` all become
    ``HD 189733 b``.  Other designations retain their internal spelling while
    whitespace is made predictable for the archive and local cache.
    """
    value = " ".join(query.strip().split())
    match = re.fullmatch(r"([A-Za-z]+)\s*(\d+)\s*([A-Za-z])?", value)
    if not match:
        return value
    prefix, number, letter = match.groups()
    return f"{prefix.upper()} {number}{(' ' + letter.lower()) if letter else ''}"


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
        # A read-only home directory must not turn a successful lookup into a failure.
        pass


def cached_exoplanet_suggestions(
    query: str, *, cache_path: Path | None = None, limit: int = 8
) -> list[str]:
    """Return offline autocomplete candidates from previously fetched planets."""
    cache_path = cache_path or _CACHE_PATH
    needle = _cache_key(query)
    if not needle:
        return []
    names = {
        str(row.get("planet_name", "")).strip()
        for row in _read_cache(cache_path).values()
        if isinstance(row, dict) and needle in _cache_key(str(row.get("planet_name", "")))
    }
    return sorted(name for name in names if name)[:limit]


def _number(row: dict, key: str, *, required: bool = False) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        if required:
            raise ExoplanetLookupError(f"The catalogue has no {key} for this planet.")
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        if required:
            raise ExoplanetLookupError(f"The catalogue returned an invalid {key} value.") from exc
        return None


def _from_row(row: dict, query: str) -> ExoplanetTarget:
    try:
        planet = str(row["pl_name"]).strip()
        host = str(row["hostname"]).strip()
    except (KeyError, TypeError) as exc:
        raise ExoplanetLookupError(
            f"No confirmed transiting planet named ‘{query}’ was found."
        ) from exc
    if not planet or not host:
        raise ExoplanetLookupError(f"No confirmed transiting planet named ‘{query}’ was found.")
    ra = _number(row, "ra", required=True)
    dec = _number(row, "dec", required=True)
    period = _number(row, "pl_orbper", required=True)
    epoch = _number(row, "pl_tranmid", required=True)
    if not (0 <= ra < 360 and -90 <= dec <= 90 and period > 0 and epoch > 2_000_000):
        raise ExoplanetLookupError("The catalogue returned an unusable transit ephemeris.")
    system = str(row.get("pl_tranmid_systemref") or "").strip()
    normalized_system = system.upper().replace("-", "_").replace(" ", "_")
    if "BJD" not in normalized_system or "TDB" not in normalized_system:
        raise ExoplanetLookupError(
            "The published transit epoch is not explicitly BJD_TDB; Argos will not "
            "silently convert it. Choose an ephemeris with a BJD_TDB reference."
        )
    return ExoplanetTarget(
        planet_name=planet,
        host_name=host,
        ra_degrees=ra,
        dec_degrees=dec,
        period_days=period,
        epoch_bjd_tdb=epoch,
        duration_hours=_number(row, "pl_trandur"),
        depth_percent=_number(row, "pl_trandep"),
        period_error_days=_number(row, "pl_orbpererr1"),
        epoch_error_days=_number(row, "pl_tranmiderr1"),
        epoch_system=system,
        retrieved_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def lookup_exoplanet(
    query: str,
    *,
    timeout_s: float = 12.0,
    cache_path: Path | None = None,
) -> ExoplanetTarget:
    """Fetch a confirmed planet's ephemeris from NASA's ``pscomppars`` table.

    The query intentionally asks for only the columns Argos shows and stores.
    A cached exact name is preferred; clearing the local cache is the explicit
    way to refresh a previously prepared target.
    """
    cache_path = cache_path or _CACHE_PATH
    query = normalize_exoplanet_designation(query)
    if not query:
        raise ExoplanetLookupError("Enter a planet designation first (for example HD 189733 b).")
    key = _cache_key(query)
    cached = _read_cache(cache_path).get(key)
    if isinstance(cached, dict):
        try:
            return ExoplanetTarget(**cached)
        except (TypeError, ValueError):
            pass

    # PSCompPars contains one preferred, homogenised row per confirmed planet.
    columns = (
        "pl_name,hostname,ra,dec,pl_orbper,pl_orbpererr1,pl_tranmid,"
        "pl_tranmiderr1,pl_tranmid_systemref,pl_trandur,pl_trandep"
    )
    safe_query = query.replace("'", "''")
    sql = f"select {columns} from pscomppars " f"where lower(pl_name) = lower('{safe_query}')"
    try:
        response = requests.get(
            _TAP_URL, params={"query": sql, "format": "json"}, timeout=timeout_s
        )
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ExoplanetLookupError(
            "NASA Exoplanet Archive is unavailable. Connect to the internet or use a cached planet."
        ) from exc
    if not isinstance(rows, list) or not rows:
        # The archive is also the authoritative autocomplete fallback.  A
        # compact partial designation (e.g. ``hd18973``) resolves to its first
        # matching confirmed planet instead of making the observer guess spaces
        # and case at the telescope.
        compact = query.replace(" ", "")
        prefix = re.match(r"([A-Za-z]+)(\d+)", compact)
        if prefix is None:
            raise ExoplanetLookupError(f"No confirmed transiting planet named ‘{query}’ was found.")
        pattern = f"{prefix.group(1).upper()} {prefix.group(2)}%".replace("'", "''")
        partial_sql = (
            f"select {columns} from pscomppars where lower(pl_name) like lower('{pattern}')"
        )
        try:
            response = requests.get(
                _TAP_URL, params={"query": partial_sql, "format": "json"}, timeout=timeout_s
            )
            response.raise_for_status()
            rows = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ExoplanetLookupError("NASA Exoplanet Archive search failed.") from exc
    if not isinstance(rows, list) or not rows:
        raise ExoplanetLookupError(f"No confirmed transiting planet named ‘{query}’ was found.")
    result = _from_row(rows[0], query)
    cache = _read_cache(cache_path)
    cache[key] = asdict(result)
    _write_cache(cache_path, cache)
    return result
