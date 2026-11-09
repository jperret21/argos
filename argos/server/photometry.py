"""Live differential photometry (rows A54-A58 of ``web/spec/README.md`` §4.3).

A Qt-free port of the live photometry half of ``AcquisitionEngine``
(``argos/core/session/acquisition_engine.py``, 0.5.0):

- **when**: one point per field solution outside a sequence
  (``measure_photometry_if_idle``, 1062-1065, called by
  ``_on_astrometry_solved``, ``imaging_page.py:1417``), on the newest frame
  of the solved geometry (Qt's ``_last_raw``); a sequence measures every
  saved sub (``_on_seq_frame_saved``, 772-797: :meth:`measure_saved_frame`);
- **what**: ``_measure_photometry`` (1604-1667) over the unchanged core
  ``measure_frame`` with the apertures placed by core's ``ApertureTracker``
  (``_wcs_for_frame`` / ``_build_live_tracker``, 1542-1582: an owner decision,
  the wave 4 ``FieldTracker`` keeps placing the overlays), the series FWHM
  (P7), ``_emit_live_point`` (1700-1765), the run-level floor
  (``_apply_systematic_floor``, 1767-1795), the CSVs (``_photometry_csv_path``,
  1531-1540) and the leave-one-out report (``_write_live_quality_report``,
  1669-1698), the flight recorder (``_diagnostics``, 887-913);
- **reset**: an object change clears the curves (``on_object_changed`` →
  ``clear_lightcurves``, 258-274, 1281-1293); a set change or a new solution
  drops the tracker (``_reset_tracker``, 1595-1602).

One deliberate difference with the Qt 0.5.0 code: the series FWHM is frozen
on the **first** measured frame. Qt read it before ``_diagnostics`` reset it on
a new object, so its first point had its own aperture and the series used the
second frame's FWHM (``notes/release_0_5_0.md`` S31, fixed in the release
branch; the owner's CSVs show it: ``fwhm`` 2.16 on the first row, 2.12 on the
194 others).

Threads: measurements run on one photometry thread (FIFO), never on the event
loop. Lock order: the service lock, then the hub's; the target set's lock is
never held while this one is taken. The newest records are kept for a new
client's snapshots and read without the service lock.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from argos.core.catalog.targets import (
    ROLE_CHECK,
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    comparison_chart_id,
)
from argos.core.config import observing_site
from argos.core.imaging.green import green_plane
from argos.core.imaging.metrics import detect_stars
from argos.core.photometry.airmass import (
    airmass_at,
    airmass_from_altitude,
    bjd_tdb,
    julian_date,
)
from argos.core.photometry.lightcurve import LcPoint, LightCurve
from argos.core.photometry.params import DEFAULT_FWHM, PhotometryParams, measure_frame
from argos.core.photometry.quality import comparison_quality_report, save_comparison_quality_report
from argos.core.photometry.tracking import ApertureTracker, TrackedWCS, select_tracking_anchors
from argos.core.photometry.uncertainty import apply_systematic_floor, estimate_systematic_floor
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: The Qt texts (``acquisition_engine.py:1612-1615``; S35 in the release branch).
NO_EPOCH_TEXT = "Photometry skipped: the frame has no exposure time (DATE-OBS/EXPTIME)."
FIELD_LOST_TEXT = (
    "Photometry skipped: no star of the set where the solution places it"
    " — the field moved since the solve, or clouds."
)

STATUS_TEXT = {
    "no_target": "No target star: choose one on the image or in the Variables list.",
    "not_solved": "Waiting for a field solution: the next one measures a point.",
    "waiting": "Waiting for the next field solution.",
    "no_epoch": "Skipped frame #{seq}: it has no exposure time (DATE-OBS/EXPTIME).",
    "no_comparison": "Skipped frame #{seq}: the target set has no comparison star.",
    "no_point": "Skipped frame #{seq}: no star of the set could be measured.",
    "field_lost": (
        "Skipped frame #{seq}: no star of the set where the solution places it"
        " (the field moved since the solve, or clouds)."
    ),
}


def bundled_iers_only() -> None:
    """Never let astropy download IERS or leap-second tables (release S37).

    Core's ``bjd_tdb`` lets astropy fetch ``finals2000A.all`` and the leap
    seconds on first use; offline it then refuses its bundled table and every
    BJD_TDB is lost (2.3 s per frame refused, ~18 s on a hanging network). The
    bundled tables give the same BJD to the bit. Same settings as the mount's
    coordinate conversion (``telescope.py``) and the release branch's fix.
    """
    from astropy.utils import iers

    iers.conf.auto_download = False
    iers.conf.auto_max_age = None


def write_csv_atomic(curve: LightCurve, path: Path) -> None:
    """``LightCurve.to_csv`` written beside the file and renamed over it (release S38).

    A reader (Review, a spreadsheet) or a crash mid-write sees the previous file
    or the new one, never a truncated one. The same bytes as ``to_csv``.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        curve.to_csv(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _num(value: Any) -> float | None:
    """A finite float, else ``None`` (strict JSON: NaN and ±inf are not numbers)."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def point_record(
    point: LcPoint,
    frame_seq: int | None,
    t: str | None,
    zero_point: float | None = None,
    zp_rms: float | None = None,
) -> dict[str, Any]:
    """An ``LcPoint`` on the wire (every field of ``lightcurve.py:38-62``, unrounded).

    Plus the star's ensemble zero point and its rms on that frame (``DiffResult``,
    the flight recorder's ``ensemble`` record): not in the CSV, the night's
    extinction and transparency trend for the plot's ensemble facet.
    """
    return {
        "jd_utc": _num(point.jd_utc),
        "t": t,
        "bjd_tdb": _num(point.bjd_tdb),
        "mag": _num(point.mag),
        "mag_err": _num(point.mag_err),
        "formal_mag_err": _num(point.formal_mag_err),
        "sigma_syst": _num(point.sigma_syst),
        "airmass": _num(point.airmass),
        "fwhm": _num(point.fwhm),
        "sky_adu": _num(point.sky_adu),
        "comps_used": int(point.comps_used or 0),
        "relative_flux": _num(point.relative_flux),
        "relative_flux_err": _num(point.relative_flux_err),
        "relative_comps_used": int(point.relative_comps_used or 0),
        "saturated": bool(point.saturated),
        "suspect": bool(point.suspect),
        "frame_seq": frame_seq,
        "zero_point": _num(zero_point),
        "zp_rms": _num(zp_rms),
    }


def curve_key(star) -> str:
    """Qt's curve key (``_emit_live_point``, 1740): the AUID, else the display name."""
    return star.auid or star.display_name


def safe_name(text: str) -> str:
    """``_photometry_csv_path`` / ``_diagnostics`` file-name rule (1531-1540, 897)."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_preview_csv(folder: Path, obj: str, tag: str, now: datetime, taken=()) -> Path:
    """``_new_preview_csv`` (S40): ``<folder>/<object>_<YYYYMMDDTHHMMSSZ>_<star>.csv``,
    a file not yet used; ``-2``, ``-3``… on the time for curves started in the
    same second. Review still finds ``<object>.json`` and the star."""
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    count = 1
    while True:
        mark = stamp if count == 1 else f"{stamp}-{count}"
        path = folder / f"{safe_name(f'{obj}_{mark}_{tag}')}.csv"
        if path not in taken and not path.exists():
            return path
        count += 1


class SessionDiagnostics:
    """The live flight recorder (``argos/core/session/diagnostics.py``, P11).

    A line-for-line port: the core module sits in the ``argos.core.session``
    package, whose ``__init__`` imports the Qt ``DeviceSession`` (the server
    never imports Qt, ``tests/server/test_no_qt.py``). One JSON object per line;
    a write error disables it with one warning; a no-op when disabled.
    """

    _NDIGITS = 4

    def __init__(self, path: Path | str, enabled: bool = True) -> None:
        self._path = Path(path)
        self._enabled = bool(enabled)
        self._fh = None

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def _clean(cls, value: Any) -> Any:
        if isinstance(value, float):
            return round(value, cls._NDIGITS)
        if isinstance(value, dict):
            return {k: cls._clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._clean(v) for v in value]
        return value

    def record(self, kind: str, frame: int | None = None, **fields: Any) -> None:
        if not self._enabled:
            return
        doc: dict[str, Any] = {
            "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": kind,
        }
        if frame is not None:
            doc["frame"] = int(frame)
        doc.update({k: self._clean(v) for k, v in fields.items() if v is not None})
        try:
            if self._fh is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = open(self._path, "a", encoding="utf-8")
            self._fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
            self._fh.flush()
        except OSError as exc:
            logger.warning("Diagnostics disabled (write failed): %s", exc)
            self._enabled = False
            self.close()

    def star(self, frame: int, star, phot, x: float, y: float) -> None:
        self.record(
            "star",
            frame=frame,
            auid=star.auid or None,
            name=star.display_name,
            role=star.role,
            x=float(x),
            y=float(y),
            flux_adu=phot.flux_adu if phot else None,
            sky_adu=phot.sky_adu if phot else None,
            peak_adu=phot.peak_adu if phot else None,
            snr=phot.snr if phot else None,
            inst_mag=phot.inst_mag if phot else None,
            inst_mag_err=phot.inst_mag_err if phot else None,
            saturated=bool(phot.saturated) if phot else None,
            suspect=bool(getattr(phot, "suspect", False)) or None if phot else None,
            measured=phot is not None,
        )

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


@dataclass
class MeasureRequest:
    """One frame to measure through one solution."""

    frame_seq: int
    raw: np.ndarray
    wcs: Any  # the reference solve (green px)
    epoch: datetime | None  # exposure midpoint (UTC)
    generation: int  # the field generation of the solution
    fwhm: float | None = None  # the frame's mean FWHM when known (green px)
    run_root: Path | None = None  # a sequence's run folder (wave 6)
    origin: str = "live"  # the frame's origin; "file" = Open FITS (another night)
    reset_tracker: bool = False  # a new solution: rebuild the tracker first
    egain: float | None = None  # an opened frame's own e-/ADU (frame_egain, S41)


class PhotometryService:
    """The live curves, their points and the leave-one-out report."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._lock = threading.RLock()
        self._curves: dict[str, LightCurve] = {}
        #: Per curve: the star's set key, its catalogue magnitudes and, per point,
        #: (frame seq, ISO midpoint).
        self._meta: dict[str, dict[str, Any]] = {}
        self._csv: dict[str, Path] = {}
        #: Outside a run, the CSV each curve was given when it started (S40).
        self._preview_csv: dict[str, Path] = {}
        self._revision = 0
        self._seq = 0
        self._frames = 0
        self._points = 0
        self._object: str | None = None
        #: P7: the series FWHM (green px), frozen on the first measured frame.
        self._phot_fwhm: float | None = None
        self._tracker: ApertureTracker | None = None
        self._tracker_anchors = 0  # anchor stars the tracker was built with
        self._diag: SessionDiagnostics | None = None
        self._diag_object: str | None = None
        self._diag_frame = 0
        self._last: dict[str, Any] | None = None
        self._outcome: tuple[str, str | None, int | None] | None = None  # state, reason, seq
        self._measured_keys: frozenset[str] = frozenset()  # the set the outcome is about
        self._quality_report: dict[str, Any] | None = None
        self._quality_revision = 0
        self._quality_record: dict[str, Any] = {
            "revision": 0,
            "frame_seq": None,
            "report": None,
        }
        self._status: dict[str, Any] = self._status_record()
        # the photometry thread
        self._queue: deque[MeasureRequest] = deque()
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._busy = 0

    # ------------------------------------------------------------------
    # Lifecycle and the photometry thread
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._queue.clear()
            self._cond.notify_all()
        with self._lock:
            if self._diag is not None:
                self._diag.close()
                self._diag = None

    def idle(self) -> bool:
        """Nothing queued or measuring (tests)."""
        with self._cond:
            return not self._queue and self._busy == 0

    def submit(self, request: MeasureRequest) -> None:
        with self._cond:
            if self._closed:
                return
            self._queue.append(request)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, name="argos-photometry", daemon=True
                )
                self._thread.start()
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                request = self._queue.popleft()
                self._busy += 1
            try:
                self.measure(request)
            except Exception:
                logger.exception("Photometry: frame %s failed", request.frame_seq)
            finally:
                with self._cond:
                    self._busy -= 1

    # ------------------------------------------------------------------
    # Hooks (field, targets, observation)
    # ------------------------------------------------------------------

    def on_solved(self, request: MeasureRequest) -> None:
        """A new solution was applied: ``measure_photometry_if_idle`` (1062-1065)."""
        with self._hub._lock:
            owner = self._hub._camera_state.owner
        if owner in ("sequence", "autofocus"):
            # A sequence measures every saved sub instead; a fresh solution is
            # still a new reference for its tracker (_on_reference_solved).
            with self._lock:
                self._tracker = None
            return
        self.submit(replace(request, reset_tracker=True))

    def measure_saved_frame(self, request: MeasureRequest) -> None:
        """A sequence's saved sub (``_on_seq_frame_saved``, 793-797; wave 6)."""
        self.submit(request)

    def on_targets_changed(self) -> None:
        """``_reset_tracker`` after a set change (1301, 1320, 1345, 1510).

        When the set's stars changed, the status waits for the next measurement:
        the last one was of the previous set (its points, its frame).
        """
        keys = frozenset(s.key() for s in self._hub.targets.snapshot().stars)
        with self._lock:
            self._tracker = None
            if keys != self._measured_keys:
                self._outcome = None
        self.refresh_status()

    def on_object_changed(self, object_name: str) -> None:
        """``on_object_changed`` (1281-1293): fresh curves for the new object."""
        with self._lock:
            if object_name != self._object:
                previous, self._object = self._object, object_name
                self._tracker = None
                if previous is not None or self._curves:
                    self._reset_locked("object_changed")
        self.refresh_status()

    def clear(self, reason: str = "cleared") -> None:
        """``clear_lightcurves`` (258-274); also a sequence start (650-692, wave 6)."""
        with self._lock:
            self._reset_locked(reason)
        self.refresh_status()

    def _reset_locked(self, reason: str) -> None:
        self._curves.clear()
        self._meta.clear()
        self._csv.clear()
        self._preview_csv.clear()
        self._frames = 0
        self._points = 0
        self._last = None
        self._outcome = None
        self._quality_report = None
        self._publish_reset(reason)
        self._publish_quality(None)

    def _publish_reset(self, reason: str) -> None:
        """Lock held: a new revision; clients re-read ``GET /api/photometry/live``."""
        self._revision += 1
        self._seq += 1
        reset = {
            "type": "photometry_reset",
            "seq": self._seq,
            "revision": self._revision,
            "reason": reason,
        }
        self._hub.bus.publish("photometry_reset", None, reset)

    # ------------------------------------------------------------------
    # Records
    # ------------------------------------------------------------------

    def series_fwhm(self) -> float | None:
        """The frozen series FWHM (green px), read without the lock."""
        return self._phot_fwhm

    def snapshots(self, seq: int) -> list[tuple[str, int, dict[str, Any]]]:
        """Hub lock held: what a new ``/ws/events`` client receives."""
        return [
            ("photometry", seq, {"type": "photometry", **self._status}),
            ("comparison_quality", seq, {"type": "comparison_quality", **self._quality_record}),
        ]

    def _status_record(self) -> dict[str, Any]:
        """Lock held (or init): the ``photometry`` status for the current state."""
        try:
            tset = self._hub.targets.target_set()
            has_target = bool(tset.by_role(ROLE_TARGET))
        except Exception:  # during start-up
            has_target = False
        solved = bool(getattr(self._hub, "field", None) and self._hub.field.solved)
        if not has_target:
            state, reason = "off", "no_target"
        elif not solved:
            state, reason = "waiting", "not_solved"
        elif self._outcome is None:
            state, reason = "waiting", None
        else:
            state, reason = self._outcome[0], self._outcome[1]
        if state == "off":
            message = STATUS_TEXT["no_target"]
        elif state == "waiting":
            message = STATUS_TEXT["not_solved" if reason else "waiting"]
        elif state == "measured":
            last = self._last or {}
            message = f"{last.get('points', 0)} point(s) on frame #{last.get('frame_seq')}"
        else:
            message = STATUS_TEXT[reason or "no_point"].format(seq=self._outcome[2])
        return {
            "state": state,
            "reason": reason,
            "message": message,
            "frames": self._frames,
            "points": self._points,
            "last": dict(self._last) if self._last is not None else None,
            "revision": self._revision,
        }

    def refresh_status(self) -> None:
        """Re-derive and publish the status when it changed (set, field, outcome)."""
        with self._lock:
            record = self._status_record()
            if record == self._status:
                return
            self._status = record
            with self._hub._lock:
                self._hub._publish("photometry", record)

    def _publish_quality(self, frame_seq: int | None) -> None:
        """Lock held: the ``comparison_quality`` snapshot."""
        self._quality_revision += 1
        record = {
            "revision": self._quality_revision,
            "frame_seq": frame_seq,
            "report": self._wire_report(self._quality_report),
        }
        self._quality_record = record
        with self._hub._lock:
            self._hub._publish("comparison_quality", record)

    def _wire_report(self, report: dict[str, Any] | None) -> dict[str, Any] | None:
        """Lock held: the core report plus each comparison's keys and newest point."""
        if report is None:
            return None
        entries = []
        for entry in report.get("comparison_stars", []):
            key = entry.get("auid") or entry.get("name")
            meta = self._meta.get(key, {})
            curve = self._curves.get(key)
            last = None
            if curve is not None and curve.points:
                p = curve.points[-1]
                last = {
                    "mag": _num(p.mag),
                    "mag_err": _num(p.mag_err),
                    "comps_used": int(p.comps_used or 0),
                    "jd_utc": _num(p.jd_utc),
                }
            entries.append({**entry, "key": key, "star_key": meta.get("star_key"), "last": last})
        return {**report, "comparison_stars": entries}

    def live_record(self) -> dict[str, Any]:
        """``GET /api/photometry/live`` (A54)."""
        cfg = self._hub.config.get
        tset = self._hub.targets.snapshot()
        geometry = self._hub.targets.geometry()
        with self._lock:
            set_keys = {curve_key(s): s.key() for s in tset.stars}
            curves = []
            for key, curve in self._curves.items():
                meta = self._meta.get(key, {})
                extra = meta.get("points", [])
                mags = dict(meta.get("mags") or {})
                floor = next(
                    (p.sigma_syst for p in reversed(curve.points) if p.sigma_syst is not None),
                    None,
                )
                curves.append(
                    {
                        "key": key,
                        "star_key": set_keys.get(key),  # null: no longer in the set
                        "role": curve.role,
                        "name": curve.name,
                        "auid": curve.auid or None,
                        "mags": mags,
                        "catalogue_v": _num(mags.get("V")),
                        "sigma_syst": _num(floor),
                        "csv": str(self._csv[key]) if key in self._csv else None,
                        "points": [
                            point_record(p, *(extra[i] if i < len(extra) else (None, None)))
                            for i, p in enumerate(curve.points)
                        ],
                    }
                )
            record = {
                "object_name": tset.object_name or "Unknown",
                "run_root": None,
                "sequence_running": False,
                "band": str(cfg("photometry.default_band", "TG") or "TG"),
                "obscode": str(cfg("observer.obscode", "") or ""),
                "chart_id": comparison_chart_id(tset.by_role(ROLE_COMPARISON)),
                "site_set": observing_site(self._hub.config) is not None,
                "geometry": {**geometry, "series_fwhm_px": self._phot_fwhm},
                "curves": curves,
                "quality": self._quality_record["report"],
                "status": dict(self._status),
                "revision": self._revision,
                "seq": self._seq,
            }
        return record

    # ------------------------------------------------------------------
    # The measurement (acquisition_engine.py:1604-1667)
    # ------------------------------------------------------------------

    def _cfg(self, key: str, default: Any) -> Any:
        value = self._hub.config.get(key, default)
        return default if value is None else value

    def _sessions_base(self) -> Path:
        return self._hub._sessions_root()

    def _diagnostics(self, tset: TargetSet, run_root: Path | None) -> SessionDiagnostics:
        """``_diagnostics`` (887-913). Lock held."""
        obj = tset.object_name or "Unknown"
        if self._diag is None or self._diag_object != obj:
            if self._diag is not None:
                self._diag.close()
            root = run_root / "diagnostics" if run_root is not None else self._sessions_base()
            if run_root is None:
                root = root / "targets"
            self._diag = SessionDiagnostics(
                root / f"{safe_name(obj) or 'Unknown'}_live_diagnostics.jsonl",
                enabled=bool(self._cfg("diagnostics.enabled", False)),
            )
            self._diag_object = obj
            self._diag_frame = 0
            self._phot_fwhm = None  # new object → re-sample the series FWHM (P7)
        return self._diag

    def _csv_path(self, tset: TargetSet, star, run_root: Path | None, key: str) -> Path:
        """``_photometry_csv_path``: a run's ``photometry/{role}_{object}_{star}.csv``;
        outside a run, the curve's own file, named after its start (S40)."""
        obj = tset.object_name or "Unknown"
        tag = star.auid or star.display_name
        if run_root is not None:
            safe = safe_name(f"{obj}_{tag}")
            role = getattr(star, "role", "target") or "target"
            return run_root / "photometry" / f"{role}_{safe or 'photometry'}.csv"
        path = self._preview_csv.get(key)
        if path is None:
            path = new_preview_csv(
                self._sessions_base() / "targets",
                obj,
                tag,
                _utcnow(),
                taken=set(self._preview_csv.values()),
            )
            self._preview_csv[key] = path
        return path

    def _frame_fwhm(self, request: MeasureRequest) -> float | None:
        """The measured frame's mean FWHM (green px): Qt's ``_last_fwhm``.

        ``detect_stars`` with ``imaging.star_radius_px``, as the frame metrics
        (and the Qt display pipeline, ``preview_processor.py:58-75``) measure it.
        """
        if request.fwhm is not None:
            return request.fwhm
        known = self._hub.targets.fwhm_for(request.frame_seq)
        if known is not None:
            return known[0]
        try:
            return detect_stars(request.raw, radius=self._hub._star_radius()).mean_fwhm
        except Exception:
            logger.warning("Photometry: FWHM of frame %s failed", request.frame_seq, exc_info=True)
            return None

    def _allow_rotation(self) -> bool:
        """An EQ mount has no field rotation (``_wcs_for_frame``, 1557-1560)."""
        with self._hub._lock:
            alignment = self._hub._mount_state.alignment
        return alignment not in ("eq", "eq_gem")

    def _wcs_for_frame(self, green, tset: TargetSet, params: PhotometryParams, wcs):
        """``_wcs_for_frame`` (1542-1567, with the release branch's S35). Lock held."""
        if not params.track_apertures:
            return wcs
        if self._tracker is None or not self._tracker_anchors:
            # Also when built with no star seen (clouds, or the field had moved):
            # try again on this frame rather than until the next solution (S35).
            self._tracker, self._tracker_anchors = self._build_live_tracker(
                green, wcs, tset, params
            )
        self._tracker.update(green, allow_rotation=self._allow_rotation())
        return TrackedWCS(wcs, self._tracker)

    def _field_lost(self, params: PhotometryParams) -> bool:
        """No star of the set where the tracked solution places it (S35). Lock held.

        The field moved further than the tracker's search radius since the
        solution, or clouds hide every anchor: apertures there measure blank sky.
        """
        return (
            params.track_apertures and self._tracker is not None and not self._tracker.anchors_used
        )

    @staticmethod
    def _build_live_tracker(green, wcs, tset: TargetSet, params: PhotometryParams):
        """``_build_live_tracker`` (1569-1582, with the release branch's S35).

        Returns the tracker and its anchor count. Without a comparison bright
        enough to steer, any star of the set seen where the solution places it
        (SNR ≥ 5); never the set's stars unseen, whose noise centroids passed
        for anchors when the field had moved since the solve.
        """
        candidates = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        anchors = select_tracking_anchors(green, wcs, candidates, params)
        if not anchors:
            anchors = select_tracking_anchors(green, wcs, list(tset.stars), params, min_snr=5.0)
        xy = [wcs.world_to_pixel_deg(s.ra_deg, s.dec_deg) for s in anchors]
        h, w = green.shape
        tracker = ApertureTracker(
            [(float(x), float(y)) for x, y in xy],
            frame_center=(w / 2.0, h / 2.0),
            search_r=max(8.0, 2.0 * params.aperture_px(None)),
        )
        return tracker, len(anchors)

    def measure(self, request: MeasureRequest) -> int:
        """``_measure_photometry`` (1604-1667) on one frame; returns the points kept."""
        tset = self._hub.targets.snapshot()
        with self._lock:
            if request.reset_tracker:
                self._tracker = None  # _on_reference_solved (1599-1602)
            if tset.object_name != self._object:
                # The observation changed under a queued frame: never mix objects.
                if self._object is not None or self._curves:
                    self._reset_locked("object_changed")
                self._object = tset.object_name
                self._tracker = None
        if not tset.by_role(ROLE_TARGET):
            self.refresh_status()
            return 0
        if request.epoch is None:
            # An opened FITS without DATE-OBS/EXPTIME: a point stamped "now"
            # would reach the curve, its CSV and the AAVSO export (S4).
            self._hub.log("warning", NO_EPOCH_TEXT, source="photometry", topic="photometry")
            with self._lock:
                self._outcome = ("skipped", "no_epoch", request.frame_seq)
            self.refresh_status()
            return 0
        frame_fwhm = self._frame_fwhm(request)
        # An opened frame's errors use its own e-/ADU (S41), else the live chain.
        egain = request.egain if request.egain is not None else self._hub.targets.egain()
        params = PhotometryParams.from_config(self._hub.config.get, egain=egain)
        green = green_plane(request.raw)
        jd = julian_date(request.epoch)
        t_iso = utc_iso(request.epoch)
        # The mount says where it points now: never the airmass of an opened
        # frame from another night (S34, fixed for 0.5.0).
        pointing = None if request.origin == "file" else self._hub._pointing()
        air = airmass_from_altitude(pointing.alt_deg) if pointing is not None else None
        # Never the 0/0 default: without a site, the airmass is the mount's
        # (or none) and there is no BJD_TDB (X2).
        lat, lon, elev = observing_site(self._hub.config) or (None, None, 0.0)
        with self._lock:
            # The recorder first: a new object resets the series FWHM, which is
            # then frozen on THIS frame (P7; S31: Qt froze it before the reset).
            diag = self._diagnostics(tset, request.run_root)
            if self._phot_fwhm is None and frame_fwhm:
                self._phot_fwhm = frame_fwhm
            fwhm = self._phot_fwhm or DEFAULT_FWHM
            frame_no = self._diag_frame
            self._diag_frame += 1
            tracked = self._wcs_for_frame(green, tset, params, request.wcs)
            if self._field_lost(params):
                # No point on blank sky (S35); the service lock, then the hub's.
                diag.record("event", frame=frame_no, what="frame_skipped", reason="field_lost")
                self._outcome = ("skipped", "field_lost", request.frame_seq)
                self._hub.log("warning", FIELD_LOST_TEXT, source="photometry", topic="photometry")
                self.refresh_status()
                return 0
            bundled_iers_only()  # BJD_TDB offline (S37)
            results = measure_frame(
                green,
                tracked,
                tset,
                params,
                fwhm=fwhm,
                on_star=lambda s, phot, x, y: diag.star(frame_no, s, phot, x, y),
            )
            tracker = self._tracker if params.track_apertures else None
            diag.record("frame", frame=frame_no, jd_utc=jd, airmass=air, fwhm=fwhm)
            kept = 0
            target_point: dict[str, Any] | None = None
            for res in results:
                if res.diff is not None:
                    diag.record(
                        "ensemble",
                        frame=frame_no,
                        target=res.star.auid or res.star.display_name,
                        zp=res.diff.zero_point,
                        zp_rms=res.diff.zp_rms,
                        comps_used=res.diff.comps_used,
                        note=res.diff.note or None,
                    )
                # A point is worth keeping when either product exists (S18).
                has_mag = res.diff is not None and res.diff.mag is not None
                has_ratio = res.relative is not None and res.relative.flux_ratio is not None
                if not (has_mag or has_ratio):
                    continue
                point = self._emit_live_point(
                    tset, res, jd, air, fwhm, (lat, lon, elev), request, t_iso
                )
                kept += 1
                if res.star.role == ROLE_TARGET and target_point is None:
                    target_point = {
                        "key": curve_key(res.star),
                        "mag": _num(point.mag),
                        "mag_err": _num(point.mag_err),
                        "bjd_tdb": _num(point.bjd_tdb),
                    }
            self._write_live_quality_report(tset, request)
            self._frames += 1
            self._points += kept
            r_ap = params.aperture_px(fwhm)
            self._last = {
                "frame_seq": request.frame_seq,
                "t": t_iso,
                "jd_utc": jd,
                "bjd_tdb": target_point["bjd_tdb"] if target_point is not None else None,
                "points": kept,
                "target": target_point,
                "aperture_px": r_ap,
                "fwhm_px": fwhm,
                "anchors": tracker.anchors_used if tracker is not None else None,
                "tracking": (
                    {
                        "rot_deg": tracker.transform.rotation_deg,
                        "dx": tracker.transform.tx,
                        "dy": tracker.transform.ty,
                        "residual_px": tracker.residual_px,
                    }
                    if tracker is not None
                    else None
                ),
            }
            self._measured_keys = frozenset(s.key() for s in tset.stars)
            if kept:
                self._outcome = ("measured", None, request.frame_seq)
            elif not tset.by_role(ROLE_COMPARISON):
                self._outcome = ("skipped", "no_comparison", request.frame_seq)
            else:
                self._outcome = ("skipped", "no_point", request.frame_seq)
        self.refresh_status()
        return kept

    def _emit_live_point(self, tset, res, jd, air, fwhm, site, request, t_iso) -> LcPoint:
        """``_emit_live_point`` (1700-1765): the point, its curve, its CSV, its event."""
        lat, lon, elev = site
        bjd = (
            bjd_tdb(jd, res.star.ra_deg, res.star.dec_deg, float(lat), float(lon), float(elev))
            if lat is not None and lon is not None
            else None
        )
        # The target's own altitude at the midpoint, not the mount's (1712-1719).
        if lat is not None and lon is not None:
            target_air = airmass_at(jd, res.star.ra_deg, res.star.dec_deg, float(lat), float(lon))
            if target_air is not None:
                air = target_air
        point = LcPoint(
            jd_utc=jd,
            mag=res.diff.mag if res.diff and res.diff.mag is not None else float("nan"),
            mag_err=res.diff.mag_err if res.diff and res.diff.mag_err is not None else float("nan"),
            bjd_tdb=bjd,
            airmass=air,
            fwhm=fwhm,
            sky_adu=res.phot.sky_adu if res.phot else None,
            comps_used=res.diff.comps_used if res.diff else 0,
            relative_comps_used=res.relative.comps_used if res.relative else 0,
            saturated=bool(res.phot and res.phot.saturated),
            suspect=bool(res.phot and res.phot.suspect),
            formal_mag_err=(
                res.diff.formal_mag_err or res.diff.mag_err
                if res.diff and res.diff.mag_err is not None
                else None
            ),
            relative_flux=res.relative.flux_ratio if res.relative else None,
            relative_flux_err=res.relative.flux_ratio_err if res.relative else None,
        )
        key = curve_key(res.star)
        lc = self._curves.get(key)
        if lc is None or lc.role != res.star.role:
            # A star whose role changed starts a new curve (S33, fixed for 0.5.0:
            # Qt appended a check's points to its leave-one-out comparison curve).
            if lc is not None:
                self._meta.pop(key, None)
                self._preview_csv.pop(key, None)  # the old curve keeps its own file (S40)
                self._publish_reset("role_changed")
            lc = LightCurve(
                auid=res.star.auid or "", name=res.star.display_name, role=res.star.role
            )
            self._curves[key] = lc
        meta = self._meta.setdefault(key, {"points": []})
        meta["star_key"] = res.star.key()
        meta["mags"] = dict(res.star.mags)
        lc.append(point)
        zp = res.diff.zero_point if res.diff is not None else None
        zp_rms = res.diff.zp_rms if res.diff is not None else None
        meta["points"].append((request.frame_seq, t_iso, zp, zp_rms))
        self._apply_systematic_floor(lc)
        path = self._csv_path(tset, res.star, request.run_root, key)
        self._csv[key] = path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_csv_atomic(lc, path)
        except OSError as exc:
            self._hub.log(
                "warning", f"photometry.csv: {exc}", source="photometry", topic="photometry"
            )
        self._seq += 1
        floor = point.sigma_syst
        event = {
            "type": "photometry_point",
            "seq": self._seq,
            "revision": self._revision,
            "frame_seq": request.frame_seq,
            "key": key,
            "star_key": res.star.key(),
            "role": lc.role,
            "name": lc.name,
            "auid": lc.auid or None,
            "index": len(lc.points) - 1,
            "point": point_record(point, request.frame_seq, t_iso, zp, zp_rms),
            # The run-level floor: every earlier error bar is hypot(formal, it),
            # recomputed by the client (S19), never resent as a column.
            "sigma_syst": _num(floor),
        }
        self._hub.bus.publish("photometry_point", None, event)
        return point

    def _apply_systematic_floor(self, curve: LightCurve) -> bool:
        """``_apply_systematic_floor`` (1767-1795)."""
        manual = self._cfg("photometry.systematic_floor_mag", None)
        floor = estimate_systematic_floor(
            [
                (point.jd_utc, point.mag, point.formal_mag_err or point.mag_err)
                for point in curve.points
                if math.isfinite(point.mag) and math.isfinite(point.formal_mag_err or point.mag_err)
            ],
            manual_floor=manual,
        )
        if floor is None:
            return False
        changed = False
        for point in curve.points:
            if not math.isfinite(point.mag):
                continue
            formal = point.formal_mag_err if point.formal_mag_err is not None else point.mag_err
            final = apply_systematic_floor(formal, floor)
            if point.mag_err != final or point.sigma_syst != floor.sigma_systematic:
                point.mag_err = final
                point.sigma_syst = floor.sigma_systematic
                changed = True
        return changed

    def _write_live_quality_report(self, tset: TargetSet, request: MeasureRequest) -> None:
        """``_write_live_quality_report`` (1669-1698): every frame (S17). Lock held."""
        report = comparison_quality_report(
            tset,
            self._curves,
            min_points=int(self._cfg("photometry.comparison_validation_min_points", 10)),
            max_scatter_mag=float(
                self._cfg("photometry.comparison_validation_max_scatter_mag", 0.10)
            ),
            max_formal_error_mag=float(
                self._cfg("photometry.comparison_validation_max_formal_error_mag", 0.10)
            ),
        )
        self._quality_report = report
        self._publish_quality(request.frame_seq)
        if request.run_root is None:
            return
        try:
            save_comparison_quality_report(request.run_root / "photometry_quality.json", report)
        except OSError as exc:
            self._hub.log(
                "warning",
                f"Save photometry quality: {exc}",
                source="photometry",
                topic="photometry",
            )


__all__ = ["MeasureRequest", "PhotometryService", "curve_key", "point_record"]
