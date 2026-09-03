"""Small, cache-backed Gaia DR3 field-star queries for solved Argos frames.

Gaia is used here for *identification and navigation only*: it supplies a
stable source identifier, position and G magnitude for stars visible in the
solved field. It does not replace AAVSO VSP calibrated comparison sequences.
The query is intentionally narrow (position, magnitude and a row cap) and its
CSV response is cached locally for offline re-use.
"""

from __future__ import annotations

import csv
import hashlib
import math
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import requests

from argos.core.catalog.aavso import CatalogError

# ESA's public Gaia Archive TAP endpoint. TAP synchronous requests are POSTed
# (the archive's documented programmatic-access form) so the ADQL query never
# becomes a very long URL at a telescope network proxy.
_TAP_SYNC_URL = "https://gea.esac.esa.int/tap-server/tap/sync"
_CACHE_DIR = Path.home() / ".argos" / "cache" / "gaia"
_CACHE_FRESH_S = 30 * 86400.0
_DEFAULT_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class GaiaStar:
    """A Gaia DR3 source projected onto a solved field."""

    source_id: str
    ra_deg: float
    dec_deg: float
    g_mag: float | None = None
    bp_mag: float | None = None
    rp_mag: float | None = None

    @property
    def display_name(self) -> str:
        return f"Gaia DR3 {self.source_id}"


def configure_cache_directory(path: Path | str) -> None:
    """Set the local directory used for Gaia field-query responses."""
    global _CACHE_DIR
    _CACHE_DIR = Path(path).expanduser()


def _cache_path(params: dict[str, str]) -> Path:
    digest = hashlib.sha256(repr(sorted(params.items())).encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{digest}.csv"


def _load_cache(path: Path) -> tuple[str, float] | None:
    try:
        return path.read_text(encoding="utf-8"), time.time() - path.stat().st_mtime
    except OSError:
        return None


def _store_cache(path: Path, body: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    except OSError:
        # A cache must never make an otherwise successful catalogue query fail.
        return


def _parse_csv(body: str) -> list[GaiaStar]:
    stars: list[GaiaStar] = []
    try:
        rows = csv.DictReader(StringIO(body))
        for row in rows:
            source_id = str(row.get("source_id") or "").strip()
            if not source_id:
                continue
            try:
                g_mag_raw = row.get("phot_g_mean_mag")
                bp_mag_raw = row.get("phot_bp_mean_mag")
                rp_mag_raw = row.get("phot_rp_mean_mag")
                stars.append(
                    GaiaStar(
                        source_id=source_id,
                        ra_deg=float(row["ra"]),
                        dec_deg=float(row["dec"]),
                        g_mag=float(g_mag_raw) if g_mag_raw not in (None, "") else None,
                        bp_mag=float(bp_mag_raw) if bp_mag_raw not in (None, "") else None,
                        rp_mag=float(rp_mag_raw) if rp_mag_raw not in (None, "") else None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    except csv.Error as exc:
        raise CatalogError(f"Gaia returned invalid CSV: {exc}") from exc
    return stars


def gaia_cone_search(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    *,
    mag_limit: float = 13.5,
    max_results: int = 200,
    allow_network: bool = True,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    session: Any = None,
) -> list[GaiaStar]:
    """Return the brightest Gaia DR3 sources in a field cone.

    Values are validated before being interpolated in ADQL, and only four
    columns are requested from Gaia DR3 to keep the response compact.
    """
    if not (-90.0 <= dec_deg <= 90.0) or radius_deg <= 0:
        raise CatalogError("invalid Gaia field coordinates")
    try:
        limit = max(1, min(5000, int(max_results)))
        magnitude = float(mag_limit)
    except (TypeError, ValueError) as exc:
        raise CatalogError("invalid Gaia magnitude or result limit") from exc
    if not math.isfinite(magnitude):
        raise CatalogError("invalid Gaia magnitude limit")
    ra = float(ra_deg) % 360.0
    radius = min(5.0, float(radius_deg))
    if not math.isfinite(radius):
        raise CatalogError("invalid Gaia field radius")
    query = (
        f"SELECT TOP {limit} source_id, ra, dec, phot_g_mean_mag, "
        "phot_bp_mean_mag, phot_rp_mean_mag "
        "FROM gaiadr3.gaia_source "
        "WHERE CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra:.8f}, {float(dec_deg):.8f}, {radius:.8f})) = 1 "
        f"AND phot_g_mean_mag <= {magnitude:.3f} "
        "ORDER BY phot_g_mean_mag ASC"
    )
    params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query}
    path = _cache_path(params)
    cached = _load_cache(path)
    if cached is not None and (cached[1] < _CACHE_FRESH_S or not allow_network):
        return _parse_csv(cached[0])
    if not allow_network:
        return []
    sender = session.post if session is not None else requests.post
    try:
        response = sender(_TAP_SYNC_URL, data=params, timeout=timeout_s)
        response.raise_for_status()
        body = response.text
    except requests.RequestException as exc:
        if cached is not None:
            return _parse_csv(cached[0])
        raise CatalogError(f"Gaia catalogue request failed: {exc}") from exc
    stars = _parse_csv(body)
    _store_cache(path, body)
    return stars
