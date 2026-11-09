/**
 * Shape-coded markers for canvas plots (BRAND 2 principle 6, 10). Promoted
 * from src/lab/charts/core/uplot/markers.ts, merged with the research and
 * workspace light-curve plugins (src/lab/research/curve/plugins.ts,
 * src/lab/workspace/charts/plugins.ts; web/lab/PROPOSAL.md 3.2, wave 5).
 *
 * Role shapes: target circle, comparison square, check triangle, all of equal
 * area so no role looks heavier; `dot` is a neutral sample (V-curve,
 * conditions). Shapes are added to a shared Path2D (one fill or stroke call
 * whatever the point count); never closePath() on a shared Path2D, it is
 * quadratic in Chromium (lab/research/stack-capabilities 3.1: 9.2 s for
 * 50 000 triangles with it).
 *
 * The light-curve plugin (markers()):
 * - flags by shape, never by colour alone: suspect -> the hollow outline of
 *   the role shape; saturated -> an x in place of the marker;
 * - error bars in the series colour at --chart-error-opacity, capped while
 *   the view is sparse, skipped where the marker hides them;
 * - one Path2D per kind (bars, filled, hollow, crosses), culled to the
 *   visible index range, clipped to the plot box; the line dash uPlot leaves
 *   on the context is reset first;
 * - in a dense view (more points than half the plot's device pixels across),
 *   a filled marker whose centre falls on the device pixel of one already
 *   drawn is skipped: the same opaque shape at the same pixel adds nothing
 *   (50 000 points: the marker pass drops from about 21 to a few ms);
 * - the newest point wears a static ring (a pulse would be motion that
 *   carries no information); a selected point a second, wider one.
 */

import uPlot from 'uplot';

export type Shape = 'circle' | 'square' | 'triangle' | 'dot';

/** Flag bits of a light-curve point (lightcurve/columns.ts). */
export const FLAG_SUSPECT = 1;
export const FLAG_SATURATED = 2;

type PathLike = Pick<Path2D, 'moveTo' | 'lineTo' | 'arc' | 'rect'>;

