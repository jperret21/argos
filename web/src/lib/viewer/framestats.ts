/**
 * Exposure statistics of a frame for the Framing band's exposure check
 * ("check the peak, not the picture"): the peaks of the brightest STARS
 * against full scale, how many pixels the ADC clipped, the sky. Pure
 * functions; framestats.worker.ts runs `starPeaks` off the main thread, the
 * clipped counts come from the viewer's exact 65 536-bin histogram.
 *
 * Promoted and adapted from src/lab/research/frame/stats.ts (web/lab/
 * PROPOSAL.md section 6, W3 "frame worker statistics"); the detection rules
 * are those of argos/core/imaging/metrics.py detect_stars, so a hot pixel is
 * not reported as a star peak:
 *  1. robust sky (median) and sigma (1.4826 x MAD) of the detection plane;
 *  2. 3 x 3 local maxima above sky + 5 sigma, brightest first;
 *  3. a peak needs PSF support: the mean of its 4 neighbours is more than
 *     2 sigma above the sky (metrics.py _has_psf_support);
 *  4. a peak within `radius` px of a brighter accepted one is the same star.
 * On a colour sensor the detection plane is the green half-resolution plane
 * (G1 + G2) / 2, as in the core, but the PEAK reported for each star is the
 * brightest RAW pixel (any colour) of its 2 x 2 cells within +/- 1 cell:
 * clipping happens per raw pixel, whatever its colour.
 *
 * What this is not: the science metrics. HFD, FWHM, star count and sky of
 * record come from the server (`frame_metrics`, computed by the core on the
 * full frame); these numbers are for the observer's exposure choice only.
 */

import type { Histogram16 } from './stretch';

export interface StarPeak {
  /** Brightest raw ADU of the star. */
  peak: number;
  /** Position in frame px (un-rotated, numpy convention). */
  x: number;
  y: number;
}

export interface StarPeaks {
  /** Accepted stars, brightest raw peak first (at most `max`). */
  stars: StarPeak[];
  /** Detection plane sky and sigma, in raw ADU. */
  sky: number;
  sigma: number;
  /** Local maxima above the threshold before the PSF and dedup rules (a star-count proxy). */
  maxima: number;
}

export interface StarPeakOptions {
  /** CFA layout ("RGGB", "GRBG", "GBRG", "BGGR"), or null for mono data. */
  bayer?: string | null;
  /** Dedup radius in detection-plane px (core default aperture: 5). */
  radius?: number;
  /** Stars kept (brightest first). */
  max?: number;
  /** Detection threshold in sigmas (core: 5). */
  nsigma?: number;
}

/** Offsets of the two green sites in a 2 x 2 CFA cell, by pattern. */
export function greenSites(bayer: string): [[number, number], [number, number]] | null {
  const p = bayer.toUpperCase();
  if (p.length !== 4) return null;
  const at: [number, number][] = [];
  for (let i = 0; i < 4; i++) if (p[i] === 'G') at.push([i % 2, i >> 1]);
  return at.length === 2 ? [at[0], at[1]] : null;
}

/** Median and MAD of a Float32 / integer plane, exactly, through a value histogram. */
function medianMad(plane: Float32Array | Uint16Array, scale: number): { median: number; mad: number } {
  // Values are integers (mono) or half-integers (green mean): bin at `scale` per ADU.
  const n = plane.length;
  let max = 0;
  for (let i = 0; i < n; i++) if (plane[i] > max) max = plane[i];
  const size = Math.ceil(max * scale) + 1;
  const h = new Uint32Array(size);
  for (let i = 0; i < n; i++) h[Math.round(plane[i] * scale)]++;
  const rank = (hist: Uint32Array, k: number) => {
    let acc = 0;
    for (let v = 0; v < hist.length; v++) {
      acc += hist[v];
      if (acc > k) return v;
    }
    return hist.length - 1;
  };
  const med = (hist: Uint32Array) =>
    n % 2 ? rank(hist, (n - 1) / 2) : (rank(hist, n / 2 - 1) + rank(hist, n / 2)) / 2;
  const m = med(h);
  const dev = new Uint32Array(size);
  for (let v = 0; v < size; v++) if (h[v]) dev[Math.min(size - 1, Math.round(Math.abs(v - m)))] += h[v];
  return { median: m / scale, mad: med(dev) / scale };
}

/**
 * Peaks of the brightest stars. `px` is width x height raw samples (one
 * channel). Runs in about 10-20 ms on a 2 Mpx frame: call it in the worker.
 */
