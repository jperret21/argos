"""The single source of truth for differential-photometry parameters (WS7).

Both the live path (``AcquisitionEngine._measure_photometry``) and the offline
batch worker (``PhotometryBatchWorker``) build their measurement inputs here, so
the *physics* is provably identical: config keys ``photometry.*`` / ``camera.*``
are the only knobs, and the FWHM-adaptive aperture is computed the same way in
both. Qt-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from argos.core.catalog.targets import TargetSet
from argos.core.photometry.session import TargetResult, measure_targets

#: Fallback FWHM (green px) when a frame's FWHM is unknown (batch re-run of a
#: saved sub, which carries no measured FWHM on disk). The aperture then floors
#: to ``aperture_min_px``.
DEFAULT_FWHM = 3.0


@dataclass(frozen=True)
class PhotometryParams:
    """Config-derived aperture/annulus/band/noise inputs to ``measure_targets``.

    Built once from config; the FWHM-adaptive aperture radius is resolved
    per-frame by :meth:`for_fwhm`.
    """

    aperture_min_px: float
    aperture_fwhm_mult: float
    annulus_in_px: float
    annulus_out_px: float
    egain: float
    read_noise_e: float
    sat_adu: float
    band: str
    min_comps: int

    @classmethod
    def from_config(
        cls, cfg: Callable[[str, object], object], egain: float = 1.0
    ) -> "PhotometryParams":
        """Build from a ``cfg(key, default)`` accessor (the engine's ``_cfg``).

        ``egain`` (e-/ADU) is resolved by the caller — live from the connected
        driver/gain table, batch from the config table — since only the caller
        knows the frame's gain. Everything else is config-keyed.
        """
        return cls(
            aperture_min_px=float(cfg("photometry.aperture_min_px", 4)),
            aperture_fwhm_mult=float(cfg("photometry.aperture_fwhm_mult", 2.5)),
            annulus_in_px=float(cfg("photometry.annulus_in_px", 8)),
            annulus_out_px=float(cfg("photometry.annulus_out_px", 12)),
            egain=float(egain) if egain else 1.0,
            read_noise_e=float(cfg("photometry.read_noise_e", 1.5)),
            sat_adu=float(cfg("camera.linearity_max_adu", 50000)),
            band=str(cfg("photometry.default_band", "TG") or "TG"),
            min_comps=int(cfg("photometry.min_comparisons", 2)),
        )

    def aperture_px(self, fwhm: float | None) -> float:
        """FWHM-adaptive aperture radius, floored at ``aperture_min_px``."""
        f = fwhm if fwhm else DEFAULT_FWHM
        return max(self.aperture_min_px, self.aperture_fwhm_mult * f)


def measure_frame(
    green,
    wcs,
    target_set: TargetSet,
    params: PhotometryParams,
    *,
    fwhm: float | None = None,
) -> list[TargetResult]:
    """Aperture-measure one solved green frame with the shared parameter set.

    Thin wrapper over :func:`measure_targets` that resolves the FWHM-adaptive
    aperture and the annulus ordering constraints from ``params`` — the one
    place live and batch agree on geometry.
    """
    r_ap = params.aperture_px(fwhm)
    r_in = max(params.annulus_in_px, r_ap + 1)
    r_out = max(params.annulus_out_px, r_in + 2)
    return measure_targets(
        green,
        wcs,
        target_set,
        r_ap=r_ap,
        r_in=r_in,
        r_out=r_out,
        egain=params.egain,
        read_noise_e=params.read_noise_e,
        sat_adu=params.sat_adu,
        band=params.band,
        min_comps=params.min_comps,
    )
