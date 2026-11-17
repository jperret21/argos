"""Persistent target / comparison set for a session (notes/photometry_plan.md §5 B4).

Qt-free. The set is the night's selection: the variable target(s), the comparison
stars, and any check stars, each with RA/Dec + catalog id so they can be projected
onto every solved frame and (later) aperture-measured. Persisted as ``targets.json``
(atomic write, mirrors session_log) so it survives restarts.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROLE_TARGET = "target"
ROLE_COMPARISON = "comparison"
ROLE_CHECK = "check"
ROLES = (ROLE_TARGET, ROLE_COMPARISON, ROLE_CHECK)

SCHEMA = 1
SELECTION_MANIFEST_SCHEMA = 1
_SAME_SOURCE_ARCSEC = 1.0

#: S77: the stars that may take a Gaia DR3 proper motion: AAVSO VSX and VSP stars with
#: an AUID (their identity, ``key``, never depends on their position). A manual star's
#: position was measured on a frame of its own date.
CATALOGUE_POSITION_SOURCES = frozenset({"vsx", "vsp", "vsp_auto"})
#: S77: the epoch (Julian year) of a VSX/VSP position, J2000.0. RR Lyr's VSX position is
#: Gaia DR3's 2016.0 one moved back to 2000.0 with its own proper motion, to 0.05".
CATALOGUE_POSITION_EPOCH = 2000.0
#: S77: a Gaia DR3 source is a set star's when its position at J2000.0 (its own motion
#: applied) or at 2016.0 lies within this of the star's catalogue position (arcsec)...
PROPER_MOTION_MATCH_ARCSEC = 1.0
#: ...or, for a star with a catalogue V, when it is the only source within this radius
#: whose G is within ``PROPER_MOTION_MATCH_MAG`` of V (VSP's position of RR Lyr's
#: comparison 000-BJW-666, 174 mas/yr, is 3.2" from Gaia's 2016.0 one, 5.2" from its
#: J2000.0 one) and no other source there is within ``PROPER_MOTION_CROWD_MAG`` of V.
PROPER_MOTION_WIDE_ARCSEC = 6.0
PROPER_MOTION_MATCH_MAG = 1.0
PROPER_MOTION_CROWD_MAG = 2.5
_J2000_JD = 2451545.0
_JULIAN_YEAR_D = 365.25


@dataclass
class TargetStar:
    """One selected star, identified by AUID when known else by position."""

    role: str
    ra_deg: float
    dec_deg: float
    auid: str | None = None
    name: str | None = None
    source: str = "manual"  # vsx | vsp | manual
    mags: dict = field(default_factory=dict)  # band -> magnitude
    note: str = ""
    chart_id: str | None = None  # VSP chart that supplied ``mags`` (AAVSO CHART)
    #: S77: the proper motion (mas/yr; RA as µα·cos δ) of ``pm_source`` (Gaia DR3), the
    #: epoch (Julian year) and position (degrees) it starts from (Gaia's 2016.0 one;
    #: ``ra_deg``/``dec_deg`` when None). ``ra_deg``/``dec_deg`` stay the catalogue's.
    pm_ra_mas_yr: float | None = None
    pm_dec_mas_yr: float | None = None
    pm_epoch: float | None = None
    pm_ra_deg: float | None = None
    pm_dec_deg: float | None = None
    pm_source: str | None = None

    def key(self) -> str:
        """Stable identity used to dedup/update (AUID, else rounded position)."""
        if self.auid:
            return f"auid:{self.auid}"
        return f"pos:{self.ra_deg:.5f},{self.dec_deg:.5f}"

    @property
    def has_proper_motion(self) -> bool:
        return (
            self.pm_ra_mas_yr is not None
            and self.pm_dec_mas_yr is not None
            and self.pm_epoch is not None
        )

    def position_at_year(self, year: float) -> tuple[float, float]:
        """S77: RA, Dec (degrees) at Julian ``year``: the proper motion's starting
        position moved linearly (in the tangent plane: over the owner's 30 years the
        curvature of RR Lyr's 0.22"/yr path is under 1e-6"); the catalogue position
        when there is no proper motion."""
        if not self.has_proper_motion:
            return self.ra_deg, self.dec_deg
        ra0 = self.pm_ra_deg if self.pm_ra_deg is not None else self.ra_deg
        dec0 = self.pm_dec_deg if self.pm_dec_deg is not None else self.dec_deg
        years = float(year) - float(self.pm_epoch)
        dec = dec0 + float(self.pm_dec_mas_yr) * years / 3.6e6
        cos_dec = math.cos(math.radians(dec0))
        if cos_dec < 1e-9:
            return ra0, dec  # at a pole RA is undefined: no RA motion
        ra = (ra0 + float(self.pm_ra_mas_yr) * years / 3.6e6 / cos_dec) % 360.0
        return ra, dec

    def at_jd(self, jd_utc: float) -> "TargetStar":
        """S77: this star at a frame's date (JD UTC), ``ra_deg``/``dec_deg`` moved by its
        proper motion (the copy's own motion fields unchanged); itself without one."""
        if not self.has_proper_motion:
            return self
        ra, dec = self.position_at_year(2000.0 + (float(jd_utc) - _J2000_JD) / _JULIAN_YEAR_D)
        return replace(self, ra_deg=ra, dec_deg=dec)

    @property
    def display_name(self) -> str:
        # VSP's ``label`` (for example ``114``) encodes a chart magnitude
        # rather than an object name.  Showing it as the reference-star name
        # made both the image overlay and the scientific hand-off ambiguous;
        # use the traceable AUID instead.
        if (
            self.auid
            and self.source in {"vsp", "vsp_auto"}
            and self.name
            and self.name.strip().replace(".", "", 1).isdigit()
        ):
            return self.auid
        return self.name or self.auid or f"{self.ra_deg:.3f},{self.dec_deg:+.3f}"


@dataclass
class TargetSet:
    """The session's selected stars; load/save ``targets.json``."""

    object_name: str = ""
    stars: list[TargetStar] = field(default_factory=list)

    def set_role(self, star: TargetStar) -> None:
        """Add ``star`` or replace the existing one with the same identity."""
        k = star.key()
        for i, s in enumerate(self.stars):
            if s.key() == k:
                self.stars[i] = _keep_proper_motion(star, s)
                return
        # A catalogue lookup can enrich a manually selected target with an
        # AUID, changing its key from position to AUID.  Keep that as one
        # unambiguous scientific target rather than silently duplicating it.
        if star.role == ROLE_TARGET:
            for i, current in enumerate(self.stars):
                if current.role != ROLE_TARGET:
                    continue
                if _separation_arcsec(current, star) <= _SAME_SOURCE_ARCSEC:
                    self.stars[i] = _prefer_identified_target(current, star)
                    return
        self.stars.append(star)

    def remove(self, key: str) -> None:
        self.stars = [s for s in self.stars if s.key() != key]

    def by_role(self, role: str) -> list[TargetStar]:
        return [s for s in self.stars if s.role == role]

    def at_jd(self, jd_utc: float | None) -> "TargetSet":
        """S77: the set at a frame's date (JD UTC): every star with a proper motion moved
        to it (:meth:`TargetStar.at_jd`), the others as they are; ``self`` when no star
        moves (or no date). Every path that places an aperture measures this set."""
        if jd_utc is None or not any(s.has_proper_motion for s in self.stars):
            return self
        return TargetSet(object_name=self.object_name, stars=[s.at_jd(jd_utc) for s in self.stars])

    def backfill_proper_motions(self, gaia_stars) -> int:
        """S77: give the set's VSX/VSP stars with an AUID and no proper motion the proper
        motion and position of their Gaia DR3 source; returns how many stars changed.

        ``gaia_stars``: ``GaiaStar`` (``pmra_mas_yr``, ``pmdec_mas_yr``, positions at
        ``epoch``). A source is the star's (:func:`match_gaia_source`) when its J2000.0
        or 2016.0 position lies within :data:`PROPER_MOTION_MATCH_ARCSEC` of the
        catalogue position, or for a star with a catalogue V, when it is the one source
        of that brightness within :data:`PROPER_MOTION_WIDE_ARCSEC`. The aperture then
        follows Gaia's position and motion; the catalogue position is kept as written.
        """
        sources = [g for g in gaia_stars if _gaia_motion(g) is not None]
        changed = 0
        for index, star in enumerate(self.stars):
            if star.has_proper_motion or not star.auid:
                continue
            if star.source not in CATALOGUE_POSITION_SOURCES:
                continue
            g = match_gaia_source(star, sources)
            if g is None:
                continue
            pmra, pmdec, epoch = _gaia_motion(g)
            self.stars[index] = replace(
                star,
                pm_ra_mas_yr=round(pmra, 4),
                pm_dec_mas_yr=round(pmdec, 4),
                pm_epoch=epoch,
                pm_ra_deg=round(float(g.ra_deg), 9),
                pm_dec_deg=round(float(g.dec_deg), 9),
                pm_source=f"Gaia DR3 {getattr(g, 'source_id', '')}".strip(),
            )
            changed += 1
        return changed

    def backfill_chart_ids(self, comparisons) -> int:
        """S68: name the VSP chart of comparisons saved without one; returns how many.

        A comparison taken from VSP (``vsp`` or ``vsp_auto``) before Argos kept the
        chart (0.4.1), and kept since in the object's set, never got one: only a new
        pick did, so CHART stayed ``na`` on every report. It gets the chart of a VSP
        answer (``comparisons``, :class:`ComparisonStar`) that lists its AUID with the
        same catalogue magnitude in every band it holds: the sequence it is measured
        against. A star whose magnitudes differ (the sequence was revised) keeps none.
        """
        answer = {c.auid: c for c in comparisons if c.auid and c.chart_id}
        changed = 0
        for index, star in enumerate(self.stars):
            if star.role != ROLE_COMPARISON or star.chart_id:
                continue
            match = answer.get(star.auid) if star.source in {"vsp", "vsp_auto"} else None
            if match is None or not star.mags:
                continue
            mags = {band.band: band.mag for band in match.bands}
            if any(
                mags.get(band) is None or abs(float(mags[band]) - float(mag)) > 5e-4
                for band, mag in star.mags.items()
            ):
                continue
            self.stars[index] = replace(star, chart_id=match.chart_id)
            changed += 1
        return changed

    def summary(self) -> dict:
        """A display/readiness summary of the selection (Qt-free).

        Differential photometry needs at least one target (T1) and one
        comparison; a check star is recommended but optional. ``complete``
        captures that minimum so the UI can tell the user what is missing.
        """
        targets = self.by_role(ROLE_TARGET)
        comparisons = self.by_role(ROLE_COMPARISON)
        checks = self.by_role(ROLE_CHECK)
        return {
            "object": self.object_name,
            "target": targets[0].display_name if targets else None,
            "n_target": len(targets),
            "n_comparison": len(comparisons),
            "n_check": len(checks),
            "complete": bool(targets) and bool(comparisons),
        }

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "object": self.object_name,
            "stars": [_star_dict(s) for s in self.stars],
        }

    def selection_manifest(self, *, generated_by: str = "Argos") -> dict:
        """Return the explicit, auditable target/comparison hand-off.

        ``targets.json`` is mutable application state.  This separate manifest
        records the exact selection active during acquisition.  It is
        deliberately labelled as a live-preview selection: final calibrated
        validation belongs to registered frames in Siril / star_var_script.
        """

        def record(star: TargetStar, index: int) -> dict:
            return {
                "selection_index": index,
                "name": star.display_name,
                "auid": star.auid,
                "ra_deg_j2000": round(float(star.ra_deg), 8),
                "dec_deg_j2000": round(float(star.dec_deg), 8),
                "catalogue_source": star.source,
                "catalogue_magnitudes": dict(star.mags),
                "catalogue_chart_id": star.chart_id,
                "note": star.note,
                **(
                    {
                        name: getattr(star, name)
                        for name in _PM_FIELDS
                        if getattr(star, name) is not None
                    }
                    if star.has_proper_motion
                    else {}
                ),
            }

        roles = (
            ("targets", ROLE_TARGET),
            ("comparison_stars", ROLE_COMPARISON),
            ("check_stars", ROLE_CHECK),
        )
        return {
            "schema": SELECTION_MANIFEST_SCHEMA,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "generated_by": generated_by,
            "object_name": self.object_name,
            "selection_status": "provisional_live_preview",
            "scientific_note": (
                "Argos acquisition selection. This is a traceable live-preview "
                "ensemble, not a calibrated result. Revalidate comparison and "
                "check stars on registered, calibrated frames in Siril / star_var_script."
            ),
            **{
                key: [record(star, i + 1) for i, star in enumerate(self.by_role(role))]
                for key, role in roles
            },
        }

    def save_selection_manifest(self, path, *, generated_by: str = "Argos") -> None:
        """Atomically write the session photometry selection hand-off."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.selection_manifest(generated_by=generated_by), indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def append_selection_history(self, path, *, generated_by: str = "Argos") -> None:
        """Append one immutable selection snapshot to a session JSONL history."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as history:
            history.write(json.dumps(self.selection_manifest(generated_by=generated_by)) + "\n")

    @classmethod
    def from_dict(cls, d: dict) -> "TargetSet":
        valid = {f.name for f in fields(TargetStar)}
        stars = [
            TargetStar(**{k: v for k, v in s.items() if k in valid}) for s in d.get("stars", [])
        ]
        result = cls(object_name=str(d.get("object", "")))
        # Repair legacy manual + catalogue-enriched duplicates while loading.
        for star in stars:
            result.set_role(star)
        return result

    def save(self, path) -> None:
        """Atomically write ``targets.json`` (temp + os.replace)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path) -> "TargetSet":
        """Load ``targets.json``; return an empty set if missing/unreadable."""
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:  # corrupt file → start fresh, don't crash
            logger.warning("Could not read %s: %s", path, exc)
            return cls()


#: S79: a comparison or check star is crowded when a brighter star of the set (or one
#: of unknown brightness, a variable) lies within this many aperture radii: its light
#: falls in the aperture or the sky annulus (XX Cyg 2026-09-07: 000-BJV-173, 6.9 green
#: px from 000-BJV-169, 1.47 mag brighter, inside a 5.45 px aperture).
CROWDING_APERTURE_RADII = 2.0


@dataclass(frozen=True)
class Crowding:
    """S79: why a comparison or check star is crowded."""

    neighbour: str  # the neighbour's display name
    separation_arcsec: float
    #: the neighbour's catalogue magnitude minus the star's (negative: brighter) in
    #: ``band``; None when the two share no band (a variable, a manual star).
    delta_mag: float | None = None
    band: str | None = None

    def text(self, star_name: str, radius_arcsec: float) -> str:
        how = (
            f"{-self.delta_mag:.2f} mag brighter in {self.band}"
            if self.delta_mag is not None
            else "of unknown brightness"
        )
        return (
            f'{star_name}: {self.neighbour} ({how}) is {self.separation_arcsec:.1f}" away,'
            f' within {CROWDING_APERTURE_RADII:g} aperture radii ({radius_arcsec:.1f}"):'
            " its light reaches this star's aperture or sky annulus (S79)."
        )


def crowded_stars(tset: TargetSet, radius_arcsec: float) -> dict[str, Crowding]:
    """S79: the comparison and check stars of ``tset`` with a brighter star of the set,
    or one of unknown brightness, within ``radius_arcsec`` (about
    :data:`CROWDING_APERTURE_RADII` aperture radii); keyed by ``key()``, the nearest
    such neighbour each. Brighter: a smaller catalogue magnitude in V, else in the
    first band both stars hold. A star of the set within 1" is the same star."""
    out: dict[str, Crowding] = {}
    for star in tset.stars:
        if star.role not in (ROLE_COMPARISON, ROLE_CHECK):
            continue
        best: Crowding | None = None
        for other in tset.stars:
            if other is star or other.key() == star.key():
                continue
            sep = _separation_arcsec(star, other)
            if sep <= _SAME_SOURCE_ARCSEC or sep > radius_arcsec:
                continue
            band = _common_band(star, other)
            delta = None
            if band is not None:
                delta = float(other.mags[band]) - float(star.mags[band])
                if delta >= 0.0:
                    continue  # fainter or as bright: this star dominates its aperture
            if best is None or sep < best.separation_arcsec:
                best = Crowding(other.display_name, round(sep, 2), delta, band)
        if best is not None:
            out[star.key()] = best
    return out


def _common_band(a: TargetStar, b: TargetStar) -> str | None:
    if not isinstance(a.mags, dict) or not isinstance(b.mags, dict):
        return None
    if a.mags.get("V") is not None and b.mags.get("V") is not None:
        return "V"
    return next((band for band in a.mags if b.mags.get(band) is not None), None)


def comparison_chart_id(stars) -> str | None:
    """The VSP chart every comparison star comes from, else None.

    It is what an AAVSO report puts in CHART. A manual comparison, or two
    charts mixed in one ensemble, leave no single sequence to name.
    """
    charts = {s.chart_id for s in stars if s.role == ROLE_COMPARISON}
    if len(charts) != 1:
        return None
    return charts.pop()


#: S77: the proper-motion fields, written only when known (a set without them keeps
#: its bytes, and an older Argos reads the file: unknown keys are ignored).
_PM_FIELDS = ("pm_ra_mas_yr", "pm_dec_mas_yr", "pm_epoch", "pm_ra_deg", "pm_dec_deg", "pm_source")


def _star_dict(star: TargetStar) -> dict:
    d = asdict(star)
    for name in _PM_FIELDS:
        if d.get(name) is None:
            d.pop(name, None)
    return d


def _at(ra_deg: float, dec_deg: float) -> TargetStar:
    return TargetStar(role=ROLE_TARGET, ra_deg=ra_deg, dec_deg=dec_deg)


def _gaia_motion(g) -> tuple[float, float, float] | None:
    pmra = getattr(g, "pmra_mas_yr", None)
    pmdec = getattr(g, "pmdec_mas_yr", None)
    if pmra is None or pmdec is None:
        return None
    return float(pmra), float(pmdec), float(getattr(g, "epoch", 2016.0))


def match_gaia_source(star: TargetStar, sources):
    """S77: the Gaia DR3 source (with a proper motion) of a catalogue star, or None.

    Close match: the brightest source whose position at J2000.0 (its own motion) or at
    its epoch lies within :data:`PROPER_MOTION_MATCH_ARCSEC` of the star's catalogue
    position. Wide match, for a star with a catalogue V only: within
    :data:`PROPER_MOTION_WIDE_ARCSEC`, the one source whose G is within
    :data:`PROPER_MOTION_MATCH_MAG` of V, when no other source there is within
    :data:`PROPER_MOTION_CROWD_MAG` of V (a faint variable beside a brighter star
    never takes that star's position).
    """
    close, wide = [], []
    for g in sources:
        motion = _gaia_motion(g)
        if motion is None:
            continue
        pmra, pmdec, epoch = motion
        probe = TargetStar(
            role=ROLE_TARGET,
            ra_deg=float(g.ra_deg),
            dec_deg=float(g.dec_deg),
            pm_ra_mas_yr=pmra,
            pm_dec_mas_yr=pmdec,
            pm_epoch=epoch,
        )
        at_2000 = _at(*probe.position_at_year(CATALOGUE_POSITION_EPOCH))
        sep = min(_separation_arcsec(star, at_2000), _separation_arcsec(star, probe))
        if sep <= PROPER_MOTION_MATCH_ARCSEC:
            close.append(g)
        elif sep <= PROPER_MOTION_WIDE_ARCSEC:
            wide.append(g)
    if close:
        return min(close, key=_g_mag_key)
    v = star.mags.get("V") if isinstance(star.mags, dict) else None
    if v is None:
        return None
    near = [g for g in wide if getattr(g, "g_mag", None) is not None]
    matched = [g for g in near if abs(float(g.g_mag) - float(v)) <= PROPER_MOTION_MATCH_MAG]
    crowd = [g for g in near if abs(float(g.g_mag) - float(v)) <= PROPER_MOTION_CROWD_MAG]
    if len(matched) == 1 and len(crowd) == 1:
        return matched[0]
    return None


def _g_mag_key(g) -> float:
    mag = getattr(g, "g_mag", None)
    return float(mag) if mag is not None else math.inf


def _separation_arcsec(a: TargetStar, b: TargetStar) -> float:
    """Small-angle separation (the identity merge, S77's Gaia match, S79's crowding),
    the RA difference taken across RA 0h (359.999° and 0.001° are 7.2" apart at the
    equator, not 1.3e6")."""
    dra_deg = (a.ra_deg - b.ra_deg + 180.0) % 360.0 - 180.0
    dra = math.radians(dra_deg) * math.cos(math.radians((a.dec_deg + b.dec_deg) / 2))
    ddec = math.radians(a.dec_deg - b.dec_deg)
    return math.degrees(math.hypot(dra, ddec)) * 3600.0


def _prefer_identified_target(current: TargetStar, incoming: TargetStar) -> TargetStar:
    """Retain catalogue identity when merging two representations of a target."""
    if incoming.auid or not current.auid:
        preferred, fallback = incoming, current
    else:
        preferred, fallback = current, incoming
    return replace(
        preferred,
        auid=preferred.auid or fallback.auid,
        name=preferred.name or fallback.name,
        mags=preferred.mags or fallback.mags,
        note=preferred.note or fallback.note,
    )


def _keep_proper_motion(incoming: TargetStar, current: TargetStar) -> TargetStar:
    """S77: a star set again (a role change from the UI: the same identity, ``key``)
    keeps the catalogue position and proper motion the set holds for it when the
    incoming copy has none (it may carry a position moved to a frame's date)."""
    if incoming.has_proper_motion or not current.has_proper_motion:
        return incoming
    return replace(
        incoming,
        ra_deg=current.ra_deg,
        dec_deg=current.dec_deg,
        **{name: getattr(current, name) for name in _PM_FIELDS},
    )
