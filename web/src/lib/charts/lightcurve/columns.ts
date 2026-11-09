/**
 * One star's live light curve as typed-array columns (PROPOSAL 3.2, research
 * T1): the plot reads subarray views, never a Svelte proxy, and an append
 * costs O(1) (capacity doubles when full).
 *
 * A row is one `LcPoint` of argos/core/photometry/lightcurve.py, as the
 * server sends it (A54 snapshot curves, A55 `photometry_point`): every field
 * is kept, so the readout, the TSV and the error bars show exactly the Qt
 * values. Missing numbers are NaN; the two booleans become FLAG_* bits.
 *
 * Rows stay sorted by time: a point older than the newest one (a replayed
 * frame) is inserted in place. A point at the time of an existing row (the
 * same frame measured again, a second solution) is a new row after it, as Qt
 * keeps both (LightCurve.append): the rows match the server's points one for
 * one.
 */

import { FLAG_SATURATED, FLAG_SUSPECT } from '../uplot/markers';
import { JD_UNIX_EPOCH } from '../uplot/axes';

/** An `LcPoint` on the wire (null = Python None or NaN). */
export interface LcPoint {
  jd_utc: number;
  mag: number | null;
  mag_err: number | null;
  bjd_tdb?: number | null;
  airmass?: number | null;
  fwhm?: number | null;
  sky_adu?: number | null;
  comps_used?: number | null;
  saturated?: boolean | null;
  suspect?: boolean | null;
  formal_mag_err?: number | null;
  sigma_syst?: number | null;
  relative_flux?: number | null;
  relative_flux_err?: number | null;
  relative_comps_used?: number | null;
  /** The /ws/frames seq the point was measured on. */
  frame_seq?: number | null;
  /** The exposure midpoint, ISO (the plot uses jd_utc). */
  t?: string | null;
  /** The star's ensemble zero point on that frame (mean of catalogue − instrumental) and its rms. */
  zero_point?: number | null;
  zp_rms?: number | null;
}

/** Unix seconds of a Julian date (UTC). */
export function unixFromJd(jd: number): number {
  return (jd - JD_UNIX_EPOCH) * 86400;
}

/**
 * math.hypot(a, b) of CPython 3.10-3.11 (Modules/mathmodule.c vector_norm),
 * bit for bit: the floor is applied with the Python function in Qt and in the
 * server, and V8's Math.hypot differs from it by one ulp on about a third of
 * real error bars (wave 5 check on 1 440 points of three real sessions).
 * Dekker splitting and error-free sums, then one differential correction.
 */
export function pyHypot(a: number, b: number): number {
  const xs = [Math.abs(a), Math.abs(b)];
  if (xs.some((v) => Number.isNaN(v))) return xs.some((v) => v === Infinity) ? Infinity : NaN;
  const max = Math.max(xs[0], xs[1]);
  if (max === Infinity) return Infinity;
  if (max === 0) return 0;
  // frexp: max = m * 2^e with m in [0.5, 1).
  let e = Math.floor(Math.log2(max)) + 1;
  while (max * 2 ** -e >= 1) e++;
  while (max * 2 ** -e < 0.5) e--;
  if (e < -1021) return Math.hypot(a, b); // subnormal inputs: never an error bar
  const scale = 2 ** -e;
  const T27 = 134217729.0;
  let csum = 1.0;
  let frac1 = 0.0;
  let frac2 = 0.0;
  let frac3 = 0.0;
  let x: number;
  let t: number;
  let hi: number;
  let lo: number;
  let old: number;
  for (const v of xs) {
    x = v * scale;
    t = x * T27;
    hi = t - (t - x);
    lo = x - hi;
    x = hi * hi;
    old = csum;
    csum += x;
    frac1 += old - csum + x;
    x = 2.0 * hi * lo;
    old = csum;
    csum += x;
    frac2 += old - csum + x;
    frac3 += lo * lo;
  }
  const h = Math.sqrt(csum - 1.0 + (frac1 + frac2 + frac3));
  t = h * T27;
  hi = t - (t - h);
  lo = h - hi;
  x = -hi * hi;
  old = csum;
  csum += x;
  frac1 += old - csum + x;
  x = -2.0 * hi * lo;
  old = csum;
  csum += x;
  frac2 += old - csum + x;
  x = -lo * lo;
  old = csum;
  csum += x;
  frac3 += old - csum + x;
  x = csum - 1.0 + (frac1 + frac2 + frac3);
  return (h + x / (2.0 * h)) / scale;
}

