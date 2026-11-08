/**
 * Autofocus V-curve display fit: HFD(x) = a * sqrt(1 + ((x - c) / b)^2), a
 * hyperbola whose asymptotes are the two branches of the "V" (slopes +/- a/b)
 * and whose vertex (c, a) is the best focus. Weighted Levenberg-Marquardt on
 * (a, b, c), with the parameter covariance (J^T W J)^-1 scaled by the reduced
 * chi^2 when it exceeds 1, so the chart can show the uncertainty of the
 * vertex and an envelope of the curve. Promoted from src/lab/charts/core/fit.ts
 * (web/lab/PROPOSAL.md section 6, W3). No uPlot, no DOM: unit-tested in node.
 *
 * This is a DISPLAY model. The focuser is moved by the server's autofocus
 * worker (argos/workers/autofocus_worker.py: a parabola fitted on the V zone,
 * argos/core/imaging/focus.py fit_v_curve); the chart marks the worker's
 * decision, never this fit's vertex, as the chosen position (BRAND 10:
 * "provisional vs decided"). Without sample errors (the server sends none)
 * every weight is 1 and `unknownErrors` scales the covariance by the residual
 * variance (reduced chi^2 of unit weights), in both directions: max(1, chi2red)
 * would overstate the uncertainty tenfold for 0.1 px residuals.
 */

export interface Sample {
  x: number;
  y: number;
  /** 1 sigma of y. */
  s: number;
}

export interface HyperbolaFit {
  a: number;
  b: number;
  c: number;
  /** Covariance matrix of (a, b, c), row-major 3x3. */
  cov: number[];
  sigmaA: number;
  sigmaB: number;
  sigmaC: number;
  chi2red: number;
  /** Coefficient of determination (unweighted). */
  r2: number;
  iterations: number;
  converged: boolean;
}

export function hyperbola(x: number, a: number, b: number, c: number): number {
  const u = (x - c) / b;
  return a * Math.sqrt(1 + u * u);
}

/** Partial derivatives of the model with respect to (a, b, c). */
function gradient(x: number, a: number, b: number, c: number): [number, number, number] {
  const u = (x - c) / b;
  const r = Math.sqrt(1 + u * u);
  return [r, (-a * u * u) / (b * r), (-a * u) / (b * r)];
}

function solve3(m: number[], v: number[]): number[] | null {
  // Gaussian elimination with partial pivoting on a 3x3 system.
  const A = [m.slice(0, 3).concat(v[0]), m.slice(3, 6).concat(v[1]), m.slice(6, 9).concat(v[2])];
  for (let col = 0; col < 3; col++) {
    let p = col;
    for (let r = col + 1; r < 3; r++) if (Math.abs(A[r][col]) > Math.abs(A[p][col])) p = r;
    if (Math.abs(A[p][col]) < 1e-300) return null;
    [A[col], A[p]] = [A[p], A[col]];
    for (let r = col + 1; r < 3; r++) {
      const f = A[r][col] / A[col][col];
      for (let k = col; k < 4; k++) A[r][k] -= f * A[col][k];
    }
  }
  const out = [0, 0, 0];
  for (let r = 2; r >= 0; r--) {
    let s = A[r][3];
    for (let k = r + 1; k < 3; k++) s -= A[r][k] * out[k];
    out[r] = s / A[r][r];
  }
  return out;
}

function invert3(m: number[]): number[] | null {
  const cols = [0, 1, 2].map((i) => solve3(m, [i === 0 ? 1 : 0, i === 1 ? 1 : 0, i === 2 ? 1 : 0]));
  if (cols.some((c) => c === null)) return null;
  const c = cols as number[][];
  return [c[0][0], c[1][0], c[2][0], c[0][1], c[1][1], c[2][1], c[0][2], c[1][2], c[2][2]];
}

export interface FitOptions {
  maxIter?: number;
  /**
   * The samples carry no measured error (`s` is a placeholder, e.g. 1): the
   * covariance is then scaled by the reduced chi^2 itself, i.e. by the
   * residual variance, in both directions. With known errors (default) it is
   * scaled by max(1, chi2red): never tighter than the stated errors.
   */
  unknownErrors?: boolean;
}

