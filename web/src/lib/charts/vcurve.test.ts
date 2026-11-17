import { describe, expect, it } from 'vitest';
import { hyperbola } from './fit';
import { coarseZone, curveColumns, fittedPositions, vcurveModel, verdict, vZone, type AfSampleRecord, type AutofocusRecord } from './vcurve';

// A sweep shaped like the worker's (autofocus_worker.py): start 5000, half
// range 2000, 9 coarse positions 500 apart, 4 fine ones around the raw
// minimum (focus.py refine_positions: +/- 167, 333), then one verify frame.
const TRUE = { a: 2.1, b: 300, c: 5420 };
const hfd = (x: number) => Math.min(12, hyperbola(x, TRUE.a, TRUE.b, TRUE.c)); // far defocus saturates
const COARSE = [3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000];
const FINE = [5167, 5333, 5667, 5833];

function samples(k: number, failAt = -1): AfSampleRecord[] {
  const all: AfSampleRecord[] = [
    ...COARSE.map((p) => ({ position: p, hfd_px: hfd(p), stage: 'coarse' })),
    ...FINE.map((p) => ({ position: p, hfd_px: hfd(p), stage: 'fine' })),
  ];
  return all.slice(0, k).map((s, i) => (i === failAt ? { ...s, hfd_px: null } : s));
}

