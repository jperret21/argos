/**
 * A synthetic observing night for the chart lab: SW And (an RRab star) from
 * Paris on 2026-11-01, measured by a Seestar-like instrument.
 *
 * Every number is generated (seeded, deterministic per frame index), but the
 * shapes follow the physics and the owner's real nights
 * (lab/research/functional-spaces.md): a ~51.5 s median cadence, two
 * autofocus pauses, three cloud passages that dim every star but cancel in
 * the differential magnitude, extinction with airmass, a focus loss at
 * 22:16 UTC that triples the HFD until the 23:31 autofocus, a saturated
 * target near maximum light, a satellite trail flagged suspect, and a Moon
 * that rises after midnight and brightens the sky.
 *
 * Nothing here is a measurement. Star labels are synthetic on purpose (no
 * real AUID is implied).
 */

import { airmass, bjdApprox, horizontal, jdFromUnix, moonAltitude, type RaDec, type Site } from './astro';

export const SITE: Site = { name: 'Paris', lat: 48.8566, lon: 2.3522, utcOffsetH: 1 };

export interface StarDef {
  key: string;
  label: string;
  role: 'target' | 'comparison' | 'check';
  /** Catalogue V (comparisons, check) or the mean V of the target. */
  v: number;
  pos: RaDec;
}

const hms = (h: number, m: number, s: number) => (h + m / 60 + s / 3600) * 15;
const dms = (d: number, m: number, s: number) => Math.sign(d || 1) * (Math.abs(d) + m / 60 + s / 3600);

export const TARGET: StarDef = { key: 'T', label: 'SW And', role: 'target', v: 9.7, pos: { ra: hms(0, 23, 43.1), dec: dms(29, 24, 4) } };
export const CHECK: StarDef = { key: 'K', label: 'K · V 10.41', role: 'check', v: 10.412, pos: { ra: hms(0, 24, 2.0), dec: dms(29, 31, 40) } };
export const COMPS: StarDef[] = [
  { key: 'C1', label: 'C1 · V 9.92', role: 'comparison', v: 9.921, pos: { ra: hms(0, 23, 11.4), dec: dms(29, 19, 2) } },
  { key: 'C2', label: 'C2 · V 10.31', role: 'comparison', v: 10.308, pos: { ra: hms(0, 24, 20.8), dec: dms(29, 14, 51) } },
  { key: 'C3', label: 'C3 · V 10.77', role: 'comparison', v: 10.766, pos: { ra: hms(0, 22, 58.0), dec: dms(29, 33, 15) } },
  { key: 'C4', label: 'C4 · V 11.05', role: 'comparison', v: 11.047, pos: { ra: hms(0, 24, 47.3), dec: dms(29, 27, 30) } },
  { key: 'C5', label: 'C5 · V 11.38', role: 'comparison', v: 11.384, pos: { ra: hms(0, 23, 31.9), dec: dms(29, 8, 44) } },
];

const T = (h: number, m: number, s = 0, day = 1) => Date.UTC(2026, 10, day, h, m, s) / 1000;

export const NIGHT_LABEL = '2026-11-01';
export const RUN_START = T(18, 40);
export const RUN_END = T(2, 5, 0, 2);
/** Autofocus runs (the sequence pauses ~3.4 min each). */
export const AUTOFOCUS = [T(20, 31), T(23, 31)];
/** The focus loss (dew / slipped focus) the 23:31 autofocus repairs. */
export const FOCUS_LOSS = T(22, 16, 0);
/** Cloud passages: centre, peak extinction (mag), half-width (s). */
const CLOUDS: [number, number, number][] = [
  [T(19, 52), 0.55, 240],
  [T(21, 6), 1.2, 360],
  [T(23, 58), 0.35, 180],
];
/** A satellite trail crosses the target aperture (flagged suspect by the pipeline). */
const TRAILS = [T(20, 12, 30), T(0, 41, 10, 2)];

