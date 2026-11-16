"""Read a finished Argos session for the offline Review workspace.

The reader is deliberately Qt-free: a session is useful after a crash, on a
different computer, or before any hardware is connected.  It consumes the
durable ``session.json`` truth and only reads FITS headers for telemetry that
is not part of that log (currently CCD temperature).
"""

from __future__ import annotations

import bisect
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from argos.core.imaging.session_log import SESSION_FILENAME
from argos.core.imaging.sky_geometry import (
    SITE_FIT_MAX_RMS_DEG,
    SiteFit,
    angle_between_directions,
    horizontal_at,
)
from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON, ROLE_TARGET, TargetSet
from argos.core.photometry.airmass import airmass_at, julian_date
from argos.core.photometry.lightcurve import LightCurve, read_curves_csv
from argos.core.photometry.uncertainty import apply_systematic_floor, estimate_systematic_floor

#: X3: the Settings site is wrong when the direction of the frame's RA/DEC at DATE-OBS,
#: seen from it, is more than this from the mount's ALTITUDE/AZIMUTH (device_session.py).
SITE_CHECK_TOLERANCE_DEG = 5.0
#: S78 (amended): without a fitted site, the Settings site gives a comparison or check
#: star its own airmass only when it reproduces the mount's pointing as closely as a
#: fitted site must (the median S66 offset of the run's lights, degrees); else the star
#: keeps the frame's header AIRMASS, the field centre's. The owner's short runs lie
#: 2.0-2.4° (XX Cyg) and 89° (RR Lyr 2026-09-25) off: a site 2° off moves a comparison's
#: airmass by 0.013, ten times the header's 0.0012 (notes S78).
STAR_SITE_MAX_OFFSET_DEG = SITE_FIT_MAX_RMS_DEG
#: S66: a point takes the header AIRMASS of the light whose mid-exposure is this close (s).
HEADER_AIRMASS_MATCH_S = 5.0
#: S67 (S35's rule on old files): a frame on which a target's SNR is below this, or its
#: ensemble zero point this far from the run's median, holds no detection.
NO_DETECTION_SNR = 3.0
ZP_OUTLIER_MAG = 1.0
#: The flight recorder rounds ``jd_utc`` to 4 decimals (diagnostics.py), 4.3 s at most.
RECORDER_JD_TOL = 1.0e-4
#: S66 (X1): a light whose RA, DEC, ALTITUDE, AZIMUTH and AIRMASS are all those of a
#: light at least this long (s) before it holds a frozen pointing, a lost mount's last
#: poll (0.3.0-0.4.2): no site check, and its header AIRMASS is stale.
FROZEN_POINTING_S = 60.0
#: S71: Review warns when the comparisons' median SNR in the flight recorder is below
#: this: the zero point then rests on the brightest of them.
FAINT_ENSEMBLE_SNR = 10.0


class SessionReviewError(ValueError):
    """The selected folder does not contain a readable Argos session."""


@dataclass(frozen=True)
class ReviewFrame:
    filename: str
    image_type: str
    filter_name: str
    exposure_s: float
    gain: int
    timestamp: datetime | None
    hfd: float | None = None
    fwhm: float | None = None
    star_count: int | None = None
    sky_adu: float | None = None
    peak_adu: float | None = None
    eccentricity: float | None = None
    ccd_temp: float | None = None


@dataclass
class ReviewedSession:
    root: Path
    object_name: str
    started_utc: str
    software: str
    observer: str
    frames: list[ReviewFrame] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    comparison_quality: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def light_frames(self) -> list[ReviewFrame]:
        return [frame for frame in self.frames if frame.image_type.lower().startswith("light")]

    @property
    def filter_counts(self) -> Counter[str]:
        return Counter(frame.filter_name or "—" for frame in self.frames)

    @property
    def image_type_counts(self) -> Counter[str]:
        return Counter(frame.image_type or "Unknown" for frame in self.frames)

    def metric_samples(self) -> list[tuple[float, ReviewFrame]]:
        """Return light-frame elapsed seconds and frames with a valid timestamp."""
        dated = [(frame.timestamp, frame) for frame in self.light_frames if frame.timestamp]
        if not dated:
            return []
        first = min(timestamp for timestamp, _frame in dated)
        return [((timestamp - first).total_seconds(), frame) for timestamp, frame in dated]

    def readiness_issues(self) -> list[str]:
        issues = list(self.warnings)
        if not self.light_frames:
            issues.append("No light frames were recorded.")
        if not any(self.root.rglob("*.fit*")):
            issues.append("No FITS frames found in this session folder.")
        return issues

    def frame_path(self, frame: ReviewFrame) -> Path | None:
        """Find the stored FITS for a logged frame without modifying the session."""
        return next(self.root.rglob(frame.filename), None)

    def nearest_light_frame(self, jd_utc: float) -> ReviewFrame | None:
        """Match a preview-photometry JD to its closest recorded light frame."""
        if not self.light_frames:
            return None
        seconds_since_unix = (float(jd_utc) - 2_440_587.5) * 86_400.0
        candidates = [frame for frame in self.light_frames if frame.timestamp is not None]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda frame: abs(frame.timestamp.timestamp() - seconds_since_unix),
        )


