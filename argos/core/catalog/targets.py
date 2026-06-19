"""Persistent target / comparison set for a session (docs/photometry_plan.md §5 B4).

Qt-free. The set is the night's selection: the variable target(s), the comparison
stars, and any check stars, each with RA/Dec + catalog id so they can be projected
onto every solved frame and (later) aperture-measured. Persisted as ``targets.json``
(atomic write, mirrors session_log) so it survives restarts.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

logger = logging.getLogger(__name__)

ROLE_TARGET = "target"
ROLE_COMPARISON = "comparison"
ROLE_CHECK = "check"
ROLES = (ROLE_TARGET, ROLE_COMPARISON, ROLE_CHECK)

SCHEMA = 1


@dataclass
class TargetStar:
    """One selected star, identified by AUID when known else by position."""

    role: str
    ra_deg: float
    dec_deg: float
    auid: str | None = None
    name: str | None = None
    source: str = "manual"  # vsx | vsp | manual
    mags: dict = field(default_factory=dict)  # band -> magnitude
    note: str = ""

    def key(self) -> str:
        """Stable identity used to dedup/update (AUID, else rounded position)."""
        if self.auid:
            return f"auid:{self.auid}"
        return f"pos:{self.ra_deg:.5f},{self.dec_deg:.5f}"

    @property
    def display_name(self) -> str:
        return self.name or self.auid or f"{self.ra_deg:.3f},{self.dec_deg:+.3f}"


@dataclass
class TargetSet:
    """The session's selected stars; load/save ``targets.json``."""

    object_name: str = ""
    stars: list[TargetStar] = field(default_factory=list)

    def set_role(self, star: TargetStar) -> None:
        """Add ``star`` or replace the existing one with the same identity."""
        k = star.key()
        for i, s in enumerate(self.stars):
            if s.key() == k:
                self.stars[i] = star
                return
        self.stars.append(star)

    def remove(self, key: str) -> None:
        self.stars = [s for s in self.stars if s.key() != key]

    def by_role(self, role: str) -> list[TargetStar]:
        return [s for s in self.stars if s.role == role]

    def summary(self) -> dict:
        """A display/readiness summary of the selection (Qt-free).

        Differential photometry needs at least one target (T1) and one
        comparison; a check star is recommended but optional. ``complete``
        captures that minimum so the UI can tell the user what is missing.
        """
        targets = self.by_role(ROLE_TARGET)
        comparisons = self.by_role(ROLE_COMPARISON)
        checks = self.by_role(ROLE_CHECK)
        return {
            "object": self.object_name,
            "target": targets[0].display_name if targets else None,
            "n_target": len(targets),
            "n_comparison": len(comparisons),
            "n_check": len(checks),
            "complete": bool(targets) and bool(comparisons),
        }

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "object": self.object_name, "stars": [asdict(s) for s in self.stars]}

    @classmethod
    def from_dict(cls, d: dict) -> "TargetSet":
        valid = {f.name for f in fields(TargetStar)}
        stars = [TargetStar(**{k: v for k, v in s.items() if k in valid}) for s in d.get("stars", [])]
        return cls(object_name=str(d.get("object", "")), stars=stars)

    def save(self, path) -> None:
        """Atomically write ``targets.json`` (temp + os.replace)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path) -> "TargetSet":
        """Load ``targets.json``; return an empty set if missing/unreadable."""
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:  # corrupt file → start fresh, don't crash
            logger.warning("Could not read %s: %s", path, exc)
            return cls()
