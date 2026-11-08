"""Plate solving for the live field (rows A43, A45): ASTAP, WCS and grid in frame px.

A Qt-free port of the solve path of the Qt app with one change: the ASTAP
process can be **cancelled** (killed). Everything else is the fixed 0.5.0
behaviour, reused from ``argos.core`` wherever it is not Qt-coupled:

- :func:`solve_green` is ``solve_array`` (``platesolve.py:197-247``) — the
  temporary FITS of the green plane, the downsample clamp, the retry at
  native sampling, the whole-sky retry of a hinted solve — with
  ``subprocess.Popen`` instead of ``subprocess.run`` so a cancel kills the
  process. The command is core's ``_build_command`` (``platesolve.py:
  284-303``), so the ASTAP database flags keep the S24 rule (``-D <set> -d
  <folder>``, ``platesolve.py:306-319``).
- Settings come from ``build_solve_settings`` (``astrometry_session.py:
  36-75``), the WCS from ``wcs_from_result`` and the grid from
  ``overlay_for`` (``astrometry_session.py:95-153``) — green-plane px — and
  are converted here to the wire's **frame px** (protocol.md "Positions:
  frame pixels"): ``x_frame = 2·x_green + 0.5``.
"""

from __future__ import annotations

import logging
import math
import subprocess
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import numpy as np

from argos.core.imaging.platesolve import (
    FrameWCS,
    SolveResult,
    SolveSettings,
    _build_command,
    _clamp_downsample,
    find_astap,
    parse_astap_ini,
)

logger = logging.getLogger(__name__)

#: Poll period of a running ASTAP process (cancel latency).
_POLL_S = 0.05

Progress = Callable[[str], None]


class SolveCancelled(Exception):
    """The solve was cancelled; the ASTAP process was killed."""


# ---------------------------------------------------------------------------
# Green plane <-> frame px
# ---------------------------------------------------------------------------


def to_frame(x_green: float, y_green: float) -> tuple[float, float]:
    """Green-plane px -> frame px (numpy convention, protocol.md)."""
    return 2.0 * float(x_green) + 0.5, 2.0 * float(y_green) + 0.5


def to_green(x_frame: float, y_frame: float) -> tuple[float, float]:
    """Frame px -> green-plane px (inverse of :func:`to_frame`)."""
    return (float(x_frame) - 0.5) / 2.0, (float(y_frame) - 0.5) / 2.0


def frame_shape_of(green_shape: tuple[int, int]) -> list[int]:
    """The frame size ``[h, w]`` a green shape comes from (even dimensions)."""
    return [int(green_shape[0]) * 2, int(green_shape[1]) * 2]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def frame_wcs_record(wcs: FrameWCS, green_shape: tuple[int, int]) -> dict[str, Any]:
    """The solution's TAN WCS expressed in frame px (``FrameWcs`` of protocol.md).

    A green 0-based pixel ``g`` is frame pixel ``2g + 0.5``; FITS pixels are
    1-based, so ``crpix_frame = 2·(crpix_green − 1) + 0.5 + 1`` and the CD
    matrix (degrees per pixel) halves.
    """
    return {
        "ctype": ["RA---TAN", "DEC--TAN"],
        "crval": [wcs.crval1, wcs.crval2],
        "crpix": [2.0 * wcs.crpix1 - 0.5, 2.0 * wcs.crpix2 - 0.5],
        "cd": [[wcs.cd[0] / 2.0, wcs.cd[1] / 2.0], [wcs.cd[2] / 2.0, wcs.cd[3] / 2.0]],
        "frame_shape": frame_shape_of(green_shape),
    }


def wire_mirrored(wcs: FrameWCS) -> bool | None:
    """Whether the sky is mirrored as the wire draws it (frame px, y down).

    ASTAP's ``mirrored`` is for a FITS display (y up). In px, east is
    ``CD⁻¹·(1, 0)`` and north ``CD⁻¹·(0, 1)``; an unmirrored view (north up,
    east left, y down) has ``north × east < 0``, i.e. ``det(CD) > 0``. The
    client's compass uses the same rule.
    """
    a, b, c, d = (float(v) for v in wcs.cd)
    det = a * d - b * c
    if not math.isfinite(det) or det == 0.0:
        return None
    return det < 0.0


def grid_record(overlay: Any) -> dict[str, Any] | None:
    """A ``WCSOverlay`` (green px, NaN breaks) as the wire's ``Grid`` (frame px)."""
    if overlay is None:
        return None
    lines: list[list[list[float]]] = []
    for xs, ys in overlay.lines:
        segment: list[list[float]] = []
        for x, y in zip(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)):
            if math.isfinite(x) and math.isfinite(y):
                fx, fy = to_frame(x, y)
                segment.append([round(fx, 2), round(fy, 2)])
            elif segment:
                if len(segment) > 1:
                    lines.append(segment)
                segment = []
        if len(segment) > 1:
            lines.append(segment)
    labels = []
    for x, y, text in overlay.labels:
        fx, fy = to_frame(x, y)
        # wcs_grid labels iso-Dec lines with format_dec_dms (a sign first) and
        # iso-RA lines with format_ra_hms (platesolve.py:510-519).
        axis = "dec" if str(text)[:1] in "+-−" else "ra"
        labels.append({"x": round(fx, 2), "y": round(fy, 2), "text": text, "axis": axis})
    centre = None
    if overlay.center is not None:
        cx, cy = to_frame(*overlay.center)
        centre = {"x": round(cx, 2), "y": round(cy, 2), "label": overlay.center_label}
    return {"lines": lines, "labels": labels, "centre": centre}


