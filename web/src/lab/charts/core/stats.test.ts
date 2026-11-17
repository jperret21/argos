import { describe, expect, it } from 'vitest';
import { robustSigma, trailingBand, trailingMedian } from './stats';

describe('causal statistics', () => {
  it('a trailing band never changes the past when a point is appended', () => {
    const ys = [1, 2, 3, 2, 1, 5, 2, 3, 2, 2];
    const a = trailingBand(ys, 8, 4);
    const b = trailingBand(ys, 10, 4);
    for (let i = 0; i < 8; i++) {
      expect(b.mean[i]).toBe(a.mean[i]);
      expect(b.hi[i]).toBe(a.hi[i]);
    }
    expect(a.hi[1]).toBe(a.mean[1]); // fewer than 3 points: no spread claimed
  });
  it('trailing median skips flagged points', () => {
    const m = trailingMedian([1, 1, 9, 1, 1], 5, 3, (i) => i === 2);
    expect(m[3]).toBe(1);
  });
  it('robust sigma of a Gaussian-like sample', () => {
    const ys = [-1, -0.5, 0, 0.5, 1, 0.2, -0.3, 0.1, 100];
    expect(robustSigma(ys, 0, ys.length)).toBeLessThan(1.2);
  });
});
