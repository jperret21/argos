/**
 * Canvas mini-charts for chips, rail rows and the glance view. No library:
 * a sparkline of 100-500 points costs a few microseconds
 * (stack-capabilities 4.2). Tokens are resolved by the caller (ChartInks),
 * so Night Red holds; the canvas is sized in CSS px and drawn at the
 * device ratio.
 *
 * Rules: values are drawn exactly (no smoothing, no easing); the newest
 * value is a dot; a reference (threshold, limit) is a dashed hairline; the
 * part of the line beyond a threshold is marked by a heavier stroke and a
 * rug, so the state never rests on colour alone.
 */

import type { ChartInks } from '../core/palette';

export interface SparkSpec {
  xs: ArrayLike<number>;
  ys: ArrayLike<number>;
  /** Number of valid points (prefix of xs / ys). */
  n: number;
  /** x window; default: the data extent. */
  x0?: number;
  x1?: number;
  /** y range; default: data extent padded 12 %. */
  y0?: number;
  y1?: number;
  /** Larger values drawn lower (magnitudes, airmass). */
  invert?: boolean;
  /** Dashed reference line (threshold, limit). */
  ref?: number;
  /** Values above `ref` are "out" (or below, with refBelow). */
  refBelow?: boolean;
  /** Mark the out-of-range part (heavier stroke + rug). */
  markOut?: boolean;
  /** Line colour. */
  color: string;
  /** Dot on the newest value. */
  lastDot?: boolean;
  /** Vertical now-line at this x. */
  now?: number;
  /** Draw points instead of a line (photometry). */
  dots?: boolean;
  /** Line width, CSS px. */
  width?: number;
  /** A filled area under the line down to the bottom (altitude). */
  area?: boolean;
}

export function sizeCanvas(c: HTMLCanvasElement, w: number, h: number): CanvasRenderingContext2D | null {
  const dpr = window.devicePixelRatio || 1;
  const W = Math.round(w * dpr);
  const H = Math.round(h * dpr);
  if (c.width !== W || c.height !== H) {
    c.width = W;
    c.height = H;
  }
  const ctx = c.getContext('2d');
  if (!ctx) return null;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return ctx;
}

export function drawSpark(ctx: CanvasRenderingContext2D, w: number, h: number, s: SparkSpec, ink: ChartInks): void {
  const n = s.n;
  if (n < 1) return;
  const pad = 2;
  let x0 = s.x0 ?? s.xs[0];
  let x1 = s.x1 ?? s.xs[n - 1];
  if (x1 <= x0) x1 = x0 + 1;
  let y0 = s.y0;
  let y1 = s.y1;
  if (y0 === undefined || y1 === undefined) {
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = 0; i < n; i++) {
      const x = s.xs[i];
      if (x < x0 || x > x1) continue;
      const v = s.ys[i];
      if (!Number.isFinite(v)) continue;
      lo = Math.min(lo, v);
      hi = Math.max(hi, v);
    }
    if (s.ref !== undefined) {
      lo = Math.min(lo, s.ref);
      hi = Math.max(hi, s.ref);
    }
    if (!Number.isFinite(lo)) return;
    const span = Math.max(hi - lo, Math.abs(hi) * 0.02, 1e-6);
    y0 ??= lo - span * 0.12;
    y1 ??= hi + span * 0.12;
  }
  const X = (x: number) => pad + ((x - x0) / (x1 - x0)) * (w - 2 * pad - (s.lastDot ? 3 : 0));
  const Y = (v: number) => {
    const f = (v - (y0 as number)) / ((y1 as number) - (y0 as number));
    return s.invert ? pad + f * (h - 2 * pad) : h - pad - f * (h - 2 * pad);
  };

  const out = (v: number) => s.ref !== undefined && (s.refBelow ? v < s.ref : v > s.ref);

  if (s.ref !== undefined) {
    const y = Math.round(Y(s.ref)) + 0.5;
    ctx.strokeStyle = ink.reference.a(0.8);
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (s.now !== undefined && s.now >= x0 && s.now <= x1) {
    const x = Math.round(X(s.now)) + 0.5;
    ctx.strokeStyle = ink.highlight.a(0.55);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }

  const lw = s.width ?? 1.25;
  if (s.dots) {
    ctx.fillStyle = s.color;
    for (let i = 0; i < n; i++) {
      const x = s.xs[i];
      const v = s.ys[i];
      if (x < x0 || x > x1 || !Number.isFinite(v)) continue;
      ctx.fillRect(X(x) - 1, Y(v) - 1, 2, 2);
    }
  } else {
    if (s.area) {
      ctx.beginPath();
      let started = false;
      let lastX = 0;
      for (let i = 0; i < n; i++) {
        const x = s.xs[i];
        const v = s.ys[i];
        if (x < x0 || x > x1 || !Number.isFinite(v)) continue;
        if (!started) {
          ctx.moveTo(X(x), h);
          started = true;
        }
        ctx.lineTo(X(x), Y(v));
        lastX = X(x);
      }
      ctx.lineTo(lastX, h);
      ctx.fillStyle = s.color.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, 'rgba($1,$2,$3,0.16)');
      ctx.fill();
    }
    ctx.strokeStyle = s.color;
    ctx.lineWidth = lw;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    let pen = false;
    for (let i = 0; i < n; i++) {
      const x = s.xs[i];
      const v = s.ys[i];
      if (x < x0 || x > x1 || !Number.isFinite(v)) {
        pen = false;
        continue;
      }
      if (pen) ctx.lineTo(X(x), Y(v));
      else ctx.moveTo(X(x), Y(v));
      pen = true;
    }
    ctx.stroke();
    if (s.markOut && s.ref !== undefined) {
      // The out-of-range stretches: a heavier stroke, and a rug at the bottom.
      ctx.lineWidth = lw + 1.25;
      ctx.beginPath();
      let prev: [number, number] | null = null;
      for (let i = 0; i < n; i++) {
        const x = s.xs[i];
        const v = s.ys[i];
        if (x < x0 || x > x1 || !Number.isFinite(v)) {
          prev = null;
          continue;
        }
        const p: [number, number] = [X(x), Y(v)];
        if (out(v)) {
          if (prev) {
            ctx.moveTo(prev[0], prev[1]);
            ctx.lineTo(p[0], p[1]);
          } else ctx.moveTo(p[0], p[1]);
          ctx.fillRect(p[0] - 0.5, h - 2, 1, 2);
        }
        prev = out(v) ? p : null;
      }
      ctx.stroke();
    }
  }
  if (s.lastDot) {
    let i = n - 1;
    while (i >= 0 && !Number.isFinite(s.ys[i])) i--;
    if (i >= 0 && s.xs[i] >= x0 && s.xs[i] <= x1) {
      ctx.fillStyle = s.color;
      ctx.beginPath();
      ctx.arc(X(s.xs[i]), Y(s.ys[i]), 2.25, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
