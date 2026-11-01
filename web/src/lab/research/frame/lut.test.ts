import { describe, expect, it } from 'vitest';
import { buildLut, oklabToSrgb } from './gl';

/** OKLab lightness of an sRGB byte triple (inverse of oklabToSrgb's L). */
function okL(r: number, g: number, b: number): number {
  const lin = (c: number) => {
    const x = c / 255;
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  const [R, G, B] = [lin(r), lin(g), lin(b)];
  const l = Math.cbrt(0.4122214708 * R + 0.5363015239 * G + 0.0514459929 * B);
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  return 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
}

describe('perceptual LUTs', () => {
  it('maps white and black exactly', () => {
    expect(oklabToSrgb(1, 0, 0).map((v) => Math.round(v * 255))).toEqual([255, 255, 255]);
    expect(oklabToSrgb(0, 0, 0).map((v) => Math.round(v * 255))).toEqual([0, 0, 0]);
  });

  for (const p of ['fire', 'ice', 'neutral'] as const) {
    it(`${p}: lightness rises monotonically with the stretched value`, () => {
      const lut = buildLut(p);
      let prev = -1;
      for (let i = 0; i < 256; i++) {
        const L = okL(lut[i * 4], lut[i * 4 + 1], lut[i * 4 + 2]);
        expect(L).toBeGreaterThanOrEqual(prev - 0.004); // 8-bit rounding
        prev = L;
      }
      expect(okL(lut[0], lut[1], lut[2])).toBeLessThan(0.01);
      expect(okL(lut[1020], lut[1021], lut[1022])).toBeGreaterThan(0.99);
    });
  }
});
