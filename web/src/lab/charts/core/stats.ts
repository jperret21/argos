/**
 * Causal statistics for live charts: the value at i depends on points
 * i-w+1 .. i only, so appending a point never changes what is already drawn
 * (the past never moves on a live chart). Computed over a whole column;
 * charts show the revealed prefix.
 */

export interface Band {
  mean: Float64Array;
  hi: Float64Array;
  lo: Float64Array;
}

/** Trailing mean +/- 1 sample sigma over w points (NaN-aware; < 3 points: no spread claimed). */
export function trailingBand(ys: ArrayLike<number>, n: number, w: number): Band {
  const mean = new Float64Array(n);
  const hi = new Float64Array(n);
  const lo = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let s = 0;
    let k = 0;
    for (let j = Math.max(0, i - w + 1); j <= i; j++) {
      const v = ys[j];
      if (Number.isFinite(v)) {
        s += v;
        k++;
      }
    }
    const m = k ? s / k : NaN;
    let q = 0;
    for (let j = Math.max(0, i - w + 1); j <= i; j++) {
      const v = ys[j];
      if (Number.isFinite(v)) q += (v - m) * (v - m);
    }
    const sd = k > 2 ? Math.sqrt(q / (k - 1)) : 0;
    mean[i] = m;
    hi[i] = m + sd;
    lo[i] = m - sd;
  }
  return { mean, hi, lo };
}

/** Trailing median over w points (NaN-aware). */
export function trailingMedian(ys: ArrayLike<number>, n: number, w: number, skip?: (i: number) => boolean): Float64Array {
  const out = new Float64Array(n);
  const buf: number[] = [];
  for (let i = 0; i < n; i++) {
    buf.length = 0;
    for (let j = Math.max(0, i - w + 1); j <= i; j++) if (Number.isFinite(ys[j]) && !skip?.(j)) buf.push(ys[j]);
    if (!buf.length) {
      out[i] = NaN;
      continue;
    }
    buf.sort((a, b) => a - b);
    const k = buf.length;
    out[i] = k % 2 ? buf[(k - 1) / 2] : (buf[k / 2 - 1] + buf[k / 2]) / 2;
  }
  return out;
}

/** Robust scatter: 1.4826 x MAD of the finite values in [i0, i1). */
export function robustSigma(ys: ArrayLike<number>, i0: number, i1: number): number {
  const a: number[] = [];
  for (let i = i0; i < i1; i++) if (Number.isFinite(ys[i])) a.push(ys[i]);
  if (a.length < 3) return NaN;
  a.sort((x, y) => x - y);
  const med = a[a.length >> 1];
  const d = a.map((v) => Math.abs(v - med)).sort((x, y) => x - y);
  return 1.4826 * d[d.length >> 1];
}

/** Root mean square about the mean of the finite values in [i0, i1). */
export function rms(ys: ArrayLike<number>, i0: number, i1: number): number {
  let s = 0;
  let k = 0;
  for (let i = i0; i < i1; i++) {
    if (Number.isFinite(ys[i])) {
      s += ys[i];
      k++;
    }
  }
  if (k < 2) return NaN;
  const m = s / k;
  let q = 0;
  for (let i = i0; i < i1; i++) if (Number.isFinite(ys[i])) q += (ys[i] - m) ** 2;
  return Math.sqrt(q / (k - 1));
}
