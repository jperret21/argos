/**
 * Display histogram of a frame: port of the Qt preview's binning
 * (argos/workers/preview_processor.py + argos/core/imaging/stretch.py
 * quantization_step / _histogram_edges / channel_histograms).
 *
 * - Range: [min, 99.8th percentile] of the frame, so the sky peak fills the
 *   plot instead of collapsing against the left edge (stars above the range
 *   are left out of the plot, never out of the data).
 * - Bins snap to the sensor's ADU quantization grid: a Seestar delivers 12-bit
 *   values shifted into 16 bits (multiples of 16 ADU), and bins narrower than
 *   that grid draw a comb of empty bins. Levels sit at bin centres.
 *
 * Everything is computed exactly from the viewer's 65536-bin count table
 * (histogram16), so no pass over the pixels is repeated. Differences from the
 * Qt widget: the quantization step is measured on every pixel instead of a
 * 200 000-sample stride, and CFA frames give one pooled curve, not R/G/B.
 */

import { type Histogram16, percentile, STF_WHITE_PERCENTILE } from './stretch';

export const DEFAULT_BINS = 128;

export interface BinnedHistogram {
  /** nbins + 1 bin edges (ADU); a value v falls in [edges[i], edges[i+1]), last bin closed. */
  edges: Float64Array;
  /** nbins bin centres (ADU). */
  centers: Float64Array;
  /** nbins sample counts. */
  counts: Float64Array;
  /** Quantization step used for the edges (1 = continuous data). */
  step: number;
  lo: number;
  hi: number;
}

/**
 * Largest power-of-two grid that at least `minFraction` of the samples lie on
 * (stretch.quantization_step). Returns 1 when no grid dominates.
 */
export function quantizationStep(h: Histogram16, minFraction = 0.9): number {
  if (h.n === 0) return 1;
  let step = 1;
  for (let bit = 1; bit < 16; bit++) {
    const q = 1 << bit;
    let onGrid = 0;
    for (let v = 0; v <= h.max; v += q) onGrid += h.counts[v];
    if (onGrid / h.n >= minFraction) step = q;
    else break;
  }
  return step;
}

/** Plot range of the preview: [min, 99.8th percentile], never empty. */
export function displayRange(h: Histogram16): { lo: number; hi: number } {
  const lo = h.min;
  let hi = percentile(h, STF_WHITE_PERCENTILE);
  if (!(hi > lo)) hi = h.max > lo ? h.max : lo + 1;
  return { lo, hi };
}

/** stretch._histogram_edges: uniform edges, snapped to the grid when quantized. */
export function histogramEdges(step: number, bins: number, lo: number, hi: number): Float64Array {
  if (step < 2) {
    // numpy.linspace(lo, hi, bins + 1): start + i * delta / bins, last = stop.
    const edges = new Float64Array(bins + 1);
    const delta = (hi - lo) / bins;
    for (let i = 0; i <= bins; i++) edges[i] = lo + i * delta;
    edges[bins] = hi;
    return edges;
  }
  const targetW = (hi - lo) / bins;
  const width = Math.max(1, Math.round(targetW / step)) * step;
  const start = (Math.floor(lo / step) - 0.5) * step;
  const nbins = Math.max(1, Math.ceil((hi - start) / width));
  const edges = new Float64Array(nbins + 1);
  for (let i = 0; i <= nbins; i++) edges[i] = start + width * i;
  return edges;
}

/**
 * numpy.histogram(samples, edges) computed from the count table: integer
 * values outside [edges[0], edges[last]] are dropped.
 */
export function binHistogram(
  h: Histogram16,
  bins = DEFAULT_BINS,
  range: { lo: number; hi: number } = displayRange(h),
): BinnedHistogram {
  let { lo, hi } = range;
  if (hi <= lo) hi = lo + 1;
  const step = quantizationStep(h);
  const edges = histogramEdges(step, bins, lo, hi);
  const nbins = edges.length - 1;
  const counts = new Float64Array(nbins);
  const first = Math.max(0, Math.ceil(edges[0]));
  const last = Math.min(65535, Math.floor(edges[nbins]));
  let bin = 0;
  for (let v = first; v <= last; v++) {
    const c = h.counts[v];
    if (c === 0) continue;
    while (bin < nbins - 1 && v >= edges[bin + 1]) bin++;
    if (v < edges[bin]) continue; // cannot happen for v >= edges[0]; kept for safety
    counts[bin] += c;
  }
  const centers = new Float64Array(nbins);
  for (let i = 0; i < nbins; i++) centers[i] = (edges[i] + edges[i + 1]) * 0.5;
  return { edges, centers, counts, step, lo, hi };
}
