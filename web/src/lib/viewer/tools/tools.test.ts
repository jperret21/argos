import { describe, expect, it } from 'vitest';
import { cfaSites } from '../palettes/cfa';
import { overlayMatrix, type Turns } from '../rotation';
import {
  centredRect,
  clampRect,
  frameRectToScreen,
  frameToScreen,
  frameVectorToScreen,
  isFrameRect,
  moveRect,
  pixelAt,
  screenRectToFrame,
  screenToFrame,
  type ViewerGeometry,
} from './geometry';
import { regionStats } from './region';

const geom = (turns: Turns, frame = { width: 6, height: 4 }): ViewerGeometry => ({
  view: { scale: 10, tx: 5, ty: 7 },
  frame,
  turns,
  viewport: { width: 200, height: 200 },
  dpr: 1,
});

/** Apply the SVG overlay matrix (what the overlay snippet draws through), then the view. */
function viaOverlay(g: ViewerGeometry, x: number, y: number) {
  const m = overlayMatrix(g.frame.width, g.frame.height, g.turns).match(/-?\d+(\.\d+)?/g)!.map(Number);
  const [a, b, c, d, e, f] = m;
  const u = a * x + c * y + e;
  const v = b * x + d * y + f;
  return { x: g.view.tx + 0.5 * g.view.scale + u * g.view.scale, y: g.view.ty + 0.5 * g.view.scale + v * g.view.scale };
}

describe('viewer geometry', () => {
  for (const k of [0, 1, 2, 3] as Turns[]) {
    it(`frameToScreen agrees with the overlay transform (turns ${k}) and inverts`, () => {
      const g = geom(k);
      for (const [x, y] of [
        [0, 0],
        [5, 3],
        [2.3, 1.7],
      ]) {
        const s = frameToScreen(g, x, y);
        const o = viaOverlay(g, x, y);
        expect(s.x).toBeCloseTo(o.x, 9);
        expect(s.y).toBeCloseTo(o.y, 9);
        const back = screenToFrame(g, s.x, s.y);
        expect(back.x).toBeCloseTo(x, 9);
        expect(back.y).toBeCloseTo(y, 9);
      }
    });

    it(`a frame rectangle maps to the box of its pixels and back (turns ${k})`, () => {
      const g = geom(k);
      const r = { x0: 1, y0: 1, x1: 4, y1: 3 };
      const s = frameRectToScreen(g, r);
      expect(s.width * s.height).toBeCloseTo(3 * 2 * 100, 6);
      expect(screenRectToFrame(g, s)).toEqual(r);
    });

    it(`directions turn with the display (turns ${k})`, () => {
      // +x of the frame, through the overlay transform.
      const g = geom(k);
      const a = viaOverlay(g, 1, 1);
      const b = viaOverlay(g, 2, 1);
      const v = frameVectorToScreen(1, 0, k);
      expect((b.x - a.x) / 10).toBeCloseTo(v.x, 9);
      expect((b.y - a.y) / 10).toBeCloseTo(v.y, 9);
    });
  }

  it('pixelAt: the pixel under the pointer, null outside', () => {
    const g = geom(0);
    expect(pixelAt(g, 5 + 0.1, 7 + 0.1)).toEqual({ x: 0, y: 0 });
    expect(pixelAt(g, 5 + 59.9, 7 + 39.9)).toEqual({ x: 5, y: 3 });
    expect(pixelAt(g, 4, 7)).toBeNull();
  });

  it('rectangles stay inside the frame', () => {
    const f = { width: 100, height: 50 };
    expect(clampRect({ x0: -5, y0: 10, x1: 120, y1: 20 }, f)).toEqual({ x0: 0, y0: 10, x1: 100, y1: 20 });
    expect(moveRect({ x0: 90, y0: 0, x1: 100, y1: 10 }, 5, -3, f)).toEqual({ x0: 90, y0: 0, x1: 100, y1: 10 });
    expect(moveRect({ x0: 10, y0: 10, x1: 20, y1: 20 }, -3, 4, f)).toEqual({ x0: 7, y0: 14, x1: 17, y1: 24 });
    expect(centredRect(f, 80)).toEqual({ x0: 25, y0: 0, x1: 75, y1: 50 });
    expect(centredRect({ width: 1080, height: 1920 })).toEqual({ x0: 500, y0: 920, x1: 580, y1: 1000 });
    expect(isFrameRect({ x0: 1, y0: 1, x1: 2, y1: 2 })).toBe(true);
    expect(isFrameRect({ x0: 1, y0: 1, x1: 1, y1: 2 })).toBe(false);
    expect(isFrameRect('x')).toBe(false);
  });
});

