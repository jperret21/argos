/**
 * Low-precision astronomy for the chart lab: Sun, Moon, target altitude,
 * twilight crossings, Julian dates and an approximate BJD_TDB.
 *
 * Accuracy (enough to draw a night, not to reduce data):
 * - Sun: Astronomical Almanac low-precision formulae, about 0.01 deg.
 * - Moon: the Almanac's 6-term series, about 0.3 deg, topocentric parallax
 *   applied to the altitude only.
 * - BJD: heliocentric light time (Earth = minus the Sun's geocentric vector)
 *   plus TT - UTC = 69.184 s. The Sun-barycentre offset is ignored, so the
 *   value is within about 4 s of a true BJD_TDB. In ARGOS the server computes
 *   the exact BJD_TDB (astropy); the lab labels its values "approx.".
 *
 * Pure functions on unix seconds (UTC), degrees in and out. No DOM, no
 * Svelte: unit-tested in node (astro.test.ts).
 */

const RAD = Math.PI / 180;
const DEG = 180 / Math.PI;

export const JD_UNIX_EPOCH = 2440587.5;
/** TT - UTC since 2017-01-01 (37 leap seconds + 32.184 s). */
export const TT_MINUS_UTC_S = 69.184;
/** Speed of light, AU per day. */
const C_AU_PER_DAY = 173.144633;

export interface Site {
  name: string;
  lat: number;
  /** East positive. */
  lon: number;
  /** UTC offset of the observer's civil time, hours (display only). */
  utcOffsetH: number;
}

export interface RaDec {
  /** Degrees. */
  ra: number;
  dec: number;
}

export function jdFromUnix(t: number): number {
  return t / 86400 + JD_UNIX_EPOCH;
}

export function unixFromJd(jd: number): number {
  return (jd - JD_UNIX_EPOCH) * 86400;
}

const norm360 = (x: number) => ((x % 360) + 360) % 360;

/** Greenwich mean sidereal time, degrees (IAU 1982, linear term; 0.1 s/century drift is irrelevant here). */
export function gmstDeg(jd: number): number {
  return norm360(280.46061837 + 360.98564736629 * (jd - 2451545.0));
}

/** Sun: apparent geocentric RA/Dec (deg), distance (AU) and ecliptic longitude. */
export function sunPosition(jd: number): RaDec & { r: number; lambda: number; eps: number } {
  const n = jd - 2451545.0;
  const L = norm360(280.46 + 0.9856474 * n);
  const g = norm360(357.528 + 0.9856003 * n) * RAD;
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * RAD;
  const eps = (23.439 - 0.0000004 * n) * RAD;
  const r = 1.00014 - 0.01671 * Math.cos(g) - 0.00014 * Math.cos(2 * g);
  const ra = norm360(Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda)) * DEG);
  const dec = Math.asin(Math.sin(eps) * Math.sin(lambda)) * DEG;
  return { ra, dec, r, lambda: lambda * DEG, eps: eps * DEG };
}

/** Moon: geocentric RA/Dec (deg), horizontal parallax (deg) and illuminated fraction. */
export function moonPosition(jd: number): RaDec & { parallax: number; illumination: number } {
  const T = (jd - 2451545.0) / 36525;
  const s = (a: number, b: number) => Math.sin((a + b * T) * RAD);
  const c = (a: number, b: number) => Math.cos((a + b * T) * RAD);
  const lambda =
    218.32 +
    481267.881 * T +
    6.29 * s(135.0, 477198.87) -
    1.27 * s(259.3, -413335.36) +
    0.66 * s(235.7, 890534.22) +
    0.21 * s(269.9, 954397.74) -
    0.19 * s(357.5, 35999.05) -
    0.11 * s(186.5, 966404.03);
  const beta = 5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15) - 0.17 * s(217.6, -407332.21);
  const parallax =
    0.9508 + 0.0518 * c(134.9, 477198.85) + 0.0095 * c(259.2, -413335.38) + 0.0078 * c(235.7, 890534.23) + 0.0028 * c(269.9, 954397.7);
  const sun = sunPosition(jd);
  const eps = sun.eps * RAD;
  const l = lambda * RAD;
  const b = beta * RAD;
  const x = Math.cos(b) * Math.cos(l);
  const y = Math.cos(eps) * Math.cos(b) * Math.sin(l) - Math.sin(eps) * Math.sin(b);
  const z = Math.sin(eps) * Math.cos(b) * Math.sin(l) + Math.cos(eps) * Math.sin(b);
  const ra = norm360(Math.atan2(y, x) * DEG);
  const dec = Math.asin(z) * DEG;
  // Elongation from the Sun, then the phase angle (Moon much closer than the Sun).
  const cosPsi = Math.cos(b) * Math.cos(l - sun.lambda * RAD);
  const illumination = (1 - cosPsi) / 2;
  return { ra, dec, parallax, illumination };
}

export interface Horizontal {
  alt: number;
  /** Azimuth from north through east, degrees. */
  az: number;
  /** Hour angle, degrees in (-180, 180]. */
  ha: number;
}