/** RRab ephemeris (synthetic, shaped like SW And): maximum light at 22:02 UTC. */
const PERIOD_D = 0.44226;
const EPOCH_MAX_BJD = 2461346.4181;
const M_BRIGHT = 9.31;
const M_FAINT = 10.18;
const EXTINCTION_K = 0.21;
const ZERO_POINT = -12.05;
const C4_AMPLITUDE = 0.028; // the comparison that is not quite constant

export const FLAG_SUSPECT = 1;
export const FLAG_SATURATED = 2;

/** mulberry32. */
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

export function gauss(rand: () => number): number {
  let u = 0;
  while (u === 0) u = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
}

/** RRab template: fast rise over 15 % of the period, slow decline. phase 0 = maximum. */
export function rrab(phase: number): number {
  const p = phase - Math.floor(phase);
  const amp = M_FAINT - M_BRIGHT;
  if (p > 0.85) {
    const s = (p - 0.85) / 0.15;
    return M_FAINT - amp * (s * s * (3 - 2 * s));
  }
  const k = 0.32;
  return M_BRIGHT + (amp * (1 - Math.exp(-p / k))) / (1 - Math.exp(-0.85 / k));
}

export function cloudAt(t: number): number {
  let m = 0;
  for (const [c, a, w] of CLOUDS) m += a * Math.exp(-0.5 * ((t - c) / w) ** 2);
  return m;
}

export function targetTrueMag(t: number): number {
  return rrab((bjdApprox(t, TARGET.pos) - EPOCH_MAX_BJD) / PERIOD_D);
}

// -- Columns ----------------------------------------------------------------------

/** Column store for one night (the shape uPlot wants; no per-point objects). */
export interface NightColumns {
  n: number;
  t: Float64Array;
  /** Approximate BJD_TDB minus JD_UTC, seconds (light time + TT - UTC). */
  bjdOffsetS: Float64Array;
  alt: Float64Array;
  airmass: Float64Array;
  target: Float64Array;
  targetErr: Float64Array;
  /** FLAG_* bits. */
  flags: Uint8Array;
  peakAdu: Float64Array;
  /** Check star minus its catalogue V. */
  checkDelta: Float64Array;
  checkErr: Float64Array;
  /** Comparison ensemble: mean of (instrumental - catalogue) over the stars used. */
  ensOffset: Float64Array;
  /** Spread (1 sigma) of the comparisons around that mean. */
  ensSpread: Float64Array;
  nUsed: Uint8Array;
  /** Leave-one-out residual of each comparison (mag), NaN when not measured. */
  comps: Float64Array[];
  compErr: Float64Array[];
  hfd: Float64Array;
  fwhm: Float64Array;
  stars: Float64Array;
  sky: Float64Array;
  sensorC: Float64Array;
  focuser: Float64Array;
}

function columns(cap: number): NightColumns {
  const f = () => new Float64Array(cap);
  return {
    n: 0,
    t: f(),
    bjdOffsetS: f(),
    alt: f(),
    airmass: f(),
    target: f(),
    targetErr: f(),
    flags: new Uint8Array(cap),
    peakAdu: f(),
    checkDelta: f(),
    checkErr: f(),
    ensOffset: f(),
    ensSpread: f(),
    nUsed: new Uint8Array(cap),
    comps: COMPS.map(f),
    compErr: COMPS.map(f),
    hfd: f(),
    fwhm: f(),
    stars: f(),
    sky: f(),
    sensorC: f(),
    focuser: f(),
  };
}

export interface ScheduleOptions {
  /** Median start-to-start interval, s. */
  cadence: number;
  /** 1 sigma jitter of the interval, s. */
  jitter: number;
  seed: number;
  start?: number;
  end?: number;
}

