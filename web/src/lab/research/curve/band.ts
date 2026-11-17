/**
 * Stability band for a live light curve (no uPlot import: unit-testable in node).
 */

/**
 * Trailing-window mean and ±1 sample standard deviation of a series, kept
 * as columns for a native uPlot band (bands: [{ series: [hi, lo] }]).
 * Trailing on purpose: the value at i depends on points i-w+1 .. i only,
 * so appending a point never changes the band already drawn (the past
 * never moves on a live chart). Extended incrementally: O(w) per new point.
 */
export interface BandColumns {
  n: number;
  mean: Float64Array;
  hi: Float64Array;
  lo: Float64Array;
}

export function emptyBand(capacity: number): BandColumns {
  return { n: 0, mean: new Float64Array(capacity), hi: new Float64Array(capacity), lo: new Float64Array(capacity) };
}

export function extendBand(b: BandColumns, ys: ArrayLike<number>, n: number, w: number): BandColumns {
  if (n < b.n) b = emptyBand(Math.max(1024, n));
  if (b.mean.length < n) {
    const cap = Math.max(n, b.mean.length * 2);
    const grow = (a: Float64Array) => {
      const c = new Float64Array(cap);
      c.set(a.subarray(0, b.n));
      return c;
    };
    b = { n: b.n, mean: grow(b.mean), hi: grow(b.hi), lo: grow(b.lo) };
  }
  for (let i = b.n; i < n; i++) {
    const i0 = Math.max(0, i - w + 1);
    const k = i - i0 + 1;
    let s = 0;
    for (let j = i0; j <= i; j++) s += ys[j];
    const m = s / k;
    let q = 0;
    for (let j = i0; j <= i; j++) q += (ys[j] - m) * (ys[j] - m);
    const sd = k > 2 ? Math.sqrt(q / (k - 1)) : 0; // fewer than 3 points: no spread claimed
    b.mean[i] = m;
    b.hi[i] = m + sd;
    b.lo[i] = m - sd;
  }
  b.n = n;
  return b;
}

