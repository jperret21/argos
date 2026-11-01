import { describe, expect, it } from 'vitest';
import { emptyBand, extendBand } from './band';

describe('extendBand', () => {
  const ys = Float64Array.from({ length: 200 }, (_, i) => 10 + 0.01 * Math.sin(i * 1.7) + (i > 150 ? 0.05 * Math.cos(i) : 0));

  it('gives the trailing mean and sample sigma', () => {
    const b = extendBand(emptyBand(4), ys, 40, 15);
    const win = Array.from(ys.subarray(25, 40));
    const m = win.reduce((a, v) => a + v, 0) / win.length;
    const sd = Math.sqrt(win.reduce((a, v) => a + (v - m) ** 2, 0) / (win.length - 1));
    expect(b.mean[39]).toBeCloseTo(m, 12);
    expect(b.hi[39] - b.mean[39]).toBeCloseTo(sd, 12);
    expect(b.mean[39] - b.lo[39]).toBeCloseTo(sd, 12);
  });

  it('never changes values already computed when points are appended', () => {
    let b = extendBand(emptyBand(8), ys, 100, 15);
    const before = Float64Array.from(b.hi.subarray(0, 100));
    for (let n = 101; n <= 200; n++) b = extendBand(b, ys, n, 15);
    expect(Array.from(b.hi.subarray(0, 100))).toEqual(Array.from(before));
  });

  it('claims no spread with fewer than three points, and restarts on a shorter series', () => {
    let b = extendBand(emptyBand(8), ys, 2, 15);
    expect(b.hi[1]).toBe(b.mean[1]);
    b = extendBand(b, ys, 60, 15);
    b = extendBand(b, ys, 10, 15);
    expect(b.n).toBe(10);
  });
});
