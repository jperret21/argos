"""Resolve a target name (e.g. ``"M 42"``, ``"T CrB"``) to J2000 coords.

Uses the Simbad sim-script endpoint over HTTP — same approach as the
varstar-postprod pipeline. No astroquery dependency: the format we receive
is fully controlled by the script we send, so a 30-line regex parser is all
we need.

Results are cached on disk so the same name doesn't keep hitting Simbad on
every wizard run. The cache is keyed by the *normalized* input (uppercase,
collapsed whitespace) and never expires; clear it manually if a target's
catalogued position changes (very rare for the photometric targets we care
about).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


SIMBAD_URL = "https://simbad.cds.unistra.fr/simbad/sim-script"

# Pipe-separated to keep parsing trivial; %~ avoids the literal '|' inside fields.
_SIMBAD_SCRIPT = (
    'output console=off script=off error=merge\n'
    'format object "##|%MAIN_ID|%COO(d;A)|%COO(d;D)|%OTYPE_S|%FLUXLIST(V)[%5.2(F)]|##"\n'
    'query id {name}\n'
)

_RESULT_RE = re.compile(
    r"##\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|##"
)

_USER_CACHE_PATH = Path.home() / ".seercontrol" / "target_cache.json"


@dataclass(frozen=True)
class Target:
    """A resolved sky target — what the wizard needs to drive a slew."""

    name: str                  # the canonical (Simbad main) identifier
    queried_name: str          # what the user typed (preserved for the log)
    ra_hours: float            # J2000 right ascension in decimal hours
    dec_degrees: float         # J2000 declination in decimal degrees
    object_type: str = ""      # Simbad OTYPE_S (e.g. "Star", "GroupG", "HII")
    magnitude: float | None = None   # V mag if Simbad reports one


def resolve_name(
    name: str,
    *,
    timeout_s: float = 5.0,
    cache_path: Path | None = None,
) -> Target | None:
    """Look up a name. Returns ``None`` when offline or unresolvable."""
    key = _normalize(name)
    if not key:
        return None

    cache_path = cache_path or _USER_CACHE_PATH
    cache = _load_cache(cache_path)
    cached = cache.get(key)
    if cached is not None:
        try:
            return _target_from_dict(cached, queried_name=name)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Discarding malformed cache entry for %s: %s", key, exc)

    try:
        resp = requests.post(
            SIMBAD_URL,
            data={"script": _SIMBAD_SCRIPT.format(name=name)},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        logger.info("Simbad request failed for %s: %s", name, exc)
        return None

    if resp.status_code != 200:
        logger.info("Simbad HTTP %d for %s", resp.status_code, name)
        return None

    target = _parse_simbad_response(resp.text, queried_name=name)
    if target is None:
        return None

    cache[key] = asdict(target)
    # Don't persist the user-typed name in the cache — keep the canonical one.
    cache[key].pop("queried_name", None)
    _save_cache(cache_path, cache)
    return target


# --------------------------------------------------------------------------- #
# Response parsing                                                             #
# --------------------------------------------------------------------------- #

def _parse_simbad_response(text: str, *, queried_name: str) -> Target | None:
    """Pull the pipe-delimited fields out of a sim-script response."""
    # The "::error::" block precedes any data when the lookup failed.
    if "::error::" in text and "Identifier not found" in text:
        return None

    match = _RESULT_RE.search(text)
    if match is None:
        return None
    main_id, ra_str, dec_str, otype, vmag_str = (s.strip() for s in match.groups())

    try:
        ra_deg = float(ra_str)
        dec_deg = float(dec_str)
    except ValueError:
        return None

    mag: float | None = None
    if vmag_str and vmag_str not in {"~", ""}:
        try:
            mag = float(vmag_str)
        except ValueError:
            mag = None

    return Target(
        name=main_id or queried_name,
        queried_name=queried_name,
        ra_hours=ra_deg / 15.0,
        dec_degrees=dec_deg,
        object_type=otype,
        magnitude=mag,
    )


# --------------------------------------------------------------------------- #
# Cache                                                                        #
# --------------------------------------------------------------------------- #

def _normalize(name: str) -> str:
    return " ".join(name.upper().split())


def _load_cache(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read target cache %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(path: Path, cache: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True))
    except OSError as exc:
        logger.warning("Could not write target cache %s: %s", path, exc)


def _target_from_dict(data: dict, *, queried_name: str) -> Target:
    return Target(
        name=str(data["name"]),
        queried_name=queried_name,
        ra_hours=float(data["ra_hours"]),
        dec_degrees=float(data["dec_degrees"]),
        object_type=str(data.get("object_type", "")),
        magnitude=(float(data["magnitude"]) if data.get("magnitude") is not None else None),
    )
