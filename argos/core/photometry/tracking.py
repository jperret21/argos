"""Aperture tracking across saved frames — field-rotation / drift correction.

A single reference plate solve is only valid at the instant it was made: on an
alt-az mount the field rotates around the frame centre for the rest of the
session, and any mount drifts. Rather than model the rotation from time + site
(parity and clock pitfalls), measure it: each frame, re-centroid the anchor
stars in a small window around their predicted positions, fit the rigid
transform (rotation + translation, no scale) that maps the *reference*
positions onto the measured ones, and use it to place every aperture. The
transform is re-fit from the reference geometry on every frame — prediction
only seeds the search windows — so centroid noise never accumulates, while
consecutive subs rotate by well under a pixel so the windows never lose their
star.

``measure_targets()`` only needs ``world_to_pixel_deg`` from its ``wcs``
argument, so :class:`TrackedWCS` wraps the reference solve and applies the
current transform after projection — the measurement core stays untouched.

S69: each window's centroid is re-centred on itself until it converges, then
refined in a small window (:func:`refine_centroid`). One centroid in a window
centred on the prediction kept 30-80 % of the prediction error (the clipped sky
noise of the whole window and the truncated wings of a moved star pull it to
the window's centre), so on a field rotating 0.7° per sub the fit lagged the
field by about 1° (XX Cyg 2026-09-07: 15.37° found against ASTAP's 16.49°,
comparisons 4-8.5 px off their apertures). Two safety nets follow the fit: a
re-solve is due once the tracked rotation since the solution exceeds
:data:`RESOLVE_ROTATION_DEG`, and a comparison or check star whose centroid is
more than :data:`CENTRING_MAX_PX` from its aperture centre is left out of the
frame's ensemble (:func:`centring_offsets`).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

#: S69: a centroid is re-centred on itself until it moves less than this (green px),
#: at most ``_CENTROID_MAX_PASSES`` times per radius.
_CENTROID_CONVERGED_PX = 0.01
_CENTROID_MAX_PASSES = 10
#: S69: the radius (green px) of the last re-centred passes: about two FWHM of the
#: owner's stars (1.7-2.3 green px), so a neighbour 7 px away (XX Cyg's 000-BJV-169
#: and 000-BJV-173) no longer drags the centroid as it does in the search window.
CENTROID_FINE_R_PX = 4.0
#: S69 (a): a re-solve is due when the tracked rotation since the solution exceeds
#: this (degrees). The tracker's rigid fit carries a solution's geometry across the
#: field; past a few degrees its error at the field's edge reaches the 1 px of (b).
RESOLVE_ROTATION_DEG = 2.0
#: S69 (b): a comparison or check star whose centroid is more than this many green
#: px from its aperture centre is left out of the frame's ensemble.
CENTRING_MAX_PX = 1.0
#: S69 (b): only a star seen at this SNR (S35's threshold) is tested: the centroid
#: of a fainter one scatters by about 1.6/SNR px per axis in its aperture, so the
#: 1 px test would leave it out on noise alone.
CENTRING_MIN_SNR = 5.0
#: S69: a star of the set with at least this fraction of another's flux is that
#: star's neighbour. A re-centred centroid climbs onto a neighbour inside its window
#: (XX Cyg 2026-09-07: 000-BJV-173's window ended on 000-BJV-169, 4.9 times brighter
#: and 6.9 green px away); a neighbour under a quarter of the flux pulls it by less
#: than a fifth of their distance, and the 4 px window then leaves it out.
NEIGHBOUR_FLUX_FRACTION = 0.25
#: S69: the largest motion of a set star between two subs seen on the owner's runs
#: (XX Cyg 2026-09-07 at 0.7° per sub: 4.2-7.5 green px), rounded up. An anchor's
#: window, centred on its prediction, reaches a neighbour up to the search radius
#: plus this from the star.
ANCHOR_MOTION_PX = 8.0
#: S69 (b): the centring centroid of a star with a neighbour is taken in a window of
#: this fraction of their distance (the neighbour's core stays outside it); a star
#: whose window would be under ``CENTRING_MIN_WINDOW_PX`` is blended with its
#: neighbour and is not tested.
CENTRING_NEIGHBOUR_FRACTION = 0.45
CENTRING_MIN_WINDOW_PX = 2.0
#: S69 (b): the centring centroid is one centroid in the aperture radius (it finds a
#: star up to the aperture's edge), then re-centred in a window of this radius (green
#: px, 3σ of the owner's stars). Re-centred in the aperture radius, the window of a
#: star near SNR 5 wandered onto noise or an uncatalogued star (XX Cyg 2026-08-29
#: 000-BJV-178, frame 5: 2.68 px where a Gaussian fit puts it 0.08 px from its
#: aperture centre).
CENTRING_WINDOW_PX = 3.0


def tracker_search_r(params) -> float:
    """The tracker's centroid search radius (green px) for ``params``: twice the
    default aperture, at least 8 px (the live, sequence and re-run trackers')."""
    return max(8.0, 2.0 * params.aperture_px(None))


#: S69: a star's brightness for the neighbour rule is its sky-subtracted flux within
#: this radius (green px) of its position: 90 % of a star of the owner's FWHM, and
#: nothing of a neighbour 4.4 px away or more (the aperture's flux, 5.45 px, holds
#: 30 % of 000-BJV-169's light at 000-BJV-173's position).
CORE_FLUX_R_PX = 2.0


def _measured(green, wcs, stars, params, r_ap: float):
    """Each star of ``stars`` with its position through ``wcs``, its aperture
    measurement there (None outside the frame) and its core flux (S69, within
    :data:`CORE_FLUX_R_PX`): ``(star, x, y, phot, core)``."""
    from argos.core.photometry.aperture import measure_aperture

    r_in = max(params.annulus_in_px, r_ap + 1.0)
    r_out = max(params.annulus_out_px, r_in + 2.0)
    out = []
    for star in stars:
        x, y = (float(v) for v in wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg))
        phot = None
        if math.isfinite(x) and math.isfinite(y):
            phot = measure_aperture(
                green,
                x,
                y,
                r_ap,
                r_in,
                r_out,
                egain=params.egain,
                read_noise_e=params.read_noise_e,
                sat_adu=params.sat_adu,
                black_adu=params.black_adu,
                plane_pixels=params.plane_pixels,
            )
        core = _core_flux(green, x, y, phot.sky_adu) if phot is not None else None
        out.append((star, x, y, phot, core))
    return out


