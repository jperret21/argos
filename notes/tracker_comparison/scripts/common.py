"""Shared helpers for the tracker comparison scripts (no personal metadata read).

Every script takes paths as arguments and runs on COPIES of the frames. The
Argos tree imported is the one on ``PYTHONPATH`` (the release/0.5.0 worktree for
the fixed Qt code); the web tracker is loaded from a file path given on the
command line, so the two codebases never mix silently.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import os
from pathlib import Path

from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, TargetSet
from argos.core.imaging.platesolve import FrameWCS

#: Proper motions applied to the truth (``proper_motions.json`` beside this folder).
#: ``TRACKER_STUDY_PM=none`` turns them off (the catalogue position, as before the
#: science review of 2026-11-12).
PROPER_MOTIONS_PATH = Path(__file__).resolve().parent.parent / "proper_motions.json"
J2000_JD = 2451545.0


class Solutions(dict):
    """``frame index -> FrameWCS``, with each frame's exposure midpoint in ``jd`` (JD UTC)."""

    def __init__(self) -> None:
        super().__init__()
        self.jd: dict[int, float] = {}


def load_solutions(path: Path) -> Solutions:
    """``frame index -> FrameWCS`` from ``solve_frames.py`` output.

    Solved frames only, and in truth mode only those whose solves agreed.
    """
    out = Solutions()
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        if row.get("jd_mid") is not None:
            out.jd[int(row["frame"])] = float(row["jd_mid"])
        if "crval" in row and row.get("consensus", True):
            out[int(row["frame"])] = FrameWCS(*row["crval"], *row["crpix"], tuple(row["cd"]))
    return out


def load_proper_motions(path: Path = PROPER_MOTIONS_PATH) -> dict[str, tuple[float, float]]:
    """``star key -> (pm_ra·cos(dec), pm_dec)`` in mas/yr, catalogue epoch J2000.0."""
    if os.environ.get("TRACKER_STUDY_PM", "").lower() == "none" or not Path(path).exists():
        return {}
    doc = json.loads(Path(path).read_text())
    return {
        key: (float(v["pmra_cosdec_mas_yr"]), float(v["pmdec_mas_yr"]))
        for key, v in doc["stars"].items()
    }


PROPER_MOTIONS = load_proper_motions()


def at_epoch(star, jd: float | None) -> tuple[float, float]:
    """The star's (RA, Dec) in degrees at ``jd``: the J2000.0 catalogue position moved by
    its proper motion (stars without one in ``proper_motions.json`` are not moved)."""
    pm = PROPER_MOTIONS.get(star_key(star))
    if pm is None or jd is None:
        return star.ra_deg, star.dec_deg
    years = (jd - J2000_JD) / 365.25
    dec = star.dec_deg + pm[1] * years / 3.6e6
    ra = star.ra_deg + pm[0] * years / 3.6e6 / math.cos(math.radians(star.dec_deg))
    return ra, dec


def star_at_epoch(star, jd: float | None):
    """``star`` with its position moved to ``jd`` (same key and role)."""
    ra, dec = at_epoch(star, jd)
    return dataclasses.replace(star, ra_deg=ra, dec_deg=dec, mags=dict(star.mags))


def set_at_epoch(tset: TargetSet, jd: float | None) -> TargetSet:
    """A copy of ``tset`` with every star moved to ``jd`` (the truth arm measures there)."""
    out = TargetSet(object_name=tset.object_name)
    for star in tset.stars:
        out.set_role(star_at_epoch(star, jd))
    return out


def separation_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def load_target_set(path: Path, check: str = "nearest") -> tuple[TargetSet, str | None]:
    """The run's target set with one comparison turned into the check star.

    ``check="nearest"``: the comparison nearest the (first) target on the sky
    becomes the check (the owner's runs have none). ``check="none"`` keeps the
    set as saved. Any other value is the AUID of the comparison to use.
    Returns the set and the check's AUID (None when none was assigned).
    """
    tset = TargetSet.load(path)
    if check == "none":
        return tset, None
    target = tset.by_role("target")[0]
    comps = tset.by_role(ROLE_COMPARISON)
    if check == "nearest":
        chosen = min(
            comps, key=lambda s: separation_deg(s.ra_deg, s.dec_deg, target.ra_deg, target.dec_deg)
        )
    else:
        chosen = next(s for s in comps if s.auid == check)
    tset.set_role(dataclasses.replace(chosen, role=ROLE_CHECK, mags=dict(chosen.mags)))
    return tset, chosen.auid


def star_key(star) -> str:
    return star.auid or star.display_name


def truth_xy(solutions: dict[int, FrameWCS], frame: int, star) -> tuple[float, float] | None:
    """The star's green-px position on ``frame`` from that frame's own solve, the star
    moved to the frame's date by its proper motion (``at_epoch``)."""
    wcs = solutions.get(frame)
    if wcs is None:
        return None
    ra, dec = at_epoch(star, getattr(solutions, "jd", {}).get(frame))
    x, y = wcs.world_to_pixel_deg(ra, dec)
    return float(x), float(y)


def load_module(path: Path, name: str):
    """Import a module from a file (the web tracker, ``argos/server/field_track.py``)."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
