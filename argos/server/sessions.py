"""The list of recorded sessions (row A67, list only; wave 2).

A session is a folder directly inside ``sessions_path`` that holds a
``session.json`` (``argos/core/imaging/session_log.py``). The summary is a
Qt-free port of ``argos/core/session/review.py:76-175``
(``load_session(read_temperature=False)`` and ``readiness_issues``): that
module cannot be imported here, because the ``argos.core.session`` package
loads PyQt6 (``tests/server/test_no_qt.py``). Differences, on purpose:
missing FITS frames are counted in one issue line instead of one line each,
and the per-star curves are counted by their file prefix (``target_``,
``comparison_``, ``check_``) instead of being loaded.

Summaries are cached per folder, keyed by the stamps of the folder and of
``session.json``; nothing is ever written into a session.
"""

from __future__ import annotations

import json
import os
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argos.core.imaging.session_log import SESSION_FILENAME

_FITS = (".fit", ".fits", ".fts")
_CURVE_ROLES = ("target", "comparison", "check")
#: Folders below a session searched for FITS files (lights/, darks/…).
_MAX_FITS_DEPTH = 3


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _fits_names(root: Path) -> set[str]:
    """FITS file names in the session tree (review.py:146 ``rglob("*.fit*")``), no links."""
    names: set[str] = set()
    base_depth = len(root.parts)
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        if len(Path(current).parts) - base_depth >= _MAX_FITS_DEPTH:
            dirnames[:] = []
        for name in filenames:
            if name.lower().endswith(_FITS):
                names.add(name)
    return names


def _curve_counts(root: Path) -> dict[str, int]:
    counts = {role: 0 for role in _CURVE_ROLES}
    folder = root / "photometry"
    try:
        names = [p.name for p in folder.glob("*.csv")]
    except OSError:
        return counts
    for name in names:
        for role in _CURVE_ROLES:
            if name.startswith(f"{role}_"):
                counts[role] += 1
                break
    return counts


def summarise(root: Path) -> dict[str, Any]:
    """One SessionSummary (``protocol.md`` "Session list")."""
    summary: dict[str, Any] = {
        "path": str(root),
        "folder": root.name,
        "object": "Unknown",
        "started_utc": "",
        "frames": 0,
        "lights": 0,
        "filters": {},
        "image_types": {},
        "missing_frames": 0,
        "curves": _curve_counts(root),
        "has_quality": (root / "photometry_quality.json").is_file(),
        "has_targets": (root / "targets.json").is_file(),
        "issues": [],
    }
    issues: list[str] = summary["issues"]
    session_path = root / SESSION_FILENAME
    # review.py:110-117
    try:
        document = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        issues.append(f"Could not read {SESSION_FILENAME}: {exc}")
        return summary
    if not isinstance(document, dict) or not isinstance(document.get("frames"), list):
        issues.append(f"{SESSION_FILENAME} has no frame list")
        return summary
    summary["object"] = str(document.get("object") or "Unknown")
    summary["started_utc"] = str(document.get("started_utc") or "")
    # review.py:125-143
    observation = root / "observation.json"
    if observation.is_file():
        try:
            json.loads(observation.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            issues.append("Could not read observation.json.")
    quality = root / "photometry_quality.json"
    if quality.is_file():
        try:
            payload = json.loads(quality.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                issues.append("Ignored an invalid photometry_quality.json.")
        except (OSError, ValueError):
            issues.append("Could not read photometry_quality.json.")
    # review.py:146-175, without the FITS temperature read
    fits = _fits_names(root)
    filters: Counter[str] = Counter()
    types: Counter[str] = Counter()
    frames = lights = missing = 0
    for row in document["frames"]:
        if not isinstance(row, dict):
            issues.append("Ignored an invalid frame row in session.json.")
            continue
        try:
            filename = str(row["filename"])
            image_type = str(row.get("image_type") or "Unknown")
            filter_name = str(row.get("filter_name") or "")
            float(row.get("exposure_s") or 0.0)
            int(row.get("gain") or 0)
        except (KeyError, TypeError, ValueError):
            issues.append("Ignored a malformed frame row in session.json.")
            continue
        frames += 1
        if image_type.lower().startswith("light"):
            lights += 1
        filters[filter_name or "—"] += 1
        types[image_type] += 1
        if filename not in fits:
            missing += 1
    if missing:
        noun = "frame" if missing == 1 else "frames"
        verb = "is" if missing == 1 else "are"
        issues.append(f"{missing} FITS {noun} listed in session.json {verb} missing")
    # review.py:76-82 (readiness_issues)
    if not lights:
        issues.append("No light frames were recorded.")
    if not fits:
        issues.append("No FITS frames found in this session folder.")
    summary.update(
        frames=frames,
        lights=lights,
        missing_frames=missing,
        filters=dict(filters),
        image_types=dict(types),
    )
    return summary


def is_session(path: Path) -> bool:
    return (path / SESSION_FILENAME).is_file()


class SessionIndex:
    """Cached summaries of the sessions under one root; thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[Any, dict[str, Any]]] = {}

    def page(self, root: Path, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        scanned = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        out: dict[str, Any] = {
            "root": str(root),
            "exists": root.is_dir(),
            "total": 0,
            "offset": offset,
            "limit": limit,
            "sessions": [],
            "scanned_utc": scanned,
        }
        if not out["exists"]:
            return out
        summaries = []
        seen: set[str] = set()
        try:
            children = sorted(os.scandir(root), key=lambda e: e.name)
        except OSError:
            return out
        for entry in children:
            try:
                if entry.is_symlink() or not entry.is_dir():
                    continue
            except OSError:
                continue
            folder = Path(entry.path)
            session_json = folder / SESSION_FILENAME
            if not session_json.is_file():
                continue
            key = str(folder)
            seen.add(key)
            stamp = (_stamp(folder), _stamp(session_json), _stamp(folder / "photometry"))
            with self._lock:
                cached = self._cache.get(key)
            if cached is not None and cached[0] == stamp:
                summary = cached[1]
            else:
                summary = summarise(folder)
                with self._lock:
                    self._cache[key] = (stamp, summary)
            summaries.append(summary)
        with self._lock:
            for key in [k for k in self._cache if k not in seen and Path(k).parent == root]:
                del self._cache[key]
        summaries.sort(key=lambda s: (s["started_utc"], s["folder"]), reverse=True)
        out["total"] = len(summaries)
        out["sessions"] = [dict(s) for s in summaries[offset : offset + limit]]
        return out