def _core_flux(green: np.ndarray, x: float, y: float, sky: float) -> float | None:
    """Sky-subtracted flux within :data:`CORE_FLUX_R_PX` of ``(x, y)`` (None off the frame)."""
    h, w = green.shape
    ri = int(math.ceil(CORE_FLUX_R_PX))
    px, py = int(round(x)), int(round(y))
    y0, y1, x0, x1 = py - ri, py + ri + 1, px - ri, px + ri + 1
    if y0 < 0 or x0 < 0 or y1 > h or x1 > w:
        return None
    yy, xx = np.mgrid[y0:y1, x0:x1]
    disc = (yy - y) ** 2 + (xx - x) ** 2 <= CORE_FLUX_R_PX**2
    return float((green[y0:y1, x0:x1].astype(np.float64)[disc] - sky).sum())


def neighbour_distance(star, x: float, y: float, core: float | None, neighbours) -> float:
    """S69: distance (green px) from ``(x, y)`` to the nearest other star of
    ``neighbours`` (``_measured`` tuples) whose core flux is at least
    :data:`NEIGHBOUR_FLUX_FRACTION` of ``core`` (any star with a positive core flux
    when ``core`` is unknown or not positive); ``inf`` when there is none. A star of
    the set within 1 px is the same star under another identity, not a neighbour."""
    key = star.key()
    best = math.inf
    for other, ox, oy, _phot, other_core in neighbours:
        if other.key() == key or other_core is None or not other_core > 0:
            continue
        if core is not None and core > 0 and other_core < NEIGHBOUR_FLUX_FRACTION * core:
            continue
        distance = math.hypot(ox - x, oy - y)
        if distance < CENTRING_MAX_PX:
            continue  # the same star listed twice (two identities), not a neighbour
        best = min(best, distance)
    return best


