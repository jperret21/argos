/**
 * The autofocus V-curve as data for VCurvePlot.svelte: pure functions over
 * the server's `autofocus` record (argos/server/protocol.md "Autofocus
 * (A36)", a port of argos/workers/autofocus_worker.py:48-232 with
 * argos/core/imaging/focus.py unchanged). No uPlot, no DOM: unit-tested.
 *
 * Two fits, two roles (BRAND 10 "provisional vs decided"):
 * - the WORKER's parabola (`fit.coeffs` over `fit.window`, focus.py
 *   fit_v_curve on the fine samples plus the coarse minimum) is what moved
 *   the focuser; its decision is `best.position`, drawn in brass once the
 *   sweep ends `done`;
 * - a DISPLAY hyperbola (charts/fit.ts) over the same V zone gives the
 *   asymptotes, a +/- 1 sigma envelope and a vertex with its uncertainty.
 *   While the sweep runs the vertex is provisional (dashed, no brass); it
 *   never replaces the worker's decision.
 *
 * Errors: the server sends one HFD per sample and no uncertainty. The fit
 * therefore uses unit weights with the covariance scaled by the residual
 * variance (fit.ts `unknownErrors`), and the error bars drawn on the fitted
 * samples are that residual scatter (+/- 1 sigma about the fit), said so in
 * the legend; never an invented per-sample error.
 *
 * The fitted samples are the worker's (autofocus_worker.py:146-153): once the
 * fine sweep has started, the fine samples plus the coarse minimum (the
 * server's `fit.samples` when it sent them); the rest of the coarse sweep is
 * drawn hollow and left out of the display fit, as the worker leaves it out
 * (far from focus the HFD saturates and would bend the fit). During the
 * coarse sweep every coarse sample is fitted (the vertex is provisional).
 * `fit.window` is NOT the sample selection: it bounds where the worker
 * accepts a vertex (raw minimum +/- one coarse step).
 *
 * When the worker's samples give no usable hyperbola (too few, not
 * bracketed, not converged: typical of real fine sweeps once the run is
 * decided), the display fit falls back to every coarse and fine sample, so
 * the decided state never shows less evidence than the provisional one
 * (design review of wave 3); when even that fails, `noFit` says why in words.
 */

import { curveSigma, fitHyperbola, hyperbola, type HyperbolaFit, type Sample } from './fit';

/** One sample of the sweep, as the server sends it. */
export interface AfSampleRecord {
  position: number;
  hfd_px: number | null;
  stage?: 'coarse' | 'fine' | 'verify' | string | null;
  t?: string | null;
}

/** The subset of the server's AutofocusState the plot reads (structural). */
export interface AutofocusRecord {
  state: 'idle' | 'running' | 'stopping' | 'done' | 'rejected' | 'cancelled' | 'failed' | string;
  stage?: string | null;
  step?: number | null;
  total?: number | null;
  params?: { exposure_s?: number; gain?: number; half_range?: number; num_steps?: number } | null;
  start_position?: number | null;
  position?: number | null;
  samples?: readonly AfSampleRecord[] | null;
  best?: { position: number; hfd_px?: number | null; fitted_hfd_px?: number | null; method?: string | null } | null;
  fit?: { coeffs?: readonly number[] | null; window?: readonly number[] | null; samples?: readonly (readonly number[])[] | null } | null;
  message?: string | null;
  run?: number;
  started_utc?: string | null;
  ended_utc?: string | null;
}

export type SampleKind = 'fitted' | 'outside' | 'verify' | 'failed';

export interface PlotSample {
  x: number;
  /** NaN for a failed frame (no HFD): drawn as a tick on the axis. */
  y: number;
  kind: SampleKind;
  stage: string;
  /** 1-based frame number in the sweep. */
  n: number;
}

