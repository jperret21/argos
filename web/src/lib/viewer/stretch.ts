/**
 * Display stretch: TypeScript port of argos/core/imaging/stretch.py.
 *
 * The Qt app and the web UI must show the same picture for the same frame, so
 * the auto-stretch reproduces auto_stf / auto_levels operation by operation,
 * with the same constants. The per-pixel transfer itself runs on the GPU
 * (viewer/shaders.ts); stretchValue() below is the CPU reference of that shader
 * and is what the tests compare against the Python apply_stretch().
 *
 * Statistics are computed exactly from a 65536-bin histogram of the uint16
 * samples (no subsampling, no sort): every order statistic numpy needs
 * (median, MAD, linear-interpolated percentile) is recovered exactly from it.
 * Arithmetic is float64, like numpy's for these reductions; the only
 * difference is the std() fallback (numpy accumulates float32), which is
 * used only when MAD == 0 and agrees to float32 precision.
 */

export type StretchMode = 'linear' | 'log' | 'asinh';

export const STRETCH_MODES: readonly StretchMode[] = ['linear', 'log', 'asinh'];

/** Steepness of the non-linear transfers (stretch.py: _LOG_K, _ASINH_K). */
export const LOG_K = 1000.0;
export const ASINH_K = 30.0;

/** auto_stf defaults (stretch.py). */
export const STF_TARGET_BG = 0.25;
export const STF_SHADOW_CLIP = 2.8;
export const STF_WHITE_PERCENTILE = 99.8;
/** MAD -> Gaussian sigma. */
export const MAD_TO_SIGMA = 1.4826;

export interface StretchParams {
  black: number;
  white: number;
  /** PixInsight MTF balance in (0, 1); 0.5 is neutral. */
  midtones: number;
  mode: StretchMode;
}

export const NEUTRAL_STRETCH: StretchParams = { black: 0, white: 65535, midtones: 0.5, mode: 'linear' };

// ---------------------------------------------------------------------------
// Exact statistics of uint16 data via a full-resolution histogram
// ---------------------------------------------------------------------------

export interface Histogram16 {
  /** counts[v] = number of samples equal to v, v in [0, 65535]. */
  counts: Uint32Array;
  n: number;
  min: number;
  max: number;
}

/** One pass over the samples (all channels together, like ndarray.ravel()). */
export function histogram16(data: ArrayLike<number>): Histogram16 {
  const counts = new Uint32Array(65536);
  const n = data.length;
  for (let i = 0; i < n; i++) counts[data[i]]++;
  let min = 0;
  let max = 0;
  if (n > 0) {
    while (counts[min] === 0) min++;
    max = 65535;
    while (counts[max] === 0) max--;
  }
  return { counts, n, min, max };
}

/** k-th smallest sample (0-based) of a count table. */
function orderStatistic(counts: Uint32Array, k: number): number {
  let seen = 0;
  for (let v = 0; v < counts.length; v++) {
    seen += counts[v];
    if (seen > k) return v;
  }
  return counts.length - 1;
}

/** numpy.median: middle sample, or the mean of the two middle ones. */
function medianOfCounts(counts: Uint32Array, n: number): number {
  if (n === 0) return Number.NaN;
  if (n % 2 === 1) return orderStatistic(counts, (n - 1) / 2);
  return (orderStatistic(counts, n / 2 - 1) + orderStatistic(counts, n / 2)) / 2;
}

export function median(h: Histogram16): number {
  return medianOfCounts(h.counts, h.n);
}

/**
 * Median of |x - med|. `med` is an integer or a half-integer (median of
 * integers), so every deviation is k (integer med) or k + 0.5 (half-integer
 * med): the deviations are themselves histogrammed exactly by k.
 */
export function medianAbsDeviation(h: Histogram16, med: number): number {
  if (h.n === 0) return Number.NaN;
  const dev = new Uint32Array(65536);
  const c = h.counts;
  const half = med !== Math.floor(med);
  const m = Math.floor(med);
  for (let v = h.min; v <= h.max; v++) {
    const count = c[v];
    if (count === 0) continue;
    // integer med: k = |v - m|;  half-integer med (m + 0.5): k = |v - m - 0.5| - 0.5
    const k = half ? (v > m ? v - m - 1 : m - v) : Math.abs(v - m);
    dev[k] += count;
  }
  const k = medianOfCounts(dev, h.n);
  return half ? k + 0.5 : k;
}

