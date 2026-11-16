"""AAVSO and CSV exports (rows A77-A79 of ``web/spec/README.md`` §4.3).

The files are written by the fixed core writers themselves, never by a
re-implementation: ``write_aavso`` and ``write_curves_csv``
(``argos/core/photometry/lightcurve.py``), on the very ``LightCurve`` objects
the Review plot shows (``hub.review.curve_set(source)``, rows A68-A70), driven
as Qt's Review drives them: Analyze **Open curve CSV**
(``analyze_page.py:737-783``) hands the curves, ``observer.obscode``,
``photometry.default_band`` and the target set to the Photometry window,
whose **Export AAVSO** (``photometry_window.py:362-418``) and **Export
measurements** (``:345-360``) call the writers.

The guards are Qt 0.5.0's (S10 unidentified curves, S11 observer code and
flagged points, S53 one filter per report) plus S60 (no undated row) and S61
(one filter per CSV), with the preview the dialog shows (Q-R2, Q-R3).
"""

from __future__ import annotations

import logging
import math
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from argos.core.catalog.targets import ROLE_CHECK, ROLE_TARGET, comparison_chart_id
from argos.core.photometry import lightcurve
from argos.core.photometry.lightcurve import write_aavso, write_curves_csv
from argos.server.errors import ApiError
from argos.server.jobs import JobContext

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: GUARD (S60): a point dated before this is undated (a pre-0.5.0 batch re-run wrote
#: JD 0 for a frame without DATE-OBS, S13). The fixed core skips such points itself
#: (``AavsoExportSummary.undated_excluded``); before S60 reaches this tree the server
#: leaves them out before calling the writer, which then writes the same file.
MIN_AAVSO_JD = getattr(lightcurve, "MIN_AAVSO_JD", 2_400_000.0)
_CORE_SKIPS_UNDATED = "undated_excluded" in getattr(
    lightcurve.AavsoExportSummary, "__dataclass_fields__", {}
)

#: Johnson/Cousins filter tokens whose band letter FILT should name (S11).
_JOHNSON = {"u": "U", "b": "B", "v": "V", "r": "R", "i": "I"}
_BAND_RE = re.compile(r"^[A-Za-z0-9]{1,5}$")
_HEAD_ROWS = 3


def plural(n: int, word: str, many: str | None = None) -> str:
    """``"1 point"``, ``"2 points"``: the W7 strings say the count once, in words."""
    return f"{n} {word if n == 1 else (many or word + 's')}"


#: Session subfolders an export never writes into: the run's own data (its curve
#: CSVs, frames and flight recorder) and re-run outputs (W7 technical review).
_PROTECTED_DIRS = ("photometry", "lights", "diagnostics", "darks", "flats", "biases")
_PROTECTED_FILES = ("session.json", "targets.json")


def protected_reason(path: Path, sources: list[Path]) -> str | None:
    """Why ``path`` must not be overwritten by an export, or ``None``.

    The export's own source files, and inside an Argos session (a folder holding
    ``session.json``) its data folders, re-run folders and record files.
    """
    resolved = path.resolve()
    if any(resolved == src.resolve() for src in sources if src is not None):
        return f"{path.name} is a source of this export"
    for parent in resolved.parents:
        if (parent / "session.json").is_file():
            rel = resolved.relative_to(parent)
            top = rel.parts[0]
            if len(rel.parts) == 1 and top in _PROTECTED_FILES:
                return f"{path.name} is the session's own record"
            if len(rel.parts) > 1 and (
                top in _PROTECTED_DIRS or top.startswith("photometry_rerun_")
            ):
                return f"{top}/ holds the session's own data"
            return None
    return None


def _safe(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value) or "photometry"


def undated(point) -> bool:
    """S60: a point without a usable date (JD 0 from a pre-0.5.0 batch re-run)."""
    jd = point.jd_utc
    return not (isinstance(jd, (int, float)) and math.isfinite(jd) and jd >= MIN_AAVSO_JD)


def obscode_is_set(code: str) -> bool:
    """Q-R2 / S11: empty or Qt's ``XXX`` placeholder is no observer code."""
    return bool(code) and code.upper() != "XXX"


def band_note(band: str, token: str | None) -> str | None:
    """S11: a warning when FILT does not fit the frames' filter (the export is allowed)."""
    token = (token or "").lower()
    if token == "lp":
        return (
            "The frames were taken through the LP filter, a duo-band nebula filter: no AAVSO"
            f" band matches it. FILT={band} would misreport the band."
        )
    letter = _JOHNSON.get(token)
    if letter is not None and band.upper() != letter:
        return f"The frames were taken through the {letter} filter but FILT is {band}."
    return None


# ---------------------------------------------------------------------------
# The selection
# ---------------------------------------------------------------------------


@dataclass
class Selection:
    """What one export reads from a curve set."""

    data: Any  # review.CurveSetData
    filter: str | None
    filters: list[str]
    curves: list[Any] = field(default_factory=list)  # ReviewCurveData, source order
    check: Any = None
    refusal: dict[str, Any] | None = None


def _refuse(code: str, message: str, **details: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "message": message}
    if details:
        out["details"] = details
    return out


def _filters(curves, roles) -> list[str]:
    """S53's tokens: the non-empty filter tokens of the curves of ``roles``."""
    return sorted({c.filter for c in curves if c.filter and c.lc.role in roles})


def select_for_aavso(data, body: dict[str, Any]) -> Selection:
    """The target curves and the check curve one AAVSO report covers, or a refusal."""
    curves = list(data.curves)
    tokens = _filters(curves, (ROLE_TARGET, ROLE_CHECK))
    chosen = body.get("filter")
    sel = Selection(data=data, filter=None, filters=tokens)
    if chosen is not None:
        if chosen not in tokens and not (chosen == "" and not tokens):
            sel.refusal = _refuse(
                "unknown_curve", f"No curve in the filter {chosen!r}.", filters=tokens
            )
            return sel
        pool = [c for c in curves if c.filter == chosen]
        sel.filter = chosen
    elif len(tokens) > 1:
        sel.refusal = _refuse(
            "multiple_filters",
            f"These curves are in {len(tokens)} filters ({', '.join(tokens)}), and an AAVSO"
            " report has one band: choose one.",
            filters=tokens,
        )
        return sel
    else:
        pool = curves
        sel.filter = tokens[0] if tokens else None
    keys = body.get("keys")
    by_key = {c.key: c for c in pool}
    if keys is not None:
        wrong = [k for k in keys if k not in by_key or by_key[k].lc.role != ROLE_TARGET]
        if wrong:
            sel.refusal = _refuse(
                "unknown_curve",
                f"Not a target curve of this filter: {', '.join(wrong)}.",
                keys=wrong,
            )
            return sel
        targets = [by_key[k] for k in keys]
    else:
        targets = [c for c in pool if c.lc.role == ROLE_TARGET]
    sel.curves = [c for c in targets if c.lc.points]
    if body.get("use_check", True):
        check_key = body.get("check_key")
        if check_key is not None:
            check = by_key.get(check_key)
            if check is None or check.lc.role != ROLE_CHECK:
                sel.refusal = _refuse(
                    "unknown_curve",
                    f"Not a check curve of this filter: {check_key}.",
                    keys=[check_key],
                )
                return sel
            sel.check = check
        else:
            sel.check = next((c for c in pool if c.lc.role == ROLE_CHECK and c.lc.points), None)
    if not sel.curves:
        sel.refusal = _refuse("no_target", "No target points to export.")
        return sel
    problems = [c.problem for c in (*sel.curves, sel.check) if c is not None and c.problem]
    if problems:
        sel.refusal = _refuse(
            "curve_unidentified",
            "The star or role of this light curve is unknown — no AAVSO export.",
            problems=problems,
        )
    return sel


def select_for_csv(data, body: dict[str, Any]) -> Selection:
    """The curves of one CSV export (every curve with points), or a refusal."""
    curves = list(data.curves)
    keys = body.get("keys")
    chosen = body.get("filter")
    sel = Selection(
        data=data, filter=chosen, filters=_filters(curves, ("target", "check", "comparison"))
    )
    if chosen is not None:
        curves = [c for c in curves if c.filter == chosen]
    by_key = {c.key: c for c in curves}
    if keys is not None:
        wrong = [k for k in keys if k not in by_key]
        if wrong:
            sel.refusal = _refuse(
                "unknown_curve", f"No such curve: {', '.join(wrong)}.", keys=wrong
            )
            return sel
        curves = [by_key[k] for k in keys]
    sel.curves = [c for c in curves if c.lc.points]
    if not sel.curves:
        sel.refusal = _refuse("no_points", "No measurements to export.")
        return sel
    tokens = sorted({c.filter for c in sel.curves if c.filter})
    if len(tokens) > 1:
        # S61: the file has no filter column; read back, one star's two curves merge.
        sel.refusal = _refuse(
            "multiple_filters",
            f"These curves are in {len(tokens)} filters ({', '.join(tokens)}): the CSV has no"
            " filter column, so export one filter at a time.",
            filters=tokens,
        )
        return sel
    sel.filter = tokens[0] if tokens else chosen
    return sel


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _dated_copy(lc):
    """GUARD (S60): ``lc`` without its undated points, for a core without S60."""
    if _CORE_SKIPS_UNDATED or not any(undated(p) for p in lc.points):
        return lc
    copy = lightcurve.LightCurve(
        auid=lc.auid, name=lc.name, role=lc.role, filter_name=lc.filter_name
    )
    copy.points = [p for p in lc.points if not undated(p)]
    return copy


@dataclass
class AavsoArgs:
    obscode: str
    band: str
    chart: str | None


def write_report(path: Path, sel: Selection, args: AavsoArgs):
    """``write_aavso`` exactly as Qt's Export AAVSO calls it: the curves, then the check."""
    curves = [_dated_copy(c.lc) for c in sel.curves]
    if sel.check is not None:
        curves.append(sel.check.lc)
    return write_aavso(path, curves, obscode=args.obscode, filt=args.band, chart=args.chart)


#: The left-out counts of a report, in ``write_aavso``'s order.
EXCLUDED_KEYS = ("saturated", "no_detection", "suspect", "nonfinite", "undated")


def _counts(lc) -> dict[str, int]:
    """Per-target counts with ``write_aavso``'s rules (S60 first, then non-finite, flags).

    ``no_detection``: suspect points of a frame without a detection in the run's flight
    recorder (S67, ``LcPoint.no_detection``), counted apart as the writer does.
    """
    out = {"points": len(lc.points), "rows": 0, **{k: 0 for k in EXCLUDED_KEYS}}
    for p in lc.points:
        if undated(p):
            out["undated"] += 1
        elif not (math.isfinite(p.mag) and math.isfinite(p.mag_err)):
            out["nonfinite"] += 1
        elif p.saturated:
            out["saturated"] += 1
        elif p.suspect and getattr(p, "no_detection", False):
            out["no_detection"] += 1
        elif p.suspect:
            out["suspect"] += 1
        else:
            out["rows"] += 1
    return out


#: The sessions backend's per-point flags from the run's flight recorder (A69): a target
#: SNR below 3 (no detection, S35's rule) or a zero point > 1 mag off (S52).
_RECORDER_FLAGS = ("low_snr", "zp_outlier")
#: S56's old-file rule (A69 ``few_anchors``): fewer than 3 anchors at SNR 10.
_UNVERIFIED_FLAGS = ("few_anchors",)


def recorder_flagged(curve, codes: tuple[str, ...] = _RECORDER_FLAGS) -> list[int]:
    """Indices of ``curve``'s points that would be rows but the flight recorder flags.

    Once the core applies S67 (the merge), a no-detection frame's points are suspect
    and left out, so none remains here; the S56 ``few_anchors`` points stay written,
    with the preview's warning pointing to a re-run (S58).
    """
    flags = getattr(curve, "flags", None) or []
    out = []
    for i, p in enumerate(curve.lc.points):
        if i >= len(flags) or not set(flags[i]) & set(codes):
            continue
        if codes is _UNVERIFIED_FLAGS and set(flags[i]) & set(_RECORDER_FLAGS):
            continue  # counted once, as no detection
        if undated(p) or not (math.isfinite(p.mag) and math.isfinite(p.mag_err)):
            continue
        if p.saturated or p.suspect:
            continue
        out.append(i)
    return out


def _excluded_note(excluded: dict[str, int]) -> str | None:
    parts = []
    if excluded["saturated"]:
        parts.append(f"{excluded['saturated']} saturated")
    if excluded.get("no_detection"):
        parts.append(f"{excluded['no_detection']} suspect (no detection)")  # S67
    if excluded["suspect"]:
        parts.append(f"{excluded['suspect']} suspect (cosmic ray / hot pixel, or no verified lock)")
    if excluded["nonfinite"]:
        parts.append(f"{excluded['nonfinite']} without a magnitude")
    if excluded["undated"]:
        parts.append(f"{excluded['undated']} undated (JD 0)")
    if not parts:
        return None
    total = sum(excluded.get(k, 0) for k in EXCLUDED_KEYS)
    return "Left out: " + ", ".join(parts) + (" point." if total == 1 else " points.")


class ExportService:
    """``POST /api/export/aavso/preview``, ``/api/export/aavso``, ``/api/export/csv``."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub

    # -- inputs ----------------------------------------------------------------

    def _curve_set(self, source: Any):
        review = getattr(self._hub, "review", None)
        if review is None:  # pragma: no cover - wired in Hub
            raise ApiError(503, "unavailable", "Review is not available")
        if not isinstance(source, dict):
            raise ApiError(400, "invalid_argument", "source must be an object")
        return review.curve_set(source)

    def _aavso_args(self, sel: Selection, body: dict[str, Any]) -> tuple[AavsoArgs, dict]:
        get = self._hub.config.get
        code = body.get("obscode")
        code = str(code if code is not None else (get("observer.obscode", "") or "")).strip()
        band = body.get("filt")
        band_source = "request" if band is not None else "settings"
        band = str(band if band is not None else (get("photometry.default_band", "TG") or "TG"))
        band = band.strip()
        chart = body.get("chart")
        if chart is not None:
            chart_source = "request"
        else:
            targets = sel.data.targets
            chart = comparison_chart_id(targets.stars) if targets is not None else None
            chart_source = "targets" if chart else "none"
        info = {"band_source": band_source, "chart_source": chart_source}
        return AavsoArgs(obscode=code, band=band, chart=chart), info

    def _default_path(self, data, filter_token: str | None, suffix: str) -> Path | None:
        root = getattr(data, "root", None)
        if root is None:
            return None
        obj = _safe(data.object_name or Path(root).name)
        token = f"_{filter_token}" if filter_token else ""
        return Path(root) / f"{obj}{token}_{suffix}"

    # -- A77 -------------------------------------------------------------------

    def _aavso_plan(self, body: dict[str, Any]):
        data = self._curve_set(body.get("source"))
        sel = select_for_aavso(data, body)
        args, info = self._aavso_args(sel, body)
        refusal = sel.refusal
        if refusal is None and not obscode_is_set(args.obscode):
            refusal = _refuse(
                "obscode_unset",
                "Set your AAVSO observer code in Settings first: it is stamped on every AAVSO"
                " report.",
            )
        if refusal is None and not _BAND_RE.match(args.band):
            refusal = _refuse(
                "invalid_band",
                f"FILT {args.band!r} is not an AAVSO band code (1-5 letters or digits).",
            )
        return data, sel, args, info, refusal

    def preview(self, body: dict[str, Any]) -> dict[str, Any]:
        """``POST /api/export/aavso/preview`` (A77): the same call, into a scratch file."""
        data, sel, args, info, refusal = self._aavso_plan(body)
        targets = []
        total = {k: 0 for k in EXCLUDED_KEYS}
        flagged_rows = unverified_rows = 0
        flagged_points: list[dict[str, Any]] = []
        for c in sel.curves:
            counts = _counts(c.lc)
            flagged = recorder_flagged(c)
            unverified = recorder_flagged(c, _UNVERIFIED_FLAGS)
            flagged_rows += len(flagged)
            unverified_rows += len(unverified)
            targets.append(
                {
                    "key": c.key,
                    "name": c.lc.name,
                    **counts,
                    "recorder_flagged": flagged,
                    "unverified_lock": unverified,
                }
            )
            for i in sorted(flagged + unverified):
                p = c.lc.points[i]
                flagged_points.append(
                    {
                        "key": c.key,
                        "index": i,
                        "jd_utc": p.jd_utc,
                        "mag": p.mag,
                        "mag_err": p.mag_err,
                        "flags": list(c.flags[i]),
                    }
                )
            for k in total:
                total[k] += counts[k]
        rows = sum(t["rows"] for t in targets)
        head = ""
        kname = None
        kmag_rows = 0
        if sel.curves and sel.refusal is None:
            preview_args = AavsoArgs(
                obscode=args.obscode if obscode_is_set(args.obscode) else "XXX",
                band=args.band,
                chart=args.chart,
            )
            with tempfile.TemporaryDirectory(prefix="argos-aavso-preview-") as tmp:
                path = Path(tmp) / "aavso.txt"
                summary = write_report(path, sel, preview_args)
                lines = path.read_text(encoding="utf-8").splitlines()
            data_lines = [ln for ln in lines if not ln.startswith("#")]
            head = "\n".join(lines[: len(lines) - len(data_lines) + _HEAD_ROWS]) + "\n"
            for ln in data_lines:
                fields = ln.split(",")
                if len(fields) >= 11 and fields[9] != "na":
                    kname = fields[9]
                    kmag_rows += 1
            if summary.rows != rows:  # pragma: no cover - the counts are the writer's rules
                logger.warning("AAVSO preview: %d rows counted, %d written", rows, summary.rows)
                rows = summary.rows
        if refusal is None and rows == 0:
            refusal = _refuse(
                "no_rows", "Every point is left out (flagged, undated or without a magnitude)."
            )
        check = None
        if sel.check is not None:
            check = {
                "key": sel.check.key,
                "name": sel.check.lc.name,
                "kname": kname,
                "points": len(sel.check.lc.points),
                "kmag_rows": kmag_rows,
            }
        airmass_bad = getattr(data, "airmass_source", "csv") == "header"
        airmass_header = getattr(data, "airmass_column", "csv") == "header"
        notes = []
        warnings: list[dict[str, Any]] = []
        excluded_note = _excluded_note(total)
        if excluded_note:
            notes.append(excluded_note)
        if sel.check is None:
            notes.append("No check star in this source: KNAME and KMAG are na.")
        elif not kmag_rows:
            notes.append("The check star has no usable point on these frames: KMAG is na.")
        if flagged_rows:
            warnings.append(
                {
                    "code": "recorder_flagged",
                    "count": flagged_rows,
                    "message": (
                        f"{plural(flagged_rows, 'point')} would be written although the run's"
                        " flight recorder marks them as no detection (target SNR below 3) or a"
                        " zero point more than 1 mag off: check them before you submit."
                    ),
                }
            )
        if unverified_rows:
            warnings.append(
                {
                    "code": "unverified_lock",
                    "count": unverified_rows,
                    "message": (
                        f"{plural(unverified_rows, 'point')} would be written although fewer"
                        " than 3 comparison or check stars reached SNR 10 on their frames"
                        " (S56): nothing verified the apertures. The rule is conservative:"
                        " re-run the photometry on this session first (S58), which verifies"
                        " each such frame with a plate solve and flags only those it cannot."
                    ),
                }
            )
        note = band_note(args.band, sel.filter)
        if note:
            notes.append(note)
        airmass_message = None
        if airmass_header:
            # S66 (option b): each Argos frame's header AIRMASS; a point without one (no
            # light within 5 s, no AIRMASS, a frozen pointing) keeps the CSV's.
            computed = int(getattr(getattr(data, "rules", None), "airmass_computed", 0) or 0)
            airmass_message = "AMASS is each frame's FITS header AIRMASS, from the mount (S66)."
            if airmass_bad:
                airmass_message += (
                    " The site in Settings was not where the telescope was during this run."
                )
                if computed:
                    airmass_message += (
                        f" {plural(computed, 'point')} of the run without one keep the airmass"
                        " computed for that site, which is wrong."
                    )
                    warnings.insert(
                        0,
                        {
                            "code": "airmass_wrong_site",
                            "count": computed,
                            "message": airmass_message,
                        },
                    )
        elif airmass_bad:
            airmass_message = (
                "AMASS comes from the curves' airmass, computed for the site in Settings, which"
                " was not where the telescope was during this run: these values are wrong (the"
                " FITS header AIRMASS, from the mount, is right)."
            )
            warnings.insert(
                0, {"code": "airmass_wrong_site", "count": rows, "message": airmass_message}
            )
        default = self._default_path(data, sel.filter, "aavso.txt")
        return {
            "source": dict(getattr(data, "source", body.get("source") or {})),
            "object": getattr(data, "object_name", None),
            "obscode": args.obscode if obscode_is_set(args.obscode) else "",
            "obscode_set": obscode_is_set(args.obscode),
            "band": args.band,
            "band_source": info["band_source"],
            "filter": sel.filter,
            "filters": sel.filters,
            "band_note": note,
            "chart": args.chart or "na",
            "chart_source": info["chart_source"],
            "check": check,
            "targets": targets,
            "rows": rows,
            "excluded": total,
            "recorder_flagged": flagged_rows,
            "unverified_lock": unverified_rows,
            "flagged_points": flagged_points,
            "warnings": warnings,
            "airmass": {
                "source": "header" if airmass_header else "csv",
                "state": "mismatch" if airmass_bad else "ok",
                "message": airmass_message,
            },
            "notes": notes,
            "refusal": refusal,
            "head": head,
            "default_path": str(default) if default is not None else None,
        }

    # -- A78, A79 --------------------------------------------------------------

    def _destination(self, body: dict[str, Any], suffix: str, data=None) -> Path | None:
        raw = body.get("path")
        if raw is None:
            return None
        path, _root = self._hub.fs_roots.resolve(str(raw), what="export file")
        if path.suffix.lower() != suffix:
            raise ApiError(400, "invalid_argument", f"The export file must end in {suffix}")
        if path.is_dir():
            raise ApiError(400, "invalid_argument", f"{path} is a folder")
        if not path.parent.is_dir():
            raise ApiError(404, "not_found", f"No folder {path.parent}")
        sources = [getattr(c, "csv", None) for c in getattr(data, "curves", None) or []]
        reason = protected_reason(path, [p for p in sources if p is not None])
        if reason is not None:
            raise ApiError(
                409,
                "protected_path",
                f"{reason}: an export never replaces it. Choose another file name or folder.",
            )
        if path.exists() and not body.get("overwrite"):
            raise ApiError(
                409, "file_exists", f"{path.name} exists: confirm to replace it", details={}
            )
        return path

    def _start(self, kind: str, path: Path | None, name: str, write) -> dict[str, Any]:
        hub = self._hub
        resource = str(path) if path is not None else f"download:{uuid.uuid4().hex}"

        def body(ctx: JobContext) -> dict[str, Any]:
            target = path if path is not None else hub._download_path(ctx.id, name)
            # Written beside, then renamed: a failed write never truncates the file
            # it replaces (W7 technical review).
            part = target.with_name(f".{target.name}.{ctx.id}.part")
            try:
                result = write(part)
                os.replace(part, target)
            except OSError as exc:
                part.unlink(missing_ok=True)
                hub.log("error", f"{kind} export failed: {exc}", source="review", topic="export")
                raise ApiError(500, "write_failed", f"Could not write {target}: {exc}") from exc
            if path is None:
                with hub._downloads_lock:
                    hub._downloads[ctx.id] = (target, name)
            result.update(
                {
                    "path": str(target) if path is not None else None,
                    "name": name,
                    "bytes": target.stat().st_size,
                    "download": path is None,
                }
            )
            return result

        hub._prune_downloads()
        return hub.jobs.start("export", body, resource=resource, cancellable=False, stage="writing")

    def export_aavso(self, body: dict[str, Any]) -> dict[str, Any]:
        """``POST /api/export/aavso`` (A78): refusals at once (409), then the ``export`` job."""
        data, sel, args, _info, refusal = self._aavso_plan(body)
        if refusal is None and sel.curves:
            if sum(_counts(c.lc)["rows"] for c in sel.curves) == 0:
                refusal = _refuse(
                    "no_rows",
                    "Every point is left out (flagged, undated or without a magnitude).",
                )
        if refusal is not None:
            raise ApiError(409, refusal["code"], refusal["message"], details=refusal.get("details"))
        path = self._destination(body, ".txt", data)
        default = self._default_path(data, sel.filter, "aavso.txt")
        name = (
            path.name
            if path is not None
            else (default.name if default is not None else "aavso.txt")
        )

        def write(target: Path) -> dict[str, Any]:
            summary = write_report(target, sel, args)
            excluded = {k: 0 for k in EXCLUDED_KEYS}
            for c in sel.curves:
                counts = _counts(c.lc)
                for k in excluded:
                    excluded[k] += counts[k]
            note = _excluded_note(excluded)
            text = f"AAVSO export: {plural(summary.rows, 'observation')} written to {name}."
            if note:
                text += " " + note
            self._hub.log("info", text, source="review", topic="export")
            return {
                "rows": summary.rows,
                "curves": len(sel.curves),
                "filter": sel.filter,
                "excluded": excluded,
                "notes": [text],
            }

        return self._start("AAVSO", path, name, write)

    def export_csv(self, body: dict[str, Any]) -> dict[str, Any]:
        """``POST /api/export/csv`` (A79): ``write_curves_csv`` over the selected curves."""
        data = self._curve_set(body.get("source"))
        sel = select_for_csv(data, body)
        if sel.refusal is not None:
            raise ApiError(
                409, sel.refusal["code"], sel.refusal["message"], details=sel.refusal.get("details")
            )
        path = self._destination(body, ".csv", data)
        default = self._default_path(data, sel.filter, "photometry.csv")
        name = (
            path.name
            if path is not None
            else (default.name if default is not None else "photometry.csv")
        )
        curves = [c.lc for c in sel.curves]

        def write(target: Path) -> dict[str, Any]:
            write_curves_csv(target, curves)
            rows = sum(len(lc.points) for lc in curves)
            text = (
                f"CSV export: {plural(len(curves), 'curve')}, {plural(rows, 'row')}"
                f" written to {name}."
            )
            self._hub.log("info", text, source="review", topic="export")
            return {
                "rows": rows,
                "curves": len(curves),
                "filter": sel.filter,
                "excluded": None,
                "notes": [text],
            }

        return self._start("CSV", path, name, write)


__all__ = [
    "MIN_AAVSO_JD",
    "ExportService",
    "band_note",
    "obscode_is_set",
    "plural",
    "protected_reason",
    "recorder_flagged",
    "select_for_aavso",
    "select_for_csv",
    "undated",
    "write_report",
]
