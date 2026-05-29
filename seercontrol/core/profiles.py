"""Acquisition profiles — opinionated presets the user picks in the wizard.

A *profile* bundles the few parameters that actually differ between session
types (number of frames, exposure, gain, filter, frame type, continuous-vs-
batch). The wizard pre-fills the capture form from a profile so the user can
hit START without tweaking individual fields.

Built-in profiles cover the scientific cases SeerControl is designed for —
variable-star photometry and exoplanet transits — plus a generic deep-sky
preset for visual imaging. User additions live in
``~/.seercontrol/profiles.json`` and are merged on top of the built-ins.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# Average per-frame overhead in seconds: download + save + small mount settle.
# Empirically the ImageBytes path adds ~3 s; we round up to be safe in ETA.
_FRAME_OVERHEAD_S = 4.0

# IMX585 raw frame footprint on disk (uint16 FITS, ~8.3 MP).
_FRAME_SIZE_MB = 16.6

_USER_PROFILES_PATH = Path.home() / ".seercontrol" / "profiles.json"


@dataclass(frozen=True)
class Profile:
    """A named acquisition plan.

    Attributes:
        name:        Short display name (one line).
        description: One-sentence hint shown next to the name in the wizard.
        frame_type:  FITS IMAGETYP value ('Light Frame', 'Dark Frame', ...).
        exposure_s:  Per-frame exposure in seconds.
        gain:        Camera gain setting (0-600 on the Seestar S30 Pro).
        filter_name: Filter wheel slot label ('LP', 'IR-cut', 'Ha', ...).
        frames:      Number of frames to acquire.
        continuous:  When True, the wizard treats the sequence as a long
                     monitoring run (e.g. transit) — no manual pauses, the
                     "Take darks now?" prompt is suppressed at the end.
        tags:        Free-form tags (e.g. {"variable", "photometry"}) used to
                     decide which extra checks the wizard runs (FOV check
                     against APASS for "photometry" tags, etc.).
    """

    name: str
    description: str
    frame_type: str
    exposure_s: float
    gain: int
    filter_name: str
    frames: int
    continuous: bool = False
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def total_duration_s(self) -> float:
        """Wall-clock estimate for the full session."""
        return (self.exposure_s + _FRAME_OVERHEAD_S) * self.frames

    @property
    def estimated_size_mb(self) -> float:
        return self.frames * _FRAME_SIZE_MB

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "description": self.description,
            "frame_type":  self.frame_type,
            "exposure_s":  self.exposure_s,
            "gain":        self.gain,
            "filter_name": self.filter_name,
            "frames":      self.frames,
            "continuous":  self.continuous,
            "tags":        sorted(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            frame_type=str(data.get("frame_type", "Light Frame")),
            exposure_s=float(data["exposure_s"]),
            gain=int(data["gain"]),
            filter_name=str(data.get("filter_name", "LP")),
            frames=int(data["frames"]),
            continuous=bool(data.get("continuous", False)),
            tags=frozenset(str(t) for t in data.get("tags", ())),
        )


# --------------------------------------------------------------------------- #
# Built-in profiles                                                            #
# --------------------------------------------------------------------------- #

_BUILTIN: tuple[Profile, ...] = (
    Profile(
        name="Variable star — CV outburst",
        description="60 × 30 s, LP filter, gain 80 — cadence for cataclysmic variables under outburst.",
        frame_type="Light Frame",
        exposure_s=30.0,
        gain=80,
        filter_name="LP",
        frames=60,
        tags=frozenset({"variable", "photometry"}),
    ),
    Profile(
        name="Variable star — LPV",
        description="30 × 60 s, IR-cut, gain 80 — slower cadence for long-period variables.",
        frame_type="Light Frame",
        exposure_s=60.0,
        gain=80,
        filter_name="IR-cut",
        frames=30,
        tags=frozenset({"variable", "photometry"}),
    ),
    Profile(
        name="Exoplanet transit (continuous)",
        description="200 × 20 s, IR-cut, gain 80 — high-cadence run across an ingress/egress.",
        frame_type="Light Frame",
        exposure_s=20.0,
        gain=80,
        filter_name="IR-cut",
        frames=200,
        continuous=True,
        tags=frozenset({"transit", "photometry"}),
    ),
    Profile(
        name="Deep sky — wide",
        description="60 × 60 s, LRGB, gain 80 — generic deep-sky imaging.",
        frame_type="Light Frame",
        exposure_s=60.0,
        gain=80,
        filter_name="LRGB",
        frames=60,
        tags=frozenset({"deepsky"}),
    ),
)


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def builtin_profiles() -> list[Profile]:
    """Return a fresh list of the built-in profiles."""
    return list(_BUILTIN)


def load_profiles(user_path: Path | None = None) -> list[Profile]:
    """Return built-in profiles merged with the user's JSON overrides.

    User entries with the same ``name`` as a built-in replace the built-in.
    Missing or unreadable user file is silently ignored — the wizard always
    has at least the built-ins available.
    """
    path = user_path or _USER_PROFILES_PATH
    by_name: dict[str, Profile] = {p.name: p for p in _BUILTIN}

    if not path.is_file():
        return list(by_name.values())

    try:
        entries = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read user profiles %s: %s", path, exc)
        return list(by_name.values())

    if not isinstance(entries, list):
        logger.warning("User profiles file must contain a JSON list, got %s", type(entries).__name__)
        return list(by_name.values())

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            p = Profile.from_dict(entry)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed user profile entry: %s", exc)
            continue
        by_name[p.name] = p

    return list(by_name.values())


def find_profile(name: str, profiles: list[Profile] | None = None) -> Profile | None:
    """Look up a profile by name. Falls back to the built-ins if none given."""
    for p in (profiles if profiles is not None else load_profiles()):
        if p.name == name:
            return p
    return None
