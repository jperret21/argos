/**
 * Synthetic data for the workspace gallery (development only, /?gallery=1):
 * an evening of conditions rows, autofocus records in every state, exposure
 * checks. Deterministic, so screenshots are reproducible. Never imported by
 * the app.
 */

import type { ConditionsRow } from '../../../charts/conditions';
import { hyperbola } from '../../../charts/fit';
import type { AutofocusRecord } from '../../../charts/vcurve';

/** A seeded PRNG (mulberry32). */
function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const NOW = Date.parse('2026-11-08T22:40:00Z') / 1000;

/** Two hours of live frames every 4 s, a 6-minute pause at 21:55, HFD slowly rising. */
export function conditionsRows(n = 1700, stopEarly = 0): ConditionsRow[] {
  const r = prng(7);
  const out: ConditionsRow[] = [];
  let t = NOW - 2 * 3600;
  for (let i = 0; i < n; i++) {
    t += 4 + (r() - 0.5) * 0.4;
    if (i === 800) t += 360; // a pause
    if (t > NOW - stopEarly) break;
    const k = i / n;
    const hfd = 2.6 + 0.9 * k + 0.12 * (r() - 0.5) + (i > 1200 && i < 1260 ? 0.6 : 0);
    out.push({
      seq: i + 1,
      frame_seq: 1000 + i,
      t: new Date(t * 1000).toISOString(),
      origin: 'live',
      exposure_s: 4,
      gain: 80,
      frame_type: 'light',
      filter: 'IR',
      hfd_px: hfd,
      fwhm_px: hfd * 0.62 + 0.05 * (r() - 0.5),
      star_count: Math.round(260 - 70 * k + 10 * (r() - 0.5)),
      sky_adu: 1790 + 60 * k + 6 * (r() - 0.5),
      peak_adu: Math.round(52000 - 9000 * k + 1500 * (r() - 0.5)),
      airmass_mount: 1.08 + 0.45 * k * k,
      airmass_target: null,
      sensor_temp_c: 14 - 3 * k + 0.2 * (r() - 0.5),
      focuser_temp_c: null,
      focuser_position: i < 900 ? 5000 : 5140,
    });
  }
  return out;
}

const V = { a: 2.3, b: 260, c: 5180 };
const hfdAt = (x: number, r: () => number) => Math.min(13, hyperbola(x, V.a, V.b, V.c) * (1 + 0.035 * (r() - 0.5) * 2));
const COARSE = [3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7000];

function sweep(k: number): AutofocusRecord['samples'] {
  const r = prng(11);
  const coarse = COARSE.map((p) => ({ position: p, hfd_px: Math.round(hfdAt(p, r) * 100) / 100, stage: 'coarse' as const }));
  let min = coarse[0];
  for (const s of coarse) if ((s.hfd_px ?? 99) < (min.hfd_px ?? 99)) min = s;
  const fine = [-333, -167, 167, 333].map((o) => ({ position: min.position + o, hfd_px: Math.round(hfdAt(min.position + o, r) * 100) / 100, stage: 'fine' as const }));
  return [...coarse, ...fine].slice(0, k);
}

/** A worker-like parabola over the fine samples and the coarse minimum (numpy.polyfit order 2). */
function parabola(pts: { position: number; hfd_px: number | null }[]): [number, number, number] {
  // Normal equations on x centred for conditioning, then expanded back.
  const xs = pts.map((p) => p.position);
  const ys = pts.map((p) => p.hfd_px ?? 0);
  const m = xs.reduce((a, b) => a + b, 0) / xs.length;
  const S = [0, 0, 0, 0, 0];
  const T = [0, 0, 0];
  for (let i = 0; i < xs.length; i++) {
    const u = xs[i] - m;
    for (let k = 0; k < 5; k++) S[k] += u ** k;
    for (let k = 0; k < 3; k++) T[k] += ys[i] * u ** k;
  }
  // Solve [[S4 S3 S2][S3 S2 S1][S2 S1 S0]] [a b c] = [T2 T1 T0] (Cramer).
  const M = [
    [S[4], S[3], S[2]],
    [S[3], S[2], S[1]],
    [S[2], S[1], S[0]],
  ];
  const det = (A: number[][]) =>
    A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1]) - A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0]) + A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0]);
  const D = det(M);
  const col = (j: number) => M.map((row, i) => row.map((v, k) => (k === j ? [T[2], T[1], T[0]][i] : v)));
  const a = det(col(0)) / D;
  const b = det(col(1)) / D;
  const c = det(col(2)) / D;
  // y = a u^2 + b u + c with u = x - m  ->  in x.
  return [a, b - 2 * a * m, a * m * m - b * m + c];
}

export function autofocus(state: 'coarse' | 'fine' | 'done' | 'rejected' | 'stopping' | 'cancelled'): AutofocusRecord {
  const base = { start_position: 5000, total: 14, params: { exposure_s: 2, gain: 80, half_range: 2000, num_steps: 9 }, run: 3 };
  if (state === 'coarse') {
    const s = sweep(6);
    return { ...base, state: 'running', stage: 'coarse', step: 6, samples: s, position: s?.at(-1)?.position ?? null };
  }
  if (state === 'fine' || state === 'stopping') {
    const s = sweep(12);
    return { ...base, state: state === 'stopping' ? 'stopping' : 'running', stage: state === 'stopping' ? 'returning' : 'fine', step: 12, samples: s, position: s?.at(-1)?.position ?? null };
  }
  if (state === 'rejected') {
    const r = prng(5);
    const flat = COARSE.map((p) => ({ position: p, hfd_px: Math.round((3.1 + 0.15 * (r() - 0.5)) * 100) / 100, stage: 'coarse' as const }));
    return { ...base, state: 'rejected', stage: null, step: 9, samples: flat, position: 5000, message: 'Autofocus: flat HFD curve (3.04–3.17, span < 15%) — focus unchanged' };
  }
  if (state === 'cancelled') {
    return { ...base, state: 'cancelled', stage: null, step: 7, samples: sweep(7), position: 5000, message: 'Returned to 5000.' };
  }
  const s = sweep(13)!;
  const coarse = s.filter((x) => x.stage === 'coarse');
  let min = coarse[0];
  for (const x of coarse) if ((x.hfd_px ?? 99) < (min.hfd_px ?? 99)) min = x;
  const used = [...s.filter((x) => x.stage === 'fine'), min];
  const [a, b, c] = parabola(used);
  const best = Math.round(-b / (2 * a));
  const r = prng(3);
  const verify = Math.round(hfdAt(best, r) * 100) / 100;
  return {
    ...base,
    state: 'done',
    stage: null,
    step: 14,
    samples: [...s, { position: best, hfd_px: verify, stage: 'verify' }],
    position: best,
    best: { position: best, hfd_px: verify, fitted_hfd_px: a * best * best + b * best + c, method: 'parabola' },
    fit: { coeffs: [a, b, c], window: [min.position - 500, min.position + 500], samples: used.map((x) => [x.position, x.hfd_px ?? 0]) },
    message: `Autofocus complete — best pos=${best}  HFD=${verify}`,
  };
}
