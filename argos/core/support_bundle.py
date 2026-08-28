"""Private local diagnostics: rotating logs, crash reports and support bundles.

Nothing in this module opens a network connection.  It gives an observer a
useful, explicit way to collect evidence after a field failure without turning
Argos into telemetry software.  A support bundle is created only after an
observer chooses its destination and is never uploaded by Argos.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
import threading
import traceback
import zipfile
import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Mapping

from argos import __version__

_LOG_FILENAME = "argos.log"
_MAX_LOG_BYTES = 2_000_000
_LOG_BACKUPS = 5
_MAX_BUNDLE_FILE_BYTES = 10_000_000
_MAX_BUNDLE_SESSION_BYTES = 50_000_000
_SESSION_EXTENSIONS = frozenset({".csv", ".json", ".jsonl"})
_IPV4_RE = re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")
_PRIVATE_FIELDS = frozenset(
    {
        "address",
        "dec",
        "decdeg",
        "elevation",
        "host",
        "ip",
        "latitude",
        "longitude",
        "observer",
        "ra",
        "radeg",
        "site",
    }
)


def diagnostics_directory(home: Path | None = None, system: str | None = None) -> Path:
    """Return the standard local directory for technical Argos diagnostics."""
    user_home = Path.home() if home is None else Path(home)
    if (system or platform.system()) == "Darwin":
        return user_home / "Library" / "Logs" / "Argos"
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else user_home / ".local" / "state"
    return base / "argos"


def configure_local_logging(level: str, directory: Path | None = None) -> Path | None:
    """Configure console plus bounded local logging, returning the log path.

    A filesystem failure must never prevent the telescope application starting;
    console logging remains available in that case.
    """
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    handlers[0].setFormatter(formatter)
    path: Path | None = None
    try:
        root = directory or diagnostics_directory()
        root.mkdir(parents=True, exist_ok=True)
        path = root / _LOG_FILENAME
        file_handler = RotatingFileHandler(
            path, maxBytes=_MAX_LOG_BYTES, backupCount=_LOG_BACKUPS, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError:
        # ``basicConfig`` below ensures this remains visible even before the
        # application's logging tree exists.
        logging.getLogger(__name__).warning("Could not initialise local file logging", exc_info=True)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO), handlers=handlers, force=True
    )
    return path


def write_crash_report(
    exc_type: type[BaseException], exc: BaseException, tb, directory: Path | None = None
) -> Path | None:
    """Write a local traceback report and return its path; never raises."""
    try:
        root = directory or diagnostics_directory()
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = root / f"crash-{stamp}-{os.getpid()}.txt"
        report = [
            f"Argos {__version__} crash report",
            f"UTC: {datetime.now(timezone.utc).isoformat()}",
            f"Python: {sys.version}",
            f"Platform: {platform.platform()}",
            "",
            "".join(traceback.format_exception(exc_type, exc, tb)),
        ]
        path.write_text("\n".join(report), encoding="utf-8")
        return path
    except OSError:
        return None


def install_crash_reporter(directory: Path | None = None) -> None:
    """Persist uncaught main-thread and Python-thread tracebacks locally."""
    previous_sys_hook = sys.excepthook
    previous_thread_hook = threading_excepthook = getattr(threading, "excepthook", None)

    def report(exc_type, exc, tb) -> None:
        path = write_crash_report(exc_type, exc, tb, directory)
        logging.getLogger(__name__).critical("Unhandled exception; local report: %s", path)
        previous_sys_hook(exc_type, exc, tb)

    sys.excepthook = report

    if threading_excepthook is not None:
        def report_thread(args) -> None:
            path = write_crash_report(args.exc_type, args.exc_value, args.exc_traceback, directory)
            logging.getLogger(__name__).critical("Unhandled thread exception; local report: %s", path)
            previous_thread_hook(args)

        threading.excepthook = report_thread


def redact_text(text: str, home: Path | None = None) -> str:
    """Remove common local identifiers from a log before it enters a bundle."""
    redacted = _IPV4_RE.sub("<redacted-ip>", text)
    user_home = str(home or Path.home())
    if user_home and user_home != ".":
        redacted = redacted.replace(user_home, "~")
    return redacted


@dataclass(frozen=True)
class SupportBundle:
    """Result of a manually generated local support bundle."""

    path: Path
    files: tuple[str, ...]


def create_support_bundle(
    destination: Path | str,
    *,
    log_directory: Path | None = None,
    session_directory: Path | None = None,
    config_summary: Mapping[str, Any] | None = None,
    home: Path | None = None,
) -> SupportBundle:
    """Create a local ZIP with redacted logs and optional non-FITS session data.

    The caller decides whether to pass ``session_directory``. FITS files,
    arbitrary binaries, location and network configuration are excluded or
    redacted by construction. The result remains on the observer's computer.
    """
    target = Path(destination)
    if target.suffix.lower() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    included: list[str] = []
    manifest: dict[str, Any] = {
        "format": 1,
        "argos_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "privacy": {
            "created_locally": True,
            "uploaded_by_argos": False,
            "raw_fits_included": False,
            "site_and_network_configuration_included": False,
        },
        "configuration": dict(config_summary or {}),
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.txt",
            "This bundle was created locally by Argos at the observer's request.\n"
            "It is not uploaded automatically. It contains no raw FITS, site coordinates "
            "or network address. Review it before sharing.\n",
        )
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        included.extend(("README.txt", "manifest.json"))

        root = log_directory or diagnostics_directory(home=home)
        for log in sorted(root.glob("argos.log*")) if root.is_dir() else []:
            if log.is_file() and not log.is_symlink() and log.stat().st_size <= _MAX_BUNDLE_FILE_BYTES:
                name = f"logs/{log.name}"
                archive.writestr(name, redact_text(log.read_text(encoding="utf-8", errors="replace"), home))
                included.append(name)

        if session_directory is not None:
            session_root = Path(session_directory).resolve()
            if session_root.is_dir():
                included.extend(_add_session_metadata(archive, session_root))

    return SupportBundle(path=target, files=tuple(included))


def _add_session_metadata(archive: zipfile.ZipFile, root: Path) -> list[str]:
    """Add bounded, whitelisted session metadata; never follow links or include FITS."""
    added: list[str] = []
    total = 0
    for candidate in sorted(root.rglob("*")):
        if not candidate.is_file() or candidate.is_symlink() or candidate.suffix.lower() not in _SESSION_EXTENSIONS:
            continue
        size = candidate.stat().st_size
        if size > _MAX_BUNDLE_FILE_BYTES or total + size > _MAX_BUNDLE_SESSION_BYTES:
            continue
        relative = candidate.relative_to(root)
        name = f"session/{relative.as_posix()}"
        archive.writestr(name, _redact_session_file(candidate))
        added.append(name)
        total += size
    return added


def _private_field(key: str) -> bool:
    """True when a metadata key identifies a person, site or endpoint."""
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in _PRIVATE_FIELDS


def _redact_metadata(value: Any) -> Any:
    """Recursively redact identifiable fields while retaining diagnostic structure."""
    if isinstance(value, dict):
        return {
            key: "<redacted>" if _private_field(str(key)) else _redact_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_metadata(item) for item in value]
    return value


def _redact_session_file(path: Path) -> str:
    """Return a privacy-safe textual version of a whitelisted session file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            return json.dumps(_redact_metadata(json.loads(text)), indent=2, sort_keys=True)
        except json.JSONDecodeError:
            return "<unparseable JSON omitted from privacy-safe support bundle>\n"
    if path.suffix.lower() == ".jsonl":
        lines: list[str] = []
        for line in text.splitlines():
            try:
                lines.append(json.dumps(_redact_metadata(json.loads(line)), sort_keys=True))
            except json.JSONDecodeError:
                lines.append("<unparseable JSONL record omitted>")
        return "\n".join(lines) + ("\n" if lines else "")
    if path.suffix.lower() == ".csv":
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
                        key: "<redacted>" if _private_field(key) else value
                        for key, value in row.items()
                    }
                )
            return out.getvalue()
        except csv.Error:
            return "<unparseable CSV omitted from privacy-safe support bundle>\n"
    return redact_text(text)
