import { describe, expect, it } from 'vitest';
import { JD_UNIX_EPOCH, jdLabels, jdSplits, jdStep, stepDigits, utcSplits } from './axes';
import { FLAG_SATURATED, FLAG_SUSPECT, addShape, planMarkers } from './markers';
import { TimeZoom } from './zoom';

const DAY = 86400;
const unix = (jd: number) => (jd - JD_UNIX_EPOCH) * DAY;

describe('time axes (unix seconds on the scale; UTC, JD, BJD ticks)', () => {
  it('puts JD ticks on round fractions of a day, labelled from jd0 with the decimals of the step', () => {
    const a = unix(2461282.4012);
    const b = unix(2461282.6977); // about 7 h
    const s = jdSplits(a, b, 900);
    const step = jdStep(b - a, 900);
    expect(step).toBe(0.05);
    expect(stepDigits(step)).toBe(2);
    const labels = jdLabels(s, b - a, 900, 2461282);
    expect(labels).toEqual(['0.45', '0.50', '0.55', '0.60', '0.65']);
    for (const t of s) {
      const jd = t / DAY + JD_UNIX_EPOCH;
      expect(Math.abs(jd / step - Math.round(jd / step))).toBeLessThan(1e-6);
    }
  });

  it('shifts BJD ticks by the BJD − JD offset so the labels stay round', () => {
    const a = unix(2461282.4);
    const b = unix(2461282.5);
    const off = 312.4; // s
    const s = jdSplits(a, b, 600, off);
    const labels = jdLabels(s, b - a, 600, 2461282, off);
    expect(labels[0]).toMatch(/^0\.4\d+$/);
    // The tick labelled x sits where JD + offset = x.
    const bjd = (s[0] + off) / DAY + JD_UNIX_EPOCH - 2461282;
    expect(bjd).toBeCloseTo(Number(labels[0]), 9);
    expect(s[0]).toBeGreaterThanOrEqual(a);
  });

  it('chooses decimals that print every multiple of the step exactly', () => {
    expect(stepDigits(0.0001)).toBe(4);
    expect(stepDigits(0.0005)).toBe(4);
    expect(stepDigits(0.002)).toBe(3);
    expect(stepDigits(0.5)).toBe(1);
    expect(stepDigits(1)).toBe(0);
    expect(jdSplits(10, 5, 400)).toEqual([]);
    expect(utcSplits(0, 3600, 400).length).toBeGreaterThan(2);
  });
});

describe('markers: flags by shape, one path per kind, no closePath', () => {
  it('sorts points into solid, hollow (suspect) and cross (saturated wins), bars where longer than the marker', () => {
    const ys = [1, 2, NaN, 4, 5];
    const flags = [0, FLAG_SUSPECT, 0, FLAG_SATURATED | FLAG_SUSPECT, 0];
    const errs = [0.1, 0.01, 0.1, 0.1, 0];
    const p = planMarkers(ys, 0, 4, flags, errs, 0.05);
    expect(p.solid).toEqual([0, 4]);
    expect(p.hollow).toEqual([1]);
    expect(p.cross).toEqual([3]);
    expect(p.bars).toEqual([0, 3]);
  });

  it('never closes a shared path (Chromium is quadratic in the path size with closePath)', () => {
    const calls: string[] = [];
    const rec = new Proxy({}, { get: (_t, k) => (...a: unknown[]) => calls.push(`${String(k)}(${a.length})`) }) as Path2D;
    for (const s of ['circle', 'square', 'triangle'] as const) addShape(rec, s, 10, 10, 4);
    expect(calls.some((c) => c.startsWith('closePath'))).toBe(false);
    expect(calls.filter((c) => c.startsWith('moveTo')).length).toBe(2); // circle and triangle start a subpath; rect does itself
  });
});

describe('time zoom: Whole run, Following, Zoom kept', () => {
  function zoomOf(ext: { v: [number, number] | null }, anchor: 'center' | 'right' = 'right') {
    return new TimeZoom({ extent: () => ext.v, minSpan: 300, padLeft: 0, padRight: 0, reducedMotion: () => true, anchor: () => anchor });
  }

  it('fits the run and widens with new data', () => {
    const ext = { v: [0, 3600] as [number, number] };
    const z = zoomOf(ext);
    expect(z.update()).toEqual([0, 3600]);
    ext.v = [0, 4000];
    expect(z.update()).toEqual([0, 4000]);
    expect(z.mode).toBe('fit');
  });

  it('anchors a short live run on the right edge (now), an archived one in the middle', () => {
    expect(zoomOf({ v: [1000, 1060] }).fitView()).toEqual([760, 1060]);
    expect(zoomOf({ v: [1000, 1060] }, 'center').fitView()).toEqual([880, 1180]);
  });

  it('keeps a zoom on the past while frames arrive, and follows one that touches the end', () => {
    const ext = { v: [0, 3600] as [number, number] };
    const z = zoomOf(ext);
    z.update();
    z.setUser(600, 1200);
    expect(z.mode).toBe('manual');
    ext.v = [0, 7200];
    expect(z.update()).toEqual([600, 1200]); // new data never moves a kept zoom
    z.setUser(6000, 7200);
    expect(z.mode).toBe('follow');
    ext.v = [0, 8000];
    expect(z.update()).toEqual([6800, 8000]); // the window slides with the newest frame
    z.fit();
    expect(z.mode).toBe('fit');
    expect(z.view).toEqual([0, 8000]);
  });

  it('follows with a third of the run from the whole view, and clamps a pan inside the data', () => {
    const ext = { v: [0, 9000] as [number, number] };
    const z = zoomOf(ext);
    z.update();
    z.follow();
    expect(z.mode).toBe('follow');
    expect(z.view).toEqual([6000, 9000]);
    z.panBy(-10);
    expect(z.view).toEqual([0, 3000]);
    expect(z.mode).toBe('manual');
    z.zoomBy(100);
    expect(z.mode).toBe('fit'); // zooming out past the run is the whole run
    z.reset();
    expect(z.view).toBeNull();
  });
});
