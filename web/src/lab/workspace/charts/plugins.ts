/**
 * uPlot plugins for the workspace charts. Built on the research lab's
 * verified light-curve plugin (research/curve/plugins.ts: one Path2D per
 * kind, culled, clipped, no closePath on shared paths), with what the
 * workspace adds:
 *
 * - roleMarkers(): the same shape-coded markers with a size option (the
 *   Watch view draws 9 px markers for 2 m reading) and a static ring on the
 *   newest point (data is marked, never animated);
 * - periods(): a hatched time range (a rule that fired and is still true)
 *   and labelled event lines, drawn UNDER the series;
 * - envelope(): a filled band between two columns (the check star's
 *   trailing mean ± 1 sigma), under the series;
 * - hline(): a dashed reference line (baseline, threshold) with a label.
 *
 * Colours are resolved rgba strings passed as functions, read at draw time.
 */

import uPlot from 'uplot';

export type Shape = 'circle' | 'square' | 'triangle';

/** Canvas text is drawn in device pixels: scale a CSS font ("10px Mono") by the pixel ratio. */
export function deviceFont(font: string, dpr = uPlot.pxRatio): string {
  return font.replace(/^(\d+(?:\.\d+)?)px/, (_m, n: string) => `${Number(n) * dpr}px`);
}

function addShape(p: Path2D, shape: Shape, x: number, y: number, r: number): void {
  if (shape === 'circle') {
    p.moveTo(x + r, y);
    p.arc(x, y, r, 0, Math.PI * 2);
  } else if (shape === 'square') {
    const s = r * 0.886; // equal area
    p.rect(x - s, y - s, 2 * s, 2 * s);
  } else {
    const s = r * 1.347; // equal area, centroid on the point; no closePath (Chromium trap)
    p.moveTo(x, y - s);
    p.lineTo(x + s * 0.866, y + s * 0.5);
    p.lineTo(x - s * 0.866, y + s * 0.5);
  }
}

export interface RoleMarkerOptions {
  shape: Shape;
  color: () => string;
  errors?: () => ArrayLike<number> | null;
  errorAlpha?: () => number;
  /** Marker size in CSS px (default: 6 dense, 8 sparse; BRAND --chart-marker*). */
  size?: number;
  /** Ring on the newest point (colour), or null. */
  latest?: () => string | null;
  seriesIdx?: number;
}

export function roleMarkers(o: RoleMarkerOptions): uPlot.Plugin {
  const si = o.seriesIdx ?? 1;
  return {
    hooks: {
      draw: [
        (u) => {
          const xs = u.data[0];
          const ys = u.data[si];
          const n = xs.length;
          if (!n) return;
          const [i0, i1] = u.series[si].idxs ?? [0, n - 1];
          const dpr = uPlot.pxRatio;
          const size = (o.size ?? (i1 - i0 + 1 < 50 ? 8 : 6)) * dpr;
          const r = size / 2;
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          ctx.save();
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();
          const color = o.color();
          const errs = o.errors?.() ?? null;
          if (errs) {
            const bars = new Path2D();
            for (let i = i0; i <= i1; i++) {
              const y = ys[i];
              const e = errs[i];
              if (y == null || !(e > 0)) continue;
              const x = Math.round(u.valToPos(xs[i], 'x', true)) + 0.5;
              const ya = u.valToPos(y - e, 'y', true);
              const yb = u.valToPos(y + e, 'y', true);
              if (Math.abs(yb - ya) < size) continue;
              bars.moveTo(x, ya);
              bars.lineTo(x, yb);
            }
            ctx.globalAlpha = o.errorAlpha?.() ?? 0.55;
            ctx.strokeStyle = color;
            ctx.lineWidth = dpr;
            ctx.stroke(bars);
            ctx.globalAlpha = 1;
          }
          const pts = new Path2D();
          for (let i = i0; i <= i1; i++) {
            const y = ys[i];
            if (y == null) continue;
            addShape(pts, o.shape, u.valToPos(xs[i], 'x', true), u.valToPos(y, 'y', true), r);
          }
          ctx.fillStyle = color;
          ctx.fill(pts);
          const ring = o.latest?.() ?? null;
          const ly = ys[n - 1];
          if (ring && ly != null && i1 === n - 1) {
            ctx.strokeStyle = ring;
            ctx.lineWidth = 1.5 * dpr;
            ctx.beginPath();
            ctx.arc(u.valToPos(xs[n - 1], 'x', true), u.valToPos(ly, 'y', true), r + 3.5 * dpr, 0, Math.PI * 2);
            ctx.stroke();
          }
          ctx.restore();
        },
      ],
    },
  };
}

