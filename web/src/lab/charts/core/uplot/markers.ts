/**
 * Shape-coded markers and error bars for uPlot (BRAND 2.6, 10).
 *
 * - Role shapes: target circle, comparison square, check triangle, all of
 *   equal area so no role looks heavier; `dot` is a neutral sample (V-curve,
 *   conditions).
 * - Flags by shape, never by colour alone (spec 07 "Selection model"):
 *   suspect -> hollow outline of the role shape; saturated -> an x mark.
 * - One Path2D per kind (filled, hollow, crosses, error bars): one fill or
 *   stroke call whatever the point count; culled to the visible index range,
 *   clipped to the plot box. Never closePath() on a shared Path2D: it is
 *   quadratic in Chromium (stack-capabilities 3.1). The line dash uPlot
 *   leaves on the context is reset first.
 * - The newest point gets a static ring (a pulse would be motion that
 *   carries no information); a selected point gets a second ring.
 */

import uPlot from 'uplot';

export type Shape = 'circle' | 'square' | 'triangle' | 'dot';

export const FLAG_SUSPECT = 1;
export const FLAG_SATURATED = 2;

export interface MarkerOptions {
  seriesIdx: number;
  shape: Shape;
  color: () => string;
  errors?: () => ArrayLike<number> | null;
  showErrors?: () => boolean;
  errorAlpha?: () => number;
  /** FLAG_* bits per point. */
  flags?: () => ArrayLike<number> | null;
  /** Ring around the newest point (colour), or null. */
  latest?: () => string | null;
  /** Index of a selected point and its ring colour. */
  selected?: () => { idx: number; color: string } | null;
  /** Marker diameter in CSS px for `visible` points (BRAND: 8 sparse, 6 dense). */
  size?: (visible: number) => number;
  /** Optional per-point predicate: hollow when it returns true (e.g. "not in the fit"). */
  hollow?: (i: number) => boolean;
}

export const defaultSize = (visible: number) => (visible < 60 ? 8 : visible < 1500 ? 6 : 4);

export function addShape(p: Path2D, shape: Shape, x: number, y: number, r: number): void {
  if (shape === 'circle' || shape === 'dot') {
    p.moveTo(x + r, y);
    p.arc(x, y, r, 0, Math.PI * 2);
  } else if (shape === 'square') {
    const s = r * 0.886; // same area as the circle
    p.rect(x - s, y - s, 2 * s, 2 * s);
  } else {
    const s = r * 1.347; // same area, centroid on the point
    p.moveTo(x, y - s);
    p.lineTo(x + s * 0.866, y + s * 0.5);
    p.lineTo(x - s * 0.866, y + s * 0.5);
    p.lineTo(x, y - s); // explicit, instead of closePath()
  }
}

export function markers(o: MarkerOptions): uPlot.Plugin {
  const si = o.seriesIdx;
  const size = o.size ?? defaultSize;
  return {
    hooks: {
      draw: [
        (u) => {
          if (!u.series[si]?.show) return;
          const xs = u.data[0];
          const ys = u.data[si] as ArrayLike<number | null>;
          const n = xs.length;
          if (!n) return;
          const [i0, i1] = u.series[si].idxs ?? [0, n - 1];
          if (i1 < i0) return;
          const dpr = uPlot.pxRatio;
          const r = (size(i1 - i0 + 1) / 2) * dpr;
          const errs = o.showErrors?.() ? (o.errors?.() ?? null) : null;
          const flags = o.flags?.() ?? null;
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          const color = o.color();
          ctx.save();
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();

          if (errs) {
            const bars = new Path2D();
            const caps = i1 - i0 < 150;
            const cw = 2.5 * dpr;
            for (let i = i0; i <= i1; i++) {
              const y = ys[i];
              const e = errs[i];
              if (y == null || !(e > 0) || Number.isNaN(y)) continue;
              const x = Math.round(u.valToPos(xs[i], 'x', true)) + 0.5;
              const ya = u.valToPos(y - e, 'y', true);
              const yb = u.valToPos(y + e, 'y', true);
              if (Math.abs(yb - ya) < 2 * r + 2 * dpr) continue; // hidden by the marker anyway
              bars.moveTo(x, ya);
              bars.lineTo(x, yb);
              if (caps) {
                bars.moveTo(x - cw, Math.round(ya) + 0.5);
                bars.lineTo(x + cw, Math.round(ya) + 0.5);
                bars.moveTo(x - cw, Math.round(yb) + 0.5);
                bars.lineTo(x + cw, Math.round(yb) + 0.5);
              }
            }
            ctx.globalAlpha = o.errorAlpha?.() ?? 0.55;
            ctx.strokeStyle = color;
            ctx.lineWidth = dpr;
            ctx.stroke(bars);
            ctx.globalAlpha = 1;
          }

          const solid = new Path2D();
          const open = new Path2D();
          const cross = new Path2D();
          let nOpen = 0;
          let nCross = 0;
          for (let i = i0; i <= i1; i++) {
            const y = ys[i];
            if (y == null || Number.isNaN(y)) continue;
            const px = u.valToPos(xs[i], 'x', true);
            const py = u.valToPos(y, 'y', true);
            const f = flags ? flags[i] : 0;
            if (f & FLAG_SATURATED) {
              const k = r * 1.05;
              cross.moveTo(px - k, py - k);
              cross.lineTo(px + k, py + k);
              cross.moveTo(px - k, py + k);
              cross.lineTo(px + k, py - k);
              nCross++;
            } else if (f & FLAG_SUSPECT || o.hollow?.(i)) {
              addShape(open, o.shape, px, py, r * 1.05);
              nOpen++;
            } else addShape(solid, o.shape, px, py, r);
          }
          ctx.fillStyle = color;
          ctx.fill(solid);
          ctx.strokeStyle = color;
          if (nOpen) {
            ctx.lineWidth = 1.25 * dpr;
            ctx.stroke(open);
          }
          if (nCross) {
            ctx.lineWidth = 1.5 * dpr;
            ctx.lineCap = 'round';
            ctx.stroke(cross);
          }

          const ring = (i: number, c: string, extra: number) => {
            const y = ys[i];
            if (y == null || Number.isNaN(y) || i < i0 || i > i1) return;
            ctx.strokeStyle = c;
            ctx.lineWidth = 1.5 * dpr;
            ctx.beginPath();
            ctx.arc(u.valToPos(xs[i], 'x', true), u.valToPos(y, 'y', true), r + extra * dpr, 0, Math.PI * 2);
            ctx.stroke();
          };
          const latest = o.latest?.();
          if (latest) ring(n - 1, latest, 3.5);
          const sel = o.selected?.();
          if (sel) ring(sel.idx, sel.color, 5);
          ctx.restore();
        },
      ],
    },
  };
}

/** The same shapes as SVG paths on a 20-unit box, for HTML legends and tooltips. */
export function shapePath(shape: Shape): string {
  if (shape === 'circle' || shape === 'dot') return 'M15 10a5 5 0 1 1-10 0a5 5 0 1 1 10 0Z';
  if (shape === 'square') return 'M5.6 5.6h8.8v8.8H5.6Z';
  return 'M10 3.3l5.8 10.1H4.2Z';
}
