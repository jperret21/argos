import { describe, expect, it } from 'vitest';
import { fitBands, STRIP, stripLayout } from './layout';

// The rotated Seestar frame and the Observe screen's centre column (nav rail
// 92 px, right rail 420 px, toolbar 47 px, status bar 32 px).
const frame = { width: 1920, height: 1080 };
const centre = (w: number, h: number, rail = true) => ({
  width: w - 92 - (rail ? 420 : 0),
  height: h - 47 - 32,
});

describe('levels strip height', () => {
  it('takes the whole dead band at the reference sizes (rail open)', () => {
    for (const [w, h, maxBand] of [
      [1440, 900, 1],
      [1280, 800, 1],
      [1600, 1000, 5],
    ] as const) {
      const c = centre(w, h);
      const s = stripLayout(c, frame, 0, true);
      expect(s.compact).toBe(false);
      const stage = { width: c.width, height: c.height - s.height };
      expect(fitBands(stage, frame).y).toBeLessThanOrEqual(maxBand);
      expect(fitBands(stage, frame).x).toBe(0);
    }
  });

  it('is 299 px at 1440x900, where the bands were 150 px', () => {
    const c = centre(1440, 900);
    expect(fitBands(c, frame).y).toBeCloseTo(149.5, 1);
    expect(stripLayout(c, frame, 0, true)).toEqual({ height: 299, compact: false });
  });

  it('folds to one compact row, still as tall as the band, when it is narrow (rail closed)', () => {
    const c = centre(1440, 900, false);
    const s = stripLayout(c, frame, 0, true);
    expect(s.compact).toBe(true);
    expect(s.height).toBe(62); // floor(821 - 1348 * 9 / 16 = 62.75): the image never shrinks
    expect(fitBands({ width: c.width, height: c.height - s.height }, frame).y).toBeLessThan(1);
    // A square frame leaves no band: the compact row keeps its minimum height.
    expect(stripLayout(c, { width: 1000, height: 1000 }, 0, true)).toEqual({
      height: STRIP.compact,
      compact: true,
    });
  });

  it('leaves room for the log drawer, and is absent when closed', () => {
    const c = centre(1440, 900);
    expect(stripLayout(c, frame, 216, true).compact).toBe(true);
    expect(stripLayout(c, frame, 0, false)).toEqual({ height: 0, compact: false });
  });
});
