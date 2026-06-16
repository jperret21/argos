"""Plate-solving via ASTAP — recover a WCS for a frame (§6).

We solve on the **green plane** (densest CFA sampling, best SNR for astrometry).
ASTAP is an external binary; if it isn't installed, solving reports a clear
"not found" instead of crashing. This module stays Qt-free — it only builds the
command, runs the subprocess, and parses ASTAP's ``.ini`` result. The worker
(:mod:`seercontrol.workers.solve_worker`) drives it off the UI thread.

ASTAP writes ``<image>.ini`` next to the input with ``PLTSOLVD=T`` and the WCS
keywords (CRVAL1/2, CD matrix or CDELT/CROTA) on success.
"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

#: Don't let downsampling shrink the solved frame's short side below this many
#: pixels — ASTAP needs enough stars/quads to match. Frames from the Seestar are
#: large enough that ``-z 2`` is fine; a small frame (e.g. the 800×600 ASCOM
#: simulator image → 400×300 green plane) would lose its stars at ``-z 2``.
_MIN_SOLVE_PX = 256

#: Executable names to look for on PATH.
_ASTAP_NAMES = ("astap_cli", "astap")
#: Common macOS / Homebrew install locations checked when not on PATH.
_ASTAP_PATHS = (
    "/Applications/ASTAP.app/Contents/MacOS/astap",
    "/opt/homebrew/bin/astap",
    "/opt/homebrew/bin/astap_cli",
    "/usr/local/bin/astap",
    "/usr/local/bin/astap_cli",
)


@dataclass
class SolveSettings:
    """ASTAP invocation parameters (mostly from the Astrometry config panel)."""

    astap_path: str = ""  # explicit binary; empty → auto-detect
    database: str = ""  # star DB name (empty → ASTAP auto-picks by FOV)
    search_radius_deg: float = 30.0  # 0 = blind (slower)
    downsample: int = 2  # 0 = ASTAP auto
    scale_hint_arcsec: float | None = None  # known plate scale → faster/locked
    fov_hint_deg: float | None = None  # field height hint (deg)
    ra_hint_hours: float | None = None  # approx pointing → fast hinted solve
    dec_hint_deg: float | None = None
    timeout_s: float = 120.0


@dataclass
class SolveResult:
    """Outcome of a solve — ``solved`` plus the recovered WCS summary."""

    solved: bool
    message: str = ""
    ra_hours: float | None = None
    dec_deg: float | None = None
    scale_arcsec: float | None = None  # arcsec / px (full-res)
    rotation_deg: float | None = None
    mirrored: bool | None = None
    fields: dict = field(default_factory=dict)  # raw parsed ASTAP keys


@dataclass
class WCSOverlay:
    """Astrometry overlay geometry in **green-plane pixels** (display-agnostic).

    The viewer scales these to whatever display view is active (×1 super-pixel,
    ×2 raw/interp), exactly as it does for the star overlay.
    """

    lines: list  # list of (xs, ys) np.ndarray polylines (NaN breaks off-frame runs)
    center: tuple[float, float] | None  # field centre (CRVAL) in green px
    center_label: str  # human-readable centre RA/Dec
    target: tuple[float, float] | None  # intended target in green px (or None)


def find_astap(explicit: str = "") -> str | None:
    """Locate the ASTAP binary: explicit path → PATH → common locations."""
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p)
    for name in _ASTAP_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for cand in _ASTAP_PATHS:
        if Path(cand).exists():
            return cand
    return None


def parse_astap_ini(text: str) -> SolveResult:
    """Parse ASTAP's ``key=value`` ``.ini`` output into a :class:`SolveResult`."""
    kv: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith(("#", ";", "[")):
            key, value = line.split("=", 1)
            kv[key.strip().upper()] = value.strip()

    if kv.get("PLTSOLVD", "").upper() not in ("T", "TRUE", "1", "Y"):
        msg = kv.get("ERROR") or kv.get("WARNING") or "ASTAP did not solve the field"
        return SolveResult(solved=False, message=msg, fields=kv)

    def _f(key: str) -> float | None:
        try:
            return float(kv[key])
        except (KeyError, ValueError):
            return None

    crval1, crval2 = _f("CRVAL1"), _f("CRVAL2")  # deg
    cd1_1, cd1_2, cd2_1, cd2_2 = _f("CD1_1"), _f("CD1_2"), _f("CD2_1"), _f("CD2_2")

    scale = rotation = None
    mirrored = None
    if None not in (cd1_1, cd2_2):
        c12, c21 = cd1_2 or 0.0, cd2_1 or 0.0
        det = cd1_1 * cd2_2 - c12 * c21
        scale = math.sqrt(abs(det)) * 3600.0
        mirrored = det > 0.0
        rotation = math.degrees(math.atan2(c21, cd1_1))
    else:
        cdelt = _f("CDELT2")
        if cdelt:
            scale = abs(cdelt) * 3600.0
        rotation = _f("CROTA2")

    ra_hours = (crval1 / 15.0) % 24.0 if crval1 is not None else None
    return SolveResult(
        solved=True,
        message="solved",
        ra_hours=ra_hours,
        dec_deg=crval2,
        scale_arcsec=round(scale, 3) if scale else None,
        rotation_deg=round(rotation, 2) if rotation is not None else None,
        mirrored=mirrored,
        fields=kv,
    )