/** numpy reference: region_stats on a plain array. */
function reference(values: number[]) {
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const s = [...values].sort((a, b) => a - b);
  const median = n % 2 ? s[n >> 1] : (s[n / 2 - 1] + s[n / 2]) / 2;
  const std = Math.sqrt(values.reduce((a, v) => a + (v - mean) ** 2, 0) / n);
  return { n, mean, median, std, min: s[0], max: s[n - 1] };
}

describe('region statistics (stretch.region_stats on raw samples)', () => {
  const w = 120;
  const h = 90;
  const px = new Uint16Array(w * h);
  for (let i = 0; i < px.length; i++) px[i] = 1000 + ((i * 2654435761) >>> 0) % 997;
  px[45 * w + 60] = 65535;

  const box = (r: { x0: number; y0: number; x1: number; y1: number }) => {
    const v: number[] = [];
    for (let y = r.y0; y < r.y1; y++) for (let x = r.x0; x < r.x1; x++) v.push(px[y * w + x]);
    return v;
  };

  it('small box (sorted path) matches numpy', () => {
    const r = { x0: 10, y0: 5, x1: 21, y1: 14 };
    const s = regionStats(px, w, h, 1, r)!;
    const ref = reference(box(r));
    expect(s.n).toBe(ref.n);
    expect(s.mean).toBeCloseTo(ref.mean, 9);
    expect(s.median).toBe(ref.median);
    expect(s.std).toBeCloseTo(ref.std, 9);
    expect([s.min, s.max]).toEqual([ref.min, ref.max]);
    expect(s.clipped).toBeNull();
  });

  it('large box (count-table path) matches numpy, even n, clipped counted', () => {
    const r = { x0: 0, y0: 0, x1: 120, y1: 90 };
    const s = regionStats(px, w, h, 1, r, { threshold: 60000 })!;
    const ref = reference(box(r));
    expect(s.n).toBe(10800);
    expect(s.mean).toBeCloseTo(ref.mean, 9);
    expect(s.median).toBe(ref.median);
    expect(s.std).toBeCloseTo(ref.std, 9);
    expect(s.max).toBe(65535);
    expect(s.clipped).toBe(1);
  });

  it('clamps to the frame, null when empty', () => {
    expect(regionStats(px, w, h, 1, { x0: 110, y0: 80, x1: 200, y1: 200 })!.n).toBe(10 * 10);
    expect(regionStats(px, w, h, 1, { x0: 200, y0: 0, x1: 210, y1: 10 })).toBeNull();
  });

  it('per-colour medians of a mosaic come from real samples of each site', () => {
    const cw = 8;
    const ch = 8;
    const m = new Uint16Array(cw * ch);
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) m[y * cw + x] = (y % 2) * 2 + (x % 2) === 1 ? 300 : (y % 2) * 2 + (x % 2) === 2 ? 100 : 200;
    const s = regionStats(m, cw, ch, 1, { x0: 0, y0: 0, x1: 8, y1: 8 }, { sites: cfaSites('GRBG') })!;
    expect(s.channels).toEqual({ r: 300, g: 200, b: 100 });
    expect(s.median).toBe(200);
  });

  it('RGB frames: the mean of the channels per pixel (Qt)', () => {
    const rgb = new Uint16Array([3, 6, 9, 30, 60, 90]);
    const s = regionStats(rgb, 2, 1, 3, { x0: 0, y0: 0, x1: 2, y1: 1 })!;
    expect([s.min, s.max, s.mean, s.median]).toEqual([6, 60, 33, 33]);
  });
});

describe('Statistics card: frame block', () => {
  it('exact statistics of all raw samples, and the ADC depth from the quantization step', async () => {
    const { frameStatistics, adcText } = await import('./statistics');
    const { histogram16 } = await import('../stretch');
    // A 12-bit sensor in 16 bits: every value a multiple of 16.
    const values = [1600, 1616, 1632, 1648, 1664, 16 * 4095];
    const s = frameStatistics(histogram16(values))!;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    expect(s.mean).toBeCloseTo(mean, 9);
    expect(s.median).toBe((1632 + 1648) / 2);
    expect(s.std).toBeCloseTo(Math.sqrt(values.reduce((a, v) => a + (v - mean) ** 2, 0) / values.length), 9);
    expect([s.min, s.max]).toEqual([1600, 65520]);
    expect(adcText(s)).toBe('12-bit (16 ADU steps)');
    expect(adcText(frameStatistics(histogram16([1, 2, 3, 5]))!)).toBe('16-bit');
    expect(frameStatistics(null)).toBeNull();
  });
});