/** Exposure mid-times of the run: jittered cadence, autofocus pauses. */
export function schedule(o: ScheduleOptions): Float64Array {
  const rand = prng(o.seed);
  const start = o.start ?? RUN_START;
  const end = o.end ?? RUN_END;
  const out: number[] = [];
  let t = start + 6;
  let af = 0;
  while (t < end) {
    out.push(t);
    let dt = o.cadence + o.jitter * gauss(rand);
    if (rand() < 0.02) dt += 25 + 30 * rand(); // live re-identification of the field
    t += Math.max(o.cadence * 0.6, dt);
    if (af < AUTOFOCUS.length && t >= AUTOFOCUS[af]) {
      t = AUTOFOCUS[af] + 204;
      af++;
    }
  }
  return Float64Array.from(out);
}

/** Every frame of the night at once (cheap: ~520 frames at the real cadence, ~6 700 at 4 s). */
export function synthesizeNight(times: Float64Array, seed = 11): NightColumns {
  const n = times.length;
  const c = columns(n);
  let afIdx = 0;
  let lastAf = RUN_START;
  for (let i = 0; i < n; i++) {
    const t = times[i];
    while (afIdx < AUTOFOCUS.length && t >= AUTOFOCUS[afIdx]) lastAf = AUTOFOCUS[afIdx++];
    // Per-frame generator: deterministic whatever the order of evaluation.
    const rand = prng((seed * 7919 + i * 2654435761) >>> 0);
    const h = horizontal(TARGET.pos, SITE, t);
    const X = airmass(h.alt);
    const cloud = cloudAt(t);
    const hoursSinceAf = (t - lastAf) / 3600;
    const lost = t >= FOCUS_LOSS && t < AUTOFOCUS[1] ? 2.65 : 1;
    const hfd = Math.max(1.4, (2.22 + 0.13 * Math.sin(t / 2300) + 0.26 * (X - 1) + 0.1 * hoursSinceAf + 0.055 * gauss(rand)) * lost);
    const fwhm = Math.max(1.1, hfd * 0.84 + 0.045 * gauss(rand));
    const scint = 0.0012 * Math.pow(X, 1.75);
    const sigmaOf = (m: number) =>
      Math.hypot(0.0026 * Math.pow(10, 0.2 * (m - 9.3 + cloud + EXTINCTION_K * (X - 1))) * Math.sqrt(hfd / 2.2), scint);

    // Comparisons: instrumental - catalogue = ZP + kX + cloud + noise (+ C4's small variability).
    let sum = 0;
    let used = 0;
    let varSum = 0;
    const raw: number[] = [];
    for (let j = 0; j < COMPS.length; j++) {
      const s = COMPS[j];
      const lostInCloud = cloud > 0.7 && s.v > 11.0; // faint ones drop out under thick cloud
      const e = sigmaOf(s.v);
      const intrinsic = j === 3 ? C4_AMPLITUDE * Math.sin((2 * Math.PI * jdFromUnix(t)) / 0.137) : 0;
      const r = ZERO_POINT + EXTINCTION_K * X + cloud + intrinsic + e * gauss(rand);
      raw.push(lostInCloud ? NaN : r);
      c.compErr[j][i] = e;
      if (!lostInCloud) {
        sum += r;
        used++;
        varSum += e * e;
      }
    }
    const ens = sum / used;
    let spread = 0;
    for (const r of raw) if (!Number.isNaN(r)) spread += (r - ens) ** 2;
    spread = used > 1 ? Math.sqrt(spread / (used - 1)) : 0;
    for (let j = 0; j < COMPS.length; j++) {
      const r = raw[j];
      if (Number.isNaN(r)) {
        c.comps[j][i] = NaN;
        continue;
      }
      c.comps[j][i] = used > 1 ? r - (sum - r) / (used - 1) : 0;
    }
    const ensErr = Math.sqrt(varSum) / used;

    // Target: differential, so the cloud and the extinction cancel; its own noise does not.
    const mTrue = targetTrueMag(t);
    const eT = sigmaOf(mTrue);
    let mTarget = mTrue + eT * gauss(rand) + 0.004 * gauss(rand) * (cloud > 0.3 ? 1 : 0);
    let flags = 0;
    if (TRAILS.some((tt) => Math.abs(tt - t) < 30)) {
      mTarget -= 0.24; // the trail adds light: brighter
      flags |= FLAG_SUSPECT;
    }
    const peak = 1180 + 69000 * Math.pow(10, -0.4 * (mTrue - 9.3 + cloud + EXTINCTION_K * (X - 1))) * (2.25 / hfd) ** 2;
    if (peak >= 65000) flags |= FLAG_SATURATED;

    c.t[i] = t;
    c.bjdOffsetS[i] = (bjdApprox(t, TARGET.pos) - jdFromUnix(t)) * 86400;
    c.alt[i] = h.alt;
    c.airmass[i] = X;
    c.target[i] = mTarget;
    c.targetErr[i] = Math.hypot(eT, ensErr);
    c.flags[i] = flags;
    c.peakAdu[i] = Math.min(65535, peak);
    const eK = sigmaOf(CHECK.v);
    c.checkDelta[i] = 0.006 + eK * gauss(rand) + 0.004 * (X - 1);
    c.checkErr[i] = Math.hypot(eK, ensErr);
    c.ensOffset[i] = ens;
    c.ensSpread[i] = spread;
    c.nUsed[i] = used;
    c.hfd[i] = hfd;
    c.fwhm[i] = fwhm;
    c.stars[i] = Math.max(40, Math.round(2950 * Math.pow(10, -0.36 * cloud) * Math.pow(2.25 / hfd, 0.9) * (1 - 0.12 * (X - 1)) + 28 * gauss(rand)));
    const moon = moonAltitude(SITE, t);
    c.sky[i] = 1180 + 230 * cloud + (moon > 0 ? 95 * Math.sin((moon * Math.PI) / 180) : 0) + 6 * gauss(rand);
    c.sensorC[i] = 23.8 - (4.6 * (t - RUN_START)) / 26700 + 0.12 * gauss(rand);
    c.focuser[i] = Math.round(1287 + 9 * ((t - RUN_START) / 3600));
  }
  c.n = n;
  return c;
}

