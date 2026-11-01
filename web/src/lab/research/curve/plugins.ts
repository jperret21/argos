/**
 * uPlot plugins for light curves (BRAND 10):
 *
 * - markers(): shape-coded points (target circle, comparison square, check
 *   triangle) with vertical error bars at --chart-error-opacity, drawn as ONE
 *   Path2D per kind (one fill + one stroke call, whatever the point count),
 *   culled to the visible index range, clipped to the plot area.
 * - The latest point gets a static ring: new data is marked, never animated.
 * - linkX(): a drag-zoom on one facet sets the same time range on the
 *   others (cursor sync alone does not link scales).
 *
 * Series data: [x, y] with the error column passed to the plugin (not a
 * uPlot series, so the ±σ never affects auto-ranging or the legend).
 */

import uPlot from 'uplot';

export type Shape = 'circle' | 'square' | 'triangle';

export interface MarkerOptions {
  shape: Shape;
  /** Resolved colour (rgba) of the role. */
  color: () => string;
  /** Opacity of the error bars (--chart-error-opacity). */
  errorAlpha: () => number;
  /** Error column aligned with the series, or null. */
  errors: () => ArrayLike<number> | null;
  showErrors: () => boolean;
  /** Ring colour for the latest point, or null for none. */
  latest: () => string | null;
  seriesIdx?: number;
}

function addShape(p: Path2D, shape: Shape, x: number, y: number, r: number): void {
  if (shape === 'circle') {
    p.moveTo(x + r, y);
    p.arc(x, y, r, 0, Math.PI * 2);
  } else if (shape === 'square') {
    const s = r * 0.886; // same area as the circle
    p.rect(x - s, y - s, 2 * s, 2 * s);
  } else {
    const s = r * 1.347; // same area as the circle, centroid on the point
    // No closePath(): fill() closes each subpath anyway, and closePath on a
    // Path2D holding thousands of subpaths is slow in Chromium (measured:
    // 9.2 s for 50 000 triangles with it, see stack-capabilities.md).
    p.moveTo(x, y - s);
    p.lineTo(x + s * 0.866, y + s * 0.5);
    p.lineTo(x - s * 0.866, y + s * 0.5);
  }
}

export function markers(o: MarkerOptions): uPlot.Plugin {
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
          const visible = i1 - i0 + 1;
          const size = (visible < 50 ? 8 : 6) * dpr;
          const r = size / 2;
          const errs = o.showErrors() ? o.errors() : null;
          const { ctx } = u;
          const { left, top, width, height } = u.bbox;
          ctx.save();
          // uPlot leaves the last series' dash on the context (the band's mean line).
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();
          const color = o.color();
          if (errs) {
            const bars = new Path2D();
            for (let i = i0; i <= i1; i++) {
              const y = ys[i];
              const e = errs[i];
              if (y == null || !(e > 0)) continue;
              const x = Math.round(u.valToPos(xs[i], 'x', true)) + 0.5;
              const ya = u.valToPos(y - e, 'y', true);
              const yb = u.valToPos(y + e, 'y', true);
              if (Math.abs(yb - ya) < size) continue; // hidden by the marker anyway
              bars.moveTo(x, ya);
              bars.lineTo(x, yb);
            }
            ctx.globalAlpha = o.errorAlpha();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1 * dpr;
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
          const ring = o.latest();
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

/** Link the x range of a group of plots (drag-zoom on one zooms all). */
export function linkX(group: Set<uPlot>, onUser: (zoomed: boolean) => void): uPlot.Plugin {
  let busy = false;
  return {
    hooks: {
      setScale: [
        (u, key) => {
          if (key !== 'x' || busy) return;
          busy = true;
          const { min, max } = u.scales.x;
          for (const o of group) if (o !== u && min != null && max != null) o.setScale('x', { min, max });
          busy = false;
        },
      ],
      setSelect: [
        (u) => {
          if (u.select.width > 0) onUser(true);
        },
      ],
    },
  };
}

/** Same shape as an SVG for HTML legends (role glyphs, BRAND 6 / 10). */
export function shapeSvgPath(shape: Shape): string {
  if (shape === 'circle') return 'M10 5a5 5 0 1 0 0.001 0Z';
  if (shape === 'square') return 'M5.5 5.5h9v9h-9Z';
  return 'M10 3.8l6 10.4H4Z';
}

// -- Threshold annotation ---------------------------------------------------------

export interface ThresholdOptions {
  value: () => number;
  /** Dashed threshold line (--chart-reference). */
  line: () => string;
  /** Flagged points and the rug under them (--warning: a status, with a label). */
  mark: () => string;
  /** After each draw: the line's y in CSS px from the canvas top, and how many points are at or above it. */
  onDraw?: (u: uPlot, yCss: number, count: number) => void;
  seriesIdx?: number;
}

/**
 * A horizontal threshold on a uPlot chart: dashed line, a ring on every
 * point at or above it and a rug tick on the x axis, so a run of bad frames
 * is visible even when 50 000 points are on screen. The handle that moves
 * it is HTML (curve/handle.ts), positioned from onDraw.
 */
export function thresholdMarks(o: ThresholdOptions): uPlot.Plugin {
  const si = o.seriesIdx ?? 1;
  return {
    hooks: {
      draw: [
        (u) => {
          const xs = u.data[0];
          const ys = u.data[si];
          const n = xs.length;
          const v = o.value();
          const dpr = uPlot.pxRatio;
          const { left, top, width, height } = u.bbox;
          const y = u.valToPos(v, 'y', true);
          const { ctx } = u;
          ctx.save();
          ctx.beginPath();
          ctx.rect(left, top, width, height);
          ctx.clip();
          ctx.setLineDash([4 * dpr, 3 * dpr]);
          ctx.strokeStyle = o.line();
          ctx.lineWidth = dpr;
          ctx.beginPath();
          ctx.moveTo(left, Math.round(y) + 0.5);
          ctx.lineTo(left + width, Math.round(y) + 0.5);
          ctx.stroke();
          ctx.setLineDash([]);
          let count = 0;
          for (let i = 0; i < n; i++) if ((ys[i] ?? -Infinity) >= v) count++;
          const [i0, i1] = u.series[si].idxs ?? [0, n - 1];
          const rings = new Path2D();
          const rug = new Path2D();
          const r = 3.5 * dpr;
          for (let i = i0; i <= i1; i++) {
            const yi = ys[i];
            if (yi == null || yi < v) continue;
            const px = u.valToPos(xs[i], 'x', true);
            const py = u.valToPos(yi, 'y', true);
            rings.moveTo(px + r, py);
            rings.arc(px, py, r, 0, Math.PI * 2);
            const rx = Math.round(px) + 0.5;
            rug.moveTo(rx, top + height);
            rug.lineTo(rx, top + height - 6 * dpr);
          }
          ctx.strokeStyle = o.mark();
          ctx.lineWidth = 1.5 * dpr;
          ctx.stroke(rings);
          ctx.stroke(rug);
          ctx.restore();
          o.onDraw?.(u, y / dpr, count);
        },
      ],
    },
  };
}