def load_session(path: Path | str, *, read_temperature: bool = True) -> ReviewedSession:
    """Load a session folder or its ``session.json`` file.

    Bad individual frame rows are skipped and reported so a partial night can
    still be reviewed.  This function never writes or alters the session.
    """
    selected = Path(path).expanduser()
    root = selected.parent if selected.name == SESSION_FILENAME else selected
    session_path = root / SESSION_FILENAME
    if not session_path.is_file():
        raise SessionReviewError(f"No {SESSION_FILENAME} in {root}")
    try:
        document = json.loads(session_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SessionReviewError(f"Could not read {SESSION_FILENAME}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("frames"), list):
        raise SessionReviewError(f"{SESSION_FILENAME} has no frame list")

    review = ReviewedSession(
        root=root,
        object_name=str(document.get("object") or "Unknown"),
        started_utc=str(document.get("started_utc") or ""),
        software=str(document.get("software") or "Argos"),
        observer=str(document.get("observer") or ""),
    )
    observation = root / "observation.json"
    if observation.is_file():
        try:
            payload = json.loads(observation.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                review.metadata = payload
        except (OSError, ValueError):
            review.warnings.append("Could not read observation.json.")

    quality_path = root / "photometry_quality.json"
    if quality_path.is_file():
        try:
            payload = json.loads(quality_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                review.comparison_quality = payload
            else:
                review.warnings.append("Ignored an invalid photometry_quality.json.")
        except (OSError, ValueError):
            review.warnings.append("Could not read photometry_quality.json.")

    frame_paths = {candidate.name: candidate for candidate in root.rglob("*.fit*")}
    for row in document["frames"]:
        if not isinstance(row, dict):
            review.warnings.append("Ignored an invalid frame row in session.json.")
            continue
        try:
            filename = str(row["filename"])
            frame = ReviewFrame(
                filename=filename,
                image_type=str(row.get("image_type") or "Unknown"),
                filter_name=str(row.get("filter_name") or ""),
                exposure_s=float(row.get("exposure_s") or 0.0),
                gain=int(row.get("gain") or 0),
                timestamp=_parse_timestamp(row.get("timestamp")),
                hfd=_optional_float(row.get("hfd")),
                fwhm=_optional_float(row.get("fwhm")),
                star_count=_optional_int(row.get("star_count")),
                sky_adu=_optional_float(row.get("sky_adu")),
                peak_adu=_optional_float(row.get("peak_adu")),
                eccentricity=_optional_float(row.get("eccentricity")),
                ccd_temp=_fits_temperature(frame_paths.get(filename)) if read_temperature else None,
            )
        except (TypeError, ValueError):
            review.warnings.append("Ignored a malformed frame row in session.json.")
            continue
        if filename not in frame_paths:
            review.warnings.append(f"Missing FITS frame: {filename}")
        review.frames.append(frame)
    return review


def load_session_curves(review: ReviewedSession) -> dict[str, LightCurve]:
    """Load all per-star curves with their scientific roles and identities.

    Per-star CSVs deliberately contain only measurement columns so they remain
    simple inputs for external tools.  Their filename and the session's
    ``targets.json`` therefore provide the missing role/identity at Review
    time.  Older Review incorrectly treated every such file as a target,
    making calibration stars appear in the source-light-curve panel.

    The release notes' old-file rules are applied to the curves read (never to
    the files): each point takes its frame's header ``AIRMASS``, from the mount
    (S66), and the points on which the flight recorder shows no detection are
    flagged suspect, the run's ``sigma_syst`` recomputed without them (S67). A
    wrong Settings site (X3), those points and faint comparisons (S71) are added
    to ``review.warnings``.
    """
    curves = _read_session_curves(review)
    rules = apply_old_file_rules(curves.values(), review.root, light_pointings(review))
    review.warnings.extend(rules.messages())
    return curves


def _read_session_curves(review: ReviewedSession) -> dict[str, LightCurve]:
    """The run's curve CSVs, identified (``load_session_curves`` before S66, S67)."""
    curves: dict[str, LightCurve] = {}
    targets = TargetSet.load(review.root / "targets.json")
    for path in sorted((review.root / "photometry").glob("*.csv")):
        try:
            identified, _problems = identify_curve_file(path, read_curves_csv(path), targets)
            for curves_key, curve in identified.items():
                existing = curves.get(curves_key)
                # The same physical target may have an AUID and a catalogue
                # alias recorded in one session. Keep the more complete curve
                # rather than plotting a duplicate science source.
                if existing is None or len(curve.points) > len(existing.points):
                    curves[curves_key] = curve
        except (OSError, ValueError):
            review.warnings.append(f"Could not read preview curve: {path.name}")
    return curves


def identify_curve_file(
    path: Path | str, curves: dict[str, LightCurve], targets: TargetSet
) -> tuple[dict[str, LightCurve], list[str]]:
    """Give the curves read from one CSV their scientific role and star.

    A per-star CSV carries only measurement columns, so ``read_curves_csv``
    returns it as one "target" curve named after the file. The role comes
    from the engine's file-name prefix (``{role}_{object}_{tag}.csv``), the
    star from ``targets.json`` (AUID suffix first, then name); an unprefixed
    file (legacy, batch re-run) takes the role of the star it matches. A
    multi-curve export already carries role and identity and is kept as is.

    Returns the curves keyed by identity, and one problem line per one-star
    file whose role or star could not be recovered — such a curve must not
    be exported to AAVSO (its NAME would be the file name).
    """
    path = Path(path)
    role, identity, name, auid, matched = _curve_identity(path, targets)
    token = _curve_filter(path.stem, targets, auid or name) if matched else ""
    if token:
        identity = f"{identity}@{token}"  # one curve per (star, filter): S49
    identified: dict[str, LightCurve] = {}
    problems: list[str] = []
    for key, curve in curves.items():
        if key == f"target:{path.stem}" or key == path.stem:
            if role is None:
                problems.append(
                    f"{path.name}: role unknown — no role prefix in the file name and "
                    "no star of targets.json matches it."
                )
            elif not matched:
                problems.append(f"{path.name}: star unknown — no star of targets.json matches it.")
            curve.role = role or ROLE_TARGET
            curve.name = name
            curve.auid = auid
            curve.filter_name = token
            key = identity
        elif not curve.name:
            curve.name = name
        identified[str(key)] = curve
    return identified, problems


#: File-name prefixes of the engine's per-star CSVs (``{role}_{object}_{tag}``).
_ROLE_PREFIXES = (
    ("target_", ROLE_TARGET),
    ("comparison_", ROLE_COMPARISON),
    ("check_", ROLE_CHECK),
)


def _curve_identity(path: Path, targets: TargetSet) -> tuple[str | None, str, str, str, bool]:
    """Recover ``(role, key, label, auid, matched)`` for a per-star curve CSV.

    ``role`` is None for an unprefixed file that matches no star; ``matched``
    says whether a star of ``targets`` was found.
    """
    stem = path.stem
    role = next((role for prefix, role in _ROLE_PREFIXES if stem.startswith(prefix)), None)
    if role is not None:
        candidates = [star for star in targets.stars if star.role == role]
    else:  # any role; on a name tie, the science target first
        order = {ROLE_TARGET: 0, ROLE_CHECK: 1, ROLE_COMPARISON: 2}
        candidates = sorted(targets.stars, key=lambda star: order.get(star.role, 3))
    # AUID suffix is unambiguous and takes precedence over display names.
    star = next((item for item in candidates if item.auid and stem.endswith(item.auid)), None)
    if star is None:
        star = next(
            (
                item
                for item in candidates
                if item.name and stem.endswith(_safe_component(item.name))
            ),
            None,
        )
    if star is None:
        return role, f"{role or ROLE_TARGET}:{stem}", stem, "", False
    role = role or star.role

    # Targets are deduplicated by sky position, not AUID: a catalogue alias
    # and the user-selected name can legitimately describe the same star.
    if role == ROLE_TARGET:
        identity = f"{role}:pos:{star.ra_deg:.4f},{star.dec_deg:.4f}"
    else:
        identity = star.auid or f"{role}:pos:{star.ra_deg:.5f},{star.dec_deg:.5f}"
    return role, identity, star.display_name, star.auid or "", True


def _curve_filter(stem: str, targets: TargetSet, star_tag: str) -> str:
    """The filter token of a run's ``{role}_{object}_{filter}_{star}`` CSV (S49), or "".

    "" for a file written before S49 (``{role}_{object}_{star}``) and for any
    name that does not have that shape (preview curves, other software).
    """
    prefix = next((prefix for prefix, _role in _ROLE_PREFIXES if stem.startswith(prefix)), None)
    obj = _safe_component(targets.object_name or "")
    tag = _safe_component(star_tag)
    if prefix is None or not obj or not tag or not stem.endswith(f"_{tag}"):
        return ""
    middle = stem[len(prefix) : -(len(tag) + 1)]
    if not middle.startswith(f"{obj}_"):
        return ""
    token = middle[len(obj) + 1 :]
    return token if token and token == token.lower() else ""


def _safe_component(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


# ---------------------------------------------------------------------------
# The release notes' old-file rules on a run's curves (S66, S67)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FramePointing:
    """What a frame's header says about where the mount pointed, and from which site.

    ``ALTITUDE``, ``AZIMUTH`` and ``AIRMASS`` come from the mount, which knows where
    it is; ``SITELAT``/``SITELONG`` from the Settings site (X3). ``RA`` is in hours in
    a frame Argos wrote, so only those frames are checked (``argos``).
    """

    jd_start: float | None = None
    jd_mid: float | None = None
    airmass: float | None = None
    altitude: float | None = None
    azimuth: float | None = None
    ra_hours: float | None = None
    dec_deg: float | None = None
    site_lat: float | None = None
    site_lon: float | None = None
    argos: bool = False


def frame_pointing(header) -> FramePointing:
    """A :class:`FramePointing` from a FITS header (any mapping with ``get``).

    The mid-exposure is ``DATE-OBS`` + ``EXPTIME``/2, the live point's own epoch
    (S36); an ``AIRMASS`` below 1 or not finite is no airmass.
    """
    start = _fits_start(header.get("DATE-OBS"))
    exposure = _finite(header.get("EXPTIME", header.get("EXPOSURE")))
    mid = None
    if start is not None and exposure is not None and exposure >= 0:
        mid = julian_date(start + timedelta(seconds=exposure / 2.0))
    airmass = _finite(header.get("AIRMASS"))
    software = str(header.get("SOFTWARE") or header.get("SWCREATE") or "").strip()
    return FramePointing(
        jd_start=julian_date(start) if start is not None else None,
        jd_mid=mid,
        airmass=airmass if airmass is not None and airmass >= 1.0 else None,
        altitude=_finite(header.get("ALTITUDE")),
        azimuth=_finite(header.get("AZIMUTH")),
        ra_hours=_finite(header.get("RA")),
        dec_deg=_finite(header.get("DEC")),
        site_lat=_finite(header.get("SITELAT")),
        site_lon=_finite(header.get("SITELONG")),
        argos=software.startswith("Argos"),
    )


def read_frame_pointing(path: Path | str) -> FramePointing | None:
    """:func:`frame_pointing` of a FITS file's primary header, or ``None`` if unreadable."""
    try:
        from astropy.io import fits

        return frame_pointing(fits.getheader(path, 0))
    except Exception:  # a damaged frame must not block review or a re-run
        return None


def site_offset_deg(
    pointing: FramePointing | None, lat: float | None = None, lon: float | None = None
) -> float | None:
    """X3 on one frame: degrees between the mount's direction and the site's.

    The direction of the frame's ``RA``/``DEC`` at ``DATE-OBS`` seen from the site
    (the header's ``SITELAT``/``SITELONG`` unless ``lat``/``lon`` are given, the
    Settings site of a batch re-run) against the header ``ALTITUDE``/``AZIMUTH``:
    the whole direction, as altitudes alone can agree. ``None`` when the header
    cannot say (not an Argos frame, or a value missing).
    """
    if pointing is None or not pointing.argos:
        return None
    lat = pointing.site_lat if lat is None else lat
    lon = pointing.site_lon if lon is None else lon
    values = (
        pointing.jd_start,
        pointing.ra_hours,
        pointing.dec_deg,
        pointing.altitude,
        pointing.azimuth,
        lat,
        lon,
    )
    if any(value is None for value in values):
        return None
    alt, az = horizontal_at(
        pointing.jd_start, pointing.ra_hours, pointing.dec_deg, float(lat), float(lon)
    )
    return angle_between_directions(alt, az, pointing.altitude, pointing.azimuth)


class FrozenPointing:
    """S66 (X1): tells a light whose header pointing is a lost mount's last poll.

    Fed the lights in time order (:meth:`frozen`): a light whose ``RA``, ``DEC``,
    ``ALTITUDE``, ``AZIMUTH`` and ``AIRMASS`` are all those of the first light of an
    unbroken run of identical values, :data:`FROZEN_POINTING_S` or more after it, is
    frozen. A tracking mount's altitude and azimuth change every poll; within a minute
    of the freeze the values are off by 0.25° at most. Such a light's ``AIRMASS`` is
    stale (its airmass is computed instead), and it tells nothing about the site (its
    direction drifts from the computed one at about 0.2° per minute: a right site
    would be judged wrong after half an hour).
    """

    def __init__(self) -> None:
        self._key: tuple | None = None
        self._since: float | None = None

    def frozen(self, pointing: FramePointing | None) -> bool:
        key = _pointing_key(pointing)
        if key is None or pointing.jd_start is None:
            self._key = self._since = None
            return False
        if key != self._key:
            self._key, self._since = key, pointing.jd_start
            return False
        return (pointing.jd_start - self._since) * 86_400.0 >= FROZEN_POINTING_S


def _pointing_key(pointing: FramePointing | None) -> tuple | None:
    if pointing is None:
        return None
    key = (pointing.ra_hours, pointing.dec_deg, pointing.altitude, pointing.azimuth)
    return None if any(value is None for value in key) else (*key, pointing.airmass)


def frozen_pointings(pointings: list[FramePointing | None]) -> list[bool]:
    """S66 (X1): per light of ``pointings``, whether its header pointing is frozen
    (:class:`FrozenPointing`, the lights taken in ``DATE-OBS`` order)."""
    flags = [False] * len(pointings)
    order = sorted(
        (p.jd_start, index)
        for index, p in enumerate(pointings)
        if p is not None and p.jd_start is not None
    )
    detector = FrozenPointing()
    for _jd, index in order:
        flags[index] = detector.frozen(pointings[index])
    return flags


def site_mismatch(pointings: Iterable[FramePointing | None]) -> tuple[bool, float | None]:
    """X3 over a run's lights: whether the median offset is over 5°, and that median
    (Review's warning; the airmass no longer depends on it, S66).

    A light whose pointing is frozen (X1, :func:`frozen_pointings`) is not checked:
    from half an hour after the freeze it looks like a wrong site."""
    pointings = list(pointings)
    frozen = frozen_pointings(pointings)
    offsets = [
        offset
        for offset, stale in zip(map(site_offset_deg, pointings), frozen)
        if offset is not None and not stale
    ]
    if not offsets:
        return False, None
    median = statistics.median(offsets)
    return median > SITE_CHECK_TOLERANCE_DEG, median


def settings_site_reproduces(
    pointings: Iterable[FramePointing | None], lat: float | None = None, lon: float | None = None
) -> bool:
    """S78 (amended): whether the Settings site reproduces the mount's pointing well enough
    to give a comparison or check star its own airmass: the median offset (X3,
    :func:`site_offset_deg`) of the run's lights whose pointing is not frozen is within
    :data:`STAR_SITE_MAX_OFFSET_DEG`. The site is ``lat``/``lon`` (a batch re-run's
    Settings site), else each light's ``SITELAT``/``SITELONG``. False when no light can
    tell (no Argos light with a pointing): the stars then keep their header AIRMASS."""
    pointings = list(pointings)
    frozen = frozen_pointings(pointings)
    offsets = [
        offset
        for offset, stale in zip((site_offset_deg(p, lat, lon) for p in pointings), frozen)
        if offset is not None and not stale
    ]
    return bool(offsets) and statistics.median(offsets) <= STAR_SITE_MAX_OFFSET_DEG


def light_pointings(review: ReviewedSession) -> list[FramePointing | None]:
    """The header pointing of each light frame of ``review`` (``None``: not found)."""
    found: dict[str, Path] = {}
    for candidate in review.root.rglob("*.fit*"):
        found.setdefault(candidate.name, candidate)  # frame_path's first match
    return [
        read_frame_pointing(found[frame.filename]) if frame.filename in found else None
        for frame in review.light_frames
    ]


@dataclass(frozen=True)
class RecorderFrame:
    """One ``frame`` record of a run's flight recorder, judged by S35's rule (S67).

    ``low_snr``: the targets measured below SNR 3 (no detection of that target; their
    ``auid``, else name); ``zp_outlier``: a target's ensemble zero point is more than
    1 mag from its median over the run, which does not depend on a target's own flux
    (the field moved, or cloud): every star's point of the frame is affected.
    """

    file: str
    number: int
    jd_utc: float
    low_snr: frozenset[str] = frozenset()
    zp_outlier: bool = False

    @property
    def no_detection(self) -> bool:
        """Either rule holds on this frame (for one target at least)."""
        return bool(self.low_snr) or self.zp_outlier

    def flags(self, role: str, identity: str) -> bool:
        """S67: whether a point of the star ``identity`` (``auid``, else name) in
        ``role`` is a no-detection point here: every star on a zero-point outlier, a
        target on its own SNR (a faint target does not flag a second, bright one)."""
        return self.zp_outlier or (role == ROLE_TARGET and identity in self.low_snr)


def read_flight_recorder(root: Path | str) -> list[RecorderFrame]:
    """The frames of a run's ``diagnostics/<object>_live_diagnostics.jsonl``
    (:func:`_read_recorder`)."""
    return _read_recorder(root)[0]


def _read_recorder(root: Path | str) -> tuple[list[RecorderFrame], float | None]:
    """The recorder's frames judged by S35's rule, and the comparisons' median SNR.

    A frame's ``star`` records precede its ``frame`` record and its ``ensemble``
    records follow it (``acquisition_engine.py``); the frame number restarts with
    a new series, so stars attach to the next ``frame`` record of their number and
    ensembles to the last one. The zero point's median is taken per target over
    every file of the run. The SNR (S71) is the median over the comparisons of each
    one's median SNR, saturated records left out (they never enter the ensemble);
    None without one.
    """
    frames: list[tuple[str, int, float, list[dict], list[dict]]] = []
    for path in sorted((Path(root) / "diagnostics").glob("*_live_diagnostics.jsonl")):
        pending: dict[int, list[dict]] = {}
        last: dict[int, list[dict]] = {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            try:
                record = json.loads(line)
                number = int(record["frame"])
            except (ValueError, TypeError, KeyError):
                continue
            kind = record.get("kind")
            if kind == "star":
                pending.setdefault(number, []).append(record)
            elif kind == "frame":
                jd = _finite(record.get("jd_utc"))
                if jd is None:
                    continue
                ensembles: list[dict] = []
                frames.append((path.name, number, jd, pending.pop(number, []), ensembles))
                last[number] = ensembles
            elif kind == "ensemble" and number in last:
                last[number].append(record)
    targets = {
        str(star.get("auid") or star.get("name") or "")
        for _f, _n, _jd, stars, _e in frames
        for star in stars
        if star.get("role") == ROLE_TARGET
    }
    judged = no_detection_flags(
        (
            [
                (_star_identity(star), _finite(star.get("snr")))
                for star in stars
                if star.get("role") == ROLE_TARGET
            ],
            [
                (str(ens.get("target")), _finite(ens.get("zp")))
                for ens in ensembles
                if str(ens.get("target") or "") in targets
            ],
        )
        for *_head, stars, ensembles in frames
    )
    recorded = [
        RecorderFrame(name, number, jd, low, outlier)
        for (name, number, jd, _stars, _ensembles), (low, outlier) in zip(frames, judged)
    ]
    per_comparison: dict[str, list[float]] = {}
    for *_head, stars, _ensembles in frames:
        for star in stars:
            snr = _finite(star.get("snr"))
            if (
                star.get("role") == ROLE_COMPARISON
                and snr is not None
                and not star.get("saturated")
            ):
                per_comparison.setdefault(_star_identity(star), []).append(snr)
    medians = [statistics.median(values) for values in per_comparison.values()]
    return recorded, statistics.median(medians) if medians else None


def _star_identity(record: dict) -> str:
    """A recorder star's identity: its ``auid``, else its name (a curve's, alike)."""
    return str(record.get("auid") or record.get("name") or "")


def no_detection_flags(
    frames: Iterable[tuple[Iterable[tuple[str, float | None]], Iterable[tuple[str, float | None]]]],
) -> list[tuple[frozenset[str], bool]]:
    """S35's rule on a run's frames (S67): ``(low_snr, zp_outlier)`` per frame.

    Each frame is given as its targets' SNRs (``(target, snr)``) and its targets'
    ensemble zero points (``(target, zp)``). ``low_snr``: the targets below
    :data:`NO_DETECTION_SNR`, each flagging its own points only; ``zp_outlier``: a
    target's zero point more than :data:`ZP_OUTLIER_MAG` from that target's median
    over the run's frames, which flags every point of the frame. A missing value
    tells nothing. The flight recorder's frames (:func:`read_flight_recorder`) and a
    batch re-run's are judged alike.
    """
    frames = [(list(snrs), list(zps)) for snrs, zps in frames]
    zero_points: dict[str, list[float]] = {}
    for _snrs, zps in frames:
        for target, zp in zps:
            if zp is not None and math.isfinite(zp):
                zero_points.setdefault(target, []).append(zp)
    medians = {name: statistics.median(values) for name, values in zero_points.items()}
    out = []
    for snrs, zps in frames:
        low = frozenset(
            target for target, snr in snrs if snr is not None and snr < NO_DETECTION_SNR
        )
        outlier = any(
            zp is not None
            and math.isfinite(zp)
            and target in medians
            and abs(zp - medians[target]) > ZP_OUTLIER_MAG
            for target, zp in zps
        )
        out.append((low, outlier))
    return out


@dataclass
class OldFileRules:
    """What :func:`apply_old_file_rules` changed in a run's curves."""

    #: S66: the run's site check (X3, a warning), the points given their frame's header
    #: AIRMASS, and those that keep the airmass computed for the Settings site (no
    #: Argos light within 5 s, no AIRMASS, or a frozen pointing).
    site_mismatch: bool = False
    site_offset_deg: float | None = None
    airmass_from_header: int = 0
    airmass_computed: int = 0
    #: S66 (X1): the lights whose header pointing is frozen (no site check, no AIRMASS).
    frozen_lights: int = 0
    #: S78: the points of comparison and check stars given their own airmass, and the
    #: site it is computed for: "fitted" (to the lights' ALTITUDE/AZIMUTH), "settings"
    #: (the lights' SITELAT/SITELONG: no fit, and that site reproduces the mount's
    #: pointing, :func:`settings_site_reproduces`), or None (the header AIRMASS).
    airmass_own_star: int = 0
    star_airmass_site: str | None = None
    #: S71: the comparisons' median SNR in the flight recorder (None without one).
    comparison_median_snr: float | None = None
    #: S67: the recorder frames without a detection, and the points flagged on them.
    no_detection_frames: list[RecorderFrame] = field(default_factory=list)
    no_detection_points: int = 0
    #: S67: per curve (name), sigma_syst as read and as recomputed without those points.
    floors: dict[str, tuple[float, float]] = field(default_factory=dict)

    def messages(self) -> list[str]:
        """One line per rule that changed something, for Review's warnings."""
        out = []
        if self.site_mismatch:
            text = (
                "The site in Settings was not where the telescope was during this run (the "
                f"mount's direction is {self.site_offset_deg:.1f}° from the one computed for "
                "that site): fix it in Settings › Observer & site. The airmass shown and "
                "exported is each frame's FITS header AIRMASS, from the mount (S66)."
            )
            if self.star_airmass_site == "fitted":
                text += (
                    " Comparison and check stars take their own, computed for the site"
                    " fitted to the mount's pointing (S78)."
                )
            if self.airmass_computed:
                text += (
                    f" {self.airmass_computed} point(s) without one (no frame within 5 s, or"
                    " a lost mount's frozen pointing, X1) keep the airmass computed for the"
                    " Settings site, which is wrong."
                )
            out.append(text)
        if self.no_detection_points:
            n = len(self.no_detection_frames)
            out.append(
                f"{n} frame(s) of this run show no detection in its flight recorder (target "
                "SNR below 3, or a zero point more than 1 mag from the run's): their "
                f"{self.no_detection_points} point(s) are flagged suspect, left out of the "
                "AAVSO export, and sigma_syst is recomputed without them (S67)."
            )
        snr = self.comparison_median_snr
        if snr is not None and snr < FAINT_ENSEMBLE_SNR:
            out.append(
                f"The comparisons' median SNR is {snr:.1f}, below 10 (S71): the zero point "
                "rests on the brightest of them, and its error is in each point's error. "
                "Brighter comparisons give a better curve."
            )
        return out


def apply_old_file_rules(
    curves: Iterable[LightCurve], root: Path | str, pointings: list[FramePointing | None]
) -> OldFileRules:
    """The release notes' old-file rules on the curves of a run's ``photometry/`` CSVs.

    S66: every target point's airmass becomes the header ``AIRMASS`` (the field
    centre's) of the Argos light whose mid-exposure is nearest, within 5 s (the
    mount's, within 0.0004 of astropy); a point without one (no light, no ``AIRMASS``,
    or a light whose pointing is frozen, X1) keeps the airmass the run computed for the
    Settings site. S78: a comparison or check star's airmass is its own, computed for
    the site fitted to the lights' pointing (:func:`fitted_site`); without a fit, for
    the Settings site they recorded only when it reproduces the mount's pointing
    (:func:`settings_site_reproduces`), else the header ``AIRMASS`` as the target's (a
    wrong Settings site gave RR Lyr 2026-09-25's comparisons 4.0-4.9 for 1.03). The
    site check (X3) is reported, not needed. S67 (S35): every point that the run's flight recorder
    shows without a detection is flagged ``suspect`` (``no_detection``,
    :meth:`RecorderFrame.flags`: every star's on a zero-point outlier, a target's own
    below SNR 3), and a curve's ``sigma_syst`` (with each ``mag_err``) is recomputed
    without those points when it is the automatic estimate of the file's own points.
    S71: the comparisons' median SNR. The curves are changed in place; the files are
    never written.
    """
    curves = list(curves)
    rules = OldFileRules()
    rules.site_mismatch, rules.site_offset_deg = site_mismatch(pointings)
    rules.frozen_lights = sum(frozen_pointings(pointings))
    find = _header_airmass_finder(pointings)
    # S78: a comparison or check star off the field centre takes its own airmass, for
    # the site fitted to the mount's pointing, else the run's Settings site when it
    # reproduces that pointing; else the header AIRMASS, as the target.
    site = fitted_site(pointings)
    rules.star_airmass_site = "fitted" if site is not None else None
    if site is None and settings_site_reproduces(pointings):
        site = header_settings_site(pointings)
        rules.star_airmass_site = "settings" if site is not None else None
    stars = TargetSet.load(Path(root) / "targets.json") if site is not None else None
    for lc in curves:
        star = _curve_star(lc, stars) if stars is not None and lc.role != ROLE_TARGET else None
        for point in lc.points:
            if star is not None and math.isfinite(point.jd_utc):
                own = airmass_at(point.jd_utc, star.ra_deg, star.dec_deg, site[0], site[1])
                if own is not None:
                    point.airmass = own
                    rules.airmass_own_star += 1
                    continue
            airmass = find(point.jd_utc)
            if airmass is None:
                rules.airmass_computed += 1
            else:
                point.airmass = airmass
                rules.airmass_from_header += 1
    recorder, rules.comparison_median_snr = _read_recorder(root)
    rules.no_detection_frames = [frame for frame in recorder if frame.no_detection]
    if not rules.no_detection_frames:
        return rules
    find_frame = _recorder_finder(recorder)
    for lc in curves:
        marked = 0
        identity = lc.auid or lc.name
        for point in lc.points:
            frame = find_frame(point.jd_utc)
            if frame is not None and frame.flags(lc.role, identity):
                point.suspect = True
                point.no_detection = True
                marked += 1
        if marked:
            rules.no_detection_points += marked
            floor = _floor_without_no_detection(lc)
            if floor is not None:
                rules.floors[lc.name or lc.auid] = floor
    return rules


def fitted_site(pointings: list[FramePointing | None]) -> tuple[float, float] | None:
    """S78: the site (latitude, longitude) fitted to the run's Argos lights' header
    ``RA``/``DEC``/``ALTITUDE``/``AZIMUTH`` at ``DATE-OBS`` (the mount's own site), or
    None: fewer than 3 such lights over 10 minutes, or no site reproduces them within
    0.1° (:class:`SiteFit`). A light whose pointing is frozen (X1) is left out."""
    frozen = frozen_pointings(pointings)
    fit = SiteFit()
    for pointing, stale in zip(pointings, frozen):
        if pointing is None or not pointing.argos or stale or pointing.jd_start is None:
            continue
        values = (pointing.ra_hours, pointing.dec_deg, pointing.altitude, pointing.azimuth)
        if any(value is None for value in values):
            continue
        fit.add(pointing.jd_start, *values)
    return fit.site()


def header_settings_site(pointings: list[FramePointing | None]) -> tuple[float, float] | None:
    """S78: the run's Settings site as its Argos lights recorded it (``SITELAT``,
    ``SITELONG``; the median, a site changed in a run being rare), or None."""
    sites = [
        (p.site_lat, p.site_lon)
        for p in pointings
        if p is not None and p.argos and p.site_lat is not None and p.site_lon is not None
    ]
    if not sites:
        return None
    return statistics.median(s[0] for s in sites), statistics.median(s[1] for s in sites)


def _curve_star(lc: LightCurve, targets: TargetSet):
    """S78: the star of the run's set a curve measures (by AUID, else by name), or None."""
    for star in targets.stars:
        if lc.auid and star.auid == lc.auid:
            return star
    if lc.auid:
        return None
    for star in targets.stars:
        if lc.name and lc.name in (star.name, star.display_name):
            return star
    return None


def _header_airmass_finder(pointings: list[FramePointing | None]):
    """The header AIRMASS of the light whose mid-exposure is nearest a JD, within 5 s
    (none for a frame Argos did not write, or whose pointing is frozen, X1: its
    AIRMASS is the last poll's)."""
    frozen = frozen_pointings(pointings)
    dated = sorted(
        (p.jd_mid, index, p.airmass if p.argos and not frozen[index] else None)
        for index, p in enumerate(pointings)
        if p is not None and p.jd_mid is not None
    )
    jds = [item[0] for item in dated]
    tolerance = HEADER_AIRMASS_MATCH_S / 86_400.0

    def find(jd: float) -> float | None:
        if not dated or not math.isfinite(jd):
            return None
        i = bisect.bisect_left(jds, jd)
        best = min(
            (dated[j] for j in (i - 1, i) if 0 <= j < len(dated)),
            key=lambda item: (abs(item[0] - jd), item[1]),
        )
        return best[2] if abs(best[0] - jd) <= tolerance else None

    return find


def _recorder_finder(frames: list[RecorderFrame]):
    """The recorder frame nearest a JD, within the recorder's rounding (else ``None``)."""
    ordered = sorted(frames, key=lambda frame: frame.jd_utc)
    jds = [frame.jd_utc for frame in ordered]

    def find(jd: float) -> RecorderFrame | None:
        if not ordered or not math.isfinite(jd):
            return None
        i = bisect.bisect_left(jds, jd)
        near = [ordered[j] for j in (i - 1, i) if 0 <= j < len(ordered)]
        best = min(near, key=lambda frame: abs(frame.jd_utc - jd))
        return best if abs(best.jd_utc - jd) <= RECORDER_JD_TOL else None

    return find


def _floor_without_no_detection(lc: LightCurve) -> tuple[float, float] | None:
    """S67: re-estimate ``lc``'s run-level floor without its no-detection points.

    Only when the file's floor is the automatic estimate of all its points (the live
    path's ``_apply_systematic_floor``, reproduced here): a manual floor, or one from
    another rule, does not depend on these points and is kept, as it is when fewer
    than ten points remain. Returns ``(before, after)``, or ``None`` if kept.
    """

    def triples(points):
        return [
            (p.jd_utc, p.mag, p.formal_mag_err or p.mag_err)
            for p in points
            if math.isfinite(p.mag) and math.isfinite(p.formal_mag_err or p.mag_err)
        ]

    written = {p.sigma_syst for p in lc.points if math.isfinite(p.mag)}
    if len(written) != 1 or None in written:
        return None
    before = written.pop()
    current = estimate_systematic_floor(triples(lc.points))
    if current is None or not math.isclose(current.sigma_systematic, before, rel_tol=1e-9):
        return None
    floor = estimate_systematic_floor(triples(p for p in lc.points if not p.no_detection))
    if floor is None:
        return None
    for point in lc.points:
        if not math.isfinite(point.mag):
            continue
        formal = point.formal_mag_err if point.formal_mag_err is not None else point.mag_err
        point.mag_err = apply_systematic_floor(formal, floor)
        point.sigma_syst = floor.sigma_systematic
    return before, floor.sigma_systematic


def session_of_curve_file(path: Path | str) -> Path | None:
    """The session whose run wrote this curve CSV (``<session>/photometry/``), else ``None``.

    The old-file rules read the run's frames and flight recorder: they apply to the
    live run's own CSVs only. A batch re-run's folder has its own diagnostics and
    flags, and a preview curve in ``<sessions>/targets/`` has no frames to read.
    """
    folder = Path(path).parent
    root = folder.parent
    if folder.name == "photometry" and (root / SESSION_FILENAME).is_file():
        return root
    return None


def apply_old_file_rules_to_file(
    path: Path | str, curves: dict[str, LightCurve]
) -> OldFileRules | None:
    """:func:`apply_old_file_rules` for a curve CSV opened alone (Analyze **Open curve CSV**)."""
    root = session_of_curve_file(path)
    if root is None:
        return None
    try:
        review = load_session(root, read_temperature=False)
    except SessionReviewError:
        return None
    return apply_old_file_rules(curves.values(), root, light_pointings(review))


def _fits_start(value: Any) -> datetime | None:
    """A FITS ISO date-time as aware UTC (a date without a time is no epoch)."""
    text = str(value or "").strip()
    if "T" not in text:
        return None
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _fits_temperature(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        from astropy.io import fits

        value = fits.getheader(path, 0).get("CCD-TEMP")
        return _optional_float(value)
    except Exception:  # a damaged optional header must not block review
        return None