describe('V-curve model over the server autofocus record', () => {
  it('finds the coarse zone the worker uses (raw minimum +/- spacing)', () => {
    expect(coarseZone(samples(9))).toEqual({ center: 5500, spacing: 500 });
    const af: AutofocusRecord = { state: 'running', stage: 'fine', samples: samples(10) };
    expect(vZone(af)).toEqual([5000, 6000]);
    // The server's own window wins when it is known.
    expect(vZone({ ...af, fit: { coeffs: [1, 2, 3], window: [5100, 5900] } })).toEqual([5100, 5900]);
    // During the coarse sweep there is no zone yet: everything is fitted (provisional).
    expect(vZone({ state: 'running', stage: 'coarse', samples: samples(6) })).toBeNull();
  });

  it('estimates no vertex until the minimum is bracketed, and never outside the samples', () => {
    // Coarse sweep still descending: the lowest sample is the last one.
    expect(vcurveModel({ state: 'running', stage: 'coarse', samples: samples(5) }).fit).toBeNull();
    expect(vcurveModel({ state: 'running', stage: 'coarse', samples: samples(5) }).provisional).toBeNull();
    // Past the minimum: bracketed, a provisional vertex appears.
    expect(vcurveModel({ state: 'running', stage: 'coarse', samples: samples(8) }).provisional).not.toBeNull();
  });

  it('fits the samples the worker fits (fine + coarse minimum), hollow elsewhere, vertex provisional while running', () => {
    const m = vcurveModel({ state: 'running', stage: 'fine', start_position: 5000, position: 5833, samples: samples(13), step: 13, total: 14 });
    const fitted = m.samples.filter((s) => s.kind === 'fitted').map((s) => s.x);
    expect(fitted).toEqual([5500, 5167, 5333, 5667, 5833]);
    expect(m.samples.filter((s) => s.kind === 'outside').map((s) => s.x)).toEqual([3000, 3500, 4000, 4500, 5000, 6000, 6500, 7000]);
    expect(m.window).toEqual([5167, 5833]);
    // The server's own list wins (the positions its parabola used).
    expect(fittedPositions({ state: 'done', fit: { coeffs: [1, 2, 3], window: [5000, 6000], samples: [[5167, 3], [5500, 2]] } })).toEqual(new Set([5167, 5500]));
    expect(m.fit).not.toBeNull();
    expect(Math.abs(m.fit!.c - TRUE.c)).toBeLessThan(1);
    expect(m.fit!.a).toBeCloseTo(TRUE.a, 3);
    expect(m.decided).toBeNull();
    expect(m.provisional?.position).toBeCloseTo(TRUE.c, 0);
    // Noiseless samples: no scatter to draw as error bars.
    expect(m.scatter).toBeLessThan(1e-6);
    expect(m.xRange[0]).toBeLessThan(3000);
    expect(m.xRange[1]).toBeGreaterThan(7000);
  });

  it('marks the worker decision only once the sweep ends done, never the display vertex', () => {
    const base: AutofocusRecord = {
      state: 'done',
      start_position: 5000,
      position: 5431,
      samples: [...samples(13), { position: 5431, hfd_px: 2.12, stage: 'verify' }],
      best: { position: 5431, hfd_px: 2.12, fitted_hfd_px: 2.1, method: 'parabola' },
      fit: { coeffs: [2e-5, -0.2172, 592], window: [5000, 6000] },
    };
    const m = vcurveModel(base);
    expect(m.decided).toEqual({ position: 5431, hfd: 2.12, method: 'parabola' });
    expect(m.provisional).toBeNull();
    expect(m.samples.at(-1)?.kind).toBe('verify');
    expect(m.parabola).toEqual({ a: 2e-5, b: -0.2172, c: 592, lo: 5000, hi: 6000 });
    // Rejected or cancelled sweeps never show a decision.
    expect(vcurveModel({ ...base, state: 'rejected' }).decided).toBeNull();
    expect(vcurveModel({ ...base, state: 'cancelled' }).decided).toBeNull();
  });

  it('fills the plot with the V: a shallow curve does not start at zero, a deep one does', () => {
    const shallow = vcurveModel({
      state: 'done',
      samples: [4400, 4700, 5000, 5300, 5600].map((p, i) => ({ position: p, hfd_px: [6.3, 5.9, 5.3, 4.9, 5.4][i], stage: 'coarse' })),
    });
    expect(shallow.yMin).toBeGreaterThan(3);
    expect(shallow.yMax).toBeGreaterThan(6.3);
    expect(vcurveModel({ state: 'running', stage: 'fine', samples: samples(13) }).yMin).toBe(0);
  });

  it('keeps a failed frame as a failed sample (no HFD invented) and out of the fit', () => {
    const m = vcurveModel({ state: 'running', stage: 'fine', samples: samples(13, 11) });
    expect(m.samples[11].kind).toBe('failed');
    expect(Number.isNaN(m.samples[11].y)).toBe(true);
    expect(m.fit).not.toBeNull();
  });

  it('draws the curve solid inside the zone, dashed outside, and the envelope inside only', () => {
    const m = vcurveModel({ state: 'running', stage: 'fine', samples: samples(13), fit: { coeffs: [2e-5, -0.2172, 592], window: [5000, 6000] } });
    const c = curveColumns(m, 101);
    const i = c.xs.findIndex((x) => x > 5450);
    expect(c.inside[i]).not.toBeNull();
    expect(c.hi[i]).not.toBeNull();
    expect(c.inside[0]).toBeNull();
    expect(c.outside[0]).not.toBeNull();
    expect(c.hi[0]).toBeNull();
    expect(c.parabola[i]).toBeCloseTo(2e-5 * c.xs[i] ** 2 - 0.2172 * c.xs[i] + 592, 6);
    expect(c.parabola[0]).toBeNull();
  });

  it('words every state, preferring the worker’s own message', () => {
    const pos = (v: number) => String(Math.round(v));
    const px = (v: number) => `${v.toFixed(2)} px`;
    expect(verdict(null, pos, px).state).toBe('Idle');
    expect(verdict({ state: 'running', stage: 'coarse', samples: samples(3), total: 14, start_position: 5000 }, pos, px)).toMatchObject({
      state: 'Coarse sweep',
      tone: 'busy',
      text: 'Frame 3 of 14 · started at 5000.',
    });
    expect(verdict({ state: 'stopping', start_position: 5000 }, pos, px).text).toMatch(/returns to 5000 before the camera is released/);
    expect(verdict({ state: 'done', best: { position: 5431, hfd_px: 2.12, method: 'parabola' } }, pos, px).text).toBe(
      'Focuser at 5431, the vertex of the worker’s parabola; verification frame 2.12 px.',
    );
    expect(verdict({ state: 'done', best: { position: 5500, hfd_px: null, method: 'raw' } }, pos, px).text).toMatch(/lowest sample/);
    expect(verdict({ state: 'rejected', message: 'Autofocus: flat HFD curve (2.10–2.20, span < 15%) — focus unchanged' }, pos, px)).toMatchObject({
      state: 'Rejected',
      tone: 'error',
    });
    expect(verdict({ state: 'cancelled', message: 'Returned to 5000.' }, pos, px).text).toBe('Returned to 5000.');
  });
});