def select_tracking_anchors(
    green,
    wcs,
    candidates,
    params,
    *,
    min_snr: float = 10.0,
    max_anchors: int = 6,
    neighbours=None,
    isolation_px: float | None = None,
):
    """Return only bright, clean stars suitable for geometric tracking.

    The tracking constellation is deliberately distinct from the photometric
    ensemble.  A reference can be meaningful after offline calibration yet be
    too weak to centroid in a raw live sub; such a source must never steer the
    WCS transform.

    S69: a candidate with a neighbour among ``neighbours`` (the set's stars;
    default ``candidates``) holding at least a quarter of its core flux within
    ``isolation_px`` (default: the search radius plus :data:`ANCHOR_MOTION_PX`) is
    left out: its window, re-centred until it converges, ends on that neighbour, and
    the fit spends its one rejection on it every frame.
    """
    r_ap = params.aperture_px(None)
    measured = _measured(green, wcs, candidates, params, r_ap)
    if neighbours is None:
        others = measured
    else:
        others = _measured(green, wcs, neighbours, params, r_ap)
    reach = tracker_search_r(params) + ANCHOR_MOTION_PX if isolation_px is None else isolation_px
    qualified: list[tuple[float, object]] = []
    for star, x, y, phot, core in measured:
        if phot is None or phot.saturated or phot.suspect or phot.snr < min_snr:
            continue
        if neighbour_distance(star, x, y, core, others) <= reach:
            continue
        qualified.append((phot.snr, star))
    qualified.sort(key=lambda item: item[0], reverse=True)
    return [star for _snr, star in qualified[:max_anchors]]


def anchors_seen(green, wcs, stars, params, *, min_snr: float = 5.0) -> int:
    """How many of ``stars`` show a star (SNR >= ``min_snr``) where ``wcs`` places them.

    The independent check of a tracker's lock (S43): after a pointing jump
    larger than the search radius, the tracker's windows centroid on noise or
    on a neighbour and still report anchors, but its transform keeps the
    apertures on blank sky, where an aperture measures no star.
    """
    from argos.core.photometry.aperture import measure_aperture

    r_ap = params.aperture_px(None)
    r_in = max(params.annulus_in_px, r_ap + 1.0)
    r_out = max(params.annulus_out_px, r_in + 2.0)
    seen = 0
    for star in stars:
        x, y = wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
        phot = measure_aperture(
            green,
            float(x),
            float(y),
            r_ap,
            r_in,
            r_out,
            egain=params.egain,
            read_noise_e=params.read_noise_e,
            sat_adu=params.sat_adu,
            black_adu=params.black_adu,
            plane_pixels=params.plane_pixels,
        )
        if phot is not None and phot.snr >= min_snr:
            seen += 1
    return seen


def refine_centroid(green: np.ndarray, x: float, y: float, r: float) -> tuple[float, float] | None:
    """The star's centroid found within radius ``r`` of ``(x, y)``, or None.

    A local background (median of the window's outer ring) is subtracted first
    so sky level and gradients don't pull the centroid. Returns None when the
    window falls outside the frame, carries no flux, or the centroid lands
    outside the search radius (no star there — clouds, or the prediction is
    already lost).

    S69: the window is re-centred on its centroid until it converges, then in a
    :data:`CENTROID_FINE_R_PX` window (:func:`_converged_centroid_measurement`):
    a single centroid stays 30-80 % of the way to the window's centre.
    """
    measurement = _converged_centroid_measurement(green, x, y, r)
    return (measurement.x, measurement.y) if measurement is not None else None


@dataclass(frozen=True)
class _CentroidMeasurement:
    """Centroid plus its local background-subtracted signal (internal)."""

    x: float
    y: float
    signal: float


def _refine_centroid_measurement(
    green: np.ndarray, x: float, y: float, r: float
) -> _CentroidMeasurement | None:
    """Centroid with the signal used to reject a lost anchor locking on noise."""
    h, w = green.shape
    px, py = int(round(x)), int(round(y))
    ri = max(2, int(math.ceil(r)))
    y0, y1 = py - ri, py + ri + 1
    x0, x1 = px - ri, px + ri + 1
    if y0 < 0 or x0 < 0 or y1 > h or x1 > w:
        return None

    win = green[y0:y1, x0:x1].astype(np.float32)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist2 = (yy - y) ** 2 + (xx - x) ** 2
    aperture = dist2 <= r * r
    ring = win[aperture & (dist2 > (r - 1.0) ** 2)]
    if ring.size == 0:
        return None
    local_bg = float(np.median(ring))

    sub = np.where(aperture, win - local_bg, 0.0)
    np.clip(sub, 0.0, None, out=sub)
    flux = float(sub.sum())
    if flux <= 0.0:
        return None

    cx = float((xx * sub).sum() / flux)
    cy = float((yy * sub).sum() / flux)
    if (cx - x) ** 2 + (cy - y) ** 2 > r * r:
        return None
    return _CentroidMeasurement(cx, cy, flux)


