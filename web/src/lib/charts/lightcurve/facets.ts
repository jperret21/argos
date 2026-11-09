/**
 * What each facet of LightCurvePlot draws, from the store (pure: no uPlot,
 * no DOM). Magnitude view: subarray views of the store's columns (no copy,
 * an append costs nothing here). Relative-flux view: new arrays divided by
 * the series' baseline (S16: the median of the unsaturated points), which
 * moves as points arrive, as in Qt.
 *
 * The ensemble facet is the target's ensemble zero point per frame (the
 * server's DiffResult.zero_point, mean of catalogue − instrumental over the
 * comparisons used) ± its rms: up = more light (a clearer sky), as the
 * relative-flux view's transmission 10^(0.4 (zp − median zp)).
 */

import { CHECK_WINDOW, type LiveCurveStore, type StarCurve } from './store';
import { fluxBaseline, medianOf } from './trailing';
import { FLAG_SATURATED, type Shape } from '../uplot/markers';

export type FacetId = 'target' | 'check' | 'ensemble';
export type YMode = 'mag' | 'flux';

export interface FacetData {
  n: number;
  x: Float64Array;
  y: Float64Array;
  err: Float64Array | null;
  flags: Uint8Array | null;
  band: { mean: Float64Array; hi: Float64Array; lo: Float64Array } | null;
}

export const FACET_SHAPE: Record<FacetId, Shape> = { target: 'circle', check: 'triangle', ensemble: 'square' };

/** Smallest y span per facet (noise is never blown up to full height). */
export const FACET_MIN_SPAN: Record<FacetId, Record<YMode, number>> = {
  target: { mag: 0.08, flux: 0.02 },
  check: { mag: 0.04, flux: 0.02 },
  ensemble: { mag: 0.04, flux: 0.02 },
};

const EMPTY = new Float64Array(0);

export function baselineOf(s: StarCurve): number {
  const c = s.cols;
  return fluxBaseline(c.flux, c.n, (i) => (c.flags[i] & FLAG_SATURATED) !== 0);
}

function divided(a: Float64Array, n: number, base: number): Float64Array {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) out[i] = a[i] / base;
  return out;
}

/** The series a facet draws, or null when the run has none (no check star, no comparison). */
export function facetData(store: LiveCurveStore, id: FacetId, mode: YMode, keys: { target?: string | null; check?: string | null } = {}): FacetData | null {
  if (id === 'ensemble') {
    const t = store.primary('target', keys.target);
    if (!t || !t.n) return null;
    const c = t.cols;
    const n = c.n;
    let any = false;
    for (let i = 0; i < n && !any; i++) any = Number.isFinite(c.zp[i]);
    if (!any) return null;
    const zp = c.view('zp');
    const rms = c.view('zpRms');
    const hi = new Float64Array(n);
    const lo = new Float64Array(n);
    if (mode === 'mag') {
      for (let i = 0; i < n; i++) {
        const r = Number.isFinite(rms[i]) ? rms[i] : NaN;
        hi[i] = zp[i] + r;
        lo[i] = zp[i] - r;
      }
      return { n, x: c.view('t'), y: zp, err: null, flags: null, band: { mean: zp, hi, lo } };
    }
    const med = medianOf(zp, n);
    const y = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      y[i] = 10 ** (0.4 * (zp[i] - med));
      hi[i] = Number.isFinite(rms[i]) ? 10 ** (0.4 * (zp[i] + rms[i] - med)) : NaN;
      lo[i] = Number.isFinite(rms[i]) ? 10 ** (0.4 * (zp[i] - rms[i] - med)) : NaN;
    }
    return { n, x: c.view('t'), y, err: null, flags: null, band: { mean: y, hi, lo } };
  }
  const s = store.primary(id, id === 'target' ? keys.target : keys.check);
  if (!s || !s.n) return null;
  const c = s.cols;
  const n = c.n;
  if (id === 'check') s.derive();
  if (mode === 'mag') {
    const y = id === 'check' ? s.delta.subarray(0, n) : c.view('mag');
    const band = id === 'check' ? { mean: s.band.mean.subarray(0, n), hi: s.band.hi.subarray(0, n), lo: s.band.lo.subarray(0, n) } : null;
    return { n, x: c.view('t'), y, err: c.view('err'), flags: c.flagsView(), band };
  }
  const base = baselineOf(s);
  if (!(base > 0)) return { n, x: c.view('t'), y: new Float64Array(n).fill(NaN), err: null, flags: c.flagsView(), band: null };
  const band = id === 'check' ? { mean: divided(s.fluxBand.mean, n, base), hi: divided(s.fluxBand.hi, n, base), lo: divided(s.fluxBand.lo, n, base) } : null;
  return { n, x: c.view('t'), y: divided(c.flux, n, base), err: divided(c.fluxErr, n, base), flags: c.flagsView(), band };
}

/** uPlot data of a facet: [x, y] (the band and the error bars are drawn by plugins). */
export function alignedOf(d: FacetData | null): [Float64Array, Float64Array] {
  return d ? [d.x, d.y] : [EMPTY, EMPTY];
}

