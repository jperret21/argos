"""Many star measurements on one frame, with the core's exact results.

``measure_star_at`` (``metrics.py:225-276``) builds the green plane and its
robust sky of the **whole** frame on every call: right for one click, but a
field's VSP sequence (often 50-100 stars) then costs seconds on a 3840 x
2160 Seestar frame. :class:`FrameMeasurer` computes the plane and the sky
once and runs the same snap and measurement (the core's private
``_measure_star`` and ``_hfd_window``), so every number is identical to
``measure_star_at`` (``tests/server/test_field_units.py`` checks it).
"""

from __future__ import annotations

import numpy as np

from argos.core.imaging import metrics
from argos.core.imaging.green import green_plane
from argos.core.imaging.metrics import StarMeasurement


class FrameMeasurer:
    """``measure_star_at`` for many positions of one raw frame (green px)."""

    def __init__(self, raw: np.ndarray) -> None:
        self.raw = raw
        self.green = green_plane(raw)
        self.sky, self.sigma = metrics._robust_sky_sigma(self.green)

    def measure_star_at(
        self, x: float, y: float, radius: int = 5, search: int | None = None
    ) -> StarMeasurement | None:
        """Same body as ``metrics.measure_star_at`` (``metrics.py:244-276``)."""
        radius = max(2, int(radius))
        g = self.green
        h, w = g.shape
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= xi < w and 0 <= yi < h):
            return None
        sky, sigma = self.sky, self.sigma
        s = int(search) if search is not None else metrics._SNAP_SEARCH
        y0, y1 = max(0, yi - s), min(h, yi + s + 1)
        x0, x1 = max(0, xi - s), min(w, xi + s + 1)
        sub = g[y0:y1, x0:x1]
        ry, rx = np.unravel_index(int(np.argmax(sub)), sub.shape)
        py, px = y0 + int(ry), x0 + int(rx)
        star = metrics._measure_star(g, px, py, sky, radius, h, w)
        if star is None:
            return None
        peak = float(g[py, px])
        snr = (peak - sky) / sigma
        hfd = metrics._hfd_window(g, star.x, star.y, sky, radius, h, w)
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
