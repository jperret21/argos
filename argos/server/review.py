"""Review: open a recorded session, its curves, a curve CSV, the live run (rows A67-A70).

The session reader is the fixed Qt reader itself, ``argos/core/session/review.py``
(0.5.0: S9 check role, S10 one-star CSV identity, S49 file names), loaded from its
file by :func:`core_review`: its package ``argos.core.session`` imports PyQt6, which
the server must not (``tests/server/test_no_qt.py``), while the module itself is
Qt-free (it says so). Loading the same file keeps every text and rule identical to
Qt without a copy that could drift.

What this module adds around it (``protocol.md`` "Review (wave 7)"):

- the open as a job with progress and cancel (``session_open``): ``load_session(
  read_temperature=False)`` then one header per frame (Qt read ``CCD-TEMP`` on the
  UI thread, U9), the curves, the flight recorder and the checks, atomically;
- the curves as columns, keyed ``<AUID or name>@<token>`` like the live store
  (S49), each point linked to its frame (Qt's ``nearest_light_frame``) with the
  frame's header airmass and the time difference to its header mid-exposure;
- the S35/S52 "check your old files" flags from the run's flight recorder, and
  the X3 site check on the frame headers (a wrong Settings site makes the CSV
  airmass wrong; the header ``AIRMASS``, from the mount, stays right);
- the CSV import of ``AnalyzeScreen._open_lightcurve`` (``analyze_page.py:
  726-772``) with a ``422`` instead of a silent return or a ``KeyError`` crash;
- the live run's curves in the same shape (D3, read-only).

Nothing is ever written into a session or a CSV.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import logging
import math
import statistics
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable

from argos.core.catalog.targets import (
    ROLE_CHECK,
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    comparison_chart_id,
)
from argos.core.imaging.session_log import SESSION_FILENAME
from argos.core.imaging.sky_geometry import angle_between_directions, horizontal_at
from argos.core.photometry.airmass import julian_date
from argos.core.photometry.lightcurve import LightCurve, read_curves_csv
from argos.server.capture import fits_exposure_mid
from argos.server.errors import ApiError
from argos.server.jobs import JobContext
from argos.server.photometry import filter_token
from argos.server.site_check import SITE_CHECK_TOLERANCE_DEG
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

_CORE_REVIEW_PATH = Path(__file__).resolve().parents[1] / "core" / "session" / "review.py"
_CORE_REVIEW_NAME = "argos.server._core_session_review"
_core_lock = threading.Lock()

#: The CSV columns, ``LcPoint``'s fields (``lightcurve.py:16-32``).
POINT_COLUMNS = (
    "jd_utc",
    "bjd_tdb",
    "mag",
    "mag_err",
    "formal_mag_err",
    "sigma_syst",
    "airmass",
    "fwhm",
    "sky_adu",
    "comps_used",
    "relative_flux",
    "relative_flux_err",
    "relative_comps_used",
    "saturated",
    "suspect",
)
_INT_COLUMNS = ("comps_used", "relative_comps_used")
_BOOL_COLUMNS = ("saturated", "suspect")
#: Columns added beside the CSV's (protocol.md "Curves").
EXTRA_COLUMNS = (
    "frame",
    "frame_dt_s",
    "header_airmass",
    "zero_point",
    "zp_rms",
    "snr",
    "flags",
)

#: A point farther than this from every logged light frame has no frame (s).
NO_FRAME_S = 60.0
#: The release's rule for S35 / S52 points (``notes/release_0_5_0.md``, "Check your old
#: files"): a target's SNR below this, or its zero point this far from the run's median.
LOW_SNR = 3.0
ZP_OUTLIER_MAG = 1.0
#: The release's S56 rule for old files: a sub on which fewer than this many comparison
#: or check stars reached SNR ``ANCHOR_SNR`` unsaturated was measured through a lock
#: nothing verified ("treat that sub's rows as suspect"; conservative, display only).
MIN_ANCHORS = 3
ANCHOR_SNR = 10.0
#: S71: the ensemble is faint when its comparisons' median SNR (each comparison's median
#: over the run, then the median of those) is below this; the zero point is then noisy.
FAINT_ENSEMBLE_SNR = 10.0
#: A flight-recorder frame matches a point within this (d): the recorder rounds
#: ``jd_utc`` to 4 decimals (``diagnostics.py:_NDIGITS``), 4.3 s at most.
_RECORDER_JD_TOL = 1.0e-4
#: Sessions kept open in memory.
_CACHE_SIZE = 8

_ROLE_PREFIXES = (
    ("target_", ROLE_TARGET),
    ("comparison_", ROLE_COMPARISON),
    ("check_", ROLE_CHECK),
)


def core_review() -> ModuleType:
    """``argos/core/session/review.py``, loaded without its PyQt6 package ``__init__``."""
    with _core_lock:
        module = sys.modules.get(_CORE_REVIEW_NAME)
        if module is not None:
            return module
        spec = importlib.util.spec_from_file_location(_CORE_REVIEW_NAME, _CORE_REVIEW_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - the file ships with argos
            raise ImportError(f"cannot load {_CORE_REVIEW_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_CORE_REVIEW_NAME] = module  # dataclasses resolve annotations through it
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_CORE_REVIEW_NAME, None)
            raise
        return module


def core_rules() -> ModuleType | None:
    """GUARD (S66, S67): the core reader once it has the old-file rules, else ``None``.

    ``apply_old_file_rules`` (release/0.5.0: each Argos frame's header AIRMASS unless
    its pointing is frozen, the flight recorder's no-detection points flagged suspect
    per target, ``sigma_syst`` recomputed, the comparisons' median SNR) reaches this
    tree with the merge; until then Review flags those points without changing them,
    as before.
    """
    core = core_review()
    # FrozenPointing, no_detection_flags: the S66/S67 reviews' X1 and batch rules;
    # RecorderFrame.flags, FAINT_ENSEMBLE_SNR: the owner's options (b) and S71's warning.
    names = ("apply_old_file_rules", "FrozenPointing", "no_detection_flags", "FAINT_ENSEMBLE_SNR")
    if not all(hasattr(core, name) for name in names):
        return None
    return core if hasattr(core.RecorderFrame, "flags") else None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _num(value: Any) -> float | None:
    """A finite float, else ``None`` (strict JSON)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _iso(when: datetime | None) -> str | None:
    return utc_iso(when) if when is not None else None


def _star_record(star) -> dict[str, Any]:
    return {
        "key": star.key(),
        "role": star.role,
        "name": star.name,
        "display_name": star.display_name,
        "auid": star.auid or None,
        "ra_hours": float(star.ra_deg) / 15.0,
        "dec_deg": float(star.dec_deg),
        "source": star.source,
        "mags": {str(k): _num(v) for k, v in dict(star.mags or {}).items()},
        "chart_id": star.chart_id,
    }


def targets_record(targets: TargetSet | None) -> dict[str, Any]:
    if targets is None:
        return {"object_name": None, "chart_id": None, "stars": []}
    return {
        "object_name": targets.object_name or None,
        "chart_id": comparison_chart_id(targets.by_role(ROLE_COMPARISON)),
        "stars": [_star_record(s) for s in targets.stars],
    }


def _role_prefix(stem: str) -> str | None:
    return next((role for prefix, role in _ROLE_PREFIXES if stem.startswith(prefix)), None)


# ---------------------------------------------------------------------------
# Frames: headers and the site check
# ---------------------------------------------------------------------------


@dataclass
class FrameHeader:
    date_obs: str | None = None
    mid: datetime | None = None
    jd_mid: float | None = None
    airmass: float | None = None
    altitude: float | None = None
    azimuth: float | None = None
    ra_hours: float | None = None
    dec_deg: float | None = None
    site_lat: float | None = None
    site_lon: float | None = None
    software: str | None = None
    width: int | None = None
    height: int | None = None
    bayer: str | None = None
    ccd_temp: float | None = None
    #: The core's ``FramePointing`` of this header (S66), ``None`` before the merge.
    pointing: Any = None

    def record(self) -> dict[str, Any]:
        return {
            "date_obs": self.date_obs,
            "mid_utc": _iso(self.mid),
            "jd_mid": self.jd_mid,
            "airmass": self.airmass,
            "altitude": self.altitude,
            "azimuth": self.azimuth,
            "software": self.software,
            "width": self.width,
            "height": self.height,
            "bayer": self.bayer,
        }


def read_frame_header(path: Path) -> FrameHeader | None:
    """The primary header fields Review uses, or ``None`` for an unreadable file."""
    from astropy.io import fits

    try:
        header = fits.getheader(path, 0)
    except Exception:  # a damaged optional header must not block review (review.py:339-346)
        return None
    mid = fits_exposure_mid(header)
    date_obs = header.get("DATE-OBS")
    bayer = header.get("BAYERPAT")
    software = header.get("SOFTWARE") or header.get("SWCREATE")
    rules = core_rules()
    return FrameHeader(
        date_obs=str(date_obs).strip() if date_obs else None,
        mid=mid,
        jd_mid=julian_date(mid) if mid is not None else None,
        airmass=_num(header.get("AIRMASS")),
        altitude=_num(header.get("ALTITUDE")),
        azimuth=_num(header.get("AZIMUTH")),
        ra_hours=_num(header.get("RA")),
        dec_deg=_num(header.get("DEC")),
        site_lat=_num(header.get("SITELAT")),
        site_lon=_num(header.get("SITELONG")),
        software=str(software).strip() if software else None,
        width=_int(header.get("NAXIS1")),
        height=_int(header.get("NAXIS2")),
        bayer=str(bayer).strip() or None if bayer else None,
        # review.py:_fits_temperature reads the same keyword the same way.
        ccd_temp=_num(header.get("CCD-TEMP")),
        pointing=rules.frame_pointing(header) if rules is not None else None,
    )


def _argos_header(header: FrameHeader) -> bool:
    """A frame ARGOS wrote: ``RA`` is then in hours (``fits_writer.py:460-470``)."""
    return bool(header.software and header.software.startswith("Argos"))


def header_site_check(headers: list[FrameHeader]) -> dict[str, Any]:
    """X3 on the files: the header site's direction against the mount's, per light frame.

    ``notes/release_0_5_0.md`` "Site set but wrong (X3)": the header ``ALTITUDE`` /
    ``AZIMUTH`` come from the mount, ``SITELAT`` / ``SITELONG`` from Settings; the
    direction of ``RA`` / ``DEC`` at ``DATE-OBS`` computed for that site more than 5°
    from the mount's means the site was wrong (the whole direction: altitudes alone
    can agree).
    """
    angles: list[float] = []
    for h in headers:
        if not _argos_header(h):
            continue
        values = (h.ra_hours, h.dec_deg, h.altitude, h.azimuth, h.site_lat, h.site_lon)
        if any(v is None for v in values) or h.date_obs is None:
            continue
        try:
            start = datetime.fromisoformat(h.date_obs.replace("Z", "+00:00"))
        except ValueError:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        jd = julian_date(start.astimezone(timezone.utc))
        alt, az = horizontal_at(jd, h.ra_hours, h.dec_deg, h.site_lat, h.site_lon)
        angles.append(angle_between_directions(alt, az, h.altitude, h.azimuth))
    if not angles:
        return {
            "state": "unknown",
            "frames": 0,
            "median_deg": None,
            "max_deg": None,
            "message": "The frame headers do not say where the mount pointed and from which site.",
        }
    median = statistics.median(angles)
    worst = max(angles)
    if median > SITE_CHECK_TOLERANCE_DEG:
        message = (
            "The site in Settings was not where the telescope was during this run (the "
            f"mount's direction is {median:.1f}° from the one computed for that site): the "
            "curves' airmass is wrong; the FITS header AIRMASS (from the mount) is right."
        )
        state = "mismatch"
    else:
        message = (
            f"The mount and the Settings site agree within {worst:.1f}° on {len(angles)} "
            f"frame{'s' if len(angles) != 1 else ''}."
        )
        state = "ok"
    return {
        "state": state,
        "frames": len(angles),
        "median_deg": round(median, 2),
        "max_deg": round(worst, 2),
        "message": message,
    }


# ---------------------------------------------------------------------------
# The run's flight recorder (argos/core/session/diagnostics.py)
# ---------------------------------------------------------------------------


@dataclass
class RecorderFrame:
    jd: float
    number: int
    stars: list[dict[str, Any]] = field(default_factory=list)
    ensemble: list[dict[str, Any]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def read_recorder(path: Path) -> list[RecorderFrame]:
    """The ``frame`` records of a flight recorder with their stars and ensembles.

    Records of one frame: its ``star`` records (written while measuring), then the
    ``frame`` record, then its ``ensemble`` records (``acquisition_engine.py:2141-
    2172``). The frame number restarts with a new series, so stars attach to the next
    ``frame`` record of their number and ensembles to the last one.
    """
    frames: list[RecorderFrame] = []
    pending: dict[int, list[dict[str, Any]]] = {}
    last: dict[int, RecorderFrame] = {}
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return frames
    with handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            kind = record.get("kind")
            number = _int(record.get("frame"))
            if number is None:
                continue
            if kind == "star":
                pending.setdefault(number, []).append(record)
            elif kind == "frame":
                jd = _num(record.get("jd_utc"))
                if jd is None:
                    continue
                rec = RecorderFrame(jd=jd, number=number, stars=pending.pop(number, []))
                frames.append(rec)
                last[number] = rec
            elif kind == "ensemble":
                rec = last.get(number)
                if rec is not None:
                    rec.ensemble.append(record)
    _flag_recorder(frames)
    return frames


def _flag_recorder(frames: list[RecorderFrame]) -> None:
    """S35 / S52 frame-wide flag: a target's zero point > 1 mag from its run median.

    The ensemble zero point does not depend on the target's own flux, so a jump of
    more than 1 mag means the frame was measured off the stars (blank sky after a
    field jump) or through thick cloud: every star's point of it is flagged. The
    per-star SNR rule is applied point by point (:func:`_link_points`).
    """
    target_names = set()
    for rec in frames:
        for star in rec.stars:
            if star.get("role") == ROLE_TARGET:
                target_names.add(str(star.get("auid") or star.get("name") or ""))
    zps: dict[str, list[float]] = {}
    for rec in frames:
        for ens in rec.ensemble:
            name = str(ens.get("target") or "")
            zp = _num(ens.get("zp"))
            if name in target_names and zp is not None:
                zps.setdefault(name, []).append(zp)
    medians = {name: statistics.median(values) for name, values in zps.items() if values}
    for rec in frames:
        outlier = any(
            str(ens.get("target") or "") in medians
            and _num(ens.get("zp")) is not None
            and abs(_num(ens.get("zp")) - medians[str(ens.get("target"))]) > ZP_OUTLIER_MAG
            for ens in rec.ensemble
        )
        rec.flags = ["zp_outlier"] if outlier else []
        if rec.stars and _anchor_count(rec) < MIN_ANCHORS:
            rec.flags.append("few_anchors")


def comparison_median_snr(frames: list[RecorderFrame]) -> float | None:
    """S71: the median over the comparisons of each one's median SNR in the recorder.

    None without a recorded comparison SNR. Saturated records are left out: they never
    enter the ensemble.
    """
    per_star: dict[str, list[float]] = {}
    for rec in frames:
        for star in rec.stars:
            snr = _num(star.get("snr"))
            if star.get("role") != ROLE_COMPARISON or snr is None or star.get("saturated"):
                continue
            per_star.setdefault(str(star.get("auid") or star.get("name") or ""), []).append(snr)
    medians = [statistics.median(values) for values in per_star.values() if values]
    return statistics.median(medians) if medians else None


def _anchor_count(rec: RecorderFrame) -> int:
    """S56's count: comparison or check records at SNR >= 10, not saturated."""
    return sum(
        1
        for star in rec.stars
        if star.get("role") in (ROLE_COMPARISON, ROLE_CHECK)
        and (_num(star.get("snr")) or 0.0) >= ANCHOR_SNR
        and not star.get("saturated")
    )


def recorder_counts(root: Path) -> dict[str, int]:
    """The session list's cheap readiness lines from the run's flight recorder.

    Frames the open's rules flag for the target (A69): ``flagged`` (target SNR below 3
    or a zero point more than 1 mag off) and ``unverified`` (S56: fewer than 3 anchors
    at SNR 10, and not already flagged), so R0's Issues agree with R1's badge.
    """
    flagged = unverified = 0
    for path in sorted((root / "diagnostics").glob("*_live_diagnostics.jsonl")):
        for rec in read_recorder(path):
            target_snr = [_num(st.get("snr")) for st in rec.stars if st.get("role") == ROLE_TARGET]
            low = any(v is not None and v < LOW_SNR for v in target_snr)
            if low or "zp_outlier" in rec.flags:
                flagged += 1
            elif "few_anchors" in rec.flags:
                unverified += 1
    return {"flagged": flagged, "unverified": unverified}


def first_light_site_check(root: Path, frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    """X3 on the first light frame's header only (the session list: one header read)."""
    for row in frames:
        if not str(row.get("image_type") or "").lower().startswith("light"):
            continue
        name = str(row.get("filename") or "")
        for candidate in (root / "lights" / name, root / name):
            if candidate.is_file():
                header = read_frame_header(candidate)
                return header_site_check([header]) if header is not None else None
        return None
    return None


def _recorder_index(frames: list[RecorderFrame]) -> Callable[[float], RecorderFrame | None]:
    ordered = sorted(frames, key=lambda r: r.jd)
    jds = [r.jd for r in ordered]

    def find(jd: float) -> RecorderFrame | None:
        import bisect

        i = bisect.bisect_left(jds, jd)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(ordered):
                d = abs(ordered[j].jd - jd)
                if d <= _RECORDER_JD_TOL and (best is None or d < best[0]):
                    best = (d, ordered[j])
        return best[1] if best else None

    return find


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------


@dataclass
class ReviewCurveData:
    """One curve of a source: the core object as loaded, and what Review adds."""

    key: str
    identity: str
    lc: LightCurve
    role_source: str
    filter: str
    filter_source: str | None
    csv: Path | None = None
    problem: str | None = None
    mags: dict[str, float] = field(default_factory=dict)
    frame: list[int | None] = field(default_factory=list)
    frame_dt_s: list[float | None] = field(default_factory=list)
    header_airmass: list[float | None] = field(default_factory=list)
    zero_point: list[float | None] = field(default_factory=list)
    zp_rms: list[float | None] = field(default_factory=list)
    snr: list[float | None] = field(default_factory=list)
    flags: list[list[str]] = field(default_factory=list)

    @property
    def exportable(self) -> bool:
        return self.problem is None

    def _extra(self, name: str, n: int) -> list[Any]:
        values = getattr(self, name)
        if len(values) == n:
            return values
        return [[] if name == "flags" else None] * n

    def record(self) -> dict[str, Any]:
        points = self.lc.points
        n = len(points)
        columns: dict[str, list[Any]] = {}
        for name in POINT_COLUMNS:
            values = [getattr(p, name) for p in points]
            if name in _BOOL_COLUMNS:
                columns[name] = [bool(v) for v in values]
            elif name in _INT_COLUMNS:
                columns[name] = [int(v or 0) for v in values]
            else:
                columns[name] = [_num(v) for v in values]
        for name in EXTRA_COLUMNS:
            columns[name] = list(self._extra(name, n))
        floor = next((p.sigma_syst for p in reversed(points) if p.sigma_syst is not None), None)
        mags = {str(k): _num(v) for k, v in self.mags.items()}
        return {
            "key": self.key,
            "identity": self.identity,
            "role": self.lc.role,
            "name": self.lc.name,
            "auid": self.lc.auid or None,
            "role_source": self.role_source,
            "filter": self.filter,
            "filter_source": self.filter_source,
            "csv": str(self.csv) if self.csv is not None else None,
            "file_name": self.csv.name if self.csv is not None else None,
            "mags": mags,
            "catalogue_v": mags.get("V"),
            "sigma_syst": _num(floor),
            "exportable": self.exportable,
            "problem": self.problem,
            "n": n,
            "columns": columns,
        }


@dataclass
class CurveSetData:
    """The curves of one source (``protocol.md`` CurveSet) as Python objects."""

    source: dict[str, Any]
    object_name: str | None
    root: Path | None
    targets: TargetSet | None
    curves: list[ReviewCurveData]
    problems: list[str] = field(default_factory=list)
    airmass_source: str = "csv"
    revision: str = ""
    #: What the ``airmass`` column holds: the CSV's, or each Argos frame's header
    #: AIRMASS (S66; points without one keep the CSV's, ``old_file_rules``).
    airmass_column: str = "csv"
    #: The core's ``OldFileRules`` (S66, S67) applied to these curves, or ``None``.
    rules: Any = None

    @property
    def filters(self) -> list[str]:
        return sorted({c.filter for c in self.curves if c.filter})

    @property
    def multi_filter(self) -> bool:
        return len(self.filters) > 1

    def by_key(self) -> dict[str, ReviewCurveData]:
        return {c.key: c for c in self.curves}

    def record(self) -> dict[str, Any]:
        return {
            "source": dict(self.source),
            "object": self.object_name,
            "root": str(self.root) if self.root is not None else None,
            "targets": targets_record(self.targets),
            "curves": [c.record() for c in self.curves],
            "filters": self.filters,
            "multi_filter": self.multi_filter,
            "problems": list(self.problems),
            "airmass_source": self.airmass_source,
            "airmass_column": self.airmass_column,
            "old_file_rules": rules_record(self.rules),
            "revision": self.revision,
        }


def rules_record(rules: Any) -> dict[str, Any] | None:
    """The core's ``OldFileRules`` on the wire (``protocol.md`` CurveSet), or ``None``."""
    if rules is None:
        return None
    return {
        "site_mismatch": bool(rules.site_mismatch),
        "airmass_from_header": int(rules.airmass_from_header),
        "airmass_computed": int(rules.airmass_computed),
        "frozen_lights": int(rules.frozen_lights),
        # S78 (GUARD: a core before it has neither): comparison and check points given
        # their own airmass, and the site it is computed for.
        "airmass_own_star": int(getattr(rules, "airmass_own_star", 0)),
        "star_airmass_site": getattr(rules, "star_airmass_site", None),
        "no_detection_frames": [
            {
                "file": f.file,
                "frame": f.number,
                "jd_utc": f.jd_utc,
                "low_snr": sorted(f.low_snr),
                "zp_outlier": f.zp_outlier,
            }
            for f in rules.no_detection_frames
        ],
        "comparison_median_snr": _num(rules.comparison_median_snr),
        "no_detection_points": int(rules.no_detection_points),
        "sigma_syst": {name: [before, after] for name, (before, after) in rules.floors.items()},
        "messages": list(rules.messages()),
    }


def apply_rules(curves: list["ReviewCurveData"], rules: Any) -> None:
    """After the core's rules: the ``no_detection`` display flag on the points they flagged."""
    if rules is None:
        return
    for c in curves:
        for i, p in enumerate(c.lc.points):
            if getattr(p, "no_detection", False) and i < len(c.flags):
                if "no_detection" not in c.flags[i]:
                    c.flags[i].append("no_detection")


def _wire_key(lc: LightCurve, token: str) -> str:
    """``curve_key`` (S49): the star's AUID, else its name, then the filter token."""
    return f"{lc.auid or lc.name or 'TARGET'}@{token}"


def _unique(keys: set[str], key: str) -> str:
    if key not in keys:
        return key
    n = 2
    while f"{key}#{n}" in keys:
        n += 1
    return f"{key}#{n}"


def identify_file(
    path: Path, targets: TargetSet
) -> tuple[list[tuple[str, LightCurve, str, str | None]], list[str]]:
    """``identify_curve_file`` (``review.py:215-256``) with each role's origin.

    Returns ``(identity, curve, role_source, problem)`` per curve and the core's
    problem lines. ``role_source``: ``column`` for a multi-curve export (role and
    star in its columns), else the one-star file's ``prefix`` (role from the file
    name), ``targets`` (role from the matched star) or ``default`` (neither: a
    target by default, never exportable). Raises ``OSError`` / ``ValueError`` /
    ``KeyError`` / ``csv.Error`` for an unreadable file.
    """
    core = core_review()
    raw = read_curves_csv(path)
    one_star = {f"target:{path.stem}", path.stem}
    _role, _identity, _name, _auid, matched = core._curve_identity(path, targets)
    prefixed = _role_prefix(path.stem) is not None
    one_star_source = "prefix" if prefixed else "targets" if matched else "default"
    # identify_curve_file changes the curves in place and returns the same objects.
    sources = {id(c): (one_star_source if k in one_star else "column") for k, c in raw.items()}
    identified, problems = core.identify_curve_file(path, raw, targets)
    problem = "\n".join(problems) or None
    out = []
    for identity, curve in identified.items():
        source = sources.get(id(curve), "column")
        out.append((identity, curve, source, problem if source != "column" else None))
    return out, problems


def _star_mags(targets: TargetSet | None, lc: LightCurve) -> dict[str, float]:
    if targets is None:
        return {}
    for star in targets.stars:
        if star.role != lc.role:
            continue
        if (lc.auid and star.auid == lc.auid) or (not lc.auid and star.display_name == lc.name):
            return dict(star.mags or {})
    return {}


# ---------------------------------------------------------------------------
# A session
# ---------------------------------------------------------------------------


@dataclass
class SessionData:
    """One opened session: the record and the curves (``protocol.md`` ReviewSession)."""

    root: Path
    stamp: tuple
    record: dict[str, Any]
    curves: CurveSetData


def _session_stamp(root: Path) -> tuple:
    photometry = root / "photometry"
    try:
        csvs = sorted(photometry.glob("*.csv"))
    except OSError:
        csvs = []
    quality = sorted(root.glob("photometry_quality*.json"))
    diag = sorted((root / "diagnostics").glob("*_live_diagnostics.jsonl"))
    return (
        _stamp(root / SESSION_FILENAME),
        _stamp(root / "targets.json"),
        _stamp(root / "observation.json"),
        _stamp(photometry),
        tuple((p.name, _stamp(p)) for p in csvs),
        tuple((p.name, _stamp(p)) for p in quality),
        tuple((p.name, _stamp(p)) for p in diag),
    )


def _revision(stamp: tuple) -> str:
    return hashlib.sha1(repr(stamp).encode("utf-8")).hexdigest()[:16]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _quality(root: Path) -> dict[str, Any]:
    """``photometry_quality.json`` and the per-filter files of S57."""
    default = _read_json(root / "photometry_quality.json")
    default = default if isinstance(default, dict) else None
    by_filter: dict[str, Any] = {}
    for path in sorted(root.glob("photometry_quality_*.json")):
        payload = _read_json(path)
        if isinstance(payload, dict):
            token = str(payload.get("filter") or path.stem[len("photometry_quality_") :])
            by_filter[token] = payload
    return {
        "default": default,
        "default_filter": (str(default["filter"]) if default and default.get("filter") else None),
        "by_filter": by_filter,
    }


class _Progress:
    """A job context, or nothing (a synchronous ``GET``)."""

    def __init__(self, ctx: JobContext | None) -> None:
        self._ctx = ctx

    def check(self) -> None:
        if self._ctx is not None:
            self._ctx.check()

    def __call__(self, done: float | None = None, **kw: Any) -> None:
        if self._ctx is not None:
            self._ctx.progress(done, **kw)


def open_session(root: Path, ctx: JobContext | None = None) -> SessionData:
    """Read a whole session (``session_open``); ``ApiError`` / ``JobCancelled`` only."""
    progress = _Progress(ctx)
    core = core_review()
    stamp = _session_stamp(root)
    progress(0, total=None, stage="session.json")
    try:
        review = core.load_session(root, read_temperature=False)
    except core.SessionReviewError as exc:
        raise ApiError(400, "session_invalid", str(exc)) from exc
    progress.check()

    # One recursive scan, first match per name (frame_path, review.py:84-86).
    found: dict[str, Path] = {}
    for candidate in root.rglob("*.fit*"):
        found.setdefault(candidate.name, candidate)
    frames = list(review.frames)
    headers: list[FrameHeader | None] = []
    progress(0, total=len(frames), stage="headers")
    for index, frame in enumerate(frames):
        progress.check()
        path = found.get(frame.filename)
        headers.append(read_frame_header(path) if path is not None else None)
        progress(index + 1)

    progress(len(frames), stage="curves")
    targets = TargetSet.load(root / "targets.json")
    light_tokens = {
        filter_token(f.filter_name) for f in review.light_frames if f.filter_name is not None
    }
    session_token = next(iter(light_tokens)) if len(light_tokens) == 1 else ""
    light_ids = {id(f) for f in review.light_frames}
    site = header_site_check(
        [h for f, h in zip(frames, headers) if h is not None and id(f) in light_ids]
    )
    airmass_source = "header" if site["state"] == "mismatch" else "csv"
    diag_files = sorted((root / "diagnostics").glob("*_live_diagnostics.jsonl"))
    recorder: list[RecorderFrame] = []
    for path in diag_files:
        recorder.extend(read_recorder(path))
    progress.check()

    curves, problems, unreadable = _session_curves(
        root, targets, review, frames, headers, recorder, session_token, progress
    )
    # S66, S67: the core's old-file rules on the curves, as load_session_curves applies
    # them (the light headers in load_session's order, read once above). GUARD.
    rules = None
    core_rules_module = core_rules()
    if core_rules_module is not None:
        pointings = [
            h.pointing if h is not None else None
            for f, h in zip(frames, headers)
            if id(f) in light_ids
        ]
        rules = core_rules_module.apply_old_file_rules([c.lc for c in curves], root, pointings)
        apply_rules(curves, rules)
        if rules.site_mismatch:
            site = dict(site, message=rules.messages()[0])
    warnings = list(review.warnings) + unreadable
    curve_set = CurveSetData(
        source={"kind": "session", "path": str(root)},
        object_name=review.object_name,
        root=root,
        targets=targets,
        curves=curves,
        problems=problems,
        airmass_source=airmass_source,
        revision=_revision(stamp),
        airmass_column="header" if rules is not None and rules.airmass_from_header else "csv",
        rules=rules,
    )

    # Readiness: the core's lines first (readiness_issues, review.py:76-82).
    issues: list[dict[str, Any]] = [
        {"code": "session_warning", "level": "warn", "message": text} for text in warnings
    ]
    if not review.light_frames:
        issues.append(
            {"code": "no_lights", "level": "error", "message": "No light frames were recorded."}
        )
    if not found:
        issues.append(
            {
                "code": "no_fits",
                "level": "error",
                "message": "No FITS frames found in this session folder.",
            }
        )
    if site["state"] == "mismatch":
        issues.append({"code": "site_mismatch", "level": "warn", "message": site["message"]})
    no_detection = {"low_snr", "zp_outlier", "no_detection"}
    flagged = sum(
        1
        for c in curves
        if c.lc.role == ROLE_TARGET
        for flags in c.flags
        if set(flags) & no_detection
    )
    unverified = sum(
        1
        for c in curves
        if c.lc.role == ROLE_TARGET
        for flags in c.flags
        if "few_anchors" in flags and not set(flags) & no_detection
    )
    if flagged:
        if rules is not None:
            what = (
                "flagged suspect and left out of the AAVSO export; sigma_syst is recomputed "
                "without them (S67)."
            )
        else:
            what = "flagged. Leave them out of any use."
        issues.append(
            {
                "code": "flagged_points",
                "level": "warn",
                "count": flagged,
                "message": (
                    f"{flagged} target point{'s' if flagged != 1 else ''} measured with an SNR "
                    "below 3 or on a frame whose zero point is more than 1 mag from the "
                    f"run's (the field moved, or cloud): {what}"
                ),
            }
        )
    if unverified:
        issues.append(
            {
                "code": "unverified_lock",
                "level": "warn",
                "count": unverified,
                "message": (
                    f"{unverified} target point{'s' if unverified != 1 else ''} measured "
                    "while fewer than 3 comparison or check stars reached SNR 10 (S56): "
                    "nothing verified the apertures were on their stars. The rule is "
                    "conservative: a re-run of the photometry (S58) verifies each such frame "
                    "with a plate solve and flags only those it cannot verify."
                ),
            }
        )
    # S71: the core's median (Qt's Review warns alike) once merged, else this reader's.
    ensemble_snr = (
        rules.comparison_median_snr if rules is not None else comparison_median_snr(recorder)
    )
    if ensemble_snr is not None and ensemble_snr < FAINT_ENSEMBLE_SNR:
        issues.append(
            {
                "code": "faint_comparisons",
                "level": "warn",
                "median_snr": round(ensemble_snr, 1),
                "message": (
                    f"The comparisons' median SNR is {ensemble_snr:.1f}, below 10 (S71): the "
                    "zero point rests on the brightest of them, and its error is in each "
                    "point's error. Brighter comparisons give a better curve."
                ),
            }
        )
    for text in problems:
        issues.append({"code": "unidentified_curve", "level": "warn", "message": text})
    levels = {i["level"] for i in issues}
    state = "blocked" if "error" in levels else "warnings" if "warn" in levels else "ready"

    frame_records = []
    for index, (frame, header) in enumerate(zip(frames, headers)):
        path = found.get(frame.filename)
        frame_records.append(
            {
                "index": index,
                "filename": frame.filename,
                "path": str(path) if path is not None else None,
                "image_type": frame.image_type,
                "filter_name": frame.filter_name,
                "filter": filter_token(frame.filter_name),
                "light": id(frame) in light_ids,
                "exposure_s": frame.exposure_s,
                "gain": frame.gain,
                "timestamp": _iso(frame.timestamp) if frame.timestamp else None,
                "hfd": _num(frame.hfd),
                "fwhm": _num(frame.fwhm),
                "star_count": frame.star_count,
                "sky_adu": _num(frame.sky_adu),
                "peak_adu": _num(frame.peak_adu),
                "eccentricity": _num(frame.eccentricity),
                "ccd_temp": header.ccd_temp if header is not None else None,
                "header": header.record() if header is not None else None,
            }
        )
    document = _read_json(root / SESSION_FILENAME)
    summary = document.get("summary") if isinstance(document, dict) else None
    record = {
        "source": {"kind": "session", "path": str(root)},
        "path": str(root),
        "folder": root.name,
        "object": review.object_name,
        "started_utc": review.started_utc,
        "software": review.software,
        "observer": review.observer,
        "summary": summary if isinstance(summary, dict) else None,
        "counts": {
            "frames": len(frames),
            "lights": len(review.light_frames),
            "missing_frames": sum(1 for f in frames if f.filename not in found),
            "filters": dict(review.filter_counts),
            "image_types": dict(review.image_type_counts),
        },
        "metadata": dict(review.metadata),
        "quality": _quality(root),
        "warnings": warnings,
        "readiness": {"state": state, "issues": issues},
        "frames": frame_records,
        "targets": targets_record(targets),
        "curves": [
            {
                "key": c.key,
                "role": c.lc.role,
                "name": c.lc.name,
                "filter": c.filter,
                "n": len(c.lc.points),
                "file_name": c.csv.name if c.csv is not None else None,
            }
            for c in curves
        ],
        "filters": curve_set.filters,
        "multi_filter": curve_set.multi_filter,
        "site_check": site,
        "airmass_source": airmass_source,
        "diagnostics": {
            "file": diag_files[0].name if diag_files else None,
            "frames": len(recorder),
        },
        "revision": curve_set.revision,
        "opened_utc": utc_iso(),
    }
    progress.check()
    progress(len(frames), stage="done")
    return SessionData(root=root, stamp=stamp, record=record, curves=curve_set)


def _session_curves(
    root: Path,
    targets: TargetSet,
    review: Any,
    frames: list[Any],
    headers: list[FrameHeader | None],
    recorder: list[RecorderFrame],
    session_token: str,
    progress: "_Progress | None" = None,
) -> tuple[list[ReviewCurveData], list[str], list[str]]:
    """``load_session_curves`` (``review.py:178-212``) keeping each curve's file and role origin.

    One change: a file missing a column (``KeyError`` in ``read_curves_csv``) is
    reported like an unreadable one instead of aborting the open (U9).
    """
    kept: dict[str, tuple[LightCurve, Path, str, str | None]] = {}
    problems: list[str] = []
    unreadable: list[str] = []
    for path in sorted((root / "photometry").glob("*.csv")):
        try:
            identified, file_problems = identify_file(path, targets)
        except (OSError, ValueError, KeyError, csv.Error):
            unreadable.append(f"Could not read preview curve: {path.name}")
            continue
        problems.extend(file_problems)
        for identity, curve, source, problem in identified:
            existing = kept.get(identity)
            # The same target may carry an AUID and an alias (review.py:200-206).
            if existing is None or len(curve.points) > len(existing[0].points):
                kept[identity] = (curve, path, source, problem)

    light_ids = {id(f) for f in review.light_frames}
    light = [(i, f) for i, f in enumerate(frames) if id(f) in light_ids and f.timestamp is not None]
    find_light = _light_finder(light)
    find_rec = _recorder_index(recorder)
    check = progress.check if progress is not None else (lambda: None)
    curves: list[ReviewCurveData] = []
    keys: set[str] = set()
    for identity, (lc, path, source, problem) in kept.items():
        token = lc.filter_name
        filter_source = "name" if token else None
        if not token and session_token:
            token, filter_source = session_token, "session"
        key = _unique(keys, _wire_key(lc, token))
        keys.add(key)
        data = ReviewCurveData(
            key=key,
            identity=identity,
            lc=lc,
            role_source=source,
            filter=token,
            filter_source=filter_source,
            csv=path,
            problem=problem,
            mags=_star_mags(targets, lc),
        )
        check()
        _link_points(data, frames, find_light, headers, find_rec, check)
        curves.append(data)
    return curves, problems, unreadable


def nearest_light_index(light: list[tuple[int, Any]], jd_utc: float) -> int | None:
    """``ReviewedSession.nearest_light_frame`` (``review.py:88-99``), as a frame index."""
    return _light_finder(light)(jd_utc)


def _light_finder(light: list[tuple[int, Any]]) -> Callable[[float], int | None]:
    """:func:`nearest_light_index` by bisection over the sorted light timestamps.

    The same answer as ``min()`` over the list (the first of equally near frames in
    list order), in O(log n) per point instead of O(n): a 6000-frame session's
    curves linked in milliseconds rather than half a minute (W7 technical review).
    """
    import bisect

    order = sorted((f.timestamp.timestamp(), pos, index) for pos, (index, f) in enumerate(light))
    stamps = [item[0] for item in order]

    def find(jd_utc: float) -> int | None:
        if not order:
            return None
        seconds = (float(jd_utc) - 2_440_587.5) * 86_400.0
        i = bisect.bisect_left(stamps, seconds)
        best: tuple[float, int, int] | None = None
        for j in (i - 1, i):
            if not 0 <= j < len(order):
                continue
            # The first frame (in list order) of this timestamp: sorted by position.
            first = order[bisect.bisect_left(stamps, stamps[j])]
            candidate = (abs(first[0] - seconds), first[1], first[2])
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        return best[2] if best is not None else None

    return find


def _link_points(
    data: ReviewCurveData,
    frames: list[Any],
    find_light: Callable[[float], int | None],
    headers: list[FrameHeader | None],
    find_rec: Callable[[float], RecorderFrame | None],
    check: Callable[[], None] = lambda: None,
) -> None:
    star_names = {data.lc.auid, data.lc.name} - {"", None}
    for n, point in enumerate(data.lc.points):
        if n % 500 == 499:
            check()
        jd = _num(point.jd_utc)
        index = find_light(jd) if jd is not None else None
        flags: list[str] = []
        dt = header_airmass = None
        if index is not None:
            seconds = (jd - 2_440_587.5) * 86_400.0
            if abs(frames[index].timestamp.timestamp() - seconds) > NO_FRAME_S:
                index = None
        if index is None:
            flags.append("no_frame")
        else:
            header = headers[index]
            if header is not None:
                header_airmass = header.airmass
                if header.jd_mid is not None:
                    dt = round((jd - header.jd_mid) * 86_400.0, 3)
        rec = find_rec(jd) if jd is not None else None
        zp = zp_rms = snr = None
        if rec is not None:
            flags.extend(rec.flags)
            for star in rec.stars:
                if star.get("role") == data.lc.role and star_names & {
                    star.get("auid"),
                    star.get("name"),
                }:
                    snr = _num(star.get("snr"))
                    break
            for ens in rec.ensemble:
                if ens.get("target") in star_names:
                    zp, zp_rms = _num(ens.get("zp")), _num(ens.get("zp_rms"))
                    break
            if snr is not None and snr < LOW_SNR:
                flags.append("low_snr")  # not a detection (S35 / S52 rule, per star)
        data.frame.append(index)
        data.frame_dt_s.append(dt)
        data.header_airmass.append(header_airmass)
        data.zero_point.append(zp)
        data.zp_rms.append(zp_rms)
        data.snr.append(snr)
        data.flags.append(flags)


# ---------------------------------------------------------------------------
# CSV import (A70)
# ---------------------------------------------------------------------------


def target_set_of_curve(csv_path: Path) -> TargetSet | None:
    """``_target_set_of_curve`` (``analyze_page.py:786-806``), Qt-free."""
    csv_dir = csv_path.parent
    for folder in (csv_dir, csv_dir.parent):
        if (folder / "targets.json").exists():
            return TargetSet.load(folder / "targets.json")
    if csv_dir.name == "targets":
        parts = csv_path.stem.split("_")
        for count in range(len(parts) - 1, 0, -1):
            candidate = csv_dir / ("_".join(parts[:count]) + ".json")
            if candidate.is_file():
                return TargetSet.load(candidate)
    return None


def _session_light_token(csv_path: Path) -> str:
    """The one filter token of the light frames of the session holding *csv_path*, or "".

    A CSV of a run sits in ``<session>/photometry/`` (or the run folder itself); a
    pre-0.5.0 name carries no filter, but a run through one filter could only be
    that band (S49). ``session.json`` alone is read (no FITS).
    """
    for folder in (csv_path.parent, csv_path.parent.parent):
        document = _read_json(folder / SESSION_FILENAME)
        if isinstance(document, dict) and isinstance(document.get("frames"), list):
            tokens = {
                filter_token(str(row.get("filter_name") or ""))
                for row in document["frames"]
                if isinstance(row, dict)
                and str(row.get("image_type") or "").lower().startswith("light")
            }
            return next(iter(tokens)) if len(tokens) == 1 else ""
    return ""


def import_csv(path: Path) -> CurveSetData:
    """``AnalyzeScreen._open_lightcurve`` (``analyze_page.py:726-772``) without the window."""
    name = path.name
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle), None)
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_csv", f"{name} is not UTF-8 text ({exc.reason})") from exc
    except csv.Error as exc:
        raise ApiError(422, "invalid_csv", f"{name} is not a CSV file ({exc})") from exc
    except OSError as exc:
        raise ApiError(404, "not_found", f"Could not read {name}: {exc.strerror or exc}") from exc
    if not header:
        raise ApiError(422, "invalid_csv", f"No valid photometry rows in {name}")
    columns = [c.strip() for c in header]
    for required in ("jd_utc", "mag", "mag_err"):
        if required not in columns:
            raise ApiError(422, "invalid_csv", f"{name} has no '{required}' column")
    targets = target_set_of_curve(path)
    try:
        identified, problems = identify_file(path, targets or TargetSet())
    except (UnicodeDecodeError, csv.Error, ValueError, KeyError) as exc:
        raise ApiError(422, "invalid_csv", f"{name} could not be read ({exc})") from exc
    if not any(curve.points for _identity, curve, _source, _problem in identified):
        raise ApiError(422, "invalid_csv", f"No valid photometry rows in {name}")
    # S66, S67: a run's own CSV gets the old-file rules of its session, as Analyze's
    # Open curve CSV applies them (apply_old_file_rules_to_file). GUARD.
    rules = None
    core_rules_module = core_rules()
    if core_rules_module is not None:
        rules = core_rules_module.apply_old_file_rules_to_file(
            path, {str(i): curve for i, (_k, curve, _s, _p) in enumerate(identified)}
        )
    curves: list[ReviewCurveData] = []
    keys: set[str] = set()
    session_token = _session_light_token(path)
    for identity, lc, source, problem in identified:
        token = lc.filter_name
        filter_source = "name" if token else None
        if not token and session_token:
            token, filter_source = session_token, "session"
        key = _unique(keys, _wire_key(lc, token))
        keys.add(key)
        data = ReviewCurveData(
            key=key,
            identity=identity,
            lc=lc,
            role_source=source,
            filter=token,
            filter_source=filter_source,
            csv=path,
            problem=problem,
            mags=_star_mags(targets, lc),
        )
        n = len(lc.points)
        data.frame = [None] * n
        data.frame_dt_s = [None] * n
        data.header_airmass = [None] * n
        data.zero_point = [None] * n
        data.zp_rms = [None] * n
        data.snr = [None] * n
        data.flags = [[] for _ in range(n)]
        curves.append(data)
    apply_rules(curves, rules)
    wrong_site = rules is not None and rules.site_mismatch
    header_column = rules is not None and rules.airmass_from_header > 0
    return CurveSetData(
        source={"kind": "import", "path": str(path)},
        object_name=(targets.object_name or None) if targets is not None else None,
        root=None,
        targets=targets,
        curves=curves,
        problems=list(problems),
        airmass_source="header" if wrong_site else "csv",
        revision=_revision((_stamp(path),)),
        airmass_column="header" if header_column else "csv",
        rules=rules,
    )


# ---------------------------------------------------------------------------
# The live run (A54's store), read-only
# ---------------------------------------------------------------------------


def live_curve_set(hub: "Hub") -> CurveSetData:
    """The live store as a CurveSet: copies, so a later point never changes them."""
    service = hub.photometry
    record = service.live_record()
    with service._lock:  # the store itself, not its wire form: the export input
        store = {key: copy.deepcopy(curve) for key, curve in service._curves.items()}
    targets = hub.targets.snapshot()
    curves: list[ReviewCurveData] = []
    for wire in record["curves"]:
        lc = store.get(wire["key"])
        if lc is None:
            continue
        lc.points = lc.points[: len(wire["points"])]
        points = wire["points"][: len(lc.points)]
        n = len(lc.points)
        data = ReviewCurveData(
            key=wire["key"],
            identity=wire.get("star_key") or wire["key"],
            lc=lc,
            role_source="live",
            filter=wire.get("filter") or "",
            filter_source="live",
            csv=Path(wire["csv"]) if wire.get("csv") else None,
            problem=None,
            mags=dict(wire.get("mags") or {}),
        )
        data.frame = [None] * n
        data.frame_dt_s = [None] * n
        data.header_airmass = [None] * n
        data.zero_point = [p.get("zero_point") for p in points]
        data.zp_rms = [p.get("zp_rms") for p in points]
        data.snr = [None] * n
        data.flags = [[] for _ in range(n)]
        curves.append(data)
    root = record.get("run_root")
    return CurveSetData(
        source={"kind": "live"},
        object_name=record.get("object_name"),
        root=Path(root) if root else None,
        targets=targets,
        curves=curves,
        revision=f"live:{record.get('revision')}:{record.get('seq')}",
    )


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


class ReviewService:
    """Sessions opened for review (cached), scans and imports (rows A67-A70)."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._lock = threading.Lock()
        self._cache: "OrderedDict[str, SessionData]" = OrderedDict()

    # -- paths -------------------------------------------------------------------

    def resolve_session(self, raw: str) -> Path:
        real, _root = self._hub.fs_roots.resolve(raw, what="session folder")
        if real.name == SESSION_FILENAME:
            real = real.parent
        if not real.exists():
            raise ApiError(404, "not_found", f"No folder {real}")
        if not real.is_dir():
            raise ApiError(400, "invalid_argument", f"{real.name} is not a session folder")
        return real

    def resolve_file(self, raw: str, suffixes: tuple[str, ...], what: str) -> Path:
        real, _root = self._hub.fs_roots.resolve(raw, what=what)
        if real.suffix.lower() not in suffixes:
            raise ApiError(
                400, "invalid_argument", f"{real.name} is not a {'/'.join(suffixes)} file"
            )
        if not real.is_file():
            raise ApiError(404, "not_found", f"No file {real}")
        return real

    # -- A67: the scan job ---------------------------------------------------------

    def start_scan(self) -> dict[str, Any]:
        root = self._hub._sessions_root()

        def run(ctx: JobContext) -> dict[str, Any]:
            if not root.is_dir():
                return {"root": str(root), "total": 0, "scanned_utc": utc_iso()}
            folders = sorted(
                (p for p in root.iterdir() if p.is_dir() and not p.is_symlink()),
                key=lambda p: p.name,
            )
            sessions = [p for p in folders if (p / SESSION_FILENAME).is_file()]
            ctx.progress(0, total=len(sessions), stage="scanning")
            index = self._hub.sessions
            for done, folder in enumerate(sessions, start=1):
                ctx.check()
                index.refresh(folder)
                ctx.progress(done, message=folder.name)
            return {"root": str(root), "total": len(sessions), "scanned_utc": utc_iso()}

        return self._hub.jobs.start("sessions_scan", run, resource="sessions", stage="scanning")

    # -- A68: open -----------------------------------------------------------------

    def _cached(self, root: Path) -> SessionData | None:
        with self._lock:
            data = self._cache.get(str(root))
        if data is None or data.stamp != _session_stamp(root):
            return None
        return data

    def _store(self, data: SessionData) -> None:
        with self._lock:
            self._cache[str(data.root)] = data
            self._cache.move_to_end(str(data.root))
            while len(self._cache) > _CACHE_SIZE:
                self._cache.popitem(last=False)

    def start_open(self, raw: str) -> dict[str, Any]:
        root = self.resolve_session(raw)

        def run(ctx: JobContext) -> dict[str, Any]:
            data = open_session(root, ctx)
            self._store(data)
            return self.open_summary(data)

        return self._hub.jobs.start("session_open", run, resource=str(root), stage="queued")

    @staticmethod
    def open_summary(data: SessionData) -> dict[str, Any]:
        """The ``session_open`` job's result: what identifies the open, not the record.

        A job's result travels in every ``job`` event and ``GET /api/jobs`` listing
        (4.7 MB for a 6000-frame session, W7 technical review): the record itself is
        read with ``GET /api/review/session`` from the cache this open filled.
        """
        record = data.record
        return {
            "path": record["path"],
            "folder": record["folder"],
            "object": record["object"],
            "revision": record["revision"],
            "counts": record["counts"],
            "readiness": record["readiness"],
        }

    def session(self, raw: str) -> SessionData:
        root = self.resolve_session(raw)
        data = self._cached(root)
        if data is None:
            data = open_session(root)
            self._store(data)
        return data

    def session_record(self, raw: str) -> dict[str, Any]:
        return self.session(raw).record

    def session_curves(self, raw: str) -> dict[str, Any]:
        return self.session(raw).curves.record()

    # -- A69 (live), A70 -------------------------------------------------------------

    def live_curves(self) -> dict[str, Any]:
        return live_curve_set(self._hub).record()

    def import_csv(self, raw: str) -> dict[str, Any]:
        path = self.resolve_file(raw, (".csv",), "curve CSV")
        return import_csv(path).record()

    # -- for the exports and the re-run (A76-A79) --------------------------------------

    def curve_set(self, source: dict[str, Any]) -> CurveSetData:
        """The curves of a :data:`Source` as Python objects (``protocol.md`` "Sources")."""
        kind = source.get("kind") if isinstance(source, dict) else None
        if kind == "session":
            return self.session(str(source.get("path") or "")).curves
        if kind == "import":
            path = self.resolve_file(str(source.get("path") or ""), (".csv",), "curve CSV")
            return import_csv(path)
        if kind == "live":
            return live_curve_set(self._hub)
        raise ApiError(400, "invalid_argument", "source.kind must be session, import or live")


__all__ = [
    "CurveSetData",
    "ReviewCurveData",
    "ReviewService",
    "core_review",
    "header_site_check",
    "import_csv",
    "live_curve_set",
    "open_session",
    "read_recorder",
]
