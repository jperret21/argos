import { describe, expect, it } from 'vitest';
import { exposure, fixed, GROUP, grouped, MINUS, parseNumber, signed, signedGrouped } from './format';
import { deadmanExpired, directionOfKey, JogHolds } from './jog';
import { fitToolbar, type FitItem } from './overflow';
import {
  applyDetent,
  dragValue,
  EXPOSURE_LADDER,
  ladderStep,
  nearestRung,
  repeatFactor,
  repeatsBy,
  roundTo,
  scrubValue,
  stepValue,
  ticks,
} from './values';

describe('format', () => {
  it('uses the true minus and never prints -0', () => {
    expect(fixed(-1.25, 2)).toBe(`${MINUS}1.25`);
    expect(fixed(-0.0001, 2)).toBe('0.00');
    expect(signed(0.83, 2)).toBe('+0.83');
    expect(signed(-0.12, 2)).toBe(`${MINUS}0.12`);
  });
  it('groups thousands', () => {
    expect(grouped(12450)).toBe(`12${GROUP}450`);
    expect(grouped(100000)).toBe(`100${GROUP}000`);
    expect(grouped(-1250)).toBe(`${MINUS}1${GROUP}250`);
    expect(signedGrouped(300)).toBe('+300');
  });
  it('gives exposures the precision their size needs', () => {
    expect(exposure(0.02)).toBe('0.020');
    expect(exposure(0.5)).toBe('0.50');
    expect(exposure(2)).toBe('2.0');
    expect(exposure(120)).toBe('120');
  });
  it('parses what an observer types', () => {
    expect(parseNumber('0,5')).toBe(0.5);
    expect(parseNumber('12,450')).toBe(12450);
    expect(parseNumber(`${MINUS}3.5`)).toBe(-3.5);
    expect(parseNumber('12 450')).toBe(12450);
    expect(parseNumber('abc')).toBeNull();
  });
});

describe('values', () => {
  it('rounds without float dust', () => {
    expect(roundTo(0.1 + 0.2, 0.1)).toBe(0.3);
    expect(roundTo(8.73, 0.1, 8)).toBe(8.7);
  });
  it('steps with Shift x10 and Alt x0.1, clamped', () => {
    expect(stepValue(80, 1, 1, 'normal', 0, 600)).toBe(81);
    expect(stepValue(80, 1, 1, 'coarse', 0, 600)).toBe(90);
    expect(stepValue(12.3, -1, 0.1, 'fine', 8, 18)).toBe(12.29);
    expect(stepValue(599, 1, 1, 'coarse', 0, 600)).toBe(600);
  });
  it('walks the exposure ladder from any value', () => {
    expect(ladderStep(EXPOSURE_LADDER, 2, 1)).toBe(3);
    expect(ladderStep(EXPOSURE_LADDER, 2.5, 1)).toBe(3);
    expect(ladderStep(EXPOSURE_LADDER, 2.5, -1)).toBe(2);
    expect(ladderStep(EXPOSURE_LADDER, 600, 1)).toBe(600);
    expect(ladderStep(EXPOSURE_LADDER, 1, 1, 3)).toBe(5);
    expect(EXPOSURE_LADDER[nearestRung(EXPOSURE_LADDER, 1.4)]).toBe(1);
  });
  it('scrubs one rung per 12 px, linear fine steps with Alt', () => {
    const base = { start: 2, step: 0.01, min: 0.01, max: 600, ladder: EXPOSURE_LADDER };
    expect(scrubValue({ ...base, dx: 11, precision: 'normal' })).toBe(2);
    expect(scrubValue({ ...base, dx: 24, precision: 'normal' })).toBe(5);
    expect(scrubValue({ ...base, dx: -12, precision: 'normal' })).toBe(1);
    expect(scrubValue({ ...base, dx: 40, precision: 'fine', pxPerStep: 4 })).toBe(2.01);
    expect(scrubValue({ start: 80, dx: 20, step: 1, min: 0, max: 600, precision: 'coarse', pxPerStep: 4 })).toBe(130);
  });
  it('drags absolute, snaps with Shift, slows tenfold with Alt', () => {
    const base = { width: 400, min: 8, max: 18, step: 0.1 };
    expect(dragValue({ ...base, x: 200, precision: 'normal' })).toBe(13);
    expect(dragValue({ ...base, x: 213, precision: 'coarse', snap: 0.5 })).toBe(13.5);
    // 40 px at 10/400 per px = 1.0, fine -> 0.1
    expect(dragValue({ ...base, x: 240, precision: 'fine', fineFrom: { x: 200, value: 13 } })).toBe(13.1);
  });
  it('builds minor and major ticks', () => {
    const t = ticks(8, 18, 0.5, 2);
    expect(t[0]).toEqual({ value: 8, major: true });
    expect(t.length).toBe(21);
    expect(t.filter((x) => x.major).map((x) => x.value)).toEqual([8, 10, 12, 14, 16, 18]);
  });
  it('snaps to a detent only inside its radius', () => {
    expect(applyDetent(8.6, [8.7], 0.2)).toBe(8.7);
    expect(applyDetent(9.2, [8.7], 0.2)).toBe(9.2);
  });
  it('repeats after the delay, then accelerates', () => {
    expect(repeatsBy(399)).toBe(0);
    expect(repeatsBy(400)).toBe(1);
    expect(repeatsBy(400 + 80 * 5)).toBe(6);
    expect(repeatFactor(500)).toBe(1);
    expect(repeatFactor(400 + 1600)).toBe(10);
  });
});