export interface VCurveModel {
  samples: PlotSample[];
  /** The display hyperbola over the V zone (null: fewer than 4 fitted samples). */
  fit: HyperbolaFit | null;
  /** Which samples the display fit used: the worker's, or all of them (fallback). */
  fitScope: 'worker' | 'all' | null;
  /** Why there is no display hyperbola, in words (null when there is one, or no sample). */
  noFit: string | null;
  /** +/- 1 sigma residual scatter of the fitted samples about the display fit (px). */
  scatter: number | null;
  /** The extent of the fitted samples (the curve is solid inside, dashed outside). */
  window: [number, number] | null;
  /** The worker's parabola, a*p^2 + b*p + c over its window, when it sent one. */
  parabola: { a: number; b: number; c: number; lo: number; hi: number } | null;
  /** The worker's decision, only once the sweep ended `done`. */
  decided: { position: number; hfd: number | null; method: string } | null;
  /** Vertex of the display fit while no decision exists (dashed, no brass). */
  provisional: { position: number; sigma: number; hfd: number } | null;
  start: number | null;
  focuser: number | null;
  /** x range of the plot (all samples, the start and the decision, padded). */
  xRange: [number, number];
  /** y range: the sampled HFD padded (the V fills the plot; 0 only when it is near). */
  yMin: number;
  yMax: number;
  /** Frames taken / announced. */
  step: number;
  total: number;
}

const finite = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);

/** Coarse spacing and raw minimum of the coarse sweep (worker: spacing = coarse[1] - coarse[0]). */
export function coarseZone(samples: readonly AfSampleRecord[]): { center: number; spacing: number } | null {
  const coarse = samples.filter((s) => (s.stage ?? 'coarse') === 'coarse');
  const valid = coarse.filter((s) => finite(s.hfd_px));
  if (valid.length < 1) return null;
  const xs = [...new Set(coarse.map((s) => s.position))].sort((a, b) => a - b);
  const spacing = xs.length > 1 ? xs[1] - xs[0] : 0;
  let best = valid[0];
  for (const s of valid) if ((s.hfd_px as number) < (best.hfd_px as number)) best = s;
  return { center: best.position, spacing };
}

/**
 * Positions the worker's fit uses: the server's `fit.samples`, else (once the
 * fine sweep started) the fine positions and the coarse minimum; null during
 * the coarse sweep (every coarse sample is fitted, provisionally).
 */
export function fittedPositions(af: AutofocusRecord): Set<number> | null {
  const fs = af.fit?.samples;
  if (fs && fs.length) return new Set(fs.map((p) => p[0]).filter(finite));
  const samples = af.samples ?? [];
  if (!samples.some((s) => s.stage === 'fine')) return null;
  const out = new Set(samples.filter((s) => s.stage === 'fine').map((s) => s.position));
  const z = coarseZone(samples);
  if (z) out.add(z.center);
  return out;
}

/** The window the worker accepts a vertex in (server `fit.window`), else raw minimum +/- one coarse step. */
export function vZone(af: AutofocusRecord): [number, number] | null {
  const w = af.fit?.window;
  if (w && w.length === 2 && finite(w[0]) && finite(w[1])) return [Math.min(w[0], w[1]), Math.max(w[0], w[1])];
  const samples = af.samples ?? [];
  if (!samples.some((s) => s.stage === 'fine')) return null;
  const z = coarseZone(samples);
  if (!z || z.spacing <= 0) return null;
  return [z.center - z.spacing, z.center + z.spacing];
}

/** The lowest sample is not the first nor the last by position (the V is bracketed). */
export function minimumBracketed(pts: readonly Sample[]): boolean {
  const sorted = [...pts].sort((a, b) => a.x - b.x);
  let k = 0;
  for (let i = 1; i < sorted.length; i++) if (sorted[i].y < sorted[k].y) k = i;
  return k > 0 && k < sorted.length - 1;
}

/** Residual RMS about a fit, with n - 3 degrees of freedom. */
export function residualScatter(fit: HyperbolaFit, pts: readonly Sample[]): number | null {
  if (pts.length <= 3) return null;
  let ss = 0;
  for (const p of pts) ss += (p.y - hyperbola(p.x, fit.a, fit.b, fit.c)) ** 2;
  return Math.sqrt(ss / (pts.length - 3));
}

/** A display hyperbola over these samples, or why there is none. */
function displayFit(pts: readonly Sample[]): { fit: HyperbolaFit | null; why: string | null } {
  if (pts.length < 4) return { fit: null, why: `too few samples (${pts.length} of 4)` };
  // A vertex is only estimated once the minimum is bracketed (not on an edge of
  // the fitted samples, as focus.py sweep_is_degenerate asks), and only inside them.
  if (!minimumBracketed(pts)) return { fit: null, why: 'the lowest HFD is at an edge of the sweep' };
  const fit = fitHyperbola(pts, { unknownErrors: true });
  const lo0 = Math.min(...pts.map((p) => p.x));
  const hi0 = Math.max(...pts.map((p) => p.x));
  const sane = fit && fit.converged && Number.isFinite(fit.c) && fit.a > 0 && fit.c >= lo0 && fit.c <= hi0 ? fit : null;
  return sane ? { fit: sane, why: null } : { fit: null, why: 'the samples do not follow a V' };
}

