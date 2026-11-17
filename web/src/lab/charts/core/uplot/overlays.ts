/**
 * Annotations drawn on a uPlot canvas: time spans (twilight, planned run,
 * an attention episode, a stale gap), vertical lines (now, meridian,
 * autofocus, the selected time) and horizontal references (minimum altitude,
 * a threshold, a baseline), each with an optional label in Plex Mono.
 *
 * - "under" items are drawn in drawClear (beneath the grid and the data),
 *   "over" items in draw (above the data).
 * - Labels sit on a --chart-surface box so they stay legible over a grid
 *   line, and are kept inside the plot box. Patterns (hatching) are drawn
 *   as explicit strokes: they tell two bands apart without hue, which is
 *   what Night Red needs (spec 06 2.3: outlined run band, hatched transit).
 * - Lines are snapped to the device pixel grid (crisp 1 px hairlines).
 */

import uPlot from 'uplot';
import type { ChartInks } from '../palette';

export interface Label {
  text: string;
  /** Where along the line / span. */
  at?: 'top' | 'bottom' | 'left' | 'right';
  color?: string;
  /** Pixel offset from the anchor (CSS px). */
  dy?: number;
  dx?: number;
}

export type Annotation =
  | {
      kind: 'vspan';
      from: number;
      to: number;
      fill?: string;
      hatch?: string;
      edge?: string;
      edgeDash?: number[];
      /** Stroke the whole rectangle (an outlined band, spec 06: the planned run). */
      outline?: string;
      /** Restrict the span vertically (fractions of the plot height from the top). */
      y0?: number;
      y1?: number;
      label?: Label;
      layer?: 'under' | 'over';
    }
  | { kind: 'vline'; x: number; color: string; width?: number; dash?: number[]; label?: Label; layer?: 'under' | 'over' }
  | { kind: 'hline'; y: number; scale?: string; color: string; width?: number; dash?: number[]; label?: Label; layer?: 'under' | 'over' }
  | { kind: 'hspan'; from: number; to: number; scale?: string; fill: string; layer?: 'under' | 'over' };