export function starPeaks(px: Uint16Array, width: number, height: number, o: StarPeakOptions = {}): StarPeaks {
  const radius = Math.max(2, o.radius ?? 5);
  const keep = o.max ?? 16;
  const nsig = o.nsigma ?? 5;
  const sites = o.bayer ? greenSites(o.bayer) : null;

  // Detection plane g (w x h) and the raw maximum of each plane pixel (m).
  let w: number;
  let h: number;
  let g: Float32Array | Uint16Array;
  let m: Uint16Array;
  if (sites) {
    w = width >> 1;
    h = height >> 1;
    const gf = new Float32Array(w * h);
    const mm = new Uint16Array(w * h);
    const [[ax, ay], [bx, by]] = sites;
    for (let y = 0; y < h; y++) {
      const r0 = 2 * y * width;
      const r1 = r0 + width;
      for (let x = 0; x < w; x++) {
        const c = 2 * x;
        const i = y * w + x;
        const g1 = px[(ay ? r1 : r0) + c + ax];
        const g2 = px[(by ? r1 : r0) + c + bx];
        gf[i] = (g1 + g2) / 2;
        let v = px[r0 + c];
        if (px[r0 + c + 1] > v) v = px[r0 + c + 1];
        if (px[r1 + c] > v) v = px[r1 + c];
        if (px[r1 + c + 1] > v) v = px[r1 + c + 1];
        mm[i] = v;
      }
    }
    g = gf;
    m = mm;
  } else {
    w = width;
    h = height;
    g = px;
    m = px;
  }

  const { median: sky, mad } = medianMad(g, sites ? 2 : 1);
  const sigma = Math.max(1, 1.4826 * mad);
  const thr = sky + nsig * sigma;
  const support = sky + 2 * sigma;

  const cand: number[] = [];
  for (let y = 1; y < h - 1; y++) {
    const row = y * w;
    for (let x = 1; x < w - 1; x++) {
      const i = row + x;
      const v = g[i];
      if (v <= thr) continue;
      if (
        v >= g[i - 1] && v >= g[i + 1] && v >= g[i - w] && v >= g[i + w] &&
        v >= g[i - w - 1] && v >= g[i - w + 1] && v >= g[i + w - 1] && v >= g[i + w + 1]
      ) {
        cand.push(i);
      }
    }
  }
  cand.sort((a, b) => g[b] - g[a]);

  const stars: StarPeak[] = [];
  const acc: [number, number][] = [];
  const r2 = radius * radius;
  for (const i of cand) {
    const x = i % w;
    const y = (i - x) / w;
    if (acc.some(([ax, ay]) => (x - ax) ** 2 + (y - ay) ** 2 < r2)) continue;
    if ((g[i - 1] + g[i + 1] + g[i - w] + g[i + w]) / 4 <= support) continue; // hot pixel / cosmic
    let peak = 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) peak = Math.max(peak, m[i + dy * w + dx]);
    acc.push([x, y]);
    stars.push(sites ? { peak, x: 2 * x + 0.5, y: 2 * y + 0.5 } : { peak, x, y });
    if (acc.length >= 4 * keep) break;
  }
  stars.sort((a, b) => b.peak - a.peak);
  return { stars: stars.slice(0, keep), sky, sigma, maxima: cand.length };
}

/** Largest power-of-two step that at least 90 % of the samples sit on (12-bit data in 16 bits: 16). */
export function adcStep(h: Histogram16): number {
  if (h.n === 0) return 1;
  let step = 1;
  for (let bit = 1; bit < 16; bit++) {
    const q = 1 << bit;
    let on = 0;
    for (let v = 0; v <= h.max; v += q) on += h.counts[v];
    if (on / h.n >= 0.9) step = q;
    else break;
  }
  return step;
}

export interface Clipping {
  /** Highest code the ADC can produce in this data: 65 536 - step (65 535 for 16-bit data). */
  topCode: number;
  step: number;
  /** Pixels at the top code: clipped by the ADC. */
  clipped: number;
  /** Pixels at or above `level` (the profile's linearity limit), when given. */
  aboveLevel: number | null;
  /** Fraction of pixels clipped. */
  fraction: number;
}

/** Clipped pixels from the exact histogram of the frame. */
export function clipping(h: Histogram16, level: number | null = null): Clipping {
  const step = adcStep(h);
  const topCode = 65536 - step;
  let clipped = 0;
  for (let v = topCode; v <= 65535; v++) clipped += h.counts[v];
  let above: number | null = null;
  if (level !== null && Number.isFinite(level)) {
    above = 0;
    for (let v = Math.max(0, Math.ceil(level)); v <= 65535; v++) above += h.counts[v];
  }
  return { topCode, step, clipped, aboveLevel: above, fraction: h.n ? clipped / h.n : 0 };
}
