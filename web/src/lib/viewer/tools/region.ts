/**
 * Region statistics on the frame's own pixels: a port of
 * argos/core/imaging/stretch.py region_stats (n, mean, median, std, min, max;
 * numpy's population std, ddof = 0) over the RAW samples of a frame-aligned
 * box (fits_viewer.py:397-414 read the rendered array; the web reads the data,
 * so a colour preview or a palette never changes the numbers).
 *
 * - Mono and raw-mosaic frames: every sample of the box, raw ADU.
 * - A colour sensor's mosaic additionally gives each colour's median (R, G
 *   from both green sites, B), the sky per channel, on real samples only.
 * - RGB frames: the mean of the three channels per pixel, as Qt did.
 * - `clipped`: samples at or above the saturation threshold (full well).
 * Exact order statistics through a 65 536-bin count table for large boxes
 * (no sort), so the whole frame costs one pass.
 */

import type { CfaSites } from '../palettes/cfa';
import type { FrameRect } from './geometry';

export interface RegionStats {
  rect: FrameRect;
  n: number;
  mean: number;
  median: number;
  std: number;
  min: number;
  max: number;
  /** Samples >= the saturation threshold (null when no threshold was given). */
  clipped: number | null;
  /** Per-colour medians of a CFA mosaic (null for mono or RGB frames). */
  channels: { r: number; g: number; b: number } | null;
}

/** numpy.median of a count table (the mean of the two middle samples for an even n). */
function medianOfCounts(counts: Uint32Array, n: number, lo: number, hi: number): number {
  if (n === 0) return Number.NaN;
  const k1 = (n - 1) >> 1;
  const k2 = n >> 1;
  let seen = 0;
  let a = Number.NaN;
  for (let v = lo; v <= hi; v++) {
    const c = counts[v];
    if (!c) continue;
    if (Number.isNaN(a) && seen + c > k1) a = v;
    if (seen + c > k2) return (a + v) / 2;
    seen += c;
  }
  return a;
}

function sortedMedian(values: Float64Array): number {
  const n = values.length;
  if (!n) return Number.NaN;
  const s = Float64Array.from(values).sort();
  return n % 2 ? s[n >> 1] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

const COUNTS_ABOVE = 4096;

/**
 * Statistics of the pixels of `rect` (clamped to the frame; null when empty).
 * `pixels`: width * height * channels uint16, row 0 at the top.
 */
export function regionStats(
  pixels: Uint16Array,
  width: number,
  height: number,
  channels: 1 | 3,
  rect: FrameRect,
  options: { sites?: CfaSites | null; threshold?: number | null } = {},
): RegionStats | null {
  const x0 = Math.max(0, Math.min(width, rect.x0));
  const y0 = Math.max(0, Math.min(height, rect.y0));
  const x1 = Math.max(x0, Math.min(width, rect.x1));
  const y1 = Math.max(y0, Math.min(height, rect.y1));
  const n = (x1 - x0) * (y1 - y0);
  if (n <= 0) return null;
  const box = { x0, y0, x1, y1 };
  const threshold = options.threshold ?? null;

  if (channels === 3) {
    // Qt: region.mean(axis=2) for an RGB array.
    const vals = new Float64Array(n);
    let k = 0;
    let clipped = 0;
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++, k++) {
        const i = (y * width + x) * 3;
        vals[k] = (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3;
        if (threshold !== null && Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) >= threshold) clipped++;
      }
    }
    let sum = 0;
    let min = Infinity;
    let max = -Infinity;
    for (const v of vals) {
      sum += v;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    const mean = sum / n;
    let ss = 0;
    for (const v of vals) ss += (v - mean) * (v - mean);
    return { rect: box, n, mean, median: sortedMedian(vals), std: Math.sqrt(ss / n), min, max, clipped: threshold === null ? null : clipped, channels: null };
  }

  // One raw sample per pixel. Two passes: sums and the count table, then the deviations.
  const counts = n > COUNTS_ABOVE ? new Uint32Array(65536) : null;
  const small = counts ? null : new Float64Array(n);
  let sum = 0;
  let min = 65535;
  let max = 0;
  let clipped = 0;
  let k = 0;
  for (let y = y0; y < y1; y++) {
    const row = y * width;
    for (let x = x0; x < x1; x++) {
      const v = pixels[row + x];
      sum += v;
      if (v < min) min = v;
      if (v > max) max = v;
      if (threshold !== null && v >= threshold) clipped++;
      if (counts) counts[v]++;
      else small![k++] = v;
    }
  }
  const mean = sum / n;
  let ss = 0;
  let med: number;
  if (counts) {
    for (let v = min; v <= max; v++) {
      const c = counts[v];
      if (c) ss += c * (v - mean) * (v - mean);
    }
    med = medianOfCounts(counts, n, min, max);
  } else {
    for (const v of small!) ss += (v - mean) * (v - mean);
    med = sortedMedian(small!);
  }

  let perChannel: RegionStats['channels'] = null;
  const sites = options.sites ?? null;
  if (sites) {
    // Colour of each site of the 2 x 2 cell: 0 R, 1 G, 2 B.
    const colour = new Uint8Array(4).fill(1);
    colour[sites.r[1] * 2 + sites.r[0]] = 0;
    colour[sites.b[1] * 2 + sites.b[0]] = 2;
    const tables = [new Uint32Array(65536), new Uint32Array(65536), new Uint32Array(65536)];
    const nc = [0, 0, 0];
    for (let y = y0; y < y1; y++) {
      const row = y * width;
      const cy = (y & 1) * 2;
      for (let x = x0; x < x1; x++) {
        const c = colour[cy + (x & 1)];
        tables[c][pixels[row + x]]++;
        nc[c]++;
      }
    }
    const med = (c: number) => medianOfCounts(tables[c], nc[c], min, max);
    perChannel = { r: med(0), g: med(1), b: med(2) };
  }

  return { rect: box, n, mean, median: med, std: Math.sqrt(ss / n), min, max, clipped: threshold === null ? null : clipped, channels: perChannel };
}
