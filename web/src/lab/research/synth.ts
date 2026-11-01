/**
 * Synthetic, deterministic data for the lab demos (seeded PRNG, so every
 * screenshot is reproducible). Shapes and noise levels are realistic for a
 * Seestar S50 night; nothing here is a measurement.
 */

/** mulberry32: small, fast, seedable. */
export function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Standard normal deviate (Box-Muller) from a uniform source. */
export function gauss(rand: () => number): number {
  let u = 0;
  while (u === 0) u = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
}

// -- Light curve ---------------------------------------------------------------

/** Night start: 2026-11-01 18:30:00 UTC, unix seconds. */
export const NIGHT_START = Date.UTC(2026, 10, 1, 18, 30, 0) / 1000;
export const CADENCE_S = 60;

const PERIOD_D = 0.4423; // RRab-like period, days
const M_BRIGHT = 9.31;
const M_FAINT = 10.18;
const CHECK_MAG = 10.412;

/** RRab-like template: fast rise (15 % of the period), slow decline. */
export function rrabMag(phase: number): number {
  const p = phase - Math.floor(phase);
  const amp = M_FAINT - M_BRIGHT;
  if (p < 0.15) {
    const s = p / 0.15;
    return M_FAINT - amp * (s * s * (3 - 2 * s));
  }
  const k = 0.35;
  return M_BRIGHT + (amp * (1 - Math.exp(-(p - 0.15) / k))) / (1 - Math.exp(-0.85 / k));
}

export function unixToJd(t: number): number {
  return t / 86400 + 2440587.5;
}

/** Altitude (deg) of a dec +29 deg target from latitude 48.85 N, transit at 22:40 UTC. */
export function altitudeAt(t: number): number {
  const lat = (48.85 * Math.PI) / 180;
  const dec = (29 * Math.PI) / 180;
  const transit = Date.UTC(2026, 10, 1, 22, 40, 0) / 1000;
  const ha = (((t - transit) / 86164) * 2 * Math.PI) % (2 * Math.PI);
  const s = Math.sin(lat) * Math.sin(dec) + Math.cos(lat) * Math.cos(dec) * Math.cos(ha);
  return (Math.asin(s) * 180) / Math.PI;
}

export function airmass(altDeg: number): number {
  // Kasten & Young (1989).
  const h = Math.max(altDeg, 0.5);
  return 1 / (Math.sin((h * Math.PI) / 180) + 0.50572 * Math.pow(h + 6.07995, -1.6364));
}

export interface CurvePoint {
  t: number;
  target: number;
  targetErr: number;
  check: number;
  checkErr: number;
  hfd: number;
}

/** One measurement per cadence step; `i` is the frame index of the night. */
export function curvePoint(i: number, rand: () => number, cadence = CADENCE_S): CurvePoint {
  const t = NIGHT_START + i * cadence;
  const am = airmass(altitudeAt(t));
  const phase = unixToJd(t) / PERIOD_D + 0.31;
  const m = rrabMag(phase);
  // Photon + scintillation-like error, growing with magnitude and airmass.
  const cloud = i % 173 > 168 ? 3.2 : 1; // a short cloud passage now and then
  const errT = (0.0045 * Math.pow(10, 0.2 * (m - 9.3)) + 0.0025 * (am - 1)) * cloud;
  const errC = (0.0062 + 0.0025 * (am - 1)) * cloud;
  const hfd = 2.05 + 0.18 * Math.sin(i / 70) + 0.22 * (am - 1) + 0.05 * gauss(rand) + (cloud > 1 ? 0.6 : 0);
  return {
    t,
    target: m + errT * gauss(rand),
    targetErr: errT,
    check: CHECK_MAG + errC * gauss(rand),
    checkErr: errC,
    hfd,
  };
}

/** Column store, the shape uPlot wants (no per-point objects). */
export interface CurveColumns {
  t: Float64Array;
  target: Float64Array;
  targetErr: Float64Array;
  check: Float64Array;
  checkErr: Float64Array;
  hfd: Float64Array;
  length: number;
}

