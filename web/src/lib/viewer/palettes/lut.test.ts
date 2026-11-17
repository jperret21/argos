import { describe, expect, it } from 'vitest';
import {
  buildLut,
  effectivePalette,
  LUT_SIZE,
  oklabLightness,
  oklabToSrgb,
  paletteCode,
  paletteColour,
  paletteGradient,
  paletteReason,
  rampLightness,
  PALETTES,
} from './lut';

const entry = (lut: Uint8Array, i: number) => [lut[i * 4], lut[i * 4 + 1], lut[i * 4 + 2]] as const;

describe('OKLab conversions', () => {
  it('maps white and black exactly', () => {
    expect(oklabToSrgb(1, 0, 0).map((v) => Math.round(v * 255))).toEqual([255, 255, 255]);
    expect(oklabToSrgb(0, 0, 0).map((v) => Math.round(v * 255))).toEqual([0, 0, 0]);
  });

  it('oklabLightness inverts the lightness of oklabToSrgb for greys', () => {
    for (const L of [0.1, 0.3, 0.5, 0.8]) {
      const [r, g, b] = oklabToSrgb(L, 0, 0).map((v) => v * 255);
      expect(oklabLightness(r, g, b)).toBeCloseTo(L, 4);
    }
  });
});

describe('perceptual false-colour LUTs (Fire, Ice)', () => {
  for (const p of ['fire', 'ice'] as const) {
    it(`${p}: OKLab lightness is linear in the stretched value at every entry`, () => {
      const lut = buildLut(p);
      expect(entry(lut, 0)).toEqual([0, 0, 0]);
      for (let i = 1; i < LUT_SIZE; i++) {
        const [r, g, b] = entry(lut, i);
        // L0 + (1 − L0)·v: the ramp starts at the darkest 8-bit grey, so no entry is crushed.
        const err = Math.abs(oklabLightness(r, g, b) - rampLightness(i / 255));
        expect(r + g + b).toBeGreaterThan(0);
        // Rounding each channel to 8 bits moves L a little; less in the bright part.
        expect(err).toBeLessThan(i >= 16 ? 0.004 : 0.008);
      }
    });

    it(`${p}: no two entries are the same colour (the faint end is not crushed)`, () => {
      const lut = buildLut(p);
      const seen = new Set<string>();
      for (let i = 0; i < LUT_SIZE; i++) seen.add(entry(lut, i).join(','));
      expect(seen.size).toBe(LUT_SIZE);
    });

    it(`${p}: lightness rises monotonically (8-bit rounding allowed)`, () => {
      const lut = buildLut(p);
      let prev = -1;
      for (let i = 0; i < LUT_SIZE; i++) {
        const L = oklabLightness(...entry(lut, i));
        expect(L).toBeGreaterThanOrEqual(prev - 0.004);
        prev = L;
      }
    });

    it(`${p}: black at 0, white at 1, coloured in between`, () => {
      const lut = buildLut(p);
      expect(entry(lut, 0)).toEqual([0, 0, 0]);
      expect(entry(lut, 255)).toEqual([255, 255, 255]);
      const [r, g, b] = entry(lut, 128);
      expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeGreaterThan(30);
    });
  }

  it('fire is warm (red over blue) and ice cold (blue over red) mid-range', () => {
    const [fr, , fb] = paletteColour('fire', 0.5);
    const [ir, , ib] = paletteColour('ice', 0.5);
    expect(fr).toBeGreaterThan(fb);
    expect(ib).toBeGreaterThan(ir);
  });
});

describe('neutral and negative', () => {
  it('neutral is the identity grey, negative its inverse', () => {
    const n = buildLut('neutral');
    const g = buildLut('negative');
    for (const i of [0, 17, 128, 255]) {
      expect(entry(n, i)).toEqual([i, i, i]);
      expect(entry(g, i)).toEqual([255 - i, 255 - i, 255 - i]);
    }
  });

  it('every LUT is opaque and cached', () => {
    for (const p of PALETTES) {
      const lut = buildLut(p);
      expect(lut.length).toBe(LUT_SIZE * 4);
      for (let i = 0; i < LUT_SIZE; i++) expect(lut[i * 4 + 3]).toBe(255);
      expect(buildLut(p)).toBe(lut);
    }
  });

  it('shader codes: 0 = no lookup for neutral', () => {
    expect(paletteCode('neutral')).toBe(0);
    expect(paletteCode('negative')).toBeGreaterThan(0);
    expect(paletteCode('fire')).toBeGreaterThan(0);
  });

  it('a swatch gradient lists the stops', () => {
    expect(paletteGradient('fire', 3)).toMatch(/^linear-gradient\(90deg, rgb\(0 0 0\) 0%, .* rgb\(255 255 255\) 100%\)$/);
  });
});

describe('Night Red (D30): Neutral only', () => {
  it('refuses Negative, Fire and Ice with the reason', () => {
    expect(paletteReason('neutral', true)).toBeNull();
    for (const p of ['negative', 'fire', 'ice'] as const) {
      expect(paletteReason(p, true)).toBe('false colour is off in Night Red');
      expect(paletteReason(p, false)).toBeNull();
      expect(effectivePalette(p, true)).toBe('neutral');
      expect(effectivePalette(p, false)).toBe(p);
    }
  });
});
