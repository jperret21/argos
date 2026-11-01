import { describe, expect, it } from 'vitest';
import { FAST_CADENCE, FOCUS_LOSS, hfdEpisodes, REAL_CADENCE, schedule, synthesizeNight, targetTrueMag } from './night';

describe('synthetic night', () => {
  const times = schedule(REAL_CADENCE);
  const night = synthesizeNight(times);

  it('has the owner-like cadence (median ~51.5 s) and about 500 frames', () => {
    const d: number[] = [];
    for (let i = 1; i < times.length; i++) d.push(times[i] - times[i - 1]);
    d.sort((a, b) => a - b);
    expect(d[d.length >> 1]).toBeGreaterThan(50);
    expect(d[d.length >> 1]).toBeLessThan(53);
    expect(times.length).toBeGreaterThan(450);
    expect(times.length).toBeLessThan(560);
  });

  it('is deterministic', () => {
    const again = synthesizeNight(schedule(REAL_CADENCE));
    expect(again.target[123]).toBe(night.target[123]);
    expect(again.hfd[400]).toBe(night.hfd[400]);
  });

  it('reaches maximum light (V 9.31) near 21:54 UTC (BJD epoch 22:02 minus 8 min light time)', () => {
    const t0 = Date.UTC(2026, 10, 1, 21, 0) / 1000;
    let best = t0;
    for (let t = t0; t < t0 + 7200; t += 30) if (targetTrueMag(t) < targetTrueMag(best)) best = t;
    expect(targetTrueMag(best)).toBeLessThan(9.315);
    expect(Math.abs(best - Date.UTC(2026, 10, 1, 21, 54) / 1000)).toBeLessThan(5 * 60);
  });

  it('fires the HFD rule once, shortly after the focus loss, and clears after the autofocus', () => {
    const ep = hfdEpisodes(night, night.n, 1.5);
    expect(ep).toHaveLength(1);
    expect(night.t[ep[0].fired] - FOCUS_LOSS).toBeLessThan(4 * 60);
    expect(ep[0].end).not.toBeNull();
  });

  it('the stress run has more than 5 000 frames', () => {
    expect(schedule(FAST_CADENCE).length).toBeGreaterThan(5000);
  });
});