/** numpy.percentile(a, q) with the default "linear" method, exactly. */
export function percentile(h: Histogram16, q: number): number {
  if (h.n === 0) return Number.NaN;
  const vi = (h.n - 1) * (q / 100);
  if (vi >= h.n - 1) return h.max;
  if (vi <= 0) return h.min;
  const prev = Math.floor(vi);
  const t = vi - prev;
  const a = orderStatistic(h.counts, prev);
  const b = orderStatistic(h.counts, prev + 1);
  // numpy _lerp: a + (b-a)*t, or b - (b-a)*(1-t) when t >= 0.5 (same rounding).
  const diff = b - a;
  return t >= 0.5 ? b - diff * (1 - t) : a + diff * t;
}

/** Population standard deviation (numpy ddof=0), two-pass in float64. */
export function stdDev(h: Histogram16): number {
  if (h.n === 0) return Number.NaN;
  const c = h.counts;
  let sum = 0;
  for (let v = h.min; v <= h.max; v++) sum += c[v] * v;
  const mean = sum / h.n;
  let ss = 0;
  for (let v = h.min; v <= h.max; v++) {
    const count = c[v];
    if (count !== 0) ss += count * (v - mean) * (v - mean);
  }
  return Math.sqrt(ss / h.n);
}

function asHistogram(source: Histogram16 | ArrayLike<number>): Histogram16 {
  return 'counts' in source && source.counts instanceof Uint32Array ? source : histogram16(source as ArrayLike<number>);
}

// ---------------------------------------------------------------------------
// Auto levels (ports of auto_levels / auto_stf)
// ---------------------------------------------------------------------------

/** stretch.auto_levels: (black, white) from the 1st / 99th percentiles. */
export function autoLevels(
  source: Histogram16 | ArrayLike<number>,
  loPct = 1.0,
  hiPct = 99.0,
): { black: number; white: number } {
  const h = asHistogram(source);
  const black = percentile(h, loPct);
  let white = percentile(h, hiPct);
  if (white <= black) white = black + 1.0;
  return { black, white };
}

/**
 * stretch.auto_stf: PixInsight-style screen transfer. Robust median/MAD shadow
 * clip, white at the 99.8th percentile, midtones mapping the median to
 * `targetBg`. Returns linear-mode StretchParams.
 */
export function autoStf(
  source: Histogram16 | ArrayLike<number>,
  targetBg = STF_TARGET_BG,
  shadowClip = STF_SHADOW_CLIP,
): StretchParams {
  const h = asHistogram(source);
  if (h.n === 0) return { ...NEUTRAL_STRETCH };
  const med = median(h);
  const mad = medianAbsDeviation(h, med);
  const sigma = mad > 0 ? mad * MAD_TO_SIGMA : stdDev(h) || 1.0;
  const black = Math.max(h.min, med - shadowClip * sigma);
  let white = percentile(h, STF_WHITE_PERCENTILE); // clip a few hot pixels, keep the stars
  if (white <= black) white = black + 1.0;
  const x0 = Math.min(Math.max((med - black) / (white - black), 1e-4), 0.5);
  const denom = 2.0 * targetBg * x0 - targetBg - x0;
  const midtones = denom !== 0 ? (x0 * (targetBg - 1.0)) / denom : 0.5;
  return { black, white, midtones: Math.min(Math.max(midtones, 0.01), 0.99), mode: 'linear' };
}

// ---------------------------------------------------------------------------
// Transfer (CPU reference of the fragment shader)
// ---------------------------------------------------------------------------

/** PixInsight midtones transfer function: maps [0,1] -> [0,1], mtf(m, m) = 0.5. */
export function mtf(x: number, m: number): number {
  return ((m - 1.0) * x) / ((2.0 * m - 1.0) * x - m);
}

/** Midtones are clamped like apply_stretch, and 0.5 +/- 1e-3 is a no-op. */
export function effectiveMidtones(midtones: number): number {
  return Math.min(Math.max(midtones, 0.001), 0.999);
}

/** One raw sample through black/white + transfer + midtones -> [0, 1]. */
export function stretchValue(v: number, p: StretchParams): number {
  const white = p.white <= p.black ? p.black + 1.0 : p.white;
  let n = Math.min(Math.max((v - p.black) / (white - p.black), 0.0), 1.0);
  if (p.mode === 'log') n = Math.log1p(LOG_K * n) / Math.log1p(LOG_K);
  else if (p.mode === 'asinh') n = Math.asinh(ASINH_K * n) / Math.asinh(ASINH_K);
  const m = effectiveMidtones(p.midtones);
  if (Math.abs(m - 0.5) > 1e-3) n = mtf(n, m);
  return Math.min(Math.max(n, 0.0), 1.0);
}

/** [0, 1] -> 0..255 exactly as apply_stretch quantises (n*255 + 0.5, truncated). */
export function toDisplayByte(n: number): number {
  return Math.floor(Math.min(Math.max(n, 0), 1) * 255.0 + 0.5);
}
