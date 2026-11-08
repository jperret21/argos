"""The photometry target set and its roles (rows A51-A53).

A Qt-free port of the target-set half of ``AcquisitionEngine``:

- the set is keyed by the observation's object name (D11) and stored as
  ``<sessions_path>/targets/<object>.json`` by ``TargetSet.save`` — the Qt
  file, byte for byte (``_target_path`` / ``target_set`` /
  ``_save_target_set``, ``acquisition_engine.py:1242-1264``);
- ``set_role`` / ``remove`` are ``set_target_role`` / ``remove_target``
  (1295-1302, 1506-1511) with the card's "object name if empty" rule
  (``imaging_page.py:2035-2044``);
- a new target gets its comparisons from the field's VSP sequence through
  ``_auto_select_comparisons`` and the pilot quality gate
  (``_pilot_comparison_quality``), 1348-1491;
- ``geometry`` is ``photometry_geometry`` (1493-1504).

Locking: the set has its own lock, taken before the hub's and never while
the hub's is held; events are published after the set lock is released.
The newest record is cached for a new client's snapshots.
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from argos.core.catalog.photometry import ComparisonQuality, auto_comparison_stars
from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, ROLES, TargetSet, TargetStar
from argos.core.hardware import active as hardware
from argos.core.imaging import sensor_models
from argos.core.imaging.platesolve import angular_separation_deg
from argos.core.photometry.aperture import measure_aperture
from argos.core.photometry.params import DEFAULT_FWHM, PhotometryParams
from argos.server.errors import ApiError
from argos.server.field_measure import FrameMeasurer
from argos.server.observation import target_file

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

ROLE_WORDS = {"target": "Target", "comparison": "Comparison", "check": "Check"}


def star_record(star: TargetStar, xy: tuple[float, float] | None = None) -> dict[str, Any]:
    """A ``TargetStar`` on the wire (protocol.md "Target set")."""
    return {
        "key": star.key(),
        "role": star.role,
        "name": star.name,
        "display_name": star.display_name,
        "ra_deg": star.ra_deg,
        "dec_deg": star.dec_deg,
        "ra_hours": star.ra_deg / 15.0,
        "auid": star.auid,
        "source": star.source,
        "mags": dict(star.mags),
        "chart_id": star.chart_id,
        "note": star.note,
        "x": round(xy[0], 2) if xy is not None else None,
        "y": round(xy[1], 2) if xy is not None else None,
    }


def pending_star(
    ra_deg: float,
    dec_deg: float,
    *,
    auid: str | None,
    name: str | None,
    source: str,
    mags: dict | None = None,
    chart_id: str | None = None,
) -> dict[str, Any]:
    """The Qt card's ``pending`` dict (``imaging_page.py:804-978``), with ``ra_hours``."""
    return {
        "ra_deg": float(ra_deg),
        "dec_deg": float(dec_deg),
        "ra_hours": float(ra_deg) / 15.0,
        "auid": auid,
        "name": name,
        "source": source,
        "mags": dict(mags or {}),
        "chart_id": chart_id,
    }


def star_from_pending(pending: dict[str, Any], role: str) -> TargetStar:
    """``TargetStar(role=role, **pending)`` (``imaging_page.py:2039``)."""
    if pending.get("ra_deg") is not None:
        ra_deg = float(pending["ra_deg"])
    elif pending.get("ra_hours") is not None:
        ra_deg = float(pending["ra_hours"]) * 15.0
    else:
        raise ApiError(400, "invalid_argument", "The star needs ra_deg or ra_hours")
    if pending.get("dec_deg") is None:
        raise ApiError(400, "invalid_argument", "The star needs dec_deg")
    dec_deg = float(pending["dec_deg"])
    if not (math.isfinite(ra_deg) and math.isfinite(dec_deg)) or not -90.0 <= dec_deg <= 90.0:
        raise ApiError(400, "invalid_argument", "The star's coordinates are out of range")
    mags = pending.get("mags") or {}
    if not isinstance(mags, dict):
        raise ApiError(400, "invalid_argument", "mags must be an object {band: magnitude}")
    return TargetStar(
        role=role,
        ra_deg=ra_deg % 360.0,
        dec_deg=dec_deg,
        auid=pending.get("auid") or None,
        name=pending.get("name") or None,
        source=str(pending.get("source") or "manual"),
        mags={str(k): float(v) for k, v in mags.items()},
        chart_id=pending.get("chart_id") or None,
    )


