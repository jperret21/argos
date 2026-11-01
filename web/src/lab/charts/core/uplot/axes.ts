/**
 * Axes from tokens: Plex Mono 10 px ticks (--text-2xs), --chart-text labels,
 * --chart-grid hairlines, --chart-axis border (BRAND 10).
 *
 * Time is always unix seconds on the x scale, whatever the axis shows, so
 * the zoom survives a UTC / JD / BJD switch and every chart of a group
 * shares one scale. UTC uses uPlot's time ticks in Etc/UTC; JD and BJD use
 * our own splits at round fractions of a day, labelled as an offset from the
 * night's integer JD (named in the axis title: "JD − 2461346"). A night never
 * crosses an integer JD (it changes at 12:00 UTC).
 */

import uPlot from 'uplot';
import { clockUtc } from '../format';
import type { ChartInks } from '../palette';
import { JD_UNIX_EPOCH } from '../../sim/astro';

export type TimeAxisMode = 'utc' | 'jd' | 'bjd';

export interface TimeAxisOptions {
  mode: TimeAxisMode;
  /** Integer part subtracted from JD / BJD tick labels. */
  jd0: number;
  /** BJD - JD in seconds near unix time t (BJD mode). */
  bjdOffsetS?: (t: number) => number;
  /** False: ticks and grid only, no labels (upper facets of a wall). */
  labels: boolean;
  size?: number;
}

const DAY = 86400;
const STEPS_D = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1];

export const utcTz = (ts: number) => uPlot.tzDate(new Date(ts * 1e3), 'Etc/UTC');

export function timeAxis(ink: ChartInks, o: TimeAxisOptions): uPlot.Axis {
  const font = `400 10px ${ink.mono}`;
  const base: uPlot.Axis = {
    stroke: ink.text.a(),
    font,
    size: o.labels ? (o.size ?? 24) : 2,
    gap: 3,
    space: o.mode === 'utc' ? 64 : 76,
    ticks: { stroke: ink.axis.a(), width: 1, size: o.labels ? 3 : 0 },
    grid: { stroke: ink.grid.a(), width: 1 },
    border: { show: true, stroke: ink.axis.a(), width: 1 },
  };
  if (o.mode === 'utc') {
    return {
      ...base,
      values: (u, splits) => {
        if (!o.labels) return splits.map(() => '');
        const span = (u.scales.x.max ?? 0) - (u.scales.x.min ?? 0);
        return splits.map((v) => clockUtc(v, span < 900));
      },
    };
  }
  const offsetDays = (t: number) => (o.mode === 'bjd' ? (o.bjdOffsetS?.(t) ?? 0) / DAY : 0);
  return {
    ...base,
    splits: (u, _axisIdx, min, max) => {
      const mid = (min + max) / 2;
      const off = offsetDays(mid);
      const j0 = min / DAY + JD_UNIX_EPOCH + off;
      const j1 = max / DAY + JD_UNIX_EPOCH + off;
      const px = u.bbox.width / uPlot.pxRatio || 400;
      const want = (j1 - j0) / Math.max(1, px / 90);
      const step = STEPS_D.find((s) => s >= want) ?? 1;
      const out: number[] = [];
      for (let j = Math.ceil(j0 / step) * step; j <= j1 + 1e-12; j += step) out.push((j - JD_UNIX_EPOCH - off) * DAY);
      return out;
    },
    values: (u, splits) => {
      if (!o.labels) return splits.map(() => '');
      const span = ((u.scales.x.max ?? 0) - (u.scales.x.min ?? 0)) / DAY;
      const digits = span < 0.02 ? 4 : span < 0.2 ? 3 : 2;
      return splits.map((t) => (t / DAY + JD_UNIX_EPOCH + offsetDays(t) - o.jd0).toFixed(digits));
    },
  };
}

export interface ValueAxisOptions {
  format: (v: number) => string;
  size?: number;
  space?: number;
  side?: 1 | 3;
  splits?: uPlot.Axis.Splits;
  /** Hide the labels (sparkline-like facets). */
  labels?: boolean;
}

export function valueAxis(ink: ChartInks, o: ValueAxisOptions): uPlot.Axis {
  return {
    stroke: ink.text.a(),
    font: `400 10px ${ink.mono}`,
    size: o.size ?? 48,
    gap: 5,
    space: o.space ?? 26,
    side: o.side ?? 3,
    ticks: { show: false },
    grid: { stroke: ink.grid.a(), width: 1 },
    splits: o.splits,
    values: (_u, splits) => splits.map((v) => (o.labels === false || v == null ? '' : o.format(v))),
  };
}

/** A y range with padding and a minimum span (so noise is never blown up). */
export function paddedRange(minSpan: number, pad = 0.1, include?: () => number[]): uPlot.Range.Function {
  return (_u, min, max) => {
    if (min == null || max == null || !Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
    for (const v of include?.() ?? []) {
      if (Number.isFinite(v)) {
        min = Math.min(min, v);
        max = Math.max(max, v);
      }
    }
    let span = max - min;
    if (span < minSpan) {
      const mid = (min + max) / 2;
      min = mid - minSpan / 2;
      max = mid + minSpan / 2;
      span = minSpan;
    }
    return [min - span * pad, max + span * pad];
  };
}
