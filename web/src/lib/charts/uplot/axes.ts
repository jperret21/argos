/**
 * Axes from tokens: Plex Mono 10 px ticks (--text-2xs), --chart-text labels,
 * --chart-grid hairlines, --chart-axis border (BRAND 10). Promoted from
 * src/lab/charts/core/uplot/axes.ts.
 *
 * Time is always unix seconds on the x scale, whatever the axis shows, so a
 * zoom survives a UTC / JD / BJD switch and every facet of a group shares one
 * scale (D26). The UTC axis uses our own splits on round clock steps and names
 * the scale on its last tick ("21:30 UTC"). The JD and BJD axes put their
 * ticks on round fractions of a day, labelled as an offset from an integer
 * day `jd0` that the chart names in its axis title ("JD − 2461346"). BJD
 * positions use the BJD − JD offset of the middle of the view: it changes by
 * less than 0.4 s per hour (the Earth's orbital motion), well under a pixel,
 * and keeps the labels exactly round; the readouts give each point's own BJD.
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

export type TimeAxisMode = 'utc' | 'jd' | 'bjd';

/** Julian date of the unix epoch. */
export const JD_UNIX_EPOCH = 2440587.5;
const DAY = 86400;
/** Tick steps of the JD / BJD axes, days (0.0001 d = 8.6 s). */
const STEPS_D = [0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1];

/** The tick step (days) for a JD axis spanning `spanS` seconds over `widthPx`. */
export function jdStep(spanS: number, widthPx: number, pxPerTick = 90): number {
  const want = spanS / DAY / Math.max(1, widthPx / pxPerTick);
  return STEPS_D.find((s) => s >= want) ?? 1;
}

/** Decimals that print every multiple of `step` exactly (0.0005 -> 4, 0.025 -> 3, 0.02 -> 2, 1 -> 0). */
export function stepDigits(step: number): number {
  if (!(step > 0) || !Number.isFinite(step)) return 0;
  for (let d = 0; d < 10; d++) {
    const k = step * 10 ** d;
    if (Math.abs(k - Math.round(k)) < 1e-6 * Math.max(1, k)) return d;
  }
  return 10;
}

/**
 * Unix seconds of the round (B)JD values in [min, max]: where the JD / BJD
 * ticks go. `offsetS` is BJD − JD in seconds (0 for the JD axis). Integer
 * multiples of the step, so no rounding error accumulates along the axis.
 */
export function jdSplits(min: number, max: number, widthPx: number, offsetS = 0, pxPerTick = 90): number[] {
  if (!(max > min) || !Number.isFinite(min) || !Number.isFinite(max)) return [];
  const step = jdStep(max - min, widthPx, pxPerTick);
  const j0 = (min + offsetS) / DAY + JD_UNIX_EPOCH;
  const j1 = (max + offsetS) / DAY + JD_UNIX_EPOCH;
  const out: number[] = [];
  for (let k = Math.ceil(j0 / step - 1e-9); k * step <= j1 + 1e-12; k++) out.push((k * step - JD_UNIX_EPOCH) * DAY - offsetS);
  return out;
}

/** Labels of jdSplits: (B)JD − jd0, with the decimals of the step. */
export function jdLabels(splits: readonly number[], spanS: number, widthPx: number, jd0: number, offsetS = 0, pxPerTick = 90): string[] {
  const step = jdStep(spanS, widthPx, pxPerTick);
  const digits = stepDigits(step);
  return splits.map((t) => {
    const k = Math.round(((t + offsetS) / DAY + JD_UNIX_EPOCH) / step);
    const v = k * step - jd0;
    return (Math.abs(v) < step / 2 ? 0 : v).toFixed(digits);
  });
}

export interface TimeAxisOptions {
  /** False: ticks and grid only, no labels (upper facets of small multiples). */
  labels: boolean;
  size?: number;
  /**
   * Name the scale on the last UTC tick ("21:30 UTC", default). A chart that
   * names its time axis in a title line turns it off: the suffix of a tick at
   * the right edge would be cut.
   */
  suffix?: boolean;
  /** UTC (default), JD or BJD ticks; the scale stays unix seconds. */
  mode?: TimeAxisMode;
  /** Integer day subtracted from JD / BJD labels (named in the chart's axis title). */
  jd0?: number;
  /** BJD − JD in seconds near unix time t (BJD axis). */
  bjdOffsetS?: (t: number) => number;
}

/** The time axis of a mode: UTC clock ticks, or JD / BJD offsets from jd0. */
export function timeAxis(ink: ChartInks, o: TimeAxisOptions): uPlot.Axis {
  const mode = o.mode ?? 'utc';
  if (mode === 'utc') return utcAxis(ink, o);
  const offset = (u: uPlot) => {
    if (mode !== 'bjd' || !o.bjdOffsetS) return 0;
    const { min, max } = u.scales.x;
    return min == null || max == null ? 0 : o.bjdOffsetS((min + max) / 2);
  };
  return {
    ...utcAxis(ink, o),
    splits: (u) => {
      const { min, max } = u.scales.x;
      if (min == null || max == null) return [];
      return jdSplits(min, max, u.bbox.width / uPlot.pxRatio, offset(u));
    },
    values: (u, splits) => {
      if (!o.labels) return splits.map(() => '');
      const span = (u.scales.x.max ?? 0) - (u.scales.x.min ?? 0);
      return jdLabels(splits, span, u.bbox.width / uPlot.pxRatio, o.jd0 ?? 0, offset(u));
    },
  };
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
      const named = o.suffix !== false;
      return splits.map((v, i) => clockUtc(v, span < 600) + (named && i === splits.length - 1 ? ' UTC' : ''));
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
