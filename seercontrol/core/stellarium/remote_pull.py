"""Read the currently-selected sky object from a running Stellarium.

Stellarium ships a "Remote Control" plugin that, once enabled by the user,
serves an HTTP REST API on ``localhost:8090``. ``GET /api/objects/info``
returns the object currently selected in the planetarium — handy as a
one-click way to send a target to SeerControl without typing coordinates.

Single function, single HTTP call, sub-2-second timeout. Failure modes
(plugin disabled, Stellarium not running, nothing selected) all return
``None`` so the caller can show a friendly UI message instead of crashing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class StellariumTarget:
    """Snapshot of the object selected in Stellarium when we asked."""

    name: str            # localized or canonical name as reported by Stellarium
    ra_hours: float      # J2000 right ascension in decimal hours
    dec_degrees: float   # J2000 declination in decimal degrees
    magnitude: float | None = None


def pull_selected_object(
    host: str = "127.0.0.1",
    port: int = 8090,
    timeout_s: float = 2.0,
) -> StellariumTarget | None:
    """Fetch the object currently selected in Stellarium.

    Returns ``None`` when:
      - the Remote Control plugin is not enabled in Stellarium
      - Stellarium is not running on ``host:port``
      - no object is currently selected
      - the response is missing J2000 coordinates

    Args:
        host:      Hostname or IP of the machine running Stellarium.
        port:      Port the Remote Control plugin listens on (8090 default).
        timeout_s: HTTP timeout — kept short so the UI stays responsive.
    """
    url = f"http://{host}:{port}/api/objects/info"
    try:
        resp = requests.get(url, params={"format": "json"}, timeout=timeout_s)
    except requests.RequestException as exc:
        logger.info("Stellarium pull failed: %s", exc)
        return None

    if resp.status_code != 200:
        logger.info("Stellarium pull HTTP %d: %s", resp.status_code, resp.text[:120])
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.info("Stellarium pull: non-JSON response")
        return None

    if not isinstance(data, dict) or not data:
        return None

    # Stellarium exposes both current-epoch (ra/dec) and J2000 fields under
    # slightly different keys depending on plugin version.
    ra_deg = _first_present(data, "raJ2000", "ra-J2000", "ra_j2000")
    dec_deg = _first_present(data, "decJ2000", "dec-J2000", "dec_j2000")
    if ra_deg is None or dec_deg is None:
        # Some Stellarium builds only emit current-epoch ra/dec — degrade gracefully.
        ra_deg = _first_present(data, "ra")
        dec_deg = _first_present(data, "dec")
    if ra_deg is None or dec_deg is None:
        return None

    name = (
        data.get("localized-name")
        or data.get("name")
        or data.get("designations", "Unknown")
    )
    mag = _first_present(data, "vmag", "vmage", "mag")

    return StellariumTarget(
        name=str(name)[:60],
        ra_hours=float(ra_deg) / 15.0,
        dec_degrees=float(dec_deg),
        magnitude=float(mag) if mag is not None else None,
    )


def _first_present(data: dict, *keys: str):
    """Return the first non-None value among ``keys`` in ``data``, else None."""
    for k in keys:
        v = data.get(k)
        if v is not None:
            return v
    return None
