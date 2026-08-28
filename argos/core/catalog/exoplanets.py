"""Exoplanet ephemerides from the NASA Exoplanet Archive.

Argos uses this catalogue only to prepare an observing run.  The download is
explicitly requested by the observer and successful results are cached locally
so a prepared target remains usable away from the internet.  Transit fitting
and the science-grade light curve remain post-processing work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import requests

_TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
_CACHE_PATH = Path.home() / "Argos" / "cache" / "exoplanets.json"


def configure_cache_path(path: Path | str) -> None:
    """Set the persistent NASA ephemeris cache location for future lookups."""
    global _CACHE_PATH
    _CACHE_PATH = Path(path).expanduser()


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
