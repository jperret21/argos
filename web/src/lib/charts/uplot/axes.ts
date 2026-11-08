/**
 * Axes from tokens: Plex Mono 10 px ticks (--text-2xs), --chart-text labels,
 * --chart-grid hairlines, --chart-axis border (BRAND 10). Promoted from
 * src/lab/charts/core/uplot/axes.ts (the UTC axis; the JD / BJD axes come
 * with the light curve, wave 5).
 *
 * Time is unix seconds on the x scale. The UTC axis uses our own splits on
 * round clock steps and names the scale on its last tick ("21:30 UTC").
 */

import uPlot from 'uplot';
import { clockUtc } from '../../format/time';
import type { ChartInks } from '../ink';

/** Clock steps for UTC ticks, seconds. */
const STEPS_S = [10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600];

/** Splits on round UTC clock times, about one per `pxPerTick` of width. */
export function utcSplits(min: number, max: number, widthPx: number, pxPerTick = 90): number[] {
  if (!(max > min) || !Number.isFinite(min) || !Number.isFinite(max)) return [];
  const want = (max - min) / Math.max(1, widthPx / pxPerTick);
  const step = STEPS_S.find((s) => s >= want) ?? STEPS_S[STEPS_S.length - 1];
  const out: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) out.push(t);
  return out;
}

export interface TimeAxisOptions {
  /** False: ticks and grid only, no labels (upper facets of small multiples). */
  labels: boolean;
  size?: number;
}

export function utcAxis(ink: ChartInks, o: TimeAxisOptions): uPlot.Axis {
  return {
    stroke: ink.text.a(),
    font: `400 10px ${ink.mono}`,
    size: o.labels ? (o.size ?? 22) : 2,
    gap: 3,
    ticks: { stroke: ink.axis.a(), width: 1, size: o.labels ? 3 : 0 },
    grid: { stroke: ink.grid.a(), width: 1 },
    border: { show: true, stroke: ink.axis.a(), width: 1 },
    splits: (u) => {
      const { min, max } = u.scales.x;
      if (min == null || max == null) return [];
      return utcSplits(min, max, u.bbox.width / uPlot.pxRatio);
    },
    values: (u, splits) => {
      if (!o.labels) return splits.map(() => '');
      const span = (u.scales.x.max ?? 0) - (u.scales.x.min ?? 0);
      // The last tick names the scale (BRAND 10: time named).
      return splits.map((v, i) => clockUtc(v, span < 600) + (i === splits.length - 1 ? ' UTC' : ''));
    },
  };
}

export interface ValueAxisOptions {
  format: (v: number) => string;
  size?: number;
  space?: number;
  side?: 1 | 3;
  splits?: uPlot.Axis.Splits;
  /** Hide the labels. */
  labels?: boolean;
  /** Axis title (unit), drawn in mono beside the ticks. */
  label?: string;
}

export function valueAxis(ink: ChartInks, o: ValueAxisOptions): uPlot.Axis {
  return {
    stroke: ink.text.a(),
    font: `400 10px ${ink.mono}`,
    size: o.size ?? 44,
    gap: 5,
    space: o.space ?? 26,
    side: o.side ?? 3,
    ticks: { show: false },
    grid: { stroke: ink.grid.a(), width: 1 },
    splits: o.splits,
    values: (_u, splits) => splits.map((v) => (o.labels === false || v == null ? '' : o.format(v))),
    ...(o.label ? { label: o.label, labelSize: 14, labelFont: `400 10px ${ink.mono}`, labelGap: 2 } : {}),
  };
}

/** A y range with padding and a minimum span (noise is never blown up to full height). */
export function paddedRange(minSpan: number, pad = 0.1, include?: () => readonly number[]): uPlot.Range.Function {
  return (_u, min, max) => padRange(min, max, minSpan, pad, include?.() ?? []);
}

/** The pure part of paddedRange (tested). */
export function padRange(
  min: number | null,
  max: number | null,
  minSpan: number,
  pad = 0.1,
  include: readonly number[] = [],
): [number, number] {
  let lo = min ?? NaN;
  let hi = max ?? NaN;
  for (const v of include) {
    if (!Number.isFinite(v)) continue;
    lo = Number.isFinite(lo) ? Math.min(lo, v) : v;
    hi = Number.isFinite(hi) ? Math.max(hi, v) : v;
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  let span = hi - lo;
  if (span < minSpan) {
    const mid = (lo + hi) / 2;
    lo = mid - minSpan / 2;
    hi = mid + minSpan / 2;
    span = minSpan;
  }
  return [lo - span * pad, hi + span * pad];
}
