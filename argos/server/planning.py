"""Visibility, exoplanet lookups and the transit planner (rows A42, A65, A66).

- **Visibility** (A65): a target's altitude over one night at the Settings
  site. Altitudes are the core's fast spherical trigonometry
  (``sky_geometry.altitude_at``, the function Qt's visibility plot samples
  through ``upcoming_night_altitudes``); the night is astronomical dusk to
  dawn (Q-P6) instead of Qt's fixed 18:00-06:00, and a night spans midnight
  (S26). The Sun is the Astronomical Almanac's low-precision position.
- **Exoplanets** (A42): ``exoplanets.lookup_exoplanet`` and
  ``cached_exoplanet_suggestions`` with the configured cache file.
- **Transits** (A66): ``predict_next_transit`` from ``bjd_tdb(julian_date(
  now))`` at the site and ``utc_from_bjd_tdb`` as ``sequencer_page.py:132-187``,
  ``make_transit_sequence`` as ``_prepare_transit_plan`` (248-286). The server
  chooses the transit: daylight and below-limit transits are skipped (Q-P10).

Nothing here uses the network except the explicit exoplanet lookup; a site
is required (X2: never latitude/longitude 0/0).
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from argos.core.catalog import exoplanets
from argos.core.catalog.exoplanets import ExoplanetLookupError, ExoplanetTarget
from argos.core.config import observing_site
from argos.core.exoplanet.transit import (
    TransitWindow,
    make_transit_sequence,
    predict_next_transit,
)
from argos.core.imaging.sky_geometry import altitude_at
from argos.core.photometry.airmass import bjd_tdb, julian_date, utc_from_bjd_tdb
from argos.server.errors import ApiError
from argos.server.sequence_plan import LOCKED_MESSAGE, light_filter_default, parse_utc
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: Sun altitudes of the twilight limits (degrees; sunset: refraction + semi-diameter).
SUNSET_DEG = -0.833
CIVIL_DEG = -6.0
NAUTICAL_DEG = -12.0
ASTRONOMICAL_DEG = -18.0
MIN_ALT_KEY = "site.min_altitude_deg"
DEFAULT_MIN_ALT_DEG = 30.0
#: Qt's Baseline spin box (``sequence_panel.py:394``).
MAX_BASELINE_MIN = 240.0
#: How far ahead an observable transit is searched (Q-P10).
SEARCH_DAYS = 366.0
#: Transit observability is checked on this grid (s) plus both ends.
TRANSIT_CHECK_S = 120.0
#: Candidate transits whose BJD_TDB − UTC correction is computed in one astropy call:
#: one scalar call per candidate stalled the event loop (0.4 s for a 366-day search).
TRANSIT_BATCH = 48
SKIPPED_LISTED = 20
SITE_MISSING = "Set the observing site in Settings to compute altitudes."
SITE_MISSING_TRANSIT = (
    "Set and save the observing site in Settings before preparing transit coverage."
)


# ---------------------------------------------------------------------------
# Sky geometry (pure)
# ---------------------------------------------------------------------------


def jd_of(t: float) -> float:
    """JD (UTC) of a Unix time, as ``upcoming_night_altitudes`` converts it."""
    return t / 86400.0 + 2440587.5


def _dt(t: float) -> datetime:
    return datetime.fromtimestamp(t, tz=timezone.utc)


def _iso(t: float | None) -> str | None:
    return None if t is None else utc_iso(_dt(t))


def sun_radec(jd: float) -> tuple[float, float]:
    """Apparent Sun (RA hours, Dec degrees), Astronomical Almanac low precision (≈0.01°)."""
    n = jd - 2451545.0
    mean_lon = math.radians((280.460 + 0.9856474 * n) % 360.0)
    anomaly = math.radians((357.528 + 0.9856003 * n) % 360.0)
    ecl_lon = (
        mean_lon
        + math.radians(1.915) * math.sin(anomaly)
        + math.radians(0.020) * math.sin(2 * anomaly)
    )
    obliquity = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(obliquity) * math.sin(ecl_lon), math.cos(ecl_lon))
    dec = math.asin(math.sin(obliquity) * math.sin(ecl_lon))
    return (math.degrees(ra) / 15.0) % 24.0, math.degrees(dec)


def sun_altitude(t: float, lat: float, lon: float) -> float:
    """Sun altitude (degrees, no refraction) at Unix time *t*."""
    jd = jd_of(t)
    ra_h, dec = sun_radec(jd)
    return altitude_at(jd, ra_h, dec, lat, lon)


def solar_noon(day: date, lon: float) -> float:
    """Unix time of the local mean solar noon of *day* (UTC noon minus longitude/15 h)."""
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
    return noon.timestamp() - lon / 15.0 * 3600.0


def night_date_for(t: float, lon: float) -> date:
    """The evening date of the noon-to-noon night containing *t* (02:00 → the day before)."""
    return (_dt(t) + timedelta(hours=lon / 15.0 - 12.0)).date()


def _bisect(f: Callable[[float], float], a: float, b: float, level: float) -> float:
    fa = f(a) - level
    for _ in range(40):
        if b - a < 0.5:
            break
        m = (a + b) / 2.0
        fm = f(m) - level
        if (fm < 0) == (fa < 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2.0


def crossings(
    f: Callable[[float], float], t0: float, t1: float, level: float, step: float
) -> list[tuple[float, bool]]:
    """Times where ``f`` crosses *level* in ``[t0, t1]``, with ``rising`` (to ½ s)."""
    found: list[tuple[float, bool]] = []
    a, fa = t0, f(t0) - level
    while a < t1:
        b = min(a + step, t1)
        fb = f(b) - level
        if (fa < 0) != (fb < 0):
            found.append((_bisect(f, a, b, level), fb >= 0))
        a, fa = b, fb
    return found


def intervals(
    f: Callable[[float], float], t0: float, t1: float, level: float, step: float, above: bool
) -> list[tuple[float, float]]:
    """Maximal intervals of ``[t0, t1]`` where ``f >= level`` (*above*) or ``f < level``."""

    def inside(value: float) -> bool:
        return value >= level if above else value < level

    result: list[tuple[float, float]] = []
    start = t0 if inside(f(t0)) else None
    for t, rising in crossings(f, t0, t1, level, step):
        entering = rising if above else not rising
        if entering:
            start = t
        elif start is not None:
            result.append((start, t))
            start = None
    if start is not None:
        result.append((start, t1))
    return result


def night_of(day: date, lat: float, lon: float) -> dict[str, Any]:
    """Twilight instants and the astronomical night of the evening of *day*."""
    t0 = solar_noon(day, lon)
    t1 = t0 + 86400.0

    def sun(t: float) -> float:
        return sun_altitude(t, lat, lon)

    def first(level: float, rising: bool) -> float | None:
        hits = [t for t, up in crossings(sun, t0, t1, level, 300.0) if up == rising]
        if not hits:
            return None
        return hits[-1] if rising else hits[0]

    dark = intervals(sun, t0, t1, ASTRONOMICAL_DEG, 300.0, above=False)
    night = max(dark, key=lambda span: span[1] - span[0]) if dark else None
    return {
        "date": day.isoformat(),
        "noon": t0,
        "next_noon": t1,
        "dusk": night[0] if night else None,
        "dawn": night[1] if night else None,
        "twilight": {
            "sunset_utc": first(SUNSET_DEG, False),
            "civil_dusk_utc": first(CIVIL_DEG, False),
            "nautical_dusk_utc": first(NAUTICAL_DEG, False),
            "astronomical_dusk_utc": first(ASTRONOMICAL_DEG, False),
            "astronomical_dawn_utc": first(ASTRONOMICAL_DEG, True),
            "nautical_dawn_utc": first(NAUTICAL_DEG, True),
            "civil_dawn_utc": first(CIVIL_DEG, True),
            "sunrise_utc": first(SUNSET_DEG, True),
        },
    }


def current_night_date(now: float, lat: float, lon: float) -> date:
    """The night whose dawn has not passed yet (P3: 02:00 belongs to last evening's)."""
    day = night_date_for(now, lon)
    dawn = night_of(day, lat, lon)["dawn"]
    if dawn is not None and dawn <= now:
        day += timedelta(days=1)
    return day


def visibility(
    ra_hours: float,
    dec_deg: float,
    lat: float,
    lon: float,
    day: date,
    *,
    step_min: int = 10,
    min_alt_deg: float = DEFAULT_MIN_ALT_DEG,
) -> dict[str, Any]:
    """Altitude samples, peak and the window above *min_alt_deg* in the astronomical night."""
    night = night_of(day, lat, lon)
    tw = night["twilight"]
    t0, t1 = night["noon"], night["next_noon"]
    step = step_min * 60.0

    def alt(t: float) -> float:
        return altitude_at(jd_of(t), ra_hours, dec_deg, lat, lon)

    start = tw["sunset_utc"] - 3600.0 if tw["sunset_utc"] is not None else t0 + 4 * 3600.0
    end = tw["sunrise_utc"] + 3600.0 if tw["sunrise_utc"] is not None else t0 + 20 * 3600.0
    start = max(t0, math.floor(start / step) * step)
    end = min(t1, math.ceil(end / step) * step)
    samples = []
    t = start
    while t <= end + 1e-6:
        samples.append(
            {
                "t_utc": _iso(t),
                "alt_deg": round(alt(t), 3),
                "sun_alt_deg": round(sun_altitude(t, lat, lon), 3),
            }
        )
        t += step

    notes: list[str] = []
    dusk, dawn = night["dusk"], night["dawn"]
    windows: list[tuple[float, float]] = []
    if dusk is not None and dawn is not None:
        windows = intervals(alt, dusk, dawn, min_alt_deg, 60.0, above=True)
        span = (dusk, dawn)
        if not windows:
            notes.append(f"The target stays below {min_alt_deg:g}° during the astronomical night.")
    else:
        span = (start, end)
        notes.append(
            "The Sun stays above −18° all night: no astronomical darkness at this site "
            f"on the night of {night['date']}."
        )
    peak_t, peak_alt = span[0], alt(span[0])
    t = span[0]
    while t <= span[1]:
        value = alt(t)
        if value > peak_alt:
            peak_t, peak_alt = t, value
        t += 60.0
    if alt(span[1]) > peak_alt:
        peak_t, peak_alt = span[1], alt(span[1])
    longest = max(windows, key=lambda w: w[1] - w[0]) if windows else None
    return {
        "target": {"ra_hours": ra_hours, "dec_deg": dec_deg},
        "night": {"date": night["date"], "dusk_utc": _iso(dusk), "dawn_utc": _iso(dawn)},
        "twilight": {key: _iso(value) for key, value in tw.items()},
        "samples": samples,
        "peak": {"t_utc": _iso(peak_t), "alt_deg": round(peak_alt, 3)},
        "window": (
            {"start_utc": _iso(longest[0]), "end_utc": _iso(longest[1])} if longest else None
        ),
        "windows": [{"start_utc": _iso(a), "end_utc": _iso(b)} for a, b in windows],
        "min_alt_deg": min_alt_deg,
        "step_min": step_min,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def exoplanet_record(target: ExoplanetTarget) -> dict[str, Any]:
    return {
        "planet_name": target.planet_name,
        "host_name": target.host_name,
        "ra_hours": target.ra_degrees / 15.0,
        "dec_deg": target.dec_degrees,
        "period_days": target.period_days,
        "epoch_bjd_tdb": target.epoch_bjd_tdb,
        "duration_hours": target.duration_hours,
        "depth_percent": target.depth_percent,
        "period_error_days": target.period_error_days,
        "epoch_error_days": target.epoch_error_days,
        "epoch_system": target.epoch_system,
        "source": target.source,
        "retrieved_utc": target.retrieved_utc,
    }


def window_record(window: TransitWindow) -> dict[str, Any]:
    return {**asdict(window), "coverage_hours": window.coverage_hours}


def lookup_error(exc: ExoplanetLookupError) -> ApiError:
    """The core's text with a contract code."""
    message = str(exc)
    if message.startswith("Enter a planet"):
        return ApiError(400, "invalid_argument", message)
    if message.startswith("No confirmed transiting planet"):
        return ApiError(404, "not_found", message)
    if "unavailable" in message or "search failed" in message:
        return ApiError(502, "lookup_failed", message)
    return ApiError(422, "ephemeris_unusable", message)


# ---------------------------------------------------------------------------
# Bodies
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class TransitBody(_Strict):
    planet_name: str = Field(min_length=1, max_length=120)
    baseline_minutes: float = Field(default=60.0, ge=-1e6, le=1e6)
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    from_utc: str | None = Field(default=None, max_length=40)
    epoch_number: int | None = Field(default=None, ge=-10_000_000, le=10_000_000)
    observable_only: bool = True


class TransitPlanBody(TransitBody):
    exposure_s: float = Field(default=10.0, ge=-1e9, le=1e9)
    cadence_s: float = Field(default=13.0, ge=-1e9, le=1e9)
    gain: int = Field(default=80, ge=-1_000_000_000, le=1_000_000_000)
    filter_name: str | None = Field(default=None, min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


class PlanningService:
    """Routes A42, A65 and A66 (the draft itself is :class:`PlanService`)."""

    def __init__(self, hub: "Hub", clock: Callable[[], datetime] | None = None) -> None:
        self._hub = hub
        self.clock: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        #: Injectable lookups (tests: no network).
        self.lookup: Callable[..., ExoplanetTarget] = exoplanets.lookup_exoplanet
        self.suggest_names: Callable[..., list[str]] = exoplanets.cached_exoplanet_suggestions

    # -- site and settings ---------------------------------------------------------------

    def _site(self, message: str = SITE_MISSING) -> tuple[float, float, float]:
        site = observing_site(self._hub.config)
        if site is None:
            raise ApiError(409, "site_missing", message)
        return site

    def _site_record(self) -> dict[str, Any]:
        lat, lon, elev = self._site()
        name = str(self._hub.config.get("site.name", "") or "")
        return {"name": name, "latitude_deg": lat, "longitude_deg": lon, "elevation_m": elev}

    def min_altitude(self) -> float:
        value = self._hub.config.get(MIN_ALT_KEY, DEFAULT_MIN_ALT_DEG)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return DEFAULT_MIN_ALT_DEG
        return number if math.isfinite(number) else DEFAULT_MIN_ALT_DEG

    # -- A65 -----------------------------------------------------------------------------

    def visibility(
        self,
        ra_hours: float,
        dec_deg: float,
        night: str | None = None,
        step_min: int = 10,
        min_alt_deg: float | None = None,
    ) -> dict[str, Any]:
        site = self._site_record()
        lat, lon = site["latitude_deg"], site["longitude_deg"]
        if night is not None:
            try:
                day = date.fromisoformat(night)
            except ValueError as exc:
                raise ApiError(400, "invalid_argument", "night: a date YYYY-MM-DD") from exc
        else:
            day = current_night_date(self.clock().timestamp(), lat, lon)
        source = "query" if min_alt_deg is not None else "site"
        limit = min_alt_deg if min_alt_deg is not None else self.min_altitude()
        record = visibility(
            float(ra_hours) % 24.0, dec_deg, lat, lon, day, step_min=step_min, min_alt_deg=limit
        )
        return {"site": site, **record, "min_alt_source": source}

    # -- A42 -----------------------------------------------------------------------------

    def _cache_path(self) -> Path | None:
        value = self._hub.config.get("data_paths.exoplanet_cache", "")
        return Path(str(value)).expanduser() if value else None

    def find(self, query: str) -> ExoplanetTarget:
        try:
            return self.lookup(str(query or ""), timeout_s=12.0, cache_path=self._cache_path())
        except ExoplanetLookupError as exc:
            raise lookup_error(exc) from exc

    def lookup_record(self, query: str) -> dict[str, Any]:
        """``GET /api/exoplanets/lookup`` (``ExoplanetLookupWorker``)."""
        return exoplanet_record(self.find(query))

    def suggest(self, query: str, limit: int = 8) -> dict[str, Any]:
        """``GET /api/exoplanets/suggest``: offline, from the cache."""
        text = str(query or "").strip()
        names: list[str] = []
        if text:
            try:
                names = list(self.suggest_names(text, cache_path=self._cache_path(), limit=limit))
            except Exception as exc:  # a corrupt cache must not break typing
                logger.warning("Exoplanet suggestions failed: %s", exc)
        return {"query": text, "names": names[:limit]}

    # -- A66 -----------------------------------------------------------------------------

    def _search_start(self, body: TransitBody, lon: float) -> datetime:
        if body.date is not None and body.from_utc is not None:
            raise ApiError(400, "invalid_argument", "Give date or from_utc, not both")
        if body.date is not None:
            try:
                day = date.fromisoformat(body.date)
            except ValueError as exc:
                raise ApiError(400, "invalid_argument", "date: a date YYYY-MM-DD") from exc
            return _dt(solar_noon(day, lon))
        if body.from_utc is not None:
            try:
                return parse_utc(body.from_utc)
            except ValueError as exc:
                raise ApiError(
                    400, "invalid_argument", "from_utc: not an ISO 8601 instant"
                ) from exc
        return self.clock()

    def predict(self, body: TransitBody) -> tuple[ExoplanetTarget, TransitWindow, dict[str, Any]]:
        """The transit window, chosen as Q-P10 says, and its record."""
        site = self._site(SITE_MISSING_TRANSIT)
        if body.baseline_minutes > MAX_BASELINE_MIN:
            raise ApiError(
                400,
                "invalid_argument",
                f"The baseline is at most {MAX_BASELINE_MIN:g} min each side "
                f"({body.baseline_minutes:g} given).",
            )
        target = self.find(body.planet_name)
        start = self._search_start(body, site[1])
        try:
            window, skipped, skipped_count = _choose_transit(
                target,
                site,
                start,
                baseline_minutes=float(body.baseline_minutes),
                observable_only=body.observable_only,
                epoch_number=body.epoch_number,
                min_alt=self.min_altitude(),
            )
        except ValueError as exc:
            raise ApiError(400, "invalid_argument", str(exc)) from exc
        if window is None:
            raise ApiError(
                422,
                "no_observable_transit",
                f"No transit of {target.planet_name} is observable from this site above "
                f"{self.min_altitude():g}° in the next {SEARCH_DAYS:g} days.",
            )
        record = _prediction_record(target, window, site, self.min_altitude())
        record["skipped"] = skipped
        record["skipped_count"] = skipped_count
        return target, window, record

    def predict_record(self, body: TransitBody) -> dict[str, Any]:
        return self.predict(body)[2]

    def plan(self, body: TransitPlanBody) -> dict[str, Any]:
        """``POST /api/transit/plan``: ``_prepare_transit_plan`` made the draft."""
        plans = self._hub.plan  # type: ignore[attr-defined]
        if plans.run_active():
            raise ApiError(409, "run_active", LOCKED_MESSAGE)
        target, window, record = self.predict(body)
        filter_name = body.filter_name
        if filter_name is None:
            filter_name = light_filter_default(plans.filter_names())
        try:
            plan = make_transit_sequence(
                target,
                window,
                exposure_s=float(body.exposure_s),
                cadence_s=float(body.cadence_s),
                gain=int(body.gain),
                filter_name=filter_name,
            )
        except ValueError as exc:
            raise ApiError(400, "invalid_argument", str(exc)) from exc
        # Qt's Find had set the host as the catalogue target (pointing, and the
        # photometry target of an exoplanet programme) before Prepare.
        current = self._hub.observation.target
        if current is None or current.get("name") != target.host_name:
            self._hub.observation.set_target(
                target.host_name,
                target.ra_hours,
                target.dec_degrees,
                object_type="Exoplanet host",
                source=target.source,
                programme="exoplanet",
            )
        start = parse_utc(record["utc"]["coverage_start"])
        notes = [
            f"Transit sequence prepared: {plan.steps[0].count} light frames at a "
            f"{float(body.cadence_s):.1f} s cadence.",
            f"Starts at the coverage start, {start:%Y-%m-%d %H:%M} UTC.",
        ]
        plan_record = plans.set_transit_plan(
            plan, notes, start_at_utc=record["utc"]["coverage_start"]
        )
        self._hub.log(
            "info",
            f"Transit plan: {target.planet_name}, E={window.epoch_number}, "
            f"{plan.steps[0].count} frames from {record['utc']['coverage_start']}",
            source="plan",
            topic="sequence",
        )
        return {"plan": plan_record, "prediction": record}


def _transit_ok(
    t0: float, t1: float, ra_h: float, dec: float, lat: float, lon: float, min_alt: float
) -> str | None:
    """``None`` when ``[t0, t1]`` is dark and above the limit, else the reason."""
    n = max(1, math.ceil((t1 - t0) / TRANSIT_CHECK_S))
    reason = None
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        if sun_altitude(t, lat, lon) >= ASTRONOMICAL_DEG:
            return "daylight"
        if altitude_at(jd_of(t), ra_h, dec, lat, lon) < min_alt:
            reason = "below_limit"
    return reason


def _utc_seconds(bjd: float, correction: float) -> float:
    return (bjd - correction - 2440587.5) * 86400.0


def _bjd_tdb_many(
    jd_utc: list[float], ra: float, dec: float, lat: float, lon: float, elev: float
) -> list[float] | None:
    """``airmass.bjd_tdb`` for many instants in one astropy call (same arithmetic)."""
    try:
        import astropy.units as u
        from astropy.coordinates import EarthLocation, SkyCoord
        from astropy.time import Time

        from argos.core.photometry.airmass import _bundled_iers_only

        _bundled_iers_only()
        t = Time(jd_utc, format="jd", scale="utc")
        loc = EarthLocation.from_geodetic(lon=lon * u.deg, lat=lat * u.deg, height=elev * u.m)
        target = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
        ltt = t.light_travel_time(target, kind="barycentric", location=loc)
        return [float(v) for v in (t.tdb + ltt).jd]
    except Exception:  # pragma: no cover - astropy missing: the coarse correction stays
        return None


def _corrections(
    mids: list[float], correction: float, ra: float, dec: float, site: tuple[float, float, float]
) -> list[float]:
    """BJD_TDB − JD_UTC at each mid-transit (two fixed-point passes, converged to µs)."""
    lat, lon, elev = site
    out = [correction] * len(mids)
    for _ in range(2):
        guess = [m - c for m, c in zip(mids, out)]
        exact = _bjd_tdb_many(guess, ra, dec, lat, lon, elev)
        if exact is None:
            return out
        out = [e - g for e, g in zip(exact, guess)]
    return out


def _choose_transit(
    target: ExoplanetTarget,
    site: tuple[float, float, float],
    start: datetime,
    *,
    baseline_minutes: float,
    observable_only: bool,
    epoch_number: int | None,
    min_alt: float,
) -> tuple[TransitWindow | None, list[dict[str, Any]], int]:
    """``predict_next_transit`` from *start*, skipping unobservable transits (Q-P10)."""
    lat, lon, elev = site
    ra, dec = target.ra_degrees, target.dec_degrees
    if epoch_number is not None:
        anchor = target.epoch_bjd_tdb + (epoch_number - 0.5) * target.period_days
        return (
            predict_next_transit(target, anchor, baseline_minutes=baseline_minutes),
            [],
            0,
        )
    # Qt's _current_bjd_tdb (sequencer_page.py:132-145), at the search start.
    from_bjd = bjd_tdb(julian_date(start), ra, dec, lat, lon, elev)
    if from_bjd is None:
        raise ApiError(500, "internal_error", "BJD_TDB conversion unavailable")
    window = predict_next_transit(target, from_bjd, baseline_minutes=baseline_minutes)
    if not observable_only:
        return window, [], 0
    limit = from_bjd + SEARCH_DAYS
    skipped: list[dict[str, Any]] = []
    count = 0
    correction = from_bjd - julian_date(start)  # BJD_TDB − JD_UTC, refined per transit
    half = (window.egress_bjd_tdb - window.ingress_bjd_tdb) / 2.0

    def following(w: TransitWindow) -> TransitWindow:
        return predict_next_transit(
            target, w.mid_bjd_tdb + target.period_days / 2.0, baseline_minutes=baseline_minutes
        )

    while window.mid_bjd_tdb <= limit:
        batch = [window]
        while len(batch) < TRANSIT_BATCH:
            nxt = following(batch[-1])
            if nxt.mid_bjd_tdb > limit:
                break
            batch.append(nxt)
        corrections = _corrections(
            [w.mid_bjd_tdb for w in batch], correction, ra, dec, (lat, lon, elev)
        )
        for candidate, correction in zip(batch, corrections):
            mid = _utc_seconds(candidate.mid_bjd_tdb, correction)
            reason = _transit_ok(
                mid - half * 86400.0, mid + half * 86400.0, ra / 15.0, dec, lat, lon, min_alt
            )
            if reason is None:
                return candidate, skipped, count
            count += 1
            if len(skipped) < SKIPPED_LISTED:
                skipped.append(
                    {"epoch_number": candidate.epoch_number, "mid_utc": _iso(mid), "reason": reason}
                )
        window = following(batch[-1])
    return None, skipped, count


def _prediction_record(
    target: ExoplanetTarget,
    window: TransitWindow,
    site: tuple[float, float, float],
    min_alt: float,
) -> dict[str, Any]:
    """Instants as ``_local_transit_window`` (``utc_from_bjd_tdb``), altitudes, the night."""
    lat, lon, elev = site
    ra, dec = target.ra_degrees, target.dec_degrees
    instants = {
        "coverage_start": window.coverage_start_bjd_tdb,
        "ingress": window.ingress_bjd_tdb,
        "mid": window.mid_bjd_tdb,
        "egress": window.egress_bjd_tdb,
        "coverage_end": window.coverage_end_bjd_tdb,
    }
    seconds: dict[str, float] = {}
    for key, bjd in instants.items():
        when = utc_from_bjd_tdb(bjd, ra, dec, lat, lon, elev)
        if when is None:
            raise ApiError(500, "internal_error", "BJD_TDB conversion unavailable")
        seconds[key] = when.timestamp()
    ra_h = ra / 15.0
    night = night_of(night_date_for(seconds["mid"], lon), lat, lon)

    def ok(t: float) -> bool:
        return (
            sun_altitude(t, lat, lon) < ASTRONOMICAL_DEG
            and altitude_at(jd_of(t), ra_h, dec, lat, lon) >= min_alt
        )

    usable: tuple[float, float] | None = None
    t, run_start = seconds["coverage_start"], None
    spans: list[tuple[float, float]] = []
    while t <= seconds["coverage_end"] + 1e-6:
        if ok(t):
            run_start = t if run_start is None else run_start
            last = t
        elif run_start is not None:
            spans.append((run_start, last))
            run_start = None
        t += 60.0
    if run_start is not None:
        spans.append((run_start, last))
    if spans:
        holding = [s for s in spans if s[0] <= seconds["mid"] <= s[1]]
        usable = holding[0] if holding else max(spans, key=lambda s: s[1] - s[0])
    transit_reason = _transit_ok(
        seconds["ingress"], seconds["egress"], ra_h, dec, lat, lon, min_alt
    )
    coverage_reason = _transit_ok(
        seconds["coverage_start"], seconds["coverage_end"], ra_h, dec, lat, lon, min_alt
    )
    return {
        "planet": exoplanet_record(target),
        "window": window_record(window),
        "utc": {key: _iso(value) for key, value in seconds.items()},
        "altitude_deg": {
            key: round(altitude_at(jd_of(value), ra_h, dec, lat, lon), 3)
            for key, value in seconds.items()
        },
        "sun_alt_deg": {
            key: round(sun_altitude(value, lat, lon), 3) for key, value in seconds.items()
        },
        "night": {
            "date": night["date"],
            "dusk_utc": _iso(night["dusk"]),
            "dawn_utc": _iso(night["dawn"]),
        },
        "observable": {"transit": transit_reason is None, "coverage": coverage_reason is None},
        "usable": ({"start_utc": _iso(usable[0]), "end_utc": _iso(usable[1])} if usable else None),
        "min_alt_deg": min_alt,
    }
