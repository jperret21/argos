"""Observation identity and catalogue lookups (rows A20, A38-A41).

- **One observation identity** (D11): the object name every Take shot writes
  to ``OBJECT`` and its folder, and the catalogue target the Mount card's
  Slew uses. A Qt-free port of ``ImagingPage.set_catalogue_target``
  (``imaging_page.py:2733-2756``): a catalogue choice sets the name and the
  coordinates, and only a variable-star type (``is_variable_object_type``,
  Q-P8) — or an exoplanet programme — becomes the photometry *target* of
  ``<sessions_path>/targets/<object>.json`` (``acquisition_engine.py:
  1247-1302``; comparisons are chosen in wave 5).
- **Lookups**: ``resolve_object``, ``cached_object_suggestions`` and
  ``resolve_nearby_objects`` of ``argos.core.catalog.object_resolver``,
  always with the configured cache file (``data_paths.object_catalogue_cache``),
  run by the request thread (FastAPI's pool), never on the event loop.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from argos.core.catalog import object_resolver
from argos.core.catalog.object_resolver import (
    ObjectResolutionError,
    is_variable_object_type,
    object_type_label,
)
from argos.core.catalog.targets import ROLE_TARGET, TargetSet, TargetStar
from argos.server.errors import ApiError
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

PROGRAMMES = ("variable", "exoplanet", "other")
#: Resolver entry points; tests replace them (no network in the suite).
Resolver = Callable[..., Any]


def target_file(sessions_path: Path, object_name: str) -> Path:
    """``_target_path`` (``acquisition_engine.py:1247-1249``)."""
    obj = object_name or "Unknown"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in obj)
    return Path(sessions_path) / "targets" / f"{safe or 'Unknown'}.json"


def resolved_record(result: Any) -> dict[str, Any]:
    """A ``ResolvedObject`` as the API's ``Resolved``."""
    object_type = str(getattr(result, "object_type", "") or "")
    return {
        "name": result.name,
        "ra_hours": float(result.ra_degrees) / 15.0,
        "dec_deg": float(result.dec_degrees),
        "object_type": object_type,
        "type_label": object_type_label(object_type),
        "is_variable": is_variable_object_type(object_type),
        "source": str(getattr(result, "source", "") or ""),
    }


def candidate_record(nearby: Any) -> dict[str, Any]:
    return {**resolved_record(nearby.object), "separation_arcsec": float(nearby.separation_arcsec)}


def _match_key(text: str) -> str:
    """The catalogue's own comparison key (``object_resolver._cache_key``)."""
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _suggest_rank(name: str, query: str) -> tuple[int, list[Any]]:
    """Exact match first, then names starting with the text, each in natural order."""
    key, q = _match_key(name), _match_key(query)
    quality = 0 if key == q else 1 if key.startswith(q) else 2
    natural = [
        int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)
    ]
    # Mixed int / str parts never compare: tag each part with its kind.
    return quality, [(0, p) if isinstance(p, int) else (1, p) for p in natural]


