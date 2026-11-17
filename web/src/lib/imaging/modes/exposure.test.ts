import { describe, expect, it } from 'vitest';
import { exposureCheck, frac, peakState, profileLimits } from './exposure';

const peaks = (seq: number, values: number[]) => ({
  seq,
  result: { stars: values.map((peak, i) => ({ peak, x: i, y: i })), sky: 1800, sigma: 25, maxima: values.length },
});
const clip = { topCode: 65520, step: 16, clipped: 42, aboveLevel: null, fraction: 42 / 2073600 };

describe('exposure check (Framing band)', () => {
  it('draws true-length bars to 65 535 and words each star (never an OK badge)', () => {
    const c = exposureCheck({ seq: 7, peaks: peaks(7, [65520, 52000, 30000]), clip, metrics: null, linearity: 50000, fullWell: 60000 });
    expect(c.current).toBe(true);
    expect(c.rows.map((r) => r.state)).toEqual(['clipped', 'nonlinear', 'ok']);
    expect(c.rows[2].frac).toBeCloseTo(30000 / 65535, 9);
    expect(c.linearity).toBeCloseTo(50000 / 65535, 9);
    expect(c.fullWell).toBeCloseTo(60000 / 65535, 9);
    expect(c.starsClipped).toBe(1);
    expect(c.starsNonLinear).toBe(2);
    expect(c.clipped).toBe(42);
    expect(c.sky).toBe(1800);
  });

  it('shows the previous frame’s numbers, marked, while this one is measured; never a later or an old frame', () => {
    const c = exposureCheck({ seq: 8, peaks: peaks(7, [40000]), clip, metrics: { seq: 7, hfd_px: 2.5, sky_adu: 1700 } });
    expect(c.current).toBe(false);
    expect(c.peaksSeq).toBe(7);
    expect(c.rows).toHaveLength(1);
    expect(c.metricsCurrent).toBe(false);
    expect(c.metrics?.seq).toBe(7);
    // Too old, or from the future (a restarted server numbers from 1 again): nothing.
    const old = exposureCheck({ seq: 20, peaks: peaks(7, [40000]), clip, metrics: { seq: 7, hfd_px: 2.5 } });
    expect(old.rows).toEqual([]);
    expect(old.metrics).toBeNull();
    expect(old.sky).toBeNull();
    const future = exposureCheck({ seq: 3, peaks: peaks(7, [40000]), clip, metrics: { seq: 7, hfd_px: 2.5 } });
    expect(future.rows).toEqual([]);
    expect(future.metrics).toBeNull();
    const ok = exposureCheck({ seq: 7, peaks: peaks(7, [40000]), clip, metrics: { seq: 7, hfd_px: 2.5, sky_adu: 1700 } });
    expect(ok.metrics?.hfd_px).toBe(2.5);
    expect(ok.sky).toBe(1700); // the server's sky of record wins over the worker's
  });

  it('keeps the last peaks, with their lag, while the worker catches up (no blank list)', () => {
    const c = exposureCheck({ seq: 12, peaks: peaks(7, [40000]), clip, metrics: null });
    expect(c.rows).toHaveLength(1);
    expect(c.lag).toBe(5);
    expect(c.current).toBe(false);
    expect(exposureCheck({ seq: 7, peaks: peaks(7, [40000]), clip, metrics: null }).lag).toBe(0);
  });

  it('collapses two or more clipped stars into one line and keeps the unclipped ones', () => {
    const c = exposureCheck({ seq: 7, peaks: peaks(7, [65520, 65520, 65520, 41000, 30000]), clip, metrics: null, linearity: 50000, rows: 4 });
    expect(c.clippedGroup).toBe(3);
    expect(c.rows.map((r) => r.peak)).toEqual([41000, 30000]);
    expect(c.capacity).toBe(4);
    const one = exposureCheck({ seq: 7, peaks: peaks(7, [65520, 41000]), clip, metrics: null, linearity: 50000 });
    expect(one.clippedGroup).toBe(0);
    expect(one.rows[0].state).toBe('clipped');
  });

  it('keeps an unknown peak empty and reads the profile limits with overrides', () => {
    expect(frac(NaN)).toBe(0);
    expect(frac(70000)).toBe(1);
    expect(peakState(100, null, null)).toBe('ok');
    expect(profileLimits({ full_well_adu: 60000, linearity_max_adu: 50000, overrides: { linearity_max_adu: 48000 } })).toEqual({
      linearity: 48000,
      fullWell: 60000,
    });
    expect(profileLimits(null)).toEqual({ linearity: null, fullWell: null });
  });
});