export interface PeriodOptions {
  /** Hatched ranges [from, to] in x units (to = Infinity: until the right edge). */
  ranges: () => readonly [number, number][];
  /** Vertical event lines with a short label at the top. */
  events: () => readonly { x: number; label: string }[];
  /** Vertical "now" line, or null. */
  now?: () => number | null;
  hatch: () => string;
  line: () => string;
  text: () => string;
  reference: () => string;
  font: () => string;
  /** Draw the event labels (only on the top facet of a wall). */
  labels?: boolean;
}

export function periods(o: PeriodOptions): uPlot.Plugin {
  return {
    hooks: {
      drawAxes: [
        (u) => {
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          const dpr = uPlot.pxRatio;
          ctx.save();
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();
          for (const [a, b] of o.ranges()) {
            const x0 = Math.max(left, u.valToPos(a, 'x', true));
            const x1 = Number.isFinite(b) ? Math.min(left + width, u.valToPos(b, 'x', true)) : left + width;
            if (x1 <= x0) continue;
            // 45° hatch: a texture of thin lines, quieter than a fill.
            ctx.save();
            ctx.beginPath();
            ctx.rect(x0, top, x1 - x0, height);
            ctx.clip();
            ctx.strokeStyle = o.hatch();
            ctx.lineWidth = dpr;
            const step = 7 * dpr;
            ctx.beginPath();
            for (let x = x0 - height; x < x1; x += step) {
              ctx.moveTo(x, top + height);
              ctx.lineTo(x + height, top);
            }
            ctx.stroke();
            ctx.restore();
          }
          const now = o.now?.() ?? null;
          if (now !== null) {
            const x = Math.round(u.valToPos(now, 'x', true)) + 0.5;
            if (x >= left && x <= left + width) {
              ctx.setLineDash([2 * dpr, 3 * dpr]);
              ctx.strokeStyle = o.reference();
              ctx.lineWidth = dpr;
              ctx.beginPath();
              ctx.moveTo(x, top);
              ctx.lineTo(x, top + height);
              ctx.stroke();
              ctx.setLineDash([]);
            }
          }
          for (const e of o.events()) {
            const x = Math.round(u.valToPos(e.x, 'x', true)) + 0.5;
            if (x < left || x > left + width) continue;
            ctx.strokeStyle = o.line();
            ctx.lineWidth = 1.5 * dpr;
            ctx.beginPath();
            ctx.moveTo(x, top);
            ctx.lineTo(x, top + height);
            ctx.stroke();
          }
          ctx.restore();
        },
      ],
      draw: [
        (u) => {
          if (!o.labels) return;
          const { ctx } = u;
          const { left, top, width } = u.bbox;
          const dpr = uPlot.pxRatio;
          ctx.save();
          ctx.font = deviceFont(o.font(), dpr);
          ctx.textBaseline = 'top';
          ctx.textAlign = 'left';
          for (const e of o.events()) {
            const x = u.valToPos(e.x, 'x', true);
            if (x < left || x > left + width) continue;
            const tw = ctx.measureText(e.label).width;
            // Label to the right of the line, flipped left near the edge.
            const flip = x + tw + 8 * dpr > left + width;
            ctx.textAlign = flip ? 'right' : 'left';
            ctx.fillStyle = o.text();
            ctx.fillText(e.label, flip ? x - 6 * dpr : x + 6 * dpr, top + 3 * dpr);
          }
          ctx.restore();
        },
      ],
    },
  };
}