def _converged_centroid_position(
    green: np.ndarray, x: float, y: float, r: float, fine_r: float = CENTROID_FINE_R_PX
) -> _CentroidMeasurement | None:
    """S69: the centroid re-centred on itself, first in the ``r`` window, then in a
    ``fine_r`` one, each until it moves less than ``_CENTROID_CONVERGED_PX``.

    The first window's centroid keeps the signal (the tracker's lost-anchor test
    compares it with the anchor's first one). None when that first window finds
    nothing; a later window that leaves the frame or finds no flux ends the passes
    at the last centroid. The result may lie further than ``r`` from ``(x, y)``.

    Why: the background-subtracted flux is clipped at zero, so the sky noise of the
    whole window adds a positive flux centred on the window, and a window centred on
    a prediction truncates a moved star's wings. Both pull a single centroid toward
    the window's centre: on XX Cyg 2026-09-07 it kept 30-80 % of the prediction
    error, and the tracker lagged the rotating field by about 1°. Re-centred on
    itself, the window ends centred on the star, where both pulls cancel.
    """
    first = _refine_centroid_measurement(green, x, y, r)
    if first is None:
        return None
    cx, cy = first.x, first.y
    for radius in (r, min(fine_r, r)):
        for _ in range(_CENTROID_MAX_PASSES):
            again = _refine_centroid_measurement(green, cx, cy, radius)
            if again is None:
                break
            moved = math.hypot(again.x - cx, again.y - cy)
            cx, cy = again.x, again.y
            if moved < _CENTROID_CONVERGED_PX:
                break
    return _CentroidMeasurement(cx, cy, first.signal)


def _converged_centroid_measurement(
    green: np.ndarray, x: float, y: float, r: float, fine_r: float = CENTROID_FINE_R_PX
) -> _CentroidMeasurement | None:
    """:func:`_converged_centroid_position`, or None when it lands further than ``r``
    from ``(x, y)`` (no star of that window: the search radius stays the limit)."""
    measurement = _converged_centroid_position(green, x, y, r, fine_r)
    if measurement is None or (measurement.x - x) ** 2 + (measurement.y - y) ** 2 > r * r:
        return None
    return measurement


def centring_offsets(
    green: np.ndarray,
    wcs,
    stars,
    params,
    *,
    fwhm: float | None,
    min_snr: float = CENTRING_MIN_SNR,
    neighbours=None,
) -> dict[str, float]:
    """S69 (b): how far (green px) each star's centroid is from its aperture centre.

    For every star of ``stars`` seen where ``wcs`` places it (aperture SNR >=
    ``min_snr``, unsaturated, no hot pixel), the distance between that position and
    the star's centroid found within the aperture radius (:func:`refine_centroid`;
    ``inf`` when it leaves the aperture). Keyed by ``star.key()``; a star not seen
    is not tested (its centroid is noise). A star more than :data:`CENTRING_MAX_PX`
    off is left out of the frame's ensemble (``measure_targets(exclude=...)``).

    A star with a neighbour among ``neighbours`` (the set's stars; default
    ``stars``) holding at least a quarter of its core flux has its centroid taken within
    :data:`CENTRING_NEIGHBOUR_FRACTION` of their distance, so the neighbour cannot
    pull it out of its aperture (XX Cyg 2026-09-07: 000-BJV-173, 6.9 px from
    000-BJV-169, was reported off-centre on 7 of 24 frames while 0.03-0.20 px from
    its aperture centre); one closer than :data:`CENTRING_MIN_WINDOW_PX` /
    :data:`CENTRING_NEIGHBOUR_FRACTION` is blended with it and not tested. The
    centroid is re-centred in :data:`CENTRING_WINDOW_PX` only
    (:func:`_centring_centroid`).
    """
    r_ap = params.aperture_px(fwhm)
    measured = _measured(green, wcs, stars, params, r_ap)
    others = measured if neighbours is None else _measured(green, wcs, neighbours, params, r_ap)
    offsets: dict[str, float] = {}
    for star, x, y, phot, core in measured:
        if phot is None or phot.saturated or phot.suspect or phot.snr < min_snr:
            continue
        near = neighbour_distance(star, x, y, core, others)
        window = min(r_ap, CENTRING_NEIGHBOUR_FRACTION * near)
        if window < CENTRING_MIN_WINDOW_PX:
            continue  # blended with its neighbour: no centroid of its own
        found = _centring_centroid(green, x, y, window, min(window, CENTRING_WINDOW_PX))
        if found is None:
            continue  # the window leaves the frame: measure_aperture has no star either
        offset = math.hypot(found[0] - x, found[1] - y)
        offsets[star.key()] = offset if offset <= r_ap else math.inf
    return offsets