export function vcurveModel(af: AutofocusRecord | null): VCurveModel {
  const raw = af?.samples ?? [];
  const used = af ? fittedPositions(af) : null;
  let samples: PlotSample[] = raw.map((s, i) => {
    const stage = s.stage ?? 'coarse';
    const y = finite(s.hfd_px) ? s.hfd_px : NaN;
    let kind: SampleKind;
    if (!Number.isFinite(y)) kind = 'failed';
    else if (stage === 'verify') kind = 'verify';
    else if (!used || used.has(s.position)) kind = 'fitted';
    else kind = 'outside';
    return { x: s.position, y, kind, stage, n: i + 1 };
  });
  const ptsOf = (list: PlotSample[]): Sample[] => list.filter((s) => s.kind === 'fitted').map((s) => ({ x: s.x, y: s.y, s: 1 }));
  let pts = ptsOf(samples);
  let { fit: sane, why } = displayFit(pts);
  let fitScope: VCurveModel['fitScope'] = sane ? 'worker' : null;
  if (!sane && samples.some((s) => s.kind === 'outside')) {
    // Fallback: every coarse and fine sample, so the evidence stays on the plot.
    const all = samples.map((s) => (s.kind === 'outside' ? { ...s, kind: 'fitted' as const } : s));
    const tried = displayFit(ptsOf(all));
    if (tried.fit) {
      samples = all;
      pts = ptsOf(all);
      sane = tried.fit;
      why = null;
      fitScope = 'all';
    }
  }
  const noFit = sane || !raw.length ? null : `no hyperbola: ${why}`;
  const fx = samples.filter((s) => s.kind === 'fitted').map((s) => s.x);
  const zone: [number, number] | null = fx.length ? [Math.min(...fx), Math.max(...fx)] : null;
  const scatter = sane ? residualScatter(sane, pts) : null;

  const coeffs = af?.fit?.coeffs;
  const win = af?.fit?.window;
  const parabola =
    coeffs && coeffs.length === 3 && coeffs.every(finite) && win && win.length === 2
      ? { a: coeffs[0], b: coeffs[1], c: coeffs[2], lo: Math.min(win[0], win[1]), hi: Math.max(win[0], win[1]) }
      : null;

  const decided =
    af?.state === 'done' && af.best && finite(af.best.position)
      ? { position: af.best.position, hfd: finite(af.best.hfd_px) ? af.best.hfd_px : null, method: af.best.method ?? 'parabola' }
      : null;
  const provisional =
    !decided && sane && af && (af.state === 'running' || af.state === 'stopping')
      ? { position: sane.c, sigma: sane.sigmaC, hfd: sane.a }
      : null;

  const start = af && finite(af.start_position) ? af.start_position : null;
  const focuser = af && finite(af.position) ? af.position : null;
  const xs: number[] = samples.map((s) => s.x);
  if (start !== null) xs.push(start);
  if (decided) xs.push(decided.position);
  let lo = xs.length ? Math.min(...xs) : 0;
  let hi = xs.length ? Math.max(...xs) : 1;
  if (!(hi > lo)) {
    lo -= 100;
    hi += 100;
  }
  const pad = (hi - lo) * 0.06;
  let yLo = Infinity;
  let yHi = -Infinity;
  for (const s of samples) {
    if (!Number.isFinite(s.y)) continue;
    const e = s.kind === 'fitted' && scatter ? scatter : 0;
    yLo = Math.min(yLo, s.y - e);
    yHi = Math.max(yHi, s.y + e);
  }
  let yMin = 0;
  let yMax = 6;
  if (Number.isFinite(yLo)) {
    // At least half the best HFD of height: a flat sweep must look flat.
    const span = Math.max(yHi - yLo, 0.5 * yLo, 0.5);
    yMin = Math.max(0, yLo - 0.35 * span);
    yMax = yHi + 0.15 * span;
    // A V that reaches near zero keeps its true baseline.
    if (yMin < 0.25 * span) yMin = 0;
  }

  return {
    samples,
    fit: sane,
    fitScope,
    noFit,
    scatter,
    window: zone,
    parabola,
    decided,
    provisional,
    start,
    focuser,
    xRange: [lo - pad, hi + pad],
    yMin,
    yMax,
    step: af?.step ?? samples.length,
    total: af?.total ?? samples.length,
  };
}