/** Flag counts of a facet's series (legend keys). */
export function flagCounts(flags: Uint8Array | null, y: Float64Array | null): { suspect: number; saturated: number } {
  let suspect = 0;
  let saturated = 0;
  if (!flags) return { suspect, saturated };
  for (let i = 0; i < flags.length; i++) {
    if (y && !Number.isFinite(y[i])) continue;
    const f = flags[i];
    if (f & FLAG_SATURATED) saturated++;
    else if (f & 1) suspect++;
  }
  return { suspect, saturated };
}

/** Index range [i0, i1] of x within [a, b] (both inclusive; i1 < i0 when none). */
export function visibleRange(x: ArrayLike<number>, n: number, a: number, b: number): [number, number] {
  let lo = 0;
  let hi = n;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (x[m] < a) lo = m + 1;
    else hi = m;
  }
  const i0 = lo;
  hi = n;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (x[m] <= b) lo = m + 1;
    else hi = m;
  }
  return [i0, lo - 1];
}

/** Finite y range over the visible rows, the band edges included (the facet's y scale). */
export function yExtent(d: FacetData, a: number, b: number): [number, number] | null {
  const [i0, i1] = visibleRange(d.x, d.n, a, b);
  let lo = Infinity;
  let hi = -Infinity;
  const take = (v: number) => {
    if (!Number.isFinite(v)) return;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  };
  for (let i = i0; i <= i1; i++) {
    take(d.y[i]);
    if (d.band) {
      take(d.band.hi[i]);
      take(d.band.lo[i]);
    }
  }
  return Number.isFinite(lo) ? [lo, hi] : null;
}

/** The check star's scatter: the trailing band's sigma at its newest valid row (BRAND 10: in the readout). */
export function checkSigma(store: LiveCurveStore, key?: string | null): { sigma: number; count: number } | null {
  const s = store.primary('check', key);
  if (!s || !s.n) return null;
  s.derive();
  for (let i = s.n - 1; i >= 0; i--) {
    const k = s.band.count[i];
    if (k) return { sigma: k > 2 ? s.band.sd[i] : NaN, count: Math.min(k, CHECK_WINDOW) };
  }
  return null;
}

/** The check facet's symmetric scale (mag): ±rung about 0, from this ladder up. */
export const CHECK_RUNGS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5] as const;

/**
 * The smallest rung that holds the trailing band and 90 % of the visible check
 * points (the rest are drawn as carets on the edge): the facet's height then
 * shows the scatter, a noisy check never looks as flat as a good one.
 */
export function checkRung(d: FacetData, a: number, b: number): number {
  const [i0, i1] = visibleRange(d.x, d.n, a, b);
  const abs: number[] = [];
  let band = 0;
  for (let i = i0; i <= i1; i++) {
    if (Number.isFinite(d.y[i])) abs.push(Math.abs(d.y[i]));
    if (d.band) {
      for (const v of [d.band.hi[i], d.band.lo[i]]) if (Number.isFinite(v)) band = Math.max(band, Math.abs(v));
    }
  }
  abs.sort((x, y) => x - y);
  const q90 = abs.length ? abs[Math.max(0, Math.ceil(0.9 * abs.length) - 1)] : 0;
  const need = Math.max(q90, band);
  for (const r of CHECK_RUNGS) if (need <= r) return r;
  return CHECK_RUNGS[CHECK_RUNGS.length - 1];
}

const LADDER = [1, 2, 5];

/** Round values on a 1 / 2 / 5 × 10^n step inside [min, max]. */
function stepSplits(min: number, max: number, step: number): number[] {
  const out: number[] = [];
  for (let k = Math.ceil(min / step - 1e-9); k * step <= max + step * 1e-9; k++) out.push(k * step);
  return out;
}

/**
 * Y ticks of a facet on a 1 / 2 / 5 × 10^n step, as many as fit `minGap` px
 * apart: three or more labelled values (top, middle, bottom) from 26 px of
 * data height, never fewer than two (the old default gave short facets one
 * tick, so a facet had no readable scale).
 */
export function niceSplits(min: number, max: number, plotPx: number, minGap = 13): { splits: number[]; step: number } {
  if (!(max > min) || !Number.isFinite(min) || !Number.isFinite(max)) return { splits: [], step: 0 };
  const span = max - min;
  const most = Math.max(2, Math.floor(plotPx / minGap) + 1);
  let e = Math.floor(Math.log10(span)) - 3;
  let prev: { splits: number[]; step: number } | null = null;
  for (let guard = 0; guard < 40; guard++, e++) {
    for (const m of LADDER) {
      const step = m * 10 ** e;
      const splits = stepSplits(min, max, step);
      if (splits.length <= most) {
        if (splits.length >= Math.min(3, most) || !prev) return { splits, step };
        return prev;
      }
      prev = { splits, step };
    }
  }
  return prev ?? { splits: [min, max], step: span };
}

/**
 * [lo, hi] widened so a marker (and the newest point's ring) of `marginPx`
 * never crosses the plot edge: the padding is in pixels, not a fraction of the
 * span (10 % was 3 px on a short facet, less than a marker's radius).
 */
export function padPixels(lo: number, hi: number, plotPx: number, marginPx: number): [number, number] {
  if (!(hi > lo) || !(plotPx > 2 * marginPx + 1)) return [lo, hi];
  const p = (marginPx * (hi - lo)) / (plotPx - 2 * marginPx);
  return [lo - p, hi + p];
}