def _centring_centroid(
    green: np.ndarray, x: float, y: float, r: float, fine_r: float
) -> tuple[float, float] | None:
    """S69 (b): one centroid within ``r`` of ``(x, y)``, then re-centred on itself in a
    ``fine_r`` window until it converges; None when the first window finds nothing."""
    first = _refine_centroid_measurement(green, x, y, r)
    if first is None:
        return None
    cx, cy = first.x, first.y
    for _ in range(_CENTROID_MAX_PASSES):
        again = _refine_centroid_measurement(green, cx, cy, fine_r)
        if again is None:
            break
        moved = math.hypot(again.x - cx, again.y - cy)
        cx, cy = again.x, again.y
        if moved < _CENTROID_CONVERGED_PX:
            break
    return cx, cy


def off_centre(offsets: dict[str, float], max_px: float = CENTRING_MAX_PX) -> frozenset[str]:
    """S69 (b): the keys of :func:`centring_offsets` more than ``max_px`` off."""
    return frozenset(key for key, offset in offsets.items() if offset > max_px)


def rotation_resolve_due(rotation_deg: float, attempted_deg: float | None = None) -> bool:
    """S69 (a): the tracked rotation since the solution calls for a re-solve.

    ``attempted_deg``: the rotation at which the last re-solve for rotation failed
    (no solution, or refused): the next attempt waits until the field has turned
    another :data:`RESOLVE_ROTATION_DEG`, so a solver that keeps failing costs one
    attempt per 2° of field rotation, never one per frame.
    """
    turned = abs(rotation_deg)
    if turned <= RESOLVE_ROTATION_DEG:
        return False
    return attempted_deg is None or turned > abs(attempted_deg) + RESOLVE_ROTATION_DEG


@dataclass(frozen=True)
class RigidTransform:
    """2D rotation by ``theta_rad`` about ``(cx, cy)`` followed by ``(tx, ty)``."""

    theta_rad: float
    tx: float
    ty: float
    cx: float
    cy: float

    @classmethod
    def identity(cls, cx: float, cy: float) -> "RigidTransform":
        return cls(0.0, 0.0, 0.0, cx, cy)

    def apply(self, x: float, y: float) -> tuple[float, float]:
        c, s = math.cos(self.theta_rad), math.sin(self.theta_rad)
        dx, dy = x - self.cx, y - self.cy
        return (
            self.cx + c * dx - s * dy + self.tx,
            self.cy + s * dx + c * dy + self.ty,
        )

    def invert(self, x: float, y: float) -> tuple[float, float]:
        """Map a current-frame point back into the reference frame."""
        c, s = math.cos(self.theta_rad), math.sin(self.theta_rad)
        # Undo the post-rotation translation, then rotate by -theta around
        # the same pivot.  This is the inverse of :meth:`apply`.
        dx, dy = x - self.cx - self.tx, y - self.cy - self.ty
        return self.cx + c * dx + s * dy, self.cy - s * dx + c * dy

    @property
    def rotation_deg(self) -> float:
        return math.degrees(self.theta_rad)

    @property
    def shift_px(self) -> float:
        return math.hypot(self.tx, self.ty)


