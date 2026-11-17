import { describe, expect, it } from 'vitest';
import { dragLevel, handleLevels, midtonesFraction, midtonesFromFraction, pickHandle } from './levels';
import { stretchValue, type StretchMode, type StretchParams } from './stretch';

const MODES: StretchMode[] = ['linear', 'log', 'asinh'];

describe('level handles on the histogram', () => {
  it('puts the midtones handle where the stretched value is one half', () => {
    for (const mode of MODES) {
      for (const midtones of [0.05, 0.2, 0.5, 0.8]) {
        const p: StretchParams = { black: 1900, white: 2300, midtones, mode };
        const { mid } = handleLevels(p);
        expect(mid).toBeGreaterThan(p.black);
        expect(mid).toBeLessThan(p.white);
        expect(stretchValue(mid, p)).toBeCloseTo(0.5, 6);
      }
    }
  });

  it('inverts the midtones position to 0.001', () => {
    for (const mode of MODES) {
      for (const m of [0.003, 0.25, 0.5, 0.731, 0.999]) {
        expect(midtonesFromFraction(midtonesFraction(m, mode), mode)).toBeCloseTo(m, 3);
      }
    }
  });

  it('snaps dragged levels to whole ADU and keeps black below white', () => {
    const p: StretchParams = { black: 1900, white: 2300, midtones: 0.25, mode: 'linear' };
    expect(dragLevel('black', 1950.4, p)).toEqual({ black: 1950 });
    expect(dragLevel('black', 2500, p)).toEqual({ black: 2299 });
    expect(dragLevel('white', 1000, p)).toEqual({ white: 1901 });
    expect(dragLevel('white', 70000, p)).toEqual({ white: 65535 });
    expect(dragLevel('mid', 2100, p)).toEqual({ midtones: 0.5 }); // half-way, linear
  });

  it('picks the nearest handle within the tolerance, ends first', () => {
    const at = { black: 100, mid: 140, white: 300 };
    expect(pickHandle(103, at)).toBe('black');
    expect(pickHandle(137, at)).toBe('mid');
    expect(pickHandle(120, at)).toBeNull();
    expect(pickHandle(100, { black: 100, mid: 100, white: 300 })).toBe('black');
  });
});
