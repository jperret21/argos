"""Read-only folder listing for the in-app file picker (row A11).

Decisions D20 / Q-G7 (one in-app ``FilePicker`` everywhere, Night Red
included) and Q-R4 (the browser build opens nothing outside the data paths
unless the token holder types it): the server lists folders, read-only,
only inside its **allowed roots** — the observer's home folder and the
ARGOS data folders. Every path is resolved (``realpath``) before it is
compared with the roots, which are resolved too, so neither ``..`` nor a
symbolic link can lead outside; entries whose link points outside (or
nowhere) are left out of a listing.

Nothing here opens a file, writes, or touches the network. It replaces the
18 ``QFileDialog`` sites of the Qt app (``web/spec/01-shell-and-global.md``
appendix A.2) on the server side.
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from argos.server.errors import ApiError

#: Entries returned by one listing at most.
MAX_ENTRIES = 5000
#: Names looked at per folder when counting its FITS files.
MAX_COUNT_SCAN = 10_000
FITS_SUFFIXES = (".fit", ".fits", ".fts")

#: ``data_paths.*`` keys that name a folder (or a file, whose folder counts).
_DATA_DIR_KEYS = (
    "sessions_path",
    "data_paths.sequence_presets_directory",
    "data_paths.camera_calibration_directory",
    "data_paths.aavso_cache_directory",
    "data_paths.gaia_cache_directory",
    "data_paths.field_catalogue_cache_directory",
)
_DATA_FILE_KEYS = ("data_paths.object_catalogue_cache", "data_paths.exoplanet_cache")


def _iso_mtime(st: os.stat_result) -> str:
    when = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    return when.isoformat(timespec="seconds").replace("+00:00", "Z")


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


#: Volumes of these systems are case-insensitive by default (APFS, NTFS), and
#: ``realpath`` keeps the letter case as typed there.
_CASE_INSENSITIVE_OS = sys.platform in ("darwin", "win32")


def _true_case(path: Path) -> Path:
    """*path* spelled as the file system stores it, component by component.

    For a case-insensitive volume, where ``realpath`` keeps the case as typed:
    ``/USERS/me`` names the same folder as ``/Users/me`` but would not compare
    equal to the root. A component is respelled only when the folder holds
    exactly one entry of that name in another case AND both spellings are the
    same file (``samefile``), so on a case-sensitive volume nothing changes
    meaning. The first missing component and the rest stay as typed.
    """
    parts = path.parts
    fixed = Path(parts[0])
    for i, name in enumerate(parts[1:], start=1):
        candidate = fixed / name
        try:
            names = os.listdir(fixed)
        except OSError:
            return fixed.joinpath(*parts[i:])
        if name in names:
            fixed = candidate
            continue
        folded = name.casefold()
        matches = [n for n in names if n.casefold() == folded]
        try:
            same = len(matches) == 1 and os.path.samefile(candidate, fixed / matches[0])
        except OSError:
            same = False
        if not same:
            return fixed.joinpath(*parts[i:])
        fixed = fixed / matches[0]
    return fixed


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


@dataclass(frozen=True)
class Place:
    id: str
    label: str
    path: Path

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "path": str(self.path),
                "exists": self.path.is_dir()}  # fmt: skip


class AllowedRoots:
    """The folders the server may browse, from the live configuration.

    *get* reads a config key; *extra* gives further folders (the config and
    log folders). Recomputed on every call, so a ``data_paths`` change applies
    at once.
    """

    def __init__(
        self,
        get: Callable[[str, Any], Any],
        extra: Callable[[], Iterable[Path | None]] = lambda: (),
        home: Callable[[], Path] = Path.home,
    ) -> None:
        self._get = get
        self._extra = extra
        self._home = home

    def _configured(self, key: str) -> Path | None:
        value = self._get(key, None)
        if not isinstance(value, str) or not value.strip():
            return None
        path = Path(value.strip()).expanduser()
        return path if path.is_absolute() else None

    def roots(self) -> list[Path]:
        """Resolved roots, most specific (longest) first, no duplicates."""
        found: list[Path] = [self._home()]
        found += [p for p in (self._configured(k) for k in _DATA_DIR_KEYS) if p is not None]
        found += [p.parent for p in (self._configured(k) for k in _DATA_FILE_KEYS) if p]
        found += [p for p in self._extra() if p is not None]
        seen: dict[str, Path] = {}
        for path in found:
            real = _real(path)
            seen.setdefault(str(real), real)
        return sorted(seen.values(), key=lambda p: len(p.parts), reverse=True)

    def root_of(self, real: Path) -> Path | None:
        """The allowed root containing the resolved path *real* (outermost), or ``None``."""
        containing = [root for root in self.roots() if _inside(real, root)]
        return min(containing, key=lambda p: len(p.parts)) if containing else None

    def places(self, extra: Iterable[tuple[str, str, Path | None]] = ()) -> list[Place]:
        home = self._home()
        candidates: list[tuple[str, str, Path | None]] = [
            ("home", "Home", home),
            ("desktop", "Desktop", home / "Desktop"),
            ("sessions", "Sessions", self._configured("sessions_path")),
            ("presets", "Sequence presets",
             self._configured("data_paths.sequence_presets_directory")),
            ("calibrations", "Calibrations",
             self._configured("data_paths.camera_calibration_directory")),
            *extra,
        ]  # fmt: skip
        places = []
        for place_id, label, path in candidates:
            if path is None:
                continue
            if place_id == "desktop" and not path.is_dir():
                continue
            places.append(Place(place_id, label, path))
        return places

    def resolve(self, raw: str | os.PathLike[str], *, what: str = "path") -> tuple[Path, Path]:
        """``(resolved path, its root)``; ``400`` relative, ``403`` outside the roots."""
        text = str(raw).strip()
        if not text:
            raise ApiError(400, "invalid_argument", f"Give an absolute {what}")
        if "\x00" in text:
            # os.path.realpath raises ValueError on it: a 400, never a 500.
            raise ApiError(400, "invalid_argument", f"The {what} is not a valid path")
        try:
            path = Path(text).expanduser()
            if not path.is_absolute():
                raise ApiError(400, "invalid_argument", f"The {what} must be absolute: {text}")
            real = _real(path)
        except (ValueError, OSError) as exc:
            raise ApiError(400, "invalid_argument", f"The {what} is not a valid path") from exc
        root = self.root_of(real)
        if root is None and _CASE_INSENSITIVE_OS:
            # A valid folder typed in another letter case (APFS): respell it from
            # the file system, then compare again. Never widens the roots.
            respelled = _true_case(real)
            if respelled != real:
                real, root = respelled, self.root_of(respelled)
        if root is None:
            raise ApiError(
                403,
                "forbidden_path",
                f"{path} is outside the folders ARGOS may browse (your home folder and the "
                "ARGOS data folders)",
            )
        return real, root

    def allows(self, real: Path) -> bool:
        return self.root_of(real) is not None


def _fits_count(path: Path) -> int:
    count = 0
    try:
        with os.scandir(path) as it:
            for i, entry in enumerate(it):
                if i >= MAX_COUNT_SCAN:
                    break
                if entry.name.lower().endswith(FITS_SUFFIXES):
                    try:
                        if entry.is_file():
                            count += 1
                    except OSError:
                        continue
    except OSError:
        return 0
    return count


def parse_exts(ext: str | None) -> tuple[str, ...]:
    """``".fits,.fit,FTS"`` → ``(".fits", ".fit", ".fts")``."""
    if not ext:
        return ()
    out = []
    for part in ext.split(","):
        part = part.strip().lower()
        if not part:
            continue
        out.append(part if part.startswith(".") else f".{part}")
    return tuple(out)


def list_folder(
    roots: AllowedRoots,
    path: str | None,
    *,
    default: Path,
    kind: str = "any",
    exts: tuple[str, ...] = (),
    counts: str | None = None,
    hidden: bool = False,
    places: list[Place] | None = None,
) -> dict[str, Any]:
    """``GET /api/fs/list`` (see ``protocol.md`` "File listing")."""
    if path is None or not str(path).strip():
        target = default if default.is_dir() else Path.home()
        real, root = roots.resolve(target)
    else:
        real, root = roots.resolve(path)
    try:
        st = real.stat()
    except FileNotFoundError:
        raise ApiError(404, "not_found", f"No folder {real}") from None
    except OSError as exc:
        raise ApiError(403, "forbidden_path", f"Cannot read {real}: {exc.strerror}") from exc
    selected: str | None = None
    if not stat.S_ISDIR(st.st_mode):
        if kind == "dir" or not stat.S_ISREG(st.st_mode):
            raise ApiError(400, "invalid_argument", f"{real} is not a folder")
        # A file path typed in the picker: list its folder with the file selected.
        if exts and not real.name.lower().endswith(exts):
            wanted = "/".join(exts)
            raise ApiError(400, "invalid_argument", f"{real.name} is not a {wanted} file")
        selected = real.name
        real = real.parent

    dirs: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    try:
        entries = list(os.scandir(real))
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ApiError(403, "forbidden_path", f"Cannot list {real}: {reason}") from exc
    for entry in entries:
        if not hidden and entry.name.startswith("."):
            continue
        try:
            is_link = entry.is_symlink()
            if is_link:
                target = _real(Path(entry.path))
                if not target.exists() or not roots.allows(target):
                    continue  # a link outside the roots (or broken) is never shown
            entry_st = entry.stat()  # follows the link
        except OSError:
            continue
        if stat.S_ISDIR(entry_st.st_mode):
            record: dict[str, Any] = {
                "name": entry.name,
                "kind": "dir",
                "size": None,
                "mtime": _iso_mtime(entry_st),
                "symlink": is_link,
                "fits_count": None,
            }
            dirs.append(record)
        elif stat.S_ISREG(entry_st.st_mode):
            if kind == "dir":
                continue
            if exts and not entry.name.lower().endswith(exts):
                continue
            files.append(
                {
                    "name": entry.name,
                    "kind": "file",
                    "size": entry_st.st_size,
                    "mtime": _iso_mtime(entry_st),
                    "symlink": is_link,
                    "fits_count": None,
                }
            )
    dirs.sort(key=lambda e: (e["name"].casefold(), e["name"]))
    files.sort(key=lambda e: (e["name"].casefold(), e["name"]))
    listed = dirs + files
    truncated = len(listed) > MAX_ENTRIES
    listed = listed[:MAX_ENTRIES]
    if counts == "fits":
        for record in listed:
            if record["kind"] == "dir":
                record["fits_count"] = _fits_count(real / record["name"])

    parent = real.parent
    parent_out = str(parent) if real != root and roots.allows(parent) else None
    return {
        "path": str(real),
        "parent": parent_out,
        "root": str(root),
        "places": [p.to_dict() for p in (places or roots.places())],
        "entries": listed,
        "truncated": truncated,
        "selected": selected,
    }
