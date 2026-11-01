"""The configuration file, read and written by the server (rows A8-A10).

The same ``config.json`` the Qt app uses (``argos/core/config.py``), so both
UIs see one configuration during the transition. ``Config`` itself cannot be
reused as is: its location is a module constant (``~/.argos``, which tests
and smoke runs must never touch), ``Config.set`` writes the file on every key
(``config.py:241-248``) without atomicity, and nothing reports what changed.
This store keeps the core's format and loading rules — the shipped defaults
deep-merged under the file, then the five migrations, exactly as
``Config.load`` (``config.py:196-219``) — and adds:

- a configurable folder (``None`` = in memory, never written);
- one validated **commit** per request: every key checked against
  :mod:`argos.server.config_meta` first, nothing written if one fails;
- an **atomic** write: temporary file in the same folder, ``fsync``,
  ``os.replace``; a crash leaves the old or the new file, never a mix;
- **external changes**: the file's stamp (mtime, size, inode) is compared
  before every commit and every ``GET``; when another program (the Qt app)
  wrote it, it is re-read first, so a commit never overwrites that change,
  and the change is announced;
- a listener called with ``(changed, values, revision, source)`` while the
  store lock is held, so announcements leave in commit order.

Reads (:meth:`get`, :meth:`values`) take no lock: the data dict is replaced
whole on every change, never mutated, so a reader always sees one version.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from argos.core import config as core_config
from argos.core.hardware import active, catalog
from argos.server.config_meta import (
    LEGACY_MIRROR,
    META,
    InvalidValue,
    validate_value,
)
from argos.server.errors import ApiError

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "config.json"

#: ``(changed, values, revision, source)``; called with the store lock held.
Listener = Callable[[dict[str, Any], dict[str, Any], int, str], None]

_MISSING = object()


@dataclass(frozen=True)
class PatchResult:
    values: dict[str, Any]
    changed: dict[str, Any]
    warnings: list[dict[str, str]]
    revision: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": self.values,
            "changed": self.changed,
            "warnings": self.warnings,
            "revision": self.revision,
        }


def _get_nested(data: dict[str, Any], key: str, default: Any = None) -> Any:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _set_nested(data: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    node = data
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    if value is _MISSING:
        node.pop(parts[-1], None)
    else:
        node[parts[-1]] = value


def _flatten(data: dict[str, Any]) -> dict[str, Any]:
    """The exposed values: one entry per key of :data:`META`."""
    values: dict[str, Any] = {}
    for key, meta in META.items():
        value = _get_nested(data, key, _MISSING)
        values[key] = copy.deepcopy(meta.default) if value is _MISSING else value
    return values


def load_config_data(path: Path) -> dict[str, Any]:
    """Defaults + file + migrations, as ``Config.load`` (``config.py:206-216``).

    Raises ``OSError`` or ``ValueError`` when the file cannot be read or parsed.
    """
    with path.open("r", encoding="utf-8") as handle:
        on_disk = json.load(handle)
    if not isinstance(on_disk, dict):
        raise ValueError("the top level is not a JSON object")
    data = core_config._deep_merge(core_config._DEFAULTS, on_disk)
    core_config._migrate_camera_keys(data)
    core_config._migrate_legacy_site(data, on_disk)
    core_config._migrate_alpaca_profiles(data, on_disk)
    core_config._migrate_diagnostics_opt_in(data, on_disk)
    core_config._migrate_catalogue_display_limit(data, on_disk)
    return data


def _stamp(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


class ConfigStore:
    """Thread-safe owner of the configuration (see the module docstring)."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = Path(directory).expanduser() if directory is not None else None
        self._path = self._dir / CONFIG_FILENAME if self._dir is not None else None
        self._lock = threading.RLock()
        self._listeners: list[Listener] = []
        self._data: dict[str, Any] = core_config._deep_copy(core_config._DEFAULTS)
        self._stamp: tuple[int, int, int] | None = None
        self._revision = 0
        #: Why the file could not be read at start-up (it is kept aside before
        #: the first write replaces it), or ``None``.
        self.load_error: str | None = None
        self._load_initial()

    # -- properties ----------------------------------------------------------

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def directory(self) -> Path | None:
        return self._dir

    @property
    def revision(self) -> int:
        return self._revision

    def add_listener(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    # -- reading ---------------------------------------------------------------

    def _load_initial(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            self._data = load_config_data(self._path)
            self._stamp = _stamp(self._path)
        except (OSError, ValueError) as exc:
            self.load_error = f"{self._path}: {exc}"
            logger.error("Could not read the configuration (%s); using the defaults", exc)

    def get(self, key: str, default: Any = None) -> Any:
        """Any dotted key of the file (exposed or not), like ``Config.get``."""
        return _get_nested(self._data, key, default)

    def values(self) -> dict[str, Any]:
        return copy.deepcopy(_flatten(self._data))

    def snapshot(self) -> dict[str, Any]:
        """``GET /api/config``: re-reads the file first if another program wrote it."""
        self.refresh()
        return {
            "values": self.values(),
            "meta": {key: meta.to_dict() for key, meta in META.items()},
            "revision": self._revision,
            "path": str(self._path) if self._path is not None else None,
        }

    def refresh(self) -> dict[str, Any]:
        """Re-read the file if it changed on disk; returns (and announces) what changed."""
        with self._lock:
            return self._reload_if_changed()

    def _reload_if_changed(self) -> dict[str, Any]:
        if self._path is None:
            return {}
        stamp = _stamp(self._path)
        if stamp is None or stamp == self._stamp:
            return {}  # unchanged, or deleted: keep what we have
        try:
            fresh = load_config_data(self._path)
        except (OSError, ValueError) as exc:
            logger.warning("Configuration changed on disk but cannot be read: %s", exc)
            return {}
        before = _flatten(self._data)
        self._data = fresh
        self._stamp = stamp
        self.load_error = None
        after = _flatten(fresh)
        changed = {key: after[key] for key in after if after[key] != before.get(key)}
        if changed:
            self._revision += 1
            logger.info("Configuration changed by another program: %s", sorted(changed))
            self._notify(changed, "file")
        return changed

    # -- writing ---------------------------------------------------------------

    def patch(self, changes: dict[str, Any], source: str = "api") -> PatchResult:
        """``PATCH /api/config``: validate every key, then commit them together."""
        if not isinstance(changes, dict) or not changes:
            raise ApiError(400, "invalid_argument", "Send at least one setting to change")
        errors: dict[str, str] = {}
        normalised: dict[str, Any] = {}
        warnings: list[dict[str, str]] = []
        for key, value in changes.items():
            meta = META.get(key)
            if meta is None:
                errors[key] = "unknown setting"
                continue
            if meta.read_only:
                errors[key] = (
                    "is changed with PUT /api/profile"
                    if key == "hardware.profile"
                    else "is read-only"
                )
                continue
            try:
                normalised[key], warning = validate_value(meta, value)
            except InvalidValue as exc:
                errors[key] = str(exc)
                continue
            if warning:
                warnings.append({"key": key, "message": warning})
        if errors:
            first = next(iter(errors))
            raise ApiError(
                400,
                "invalid_argument",
                f"{META[first].label if first in META else first}: {errors[first]}",
                details={"fields": errors},
            )
        return self._commit(normalised, warnings, source)

    def set_internal(self, changes: dict[str, Any], source: str = "server") -> PatchResult:
        """Commit values the server itself decided (profile, last Alpaca address).

        Read-only keys are allowed here; values are still validated.
        """
        normalised = {}
        for key, value in changes.items():
            meta = META[key]
            try:
                normalised[key], _ = validate_value(meta, value)
            except InvalidValue as exc:
                raise ApiError(400, "invalid_argument", f"{meta.label}: {exc}") from exc
        return self._commit(normalised, [], source)

    def _commit(
        self, normalised: dict[str, Any], warnings: list[dict[str, str]], source: str
    ) -> PatchResult:
        with self._lock:
            self._reload_if_changed()
            before = _flatten(self._data)
            data = copy.deepcopy(self._data)
            for key, value in normalised.items():
                _set_nested(data, key, _MISSING if value is None else value)
            self._side_values(data, normalised)
            after = _flatten(data)
            changed = {key: after[key] for key in after if after[key] != before.get(key)}
            if data != self._data:
                self._write(data)
                self._data = data
                if changed:
                    self._revision += 1
                    self._notify(changed, source)
            return PatchResult(
                values=copy.deepcopy(after),
                changed=copy.deepcopy(changed),
                warnings=warnings,
                revision=self._revision,
            )

    @staticmethod
    def _side_values(data: dict[str, Any], normalised: dict[str, Any]) -> None:
        """Keys written along with others, as the Qt editors did."""
        if "diagnostics.enabled" in normalised:
            # configuration_page.py:1200-1206: the first explicit choice marks
            # the opt-in so the load migration never overrides it again.
            _set_nested(data, "diagnostics.local_opt_in_v1", True)
        mirror = [key for key in LEGACY_MIRROR if key in normalised]
        if mirror:
            # Decision Q-C1: the web edits hardware.overrides; the Qt app still
            # reads camera.* (imaging_page.py:722, params.py:64), so the
            # effective value is mirrored there.
            key = _get_nested(data, active.CFG_PROFILE, catalog.DEFAULT_PROFILE.key)
            base = catalog.get(key) or catalog.DEFAULT_PROFILE
            for override_key in mirror:
                legacy_key, field_name = LEGACY_MIRROR[override_key]
                value = _get_nested(data, override_key, None)
                _set_nested(data, legacy_key, getattr(base, field_name) if value is None else value)

    def _write(self, data: dict[str, Any]) -> None:
        if self._path is None or self._dir is None:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            if self.load_error is not None and self._path.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                kept = self._path.with_name(f"{CONFIG_FILENAME}.unreadable-{stamp}")
                os.replace(self._path, kept)
                logger.warning("Unreadable configuration kept as %s", kept)
                self.load_error = None
            try:
                mode = self._path.stat().st_mode & 0o777
            except OSError:
                mode = 0o644
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{CONFIG_FILENAME}.", suffix=".tmp", dir=self._dir
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(tmp_name, mode)
                os.replace(tmp_name, self._path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            _fsync_dir(self._dir)
            self._stamp = _stamp(self._path)
        except OSError as exc:
            logger.error("Could not write %s: %s", self._path, exc)
            raise ApiError(
                500, "internal_error", f"Could not write the configuration: {exc}"
            ) from exc

    def _notify(self, changed: dict[str, Any], source: str) -> None:
        values = _flatten(self._data)
        for listener in list(self._listeners):
            try:
                listener(copy.deepcopy(changed), copy.deepcopy(values), self._revision, source)
            except Exception:
                logger.exception("Configuration listener failed")


def _fsync_dir(directory: Path) -> None:
    """Make the rename durable (best effort; not every platform allows it)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