def solve_array(green: np.ndarray, settings: SolveSettings) -> SolveResult:
    """Plate-solve a 2-D green-plane array. Writes a temp FITS and runs ASTAP.

    Returns a :class:`SolveResult`; ``solved=False`` (with a message) when ASTAP
    is missing, times out, or fails to solve — never raises for those cases.
    """
    from astropy.io import fits  # heavy import — only when solving

    astap = find_astap(settings.astap_path)
    if astap is None:
        return SolveResult(False, message="ASTAP not found — set its path in Configuration")
    if green.ndim != 2:
        return SolveResult(False, message=f"expected a 2-D plane, got {green.shape}")

    # Don't downsample a frame that's already small into too few stars (no-op for
    # the large Seestar frames this is tuned for; rescues small sim/cropped ones).
    eff = settings
    short = int(min(green.shape))
    down = _clamp_downsample(short, settings.downsample)
    if down != settings.downsample:
        logger.info("ASTAP: downsample %d→%d (short side %dpx)", settings.downsample, down, short)
        eff = replace(settings, downsample=down)

    with tempfile.TemporaryDirectory() as tmp:
        fits_path = Path(tmp) / "solve.fits"
        fits.PrimaryHDU(data=green.astype(np.uint16)).writeto(fits_path, overwrite=True)

        result = _run_astap(astap, fits_path, eff)
        # A hinted (local-radius) solve trusts the pointing hint. If it failed,
        # the hint may be wrong or stale (mount not actually on target), so the
        # local radius scanned the wrong patch of sky — retry once whole-sky.
        local = eff.search_radius_deg and eff.search_radius_deg > 0
        hinted = eff.ra_hint_hours is not None and eff.dec_hint_deg is not None
        if not result.solved and hinted and local:
            logger.info("ASTAP: hinted solve failed — retrying blind (whole-sky)")
            result = _run_astap(
                astap, fits_path, replace(eff, ra_hint_hours=None, dec_hint_deg=None)
            )
        return result


