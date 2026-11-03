import { describe, expect, it } from 'vitest';
import {
  applyDetent,
  clamp,
  decimalsOf,
  dragValue,
  EXPOSURE_LADDER,
  ladderStep,
  nearestRung,
  precisionOf,
  ratioOf,
  repeatFactor,
  repeatsBy,
  ringFraction,
  roundTo,
  scrubValue,
  stepFor,
  stepValue,
  ticks,
  valueAt,
} from './values';

describe('modifiers and steps (BRAND 8)', () => {
  it('maps plain / Shift / Alt to one step, x10, x0.1', () => {
    expect(precisionOf({ shiftKey: false, altKey: false })).toBe('normal');
    expect(precisionOf({ shiftKey: true, altKey: false })).toBe('coarse');
    expect(precisionOf({ shiftKey: false, altKey: true })).toBe('fine');
    // Alt wins: fine adjustment is the deliberate gesture.
    expect(precisionOf({ shiftKey: true, altKey: true })).toBe('fine');
  });

  it('never gives an integer quantity a fractional step', () => {
    expect(stepFor(1, 'fine', true)).toBe(1);
    expect(stepFor(10, 'fine', true)).toBe(1);
    expect(stepFor(1, 'coarse', true)).toBe(10);
    expect(stepFor(0.5, 'fine')).toBeCloseTo(0.05, 12);
  });

  it('steps without float dust and stops at the limits', () => {
    expect(stepValue(0.1, 1, 0.1, 'normal', 0, 10)).toBe(0.2);
    expect(stepValue(0.3, 1, 0.1, 'normal', 0, 10)).toBe(0.4);
    expect(stepValue(9.95, 1, 0.1, 'normal', 0, 10)).toBe(10);
    expect(stepValue(0.05, -1, 0.1, 'normal', 0, 10)).toBe(0);
    expect(stepValue(80, 1, 1, 'coarse', 0, 600)).toBe(90);
    expect(stepValue(599, 1, 1, 'coarse', 0, 600)).toBe(600);
    expect(stepValue(12.3, -1, 0.1, 'fine', 8, 18)).toBe(12.29);
    // Between grid lines: the neighbouring line, never past it.
    expect(stepValue(85, 1, 1, 'coarse', 0, 600)).toBe(90);
    expect(stepValue(85, -1, 1, 'coarse', 0, 600)).toBe(80);
    expect(stepValue(5, -1, 1, 'fine', 0, 100)).toBe(4.9);
  });

  it('rounds to a step from an origin', () => {
    expect(roundTo(0.30000000000000004, 0.1)).toBe(0.3);
    expect(roundTo(7, 5, 1)).toBe(6);
    expect(decimalsOf(0.25)).toBe(2);
    expect(decimalsOf(1e-5)).toBe(5);
    expect(decimalsOf(5)).toBe(0);
    expect(clamp(12, 0, 10)).toBe(10);
  });
});

describe('exposure ladder', () => {
  it('goes to the next rung, from between rungs too', () => {
    expect(ladderStep(EXPOSURE_LADDER, 1, 1)).toBe(2);
    expect(ladderStep(EXPOSURE_LADDER, 1.4, 1)).toBe(2);
    expect(ladderStep(EXPOSURE_LADDER, 1.4, -1)).toBe(1);
    expect(ladderStep(EXPOSURE_LADDER, 600, 1)).toBe(600);
    expect(ladderStep(EXPOSURE_LADDER, 1, 1, 3)).toBe(5);
  });

  it('finds the nearest rung on a log scale', () => {
    expect(EXPOSURE_LADDER[nearestRung(EXPOSURE_LADDER, 1.4)]).toBe(1);
    expect(EXPOSURE_LADDER[nearestRung(EXPOSURE_LADDER, 1.5)]).toBe(2);
  });
});

describe('scrub, slider, detents', () => {
  it('scrubs one step per 4 px, x10 with Shift, ladders by 12 px', () => {
    expect(scrubValue({ start: 10, dx: 8, step: 1, min: 0, max: 100, precision: 'normal' })).toBe(12);
    expect(scrubValue({ start: 10, dx: 8, step: 1, min: 0, max: 100, precision: 'coarse' })).toBe(30);
    expect(scrubValue({ start: 10, dx: -400, step: 1, min: 0, max: 100, precision: 'normal' })).toBe(0);
    expect(
      scrubValue({ start: 1, dx: 25, step: 0.1, min: 0.01, max: 600, precision: 'normal', ladder: EXPOSURE_LADDER }),
    ).toBe(3);
  });

  it('places the thumb under the pointer, snaps with Shift, slows with Alt', () => {
    expect(dragValue({ x: 50, width: 100, min: 0, max: 10, step: 0.1, precision: 'normal' })).toBe(5);
    expect(dragValue({ x: 53, width: 100, min: 0, max: 10, step: 0.1, precision: 'coarse', snap: 1 })).toBe(5);
    expect(
      dragValue({ x: 60, width: 100, min: 0, max: 10, step: 0.1, precision: 'fine', fineFrom: { x: 50, value: 5 } }),
    ).toBe(5.1);
    expect(ratioOf(5, 0, 10)).toBe(0.5);
    expect(valueAt(2, 0, 10)).toBe(10);
  });

  it('catches the value on a detent', () => {
    expect(applyDetent(7.4, [7.25], 0.2)).toBe(7.25);
    expect(applyDetent(7.6, [7.25], 0.2)).toBe(7.6);
  });

  it('marks major ticks on multiples', () => {
    const t = ticks(0, 10, 1, 5);
    expect(t).toHaveLength(11);
    expect(t.filter((x) => x.major).map((x) => x.value)).toEqual([0, 5, 10]);
    expect(ticks(0, 10, 0, 5)).toEqual([]);
  });
});

describe('auto-repeat and time ring', () => {
  it('repeats after 400 ms every 80 ms, x10 after 1.6 s of repeating', () => {
    expect(repeatsBy(399)).toBe(0);
    expect(repeatsBy(400)).toBe(1);
    expect(repeatsBy(560)).toBe(3);
    expect(repeatFactor(1999)).toBe(1);
    expect(repeatFactor(2000)).toBe(10);
  });

  it('draws the exact fraction, quarters under reduced motion', () => {
    expect(ringFraction(0.37)).toBe(0.37);
    expect(ringFraction(0.37, true)).toBe(0.25);
    expect(ringFraction(1, true)).toBe(1);
    expect(ringFraction(1.4)).toBe(1);
    expect(ringFraction(null)).toBeNull();
    expect(ringFraction(Number.NaN)).toBeNull();
  });
});
