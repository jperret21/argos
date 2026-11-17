/**
 * Synthetic live runs for the light-curve gallery and the stress check
 * (development only). Deterministic (seeded), and fed through the same path
 * as the server's events (LiveCurveStore.apply with A55-shaped points), so
 * the gallery exercises the systematic-floor recompute, the check offset and
 * the ensemble aggregation, not a shortcut.
 *
 * The sky is invented: an RRab-like target (0.567 d, 0.9 mag), a constant
 * check star 0.012 mag off its catalogue value, five comparisons, one of
 * them slowly drifting. Real-data checks use copies of real sessions (see
 * the wave 5 report), never this.
 */

import { LiveCurveStore, type PointEvent } from '../store';
import { pyHypot, type LcPoint } from '../columns';

export const RUN_JD0 = 2461282.395; // 2026-08-29 21:28:48 UTC
export const unixOfJd = (jd: number) => (jd - 2440587.5) * 86400;

function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(r: () => number): number {
  const u = Math.max(1e-12, r());
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r());
}

/** RRab-like light: fast rise, slow decline; 0 at maximum light, 1 at minimum. */
function rrab(phase: number): number {
  const p = phase - Math.floor(phase);
  return p < 0.14 ? 1 - p / 0.14 : Math.pow((p - 0.14) / 0.86, 0.8);
}

export interface RunSpec {
  /** Frames. */
  n: number;
  /** Seconds between frames. */
  cadence?: number;
  seed?: number;
  /** A check star (catalogue magnitude, or null for none in the catalogue). */
  check?: { catalogue: number | null } | null;
  /** Comparisons in the ensemble. */
  comps?: number;
  /** BJD_TDB on every point (an observing site is set). */
  bjd?: boolean;
  /** Suspect and saturated flags sprinkled on the target and the check. */
  flags?: boolean;
  /** Comparisons without catalogue magnitudes: ratio-only target points (a transit run, S18). */
  ratioOnly?: boolean;
  /** A pause (autofocus) of this many seconds after frame `pauseAt`. */
  pauseAt?: number;
  pauseS?: number;
  /** Phase of the target at the first frame. */
  phase0?: number;
}

export interface Run {
  store: LiveCurveStore;
  /** Unix seconds of the first and last frame. */
  first: number;
  last: number;
  events: number;
}

const PERIOD_D = 0.5668;