def _run_astap(astap: str, fits_path: Path, s: SolveSettings) -> SolveResult:
    """Run ASTAP once on ``fits_path`` and parse its ``.ini``/``.wcs`` output."""
    cmd = _build_command(astap, fits_path, s)
    logger.info("ASTAP: %s", " ".join(cmd))
    try:
        subprocess.run(
            cmd,
            cwd=str(fits_path.parent),
            capture_output=True,
            timeout=s.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SolveResult(False, message=f"ASTAP timed out after {s.timeout_s:.0f}s")
    except OSError as exc:
        return SolveResult(False, message=f"could not run ASTAP: {exc}")

    for out in (fits_path.with_suffix(".ini"), fits_path.with_suffix(".wcs")):
        if out.exists():
            return parse_astap_ini(out.read_text(errors="ignore"))
    return SolveResult(False, message="ASTAP produced no solution file")


def _clamp_downsample(short_px: int, downsample: int) -> int:
    """Reduce the downsample factor so the short side stays >= ``_MIN_SOLVE_PX``.

    ``downsample=0`` (ASTAP auto) is left untouched. Large frames keep their
    configured factor; small frames are protected from losing all their stars.
    """
    down = downsample
    while down > 1 and short_px // down < _MIN_SOLVE_PX:
        down -= 1
    return down


def _build_command(astap: str, fits_path: Path, s: SolveSettings) -> list[str]:
    """Assemble the ASTAP CLI command for a (hinted or blind) solve."""
    cmd = [astap, "-f", str(fits_path), "-wcs"]
    has_pos = s.ra_hint_hours is not None and s.dec_hint_deg is not None
    if has_pos and s.search_radius_deg and s.search_radius_deg > 0:
        cmd += ["-r", f"{s.search_radius_deg:g}"]
    else:
        # A search radius is a radius *around a position*. With no pointing hint
        # there is no centre, so a local radius would scan the wrong patch of sky
        # (the bug behind "no star found" on un-pointed frames). Search the whole
        # sky instead — slower, but it actually finds the field.
        cmd += ["-r", "180"]
    if s.downsample and s.downsample > 0:
        cmd += ["-z", str(int(s.downsample))]
    if s.fov_hint_deg and s.fov_hint_deg > 0:
        cmd += ["-fov", f"{s.fov_hint_deg:g}"]
    if s.ra_hint_hours is not None and s.dec_hint_deg is not None:
        cmd += ["-ra", f"{s.ra_hint_hours:g}", "-spd", f"{s.dec_hint_deg + 90.0:g}"]
    if s.database:
        # ASTAP distinguishes ``-D <abbreviation>`` (e.g. "D05") from
        # ``-d <path>`` (a database directory). The config exposes
        # abbreviations, so pick the matching flag: a path-looking value uses
        # ``-d``, anything else is treated as an abbreviation via ``-D``.
        if "/" in s.database or Path(s.database).is_dir():
            cmd += ["-d", s.database]
        else:
            cmd += ["-D", s.database]
    return cmd


# --------------------------------------------------------------------------- #
# WCS model (§6) — turn the parsed solution into a pixel ↔ celestial mapping   #
# --------------------------------------------------------------------------- #


class FrameWCS:
    """A solved WCS for the (green-plane) frame: pixel ↔ celestial mapping.

    Backed by :class:`astropy.wcs.WCS` (TAN/gnomonic, the full FITS standard) so
    sign conventions, projection and the CD matrix are handled correctly. Pixel
    coordinates are **0-based green-plane px** (the same grid the star detector
    and ``measure_star_at`` use); celestial coordinates are RA in hours, Dec in
    degrees on the public methods, degrees on the ``*_deg`` ones.
    """

    def __init__(
        self,
        crval1: float,
        crval2: float,
        crpix1: float,
        crpix2: float,
        cd: tuple[float, float, float, float],
    ) -> None:
        from astropy.wcs import WCS  # heavy import — only once a solve exists

        self.crval1 = float(crval1)  # RA  (deg) of the reference pixel
        self.crval2 = float(crval2)  # Dec (deg) of the reference pixel
        self.crpix1 = float(crpix1)
        self.crpix2 = float(crpix2)
        self.cd = tuple(float(c) for c in cd)

        w = WCS(naxis=2)
        w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        w.wcs.crval = [self.crval1, self.crval2]
        w.wcs.crpix = [self.crpix1, self.crpix2]
        w.wcs.cd = [[self.cd[0], self.cd[1]], [self.cd[2], self.cd[3]]]
        self._w = w

    def pixel_to_world_deg(self, x, y):
        """Pixel (0-based, green px) → (RA deg, Dec deg). Accepts scalars/arrays."""
        return self._w.wcs_pix2world(x, y, 0)

    def world_to_pixel_deg(self, ra_deg, dec_deg):
        """(RA deg, Dec deg) → pixel (0-based, green px). Accepts scalars/arrays."""
        return self._w.wcs_world2pix(ra_deg, dec_deg, 0)

    def pixel_to_radec(self, x: float, y: float) -> tuple[float, float]:
        """Pixel (0-based, green px) → (RA hours, Dec deg)."""
        ra, dec = self._w.wcs_pix2world(float(x), float(y), 0)
        return float(ra) / 15.0 % 24.0, float(dec)

    def radec_to_pixel(self, ra_hours: float, dec_deg: float) -> tuple[float, float]:
        """(RA hours, Dec deg) → pixel (0-based, green px)."""
        x, y = self._w.wcs_world2pix(ra_hours * 15.0, dec_deg, 0)
        return float(x), float(y)


def frame_wcs(fields: dict, shape: tuple[int, int] | None = None) -> FrameWCS | None:
    """Build a :class:`FrameWCS` from parsed ASTAP keys (``CRVAL``/``CD``/...).

    Falls back to a CDELT+CROTA matrix if no CD is present, and to the frame
    centre for CRPIX when ASTAP omits it (``shape`` = green-plane ``(h, w)``).
    Returns ``None`` when the minimum keys are missing.
    """
    if not fields:
        return None

    def f(key: str) -> float | None:
        try:
            return float(fields[key])
        except (KeyError, ValueError, TypeError):
            return None

    crval1, crval2 = f("CRVAL1"), f("CRVAL2")
    if crval1 is None or crval2 is None:
        return None

    cd11, cd12 = f("CD1_1"), f("CD1_2")
    cd21, cd22 = f("CD2_1"), f("CD2_2")
    if cd11 is None or cd22 is None:  # derive a CD matrix from CDELT + CROTA
        cdelt1, cdelt2 = f("CDELT1"), f("CDELT2")
        if cdelt1 is None or cdelt2 is None:
            return None
        rot = math.radians(f("CROTA2") or 0.0)
        c, s = math.cos(rot), math.sin(rot)
        cd11, cd12 = cdelt1 * c, -cdelt2 * s
        cd21, cd22 = cdelt1 * s, cdelt2 * c
    cd12, cd21 = cd12 or 0.0, cd21 or 0.0

    crpix1, crpix2 = f("CRPIX1"), f("CRPIX2")
    if crpix1 is None or crpix2 is None:
        if shape is None:
            return None
        gh, gw = int(shape[0]), int(shape[1])
        crpix1, crpix2 = (gw + 1) / 2.0, (gh + 1) / 2.0  # 1-based FITS centre

    try:
        return FrameWCS(crval1, crval2, crpix1, crpix2, (cd11, cd12, cd21, cd22))
    except Exception as exc:  # pragma: no cover - astropy build guard
        logger.warning("Could not build WCS from solution: %s", exc)
        return None


def _nice_step(span: float, target_n: int) -> float:
    """A 1/2/5×10ⁿ 'nice' grid step that yields roughly ``target_n`` divisions."""
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(1, target_n)
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1.0, 2.0, 5.0):
        if raw <= m * mag:
            return m * mag
    return 10.0 * mag