def fit_rigid(
    src: list[tuple[float, float]],
    dst: list[tuple[float, float]],
    cx: float,
    cy: float,
) -> RigidTransform:
    """Least-squares rotation+translation mapping ``src`` → ``dst`` (no scale).

    Closed-form orthogonal Procrustes on the centred point sets. With a single
    pair the rotation is indeterminate, so it degrades to pure translation.
    ``(cx, cy)`` is only the pivot the result is expressed about (any rigid
    transform can be written about any pivot); it does not affect the fit.
    """
    if len(src) != len(dst) or not src:
        raise ValueError("fit_rigid needs matched, non-empty point lists")

    sx = np.array([p[0] for p in src], dtype=np.float64)
    sy = np.array([p[1] for p in src], dtype=np.float64)
    dx = np.array([p[0] for p in dst], dtype=np.float64)
    dy = np.array([p[1] for p in dst], dtype=np.float64)

    if len(src) == 1:
        theta = 0.0
    else:
        psx, psy = sx - sx.mean(), sy - sy.mean()
        pdx, pdy = dx - dx.mean(), dy - dy.mean()
        theta = math.atan2(
            float((psx * pdy - psy * pdx).sum()),
            float((psx * pdx + psy * pdy).sum()),
        )

    # Translation: what's left after rotating the source about the pivot.
    c, s = math.cos(theta), math.sin(theta)
    rx = cx + c * (sx - cx) - s * (sy - cy)
    ry = cy + s * (sx - cx) + c * (sy - cy)
    return RigidTransform(
        theta_rad=theta,
        tx=float((dx - rx).mean()),
        ty=float((dy - ry).mean()),
        cx=cx,
        cy=cy,
    )


def fit_translation(
    src: list[tuple[float, float]],
    dst: list[tuple[float, float]],
    cx: float,
    cy: float,
) -> RigidTransform:
    """Least-squares translation-only mapping from ``src`` to ``dst``.

    An equatorial mount has no field rotation, but it can still have small
    guide/periodic drift.  Constraining this fit prevents centroid noise from
    inventing a rotation and moving apertures at the edges of the sensor.
    """
    if len(src) != len(dst) or not src:
        raise ValueError("fit_translation needs matched, non-empty point lists")
    return RigidTransform(
        theta_rad=0.0,
        tx=float(np.mean([dx - sx for (sx, _sy), (dx, _dy) in zip(src, dst)])),
        ty=float(np.mean([dy - sy for (_sx, sy), (_dx, dy) in zip(src, dst)])),
        cx=cx,
        cy=cy,
    )