export function addShape(p: PathLike, shape: Shape, x: number, y: number, r: number): void {
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

/** A vertical error bar with 3 px caps, snapped to the pixel grid (device px). */
export function addErrorBar(p: PathLike, x: number, yLo: number, yHi: number, cap: number): void {
  const xr = Math.round(x) + 0.5;
  p.moveTo(xr, yLo);
  p.lineTo(xr, yHi);
  p.moveTo(xr - cap, Math.round(yLo) + 0.5);
  p.lineTo(xr + cap, Math.round(yLo) + 0.5);
  p.moveTo(xr - cap, Math.round(yHi) + 0.5);
  p.lineTo(xr + cap, Math.round(yHi) + 0.5);
}

/** Marker diameter (CSS px) for `visible` points: --chart-marker-sparse 8, --chart-marker 6, 4 beyond 1 500. */
export const defaultSize = (visible: number): number => (visible < 60 ? 8 : visible < 1500 ? 6 : 4);

/** Error bars get caps below this many visible points. */
export const CAPS_BELOW = 150;

export interface MarkerOptions {
  seriesIdx: number;
  shape: Shape;
  /** Resolved colour (rgba) of the role. */
  color: () => string;
  /** Error column aligned with the series (± half-length), or null. */
  errors?: () => ArrayLike<number> | null;
  showErrors?: () => boolean;
  errorAlpha?: () => number;
  /** FLAG_* bits per point, aligned with the series. */
  flags?: () => ArrayLike<number> | null;
  /** Ring colour of the newest point, or null for none. */
  latest?: () => string | null;
  /** A selected point (index in the series) and its ring colour. */
  selected?: () => { idx: number; color: string } | null;
  /** Marker diameter in CSS px for `visible` points. */
  size?: (visible: number) => number;
  /**
   * A point beyond the y range is drawn as a caret on the edge it passed (a
   * fixed-scale facet: the check's ±rung), so it is never silently cut.
   */
  carets?: () => boolean;
}

/** What one draw would add to each path, without a canvas (the logic the tests check). */
export interface MarkerPlan {
  solid: number[];
  hollow: number[];
  cross: number[];
  bars: number[];
}

/**
 * Sort the visible points into the four kinds: finite y only; saturated wins
 * over suspect (a clipped value is the stronger warning); an error bar only
 * where it is longer than the marker (`minBar`, in y units).
 */
export function planMarkers(
  ys: ArrayLike<number | null>,
  i0: number,
  i1: number,
  flags: ArrayLike<number> | null,
  errs: ArrayLike<number> | null,
  minBar = 0,
): MarkerPlan {
  const plan: MarkerPlan = { solid: [], hollow: [], cross: [], bars: [] };
  for (let i = i0; i <= i1; i++) {
    const y = ys[i];
    if (y == null || !Number.isFinite(y)) continue;
    const f = flags ? flags[i] : 0;
    if (f & FLAG_SATURATED) plan.cross.push(i);
    else if (f & FLAG_SUSPECT) plan.hollow.push(i);
    else plan.solid.push(i);
    const e = errs ? errs[i] : NaN;
    if (e > 0 && 2 * e > minBar) plan.bars.push(i);
  }
  return plan;
}

/**
 * A device-pixel occupancy grid (one bit per pixel), reused between draws:
 * mark(x, y) is true the first time a pixel is marked.
 */
export class PixelGrid {
  private bits = new Uint32Array(0);
  private w = 0;
  private h = 0;
  private x0 = 0;
  private y0 = 0;

  reset(left: number, top: number, width: number, height: number): void {
    this.x0 = Math.floor(left);
    this.y0 = Math.floor(top);
    this.w = Math.ceil(width) + 2;
    this.h = Math.ceil(height) + 2;
    const words = Math.ceil((this.w * this.h) / 32);
    if (this.bits.length < words) this.bits = new Uint32Array(words);
    else this.bits.fill(0, 0, words);
  }

  mark(x: number, y: number): boolean {
    const cx = Math.round(x) - this.x0;
    const cy = Math.round(y) - this.y0;
    if (cx < 0 || cy < 0 || cx >= this.w || cy >= this.h) return true;
    const k = cy * this.w + cx;
    const bit = 1 << (k & 31);
    const word = k >>> 5;
    if (this.bits[word] & bit) return false;
    this.bits[word] |= bit;
    return true;
  }
}

export function markers(o: MarkerOptions): uPlot.Plugin {
  const si = o.seriesIdx;
  const size = o.size ?? defaultSize;
  const grid = new PixelGrid();
  return {
    hooks: {
      draw: [
        (u) => {
          const s = u.series[si];
          if (!s?.show) return;
          const xs = u.data[0];
          const ys = u.data[si] as ArrayLike<number | null>;
          const n = xs.length;
          if (!n) return;
          const [i0, i1] = s.idxs ?? [0, n - 1];
          if (i1 < i0) return;
          const dpr = uPlot.pxRatio;
          const r = (size(i1 - i0 + 1) / 2) * dpr;
          const errs = o.showErrors?.() === false ? null : (o.errors?.() ?? null);
          const flags = o.flags?.() ?? null;
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          const color = o.color();
          ctx.save();
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();

          const xAt = (i: number) => u.valToPos(xs[i], 'x', true);
          const yAt = (v: number) => u.valToPos(v, 'y', true);

          // Bars (and bands, elsewhere) stop at the plot box; the glyphs and rings below do not:
          // a point at the edge keeps its whole marker (the plot's margin holds its centre).
          if (errs) {
            const bars = new Path2D();
            const caps = i1 - i0 < CAPS_BELOW;
            const cw = 2.5 * dpr;
            let any = false;
            for (let i = i0; i <= i1; i++) {
              const y = ys[i];
              const e = errs[i];
              if (y == null || !Number.isFinite(y) || !(e > 0)) continue;
              const ya = yAt(y - e);
              const yb = yAt(y + e);
              if (Math.abs(yb - ya) < 2 * r + 2 * dpr) continue; // hidden by the marker anyway
              const x = Math.round(xAt(i)) + 0.5;
              bars.moveTo(x, ya);
              bars.lineTo(x, yb);
              if (caps) {
                bars.moveTo(x - cw, Math.round(ya) + 0.5);
                bars.lineTo(x + cw, Math.round(ya) + 0.5);
                bars.moveTo(x - cw, Math.round(yb) + 0.5);
                bars.lineTo(x + cw, Math.round(yb) + 0.5);
              }
              any = true;
            }
            if (any) {
              ctx.globalAlpha = o.errorAlpha?.() ?? 0.55;
              ctx.strokeStyle = color;
              ctx.lineWidth = dpr;
              ctx.stroke(bars);
              ctx.globalAlpha = 1;
            }
          }

          ctx.restore();
          ctx.save();
          ctx.setLineDash([]);
          ctx.beginPath();
          const spill = 12 * dpr;
          ctx.rect(left - spill, top - spill, width + 2 * spill, height + 2 * spill);
          ctx.clip();
          const solid = new Path2D();
          const open = new Path2D();
          const cross = new Path2D();
          const carets = new Path2D();
          let nOpen = 0;
          let nCross = 0;
          let nCaret = 0;
          const clamp = o.carets?.() ?? false;
          const dense = i1 - i0 + 1 > width / 2;
          if (dense) grid.reset(left, top, width, height);
          for (let i = i0; i <= i1; i++) {
            const y = ys[i];
            if (y == null || !Number.isFinite(y)) continue;
            const px = xAt(i);
            const py = yAt(y);
            if (clamp && (py < top || py > top + height)) {
              // A caret pointing out of the plot, on the edge the point passed.
              const up = py < top;
              const e = up ? top + 1 : top + height - 1;
              const k = 3.5 * dpr;
              carets.moveTo(px - k, up ? e + 1.6 * k : e - 1.6 * k);
              carets.lineTo(px, e);
              carets.lineTo(px + k, up ? e + 1.6 * k : e - 1.6 * k);
              nCaret++;
              continue;
            }
            const f = flags ? flags[i] : 0;
            if (f & FLAG_SATURATED) {
              const k = r * 1.05;
              cross.moveTo(px - k, py - k);
              cross.lineTo(px + k, py + k);
              cross.moveTo(px - k, py + k);
              cross.lineTo(px + k, py - k);
              nCross++;
            } else if (f & FLAG_SUSPECT) {
              addShape(open, o.shape, px, py, r * 1.05);
              nOpen++;
            } else if (!dense || grid.mark(px, py)) addShape(solid, o.shape, px, py, r);
          }
          ctx.fillStyle = color;
          ctx.fill(solid);
          if (nCaret) ctx.fill(carets);
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
            if (y == null || !Number.isFinite(y) || i < i0 || i > i1) return;
            ctx.strokeStyle = c;
            ctx.lineWidth = 1.5 * dpr;
            ctx.beginPath();
            ctx.arc(xAt(i), yAt(y), r + extra * dpr, 0, Math.PI * 2);
            ctx.stroke();
          };
          const latest = o.latest?.();
          if (latest) {
            // The newest point with a value (a ratio-only frame has no magnitude).
            let k = n - 1;
            while (k >= 0 && (ys[k] == null || !Number.isFinite(ys[k] as number))) k--;
            if (k >= 0) ring(k, latest, 3.5);
          }
          const sel = o.selected?.();
          if (sel) ring(sel.idx, sel.color, 5.5);
          ctx.restore();
        },
      ],
    },
  };
}

/** The role shapes as SVG paths on a 20-unit box, for HTML legends and readouts. */
export function shapePath(shape: Shape): string {
  if (shape === 'circle' || shape === 'dot') return 'M15 10a5 5 0 1 1-10 0a5 5 0 1 1 10 0Z';
  if (shape === 'square') return 'M5.6 5.6h8.8v8.8H5.6Z';
  return 'M10 3.3l5.8 10.1H4.2Z';
}