const num = (v: number | null | undefined): number => (typeof v === 'number' && Number.isFinite(v) ? v : NaN);

/** True when the point carries something to draw (Qt skips the others: lightcurve_panel.py:127-128). */
export function drawable(p: LcPoint): boolean {
  return Number.isFinite(num(p.jd_utc)) && (Number.isFinite(num(p.mag)) || Number.isFinite(num(p.relative_flux)));
}

const F64 = ['t', 'jd', 'bjd', 'mag', 'err', 'formal', 'base', 'syst', 'flux', 'fluxErr', 'airmass', 'fwhm', 'sky', 'comps', 'relComps', 'frameSeq', 'zp', 'zpRms'] as const;
export type Column = (typeof F64)[number];

export class CurveColumns {
  n = 0;
  /** Bumped by every change of an existing row (insert, replace, error recompute). */
  edits = 0;
  t!: Float64Array;
  jd!: Float64Array;
  bjd!: Float64Array;
  mag!: Float64Array;
  /** Final error (`mag_err`, with the run-level systematic floor once known). */
  err!: Float64Array;
  /** The point's formal error (`formal_mag_err`), NaN when the server sent none. */
  formal!: Float64Array;
  /** What the floor is added to: `formal_mag_err`, else the `mag_err` the point arrived with. */
  base!: Float64Array;
  /** `sigma_syst` as the point carries it. */
  syst!: Float64Array;
  flux!: Float64Array;
  fluxErr!: Float64Array;
  airmass!: Float64Array;
  fwhm!: Float64Array;
  sky!: Float64Array;
  comps!: Float64Array;
  relComps!: Float64Array;
  /** The frame the point was measured on (/ws/frames seq), NaN when unknown. */
  frameSeq!: Float64Array;
  /** The ensemble zero point of the point (mag) and its rms, NaN when the server sent none. */
  zp!: Float64Array;
  zpRms!: Float64Array;
  flags!: Uint8Array;

  constructor(capacity = 256) {
    this.alloc(Math.max(4, capacity));
  }

  get capacity(): number {
    return this.t.length;
  }

  private alloc(cap: number): void {
    const keep = this.n;
    for (const c of F64) {
      const next = new Float64Array(cap);
      const old = (this as unknown as Record<Column, Float64Array | undefined>)[c];
      if (old) next.set(old.subarray(0, keep));
      (this as unknown as Record<Column, Float64Array>)[c] = next;
    }
    const f = new Uint8Array(cap);
    if (this.flags) f.set(this.flags.subarray(0, keep));
    this.flags = f;
  }

  clear(): void {
    this.n = 0;
    this.edits++;
  }

  /** Index of the first row with t >= `t` (n when none). */
  lowerBound(t: number): number {
    let lo = 0;
    let hi = this.n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.t[mid] < t) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  /** Index of the row nearest to `t` in time, or -1 when empty. */
  nearest(t: number): number {
    if (!this.n) return -1;
    const i = this.lowerBound(t);
    if (i >= this.n) return this.n - 1;
    if (i === 0) return 0;
    return t - this.t[i - 1] <= this.t[i] - t ? i - 1 : i;
  }

  /** Index of the first row with t > `t` (n when none). */
  upperBound(t: number): number {
    let lo = 0;
    let hi = this.n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.t[mid] <= t) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  /** Every row at exactly this JD, oldest measurement first (the same frame measured twice). */
  rowsOfJd(jd: number): number[] {
    const t = unixFromJd(jd);
    const out: number[] = [];
    for (let k = Math.max(0, this.lowerBound(t) - 1); k < this.n && this.t[k] <= t + 1e-6; k++) if (this.jd[k] === jd) out.push(k);
    return out;
  }

