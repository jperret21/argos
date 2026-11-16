"""The single source of truth for differential-photometry parameters (WS7).

Both the live path (``AcquisitionEngine._measure_photometry``) and the offline
batch worker (``PhotometryBatchWorker``) build their measurement inputs here, so
the *physics* is provably identical: config keys ``photometry.*`` / ``camera.*``
are the only knobs, and the FWHM-adaptive aperture is computed the same way in
both. Qt-free.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Callable

from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.hardware import egain as camera_egain
from argos.core.photometry.aperture import GREEN_PIXELS
from argos.core.photometry.session import TargetResult, measure_targets
from argos.core.photometry.uncertainty import OSBORN_CY, scintillation_sigma

logger = logging.getLogger(__name__)

#: Fallback FWHM (green px) when a frame's FWHM is unknown.
#:
#: With the shipped defaults this does **not** fall back to the aperture floor,
#: contrary to what this comment used to claim: ``max(4, 2.5 * 3.0) = 7.5`` green
#: px, i.e. ~56 arcsec on an S30 Pro against ~30 arcsec for a frame with a
#: measured FWHM. A measurement taken without a FWHM is therefore not directly
#: comparable with one taken with it — more sky, and more neighbours.
DEFAULT_FWHM = 3.0

#: ``photometry.noise_model`` (S72). ``green_plane``, the default: the (G1+G2)/2
#: plane's model, 2 × e-/ADU, read noise rn/√2, the profile's black level subtracted,
#: the sky estimate's own error (S75) and scintillation (S74). ``pixel``: the 0.4.x
#: model, kept selectable, one raw pixel's e-/ADU and the whole sky level as photons,
#: neither term. Both use the camera's e-/ADU (S73, ``hardware.egain``).
NOISE_MODEL_PIXEL = "pixel"
NOISE_MODEL_GREEN = "green_plane"
NOISE_MODEL_DEFAULT = NOISE_MODEL_GREEN
NOISE_MODELS = (NOISE_MODEL_GREEN, NOISE_MODEL_PIXEL)

#: Scintillation computed at sea level for want of a height, or not at all for want of
#: an exposure or airmass (each logged once).
_sea_level_noted = False
_no_scint_noted = False


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
    track_apertures: bool = True  # follow field rotation / drift across a batch
    #: S72's model (``photometry.noise_model = green_plane``): the telescope profile's
    #: black level (ADU, no photon in it) and the raw pixels in a plane value (2);
    #: 0 and 1 are the 0.4.x model.
    black_adu: float = 0.0
    plane_pixels: int = 1
    #: S74's scintillation (green-plane model only): the telescope's aperture (mm, 0:
    #: no term), Osborn's C_Y, the site's height (m, None: sea level, noted), and the
    #: frame's exposure (s) and airmass, set per frame (``with_frame``).
    aperture_mm: float = 0.0
    scint_cy: float = 0.0
    #: S73: ``photometry.read_noise_e`` as set, which an e-/ADU without a measured read
    #: noise brings back in ``with_frame`` (None: keep ``read_noise_e``).
    read_noise_setting_e: float | None = None
    site_height_m: float | None = None
    exposure_s: float | None = None
    airmass: float | None = None

    @classmethod
    def from_config(
        cls, cfg: Callable[[str, object], object], egain: float = 1.0
    ) -> "PhotometryParams":
        """Build from a ``cfg(key, default)`` accessor (the engine's ``_cfg``).

        ``egain`` (e-/ADU) is resolved by the caller — live through
        ``hardware.egain.live``, a saved frame through :func:`frame_egain` — since
        only the caller knows the frame's gain. With the green-plane model, an
        ``Egain`` from the profile's photon transfer brings the read noise measured
        with it (S73); every other value is config-keyed.
        """
        green = str(cfg("photometry.noise_model", NOISE_MODEL_DEFAULT)) == NOISE_MODEL_GREEN
        read_noise = float(cfg("photometry.read_noise_e", 1.5))
        measured_rn = getattr(egain, "read_noise_e", None)
        if green and measured_rn:
            read_noise = float(measured_rn)
        return cls(
            aperture_min_px=float(cfg("photometry.aperture_min_px", 4)),
            aperture_fwhm_mult=float(cfg("photometry.aperture_fwhm_mult", 2.5)),
            annulus_in_px=float(cfg("photometry.annulus_in_px", 8)),
            annulus_out_px=float(cfg("photometry.annulus_out_px", 12)),
            egain=(
                egain if isinstance(egain, camera_egain.Egain) else (float(egain) if egain else 1.0)
            ),
            read_noise_e=read_noise,
            read_noise_setting_e=float(cfg("photometry.read_noise_e", 1.5)),
            sat_adu=float(cfg("camera.linearity_max_adu", 50000)),
            band=str(cfg("photometry.default_band", "TG") or "TG"),
            min_comps=int(cfg("photometry.min_comparisons", 2)),
            track_apertures=bool(cfg("photometry.track_apertures", True)),
            black_adu=profile_black_level(cfg) if green else 0.0,
            plane_pixels=GREEN_PIXELS if green else 1,
            aperture_mm=_profile(cfg).aperture_mm if green else 0.0,
            scint_cy=OSBORN_CY if green else 0.0,
            site_height_m=_settings_height(cfg),
        )

    @property
    def egain_source(self) -> str | None:
        """Where the e-/ADU came from (``hardware.egain``), when known."""
        return getattr(self.egain, "source", None)

    def with_frame(
        self,
        *,
        egain: float | None = None,
        exposure_s: float | None = None,
        airmass: float | None = None,
        site_height_m: float | None = None,
    ) -> "PhotometryParams":
        """These params for one frame: its own e-/ADU (and, green-plane model, the
        read noise measured with it, else the Settings one: never the read noise of
        the e-/ADU it replaces), exposure, airmass and site height. A None keeps the
        current value."""
        changes: dict = {}
        if egain is not None and (
            egain != self.egain or getattr(egain, "source", None) != self.egain_source
        ):
            changes["egain"] = egain
            measured_rn = getattr(egain, "read_noise_e", None)
            if self.plane_pixels > 1 and measured_rn:
                changes["read_noise_e"] = float(measured_rn)
            elif self.plane_pixels > 1 and self.read_noise_setting_e is not None:
                changes["read_noise_e"] = float(self.read_noise_setting_e)
        if exposure_s is not None:
            changes["exposure_s"] = float(exposure_s)
        if airmass is not None:
            changes["airmass"] = float(airmass)
        if site_height_m is not None:
            changes["site_height_m"] = float(site_height_m)
        return replace(self, **changes) if changes else self

    def scint_frac(self, airmass: float | None = None) -> float:
        """Scintillation (relative flux sigma, S74) at ``airmass`` (default the
        frame's); 0 with the 0.4.x model or without an exposure or airmass."""
        if self.scint_cy <= 0 or self.aperture_mm <= 0:
            return 0.0
        airmass = airmass if airmass is not None else self.airmass
        if self.exposure_s is None or airmass is None:
            global _no_scint_noted
            if not _no_scint_noted:
                _no_scint_noted = True
                logger.info(
                    "Scintillation not counted in a frame's errors: no exposure time or no"
                    " airmass for it (S74)"
                )
            return 0.0
        height = self.site_height_m
        if height is None:
            global _sea_level_noted
            if not _sea_level_noted:
                _sea_level_noted = True
                logger.info(
                    "Scintillation computed at sea level: no SITEELEV in the frame and no"
                    " Settings site (S74)"
                )
            height = 0.0
        return scintillation_sigma(
            self.aperture_mm, self.exposure_s, airmass, height, self.scint_cy
        )

    def aperture_px(self, fwhm: float | None) -> float:
        """FWHM-adaptive aperture radius, floored at ``aperture_min_px``.

        An unknown ``fwhm`` substitutes :data:`DEFAULT_FWHM`, which lands
        *above* the floor — see that constant's note.
        """
        f = fwhm if fwhm else DEFAULT_FWHM
        return max(self.aperture_min_px, self.aperture_fwhm_mult * f)


def _profile(cfg: Callable[[str, object], object]):
    """The telescope profile the config names (not the process-wide active one,
    so a batch built from a config measures as that config says)."""
    from argos.core.hardware import catalog

    key = cfg("hardware.profile", catalog.DEFAULT_PROFILE.key)
    return catalog.get(str(key or "")) or catalog.DEFAULT_PROFILE


def profile_black_level(cfg: Callable[[str, object], object]) -> float:
    """Black level (ADU) of the telescope profile the config names (S72)."""
    return float(_profile(cfg).black_level_adu)


def _settings_height(cfg: Callable[[str, object], object]) -> float | None:
    """The Settings site's height (m), None when no site is set (X2)."""
    from argos.core.config import observing_site

    site = observing_site(SimpleNamespace(get=cfg))
    return float(site[2]) if site is not None else None


def frame_egain(header, table=None) -> float | None:
    """e-/ADU of a saved frame (Open FITS, batch re-run), or None if unknown.

    ``hardware.egain.of_frame``: the ``camera.egain_table`` entry at the frame's
    ``GAIN``, an ``EGAIN`` that table wrote, the photon-transfer measurement of the
    camera its ``TELESCOP`` names (S73: never the wrong 0.8 or 1.723 of an S30 Pro
    frame at gain 80), then its ``EGAIN``. The value is an ``Egain``: its
    ``source`` says which. None (the caller keeps its live chain) when nothing is
    usable.
    """
    return camera_egain.of_frame(header, table)


def frame_scintillation_inputs(header) -> dict:
    """A saved frame's ``EXPTIME``, ``AIRMASS`` and ``SITEELEV`` (S74), for
    :meth:`PhotometryParams.with_frame`; None for what the header lacks."""

    def number(key, lo):
        value = header.get(key)
        if isinstance(value, bool):
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value >= lo else None

    return {
        "exposure_s": number("EXPTIME", 0.0),
        "airmass": number("AIRMASS", 1.0),
        "site_height_m": number("SITEELEV", -500.0),
    }


def measure_frame(
    green,
    wcs,
    target_set: TargetSet,
    params: PhotometryParams,
    *,
    fwhm: float | None = None,
    on_star=None,
    exclude: frozenset[str] = frozenset(),
    star_airmass: Callable[[TargetStar], float | None] | None = None,
) -> list[TargetResult]:
    """Aperture-measure one solved green frame with the shared parameter set.

    Thin wrapper over :func:`measure_targets` that resolves the FWHM-adaptive
    aperture and the annulus ordering constraints from ``params`` — the one
    place live and batch agree on geometry. ``exclude``: comparisons left out of
    the frame's ensemble (S69, off-centre). ``star_airmass``: each star's own
    airmass for its scintillation (S74); the frame's (``params.airmass``) when
    absent or None.
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
        black_adu=params.black_adu,
        plane_pixels=params.plane_pixels,
        band=params.band,
        min_comps=params.min_comps,
        on_star=on_star,
        exclude=exclude,
        scint_frac=_star_scintillation(params, star_airmass),
    )


def _star_scintillation(params: PhotometryParams, star_airmass):
    """The per-star scintillation of ``measure_targets`` (S74), None when off."""
    if params.scint_cy <= 0 or params.aperture_mm <= 0:
        return None
    if star_airmass is None:
        frac = params.scint_frac()
        return lambda _star: frac
    return lambda star: params.scint_frac(star_airmass(star))
