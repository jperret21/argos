/**
 * Frame statistics on 16-bit pixels, O(n) with a 65 536-bin histogram (no
 * sort): median, MAD, percentiles, a display histogram, a star count and an
 * HFD estimate. Pure functions: the worker runs them, the tests check them.
 */

export interface FrameStats {
  min: number;
  max: number;
  mean: number;
  median: number;
  /** Median absolute deviation (not scaled). */
  mad: number;
  p998: number;
  /** Display histogram over [histLo, histHi), `bins` counts. */
  hist: Uint32Array;
  histLo: number;
  histHi: number;
  stars: number;
  hfd: number;
  saturated: number;
}

/** Value at rank `k` (0-based) of a 65 536-bin histogram. */
export function rankFromHistogram(h: Uint32Array, k: number): number {
  let acc = 0;
  for (let v = 0; v < h.length; v++) {
    acc += h[v];
    if (acc > k) return v;
  }
  return h.length - 1;
}

/** Median of a histogram of n samples: mean of the two middle ranks when n is even. */
export function medianFromHistogram(h: Uint32Array, n: number): number {
  if (n === 0) return NaN;
  if (n % 2 === 1) return rankFromHistogram(h, (n - 1) / 2);
  return (rankFromHistogram(h, n / 2 - 1) + rankFromHistogram(h, n / 2)) / 2;
}

/** MAD from the value histogram: histogram of |v - median| built from the bins. */
export function madFromHistogram(h: Uint32Array, n: number, median: number): number {
  const dev = new Uint32Array(h.length);
  for (let v = 0; v < h.length; v++) {
    const c = h[v];
    if (c) dev[Math.min(h.length - 1, Math.round(Math.abs(v - median)))] += c;
  }
  return medianFromHistogram(dev, n);
}

export function frameStats(px: Uint16Array, width: number, height: number, bins = 256): FrameStats {
  const n = px.length;
  const h = new Uint32Array(65536);
  let min = 65535;
  let max = 0;
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const v = px[i];
    h[v]++;
    sum += v;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const median = medianFromHistogram(h, n);
  const mad = madFromHistogram(h, n, median);
  const p998 = rankFromHistogram(h, Math.floor(n * 0.998));

  const histLo = min;
  const histHi = Math.max(p998 + 1, min + bins);
  const hist = new Uint32Array(bins);
  const scale = bins / (histHi - histLo);
  for (let v = histLo; v < histHi; v++) {
    const c = h[v];
    if (c) hist[Math.min(bins - 1, Math.floor((v - histLo) * scale))] += c;
  }

  const sigma = 1.4826 * mad;
  const { stars, hfd } = detectStars(px, width, height, median, Math.max(1, sigma));
  return { min, max, mean: sum / n, median, mad, p998, hist, histLo, histHi, stars, hfd, saturated: h[65535] };
}

/**
 * Local maxima above median + 6 sigma (8-neighbourhood) count as stars; the
 * HFD is the flux-weighted mean radius x 2 of the 24 brightest, within r = 8.
 */
export function detectStars(
  px: Uint16Array,
  w: number,
  hgt: number,
  median: number,
  sigma: number,
): { stars: number; hfd: number } {
  const thr = median + 6 * sigma;
  const peaks: { i: number; v: number }[] = [];
  for (let y = 8; y < hgt - 8; y++) {
    const row = y * w;
    for (let x = 8; x < w - 8; x++) {
      const i = row + x;
      const v = px[i];
      if (v <= thr) continue;
      if (
        v >= px[i - 1] && v > px[i + 1] && v >= px[i - w] && v > px[i + w] &&
        v >= px[i - w - 1] && v >= px[i - w + 1] && v > px[i + w - 1] && v > px[i + w + 1]
      ) {
        peaks.push({ i, v });
      }
    }
  }
  peaks.sort((a, b) => b.v - a.v);
  let hfdSum = 0;
  let hfdN = 0;
  for (const p of peaks.slice(0, 24)) {
    if (p.v >= 65535) continue; // saturated cores bias the HFD
    const cx = p.i % w;
    const cy = (p.i - cx) / w;
    let f = 0;
    let fr = 0;
    for (let dy = -8; dy <= 8; dy++) {
      for (let dx = -8; dx <= 8; dx++) {
        const r = Math.hypot(dx, dy);
        if (r > 8) continue;
        const s = px[(cy + dy) * w + cx + dx] - median;
        if (s <= 0) continue;
        f += s;
        fr += s * r;
      }
    }
    if (f > 0) {
      hfdSum += (2 * fr) / f;
      hfdN++;
    }
  }
  return { stars: peaks.length, hfd: hfdN ? hfdSum / hfdN : NaN };
}