export function emptyColumns(capacity: number): CurveColumns {
  return {
    t: new Float64Array(capacity),
    target: new Float64Array(capacity),
    targetErr: new Float64Array(capacity),
    check: new Float64Array(capacity),
    checkErr: new Float64Array(capacity),
    hfd: new Float64Array(capacity),
    length: 0,
  };
}

/** Append in place, growing the buffers by doubling (amortised O(1)). */
export function appendPoint(c: CurveColumns, p: CurvePoint): CurveColumns {
  if (c.length === c.t.length) {
    const grow = (a: Float64Array) => {
      const b = new Float64Array(a.length * 2);
      b.set(a);
      return b;
    };
    c = {
      t: grow(c.t),
      target: grow(c.target),
      targetErr: grow(c.targetErr),
      check: grow(c.check),
      checkErr: grow(c.checkErr),
      hfd: grow(c.hfd),
      length: c.length,
    };
  }
  const i = c.length;
  c.t[i] = p.t;
  c.target[i] = p.target;
  c.targetErr[i] = p.targetErr;
  c.check[i] = p.check;
  c.checkErr[i] = p.checkErr;
  c.hfd[i] = p.hfd;
  c.length = i + 1;
  return c;
}

// -- Frames table --------------------------------------------------------------

export interface FrameRow {
  n: number;
  t: number;
  exp: number;
  filter: 'IRCUT' | 'LP';
  hfd: number;
  stars: number;
  sky: number;
  airmass: number;
  fwhm: number;
  flag: '' | 'cloud' | 'trail' | 'focus';
  file: string;
}

export function frameRows(count: number, seed = 7): FrameRow[] {
  const rand = prng(seed);
  const rows: FrameRow[] = [];
  for (let i = 0; i < count; i++) {
    const t = NIGHT_START + i * 10.6;
    const am = airmass(altitudeAt(t));
    let flag: FrameRow['flag'] = '';
    const r = rand();
    if (r < 0.012) flag = 'cloud';
    else if (r < 0.018) flag = 'trail';
    else if (r < 0.022) flag = 'focus';
    const hfd = 2.0 + 0.2 * (am - 1) + 0.08 * gauss(rand) + (flag === 'focus' ? 1.4 : flag === 'trail' ? 0.9 : 0);
    const stars = Math.max(0, Math.round(410 - 60 * (am - 1) + 12 * gauss(rand) - (flag === 'cloud' ? 300 : 0)));
    const d = new Date(t * 1000);
    const hh = String(d.getUTCHours()).padStart(2, '0');
    const mm = String(d.getUTCMinutes()).padStart(2, '0');
    const ss = String(d.getUTCSeconds()).padStart(2, '0');
    rows.push({
      n: i + 1,
      t,
      exp: 10,
      filter: i % 900 < 600 ? 'IRCUT' : 'LP',
      hfd,
      stars,
      sky: 1790 + 40 * (am - 1) + 6 * gauss(rand) + (flag === 'cloud' ? 220 : 0),
      airmass: am,
      fwhm: hfd * 2.4 * 0.86,
      flag,
      file: `Light_SW-And_10.0s_IRCUT_20261101-${hh}${mm}${ss}.fit`,
    });
  }
  return rows;
}

// -- Comparison ensemble -------------------------------------------------------

export interface CompStar {
  id: string;
  label: string;
  v: number;
  rms: number;
}

export function comparisonStars(): CompStar[] {
  const rand = prng(11);
  const labels = ['93', '96', '99', '102', '104', '108', '111', '115'];
  return labels.map((label, i) => ({
    id: `000-BCX-${(312 + i * 17).toString().padStart(3, '0')}`,
    label,
    v: Number(label) / 10 + 0.02 * gauss(rand),
    rms: 0.006 + 0.012 * rand(),
  }));
}
