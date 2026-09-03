"""Read a finished Argos session for the offline Review workspace.

The reader is deliberately Qt-free: a session is useful after a crash, on a
different computer, or before any hardware is connected.  It consumes the
durable ``session.json`` truth and only reads FITS headers for telemetry that
is not part of that log (currently CCD temperature).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from argos.core.imaging.session_log import SESSION_FILENAME
from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet
from argos.core.photometry.lightcurve import LightCurve, read_curves_csv


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
    """
    curves: dict[str, LightCurve] = {}
    targets = TargetSet.load(review.root / "targets.json")
    for path in sorted((review.root / "photometry").glob("*.csv")):
        try:
            role, identity, name, auid = _curve_identity(path, targets)
            for key, curve in read_curves_csv(path).items():
                # A multi-curve CSV already carries identity metadata.  The
                # one-star session CSVs use the sidecar data reconstructed
                # above.  Filename role always wins for those legacy files.
                if key == f"target:{path.stem}" or key == path.stem:
                    curve.role = role
                    curve.name = name
                    curve.auid = auid
                    key = identity
                elif not curve.name:
                    curve.name = name
                curves_key = str(key)
                existing = curves.get(curves_key)
                # The same physical target may have an AUID and a catalogue
                # alias recorded in one session. Keep the more complete curve
                # rather than plotting a duplicate science source.
                if existing is None or len(curve.points) > len(existing.points):
                    curves[curves_key] = curve
        except (OSError, ValueError):
            review.warnings.append(f"Could not read preview curve: {path.name}")
    return curves


def _curve_identity(path: Path, targets: TargetSet) -> tuple[str, str, str, str]:
    """Recover ``(role, key, label, auid)`` for a per-star curve CSV."""
    stem = path.stem
    role = ROLE_COMPARISON if stem.startswith("comparison_") else ROLE_TARGET
    candidates = [star for star in targets.stars if star.role == role]
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
        return role, f"{role}:{stem}", stem, ""

    # Targets are deduplicated by sky position, not AUID: a catalogue alias
    # and the user-selected name can legitimately describe the same star.
    if role == ROLE_TARGET:
        identity = f"{role}:pos:{star.ra_deg:.4f},{star.dec_deg:.4f}"
    else:
        identity = star.auid or f"{role}:pos:{star.ra_deg:.5f},{star.dec_deg:.5f}"
    return role, identity, star.display_name, star.auid or ""


def _safe_component(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


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