describe('viewer context menu items', () => {
  it('says why each item cannot act', async () => {
    const { viewerMenuItems } = await import('./viewermenu');
    const off = viewerMenuItems({ pixel: null, sky: null, keys: {}, canIdentify: true, hasSelection: false });
    const reason = (items: ReturnType<typeof viewerMenuItems>, id: string) => (items.find((i) => 'id' in i && i.id === id) as { disabledReason?: string | null }).disabledReason ?? null;
    expect(reason(off, 'identify')).toBe('the pointer is not on the image');
    expect(reason(off, 'copy-pixel')).toBe('the pointer is not on the image');
    expect(reason(off, 'clear')).toBe('no star is selected');
    expect(reason(off, 'fit')).toBeNull();
    const on = viewerMenuItems({ pixel: { x: 512.4, y: 1033 }, sky: null, keys: { fit: 'F' }, canIdentify: false, identifyReason: 'no frame yet', hasSelection: true });
    expect(reason(on, 'copy-sky')).toBe('identify the field first (S)');
    expect(reason(on, 'identify')).toBe('no frame yet');
    expect(reason(on, 'clear')).toBeNull();
    const pixel = on.find((i) => 'id' in i && i.id === 'copy-pixel') as { detail?: string };
    expect(pixel.detail).toBe('x 512 · y 1033');
    const solved = viewerMenuItems({ pixel: { x: 1, y: 2 }, sky: { raHours: 5.5881, decDeg: -5.3911 }, keys: {}, canIdentify: true, hasSelection: false });
    const sky = solved.find((i) => 'id' in i && i.id === 'copy-sky') as { detail?: string; disabledReason?: string | null };
    expect(sky.disabledReason).toBeNull();
    expect(sky.detail).toBe('05h 35m 17.2s  −05° 23′ 28.0″');
  });
});

describe('viewer tools store (per viewer, safe without storage)', () => {
  const memory = () => {
    const m = new Map<string, string>();
    return { map: m, getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  };

  it('defaults: Colour preview, Neutral, centre crosshair, loupe 4x off, tools off', async () => {
    const { ViewerTools } = await import('./tools.svelte');
    const t = new ViewerTools(memory());
    expect([t.preview, t.palette, t.crosshairMode, t.loupe, t.loupeMag, t.saturation, t.region]).toEqual(['colour', 'neutral', 'centre', false, 4, false, false]);
  });

  it('remembers choices and ignores what storage cannot hold', async () => {
    const { ViewerTools } = await import('./tools.svelte');
    const s = memory();
    const t = new ViewerTools(s);
    t.setPalette('fire');
    t.setPreview('r');
    t.setLoupeMag(8);
    t.toggleLoupe(true);
    t.toggleRegion({ width: 1080, height: 1920 });
    const again = new ViewerTools(s);
    expect([again.palette, again.preview, again.loupe, again.loupeMag, again.region]).toEqual(['fire', 'r', true, 8, true]);
    expect(again.regionRect).toEqual({ x0: 500, y0: 920, x1: 580, y1: 1000 });
    s.map.set('argos.view.palette', '"rainbow"');
    s.map.set('argos.view.loupe', '{"on":true,"mag":3}');
    const bad = new ViewerTools(s);
    expect([bad.palette, bad.loupeMag]).toEqual(['neutral', 4]);
  });

  it('measures the box on the raw samples of the frame on screen, placed on first use', async () => {
    const { ViewerTools } = await import('./tools.svelte');
    const t = new ViewerTools(memory());
    const w = 200;
    const h = 100;
    const pixels = new Uint16Array(w * h).fill(1000);
    const frame = { header: { width: w, height: h, channels: 1 as const }, pixels } as unknown as import('../../api/frames').DecodedFrame;
    t.region = true;
    t.measure(frame, { threshold: 60000 });
    expect(t.regionRect).toEqual({ x0: 60, y0: 10, x1: 140, y1: 90 });
    expect(t.regionResult).toMatchObject({ n: 6400, mean: 1000, median: 1000, std: 0, clipped: 0 });
    t.regionAt({ width: w, height: h }, { x: 10, y: 10 });
    expect(t.regionRect).toEqual({ x0: 0, y0: 0, x1: 80, y1: 80 });
    t.toggleRegion(null, false);
    t.measure(frame);
    expect(t.regionResult).toBeNull();
  });
});