export function annotations(get: () => Annotation[], inks: () => ChartInks): uPlot.Plugin {
  const draw = (u: uPlot, layer: 'under' | 'over') => {
    const list = get();
    if (!list.length) return;
    const dpr = uPlot.pxRatio;
    const { ctx } = u;
    const { left, top, width, height } = u.bbox;
    const ink = inks();
    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top, width, height);
    ctx.clip();
    ctx.setLineDash([]);
    const labels: (() => void)[] = [];
    for (const a of list) {
      if ((a.layer ?? (a.kind === 'vspan' || a.kind === 'hspan' ? 'under' : 'over')) !== layer) continue;
      if (a.kind === 'vspan') {
        let x0 = u.valToPos(a.from, 'x', true);
        let x1 = u.valToPos(a.to, 'x', true);
        if (x1 < left || x0 > left + width) continue;
        x0 = Math.max(left - 2, x0);
        x1 = Math.min(left + width + 2, x1);
        const y0 = top + (a.y0 ?? 0) * height;
        const y1 = top + (a.y1 ?? 1) * height;
        if (a.fill) {
          ctx.fillStyle = a.fill;
          ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
        }
        if (a.hatch) {
          ctx.save();
          ctx.beginPath();
          ctx.rect(x0, y0, x1 - x0, y1 - y0);
          ctx.clip();
          ctx.strokeStyle = a.hatch;
          ctx.lineWidth = dpr;
          const step = 6 * dpr;
          ctx.beginPath();
          for (let x = x0 - (y1 - y0); x < x1; x += step) {
            ctx.moveTo(x, y1);
            ctx.lineTo(x + (y1 - y0), y0);
          }
          ctx.stroke();
          ctx.restore();
        }
        if (a.outline) {
          ctx.strokeStyle = a.outline;
          ctx.lineWidth = dpr;
          ctx.strokeRect(Math.round(x0) + 0.5, Math.round(y0) + 0.5, Math.round(x1 - x0) - 1, Math.round(y1 - y0) - 1);
        }
        if (a.edge) {
          ctx.strokeStyle = a.edge;
          ctx.lineWidth = dpr;
          ctx.setLineDash((a.edgeDash ?? []).map((d) => d * dpr));
          ctx.beginPath();
          const sx0 = Math.round(x0) + 0.5;
          const sx1 = Math.round(x1) - 0.5;
          ctx.moveTo(sx0, y1);
          ctx.lineTo(sx0, y0);
          ctx.moveTo(sx1, y0);
          ctx.lineTo(sx1, y1);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        if (a.label) {
          const L = a.label;
          const at = L.at ?? 'top';
          labels.push(() => label(ctx, ink, L, Math.max(left, x0) + 4 * dpr, at === 'bottom' ? y1 - 4 * dpr : y0 + 4 * dpr, at === 'bottom' ? 'bottom' : 'top', 'left', left, width));
        }
      } else if (a.kind === 'vline') {
        const x = Math.round(u.valToPos(a.x, 'x', true)) + 0.5;
        if (x < left - 1 || x > left + width + 1) continue;
        ctx.strokeStyle = a.color;
        ctx.lineWidth = (a.width ?? 1) * dpr;
        ctx.setLineDash((a.dash ?? []).map((d) => d * dpr));
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, top + height);
        ctx.stroke();
        ctx.setLineDash([]);
        if (a.label) {
          const L = a.label;
          const at = L.at ?? 'top';
          const flip = x > left + width * 0.82; // keep the label inside, on the free side
          labels.push(() =>
            label(ctx, ink, L, flip ? x - 4 * dpr : x + 4 * dpr, at === 'bottom' ? top + height - 4 * dpr : top + 4 * dpr, at === 'bottom' ? 'bottom' : 'top', flip ? 'right' : 'left', left, width),
          );
        }
      } else if (a.kind === 'hline') {
        const y = Math.round(u.valToPos(a.y, a.scale ?? 'y', true)) + 0.5;
        if (y < top - 1 || y > top + height + 1) continue;
        ctx.strokeStyle = a.color;
        ctx.lineWidth = (a.width ?? 1) * dpr;
        ctx.setLineDash((a.dash ?? []).map((d) => d * dpr));
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(left + width, y);
        ctx.stroke();
        ctx.setLineDash([]);
        if (a.label) {
          const L = a.label;
          const right = (L.at ?? 'right') === 'right';
          labels.push(() => label(ctx, ink, L, right ? left + width - 4 * dpr : left + 4 * dpr, y - 3 * dpr, 'bottom', right ? 'right' : 'left', left, width));
        }
      } else {
        const ya = u.valToPos(a.from, a.scale ?? 'y', true);
        const yb = u.valToPos(a.to, a.scale ?? 'y', true);
        ctx.fillStyle = a.fill;
        ctx.fillRect(left, Math.min(ya, yb), width, Math.abs(yb - ya));
      }
    }
    for (const l of labels) l();
    ctx.restore();
  };
  return {
    hooks: {
      drawClear: [(u) => draw(u, 'under')],
      draw: [(u) => draw(u, 'over')],
    },
  };
}

/** A mono label on a surface box; x / y are the anchor in canvas pixels. */
export function label(
  ctx: CanvasRenderingContext2D,
  ink: ChartInks,
  L: Label,
  x: number,
  y: number,
  base: 'top' | 'bottom',
  align: 'left' | 'right',
  left: number,
  width: number,
): void {
  const dpr = uPlot.pxRatio;
  ctx.font = `500 ${Math.round(10 * dpr)}px ${ink.mono}`;
  const w = ctx.measureText(L.text).width;
  const h = 14 * dpr;
  const pad = 3 * dpr;
  let bx = align === 'left' ? x : x - w - 2 * pad;
  bx = Math.max(left + dpr, Math.min(left + width - w - 2 * pad - dpr, bx));
  bx += (L.dx ?? 0) * dpr;
  const by = (base === 'top' ? y : y - h) + (L.dy ?? 0) * dpr;
  ctx.fillStyle = ink.surface.a(0.88);
  ctx.fillRect(bx, by, w + 2 * pad, h);
  ctx.fillStyle = L.color ?? ink.text.a();
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillText(L.text, bx + pad, by + h / 2 + 0.5 * dpr);
}
