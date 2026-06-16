"""Aperture photometry on the green plane (docs/photometry_plan.md §6 C1).

A circular aperture + a sky annulus → background-subtracted flux, instrumental
magnitude and a CCD-equation uncertainty. Pure numpy, Qt-free; coordinates are
green-plane px (the same grid as ``measure_star_at`` and the WCS).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AperturePhot:
    """One aperture measurement (instrumental, uncalibrated)."""

    flux_adu: float  # background-subtracted aperture sum
    sky_adu: float  # per-pixel sky (annulus median)
    n_pix: int  # aperture pixel count
    peak_adu: float  # brightest pixel in the aperture
    snr: float  # flux / flux_err (electrons)
    saturated: bool  # any aperture pixel at/above the linearity threshold
    inst_mag: float | None  # -2.5·log10(flux); None when flux ≤ 0
    inst_mag_err: float | None  # 1.0857·flux_err/flux; None when flux ≤ 0


def measure_aperture(
    green: np.ndarray,
    x: float,
    y: float,
    r_ap: float,
    r_in: float,
    r_out: float,
    *,
    egain: float = 1.0,
    read_noise_e: float = 1.5,
    sat_adu: float = 60000.0,
) -> AperturePhot | None:
    """Measure a star at (x, y) green px with a circular aperture + sky annulus.

    Args:
        green: 2-D green plane (float-able).
        x, y:  Centre, green px.
        r_ap:  Aperture radius (green px).
        r_in, r_out: Sky-annulus inner/outer radii (green px).
        egain: e-/ADU for the CCD-equation noise (≤0 → treated as 1).
        read_noise_e: Read noise (e- RMS) per pixel.
        sat_adu: Linearity/full-well threshold for the saturation flag.

    Returns:
        An :class:`AperturePhot`, or ``None`` if the aperture falls off the frame.
    """
    g = np.asarray(green, dtype=np.float32)
    h, w = g.shape
    r_out = max(float(r_out), float(r_ap))
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(0, xi - int(r_out) - 1), min(w, xi + int(r_out) + 2)
    y0, y1 = max(0, yi - int(r_out) - 1), min(h, yi + int(r_out) + 2)
    if x1 <= x0 or y1 <= y0:
        return None
    sub = g[y0:y1, x0:x1]
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist2 = (yy - y) ** 2 + (xx - x) ** 2
    ap = dist2 <= r_ap * r_ap
    if not ap.any():
        return None
    ann = (dist2 > r_in * r_in) & (dist2 <= r_out * r_out)

    sky_pixels = sub[ann]
    sky = float(np.median(sky_pixels)) if sky_pixels.size else 0.0
    ap_vals = sub[ap]
    n_pix = int(ap.sum())
    flux = float(ap_vals.sum()) - sky * n_pix
    peak = float(ap_vals.max())
    saturated = bool(peak >= sat_adu)

    egain = egain if egain and egain > 0 else 1.0
    flux_e = max(flux, 0.0) * egain
    sky_e = max(sky, 0.0) * egain
    var_e = flux_e + n_pix * (sky_e + read_noise_e * read_noise_e)
    flux_err_e = math.sqrt(var_e) if var_e > 0 else 0.0
    snr = (flux_e / flux_err_e) if flux_err_e > 0 else 0.0

    if flux > 0.0:
        inst_mag = -2.5 * math.log10(flux)
        inst_mag_err = (1.0857 * flux_err_e / flux_e) if flux_e > 0 else None
    else:
        inst_mag = inst_mag_err = None

    return AperturePhot(
        flux_adu=flux,
        sky_adu=sky,
        n_pix=n_pix,
        peak_adu=peak,
        snr=round(snr, 2),
        saturated=saturated,
        inst_mag=inst_mag if inst_mag is None else round(inst_mag, 4),
        inst_mag_err=inst_mag_err if inst_mag_err is None else round(inst_mag_err, 4),
    )