export interface EnvelopeOptions {
  hi: () => ArrayLike<number>;
  lo: () => ArrayLike<number>;
  mean?: () => ArrayLike<number>;
  fill: () => string;
  meanStroke?: () => string;
}

export function envelope(o: EnvelopeOptions): uPlot.Plugin {
  return {
    hooks: {
      drawAxes: [
        (u) => {
          const xs = u.data[0];
          const hi = o.hi();
          const lo = o.lo();
          const n = Math.min(xs.length, hi.length);
          if (n < 2) return;
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          const dpr = uPlot.pxRatio;
          ctx.save();
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();
          ctx.beginPath();
          for (let i = 0; i < n; i++) ctx.lineTo(u.valToPos(xs[i], 'x', true), u.valToPos(hi[i], 'y', true));
          for (let i = n - 1; i >= 0; i--) ctx.lineTo(u.valToPos(xs[i], 'x', true), u.valToPos(lo[i], 'y', true));
          ctx.fillStyle = o.fill();
          ctx.fill();
          const mean = o.mean?.();
          if (mean && o.meanStroke) {
            ctx.setLineDash([4 * dpr, 3 * dpr]);
            ctx.strokeStyle = o.meanStroke();
            ctx.lineWidth = dpr;
            ctx.beginPath();
            for (let i = 0; i < n; i++) ctx.lineTo(u.valToPos(xs[i], 'x', true), u.valToPos(mean[i], 'y', true));
            ctx.stroke();
          }
          ctx.restore();
        },
      ],
    },
  };
}

export interface HLineOptions {
  lines: () => readonly { y: number; color: string; label?: string; dashed?: boolean }[];
  text: () => string;
  font: () => string;
}

export function hlines(o: HLineOptions): uPlot.Plugin {
  return {
    hooks: {
      drawAxes: [
        (u) => {
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          const dpr = uPlot.pxRatio;
          ctx.save();
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();
          for (const l of o.lines()) {
            const y = Math.round(u.valToPos(l.y, 'y', true)) + 0.5;
            ctx.setLineDash(l.dashed === false ? [] : [4 * dpr, 3 * dpr]);
            ctx.strokeStyle = l.color;
            ctx.lineWidth = dpr;
            ctx.beginPath();
            ctx.moveTo(left, y);
            ctx.lineTo(left + width, y);
            ctx.stroke();
          }
          ctx.restore();
        },
      ],
      draw: [
        (u) => {
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          const dpr = uPlot.pxRatio;
          ctx.save();
          ctx.font = deviceFont(o.font(), dpr);
          ctx.textBaseline = 'bottom';
          ctx.textAlign = 'right';
          const used: number[] = [];
          for (const l of o.lines()) {
            if (!l.label) continue;
            const y = u.valToPos(l.y, 'y', true);
            if (y < top || y > top + height) continue;
            // Two labels closer than a line of text: keep the first (the rule).
            if (used.some((v) => Math.abs(v - y) < 12 * dpr)) continue;
            used.push(y);
            ctx.fillStyle = o.text();
            ctx.fillText(l.label, left + width - 4 * dpr, y - 2 * dpr);
          }
          ctx.restore();
        },
      ],
    },
  };
}

/** SVG path of a role shape in a 20 x 20 box, for HTML legends (BRAND 6 / 10). */
export function shapePath(shape: Shape): string {
  if (shape === 'circle') return 'M10 5a5 5 0 1 0 0.001 0Z';
  if (shape === 'square') return 'M5.5 5.5h9v9h-9Z';
  return 'M10 3.8l6 10.4H4Z';
}