  /** The newest row at exactly this JD, or -1. */
  indexOfJd(jd: number): number {
    const rows = this.rowsOfJd(jd);
    return rows.length ? rows[rows.length - 1] : -1;
  }

  /**
   * Store a point; returns its row and how it got there. 'appended' is the
   * live path (the past is untouched); 'inserted' moved rows the plot
   * already drew (a replayed older frame).
   */
  put(p: LcPoint): { index: number; how: 'appended' | 'inserted' } {
    const t = unixFromJd(p.jd_utc);
    let i: number;
    let how: 'appended' | 'inserted';
    if (!this.n || t >= this.t[this.n - 1]) {
      i = this.n;
      how = 'appended';
    } else {
      i = this.upperBound(t);
      how = 'inserted';
    }
    if (this.n === this.capacity) this.alloc(this.capacity * 2);
    if (i < this.n) {
      for (const c of F64) {
        const a = (this as unknown as Record<Column, Float64Array>)[c];
        a.copyWithin(i + 1, i, this.n);
      }
      this.flags.copyWithin(i + 1, i, this.n);
    }
    this.n++;
    if (how !== 'appended') this.edits++;
    this.t[i] = t;
    this.jd[i] = p.jd_utc;
    this.bjd[i] = num(p.bjd_tdb);
    this.mag[i] = num(p.mag);
    this.err[i] = num(p.mag_err);
    this.formal[i] = num(p.formal_mag_err);
    this.base[i] = Number.isFinite(this.formal[i]) ? this.formal[i] : this.err[i];
    this.syst[i] = num(p.sigma_syst);
    this.flux[i] = num(p.relative_flux);
    this.fluxErr[i] = num(p.relative_flux_err);
    this.airmass[i] = num(p.airmass);
    this.fwhm[i] = num(p.fwhm);
    this.sky[i] = num(p.sky_adu);
    this.comps[i] = num(p.comps_used);
    this.relComps[i] = num(p.relative_comps_used);
    this.frameSeq[i] = num(p.frame_seq);
    this.zp[i] = num(p.zero_point);
    this.zpRms[i] = num(p.zp_rms);
    this.flags[i] = (p.suspect ? FLAG_SUSPECT : 0) | (p.saturated ? FLAG_SATURATED : 0);
    return { index: i, how };
  }

  /**
   * The run-level systematic floor changed (S19, uncertainty.py:95-98): every
   * point with a magnitude gets `hypot(max(0, formal), sigma)` (pyHypot: the
   * Python function's bits), exactly as
   * AcquisitionEngine._apply_systematic_floor rewrites `mag_err`. The formal
   * error is `formal_mag_err`, or the point's `mag_err` when it has none (the
   * Qt fallback). Qt always sends `formal_mag_err` with a magnitude (engine,
   * batch worker and CSV reader all fill it), so the fallback is only a guard;
   * it uses the error the point ARRIVED with, so a second floor never
   * compounds on the first. Returns true when an error bar changed. Row by
   * row, so it holds whatever order the frames were measured in (the server
   * sends the floor, never the column: A55).
   */
  applyFloor(sigma: number): boolean {
    if (!Number.isFinite(sigma)) return false;
    let changed = false;
    for (let i = 0; i < this.n; i++) {
      if (!Number.isFinite(this.mag[i])) continue;
      const f = this.base[i];
      if (!Number.isFinite(f)) continue;
      const e = pyHypot(Math.max(0, f), sigma);
      if (e !== this.err[i] || this.syst[i] !== sigma) {
        this.err[i] = e;
        this.syst[i] = sigma;
        changed = true;
      }
    }
    if (changed) this.edits++;
    return changed;
  }

  /** A view of the first n rows of a column (no copy). */
  view(c: Column): Float64Array {
    return (this as unknown as Record<Column, Float64Array>)[c].subarray(0, this.n);
  }

  flagsView(): Uint8Array {
    return this.flags.subarray(0, this.n);
  }
}