class TargetService:
    """The target set of the current object (``targets`` event)."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._lock = threading.RLock()
        self._set: TargetSet | None = None
        self._path: Path | None = None
        self._revision = 0
        self._last_fwhm: float | None = None
        self._last_aperture: float | None = None
        self._record: dict[str, Any] | None = None

    # -- the set ------------------------------------------------------------------

    def _object_name(self) -> str:
        """``_object_name`` (``acquisition_engine.py:1242-1245``)."""
        with self._hub._lock:
            name = self._hub.observation.object_name
        return (name or "").strip() or "Unknown"

    def _current(self) -> tuple[TargetSet, Path]:
        """``target_set`` (1251-1257): reload when the object (or folder) changed. Lock held."""
        obj = self._object_name()
        path = target_file(self._hub._sessions_root(), obj)
        if self._set is None or self._set.object_name != obj or self._path != path:
            self._set = TargetSet.load(path)
            self._set.object_name = obj
            self._path = path
        return self._set, path

    def target_set(self) -> TargetSet:
        with self._lock:
            return self._current()[0]

    def _save(self, tset: TargetSet, path: Path) -> None:
        """``_save_target_set`` (1259-1264). Lock held."""
        try:
            tset.save(path)
        except OSError as exc:
            self._hub.log("error", f"Save targets: {exc}", source="photometry", topic="photometry")
            raise ApiError(500, "io_error", f"Save targets: {exc}") from exc

    # -- geometry -------------------------------------------------------------------

    def egain(self) -> float:
        """``_egain`` (1517-1529): config table → driver → active sensor reference."""
        with self._hub._lock:
            gain = int(self._hub._capture_settings.gain)
            camera = self._hub._slots["camera"].handle
        table = self._hub.config.get("camera.egain_table", {}) or {}
        if isinstance(table, dict) and str(gain) in table:
            try:
                return float(table[str(gain)])
            except (TypeError, ValueError):
                pass
        reader = getattr(camera, "fits_readings", None) if camera is not None else None
        if reader is not None:
            try:
                value = reader().get("egain_driver")
            except Exception as exc:  # a driver error must not block a role
                logger.info("egain from the driver unavailable: %s", exc)
                value = None
            if value:
                return float(value)
        return sensor_models.lookup_egain(hardware.profile().sensor, gain)

    def params(self, egain: float | None = None) -> PhotometryParams:
        return PhotometryParams.from_config(
            self._hub.config.get, egain=egain if egain is not None else 1.0
        )

    def geometry(self) -> dict[str, Any]:
        """``photometry_geometry`` (1493-1504), green and frame px."""
        params = self.params()
        fwhm = self._last_fwhm
        aperture = params.aperture_px(fwhm)
        inner = max(params.annulus_in_px, aperture + 1.0)
        outer = max(params.annulus_out_px, inner + 2.0)
        return {
            "aperture_px": aperture,
            "annulus_in_px": inner,
            "annulus_out_px": outer,
            "aperture_r_px": 2.0 * aperture,
            "annulus_in_r_px": 2.0 * inner,
            "annulus_out_r_px": 2.0 * outer,
            "fwhm_px": fwhm,
            "fwhm_source": "frame" if fwhm else "default",
        }

    def on_frame_fwhm(self, fwhm: float | None) -> None:
        """A metered frame's mean FWHM (green px): the aperture follows it."""
        if fwhm is None or not math.isfinite(float(fwhm)) or fwhm <= 0:
            return
        self._last_fwhm = float(fwhm)
        aperture = round(self.params().aperture_px(self._last_fwhm), 1)
        if aperture != self._last_aperture:
            self._last_aperture = aperture
            self.publish()

    # -- record and events -------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        with self._lock:
            tset, path = self._current()
            stars = list(tset.stars)
            summary = tset.summary()
            obj = tset.object_name
            revision = self._revision
        project = self._hub.field.project_reference
        return {
            "object_name": obj,
            "path": str(path),
            "stars": [star_record(s, project(s.ra_deg, s.dec_deg)) for s in stars],
            "summary": summary,
            "geometry": self.geometry(),
            "revision": revision,
        }

    def cached_record(self) -> dict[str, Any] | None:
        return self._record

    def publish(self) -> dict[str, Any]:
        record = self.record()
        with self._hub._lock:
            self._record = record
            self._hub._publish("targets", record)
        return record

    def _changed(self) -> dict[str, Any]:
        """After a role change: revision, tracker reset, ``targets`` and ``field_layers``."""
        with self._lock:
            self._revision += 1
        self._hub.field.on_targets_changed()
        return self.publish()

    def on_object_changed(self) -> None:
        """``on_object_changed`` (1281-1293): the set follows the object name."""
        with self._lock:
            before = self._path
            self._current()
            moved = self._path != before
            if moved:
                self._revision += 1
        if moved:
            self._hub.field.on_targets_changed()
        self.publish()

    def reload(self) -> None:
        """Re-read the file (another writer, a new sessions folder)."""
        with self._lock:
            self._set = None
            self._revision += 1
        self._hub.field.on_targets_changed()
        self.publish()

    # -- A52 / A53 ---------------------------------------------------------------------

    def assign(self, star: TargetStar) -> dict[str, Any]:
        """``POST /api/targets``: the card's role buttons (``imaging_page.py:2035-2044``)."""
        if star.role not in ROLES:
            raise ApiError(400, "invalid_argument", f"Unknown role {star.role!r}")
        with self._hub._lock:
            empty = not self._hub.observation.object_name.strip()
        if empty:
            # Before the save, whatever the role: the object name keys
            # targets.json + FITS OBJECT (imaging_page.py:2040-2042).
            self._hub.observation.set_name(star.display_name)
        with self._lock:
            tset, path = self._current()
            tset.set_role(star)
            if star.role == ROLE_TARGET:
                self._auto_select_comparisons(tset, star)
            self._save(tset, path)
        self._hub.log(
            "ok",
            f"{ROLE_WORDS[star.role]}: {star.display_name}",
            source="photometry",
            topic="photometry",
        )
        return self._changed()

    def remove(self, key: str) -> dict[str, Any]:
        """``DELETE /api/targets/{key}`` (``remove_target``, 1506-1511)."""
        with self._lock:
            tset, path = self._current()
            removed = next((s for s in tset.stars if s.key() == key), None)
            if removed is None:
                raise ApiError(404, "not_found", f"No star {key!r} in the target set")
            tset.remove(key)
            self._save(tset, path)
        self._hub.log(
            "ok",
            f"Removed from target set: {removed.display_name}",
            source="photometry",
            topic="photometry",
        )
        record = self._changed()
        return {**record, "removed": star_record(removed)}

    def write_role_for(self, object_name: str, star: TargetStar) -> Path:
        """Set a role in another object's set (a catalogue target, ``observation.py``)."""
        path = target_file(self._hub._sessions_root(), object_name)
        with self._lock:
            tset = TargetSet.load(path)
            tset.object_name = object_name
            tset.set_role(star)
            if star.role == ROLE_TARGET:
                self._auto_select_comparisons(tset, star)
            tset.save(path)
            if self._path == path:
                self._set = None  # re-read on the next access
        return path

    def backfill_comparisons(self) -> None:
        """The VSP answer arrived after the target (``_on_catalog``, 1225-1240)."""
        with self._lock:
            tset, path = self._current()
            targets = tset.by_role(ROLE_TARGET)
            if not targets:
                return
            self._auto_select_comparisons(tset, targets[0])
            if not tset.by_role(ROLE_COMPARISON):
                return
            self._save(tset, path)
        self._changed()

    # -- comparisons (acquisition_engine.py:1348-1491) ---------------------------------

    def _auto_select_comparisons(self, tset: TargetSet, target: TargetStar) -> int:
        """``_auto_select_comparisons`` (1348-1429). Lock held."""
        comparisons = self._hub.field.comparisons()
        if not comparisons:
            return 0
        cfg = self._hub.config.get
        band = str(cfg("photometry.default_band", "TG") or "TG")
        existing = tset.by_role(ROLE_COMPARISON)
        calibrated = [
            s for s in existing if s.mags.get(band) is not None or s.mags.get("V") is not None
        ]
        wanted = max(0, int(cfg("photometry.auto_comparisons", 5)) - len(calibrated))
        if wanted <= 0:
            return 0
        pilot = self._hub.field.pilot()
        target_inst_mag, quality = self._pilot_quality(target, comparisons, pilot)
        min_snr = float(cfg("photometry.comparison_min_snr", 10.0))
        max_delta = float(cfg("photometry.comparison_max_delta_mag", 1.5))
        max_separation = float(cfg("photometry.comparison_max_separation_arcmin", 25.0))
        picks = auto_comparison_stars(
            target.ra_deg,
            target.dec_deg,
            comparisons,
            wcs=pilot.wcs if pilot is not None else None,
            green_shape=pilot.green_shape if pilot is not None else None,
            count=wanted + len(existing),
            candidate_quality=quality,
            target_inst_mag=target_inst_mag,
            min_snr=min_snr,
            max_delta_inst_mag=max_delta,
            max_separation_arcmin=max_separation,
        )

        def already_present(candidate: TargetStar) -> bool:
            for saved in tuple(existing):
                if saved.auid and candidate.auid and saved.auid == candidate.auid:
                    return True
                if (
                    angular_separation_deg(
                        saved.ra_deg / 15.0,
                        saved.dec_deg,
                        candidate.ra_deg / 15.0,
                        candidate.dec_deg,
                    )
                    < 1.0 / 3600.0
                ):
                    if not saved.mags:
                        tset.remove(saved.key())
                        existing.remove(saved)
                        return False
                    return True
            return False

        picks = [p for p in picks if not already_present(p)][:wanted]
        for comp in picks:
            tset.set_role(comp)
        if picks:
            self._hub.log(
                "ok",
                f"Photometry: {len(picks)} pilot-qualified comparison(s) selected "
                f"for {target.display_name}",
                source="photometry",
                topic="photometry",
            )
        if quality is not None and len(picks) < wanted:
            self._hub.log(
                "warning",
                f"Photometry: only {len(picks)} of {wanted} requested comparisons pass "
                f"the pilot quality gate (SNR ≥ {min_snr:g}, Δmag ≤ {max_delta:g}, "
                f"distance ≤ {max_separation:g}′).",
                source="photometry",
                topic="photometry",
            )
        return len(picks)

    def _pilot_quality(
        self, target: TargetStar, comparisons: list, pilot: Any
    ) -> tuple[float | None, dict[str, ComparisonQuality] | None]:
        """``_pilot_comparison_quality`` (1431-1491) on the newest frame of the solved
        geometry, through the tracked solution (Qt used the reference solve)."""
        if pilot is None:
            return None, None
        measure = self.pilot_measure(pilot)
        target_phot = measure(target.ra_deg, target.dec_deg)
        if target_phot is None or target_phot.inst_mag is None:
            return None, None
        quality: dict[str, ComparisonQuality] = {}
        for star in comparisons:
            phot = measure(star.ra_deg, star.dec_deg)
            if phot is not None:
                quality[star.auid] = ComparisonQuality(
                    snr=phot.snr,
                    inst_mag=phot.inst_mag,
                    saturated=phot.saturated,
                    suspect=phot.suspect,
                )
        return target_phot.inst_mag, quality

    def pilot_measure(self, pilot: Any, egain: float | None = None):
        """The ``measure(ra, dec)`` closure of ``_pilot_comparison_quality`` (1450-1478)."""
        params = self.params(egain if egain is not None else self.egain())
        fwhm = self._last_fwhm or DEFAULT_FWHM
        r_ap = params.aperture_px(fwhm)
        r_in = max(params.annulus_in_px, r_ap + 1.0)
        r_out = max(params.annulus_out_px, r_in + 2.0)
        # One green plane and sky for the whole ensemble (identical results).
        measurer = FrameMeasurer(pilot.raw)
        green = measurer.green
        wcs = pilot.wcs

        def measure(ra_deg: float, dec_deg: float):
            x, y = wcs.world_to_pixel_deg(ra_deg, dec_deg)
            centroid = measurer.measure_star_at(
                float(x), float(y), radius=max(2, int(round(r_ap))), search=3
            )
            if centroid is None or math.hypot(centroid.x - float(x), centroid.y - float(y)) > 3.0:
                return None
            return measure_aperture(
                green,
                centroid.x,
                centroid.y,
                r_ap,
                r_in,
                r_out,
                egain=params.egain,
                read_noise_e=params.read_noise_e,
                sat_adu=params.sat_adu,
            )

        return measure
