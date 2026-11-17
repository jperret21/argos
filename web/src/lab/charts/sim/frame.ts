/**
 * Synthetic 16-bit frame histograms for the histogram lab, consistent with
 * the night's frames: the sky median is the Conditions "sky" value, the
 * star tail grows with the star count and the defocus (HFD), and pixels at
 * 65 535 appear when the target saturates. A Seestar-like 12-bit signal
 * shifted into 16 bits puts every value on a 16-ADU grid (the quantization
 * lib/viewer/histogram.ts detects). Built directly as a count table (the
 * shape lib/viewer/stretch.ts consumes), so no 2 Mpx frame is synthesized.
 */

import type { Histogram16 } from '../../../lib/viewer/stretch';
import { gauss, prng } from './night';

export const FRAME_W = 1080;
export const FRAME_H = 1920;
const GRID = 16;

function erf(x: number): number {
  // Abramowitz-Stegun 7.1.26 (|error| < 1.5e-7).
  const s = Math.sign(x);
  const a = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * a);
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-a * a);
  return s * y;
}
const Phi = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));

export interface FrameParams {
  seed: number;
  sky: number;
  /** Background noise, ADU. */
  sigma: number;
  stars: number;
  hfd: number;
  saturatedPx: number;
}

export function synthHistogram(p: FrameParams): Histogram16 {
  const counts = new Uint32Array(65536);
  const N = FRAME_W * FRAME_H;
  const rand = prng(p.seed);
  // Pixels of stars above 4 sigma: ~3.5 per star at focus, more (and fainter)
  // when defocused; the flux is conserved, so the tail steepens.
  const defocus = Math.max(1, p.hfd / 2.2);
  const starPx = Math.min(N * 0.03, p.stars * 3.5 * defocus);
  const bgPx = N - starPx - p.saturatedPx - 300;
  const add = (v: number, c: number) => {
    if (c <= 0) return;
    const k = Math.max(0, Math.min(65535, v));
    counts[k] += Math.round(c);
  };
  // Background: a main Gaussian and a slightly brighter gradient component.
  for (let v = 0; v < 65536; v += GRID) {
    const lo = v - GRID / 2;
    const hi = v + GRID / 2;
    const main = 0.78 * (Phi((hi - p.sky) / p.sigma) - Phi((lo - p.sky) / p.sigma));
    const grad = 0.22 * (Phi((hi - p.sky - 22) / (p.sigma * 1.35)) - Phi((lo - p.sky - 22) / (p.sigma * 1.35)));
    const e = bgPx * (main + grad);
    if (e < 0.05) continue;
    add(v, e + Math.sqrt(e) * gauss(rand));
  }
  // Star tail: a power law from 4 sigma above the sky to the full well.
  const x0 = 4 * p.sigma;
  const alpha = 2.0 + 0.35 * (defocus - 1);
  const norm = (alpha - 1) / x0;
  for (let v = Math.ceil((p.sky + x0) / GRID) * GRID; v < 65520; v += GRID) {
    const x = v - p.sky;
    const e = starPx * norm * Math.pow(x / x0, -alpha) * GRID;
    if (e < 0.02) {
      if (rand() < e) add(v, 1);
      continue;
    }
    add(v, Math.max(0, e + Math.sqrt(e) * gauss(rand)));
  }
  add(65535, p.saturatedPx);
  for (let i = 0; i < 300; i++) add(Math.floor(p.sky + 200 + rand() * 30000) & ~(GRID - 1), 1); // hot pixels
  let n = 0;
  let min = 65535;
  let max = 0;
  for (let v = 0; v < 65536; v++) {
    const c = counts[v];
    if (!c) continue;
    n += c;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  return { counts, n, min, max };
}
