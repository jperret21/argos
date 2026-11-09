/**
 * Statistics of a live curve that never move the past (no uPlot import:
 * unit-tested in node). Merged from src/lab/research/curve/band.ts (the
 * incremental trailing band) and src/lab/charts/core/stats.ts (finite-aware
 * windows, rms).
 */

/**
 * Trailing mean ± 1 sample standard deviation over the last `w` VALID values
 * (finite, and not excluded: a saturated point's value is clipped, so it is
 * left out like the plot baselines of S16). At an excluded row the band keeps
 * the previous value: the window has not changed. Trailing on purpose: the
 * value at row i depends on rows <= i only, so an append never changes the
 * band already drawn. Below 3 values no spread is claimed (sd = 0).
 */
export class TrailingBand {
  n = 0;
  mean = new Float64Array(0);
  sd = new Float64Array(0);
  /** mean + sd and mean - sd: the band's edges, kept as columns for the plot. */
  hi = new Float64Array(0);
  lo = new Float64Array(0);
  /** Valid values in the window at each row. */
  count = new Uint16Array(0);

  constructor(readonly w = 15) {}

  private grow(cap: number): void {
    if (this.mean.length >= cap) return;
    const size = Math.max(cap, this.mean.length * 2, 256);
    const keep = <A extends Float64Array | Uint16Array>(a: A, b: A): A => {
      b.set(a.subarray(0, this.n));
      return b;
    };
    this.mean = keep(this.mean, new Float64Array(size));
    this.sd = keep(this.sd, new Float64Array(size));
    this.hi = keep(this.hi, new Float64Array(size));
    this.lo = keep(this.lo, new Float64Array(size));
    this.count = keep(this.count, new Uint16Array(size));
  }

  /** Forget everything from row `from` on (an inserted or edited row). */
  truncate(from: number): void {
    this.n = Math.min(this.n, Math.max(0, from));
  }

  /**
   * Bring the band up to `n` rows of `ys`. `skip(i)` excludes a row from the
   * statistics (saturated). O(w) per new row.
   */
  extend(ys: ArrayLike<number>, n: number, skip?: (i: number) => boolean): void {
    if (n < this.n) this.n = 0;
    this.grow(n);
    const buf: number[] = [];
    for (let i = this.n; i < n; i++) {
      // The last w valid values at or before i.
      buf.length = 0;
      for (let j = i; j >= 0 && buf.length < this.w; j--) {
        const v = ys[j];
        if (Number.isFinite(v) && !skip?.(j)) buf.push(v);
      }
      const k = buf.length;
      if (!k) {
        this.mean[i] = this.sd[i] = this.hi[i] = this.lo[i] = NaN;
        this.count[i] = 0;
        continue;
      }
      let s = 0;
      for (const v of buf) s += v;
      const m = s / k;
      let q = 0;
      for (const v of buf) q += (v - m) * (v - m);
      const sd = k > 2 ? Math.sqrt(q / (k - 1)) : 0;
      this.mean[i] = m;
      this.sd[i] = sd;
      this.hi[i] = m + sd;
      this.lo[i] = m - sd;
      this.count[i] = k;
    }
    this.n = n;
  }
}

/** Median of the finite values of `ys[0..n)` that `keep` accepts; NaN when none. */
export function medianOf(ys: ArrayLike<number>, n: number, keep?: (i: number) => boolean): number {
  const a: number[] = [];
  for (let i = 0; i < n; i++) if (Number.isFinite(ys[i]) && (!keep || keep(i))) a.push(ys[i]);
  if (!a.length) return NaN;
  a.sort((x, y) => x - y);
  const k = a.length >> 1;
  return a.length % 2 ? a[k] : (a[k - 1] + a[k]) / 2;
}

/**
 * Baseline of the relative-flux view (S16, fixed in 0.5.0): the median of the
 * unsaturated finite fluxes, or of every finite flux when all are saturated;
 * NaN when there is no positive baseline (the series then draws nothing).
 */
export function fluxBaseline(flux: ArrayLike<number>, n: number, saturated: (i: number) => boolean): number {
  let m = medianOf(flux, n, (i) => !saturated(i));
  if (!Number.isFinite(m)) m = medianOf(flux, n);
  return m > 0 ? m : NaN;
}

/** Mean and sample standard deviation of finite values; sd NaN under 2 values. */
export function meanSd(values: readonly number[]): { mean: number; sd: number; n: number } {
  const v = values.filter((x) => Number.isFinite(x));
  if (!v.length) return { mean: NaN, sd: NaN, n: 0 };
  const m = v.reduce((a, b) => a + b, 0) / v.length;
  if (v.length < 2) return { mean: m, sd: NaN, n: 1 };
  const q = v.reduce((a, b) => a + (b - m) * (b - m), 0);
  return { mean: m, sd: Math.sqrt(q / (v.length - 1)), n: v.length };
}
