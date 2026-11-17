"""Local support bundle and crash reports (rows A5, A6).

A port of ``argos.core.support_bundle.create_support_bundle``
(``support_bundle.py:162-221``) and of its session-metadata pass
(``:224-302``) for the headless server, with what the server needs on top:

- the **bearer token** is removed from every text (its value, ``token=…``,
  ``Bearer …``, ``ARGOS_TOKEN=…``), although the log handlers already mask
  ``token=`` (``runtime.RedactTokens``);
- the **observer's coordinates** are removed from the logs too, not only
  from session files: every writing of the Settings site's and saved sites'
  latitude, longitude and elevation, ``lat=`` / ``lon=`` / ``elev=`` values
  (the core logs the mount's site as ``Mount site: lat=… lon=…``,
  ``telescope.py:208``) and every ``(lat°, lon°)`` pair (the site check names
  a site that way, also one changed since). The observer may ask for them
  (``include_site``), never by default;
- session metadata is left out unless asked (decision Q-G17);
- crash reports of the log folder (``support_bundle.py:104-122``) can go
  in, redacted the same way;
- the ZIP is written to a temporary name in the destination folder and
  renamed when complete, so a failure never leaves half a bundle.

Nothing here opens a network connection.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import platform
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from argos import __version__
from argos.core import support_bundle as core_bundle

#: Same bounds as the Qt bundle (support_bundle.py:33-35).
MAX_FILE_BYTES = 10_000_000
MAX_SESSION_BYTES = 50_000_000
SESSION_EXTENSIONS = frozenset({".csv", ".json", ".jsonl"})
#: Crash reports added at most, newest first, and their size bound.
MAX_CRASH_REPORTS = 20
MAX_CRASH_BYTES = 1_000_000
#: Crash reports listed by ``GET /api/diagnostics/crash-reports``.
MAX_LISTED_CRASHES = 50

_CRASH_RE = re.compile(r"^crash-(\d{8}T\d{6}Z)-\d+\.txt$")
_TOKEN_PATTERNS = (
    re.compile(r"(token=)[^&\s\"']+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(ARGOS_TOKEN=)\S+"),
)
#: A "(lat°, lon°)" pair, as the site check writes a site (any site, also one
#: no longer in the configuration).
_PAIR_PATTERN = re.compile(r"\(\s*[-+]?\d{1,3}(?:\.\d+)?°\s*,\s*[-+]?\d{1,3}(?:\.\d+)?°\s*\)")
_COORD_PATTERN = re.compile(
    r"\b((?:site_?)?(?:lat|latitude|lon|long|longitude|elev|elevation)\s*[=:]\s*)"
    r"[-+]?\d+(?:\.\d+)?",
    re.IGNORECASE,
)

#: Session-file keys redacted always (identity, network, target position),
#: as ``support_bundle.py:38-53``.
_ALWAYS_PRIVATE = frozenset({"address", "dec", "decdeg", "host", "ip", "observer", "obscode",
                             "observercode", "ra", "radeg", "token"})  # fmt: skip
#: Session-file keys that place the observer; kept only with ``include_site``.
_LOCATION_PRIVATE = frozenset({"elevation", "latitude", "longitude", "site", "sitelat",
                               "sitelong", "siteelev", "lat", "lon", "elev",
                               # wave 2 review: spellings the core does not write today
                               "latdeg", "londeg", "lngdeg", "lng", "sitelon", "sitelatitude",
                               "sitelongitude", "siteelevation", "elevationm", "elevm",
                               "observingsite", "geo", "location"})  # fmt: skip


class BundleError(Exception):
    """The bundle could not be written (the message is the OS reason)."""


def _number_variants(value: Any) -> set[str]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return set()
    if number == 0.0:
        return set()  # "0.0" is everywhere and places nobody
    variants = {repr(number), str(number)}
    for decimals in range(2, 9):
        variants.add(f"{number:.{decimals}f}")
        variants.add(f"{abs(number):.{decimals}f}")
    return {v for v in variants if len(v.strip("-+0.")) >= 2}


@dataclass
class Redactor:
    """Every text that enters the ZIP goes through :meth:`text`."""

    token: str | None = None
    home: Path | None = None
    include_site: bool = False
    #: Latitudes, longitudes and elevations to remove from free text.
    coordinates: Iterable[Any] = ()
    _numbers: re.Pattern[str] | None = field(default=None, init=False, repr=False)
    _values: list[float] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        variants: set[str] = set()
        for value in self.coordinates:
            variants |= _number_variants(value)
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number != 0.0 and math.isfinite(number):
                self._values.append(number)
        if variants and not self.include_site:
            alternatives = "|".join(sorted((re.escape(v) for v in variants), key=len, reverse=True))
            self._numbers = re.compile(rf"(?<![\d.])(?:{alternatives})(?![\d])")

    def text(self, value: str) -> str:
        out = value
        if self.token:
            out = out.replace(self.token, "<redacted-token>")
        for pattern in _TOKEN_PATTERNS:
            out = pattern.sub(r"\1<redacted-token>", out)
        out = core_bundle.redact_text(out, self.home)  # IPv4 and the home path
        if not self.include_site:
            out = _PAIR_PATTERN.sub("(<redacted-site>)", out)
            out = _COORD_PATTERN.sub(r"\1<redacted-site>", out)
            if self._numbers is not None:
                out = self._numbers.sub("<redacted-site>", out)
        return out

    # -- session files (support_bundle.py:256-302) ----------------------------------

    def _private(self, key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
        if normalized in _ALWAYS_PRIVATE:
            return True
        return not self.include_site and normalized in _LOCATION_PRIVATE

    def _site_number(self, value: Any) -> bool:
        """A JSON number that writes a site coordinate (exact, or rounded to 2-8 decimals).

        Strings go through :meth:`text`; numbers under keys outside the location
        list (``"geo": {"lat_deg": …}``, ``"observing_site": [lat, lon]``) would
        otherwise enter the ZIP unchanged. Whole numbers are left alone (frame
        counts, gains), as the text pass does.
        """
        if self.include_site or isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        number = float(value)
        if not math.isfinite(number) or number.is_integer():
            return False
        for site in self._values:
            if abs(number - site) <= 1e-6:
                return True
            for decimals in range(2, 9):
                if round(number, decimals) == number and round(site, decimals) == number:
                    return True
        return False

    def metadata(self, value: Any) -> Any:
        if self._site_number(value):
            return "<redacted-site>"
        if isinstance(value, dict):
            return {
                key: "<redacted>" if self._private(str(key)) else self.metadata(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.metadata(item) for item in value]
        if isinstance(value, str):
            return self.text(value)
        return value

    def session_file(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                return json.dumps(self.metadata(json.loads(text)), indent=2, sort_keys=True)
            except json.JSONDecodeError:
                return "<unparseable JSON omitted from privacy-safe support bundle>\n"
        if suffix == ".jsonl":
            lines: list[str] = []
            for line in text.splitlines():
                try:
                    lines.append(json.dumps(self.metadata(json.loads(line)), sort_keys=True))
                except json.JSONDecodeError:
                    lines.append("<unparseable JSONL record omitted>")
            return "\n".join(lines) + ("\n" if lines else "")
        if suffix == ".csv":
            try:
                reader = csv.DictReader(io.StringIO(text))
                if not reader.fieldnames:
                    return ""
                out = io.StringIO()
                writer = csv.DictWriter(out, fieldnames=reader.fieldnames, lineterminator="\n")
                writer.writeheader()
                for row in reader:
                    writer.writerow(
                        {
                            key: "<redacted>" if self._private(key or "") else value
                            for key, value in row.items()
                        }
                    )
                return self.text(out.getvalue())
            except csv.Error:
                return "<unparseable CSV omitted from privacy-safe support bundle>\n"
        return self.text(text)


def site_coordinates(get) -> list[Any]:
    """The coordinates to redact: the Settings site and every saved site."""
    values: list[Any] = [get("site.latitude", None), get("site.longitude", None)]
    values.append(get("site.elevation", None))
    values += [get("observer.latitude", None), get("observer.longitude", None)]
    favorites = get("site.favorites", []) or []
    if isinstance(favorites, list):
        for item in favorites:
            if isinstance(item, dict):
                values += [item.get("latitude"), item.get("longitude"), item.get("elevation")]
    return values


def default_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"argos-support-{__version__}-{stamp}.zip"


def crash_reports(directory: Path | None, home: Path | None = None) -> list[dict[str, Any]]:
    """``GET /api/diagnostics/crash-reports``: the crash files of the log folder."""
    if directory is None or not directory.is_dir():
        return []
    reports = []
    for path in directory.glob("crash-*.txt"):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            st = path.stat()
        except OSError:
            continue
        match = _CRASH_RE.match(path.name)
        when = None
        if match:
            try:
                when = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                when = None
        if when is None:
            when = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        summary = ""
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                tail = handle.read(MAX_CRASH_BYTES).splitlines()
            summary = next((line.strip() for line in reversed(tail) if line.strip()), "")
        except OSError:
            pass
        reports.append(
            {
                "path": str(path),
                "name": path.name,
                "t": when.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "size": st.st_size,
                "summary": core_bundle.redact_text(summary, home)[:300],
            }
        )
    reports.sort(key=lambda r: (r["t"], r["name"]), reverse=True)
    return reports[:MAX_LISTED_CRASHES]


def _session_files(root: Path) -> Iterable[tuple[Path, str]]:
    """Whitelisted session files, no links followed (support_bundle.py:229-247)."""
    total = 0
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            candidate = Path(current) / name
            if candidate.is_symlink() or candidate.suffix.lower() not in SESSION_EXTENSIONS:
                continue
            try:
                size = candidate.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES or total + size > MAX_SESSION_BYTES:
                continue
            total += size
            yield candidate, f"session/{candidate.relative_to(root).as_posix()}"


@dataclass(frozen=True)
class BundleResult:
    path: Path
    files: tuple[str, ...]
    bytes: int


def create_bundle(
    destination: Path,
    *,
    redactor: Redactor,
    log_directory: Path | None,
    session_directory: Path | None = None,
    include_crash_reports: bool = True,
    config_summary: Mapping[str, Any] | None = None,
) -> BundleResult:
    """Write the ZIP at *destination* (complete, or not at all)."""
    included: list[str] = []
    manifest: dict[str, Any] = {
        "format": 1,
        "argos_version": __version__,
        "created_by": "argos.server",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "privacy": {
            "created_locally": True,
            "uploaded_by_argos": False,
            "raw_fits_included": False,
            "tokens_included": False,
            "network_addresses_included": False,
            "site_coordinates_included": bool(redactor.include_site),
            "session_metadata_included": session_directory is not None,
        },
        "configuration": dict(config_summary or {}),
    }
    readme = (
        "This bundle was created locally by ARGOS at the observer's request.\n"
        "It is not uploaded automatically. It contains no raw FITS, no access token and no "
        "network address"
        + ("" if redactor.include_site else ", and no site coordinates")
        + ". Review it before sharing.\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".argos-support-", suffix=".zip.tmp",
                                    dir=destination.parent)  # fmt: skip
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("README.txt", readme)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
            included += ["README.txt", "manifest.json"]
            if log_directory is not None and log_directory.is_dir():
                for log in sorted(log_directory.glob("argos.log*")):
                    if log.is_symlink() or not log.is_file():
                        continue
                    if log.stat().st_size > MAX_FILE_BYTES:
                        continue
                    name = f"logs/{log.name}"
                    text = log.read_text(encoding="utf-8", errors="replace")
                    archive.writestr(name, redactor.text(text))
                    included.append(name)
                if include_crash_reports:
                    for report in crash_reports(log_directory)[:MAX_CRASH_REPORTS]:
                        path = Path(report["path"])
                        if report["size"] > MAX_CRASH_BYTES:
                            continue
                        name = f"crash/{path.name}"
                        text = path.read_text(encoding="utf-8", errors="replace")
                        archive.writestr(name, redactor.text(text))
                        included.append(name)
            if session_directory is not None:
                for candidate, name in _session_files(session_directory):
                    archive.writestr(name, redactor.session_file(candidate))
                    included.append(name)
        os.replace(tmp_name, destination)
    except OSError as exc:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise BundleError(exc.strerror or str(exc)) from exc
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return BundleResult(destination, tuple(included), destination.stat().st_size)