/** The night at the real cadence (~51.5 s), and the 4 s stress run (~6 700 frames). */
export const REAL_CADENCE = { cadence: 51.5, jitter: 1.4, seed: 3 };
export const FAST_CADENCE = { cadence: 4, jitter: 0.08, seed: 5 };

export const ensembleLabel = (n: number) => `${n}/${COMPS.length}`;

/** Baseline of the attention rule: median HFD of the first 20 frames. */
export function hfdBaseline(c: NightColumns, n: number): number | null {
  const k = Math.min(20, n);
  if (k < 5) return null;
  const a = Array.from(c.hfd.subarray(0, k)).sort((x, y) => x - y);
  return k % 2 ? a[(k - 1) / 2] : (a[k / 2 - 1] + a[k / 2]) / 2;
}

/**
 * The server's proposed attention rule (functional-spaces 4.10): HFD above
 * `factor` x baseline for 3 frames in a row. Returns the index of the frame
 * where it fired (the third one), for each episode, and where it cleared.
 */
export function hfdEpisodes(c: NightColumns, n: number, factor: number): { start: number; fired: number; end: number | null }[] {
  const base = hfdBaseline(c, n);
  if (base === null) return [];
  const thr = base * factor;
  const out: { start: number; fired: number; end: number | null }[] = [];
  let run = 0;
  let cur: { start: number; fired: number; end: number | null } | null = null;
  for (let i = 0; i < n; i++) {
    if (c.hfd[i] > thr) {
      run++;
      if (run === 3 && !cur) {
        cur = { start: i - 2, fired: i, end: null };
        out.push(cur);
      }
    } else {
      run = 0;
      if (cur) {
        cur.end = i;
        cur = null;
      }
    }
  }
  return out;
}
