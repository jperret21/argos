"""Session metadata file — ``session.json`` at the root of each session folder.

CLAUDE.md §6 calls for a JSON manifest alongside the FITS frames that records
*what* was acquired and *why*: target, profile, observer/site, the frames
themselves, weather notes. This is the file the post-processing pipeline
opens first to understand the session — no database, just a file.

The schema is intentionally flat and permissive: missing fields read back as
``None`` rather than raising. We bump ``SCHEMA_VERSION`` only when an existing
field changes meaning; new fields are additive.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from seercontrol.core.targets.resolver import Target

logger = logging.getLogger(__name__)


SCHEMA_VERSION = 1
SESSION_FILENAME = "session.json"

_DATETIME_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass
class Session:
    """Single observing session: one target, one profile, N frames."""

    target_name:        str
    target_ra_hours:    float
    target_dec_degrees: float
    target_type:        str = ""
    target_magnitude:   float | None = None

    profile_name:    str = ""
    profile_summary: str = ""

    started_at_utc:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at_utc: datetime | None = None

    observer:  str = ""
    site_lat:  float | None = None
    site_lon:  float | None = None
    site_elev: float | None = None

    frames_planned:  int = 0
    frames_acquired: int = 0
    frames_paths:    list[str] = field(default_factory=list)

    weather: dict = field(default_factory=dict)
    notes:   str  = ""

    software: str = "SeerControl"
    schema_version: int = SCHEMA_VERSION

    # ------------------------------------------------------------------
    # Constructors                                                       #
    # ------------------------------------------------------------------

    @classmethod
    def from_target(
        cls,
        target: Target,
        profile_name: str,
        profile_summary: str = "",
        frames_planned: int = 0,
        observer: str = "",
        site_lat: float | None = None,
        site_lon: float | None = None,
        site_elev: float | None = None,
        software: str = "SeerControl",
    ) -> "Session":
        return cls(
            target_name=target.name,
            target_ra_hours=target.ra_hours,
            target_dec_degrees=target.dec_degrees,
            target_type=target.object_type,
            target_magnitude=target.magnitude,
            profile_name=profile_name,
            profile_summary=profile_summary,
            frames_planned=frames_planned,
            observer=observer,
            site_lat=site_lat, site_lon=site_lon, site_elev=site_elev,
            software=software,
        )

    # ------------------------------------------------------------------
    # Mutators                                                           #
    # ------------------------------------------------------------------

    def record_frame(self, path: Path) -> None:
        self.frames_acquired += 1
        self.frames_paths.append(str(path))

    def finish(self) -> None:
        self.finished_at_utc = datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Persistence                                                                  #
# --------------------------------------------------------------------------- #

def write_session_json(folder: Path, session: Session) -> Path:
    """Serialise ``session`` to ``folder/session.json``. Returns the path written."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SESSION_FILENAME
    path.write_text(json.dumps(_to_json(session), indent=2, sort_keys=True))
    return path


def load_session_json(folder_or_file: Path) -> Session | None:
    """Read a session.json. Accepts either the folder or the file directly."""
    path = folder_or_file
    if path.is_dir():
        path = path / SESSION_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read session %s: %s", path, exc)
        return None
    return _from_json(data)


# --------------------------------------------------------------------------- #
# JSON conversion                                                              #
# --------------------------------------------------------------------------- #

def _to_json(s: Session) -> dict:
    raw = asdict(s)
    raw["started_at_utc"]  = _fmt_dt(s.started_at_utc)
    raw["finished_at_utc"] = _fmt_dt(s.finished_at_utc) if s.finished_at_utc else None
    return raw


def _from_json(data: dict) -> Session:
    return Session(
        target_name=str(data.get("target_name", "")),
        target_ra_hours=float(data.get("target_ra_hours", 0.0)),
        target_dec_degrees=float(data.get("target_dec_degrees", 0.0)),
        target_type=str(data.get("target_type", "")),
        target_magnitude=_optional_float(data.get("target_magnitude")),
        profile_name=str(data.get("profile_name", "")),
        profile_summary=str(data.get("profile_summary", "")),
        started_at_utc=_parse_dt(data.get("started_at_utc")) or datetime.now(timezone.utc),
        finished_at_utc=_parse_dt(data.get("finished_at_utc")),
        observer=str(data.get("observer", "")),
        site_lat=_optional_float(data.get("site_lat")),
        site_lon=_optional_float(data.get("site_lon")),
        site_elev=_optional_float(data.get("site_elev")),
        frames_planned=int(data.get("frames_planned", 0)),
        frames_acquired=int(data.get("frames_acquired", 0)),
        frames_paths=[str(p) for p in data.get("frames_paths", [])],
        weather=dict(data.get("weather", {})),
        notes=str(data.get("notes", "")),
        software=str(data.get("software", "SeerControl")),
        schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
    )


def _fmt_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(_DATETIME_FMT)


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, _DATETIME_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        # Permissive fallback for ISO-with-second-precision strings.
        try:
            return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