describe('toolbar overflow', () => {
  const items: FitItem[] = [
    { id: 'capture', group: 'cam', width: 34, priority: Infinity },
    { id: 'live', group: 'cam', width: 34, priority: Infinity },
    { id: 'zoom-out', group: 'zoom', width: 34, priority: 5 },
    { id: 'zoom', group: 'zoom', width: 48, priority: 6 },
    { id: 'zoom-in', group: 'zoom', width: 34, priority: 5 },
    { id: 'grid', group: 'over', width: 34, priority: 1 },
    { id: 'labels', group: 'over', width: 34, priority: 1 },
  ];
  const o = { gap: 2, separator: 17, overflow: 46 };

  it('keeps everything when it fits', () => {
    const r = fitToolbar(items, { ...o, available: 1000 });
    expect(r.hidden).toEqual([]);
  });
  it('hides the lowest priority first, rightmost first, and drops empty groups', () => {
    const full = fitToolbar(items, { ...o, available: 1000 }).width;
    const r = fitToolbar(items, { ...o, available: full - 1 });
    expect(r.hidden).toEqual(['grid', 'labels']); // menu keeps the toolbar's order
    expect(r.width).toBeLessThanOrEqual(full - 1);
  });
  it('never hides run-critical tools', () => {
    const r = fitToolbar(items, { ...o, available: 10 });
    expect(r.visible.has('capture') && r.visible.has('live')).toBe(true);
    expect(r.hidden).toEqual(['zoom-out', 'zoom', 'zoom-in', 'grid', 'labels']);
  });
});

describe('jog', () => {
  it('tracks the two axes separately', () => {
    const j = new JogHolds();
    j.press('key:ArrowUp', 'north');
    j.press('key:ArrowRight', 'east');
    expect([j.sign('secondary'), j.sign('primary')]).toEqual([1, 1]);
    j.release('key:ArrowUp');
    expect([j.sign('secondary'), j.sign('primary')]).toEqual([0, 1]);
  });
  it('lets the newest press win on one axis and falls back on release', () => {
    const j = new JogHolds();
    j.press('key:ArrowUp', 'north');
    j.press('pointer:south', 'south');
    expect(j.sign('secondary')).toBe(-1);
    j.release('pointer:south');
    expect(j.sign('secondary')).toBe(1);
    expect(j.active('secondary')).toBe('north');
  });
  it('maps arrow keys and expires the dead-man after 1 s', () => {
    expect(directionOfKey('ArrowLeft')).toBe('west');
    expect(directionOfKey('KeyA')).toBeNull();
    expect(deadmanExpired(0, 1000)).toBe(false);
    expect(deadmanExpired(0, 1001)).toBe(true);
  });
});
