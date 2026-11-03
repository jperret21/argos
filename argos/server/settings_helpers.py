"""Settings helpers: ASTAP detection, catalogue caches, place search (A81-A84).

Each is a Qt-free port of what the Qt Settings page does inline:

- :func:`astap_state` — ``ConfigurationPage._refresh_astap_status``
  (``configuration_page.py:1208-1231``) on ``find_astap`` / ``find_astap_db``
  / ``_database_args`` (``platesolve.py:119-144, 305-319``), with the
  database choice of ``astrometry_session.py:64`` (a folder wins over a set);
- :func:`cache_records` / :func:`clear_cache` —
  ``_refresh_catalogue_cache_status`` / ``_clear_catalogue_cache``
  (``configuration_page.py:1104-1163``): same five caches, same globs;
- :func:`search_places` — ``search_locations`` (``location_resolver.py:34-87``)
  with the User-Agent from the running version, an injectable HTTP getter
  (tests never reach the network) and a cancel check between requests.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from argos import __version__
from argos.core.imaging import platesolve
from argos.server.errors import ApiError

# ---------------------------------------------------------------------------
# ASTAP (A81)
# ---------------------------------------------------------------------------


def _has_database(folder: Path) -> bool:
    try:
        return folder.is_dir() and any(
            next(folder.glob(pattern), None) is not None for pattern in platesolve._ASTAP_DB_GLOBS
        )
    except OSError:
        return False


def astap_state(path: str, database_path: str, database: str) -> dict[str, Any]:
    """``GET /api/astrometry/astap`` (``protocol.md`` "ASTAP detection")."""
    configured = (path or "").strip()
    folder_text = (database_path or "").strip()
    database = (database or "").strip()
    configured_found = bool(configured) and Path(configured).expanduser().is_file()
    astap = platesolve.find_astap(str(Path(configured).expanduser()) if configured else "")
    # astrometry_session.py:64: the folder, when set, wins over the set.
    chosen = folder_text or database
    args = platesolve._database_args(astap or "", chosen)
    database_dir: str | None = None
    source: str | None = None
    if folder_text:
        database_dir = str(Path(folder_text).expanduser())
        source = "configured"
        found = _has_database(Path(database_dir))
    else:
        detected = platesolve.find_astap_db(astap or "")
        database_dir, source = (detected, "detected") if detected else (None, None)
        found = detected is not None
    if astap is None:
        message = "ASTAP not found — install it or set the path above"
    elif folder_text:
        state = "Star database" if found else "Star database not found in"
        message = f"ASTAP detected: {astap} · {state}: {database_dir}"
    elif database_dir:
        message = f"ASTAP detected: {astap} · Star database: {database_dir}"
    else:
        message = f"ASTAP detected: {astap} · Star database not detected"
    if configured and not configured_found:
        message += f" · {configured} is not a file: auto-detected instead"
    if folder_text and database:
        message += f" · Database set {database} ignored while a folder is set"
    return {
        "astap": astap,
        "configured": configured,
        "configured_found": configured_found,
        "database_dir": database_dir,
        "database_source": source,
        "database_found": found,
        "database": database,
        "database_ignored": bool(folder_text and database),
        "database_args": list(args),
        "message": message,
    }


# ---------------------------------------------------------------------------
# Catalogue caches (A83)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheKind:
    kind: str
    label: str
    key: str
    path_kind: str  # "file" | "dir"
    #: Folder caches: the full-match pattern of the file names the cache itself
    #: writes (a hash digest), so Clear never deletes a file ARGOS did not write.
    pattern: str | None
    #: Folder caches written one level down (``simbad/``, ``nasa/``); empty: the folder.
    subdirs: tuple[str, ...] = ()


#: configuration_page.py:1104-1163. The Qt page clears every ``*.json`` / ``*.csv``
#: of the folder (recursively for the field-identities cache,
#: configuration_page.py:1149-1152); with the in-app FilePicker any folder of
#: the home is one click away as a cache location, so the server clears only
#: the names each cache writes: ``aavso.py:188-189`` (SHA-1 hex ``.json``),
#: ``gaia.py:57-58`` (SHA-256 hex ``.csv``), ``field_objects.py:52,66`` and
#: ``exoplanets.py:37,91`` (SHA-256 hex ``.json`` in ``simbad/`` and ``nasa/``).
CACHE_KINDS: tuple[CacheKind, ...] = (
    CacheKind("object", "CDS/SIMBAD target-name cache", "data_paths.object_catalogue_cache",
              "file", None),
    CacheKind("exoplanet", "NASA exoplanet ephemeris cache", "data_paths.exoplanet_cache",
              "file", None),
    CacheKind("aavso", "AAVSO VSX/VSP field cache", "data_paths.aavso_cache_directory",
              "dir", r"[0-9a-f]{40}\.json"),
    CacheKind("gaia", "Gaia DR3 field-star cache", "data_paths.gaia_cache_directory",
              "dir", r"[0-9a-f]{64}\.csv"),
    CacheKind("field_catalogue", "SIMBAD / NASA field-identification cache",
              "data_paths.field_catalogue_cache_directory", "dir", r"[0-9a-f]{64}\.json",
              subdirs=("simbad", "nasa")),
)  # fmt: skip
CACHES = {c.kind: c for c in CACHE_KINDS}


def _cache_files(kind: CacheKind, path: Path) -> list[Path]:
    if kind.path_kind == "file":
        return [path] if path.is_file() and not path.is_symlink() else []
    if not path.is_dir():
        return []
    name = re.compile(kind.pattern or r"(?!)")
    files: list[Path] = []
    for folder in [path / sub for sub in kind.subdirs] or [path]:
        if folder.is_symlink() or not folder.is_dir():
            continue  # a linked subfolder could lead outside: never followed
        with os.scandir(folder) as it:
            files += [Path(e.path) for e in it if name.fullmatch(e.name)]
    return [f for f in files if f.is_file() and not f.is_symlink()]


def _cache_path(kind: CacheKind, get: Callable[[str, Any], Any]) -> Path:
    return Path(str(get(kind.key, "") or "")).expanduser()


def cache_record(kind: CacheKind, get: Callable[[str, Any], Any]) -> dict[str, Any]:
    path = _cache_path(kind, get)
    try:
        files = _cache_files(kind, path)
        size = sum(f.stat().st_size for f in files)
    except OSError:
        files, size = [], 0
    return {
        "kind": kind.kind,
        "label": kind.label,
        "key": kind.key,
        "path": str(path),
        "path_kind": kind.path_kind,
        "exists": path.exists(),
        "files": len(files),
        "bytes": size,
    }


def cache_records(get: Callable[[str, Any], Any]) -> list[dict[str, Any]]:
    return [cache_record(kind, get) for kind in CACHE_KINDS]


def clear_cache(kind_name: str, get: Callable[[str, Any], Any]) -> tuple[dict[str, Any], int]:
    """Delete the cached responses of one kind; returns ``(record, removed)``."""
    kind = CACHES.get(kind_name)
    if kind is None:
        known = ", ".join(CACHES)
        raise ApiError(404, "not_found", f"Unknown cache {kind_name!r} (known: {known})")
    removed = 0
    try:
        for path in _cache_files(kind, _cache_path(kind, get)):
            path.unlink(missing_ok=True)
            removed += 1
    except OSError as exc:
        raise ApiError(
            500, "internal_error", f"Could not clear the {kind.label}: {exc.strerror or exc}"
        ) from exc
    return cache_record(kind, get), removed


# ---------------------------------------------------------------------------
# Place search (A82)
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
PLACE_TIMEOUT_S = 8.0
USER_AGENT = f"Argos/{__version__} (astronomical observing-site search)"

#: ``(url, params, headers, timeout_s) -> decoded JSON``; raises on failure.
HttpGet = Callable[[str, dict[str, Any], dict[str, str], float], Any]


def requests_get(url: str, params: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    import requests

    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


class LookupFailed(Exception):
    """No usable answer from the network (job error ``lookup_failed``)."""


class PlaceNotFound(Exception):
    """The query matched nothing usable (job error ``not_found``)."""


def _interruptible(
    fn: Callable[[], Any], cancel: threading.Event | None, poll_s: float = 0.1
) -> Any:
    """Run *fn* on a helper thread; return its value, or ``None`` once cancelled."""
    if cancel is None:
        return fn()
    box: dict[str, Any] = {}
    done = threading.Event()

    def run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # handed back to the caller
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=run, name="argos-place-http", daemon=True).start()
    while not done.wait(poll_s):
        if cancel.is_set():
            return None  # the answer, when it comes, is dropped
    if "error" in box:
        raise box["error"]
    return box.get("value")


def search_places(
    query: str,
    *,
    http_get: HttpGet = requests_get,
    timeout_s: float = PLACE_TIMEOUT_S,
    cancel: threading.Event | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Port of ``search_locations`` (location_resolver.py:34-87)."""
    query = " ".join(query.split())
    headers = {"User-Agent": USER_AGENT}
    params = {"q": query, "format": "jsonv2", "limit": 5, "addressdetails": 0}
    if progress:
        progress(0, 1, "search")
    try:
        matches = _interruptible(
            lambda: http_get(NOMINATIM_URL, params, headers, timeout_s), cancel
        )
    except Exception as exc:
        raise LookupFailed(
            "Location search is unavailable. Check your internet connection."
        ) from exc
    if cancel is not None and cancel.is_set():
        return []
    if not isinstance(matches, list) or not matches:
        raise PlaceNotFound(f"No place found for ‘{query}’.")
    places: list[dict[str, Any]] = []
    usable = []
    for match in matches:
        try:
            latitude = float(match["lat"])
            longitude = float(match["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue
        usable.append((str(match.get("display_name") or query), latitude, longitude))
    if not usable:
        raise PlaceNotFound(f"No usable coordinates found for ‘{query}’.")
    total = len(usable) + 1
    for index, (label, latitude, longitude) in enumerate(usable, start=1):
        if progress:
            progress(index, total, "elevation")
        if cancel is not None and cancel.is_set():
            return []
        elevation = _elevation(latitude, longitude, http_get, headers, timeout_s, cancel)
        places.append(
            {"label": label, "latitude": latitude, "longitude": longitude,
             "elevation_m": elevation}
        )  # fmt: skip
    return places


def _elevation(
    latitude: float,
    longitude: float,
    http_get: HttpGet,
    headers: dict[str, str],
    timeout_s: float,
    cancel: threading.Event | None,
) -> float | None:
    """location_resolver.py:72-87: a terrain estimate; a failure never rejects the place."""
    try:
        payload = _interruptible(
            lambda: http_get(
                ELEVATION_URL, {"latitude": latitude, "longitude": longitude}, headers, timeout_s
            ),
            cancel,
        )
        values = payload.get("elevation") if isinstance(payload, dict) else None
        value = values[0] if isinstance(values, list) and values else None
        return float(value) if value is not None else None
    except Exception:
        return None