class ObservationService:
    """The observation record, the catalogue routes and the Stellarium suggestions."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._record: dict[str, Any] = {
            "object_name": "",
            "target": None,
            "photometry_target": None,
            "locked": False,
            "locked_reason": None,
            "revision": 0,
        }
        self._suggestions: dict[str, Any] | None = None
        self._suggest_lock = threading.Lock()
        #: Injectable resolver functions (tests: no network).
        self.resolve_object: Resolver = object_resolver.resolve_object
        self.suggest_names: Resolver = object_resolver.cached_object_suggestions
        self.resolve_nearby: Resolver = object_resolver.resolve_nearby_objects

    # -- record -------------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        record = dict(self._record)
        if record["target"] is not None:
            record["target"] = dict(record["target"])
        if record["photometry_target"] is not None:
            record["photometry_target"] = dict(record["photometry_target"])
        return record

    @property
    def object_name(self) -> str:
        return self._record["object_name"]

    @property
    def target(self) -> dict[str, Any] | None:
        return self._record["target"]

    def suggestions(self) -> dict[str, Any] | None:
        return dict(self._suggestions) if self._suggestions else None

    def _set(self, **changes: Any) -> dict[str, Any]:
        """Hub lock held."""
        self._record = {**self._record, **changes, "revision": self._record["revision"] + 1}
        self._hub._publish("observation", self.record())
        return self.record()

    def _check_unlocked(self) -> None:
        if self._record["locked"]:
            raise ApiError(
                409,
                "busy",
                self._record["locked_reason"] or "A sequence owns the observation.",
                details={"owner": "sequence"},
            )

    # -- PUT /api/observation, POST/DELETE /api/observation/target ---------------------

    def set_name(self, name: str) -> dict[str, Any]:
        name = " ".join(str(name).split())
        with self._hub._lock:
            self._check_unlocked()
            if name == self._record["object_name"]:
                return self.record()
            target = self._record["target"]
            photometry = self._record["photometry_target"]
            if target is not None and target["name"] != name:
                target = None
            if photometry is not None and photometry["name"] != name:
                photometry = None
            record = self._set(object_name=name, target=target, photometry_target=photometry)
        self._hub.log(
            "info",
            f"Object: {name or 'none'} (FITS OBJECT {name or 'Unknown'})",
            source="observation",
            topic="camera",
        )
        return record

    def set_target(
        self,
        name: str,
        ra_hours: float,
        dec_deg: float,
        object_type: str = "",
        source: str = "",
        programme: str | None = None,
    ) -> dict[str, Any]:
        """``set_catalogue_target`` (``imaging_page.py:2733-2756``)."""
        name = " ".join(str(name).split())
        if not name:
            raise ApiError(400, "invalid_argument", "The target needs a name")
        object_type = str(object_type or "")
        is_variable = is_variable_object_type(object_type)
        if programme is None:
            programme = "variable" if is_variable else "other"
        target = {
            "name": name,
            "ra_hours": float(ra_hours) % 24.0,
            "dec_deg": float(dec_deg),
            "object_type": object_type,
            "type_label": object_type_label(object_type),
            "is_variable": is_variable,
            "source": str(source or ""),
            "programme": programme,
        }
        photometry = None
        with self._hub._lock:
            self._check_unlocked()
        if is_variable or programme == "exoplanet":
            photometry = self._write_photometry_target(target)
        with self._hub._lock:
            self._check_unlocked()
            record = self._set(object_name=name, target=target, photometry_target=photometry)
        self._hub.log(
            "info",
            f"Catalogue target: {name} — RA {target['ra_hours']:.5f}h Dec {target['dec_deg']:+.5f}°",
            source="observation",
            topic="camera",
        )
        return record

    def clear_target(self) -> dict[str, Any]:
        with self._hub._lock:
            self._check_unlocked()
            if self._record["target"] is None and self._record["photometry_target"] is None:
                return self.record()
            return self._set(target=None, photometry_target=None)

    def _write_photometry_target(self, target: dict[str, Any]) -> dict[str, Any] | None:
        """The ``target`` role of ``targets/<object>.json`` (``_set_photometry_target``,
        ``imaging_page.py:2762-2775``; ``set_target_role``, ``acquisition_engine.py:1295-1302``)."""
        path = target_file(self._hub._sessions_root(), target["name"])
        star = TargetStar(
            role=ROLE_TARGET,
            ra_deg=target["ra_hours"] * 15.0,
            dec_deg=target["dec_deg"],
            name=target["name"],
            source=(
                "exoplanet_catalogue"
                if target["programme"] == "exoplanet"
                else "variable_catalogue"
            ),
            mags={},
        )
        try:
            tset = TargetSet.load(path)
            tset.object_name = target["name"]
            tset.set_role(star)
            tset.save(path)
        except OSError as exc:
            self._hub.log("error", f"Save targets: {exc}", source="observation", topic="camera")
            return None
        return {"key": star.key(), "name": target["name"], "path": str(path)}

    # -- catalogue lookups ------------------------------------------------------------

    def _cache_path(self) -> Path | None:
        value = self._hub.config.get("data_paths.object_catalogue_cache", "")
        return Path(str(value)).expanduser() if value else None

    def resolve(self, query: str) -> dict[str, Any]:
        """``GET /api/catalog/resolve`` (``object_resolver.resolve_object``)."""
        text = " ".join(str(query or "").split())
        if not text:
            raise ApiError(400, "invalid_argument", "Enter an object designation first.")
        try:
            result = self.resolve_object(text, timeout_s=8.0, cache_path=self._cache_path())
        except ObjectResolutionError as exc:
            message = str(exc)
            if message.startswith("No ICRS coordinates") or "invalid coordinates" in message:
                raise ApiError(404, "not_found", message) from exc
            if message.startswith("Enter an object"):
                raise ApiError(400, "invalid_argument", message) from exc
            raise ApiError(502, "lookup_failed", message) from exc
        return resolved_record(result)

    def suggest(self, query: str, limit: int = 8) -> dict[str, Any]:
        """``GET /api/catalog/suggest`` (``cached_object_suggestions``), offline.

        The core lists names in lexical order ("M 1, M 100, M 104…", which
        skips M 10-M 19): a wider page is read and ordered by match quality
        (the name itself, then names starting with the text) and then in
        natural order, numbers by value (design review of wave 3).
        """
        text = str(query or "").strip()
        names: list[str] = []
        if text:
            try:
                wide = max(limit * 25, 200)
                found = self.suggest_names(text, cache_path=self._cache_path(), limit=wide)
                names = sorted(dict.fromkeys(found), key=lambda n: _suggest_rank(n, text))
            except Exception as exc:  # a corrupt cache must not break typing
                logger.warning("Suggestions failed: %s", exc)
        return {"query": text, "names": names[:limit]}

    def nearby(
        self, ra_hours: float, dec_deg: float, network: bool = False, radius_arcsec: float = 90.0
    ) -> dict[str, Any]:
        """``GET /api/catalog/nearby`` (``resolve_nearby_objects``)."""
        try:
            found = self.resolve_nearby(
                (float(ra_hours) % 24.0) * 15.0,
                float(dec_deg),
                radius_arcsec=float(radius_arcsec),
                allow_network=bool(network),
                timeout_s=8.0,
                cache_path=self._cache_path(),
            )
        except ObjectResolutionError as exc:
            raise ApiError(502, "lookup_failed", str(exc)) from exc
        return {"candidates": [candidate_record(n) for n in found], "network": bool(network)}

    def suggest_after_goto(self, ra_hours: float, dec_deg: float) -> None:
        """``target_suggestions`` after a Stellarium GoTo (``imaging_page.py:2809-2841``).

        Offers names; never sets one. Online only when
        ``stellarium.online_target_lookup`` is on. Runs on its own thread.
        """
        allow = bool(self._hub.config.get("stellarium.online_target_lookup", False))
        if not self._suggest_lock.acquire(blocking=False):
            return  # one lookup at a time, as the Qt worker
        try:
            self._publish_suggestions(ra_hours, dec_deg, "checking", [], None)
            try:
                found = self.resolve_nearby(
                    (float(ra_hours) % 24.0) * 15.0,
                    float(dec_deg),
                    allow_network=allow,
                    cache_path=self._cache_path(),
                )
            except ObjectResolutionError as exc:
                self._publish_suggestions(ra_hours, dec_deg, "failed", [], str(exc))
                self._hub.log(
                    "warning",
                    f"Target-name suggestion: {exc}",
                    source="stellarium",
                    topic="planetarium",
                )
                return
            except Exception as exc:
                logger.exception("Target-name lookup failed")
                text = "Target-name lookup failed unexpectedly. See the log for details."
                self._publish_suggestions(ra_hours, dec_deg, "failed", [], text)
                self._hub.log("warning", f"Target-name suggestion: {text}", source="stellarium")
                del exc
                return
            candidates = [candidate_record(n) for n in found]
            self._publish_suggestions(ra_hours, dec_deg, "ready", candidates, None)
            if candidates:
                self._hub.log(
                    "info",
                    f"Stellarium target-name suggestion: {len(candidates)} nearby catalogue "
                    "candidate(s).",
                    source="stellarium",
                    topic="planetarium",
                )
        finally:
            self._suggest_lock.release()

    def _publish_suggestions(
        self,
        ra_hours: float,
        dec_deg: float,
        state: str,
        candidates: list[dict[str, Any]],
        message: str | None,
    ) -> None:
        record = {
            "ra_hours": float(ra_hours),
            "dec_deg": float(dec_deg),
            "state": state,
            "candidates": candidates,
            "message": message,
            "t": utc_iso(),
        }
        with self._hub._lock:
            self._suggestions = record
            self._hub._publish("target_suggestions", dict(record))
            self._hub._publish("stellarium", self._hub._stellarium_state())
