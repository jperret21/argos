"""Per-frame quality metrics — focus (§5) and acquisition QA (§7).

Pure numpy, Qt-free, unit-tested. Computed on the green CFA plane (densest
sampling, best SNR for stars). These are *analysis* outputs — they never modify
the raw frame.

Seestar context: 2.9 µm @ 160 mm ≈ 3.74″/px (undersampled), so HFD/FWHM are
coarse — treat the trend, not the absolute value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from seercontrol.core.imaging.debayer import compute_hfd
from seercontrol.core.imaging.green import green_plane

logger = logging.getLogger(__name__)

#: Detection threshold above the sky background, in robust sigmas.
_DETECT_SIGMA = 5.0
#: Default aperture radius (green-plane px) used to measure a star's profile.
_STAR_RADIUS = 5
#: Default cap on the number of stars measured per frame (brightest first).
_MAX_STARS = 120
#: Gaussian FWHM = this constant × sigma.
_FWHM_PER_SIGMA = 2.3548200450309493
#: Floor on the robust sigma (ADU) so a near-flat frame doesn't detect noise.
_SIGMA_FLOOR = 1.0

#: Public default aperture radius (green-plane px) for star measurement (§5).
DEFAULT_STAR_RADIUS = _STAR_RADIUS

#: Snap window (green-plane px) for the *initial* click — generous so a click
#: near a star locks onto its peak. Kept independent of the aperture radius so
#: changing the radius can't re-snap the centre onto a different star.
_SNAP_SEARCH = 6
#: Snap window when *re-measuring* an already-selected star (new frame / radius
#: change): tight, so the centre stays put and only tracks small drift.
TRACK_SNAP_SEARCH = 2

#: Plate scale (IMX585 @ 160 mm): 206.265·2.9/160 ≈ 3.74″ per full-res px. The
#: green plane is subsampled ×2, so one green-plane px spans twice that on sky.
ARCSEC_PER_FULL_PX = 206.265 * 2.9 / 160.0
ARCSEC_PER_GREEN_PX = ARCSEC_PER_FULL_PX * 2.0


@dataclass(frozen=True)
class FrameMetrics:
    """Quality summary of a single frame (display/QA only)."""

    hfd: float | None  # half-flux diameter of the brightest star (px, subsampled)
    star_count: int  # detected stars (local maxima above threshold)
    sky_adu: float  # median background (ADU)
    peak_adu: int  # brightest pixel in the raw frame (ADU)


@dataclass(frozen=True)
class DetectedStar:
    """A single detected star, measured on the green half-res plane.

    Coordinates are in **green-plane pixels** (raw // 2). The viewer scales them
    to whatever display view is active (super-pixel/channel = ×1, raw/interp =
    ×2). FWHM is in green-plane pixels; multiply by the plate scale for arcsec.
    """

    x: float  # centroid X (green-plane px)
    y: float  # centroid Y (green-plane px)
    flux: float  # background-subtracted summed flux in the window
    fwhm: float  # mean Gaussian FWHM (green-plane px)
    eccentricity: float  # 0 = round, →1 = elongated


@dataclass(frozen=True)
class StarField:
    """Detected stars + frame-level focus/shape summary (display/QA, §5/§7)."""

    stars: tuple[DetectedStar, ...]
    sky_adu: float
    mean_fwhm: float | None  # mean over detected stars (green-plane px)
    mean_eccentricity: float | None

    @property
    def count(self) -> int:
        return len(self.stars)


@dataclass(frozen=True)
class StarMeasurement:
    """Full measurement of one star (the one the user clicked).

    Coordinates are green-plane px; ``radius`` is the aperture used. The caller
    converts FWHM/HFD to arcsec with the plate scale.
    """

    x: float
    y: float
    fwhm: float | None  # mean Gaussian FWHM (green-plane px)
    eccentricity: float | None
    hfd: float | None  # half-flux diameter (green-plane px)
    peak_adu: int  # brightest raw green pixel in the aperture
    flux: float  # background-subtracted summed flux
    snr: float  # peak SNR = (peak − sky) / sigma
    sky_adu: float
    radius: int


def _green_plane(raw: np.ndarray) -> np.ndarray:
    """Return the float32 green half-res plane — the canonical (G1+G2)/2 plane.

    Single definition shared with the solver (see ``core/imaging/green.py``).
    """
    return green_plane(raw)


def _robust_sky_sigma(g: np.ndarray) -> tuple[float, float]:
    """Return (sky_median, robust_sigma) using MAD; sigma floored to avoid noise."""
    sky = float(np.median(g))
    mad = float(np.median(np.abs(g - sky)))
    sigma = mad * 1.4826 if mad > 0 else float(g.std())
    return sky, max(sigma, _SIGMA_FLOOR)


def _robust_threshold(g: np.ndarray) -> tuple[float, float]:
    """Return (sky_median, detect_threshold) using a MAD-based sigma."""
    sky, sigma = _robust_sky_sigma(g)
    return sky, sky + _DETECT_SIGMA * sigma


def frame_metrics(raw: np.ndarray) -> FrameMetrics:
    """Compute focus + quality metrics for a raw GRBG frame."""
    g = _green_plane(raw)
    sky, threshold = _robust_threshold(g)
    return FrameMetrics(
        hfd=compute_hfd(raw),
        star_count=_count_stars(g, threshold),
        sky_adu=sky,
        peak_adu=int(raw.max()),
    )


def detect_stars(
    raw: np.ndarray, max_stars: int = _MAX_STARS, radius: int = _STAR_RADIUS
) -> StarField:
    """Detect stars on the green plane and measure FWHM + eccentricity each.

    Detection pipeline (Qt-free, used for the live overlay §5 and the QA record
    §7):

    1. robust sky + MAD sigma → threshold at ``sky + 5σ``;
    2. 3×3 local maxima above threshold, brightest first;
    3. **reject hot pixels / cosmics** — a real star's 4 neighbours must also be
       elevated (a lone bright pixel has none);
    4. **deduplicate** — skip a peak within ``radius`` px of an accepted star, so
       one star isn't counted several times;
    5. measure each survivor with :func:`_measure_star` (circular aperture +
       local-background subtraction).

    Args:
        raw:       Raw 2-D GRBG frame.
        max_stars: Cap on the number of stars kept (brightest first).
        radius:    Aperture radius (green-plane px) for profile measurement and
                   the dedup separation.

    Returns:
        A :class:`StarField`. Empty (no stars) yields ``mean_*`` of ``None``.
    """
    radius = max(2, int(radius))
    g = _green_plane(raw)
    sky, sigma = _robust_sky_sigma(g)
    threshold = sky + _DETECT_SIGMA * sigma
    ys, xs = _local_maxima(g, threshold)
    if ys.size == 0:
        return StarField(stars=(), sky_adu=sky, mean_fwhm=None, mean_eccentricity=None)

    order = np.argsort(g[ys, xs])[::-1]  # brightest first
    h, w = g.shape
    min_sep2 = float(radius * radius)
    acc_y: list[int] = []
    acc_x: list[int] = []
    stars: list[DetectedStar] = []
    for i in order:
        py, px = int(ys[i]), int(xs[i])
        if any((py - ay) ** 2 + (px - ax) ** 2 < min_sep2 for ay, ax in zip(acc_y, acc_x)):
            continue  # already have a star here
        if not _has_psf_support(g, px, py, sky, sigma, h, w):
            continue  # isolated hot pixel / cosmic ray
        star = _measure_star(g, px, py, sky, radius, h, w)
        if star is None:
            continue
        stars.append(star)
        acc_y.append(py)
        acc_x.append(px)
        if len(stars) >= max_stars:
            break

    if not stars:
        return StarField(stars=(), sky_adu=sky, mean_fwhm=None, mean_eccentricity=None)
    mean_fwhm = float(np.mean([s.fwhm for s in stars]))
    mean_ecc = float(np.mean([s.eccentricity for s in stars]))
    return StarField(
        stars=tuple(stars),
        sky_adu=sky,
        mean_fwhm=round(mean_fwhm, 2),
        mean_eccentricity=round(mean_ecc, 3),
    )


def measure_star_at(
    raw: np.ndarray, x: float, y: float, radius: int = _STAR_RADIUS, search: int | None = None
) -> StarMeasurement | None:
    """Measure the star nearest a clicked point, in green-plane coordinates.

    Snaps to the brightest pixel within ``search`` px of (x, y), then measures
    centroid/FWHM/eccentricity/HFD/SNR in an aperture of ``radius``. This is the
    "click a star → read its FWHM" path (§5). Returns ``None`` if there is no
    star-like signal near the click.

    Args:
        raw:    Raw 2-D GRBG frame.
        x, y:   Click position in **green-plane** px.
        radius: Aperture radius (green-plane px).
        search: Snap radius for the local peak. Defaults to ``_SNAP_SEARCH`` and
                is **independent of** ``radius`` so changing the aperture radius
                doesn't re-snap the centre onto a different star.
    """
    radius = max(2, int(radius))
    g = _green_plane(raw)
    h, w = g.shape
    xi, yi = int(round(x)), int(round(y))
    if not (0 <= xi < w and 0 <= yi < h):
        return None
    sky, sigma = _robust_sky_sigma(g)

    s = int(search) if search is not None else _SNAP_SEARCH
    y0, y1 = max(0, yi - s), min(h, yi + s + 1)
    x0, x1 = max(0, xi - s), min(w, xi + s + 1)
    sub = g[y0:y1, x0:x1]
    ry, rx = np.unravel_index(int(np.argmax(sub)), sub.shape)
    py, px = y0 + int(ry), x0 + int(rx)

    star = _measure_star(g, px, py, sky, radius, h, w)
    if star is None:
        return None
    peak = float(g[py, px])
    snr = (peak - sky) / sigma
    hfd = _hfd_window(g, star.x, star.y, sky, radius, h, w)
    return StarMeasurement(
        x=star.x,
        y=star.y,
        fwhm=star.fwhm,
        eccentricity=star.eccentricity,
        hfd=hfd,
        peak_adu=int(peak),
        flux=star.flux,
        snr=round(float(snr), 1),
        sky_adu=round(sky, 1),
        radius=radius,
    )


def _local_maxima(g: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (ys, xs) of 3×3 local maxima above an absolute ``threshold``."""
    above = g > threshold
    if not above.any():
        return np.array([], dtype=int), np.array([], dtype=int)
    is_max = np.ones(g.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            shifted = np.roll(np.roll(g, dy, axis=0), dx, axis=1)
            is_max &= g >= shifted
    ys, xs = np.nonzero(above & is_max)
    return ys, xs


def _has_psf_support(
    g: np.ndarray, px: int, py: int, sky: float, sigma: float, h: int, w: int
) -> bool:
    """True if the 4-connected neighbours are elevated (rejects hot pixels)."""
    vals = [
        g[py + dy, px + dx]
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
        if 0 <= py + dy < h and 0 <= px + dx < w
    ]
    if not vals:
        return False
    return (float(np.mean(vals)) - sky) > 2.0 * sigma


def _measure_star(
    g: np.ndarray, px: int, py: int, sky: float, r: int, h: int, w: int
) -> DetectedStar | None:
    """Measure centroid, FWHM and eccentricity in a circular aperture.

    A local background (median of the aperture, excluding the core) is subtracted
    before the intensity-weighted second moments, so a gradient or bright sky
    doesn't inflate the width. Returns ``None`` if the aperture carries no flux.
    """
    y0, y1 = max(0, py - r), min(h, py + r + 1)
    x0, x1 = max(0, px - r), min(w, px + r + 1)
    win = g[y0:y1, x0:x1].astype(np.float32)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist2 = (yy - py) ** 2 + (xx - px) ** 2
    aperture = dist2 <= r * r

    # Local background from the thin outer ring (r−1 … r) — far enough out that
    # the star's wing barely contaminates it, so the FWHM isn't under-measured.
    ring = win[aperture & (dist2 > (r - 1) ** 2)]
    local_bg = float(np.median(ring)) if ring.size else sky

    sub = np.where(aperture, win - local_bg, 0.0)
    np.clip(sub, 0.0, None, out=sub)
    flux = float(sub.sum())
    if flux <= 0.0:
        return None

    cx = float((xx * sub).sum() / flux)
    cy = float((yy * sub).sum() / flux)
    dx = xx - cx
    dy = yy - cy
    mxx = float((sub * dx * dx).sum() / flux)
    myy = float((sub * dy * dy).sum() / flux)
    mxy = float((sub * dx * dy).sum() / flux)

    # Eigenvalues of the 2×2 covariance → major/minor variance.
    common = 0.5 * (mxx + myy)
    diff = np.sqrt(max(0.0, (0.5 * (mxx - myy)) ** 2 + mxy * mxy))
    var_major = max(common + diff, 0.0)
    var_minor = max(common - diff, 0.0)
    sigma_mean = np.sqrt(max(0.5 * (var_major + var_minor), 0.0))
    fwhm = float(_FWHM_PER_SIGMA * sigma_mean)
    ecc = float(np.sqrt(1.0 - var_minor / var_major)) if var_major > 0 else 0.0
    return DetectedStar(
        x=cx,
        y=cy,
        flux=flux,
        fwhm=round(fwhm, 2),
        eccentricity=round(ecc, 3),
    )


def _hfd_window(
    g: np.ndarray, cx: float, cy: float, sky: float, r: int, h: int, w: int
) -> float | None:
    """Half-flux diameter in a circular aperture around (cx, cy) (green-plane px)."""
    icy, icx = int(round(cy)), int(round(cx))
    y0, y1 = max(0, icy - r), min(h, icy + r + 1)
    x0, x1 = max(0, icx - r), min(w, icx + r + 1)
    win = g[y0:y1, x0:x1].astype(np.float32) - sky
    np.clip(win, 0.0, None, out=win)
    flux = float(win.sum())
    if flux <= 0.0:
        return None
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    return round(2.0 * float((dist * win).sum() / flux), 2)


def _count_stars(g: np.ndarray, threshold: float) -> int:
    """Count 3×3 local maxima above ``threshold`` (cheap star-count proxy)."""
    above = g > threshold
    if not above.any():
        return 0
    is_max = np.ones(g.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            shifted = np.roll(np.roll(g, dy, axis=0), dx, axis=1)
            is_max &= g >= shifted
    return int(np.count_nonzero(above & is_max))