export function fitHyperbola(samples: readonly Sample[], options: number | FitOptions = {}): HyperbolaFit | null {
  const maxIter = typeof options === 'number' ? options : (options.maxIter ?? 60);
  const unknownErrors = typeof options === 'number' ? false : (options.unknownErrors ?? false);
  const n = samples.length;
  if (n < 4) return null;
  // Start: vertex at the lowest sample, a = its HFD, b from the steepest branch.
  let lo = samples[0];
  for (const s of samples) if (s.y < lo.y) lo = s;
  let slope = 0;
  for (const s of samples) if (s.x !== lo.x) slope = Math.max(slope, Math.abs(s.y - lo.y) / Math.abs(s.x - lo.x));
  let a = Math.max(0.1, lo.y);
  let b = slope > 0 ? a / slope : 100;
  let c = lo.x;
  let lambda = 1e-3;
  const chi2 = (pa: number, pb: number, pc: number) => {
    let s = 0;
    for (const p of samples) {
      const r = (p.y - hyperbola(p.x, pa, pb, pc)) / p.s;
      s += r * r;
    }
    return s;
  };
  let cur = chi2(a, b, c);
  let converged = false;
  let it = 0;
  for (; it < maxIter; it++) {
    const JTJ = new Array(9).fill(0);
    const JTr = [0, 0, 0];
    for (const p of samples) {
      const g = gradient(p.x, a, b, c);
      const w = 1 / (p.s * p.s);
      const r = p.y - hyperbola(p.x, a, b, c);
      for (let i = 0; i < 3; i++) {
        JTr[i] += w * g[i] * r;
        for (let j = 0; j < 3; j++) JTJ[i * 3 + j] += w * g[i] * g[j];
      }
    }
    let improved = false;
    for (let k = 0; k < 12; k++) {
      const M = JTJ.slice();
      for (let i = 0; i < 3; i++) M[i * 4] *= 1 + lambda;
      const d = solve3(M, JTr);
      if (!d) break;
      const na = a + d[0];
      const nb = b + d[1];
      const nc = c + d[2];
      if (!(na > 0) || !(Math.abs(nb) > 1e-6)) {
        lambda *= 10;
        continue;
      }
      const next = chi2(na, nb, nc);
      if (next < cur) {
        const rel = (cur - next) / Math.max(cur, 1e-12);
        a = na;
        b = Math.abs(nb);
        c = nc;
        cur = next;
        lambda = Math.max(lambda / 10, 1e-9);
        improved = true;
        if (rel < 1e-9) converged = true;
        break;
      }
      lambda *= 10;
    }
    if (!improved) {
      converged = true;
      break;
    }
    if (converged) break;
  }
  // Covariance at the solution.
  const JTJ = new Array(9).fill(0);
  let ssTot = 0;
  let ssRes = 0;
  let mean = 0;
  for (const p of samples) mean += p.y / n;
  for (const p of samples) {
    const g = gradient(p.x, a, b, c);
    const w = 1 / (p.s * p.s);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) JTJ[i * 3 + j] += w * g[i] * g[j];
    ssTot += (p.y - mean) ** 2;
    ssRes += (p.y - hyperbola(p.x, a, b, c)) ** 2;
  }
  const inv = invert3(JTJ);
  if (!inv) return null;
  const dof = Math.max(1, n - 3);
  const chi2red = cur / dof;
  const scale = unknownErrors ? chi2red : Math.max(1, chi2red);
  const cov = inv.map((v) => v * scale);
  return {
    a,
    b,
    c,
    cov,
    sigmaA: Math.sqrt(Math.max(0, cov[0])),
    sigmaB: Math.sqrt(Math.max(0, cov[4])),
    sigmaC: Math.sqrt(Math.max(0, cov[8])),
    chi2red,
    r2: ssTot > 0 ? 1 - ssRes / ssTot : 0,
    iterations: it,
    converged,
  };
}

/** 1 sigma of the fitted curve at x (delta method on the covariance). */
export function curveSigma(f: HyperbolaFit, x: number): number {
  const g = gradient(x, f.a, f.b, f.c);
  let v = 0;
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) v += g[i] * f.cov[i * 3 + j] * g[j];
  return Math.sqrt(Math.max(0, v));
}

export interface Verdict {
  accepted: boolean;
  reason: string;
}

/**
 * The lab's acceptance rules for the display fit: a converged fit, a vertex
 * inside the sampled range, a real V (HFD span of at least 15 %, the worker's
 * MIN_RELATIVE_SPAN) and a vertex known to better than a quarter of the step.
 * Used only to word the state of the display fit while no verdict exists;
 * the verdict that moves the focuser is the server's.
 */
export function judge(f: HyperbolaFit | null, samples: readonly Sample[], step: number): Verdict {
  if (samples.length < 4) return { accepted: false, reason: 'Too few samples to fit' };
  let lo = Infinity;
  let hi = -Infinity;
  let ymin = Infinity;
  let ymax = -Infinity;
  for (const s of samples) {
    lo = Math.min(lo, s.x);
    hi = Math.max(hi, s.x);
    ymin = Math.min(ymin, s.y);
    ymax = Math.max(ymax, s.y);
  }
  const span = (ymax - ymin) / ymin;
  if (span < 0.15) return { accepted: false, reason: `Flat HFD curve (${ymin.toFixed(1)}–${ymax.toFixed(1)} px, span ${Math.round(span * 100)} % < 15 %)` };
  if (!f) return { accepted: false, reason: 'Fit failed (singular)' };
  if (!f.converged) return { accepted: false, reason: 'Fit did not converge' };
  if (f.c < lo || f.c > hi) return { accepted: false, reason: 'Best focus outside the sweep' };
  if (f.sigmaC > step / 4) return { accepted: false, reason: `Position uncertain (± ${Math.round(f.sigmaC)} steps)` };
  return { accepted: true, reason: 'Hyperbola fit accepted' };
}