/** Build a run point by point through store.apply (the live path). */
export function makeRun(spec: RunSpec, store = new LiveCurveStore()): Run {
  const r = rng(spec.seed ?? 7);
  const cadence = spec.cadence ?? 30;
  const ncomp = spec.comps ?? 5;
  const check = spec.check === undefined ? { catalogue: 11.43 } : spec.check;
  const compCat = Array.from({ length: ncomp }, (_, k) => 10.9 + 0.35 * k);
  store.load({
    object_name: 'RR Lyr (simulated)',
    band: 'TG',
    revision: 0,
    seq: 0,
    curves: [
      { key: '000-BCD-001', role: 'target', name: 'RR Lyr', auid: '000-BCD-001', points: [] },
      ...(check ? [{ key: '000-BCD-117', role: 'check', name: '000-BCD-117', auid: '000-BCD-117', catalogue_v: spec.ratioOnly ? null : check.catalogue, points: [] }] : []),
      ...compCat.map((c, k) => ({ key: `C${k + 1}`, role: 'comparison', name: `000-BCD-1${20 + k}`, auid: '', mags: spec.ratioOnly ? null : { V: c }, points: [] })),
    ],
  });
  let seq = 0;
  let events = 0;
  const formals: Record<string, number[]> = {};
  const validCount: Record<string, number> = {};
  const send = (key: string, role: string, name: string, p: LcPoint) => {
    // As the server: the floor appears at the curve's 10th valid point (S19); each point
    // carries it and the store recomputes the earlier bars.
    const f = (formals[key] ??= []);
    const valid = Number.isFinite(p.mag ?? NaN);
    f.push(valid ? (p.formal_mag_err ?? NaN) : NaN);
    const nValid = (validCount[key] = (validCount[key] ?? 0) + (valid ? 1 : 0));
    const sigma = nValid >= 10 ? 0.004 : null;
    if (sigma !== null && valid) p.mag_err = pyHypot(p.formal_mag_err ?? 0, sigma);
    const ev: PointEvent = {
      seq: ++seq,
      revision: 0,
      key,
      role,
      name,
      auid: role === 'comparison' ? null : key,
      index: f.length - 1,
      point: { ...p, sigma_syst: valid ? sigma : null, frame_seq: 1000 + f.length },
      sigma_syst: sigma,
    };
    store.apply(ev);
    events++;
  };

  let t = 0;
  const jds: number[] = [];
  for (let i = 0; i < spec.n; i++) {
    jds.push(RUN_JD0 + t / 86400);
    t += cadence * (1 + 0.02 * (r() - 0.5));
    if (spec.pauseAt !== undefined && i === spec.pauseAt) t += spec.pauseS ?? 600;
  }
  for (let i = 0; i < spec.n; i++) {
    const jd = jds[i];
    const bjd = spec.bjd === false ? null : jd + (203.6 + 0.4 * (i / spec.n)) / 86400;
    const airmass = 1.05 + 0.6 * Math.pow(i / Math.max(1, spec.n), 2);
    const phase = (spec.phase0 ?? 0.55) + (jd - RUN_JD0) / PERIOD_D;
    const light = rrab(phase);
    const v = 10.95 + 0.9 * light;
    const formal = 0.0045 + 0.004 * light;
    const sat = !!spec.flags && light < 0.03;
    const sus = !!spec.flags && r() < 0.012;
    const flux = Math.pow(10, -0.4 * (v - 11.4));
    send('000-BCD-001', 'target', 'RR Lyr', {
      jd_utc: jd,
      bjd_tdb: bjd,
      mag: spec.ratioOnly ? null : v + formal * gauss(r) + (sat ? -0.06 : 0),
      mag_err: spec.ratioOnly ? null : formal,
      formal_mag_err: spec.ratioOnly ? null : formal,
      airmass,
      fwhm: 2.4,
      sky_adu: 1800,
      comps_used: spec.ratioOnly ? 0 : ncomp,
      saturated: sat,
      suspect: sus,
      relative_flux: flux * (1 + 0.006 * gauss(r)),
      relative_flux_err: flux * 0.006,
      relative_comps_used: ncomp,
      // The ensemble zero point: extinction with the airmass, a little transparency noise.
      zero_point: spec.ratioOnly ? null : 19.42 - 0.18 * (airmass - 1) + 0.006 * gauss(r),
      zp_rms: spec.ratioOnly ? null : 0.014 + 0.003 * Math.abs(gauss(r)),
    });
    if (check) {
      const cf = 0.0075;
      const csus = !!spec.flags && r() < 0.01;
      const cm = (check.catalogue ?? 11.43) + 0.012 + 0.009 * gauss(r) + 0.004 * Math.sin(i / 37);
      send('000-BCD-117', 'check', '000-BCD-117', {
        jd_utc: jd,
        bjd_tdb: bjd,
        mag: spec.ratioOnly ? null : cm,
        mag_err: spec.ratioOnly ? null : cf,
        formal_mag_err: spec.ratioOnly ? null : cf,
        airmass,
        comps_used: ncomp,
        saturated: false,
        suspect: csus,
        relative_flux: 1 + 0.008 * gauss(r),
        relative_flux_err: 0.008,
        relative_comps_used: ncomp,
      });
    }
    compCat.forEach((cat, k) => {
      const drift = k === ncomp - 1 ? 0.03 * (i / Math.max(1, spec.n)) : 0;
      const noise = 0.008 + 0.003 * k;
      const m = cat + 0.004 * (k - 2) + drift + noise * gauss(r);
      send(`C${k + 1}`, 'comparison', `000-BCD-1${20 + k}`, {
        jd_utc: jd,
        bjd_tdb: bjd,
        mag: spec.ratioOnly ? null : m,
        mag_err: spec.ratioOnly ? null : noise,
        formal_mag_err: spec.ratioOnly ? null : noise,
        airmass,
        comps_used: ncomp - 1,
        saturated: false,
        suspect: false,
        relative_flux: 1 + noise * gauss(r) - drift,
        relative_flux_err: noise,
        relative_comps_used: ncomp - 1,
      });
    });
  }
  return { store, first: unixOfJd(jds[0] ?? RUN_JD0), last: unixOfJd(jds[jds.length - 1] ?? RUN_JD0), events };
}