export function horizontal(pos: RaDec, site: Site, t: number): Horizontal {
  const jd = jdFromUnix(t);
  let ha = norm360(gmstDeg(jd) + site.lon - pos.ra);
  if (ha > 180) ha -= 360;
  const H = ha * RAD;
  const phi = site.lat * RAD;
  const d = pos.dec * RAD;
  const sinAlt = Math.sin(phi) * Math.sin(d) + Math.cos(phi) * Math.cos(d) * Math.cos(H);
  const alt = Math.asin(Math.max(-1, Math.min(1, sinAlt)));
  const az = Math.atan2(-Math.sin(H) * Math.cos(d), Math.cos(phi) * Math.sin(d) - Math.sin(phi) * Math.cos(d) * Math.cos(H));
  return { alt: alt * DEG, az: norm360(az * DEG), ha };
}

export function sunAltitude(site: Site, t: number): number {
  return horizontal(sunPosition(jdFromUnix(t)), site, t).alt;
}

/** Topocentric Moon altitude (parallax lowers it by up to ~1 deg). */
export function moonAltitude(site: Site, t: number): number {
  const m = moonPosition(jdFromUnix(t));
  const geo = horizontal(m, site, t).alt;
  return geo - m.parallax * Math.cos(geo * RAD);
}

/** Kasten & Young (1989); finite down to the horizon. */
export function airmass(altDeg: number): number {
  const h = Math.max(altDeg, 0);
  return 1 / (Math.sin(h * RAD) + 0.50572 * Math.pow(h + 6.07995, -1.6364));
}

/** Angular separation, degrees. */
export function separation(a: RaDec, b: RaDec): number {
  const d1 = a.dec * RAD;
  const d2 = b.dec * RAD;
  const c = Math.sin(d1) * Math.sin(d2) + Math.cos(d1) * Math.cos(d2) * Math.cos((a.ra - b.ra) * RAD);
  return Math.acos(Math.max(-1, Math.min(1, c))) * DEG;
}

/**
 * Approximate BJD_TDB for an exposure mid-time: JD_UTC + (TT - UTC) + the
 * light-time projection of the Earth's heliocentric position on the target
 * direction. Within about 4 s of the exact value (see the header).
 */
export function bjdApprox(t: number, target: RaDec): number {
  const jd = jdFromUnix(t);
  const sun = sunPosition(jd);
  const l = sun.lambda * RAD;
  const e = sun.eps * RAD;
  // Earth = minus the Sun's geocentric vector.
  const ex = -sun.r * Math.cos(l);
  const ey = -sun.r * Math.cos(e) * Math.sin(l);
  const ez = -sun.r * Math.sin(e) * Math.sin(l);
  const a = target.ra * RAD;
  const d = target.dec * RAD;
  const proj = ex * Math.cos(d) * Math.cos(a) + ey * Math.cos(d) * Math.sin(a) + ez * Math.sin(d);
  return jd + TT_MINUS_UTC_S / 86400 + proj / C_AU_PER_DAY;
}

/** Times (unix s) where f(t) crosses `level` within [t0, t1], refined by bisection to 1 s. */
export function crossings(f: (t: number) => number, level: number, t0: number, t1: number, step = 120): { t: number; rising: boolean }[] {
  const out: { t: number; rising: boolean }[] = [];
  let ta = t0;
  let fa = f(ta) - level;
  for (let tb = t0 + step; tb <= t1 + step - 1e-9; tb += step) {
    const tt = Math.min(tb, t1);
    const fb = f(tt) - level;
    if ((fa < 0 && fb >= 0) || (fa >= 0 && fb < 0)) {
      let lo = ta;
      let hi = tt;
      let flo = fa;
      while (hi - lo > 1) {
        const mid = (lo + hi) / 2;
        const fm = f(mid) - level;
        if ((flo < 0 && fm < 0) || (flo >= 0 && fm >= 0)) {
          lo = mid;
          flo = fm;
        } else hi = mid;
      }
      out.push({ t: (lo + hi) / 2, rising: fa < 0 });
    }
    ta = tt;
    fa = fb;
    if (tt >= t1) break;
  }
  return out;
}

/** Time of the maximum of f in [t0, t1] (golden-section after a coarse scan). */
export function maximum(f: (t: number) => number, t0: number, t1: number, step = 300): { t: number; value: number } {
  let best = t0;
  let bestV = -Infinity;
  for (let t = t0; t <= t1; t += step) {
    const v = f(t);
    if (v > bestV) {
      bestV = v;
      best = t;
    }
  }
  let a = Math.max(t0, best - step);
  let b = Math.min(t1, best + step);
  const g = (Math.sqrt(5) - 1) / 2;
  while (b - a > 1) {
    const c = b - g * (b - a);
    const d = a + g * (b - a);
    if (f(c) > f(d)) b = d;
    else a = c;
  }
  const t = (a + b) / 2;
  return { t, value: f(t) };
}

/** Twilight levels of the Sun's altitude, degrees (sunset uses the standard -0.833). */
export const TWILIGHT = {
  sunset: -0.833,
  civil: -6,
  nautical: -12,
  astronomical: -18,
} as const;
