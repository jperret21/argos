import { describe, expect, it } from 'vitest';
import { detectStars, frameStats, madFromHistogram, medianFromHistogram } from './stats';

function hist(values: number[]): Uint32Array {
  const h = new Uint32Array(65536);
  for (const v of values) h[v]++;
  return h;
}

describe('histogram statistics (lab)', () => {
  it('median of odd and even counts matches a sort', () => {
    expect(medianFromHistogram(hist([5, 1, 9]), 3)).toBe(5);
    expect(medianFromHistogram(hist([4, 1, 9, 7]), 4)).toBe(5.5);
  });

  it('MAD of a known sample', () => {
    // |x - 5| = 4 4 0 1 3 -> median 3
    const v = [1, 9, 5, 6, 2];
    const h = hist(v);
    expect(madFromHistogram(h, v.length, medianFromHistogram(h, v.length))).toBe(3);
  });

  it('frameStats on a flat frame with one star', () => {
    const w = 64;
    const hgt = 64;
    const px = new Uint16Array(w * hgt);
    for (let i = 0; i < px.length; i++) px[i] = 1000 + (i % 3); // 1000, 1001, 1002
    // A 3x3 star at (32, 32), peak 9000.
    for (let dy = -1; dy <= 1; dy++)
      for (let dx = -1; dx <= 1; dx++) px[(32 + dy) * w + 32 + dx] = dx === 0 && dy === 0 ? 9000 : 4000;
    const s = frameStats(px, w, hgt);
    expect(s.min).toBe(1000);
    expect(s.max).toBe(9000);
    expect(s.median).toBe(1001);
    expect(s.stars).toBe(1);
    expect(s.hfd).toBeGreaterThan(0.5);
    expect(s.hfd).toBeLessThan(3);
    expect(s.hist.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(px.length);
  });

  it('detectStars ignores noise below the threshold', () => {
    const px = new Uint16Array(32 * 32).fill(500);
    expect(detectStars(px, 32, 32, 500, 10).stars).toBe(0);
  });
});