/** Curve columns for uPlot: the fit inside its zone, its extrapolation, and the envelope. */
export function curveColumns(
  m: VCurveModel,
  grid = 240,
): { xs: Float64Array; inside: (number | null)[]; outside: (number | null)[]; hi: (number | null)[]; lo: (number | null)[]; parabola: (number | null)[] } {
  const [x0, x1] = m.xRange;
  const xs = new Float64Array(grid);
  const inside: (number | null)[] = new Array(grid).fill(null);
  const outside: (number | null)[] = new Array(grid).fill(null);
  const hi: (number | null)[] = new Array(grid).fill(null);
  const lo: (number | null)[] = new Array(grid).fill(null);
  const parabola: (number | null)[] = new Array(grid).fill(null);
  const step = (x1 - x0) / (grid - 1);
  const f = m.fit;
  const zone = m.window ?? (m.samples.length ? [Math.min(...m.samples.map((s) => s.x)), Math.max(...m.samples.map((s) => s.x))] : null);
  for (let i = 0; i < grid; i++) {
    const x = x0 + step * i;
    xs[i] = x;
    if (f && zone) {
      const y = hyperbola(x, f.a, f.b, f.c);
      const inZone = x >= zone[0] - step && x <= zone[1] + step;
      if (inZone) inside[i] = y;
      if (!(x > zone[0] + step && x < zone[1] - step)) outside[i] = y;
      if (inZone) {
        const sg = curveSigma(f, x);
        hi[i] = y + sg;
        lo[i] = Math.max(0, y - sg);
      }
    }
    const p = m.parabola;
    if (p && x >= p.lo - step && x <= p.hi + step) parabola[i] = p.a * x * x + p.b * x + p.c;
  }
  return { xs, inside, outside, hi, lo, parabola };
}

export interface Verdict {
  /** One word for the chip: Idle, Coarse sweep, Fine sweep, Verifying, Returning, Focused, Rejected, Cancelled, Failed. */
  state: string;
  tone: 'idle' | 'busy' | 'ok' | 'error' | 'stale';
  /** The sentence under the plot: what happened and where the focuser is. */
  text: string;
}

const STAGE_WORDS: Record<string, string> = {
  coarse: 'Coarse sweep',
  fine: 'Fine sweep',
  verify: 'Verifying',
  returning: 'Returning',
};

/** The state of the sweep in words (the server's message wins: it is the worker's own). */
export function verdict(af: AutofocusRecord | null, fmtPos: (v: number) => string, fmtHfd: (v: number) => string): Verdict {
  if (!af || af.state === 'idle') return { state: 'Idle', tone: 'idle', text: 'No autofocus yet in this session.' };
  const n = af.samples?.length ?? 0;
  switch (af.state) {
    case 'running':
      return {
        state: STAGE_WORDS[af.stage ?? ''] ?? 'Running',
        tone: 'busy',
        text: `Frame ${n} of ${af.total ?? '—'}${af.start_position != null ? ` · started at ${fmtPos(af.start_position)}` : ''}.`,
      };
    case 'stopping':
      return {
        state: 'Returning',
        tone: 'busy',
        text: `Stopped: the focuser returns to ${af.start_position != null ? fmtPos(af.start_position) : 'its start'} before the camera is released.`,
      };
    case 'done': {
      const b = af.best;
      if (!b) return { state: 'Focused', tone: 'ok', text: af.message ?? 'Autofocus complete.' };
      const how = b.method === 'raw' ? 'lowest sample (no reliable parabola)' : 'vertex of the worker’s parabola';
      const hfd = b.hfd_px != null ? `; verification frame ${fmtHfd(b.hfd_px)}` : '';
      return { state: 'Focused', tone: 'ok', text: `Focuser at ${fmtPos(b.position)}, the ${how}${hfd}.` };
    }
    case 'rejected':
      return { state: 'Rejected', tone: 'error', text: af.message ?? 'Rejected: focus unchanged.' };
    case 'cancelled':
      return { state: 'Cancelled', tone: 'stale', text: af.message ?? 'Cancelled.' };
    case 'failed':
      return { state: 'Failed', tone: 'error', text: af.message ?? 'Autofocus failed.' };
    default:
      return { state: af.state, tone: 'idle', text: af.message ?? '' };
  }
}