def wcs_grid(
    wcs: FrameWCS,
    shape: tuple[int, int],
    target_radec: tuple[float, float] | None = None,
    target_lines: int = 4,
    samples: int = 40,
    spacing_deg: float | None = None,
) -> WCSOverlay:
    """Build RA/Dec grid lines + centre marker (+ optional target) for the frame.

    ``shape`` is the green-plane ``(h, w)``. Lines are sampled in celestial
    coordinates and projected back to pixels; points outside the frame become
    NaN so the viewer breaks the polyline there. ``target_radec`` is
    ``(ra_hours, dec_deg)`` of the intended target (a framing reticle).

    ``spacing_deg`` forces a fixed on-sky grid step (a *finer* grid than the
    ``target_lines`` auto-pick); ``None`` keeps the adaptive 1/2/5 step. The RA
    step is widened by ``1/cos(dec)`` so meridians and parallels stay visually
    even, and the line count is capped so a tiny spacing can't flood the view.
    """
    gh, gw = int(shape[0]), int(shape[1])
    if gh <= 1 or gw <= 1:
        return WCSOverlay(lines=[], center=None, center_label="", target=None)

    corners = [(0, 0), (gw - 1, 0), (0, gh - 1), (gw - 1, gh - 1), ((gw - 1) / 2, (gh - 1) / 2)]
    ras, decs = [], []
    for px, py in corners:
        ra, dec = wcs.pixel_to_world_deg(float(px), float(py))
        ras.append(float(ra))
        decs.append(float(dec))
    # Unwrap RA around the first corner so a field near 0h doesn't span ~360°.
    ref = ras[0]
    ras = [r - 360.0 if r - ref > 180 else r + 360.0 if r - ref < -180 else r for r in ras]
    ra_min, ra_max = min(ras), max(ras)
    dec_min, dec_max = min(decs), max(decs)
    if spacing_deg and spacing_deg > 0:
        # Fixed on-sky spacing; keep RA/Dec lines visually even, cap the count.
        cosd = max(0.05, math.cos(math.radians((dec_min + dec_max) / 2.0)))
        dec_step = spacing_deg
        ra_step = spacing_deg / cosd
        _max_lines = 160
        while (dec_max - dec_min) / dec_step > _max_lines:
            dec_step *= 2.0
        while (ra_max - ra_min) / ra_step > _max_lines:
            ra_step *= 2.0
    else:
        ra_step = _nice_step(ra_max - ra_min, target_lines)
        dec_step = _nice_step(dec_max - dec_min, target_lines)
    margin = 2.0
    lines: list = []

    def _line(ra_arr: np.ndarray, dec_arr: np.ndarray) -> None:
        xs, ys = wcs.world_to_pixel_deg(np.asarray(ra_arr), np.asarray(dec_arr))
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        off = (xs < -margin) | (xs > gw + margin) | (ys < -margin) | (ys > gh + margin)
        xs[off] = np.nan
        ys[off] = np.nan
        if np.isfinite(xs).any():
            lines.append((xs, ys))

    d = math.ceil(dec_min / dec_step) * dec_step
    while d <= dec_max + 1e-9:  # iso-Dec lines (constant Dec, varying RA)
        _line(np.linspace(ra_min, ra_max, samples), np.full(samples, d))
        d += dec_step
    a = math.ceil(ra_min / ra_step) * ra_step
    while a <= ra_max + 1e-9:  # iso-RA lines (constant RA, varying Dec)
        _line(np.full(samples, a), np.linspace(dec_min, dec_max, samples))
        a += ra_step

    cx, cy = wcs.world_to_pixel_deg(wcs.crval1, wcs.crval2)
    center = (float(cx), float(cy))
    center_label = (
        f"Centre  RA {format_ra_hms(wcs.crval1 / 15.0)}  Dec {format_dec_dms(wcs.crval2)}"
    )
    target = None
    if target_radec is not None:
        tx, ty = wcs.world_to_pixel_deg(target_radec[0] * 15.0, target_radec[1])
        target = (float(tx), float(ty))
    return WCSOverlay(lines=lines, center=center, center_label=center_label, target=target)


