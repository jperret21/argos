import { describe, expect, it } from 'vitest';
import { adcStep, clipping, greenSites, starPeaks } from './framestats';
import { histogram16 } from './stretch';

/** A flat noisy-ish frame with Gaussian stars and one hot pixel. */
function frame(w: number, h: number, stars: { x: number; y: number; amp: number; s?: number }[], hot?: [number, number]): Uint16Array {
  const px = new Uint16Array(w * h);
  for (let i = 0; i < px.length; i++) px[i] = 1000 + ((i * 7919) % 5) * 4; // 1000..1016, MAD > 0
  for (const st of stars) {
    const s = st.s ?? 1.4;
    for (let y = Math.floor(st.y - 6); y <= st.y + 6; y++)
      for (let x = Math.floor(st.x - 6); x <= st.x + 6; x++) {
        if (x < 0 || y < 0 || x >= w || y >= h) continue;
        const v = px[y * w + x] + st.amp * Math.exp(-((x - st.x) ** 2 + (y - st.y) ** 2) / (2 * s * s));
        px[y * w + x] = Math.min(65535, Math.round(v));
      }
  }
  if (hot) px[hot[1] * w + hot[0]] = 30000;
  return px;
}

describe('exposure statistics (frame worker)', () => {
  it('reports the peaks of stars, brightest first, and never a hot pixel', () => {
    const px = frame(
      128,
      96,
      [
        { x: 30, y: 30, amp: 20000 },
        { x: 90, y: 60, amp: 70000 }, // clipped core
        { x: 60, y: 20, amp: 5000 },
      ],
      [10, 80],
    );
    const r = starPeaks(px, 128, 96);
    const peaks = r.stars.map((s) => s.peak);
    expect([...peaks].sort((a, b) => b - a)).toEqual(peaks);
    expect(r.stars[0]).toMatchObject({ peak: 65535, x: 90, y: 60 });
    expect(r.stars[1].peak).toBeGreaterThan(20000);
    expect(r.stars).toHaveLength(3);
    expect(r.stars.some((s) => s.x === 10 && s.y === 80)).toBe(false); // the hot pixel has no PSF support
    expect(r.sky).toBeGreaterThanOrEqual(1000);
    expect(r.sky).toBeLessThanOrEqual(1016);
  });

  it('detects on the green plane of a CFA frame and reports the brightest raw pixel of any colour', () => {
    const w = 128;
    const h = 96;
    const px = frame(w, h, [{ x: 41, y: 41, amp: 30000, s: 2 }]);
    px[40 * w + 41] = 60000; // a green pixel of the core (RGGB: even row, odd column)
    px[41 * w + 41] = 65520; // the blue pixel beside it clips: it is the star's raw peak
    expect(greenSites('RGGB')).toEqual([
      [1, 0],
      [0, 1],
    ]);
    expect(greenSites('GRBG')).toEqual([
      [0, 0],
      [1, 1],
    ]);
    const r = starPeaks(px, w, h, { bayer: 'RGGB' });
    expect(r.stars).toHaveLength(1);
    expect(r.stars[0].peak).toBe(65520);
    expect(Math.abs(r.stars[0].x - 41)).toBeLessThanOrEqual(2);
  });

  it('finds the ADC step and counts the clipped pixels at the top code', () => {
    // 12-bit data shifted into 16 bits: multiples of 16, top code 65 520.
    const px = new Uint16Array(1000);
    for (let i = 0; i < px.length; i++) px[i] = (100 + (i % 50)) * 16;
    px[0] = 65520;
    px[1] = 65520;
    const h = histogram16(px);
    expect(adcStep(h)).toBe(16);
    expect(clipping(h, 50000)).toMatchObject({ topCode: 65520, step: 16, clipped: 2, aboveLevel: 2 });
    const full = histogram16(new Uint16Array([1, 2, 3, 65535]));
    expect(clipping(full)).toMatchObject({ topCode: 65535, clipped: 1, aboveLevel: null });
  });
});
