import { describe, expect, it } from 'vitest';
import { curveSigma, fitHyperbola, hyperbola, judge, type Sample } from './fit';

function sweep(a: number, b: number, c: number, noise: (i: number) => number): Sample[] {
  const out: Sample[] = [];
  for (let i = 0; i < 9; i++) {
    const x = c - 280 + i * 70;
    const y = hyperbola(x, a, b, c);
    out.push({ x, y: y + noise(i), s: 0.04 * y + 0.05 });
  }
  return out;
}

describe('hyperbola fit', () => {
  it('recovers the parameters of noiseless samples', () => {
    const f = fitHyperbola(sweep(2.6, 95, 1287, () => 0));
    expect(f).not.toBeNull();
    expect(f!.a).toBeCloseTo(2.6, 4);
    expect(f!.b).toBeCloseTo(95, 2);
    expect(f!.c).toBeCloseTo(1287, 2);
    expect(f!.r2).toBeGreaterThan(0.9999);
  });

  it('gives a position uncertainty that grows with the noise', () => {
    const wobble = (i: number) => [0.08, -0.12, 0.05, -0.03, 0.1, -0.07, 0.02, 0.11, -0.09][i];
    const small = fitHyperbola(sweep(2.6, 95, 1287, (i) => wobble(i) * 0.5))!;
    const big = fitHyperbola(sweep(2.6, 95, 1287, (i) => wobble(i) * 4))!;
    expect(Math.abs(small.c - 1287)).toBeLessThan(10);
    expect(big.sigmaC).toBeGreaterThan(small.sigmaC);
    expect(curveSigma(small, small.c)).toBeGreaterThan(0);
    expect(judge(small, sweep(2.6, 95, 1287, () => 0), 70).accepted).toBe(true);
  });

  it('rejects a flat curve', () => {
    const flat = sweep(3.1, 3000, 1287, () => 0);
    const v = judge(fitHyperbola(flat), flat, 70);
    expect(v.accepted).toBe(false);
    expect(v.reason).toMatch(/^Flat HFD curve/);
  });
});