# --------------------------------------------------------------------------- #
# Formatting + spherical helpers (§6)                                          #
# --------------------------------------------------------------------------- #


def format_ra_hms(ra_hours: float) -> str:
    """Format RA (hours) as ``HHhMMmSS.Ss``."""
    ra_hours %= 24.0
    h = int(ra_hours)
    m_full = (ra_hours - h) * 60.0
    m = int(m_full)
    s = (m_full - m) * 60.0
    if s >= 59.95:  # carry rounding so we never print 60.0s
        s = 0.0
        m += 1
    if m >= 60:
        m = 0
        h = (h + 1) % 24
    return f"{h:02d}h{m:02d}m{s:04.1f}s"


def format_dec_dms(dec_deg: float) -> str:
    """Format Dec (degrees) as ``±DD°MM'SS.S\"``."""
    sign = "+" if dec_deg >= 0 else "-"
    d = abs(dec_deg)
    deg = int(d)
    m_full = (d - deg) * 60.0
    m = int(m_full)
    s = (m_full - m) * 60.0
    if s >= 59.95:
        s = 0.0
        m += 1
    if m >= 60:
        m = 0
        deg += 1
    return f"{sign}{deg:02d}°{m:02d}'{s:04.1f}\""


def angular_separation_deg(ra1_h: float, dec1_d: float, ra2_h: float, dec2_d: float) -> float:
    """Great-circle separation (degrees) between two RA(h)/Dec(°) points."""
    a1, a2 = math.radians(ra1_h * 15.0), math.radians(ra2_h * 15.0)
    d1, d2 = math.radians(dec1_d), math.radians(dec2_d)
    hav = (
        math.sin((d2 - d1) / 2.0) ** 2
        + math.cos(d1) * math.cos(d2) * math.sin((a2 - a1) / 2.0) ** 2
    )
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(hav))))