# ---------------------------------------------------------------------------
# ASTAP, cancellable
# ---------------------------------------------------------------------------


def _run_astap(
    astap: str, fits_path: Path, s: SolveSettings, cancel: threading.Event
) -> SolveResult:
    """``_run_astap`` (``platesolve.py:249-269``) on a killable process."""
    cmd = _build_command(astap, fits_path, s)
    logger.info("ASTAP: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(fits_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return SolveResult(False, message=f"could not run ASTAP: {exc}")
    deadline = time.monotonic() + float(s.timeout_s)
    while True:
        try:
            proc.wait(timeout=_POLL_S)
            break
        except subprocess.TimeoutExpired:
            if cancel.is_set():
                proc.kill()
                proc.wait()
                raise SolveCancelled() from None
            if time.monotonic() >= deadline:
                proc.kill()
                proc.wait()
                return SolveResult(False, message=f"ASTAP timed out after {s.timeout_s:.0f}s")
    for out in (fits_path.with_suffix(".ini"), fits_path.with_suffix(".wcs")):
        if out.exists():
            return parse_astap_ini(out.read_text(errors="ignore"))
    return SolveResult(False, message="ASTAP produced no solution file")


def solve_green(
    green: np.ndarray,
    settings: SolveSettings,
    cancel: threading.Event,
    progress: Progress | None = None,
) -> SolveResult:
    """Plate-solve a green plane — ``solve_array`` (``platesolve.py:197-247``), cancellable.

    Raises :class:`SolveCancelled` when *cancel* is set while ASTAP runs.
    """
    from astropy.io import fits  # heavy import — only when solving

    def stage(text: str) -> None:
        if progress is not None:
            progress(text)

    astap = find_astap(settings.astap_path)
    if astap is None:
        return SolveResult(
            False, message="ASTAP not found — set its path in Settings › Plate solving"
        )
    if green.ndim != 2:
        return SolveResult(False, message=f"expected a 2-D plane, got {green.shape}")

    eff = settings
    short = int(min(green.shape))
    down = _clamp_downsample(short, settings.downsample)
    if down != settings.downsample:
        logger.info("ASTAP: downsample %d→%d (short side %dpx)", settings.downsample, down, short)
        eff = replace(settings, downsample=down)

    with tempfile.TemporaryDirectory(prefix="argos-solve-") as tmp:
        fits_path = Path(tmp) / "solve.fits"
        fits.PrimaryHDU(data=green.astype(np.uint16)).writeto(fits_path, overwrite=True)
        if cancel.is_set():
            raise SolveCancelled()
        stage("ASTAP")
        result = _run_astap(astap, fits_path, eff, cancel)
        attempt = eff
        if not result.solved and eff.downsample > 1:
            attempt = replace(eff, downsample=1)
            logger.info("ASTAP: downsampled solve failed — retrying at native sampling")
            stage("ASTAP at native sampling")
            result = _run_astap(astap, fits_path, attempt, cancel)
        local = attempt.search_radius_deg and attempt.search_radius_deg > 0
        hinted = attempt.ra_hint_hours is not None and attempt.dec_hint_deg is not None
        if not result.solved and hinted and local and eff.allow_blind_retry:
            logger.info("ASTAP: hinted solve failed — retrying blind (whole-sky)")
            stage("ASTAP whole-sky")
            result = _run_astap(
                astap, fits_path, replace(attempt, ra_hint_hours=None, dec_hint_deg=None), cancel
            )
        return result


def header_hint(header: Any) -> tuple[float, float] | None:
    """``(ra_hours, dec_deg)`` from ``OBJCTRA`` / ``OBJCTDEC`` (sexagesimal), else None.

    An opened file was taken elsewhere: the mount's pointing is no hint for
    it. ``RA`` / ``DEC`` are not used: ARGOS writes RA in hours, other
    software in degrees.
    """
    if header is None:
        return None
    ra_text = str(header.get("OBJCTRA", "") or "").strip()
    dec_text = str(header.get("OBJCTDEC", "") or "").strip()
    if not ra_text or not dec_text:
        return None
    try:
        ra = _sexagesimal(ra_text)
        dec = _sexagesimal(dec_text)
    except ValueError:
        return None
    if not (0.0 <= ra < 24.0 and -90.0 <= dec <= 90.0):
        return None
    return ra, dec


def _sexagesimal(text: str) -> float:
    cleaned = text.replace(":", " ").replace("−", "-").split()
    if not 1 <= len(cleaned) <= 3:
        raise ValueError(text)
    sign = -1.0 if cleaned[0].startswith("-") else 1.0
    parts = [abs(float(cleaned[0]))] + [float(p) for p in cleaned[1:]]
    value = parts[0] + (parts[1] / 60.0 if len(parts) > 1 else 0.0)
    value += parts[2] / 3600.0 if len(parts) > 2 else 0.0
    return sign * value
