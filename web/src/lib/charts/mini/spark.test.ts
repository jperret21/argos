import { describe, expect, it } from 'vitest';
import { sparkScale } from './spark';

describe('sparkline scale', () => {
  it('maps the window and the padded data extent; a reference widens the range', () => {
    const xs = [0, 1, 2, 3];
    const ys = [10, 12, NaN, 11];
    const s = sparkScale(104, 24, { xs, ys, n: 4, color: 'x' })!;
    expect(s.x0).toBe(0);
    expect(s.x1).toBe(3);
    expect(s.X(0)).toBe(2);
    expect(s.X(3)).toBe(102);
    expect(s.y0).toBeCloseTo(10 - 0.24, 9);
    expect(s.y1).toBeCloseTo(12 + 0.24, 9);
    expect(s.Y(s.y0)).toBe(22); // bottom
    const ref = sparkScale(104, 24, { xs, ys, n: 4, color: 'x', ref: 20 })!;
    expect(ref.y1).toBeGreaterThan(20);
    // Inverted (airmass, magnitudes): larger values lower.
    const inv = sparkScale(104, 24, { xs, ys, n: 4, color: 'x', invert: true })!;
    expect(inv.Y(inv.y1)).toBe(22);
  });

  it('has nothing to draw without a finite value in the window', () => {
    expect(sparkScale(10, 10, { xs: [0], ys: [NaN], n: 1, color: 'x' })).toBeNull();
    expect(sparkScale(10, 10, { xs: [], ys: [], n: 0, color: 'x' })).toBeNull();
  });
});
