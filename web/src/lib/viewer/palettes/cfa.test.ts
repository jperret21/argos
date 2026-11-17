import { describe, expect, it } from 'vitest';
import { autoStf, histogram16, median } from '../stretch';
import {
  balanced,
  cfaPlanes,
  cfaSites,
  colourHistogram,
  effectivePreview,
  frameKind,
  neutralGains,
  previewCode,
  previewStats,
  previewsFor,
  rgbPlanes,
} from './cfa';

/** A GRBG mosaic: G1 = 2000 + noise, R = 1500 + i, B = 1000 + j, G2 = G1 + 2 (row 0 at the top). */
function mosaic(w: number, h: number): Uint16Array {
  const px = new Uint16Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = x >> 1;
      const j = y >> 1;
      const site = (y % 2) * 2 + (x % 2); // 0 G1, 1 R, 2 B, 3 G2
      px[y * w + x] = site === 0 ? 2000 + ((i * 7 + j * 3) % 11) : site === 1 ? 1500 + i : site === 2 ? 1000 + j : 2002 + ((i * 7 + j * 3) % 11);
    }
  }
  return px;
}

/** debayer.split_cfa + extract_plane, written plainly (the numpy reference). */
function planesRef(px: Uint16Array, w: number, h: number) {
  const r: number[] = [];
  const g: number[] = [];
  const b: number[] = [];
  for (let y = 0; y + 1 < h; y += 2) {
    for (let x = 0; x + 1 < w; x += 2) {
      r.push(px[y * w + x + 1]);
      b.push(px[(y + 1) * w + x]);
      g.push((px[y * w + x] + px[(y + 1) * w + x + 1]) >> 1);
    }
  }
  return { r, g, b };
}

describe('CFA sites', () => {
  it('reads every Bayer pattern', () => {
    expect(cfaSites('GRBG')).toMatchObject({ r: [1, 0], g1: [0, 0], g2: [1, 1], b: [0, 1] });
    expect(cfaSites('rggb')).toMatchObject({ r: [0, 0], g1: [1, 0], g2: [0, 1], b: [1, 1] });
    expect(cfaSites('GBRG')).toMatchObject({ r: [0, 1], b: [1, 0] });
    expect(cfaSites('BGGR')).toMatchObject({ r: [1, 1], b: [0, 0] });
  });

  it('refuses what is not a Bayer pattern', () => {
    for (const p of [null, undefined, '', 'GRB', 'RRGB', 'GGGG', 'XYZW']) expect(cfaSites(p)).toBeNull();
  });
});

describe('previews offered and drawn', () => {
  it('mono frames have no preview row; RGB frames have no Raw', () => {
    expect(frameKind(1, null)).toBe('mono');
    expect(frameKind(1, 'GRBG')).toBe('cfa');
    expect(frameKind(3, null)).toBe('rgb');
    expect(previewsFor('mono')).toEqual([]);
    expect(previewsFor('cfa')).toEqual(['colour', 'raw', 'r', 'g', 'b']);
    expect(previewsFor('rgb')).toEqual(['colour', 'r', 'g', 'b']);
    expect(effectivePreview('colour', 'mono')).toBe('raw');
    expect(effectivePreview('raw', 'rgb')).toBe('colour');
  });

  it('shader codes', () => {
    expect(previewCode('raw', 'cfa')).toBe(0);
    expect(previewCode('colour', 'cfa')).toBe(1);
    expect(previewCode('colour', 'rgb')).toBe(0);
    expect(previewCode('colour', 'mono')).toBe(0);
    expect([previewCode('r', 'cfa'), previewCode('g', 'cfa'), previewCode('b', 'cfa')]).toEqual([2, 3, 4]);
    expect(previewCode('g', 'rgb')).toBe(3);
  });
});