class ApertureTracker:
    """Follow a fixed star geometry through a time-ordered frame sequence.

    Args:
        anchors_xy: Reference pixel positions (green px) of the anchor stars —
            comparisons/checks: bright and astrometrically stable. (A variable's
            position is stable too, but its centroid gets noisy at minimum.)
        frame_center: Pivot the transform is expressed about, ``(cx, cy)``.
        search_r: Centroid search radius in px. Must exceed the worst-case
            per-frame motion (sub-pixel) plus prediction error; the default is
            generous without risking a lock onto a neighbouring star.
    """

    #: The worst anchor is only examined when its residual exceeds this floor
    #: (px) — centroid noise on a faint anchor must never trigger a rejection.
    RESIDUAL_FLOOR_PX = 2.0
    #: …and it is dropped only when refitting without it shrinks the median
    #: residual below this fraction of the original. A residuals-vs-threshold
    #: test can't work here: a least-squares rigid fit smears a lone outlier's
    #: error over *all* anchors, so with 3-4 anchors the outlier's own residual
    #: never stands out. The leave-worst-out improvement is decisive instead.
    REJECT_IMPROVEMENT = 0.3
    #: A real guide star can dim in cloud, but not by an order of magnitude
    #: between consecutive science frames.  Below this fraction of its first
    #: measured signal, a centroid is almost certainly a noise/hot-pixel lock.
    MIN_SIGNAL_FRACTION = 0.20

    def __init__(
        self,
        anchors_xy: list[tuple[float, float]],
        frame_center: tuple[float, float],
        search_r: float = 8.0,
    ) -> None:
        self._anchors = [(float(x), float(y)) for x, y in anchors_xy]
        self._reference_signal: list[float | None] = [None] * len(self._anchors)
        self._search_r = float(search_r)
        self.transform = RigidTransform.identity(*frame_center)
        self.anchors_used = 0
        self.anchors_rejected = 0  # dropped by the last residual clip
        #: S69: the index (in ``anchors_xy``) of the anchor that clip dropped, or None.
        self.rejected_anchor: int | None = None
        self.anchors_signal_rejected = 0  # measurements rejected as a lost anchor
        self.residual_px = 0.0  # median |fit − measured| of the kept anchors
        self.frames_lost = 0  # consecutive frames with no anchor found

    @property
    def anchor_count(self) -> int:
        """Anchor stars the tracker was built with (0: none was seen)."""
        return len(self._anchors)

    def update(self, green: np.ndarray, *, allow_rotation: bool = True) -> int:
        """Re-fit the transform on one frame; returns anchors matched.

        On zero matches (clouds, slew glitch) the previous transform is kept —
        the next frame's windows still sit where the stars were last seen.
        With ≥3 matches, the worst-fitting anchor is dropped (P8) when its
        residual exceeds RESIDUAL_FLOOR_PX *and* refitting without it improves
        the median residual by REJECT_IMPROVEMENT — one wrong lock (hot pixel,
        neighbouring star) must not skew every aperture of the frame.

        ``allow_rotation=False`` is for an EQ mount: it retains the genuine
        frame translation while forbidding a spurious rotation fit.
        """
        matched_ref: list[tuple[float, float]] = []
        matched_meas: list[tuple[float, float]] = []
        matched_index: list[int] = []
        for index, ref in enumerate(self._anchors):
            pred = self.transform.apply(*ref)
            # S69: re-centred until it converges (a single window lagged the field).
            meas = _converged_centroid_measurement(green, pred[0], pred[1], self._search_r)
            if meas is not None:
                baseline = self._reference_signal[index]
                if baseline is None:
                    self._reference_signal[index] = meas.signal
                elif meas.signal < baseline * self.MIN_SIGNAL_FRACTION:
                    self.anchors_signal_rejected += 1
                    continue
                matched_ref.append(ref)
                matched_meas.append((meas.x, meas.y))
                matched_index.append(index)

        self.anchors_rejected = 0
        self.rejected_anchor = None
        if not matched_ref:
            self.anchors_used = 0
            self.frames_lost += 1
            return 0
        self.frames_lost = 0

        fit = fit_rigid if allow_rotation else fit_translation
        t = fit(matched_ref, matched_meas, self.transform.cx, self.transform.cy)
        residuals = self._residuals(t, matched_ref, matched_meas)

        if len(matched_ref) >= 3 and max(residuals) > self.RESIDUAL_FLOOR_PX:
            worst = int(np.argmax(residuals))
            kept_ref = matched_ref[:worst] + matched_ref[worst + 1 :]
            kept_meas = matched_meas[:worst] + matched_meas[worst + 1 :]
            t2 = fit(kept_ref, kept_meas, self.transform.cx, self.transform.cy)
            res2 = self._residuals(t2, kept_ref, kept_meas)
            if float(np.median(res2)) < self.REJECT_IMPROVEMENT * float(np.median(residuals)):
                logger.warning(
                    "Tracker: anchor at (%.0f, %.0f) rejected (%.1f px off the "
                    "consensus of the other %d) — refit",
                    matched_ref[worst][0],
                    matched_ref[worst][1],
                    residuals[worst],
                    len(kept_ref),
                )
                self.anchors_rejected = 1
                self.rejected_anchor = matched_index[worst]
                matched_ref, matched_meas = kept_ref, kept_meas
                t, residuals = t2, res2

        self.transform = t
        self.anchors_used = len(matched_ref)
        self.residual_px = float(np.median(residuals))
        return self.anchors_used

    @staticmethod
    def _residuals(t: RigidTransform, refs, meas) -> list[float]:
        return [
            math.hypot(m[0] - t.apply(*r)[0], m[1] - t.apply(*r)[1]) for r, m in zip(refs, meas)
        ]


class TrackedWCS:
    """Reference solve + live rigid correction, quacking like a FrameWCS.

    It preserves both directions of the :class:`FrameWCS` interface.  Catalogue
    overlays use ``world_to_pixel_deg``; field-geometry code needs the inverse
    direction to recover the current frame centre.
    """

    def __init__(self, wcs, tracker: ApertureTracker) -> None:
        self._wcs = wcs
        self._tracker = tracker

    def world_to_pixel_deg(self, ra_deg: float, dec_deg: float) -> tuple[float, float]:
        x, y = self._wcs.world_to_pixel_deg(ra_deg, dec_deg)
        return self._tracker.transform.apply(float(x), float(y))

    def pixel_to_radec(self, x: float, y: float) -> tuple[float, float]:
        reference_x, reference_y = self._tracker.transform.invert(float(x), float(y))
        return self._wcs.pixel_to_radec(reference_x, reference_y)

    @property
    def rotation_deg(self) -> float:
        """The tracked rotation since the solution under it (S69 a): this tracker's,
        plus that of a tracked solution it was rebuilt on (a set change, S52)."""
        inner = self._wcs.rotation_deg if isinstance(self._wcs, TrackedWCS) else 0.0
        return self._tracker.transform.rotation_deg + inner
