"""On-demand catalogue identity for one clicked source in a solved frame.

Whole-field queries are deliberately budgeted.  This module provides the
complementary precise operation: query a very small cone around a measured
image centroid, use Gaia as the astrometric source of truth, and enrich it with
SIMBAD only when both positions describe the same physical source.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from argos.core.catalog.aavso import CatalogError
from argos.core.catalog.field_objects import FieldObjectLookupError, simbad_field_objects
from argos.core.catalog.gaia import gaia_cone_search


class PointIdentityLookupError(RuntimeError):
    """Neither selected catalogue could answer a point-identification query."""


@dataclass(frozen=True)
class PointSourceIdentity:
    """A catalogue identity matched to one clicked image centroid."""

    name: str
    ra_deg: float
    dec_deg: float
    object_type: str = ""
    source: str = ""
    mags: tuple[tuple[str, float], ...] = ()
    separation_arcsec: float = 0.0
    gaia_source_id: str | None = None


def _separation_arcsec(ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
    """Great-circle separation, stable for the tiny cones used here."""
    ra1, dec1, ra2, dec2 = map(math.radians, (ra1_deg, dec1_deg, ra2_deg, dec2_deg))
    cosine = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine)))) * 3600.0


def identify_point_source(
    ra_deg: float,
    dec_deg: float,
    *,
    radius_arcsec: float = 10.0,
    gaia_mag_limit: float = 21.0,
    use_gaia: bool = True,
    use_simbad: bool = True,
    allow_gaia_network: bool = True,
    allow_simbad_network: bool = True,
) -> PointSourceIdentity | None:
    """Identify the nearest catalogue source to one WCS coordinate.

    Gaia owns the returned position whenever it has a match.  A SIMBAD name or
    physical type is attached only when its position is within 3 arcsec of the
    Gaia source.  This prevents a nearby radio/X-ray object in a crowded field
    from donating its name to the clicked star.
    """
    if not (0.0 <= ra_deg < 360.0 and -90.0 <= dec_deg <= 90.0):
        raise PointIdentityLookupError("Invalid WCS coordinate for point identification.")
    radius = float(radius_arcsec)
    if not math.isfinite(radius) or not (1.0 <= radius <= 60.0):
        raise PointIdentityLookupError("Invalid point-identification radius.")
    radius_deg = radius / 3600.0

    gaia = []
    simbad = []
    completed = 0
    errors = []
    if use_gaia:
        try:
            gaia = gaia_cone_search(
                ra_deg,
                dec_deg,
                radius_deg,
                mag_limit=gaia_mag_limit,
                max_results=12,
                allow_network=allow_gaia_network,
                timeout_s=20.0,
            )
            completed += 1
        except CatalogError as exc:
            errors.append(f"Gaia: {exc}")
    if use_simbad:
        try:
            simbad = simbad_field_objects(
                ra_deg,
                dec_deg,
                radius_deg,
                max_results=12,
                allow_network=allow_simbad_network,
                include_ordinary_stars=True,
                timeout_s=15.0,
            )
            completed += 1
        except FieldObjectLookupError as exc:
            errors.append(f"SIMBAD: {exc}")

    if completed == 0:
        raise PointIdentityLookupError(
            "; ".join(errors) or "Gaia and SIMBAD point identification are disabled."
        )

    gaia_ranked = sorted(
        ((_separation_arcsec(ra_deg, dec_deg, item.ra_deg, item.dec_deg), item) for item in gaia),
        key=lambda pair: pair[0],
    )
    simbad_ranked = sorted(
        ((_separation_arcsec(ra_deg, dec_deg, item.ra_deg, item.dec_deg), item) for item in simbad),
        key=lambda pair: pair[0],
    )
    # At the Seestar plate scale a very close pair may be one blended image
    # centroid. Do not assign either catalogue identity when the two nearest
    # candidates are indistinguishable at roughly half a green pixel.
    if len(gaia_ranked) >= 2 and gaia_ranked[1][0] <= max(2.0, gaia_ranked[0][0] * 1.5):
        return None
    nearest_gaia = gaia_ranked[0][1] if gaia_ranked else None
    nearest_simbad = simbad_ranked[0][1] if simbad_ranked else None

    if nearest_gaia is not None:
        gaia_sep = _separation_arcsec(ra_deg, dec_deg, nearest_gaia.ra_deg, nearest_gaia.dec_deg)
        if gaia_sep <= radius:
            identity = None
            if nearest_simbad is not None:
                cross_sep = _separation_arcsec(
                    nearest_gaia.ra_deg,
                    nearest_gaia.dec_deg,
                    nearest_simbad.ra_deg,
                    nearest_simbad.dec_deg,
                )
                if cross_sep <= 3.0:
                    identity = nearest_simbad
            magnitudes = [
                (label, value)
                for label, value in (
                    ("Gaia G", nearest_gaia.g_mag),
                    ("Gaia BP", nearest_gaia.bp_mag),
                    ("Gaia RP", nearest_gaia.rp_mag),
                )
                if value is not None
            ]
            if identity is not None:
                magnitudes.extend((f"SIMBAD {band}", value) for band, value in identity.mags)
            return PointSourceIdentity(
                name=identity.name if identity is not None else nearest_gaia.display_name,
                ra_deg=nearest_gaia.ra_deg,
                dec_deg=nearest_gaia.dec_deg,
                object_type=identity.object_type if identity is not None else "Star",
                source="Gaia DR3 + SIMBAD" if identity is not None else "Gaia DR3",
                mags=tuple(magnitudes),
                separation_arcsec=gaia_sep,
                gaia_source_id=nearest_gaia.source_id,
            )

    if nearest_simbad is not None:
        simbad_sep = _separation_arcsec(
            ra_deg, dec_deg, nearest_simbad.ra_deg, nearest_simbad.dec_deg
        )
        if simbad_sep <= radius:
            return PointSourceIdentity(
                name=nearest_simbad.name,
                ra_deg=nearest_simbad.ra_deg,
                dec_deg=nearest_simbad.dec_deg,
                object_type=nearest_simbad.object_type,
                source="SIMBAD",
                mags=tuple((f"SIMBAD {band}", value) for band, value in nearest_simbad.mags),
                separation_arcsec=simbad_sep,
            )
    return None