describe('CFA planes', () => {
  it('match split_cfa / extract_plane on real samples, odd sizes cropped', () => {
    const w = 11;
    const h = 9;
    const px = mosaic(w, h);
    const p = cfaPlanes(px, w, h, cfaSites('GRBG')!);
    const ref = planesRef(px, w, h);
    expect(p.cells).toBe(5 * 4);
    expect(p.r.n).toBe(ref.r.length);
    for (const [plane, values] of [
      [p.r, ref.r],
      [p.g, ref.g],
      [p.b, ref.b],
    ] as const) {
      const h16 = histogram16(values);
      expect(Array.from(plane.counts)).toEqual(Array.from(h16.counts));
      expect(plane.min).toBe(h16.min);
      expect(plane.max).toBe(h16.max);
    }
  });

  it('per-channel planes of an RGB frame', () => {
    const px = new Uint16Array([1, 2, 3, 4, 5, 6]);
    const p = rgbPlanes(px);
    expect([median(p.r), median(p.g), median(p.b)]).toEqual([2.5, 3.5, 4.5]);
  });
});

describe('display balance (neutralise_rgb_for_display)', () => {
  it('brings each sky to the median of the skies, gains clipped to 0.25-4', () => {
    expect(neutralGains([1500, 2000, 1000])).toEqual([1, 0.75, 1.5]);
    expect(neutralGains([100, 2000, 1000])).toEqual([4, 0.5, 1]);
    // Two valid channels: numpy's median of two is their mean.
    expect(neutralGains([0, 2000, 1000])).toEqual([1, 0.75, 1.5]);
    expect(neutralGains([0, 0, 0])).toEqual([1, 1, 1]);
  });

  it('floors float32 products into uint16 like astype(uint16)', () => {
    expect(balanced(1000, 1.5)).toBe(1500);
    expect(balanced(65535, 2)).toBe(65535);
    expect(balanced(3, 0.75)).toBe(2);
  });

  it('the colour view histogram counts every balanced channel value', () => {
    const w = 8;
    const h = 8;
    const px = mosaic(w, h);
    const p = cfaPlanes(px, w, h, cfaSites('GRBG')!);
    const gains = neutralGains([median(p.r), median(p.g), median(p.b)]);
    const ref = planesRef(px, w, h);
    const values = [...ref.r.map((v) => balanced(v, gains[0])), ...ref.g.map((v) => balanced(v, gains[1])), ...ref.b.map((v) => balanced(v, gains[2]))];
    const h16 = histogram16(values);
    const c = colourHistogram(p, gains);
    expect(c.n).toBe(values.length);
    expect(Array.from(c.counts)).toEqual(Array.from(h16.counts));
  });
});

describe('preview statistics (the auto levels follow the view, as Qt)', () => {
  const w = 16;
  const h = 16;
  const px = mosaic(w, h);
  const planes = cfaPlanes(px, w, h, cfaSites('GRBG')!);

  it('Raw uses the raw histogram (no view histogram)', () => {
    const s = previewStats('raw', 'cfa', planes);
    expect(s.view).toBeNull();
    expect(s.gains).toEqual([1, 1, 1]);
  });

  it('a plane view uses that plane', () => {
    expect(previewStats('r', 'cfa', planes).view).toBe(planes.r);
    expect(previewStats('b', 'cfa', planes).view).toBe(planes.b);
  });

  it('Colour balances the skies, so its auto black point sits under every sky', () => {
    const s = previewStats('colour', 'cfa', planes);
    expect(s.code).toBe(1);
    const auto = autoStf(s.view!);
    const skies = [median(planes.r) * s.gains[0], median(planes.g) * s.gains[1], median(planes.b) * s.gains[2]];
    for (const sky of skies) expect(auto.black).toBeLessThanOrEqual(sky + 1e-9);
  });

  it('mono frames: no planes, nothing to compute', () => {
    expect(previewStats('colour', 'mono', null)).toMatchObject({ code: 0, view: null });
  });
});
