"""Following the solved field from frame to frame (row A48) on core's tracker.

``ApertureTracker`` (``argos/core/photometry/tracking.py:235-339``) follows an
anchor constellation and fits the rigid transform reference -> frame. In the
Qt app only photometry used it; the web also draws every overlay, hit-tests
clicks and computes Centre and Sync through it, so a wrong lock is visible
and harmful. :class:`FieldTracker` keeps core's fit and adds (protocol.md
"Layers (A47) and the tracking transform (A48)", Tracking):

1. **a re-centred centroid**: each anchor is centroided twice, the second
   window centred on the first result (a window centred on the prediction
   lags a moving star by about one frame px);
2. **baselines from the reference**: each anchor's signal baseline (core's
   ``MIN_SIGNAL_FRACTION`` test) is measured on the solved frame, where the
   anchor is known to sit, never on the first tracked frame;
3. **a kept pose**: a rebuilt constellation (a role change) starts from the
   previous transform, not from the identity;
4. **consistent anchors only**: with three or more anchors, an update needs
   at least two matched anchors whose separations agree with the reference
   (a rigid motion keeps distances); one window that slid onto another star
   or onto noise is not a lock;
5. **health on the wire**: ``ok``, ``degraded`` or ``lost``;
6. **re-acquisition**: a lost lock is found again by matching the frame's
   detected stars to the solved frame's with a translation vote
   (:func:`vote_transform`).
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from argos.core.photometry.tracking import (
    ApertureTracker,
    RigidTransform,
    _refine_centroid_measurement,
    fit_rigid,
    fit_translation,
)

#: Two matched anchors agree when their separation differs from the
#: reference's by less than this (green px; 3 frame px). Centroids of
#: unsaturated anchors scatter by ~0.1-0.3 green px; a window locked on a
#: neighbour or on sky is several px off.
PAIR_TOL_GREEN_PX = 1.5
#: Re-acquisition: brightest stars of each list that vote.
VOTE_STARS = 80
#: Re-acquisition: a match is within this many green px of the voted pose.
VOTE_MATCH_GREEN_PX = 2.0
#: Re-acquisition: matches needed to accept the voted pose.
VOTE_MIN_MATCHES = 6

Star = tuple[float, float, float]  # x, y (green px), flux


def consistent_pairs(
    refs: Sequence[tuple[float, float]],
    meas: Sequence[tuple[float, float]],
    tol: float = PAIR_TOL_GREEN_PX,
) -> list[int]:
    """Indices of the matched anchors whose separations agree with the reference.

    An anchor is kept when it agrees with at least ``max(1, (n - 1) // 2)``
    others: a minority of wrong locks cannot carry the fit.
    """
    n = len(refs)
    if n < 2:
        return list(range(n))
    agree = [0] * n
    for i in range(n):
        for j in range(i + 1, n):
            d_ref = math.hypot(refs[i][0] - refs[j][0], refs[i][1] - refs[j][1])
            d_meas = math.hypot(meas[i][0] - meas[j][0], meas[i][1] - meas[j][1])
            if abs(d_ref - d_meas) < tol:
                agree[i] += 1
                agree[j] += 1
    need = max(1, (n - 1) // 2)
    return [i for i in range(n) if agree[i] >= need]


class FieldTracker(ApertureTracker):
    """Core's tracker with reference baselines, a kept pose and consistent anchors."""

    def __init__(
        self,
        anchors_xy: list[tuple[float, float]],
        frame_center: tuple[float, float],
        search_r: float = 8.0,
        *,
        reference_green: np.ndarray | None = None,
        pose: RigidTransform | None = None,
    ) -> None:
        super().__init__(anchors_xy, frame_center, search_r)
        if pose is not None:
            # The same pivot: the transform is expressed about the frame centre.
            self.transform = pose
        if reference_green is not None:
            ref = np.asarray(reference_green, dtype=np.float32)
            for index, (x, y) in enumerate(self._anchors):
                measured = _refine_centroid_measurement(ref, x, y, self._search_r)
                self._reference_signal[index] = measured.signal if measured else None
        self.reacquired = False

    @property
    def size(self) -> int:
        """Anchors in the constellation."""
        return len(self._anchors)

    @property
    def health(self) -> str:
        """``ok``, ``degraded`` (fewer anchors than it should have) or ``lost``."""
        if self.frames_lost > 0 or self.anchors_used == 0:
            return "lost"
        if self.anchors_used < min(3, self.size):
            return "degraded"
        return "ok"

    def update(self, green: np.ndarray, *, allow_rotation: bool = True) -> int:
        """Core's ``update`` (``tracking.py:278-339``) with the consistency rule."""
        matched_ref: list[tuple[float, float]] = []
        matched_meas: list[tuple[float, float]] = []
        for index, ref in enumerate(self._anchors):
            pred = self.transform.apply(*ref)
            meas = _refine_centroid_measurement(green, pred[0], pred[1], self._search_r)
            if meas is None:
                continue
            # A second pass centred on the first: a window centred on the
            # prediction truncates a moved star's wings and drags the
            # centroid back toward the prediction (a lag of ~1 frame px).
            again = _refine_centroid_measurement(green, meas.x, meas.y, self._search_r)
            if again is not None:
                meas = again
            baseline = self._reference_signal[index]
            if baseline is None:
                self._reference_signal[index] = meas.signal
            elif meas.signal < baseline * self.MIN_SIGNAL_FRACTION:
                self.anchors_signal_rejected += 1
                continue
            matched_ref.append(ref)
            matched_meas.append((meas.x, meas.y))

        keep = consistent_pairs(matched_ref, matched_meas)
        matched_ref = [matched_ref[i] for i in keep]
        matched_meas = [matched_meas[i] for i in keep]
        self.anchors_rejected = 0
        needed = 2 if self.size >= 3 else 1
        if len(matched_ref) < needed:
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
                self.anchors_rejected = 1
                matched_ref, matched_meas = kept_ref, kept_meas
                t, residuals = t2, res2
        self.transform = t
        self.anchors_used = len(matched_ref)
        self.residual_px = float(np.median(residuals))
        return self.anchors_used


def vote_transform(
    reference: Sequence[Star],
    current: Sequence[Star],
    prior: RigidTransform,
    *,
    allow_rotation: bool = True,
    match_px: float = VOTE_MATCH_GREEN_PX,
    min_matches: int = VOTE_MIN_MATCHES,
) -> tuple[RigidTransform, int] | None:
    """The reference -> frame transform found by matching two star lists, or None.

    The prior's rotation is kept and the translation voted: every pair of the
    brightest stars of both lists casts one vote for their offset; the peak is
    refined by a rigid (or translation-only) fit on the matched stars.
    """
    if len(reference) < min_matches or len(current) < min_matches:
        return None
    ref = np.asarray(sorted(reference, key=lambda s: -s[2])[:VOTE_STARS], dtype=np.float64)
    cur = np.asarray(sorted(current, key=lambda s: -s[2])[:VOTE_STARS], dtype=np.float64)
    c, s = math.cos(prior.theta_rad), math.sin(prior.theta_rad)
    rx = prior.cx + c * (ref[:, 0] - prior.cx) - s * (ref[:, 1] - prior.cy)
    ry = prior.cy + s * (ref[:, 0] - prior.cx) + c * (ref[:, 1] - prior.cy)
    dx = (cur[None, :, 0] - rx[:, None]).ravel()
    dy = (cur[None, :, 1] - ry[:, None]).ravel()
    span_x = max(float(np.ptp(np.r_[rx, cur[:, 0]])), 1.0)
    span_y = max(float(np.ptp(np.r_[ry, cur[:, 1]])), 1.0)
    bin_px = 2.0 * match_px
    hist, xe, ye = np.histogram2d(
        dx,
        dy,
        bins=(max(1, int(2 * span_x / bin_px)), max(1, int(2 * span_y / bin_px))),
        range=[[-span_x, span_x], [-span_y, span_y]],
    )
    i, j = np.unravel_index(int(hist.argmax()), hist.shape)
    if hist[i, j] < min_matches // 2:
        return None
    tx, ty = (xe[i] + xe[i + 1]) / 2.0, (ye[j] + ye[j + 1]) / 2.0
    transform = RigidTransform(prior.theta_rad, tx, ty, prior.cx, prior.cy)
    all_ref = np.asarray(reference, dtype=np.float64)[:, :2]
    all_cur = np.asarray(current, dtype=np.float64)[:, :2]
    tolerance = 1.5 * bin_px
    count = 0
    for _ in range(3):
        src, dst = _nearest_pairs(all_ref, all_cur, transform, tolerance)
        count = len(src)
        if count < min_matches:
            return None
        fit = fit_rigid if allow_rotation else fit_translation
        transform = fit(src, dst, prior.cx, prior.cy)
        tolerance = match_px
    src, _dst = _nearest_pairs(all_ref, all_cur, transform, match_px)
    count = len(src)
    return (transform, count) if count >= min_matches else None


def _nearest_pairs(ref, cur, transform, tolerance):
    """Unique nearest-neighbour pairs (reference, current) within *tolerance*."""
    c, s = math.cos(transform.theta_rad), math.sin(transform.theta_rad)
    px = transform.cx + c * (ref[:, 0] - transform.cx) - s * (ref[:, 1] - transform.cy)
    py = transform.cy + s * (ref[:, 0] - transform.cx) + c * (ref[:, 1] - transform.cy)
    px += transform.tx
    py += transform.ty
    src: list[tuple[float, float]] = []
    dst: list[tuple[float, float]] = []
    used: set[int] = set()
    for k in range(len(ref)):
        d = np.hypot(cur[:, 0] - px[k], cur[:, 1] - py[k])
        nearest = int(d.argmin())
        if d[nearest] < tolerance and nearest not in used:
            used.add(nearest)
            src.append((float(ref[k, 0]), float(ref[k, 1])))
            dst.append((float(cur[nearest, 0]), float(cur[nearest, 1])))
    return src, dst
