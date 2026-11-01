/**
 * Shared uPlot pieces for the workspace charts: token palette (resolved for
 * the canvas by the research lab's tokens.ts), axis styling, UTC time axis.
 *
 * Text in plots wears text tokens (--chart-text), never a series colour;
 * grid --chart-grid; axis line --chart-axis (BRAND 10). Fonts: Plex Mono
 * for ticks at --text-2xs (10 px), larger in Watch.
 */

import uPlot from 'uplot';
import { chartPalette, type ChartPalette } from '../../research/tokens';

export type { ChartPalette };
export { chartPalette };

export function utcLabel(t: number): string {
  const d = new Date(t * 1000);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

/** Ticks every 15 / 30 / 60 min on the clock, never at odd seconds. */
export function utcSplits(min: number, max: number, targetCount: number): number[] {
  const span = max - min;
  const steps = [300, 600, 900, 1800, 3600, 7200];
  const step = steps.find((s) => span / s <= targetCount) ?? 7200;
  const out: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max; t += step) out.push(t);
  return out;
}

export interface AxisStyle {
  font: number;
  /** Space reserved for tick labels on the y axis, CSS px. */
  ySize: number;
  gap?: number;
}

export function xAxis(pal: ChartPalette, s: AxisStyle, show = true): uPlot.Axis {
  return {
    show,
    stroke: pal.text,
    font: `${s.font}px ${pal.mono}`,
    size: show ? s.font + 12 : 0,
    gap: s.gap ?? 4,
    grid: { stroke: pal.grid, width: 1 },
    ticks: { stroke: pal.axis, width: 1, size: 4 },
    border: { show: true, stroke: pal.axis, width: 1 },
    splits: (u) => {
      const { min, max } = u.scales.x;
      if (min == null || max == null) return [];
      return utcSplits(min, max, Math.max(2, Math.floor(u.bbox.width / uPlot.pxRatio / 110)));
    },
    // The last tick names the scale (BRAND 10: time named).
    values: (_u, splits) => splits.map((t, i) => utcLabel(t) + (i === splits.length - 1 ? ' UTC' : '')),
  };
}

export function yAxis(pal: ChartPalette, s: AxisStyle, digits: number, ticks = 4): uPlot.Axis {
  return {
    stroke: pal.text,
    font: `${s.font}px ${pal.mono}`,
    size: s.ySize,
    gap: s.gap ?? 4,
    grid: { stroke: pal.grid, width: 1 },
    ticks: { stroke: pal.axis, width: 1, size: 4 },
    border: { show: true, stroke: pal.axis, width: 1 },
    splits: (u, axisIdx) => {
      const key = u.axes[axisIdx].scale ?? 'y';
      const { min, max } = u.scales[key];
      if (min == null || max == null || !(max > min)) return [];
      const raw = (max - min) / ticks;
      const mag = Math.pow(10, Math.floor(Math.log10(raw)));
      const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((k) => k >= raw) ?? raw;
      const out: number[] = [];
      for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
      return out;
    },
    values: (_u, splits) => splits.map((v) => (v < 0 ? '−' + Math.abs(v).toFixed(digits) : v.toFixed(digits))),
  };
}

/** Pad a [min, max] range by a fraction (never collapse to zero height). */
export function padRange(min: number, max: number, frac = 0.08, floor = 0.01): [number, number] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  const span = Math.max(max - min, floor);
  const mid = (max + min) / 2;
  return [mid - (span / 2) * (1 + 2 * frac), mid + (span / 2) * (1 + 2 * frac)];
}
