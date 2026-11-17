/**
 * The Review plot wall's model (spec 07 §2.1 E6-E9, §2.4; README R1; PROPOSAL §6 W7): which
 * cells, in which order, how many columns, the numbers in each cell's header, the health
 * strip's lanes, the cell's "Copy data (TSV)" and the per-viewer layout. Pure (no DOM, no
 * uPlot): vitest drives it.
 *
 * - Cells: one per star of the filter shown (targets first, then the check stars, then one
 *   per comparison, in the server's order), then the Conditions cell (decision D6: one
 *   frame metric on the same time axis). Each star cell is one LightCurvePlot facet.
 * - Columns: 2; 3 when the rail is collapsed and the wall is at least 1200 px wide (07 E6).
 *   Rows fill the wall's height in whole rows of 200 px or more: six cells show at
 *   1440 × 900 with the rail open (07 §2.4), none is cut in half.
 * - Statistics in a cell's header: n, and for a comparison the vetting report's scatter and
 *   status word (photometry_quality.json, S57: the report of that filter), else the core's
 *   own estimator recomputed here (uncertainty.py `estimate_lightcurve_scatter`: robust
 *   second differences / √6, unsaturated finite points, at least 10); for the check star
 *   the mean of check − catalogue V and the same scatter against the median error.
 * - Health strip (lab P12): lanes on the wall's time axis: frames (coverage; a gap is
 *   max(2 × cadence, cadence + 60 s) without a light frame; missing FITS ticked), HFD
 *   (episodes of three frames or more above 1.5 × the session's median), comps (target
 *   points measured with fewer comparisons than the run's best frame, the tick as tall as
 *   the shortfall), flags (suspect, saturated, and the server's flight-recorder flags).
 */

import { FLAG_RECORDER, FLAG_SATURATED, FLAG_SUSPECT } from '../charts/uplot/markers';
import { magBaselineOf, baselineOf, type YMode } from '../charts/lightcurve/facets';
import { medianOf } from '../charts/lightcurve/trailing';
import type { LiveCurveStore, Role, StarCurve } from '../charts/lightcurve/store';
import { isoMs } from '../charts/lightcurve/readout';
import { loadPref, savePref } from '../app/prefs';
import type { MenuEntry } from '../components/menu';
import { qualityOf, seriesLabel, type CurveExtras, type QualityReport, type QualityStar } from './source';

// -- Cells ---------------------------------------------------------------------------------------

export type CellKind = Role | 'conditions';

export interface WallCell {
  /** Stable across filters: `${role}:${star}`, "conditions". */
  id: string;
  kind: CellKind;
  /** The curve drawn (the filter shown), null for Conditions. */
  key: string | null;
  /** Star name ("RR Lyr"), or the metric's name. */
  name: string;
  /** "Name [IR]" when two filters are loaded, else the name. */
  label: string;
  auid: string | null;
  filter: string | null;
  /** Points in the curve (0 for Conditions). */
  n: number;
}

export const CONDITIONS_ID = 'conditions';
const ROLE_ORDER: Record<Role, number> = { target: 0, check: 1, comparison: 2 };

/** A curve shown under a filter: of that filter, or one that names none (before S49). */
const inFilter = (s: StarCurve, filter: string | null) => !filter || s.filter === null || s.filter === filter;

/** The star a curve belongs to, across filters. */
export const starOf = (s: StarCurve) => s.starKey ?? (s.auid || s.name || s.key);

/**
 * The wall's cells in their default order: targets, checks, comparisons (each in the
 * server's order), then Conditions when there is any frame metric.
 */
export function defaultCells(store: LiveCurveStore, filter: string | null, opts: { filtersLoaded?: number; wheel?: readonly string[]; conditions?: boolean } = {}): WallCell[] {
  const stars = [...store.stars.values()].filter((s) => inFilter(s, filter) && s.n > 0);
  const order = new Map(stars.map((s, i) => [s, i]));
  stars.sort((a, b) => ROLE_ORDER[a.role] - ROLE_ORDER[b.role] || order.get(a)! - order.get(b)!);
  const seen = new Set<string>();
  const cells: WallCell[] = [];
  for (const s of stars) {
    let id = `${s.role}:${starOf(s)}`;
    // Two curves of one star in one filter (should not happen): keep both, distinct ids.
    for (let k = 2; seen.has(id); k++) id = `${s.role}:${starOf(s)}#${k}`;
    seen.add(id);
    cells.push({ id, kind: s.role, key: s.key, name: s.name, label: seriesLabel(s.name, s.filter, opts.filtersLoaded ?? 0, opts.wheel), auid: s.auid || null, filter: s.filter, n: s.n });
  }
  // Conditions beside the target (WF-B): in the first screen whatever the number of stars.
  if (opts.conditions !== false) {
    const after = cells.reduce((k, c, i) => (c.kind === 'target' ? i + 1 : k), 0);
    cells.splice(after, 0, { id: CONDITIONS_ID, kind: 'conditions', key: null, name: 'Conditions', label: 'Conditions', auid: null, filter: null, n: 0 });
  }
  return cells;
}

// -- Layout (per viewer) -------------------------------------------------------------------------

export type MetricId = 'hfd' | 'fwhm' | 'stars' | 'sky' | 'airmass' | 'ecc' | 'temp';

export interface WallLayout {
  /** Cell ids in the observer's order (cells not listed keep their default place after). */
  order: string[];
  hidden: string[];
  /** The Conditions cell's metric. */
  metric: MetricId;
}

export const WALL_PREF = 'argos.review.wall';
export const DEFAULT_LAYOUT: WallLayout = { order: [], hidden: [], metric: 'hfd' };
const METRIC_IDS: readonly MetricId[] = ['hfd', 'fwhm', 'stars', 'sky', 'airmass', 'ecc', 'temp'];
export const isMetric = (v: unknown): v is MetricId => typeof v === 'string' && (METRIC_IDS as readonly string[]).includes(v);

export function isWallLayout(v: unknown): v is WallLayout {
  if (typeof v !== 'object' || v === null) return false;
  const o = v as Record<string, unknown>;
  const strs = (a: unknown) => Array.isArray(a) && a.every((x) => typeof x === 'string');
  return strs(o.order) && strs(o.hidden) && isMetric(o.metric);
}

export function loadWallLayout(store?: Pick<Storage, 'getItem' | 'setItem'> | null): WallLayout {
  const l = store === undefined ? loadPref(WALL_PREF, isWallLayout, DEFAULT_LAYOUT) : loadPref(WALL_PREF, isWallLayout, DEFAULT_LAYOUT, store);
  return { order: [...l.order], hidden: [...l.hidden], metric: l.metric };
}

export function saveWallLayout(l: WallLayout, store?: Pick<Storage, 'getItem' | 'setItem'> | null): void {
  if (store === undefined) savePref(WALL_PREF, l);
  else savePref(WALL_PREF, l, store);
}

/**
 * The cells in the observer's order, without the hidden ones: the listed cells by the
 * observer's rank, then the cells the order does not name (a star new to this source, a cell
 * shown again) in their default order.
 */
export function arrange(cells: readonly WallCell[], layout: Pick<WallLayout, 'order' | 'hidden'>): { shown: WallCell[]; hidden: WallCell[] } {
  const rank = new Map(layout.order.map((id, i) => [id, i]));
  const listed = cells.filter((c) => rank.has(c.id)).sort((a, b) => rank.get(a.id)! - rank.get(b.id)!);
  const sorted = [...listed, ...cells.filter((c) => !rank.has(c.id))];
  const hide = new Set(layout.hidden);
  return { shown: sorted.filter((c) => !hide.has(c.id)), hidden: sorted.filter((c) => hide.has(c.id)) };
}

/** Move a cell one place earlier (-1) or later (+1) among the shown ones; returns the new order. */
export function moveCell(shown: readonly WallCell[], id: string, dir: -1 | 1): string[] {
  const ids = shown.map((c) => c.id);
  const i = ids.indexOf(id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= ids.length) return ids;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  return ids;
}

/**
 * A cell's menu (07 §2.4; README M86-M88): Copy data (TSV), Save as PNG, Expand / Restore,
 * Move earlier / later (disabled with the reason), Hide plot, Reset layout. `index` is the
 * cell's place among the `count` shown.
 */
export function cellMenu(c: Pick<WallCell, 'kind'>, index: number, count: number, expanded: boolean): MenuEntry[] {
  return [
    { id: 'copy', label: 'Copy data (TSV)', icon: 'copy', detail: c.kind === 'conditions' ? 'UTC and the metric, per light frame' : 'UTC, JD, BJD, plotted value, mag, errors, flags' },
    { id: 'png', label: 'Save as PNG', icon: 'export' },
    { kind: 'separator' },
    { id: 'expand', label: expanded ? 'Restore the wall' : 'Expand', icon: 'expand-pane' },
    { id: 'earlier', label: 'Move earlier', icon: 'move-up', disabledReason: expanded ? 'Restore the wall first' : index <= 0 ? 'Already the first plot' : null },
    { id: 'later', label: 'Move later', icon: 'move-down', disabledReason: expanded ? 'Restore the wall first' : index < 0 || index >= count - 1 ? 'Already the last plot' : null },
    { id: 'hide', label: 'Hide plot', icon: 'remove', detail: 'Show it again from Plots in the toolbar' },
    { kind: 'separator' },
    { id: 'reset', label: 'Reset layout', icon: 'layout-reset', detail: 'Every plot, default order, Conditions on HFD' },
  ];
}

/** The Conditions cell's metric picker. */
export function metricMenu(current: MetricId): MenuEntry[] {
  return [
    { kind: 'header', label: 'Frame metric' },
    ...METRIC_IDS.map((m) => ({
      id: m,
      kind: 'radio' as const,
      label: `${METRICS[m].label}${METRICS[m].unit ? ` (${METRICS[m].unit})` : ''}`,
      checked: current === m,
      detail: m === 'airmass' ? 'The FITS header AIRMASS (the mount’s) when the frames carry it, else the photometry CSV' : m === 'temp' ? 'The FITS header CCD-TEMP' : undefined,
    })),
  ];
}

/** Columns of the wall: 2; 3 with the rail collapsed and 1200 px or more (07 E6). */
export function wallColumns(widthPx: number, railOpen: boolean): 1 | 2 | 3 {
  if (widthPx < 560) return 1;
  return !railOpen && widthPx >= 1200 ? 3 : 2;
}

/** Row height: whole rows of at least `min` px filling `availPx` (no cell cut in half). */
export function rowHeight(availPx: number, min = 200, max = 420): number {
  if (!(availPx > 0)) return 270;
  const rows = Math.max(1, Math.floor(availPx / min));
  return Math.max(min, Math.min(max, Math.floor(availPx / rows)));
}

// -- Statistics ----------------------------------------------------------------------------------

/** Robust σ (1.4826 × MAD), the core's uncertainty.robust_sigma. */
export function robustSigma(values: readonly number[]): number {
  const v = values.filter((x) => Number.isFinite(x));
  if (!v.length) return 0;
  const med = medianOf(v, v.length);
  const dev = v.map((x) => Math.abs(x - med));
  return 1.4826 * medianOf(dev, dev.length);
}

/**
 * The core's estimate_lightcurve_scatter: points sorted by time, second differences
 * m[i-1] − 2 m[i] + m[i+1], robust σ / √6; null under 10 points.
 */
export function estimateScatter(jd: ArrayLike<number>, mag: ArrayLike<number>, n: number, keep: (i: number) => boolean = () => true): number | null {
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) if (Number.isFinite(jd[i]) && Number.isFinite(mag[i]) && keep(i)) pts.push([jd[i], mag[i]]);
  if (pts.length < 10) return null;
  pts.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const d: number[] = [];
  for (let i = 1; i < pts.length - 1; i++) d.push(pts[i - 1][1] - 2 * pts[i][1] + pts[i + 1][1]);
  return robustSigma(d) / Math.sqrt(6);
}

export interface CellStats {
  n: number;
  /** Points left out of the statistics (saturated). */
  saturated: number;
  suspect: number;
  /** Scatter (mag), the report's for a vetted comparison. */
  scatter: number | null;
  /** Where the scatter comes from. */
  scatterFrom: 'report' | 'estimate' | null;
  medianErr: number | null;
  /** Check: mean of check − catalogue (unsaturated); null without a catalogue magnitude. */
  meanOffset: number | null;
  /** Target: the magnitude range (unsaturated, not suspect). */
  lo: number | null;
  hi: number | null;
  /** Comparison: the vetting line (status word), null without a report. */
  vetting: QualityStar | null;
}

export function cellStats(s: StarCurve, report: QualityReport | null): CellStats {
  const c = s.cols;
  const n = c.n;
  let sat = 0;
  let sus = 0;
  let lo = Infinity;
  let hi = -Infinity;
  const errs: number[] = [];
  const offs: number[] = [];
  // The core's `formal_mag_err or mag_err` (quality.py): a zero formal error falls back too.
  const errOf = (i: number) => (Number.isFinite(c.formal[i]) && c.formal[i] !== 0 ? c.formal[i] : c.err[i]);
  // quality.py's valid points: unsaturated, finite time, magnitude and error.
  const keep = (i: number) => (c.flags[i] & FLAG_SATURATED) === 0 && Number.isFinite(errOf(i));
  for (let i = 0; i < n; i++) {
    if (c.flags[i] & FLAG_SATURATED) sat++;
    else if (c.flags[i] & FLAG_SUSPECT) sus++;
    if (!keep(i) || !Number.isFinite(c.mag[i]) || !Number.isFinite(c.jd[i])) continue;
    // The range leaves the suspect points out too (drawn hollow, never exported), and the
    // recorder's no-detection frames (drawn hollow): the cell's axis ranges on the same set.
    if (!(c.flags[i] & (FLAG_SUSPECT | FLAG_RECORDER))) {
      lo = Math.min(lo, c.mag[i]);
      hi = Math.max(hi, c.mag[i]);
    }
    errs.push(errOf(i));
    if (s.catalogue !== null) offs.push(c.mag[i] - s.catalogue);
  }
  const vetting = s.role === 'comparison' ? qualityOf(report, s) : null;
  const est = estimateScatter(c.jd, c.mag, n, keep);
  const fromReport = vetting && vetting.scatter_mag !== null;
  return {
    n,
    saturated: sat,
    suspect: sus,
    scatter: fromReport ? vetting!.scatter_mag : est,
    scatterFrom: fromReport ? 'report' : est !== null ? 'estimate' : null,
    medianErr: fromReport && vetting!.median_formal_error_mag !== null ? vetting!.median_formal_error_mag : errs.length ? medianOf(errs, errs.length) : null,
    meanOffset: s.role === 'check' && offs.length ? offs.reduce((a, b) => a + b, 0) / offs.length : null,
    lo: Number.isFinite(lo) ? lo : null,
    hi: Number.isFinite(hi) ? hi : null,
    vetting,
  };
}

// -- Frames: conditions and health -----------------------------------------------------------------

/** A frame as the wall needs it (from A68 `frames[]`, review/frames/frames.ts FrameRow). */
export interface WallFrame {
  /** Exposure start, unix s (session.json), null when unknown. */
  t: number | null;
  /** Mid-exposure, unix s, when known (the FITS header's DATE-OBS + EXPTIME / 2, A68). */
  mid?: number | null;
  exposure_s: number | null;
  light: boolean;
  missing: boolean;
  hfd: number | null;
  fwhm: number | null;
  star_count: number | null;
  sky_adu: number | null;
  eccentricity: number | null;
  ccd_temp: number | null;
  /** The header's AIRMASS when the server reads it (A68), else absent. */
  airmass?: number | null;
}

export interface MetricDef {
  id: MetricId;
  label: string;
  unit: string;
  digits: number;
  /** Up is better drawn inverted (airmass 1.0 at the top, as altitude). */
  invert?: boolean;
  minSpan: number;
}

export const METRICS: Record<MetricId, MetricDef> = {
  hfd: { id: 'hfd', label: 'HFD', unit: 'px', digits: 2, minSpan: 0.5 },
  fwhm: { id: 'fwhm', label: 'FWHM', unit: 'px', digits: 2, minSpan: 0.5 },
  stars: { id: 'stars', label: 'Stars', unit: 'detected', digits: 0, minSpan: 20 },
  sky: { id: 'sky', label: 'Sky', unit: 'ADU', digits: 0, minSpan: 20 },
  airmass: { id: 'airmass', label: 'Airmass', unit: '', digits: 3, invert: true, minSpan: 0.05 },
  ecc: { id: 'ecc', label: 'Eccentricity', unit: '', digits: 2, minSpan: 0.05 },
  temp: { id: 'temp', label: 'Sensor', unit: '°C', digits: 1, minSpan: 1 },
};

/** Mid-exposure time of a frame (the curves' points are dated there): the header's, else start + exposure / 2. */
export const midOf = (f: Pick<WallFrame, 't' | 'exposure_s' | 'mid'>): number | null => (typeof f.mid === 'number' && Number.isFinite(f.mid) ? f.mid : f.t === null ? null : f.t + (f.exposure_s ?? 0) / 2);

export interface MetricSeries {
  x: Float64Array;
  y: Float64Array;
  n: number;
  /** Where the values come from, said under the cell's title. */
  source: string;
  /** False when no value is known (the cell says why). */
  any: boolean;
}

/**
 * One metric over the session's light frames, at mid-exposure. Airmass: the FITS header's
 * AIRMASS when the server gives it; else the target curve's (the photometry CSV, computed
 * from the Settings site: wrong when that site was wrong, as on RR Lyr 2026-09-25), and the
 * source says so.
 */
export function metricSeries(frames: readonly WallFrame[], metric: MetricId, target: StarCurve | null): MetricSeries {
  if (metric === 'airmass') {
    const lights = frames.filter((f) => f.light && midOf(f) !== null && typeof f.airmass === 'number' && Number.isFinite(f.airmass));
    if (lights.length) {
      const n = lights.length;
      const x = new Float64Array(n);
      const y = new Float64Array(n);
      lights.sort((a, b) => midOf(a)! - midOf(b)!).forEach((f, i) => {
        x[i] = midOf(f)!;
        y[i] = f.airmass!;
      });
      return { x, y, n, source: 'FITS header AIRMASS', any: true };
    }
    if (target && target.n) {
      const c = target.cols;
      let any = false;
      for (let i = 0; i < c.n && !any; i++) any = Number.isFinite(c.airmass[i]);
      return { x: c.view('t'), y: c.view('airmass'), n: c.n, source: 'photometry CSV (from the Settings site)', any };
    }
    return { x: new Float64Array(0), y: new Float64Array(0), n: 0, source: '', any: false };
  }
  const pick: Record<Exclude<MetricId, 'airmass'>, (f: WallFrame) => number | null> = {
    hfd: (f) => f.hfd,
    fwhm: (f) => f.fwhm,
    stars: (f) => f.star_count,
    sky: (f) => f.sky_adu,
    ecc: (f) => f.eccentricity,
    temp: (f) => f.ccd_temp,
  };
  const get = pick[metric];
  const lights = frames.filter((f) => f.light && midOf(f) !== null).sort((a, b) => midOf(a)! - midOf(b)!);
  const n = lights.length;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  let any = false;
  lights.forEach((f, i) => {
    x[i] = midOf(f)!;
    const v = get(f);
    y[i] = typeof v === 'number' && Number.isFinite(v) ? v : NaN;
    if (Number.isFinite(y[i])) any = true;
  });
  return { x, y, n, source: metric === 'temp' ? 'FITS header CCD-TEMP, per light frame' : 'session.json, per light frame', any };
}

/** The interval after which no frame is a gap: max(2 × cadence, cadence + 60 s) (BRAND 10). */
export function gapLimit(times: readonly number[]): number {
  if (times.length < 2) return Infinity;
  const d: number[] = [];
  for (let i = 1; i < times.length; i++) d.push(times[i] - times[i - 1]);
  const cad = medianOf(d, d.length);
  return Number.isFinite(cad) ? Math.max(2 * cad, cad + 60) : Infinity;
}

export interface Episode {
  from: number;
  to: number;
}

export interface HealthLanes {
  /** Light-frame coverage runs (mid-exposure times), broken at gaps. */
  coverage: Episode[];
  gaps: Episode[];
  missing: number[];
  /** HFD above 1.5 × the session's median for three frames or more. */
  hfd: Episode[];
  hfdBase: number | null;
  /**
   * Target points measured with fewer comparisons than the run's best frame (the most
   * `comps_used` of the run), and how many fewer as a fraction of that most (the tick's height).
   */
  fewComps: number[];
  fewCompsDeficit: number[];
  /** The most comparisons a target point of the run used (0: unknown). */
  compsBest: number;
  ensemble: number;
  suspect: number[];
  saturated: number[];
  /** Target points the server flagged from the flight recorder (A69 `flags`: zp_outlier, low_snr). */
  flagged: number[];
  /** Those flags by code ("zp_outlier": 2). */
  flaggedBy: Record<string, number>;
  lights: number;
}

export function healthOf(frames: readonly WallFrame[], target: StarCurve | null, ensembleSize: number, factor = 1.5, targetExtras: CurveExtras | null = null): HealthLanes {
  const lights = frames.filter((f) => f.light && midOf(f) !== null).sort((a, b) => midOf(a)! - midOf(b)!);
  const t = lights.map((f) => midOf(f)!);
  const limit = gapLimit(t);
  const coverage: Episode[] = [];
  const gaps: Episode[] = [];
  let start = 0;
  for (let i = 1; i <= t.length; i++) {
    if (i === t.length || t[i] - t[i - 1] > limit) {
      if (t.length) coverage.push({ from: t[start], to: t[i - 1] });
      if (i < t.length) gaps.push({ from: t[i - 1], to: t[i] });
      start = i;
    }
  }
  const missing = lights.filter((f) => f.missing).map((f) => midOf(f)!);
  const hfds = lights.map((f) => (typeof f.hfd === 'number' && Number.isFinite(f.hfd) ? f.hfd : NaN));
  const base = medianOf(hfds, hfds.length);
  const hfd: Episode[] = [];
  if (Number.isFinite(base) && base > 0) {
    const thr = base * factor;
    let run = 0;
    let from = -1;
    for (let i = 0; i <= hfds.length; i++) {
      const over = i < hfds.length && hfds[i] > thr;
      if (over) {
        if (run === 0) from = i;
        run++;
      } else {
        if (run >= 3) hfd.push({ from: t[from], to: t[i - 1] });
        run = 0;
      }
    }
  }
  const fewComps: number[] = [];
  const fewCompsDeficit: number[] = [];
  const suspect: number[] = [];
  const saturated: number[] = [];
  let best = 0;
  if (target) {
    const c = target.cols;
    // The reference is the run's best frame, not the ensemble's size: a run whose target was
    // never measured with every comparison (RR Lyr 2026-09-25: 2-5 of 6) would fill the lane.
    for (let i = 0; i < c.n; i++) if (Number.isFinite(c.comps[i]) && c.comps[i] > best) best = c.comps[i];
    for (let i = 0; i < c.n; i++) {
      if (best > 0 && Number.isFinite(c.comps[i]) && c.comps[i] < best) {
        fewComps.push(c.t[i]);
        fewCompsDeficit.push((best - c.comps[i]) / best);
      }
      if (c.flags[i] & FLAG_SATURATED) saturated.push(c.t[i]);
      else if (c.flags[i] & FLAG_SUSPECT) suspect.push(c.t[i]);
    }
  }
  const flagged: number[] = [];
  const flaggedBy: Record<string, number> = {};
  if (targetExtras) {
    targetExtras.words.forEach((w, k) => {
      // "no_frame" is the frames lane's business (no light frame within 60 s).
      const codes = w.filter((c) => c !== 'no_frame');
      if (!codes.length) return;
      flagged.push(targetExtras.t[k]);
      for (const c of codes) flaggedBy[c] = (flaggedBy[c] ?? 0) + 1;
    });
  }
  return { coverage, gaps, missing, hfd, hfdBase: Number.isFinite(base) ? base : null, fewComps, fewCompsDeficit, compsBest: best, ensemble: ensembleSize, suspect, saturated, flagged, flaggedBy, lights: lights.length };
}

/** The x extent of the wall: every curve's points and every light frame (unix s). */
export function wallExtent(store: LiveCurveStore, filter: string | null, frames: readonly WallFrame[]): [number, number] | null {
  let a = Infinity;
  let b = -Infinity;
  for (const s of store.stars.values()) {
    if (!inFilter(s, filter) || !s.n) continue;
    a = Math.min(a, s.cols.t[0]);
    b = Math.max(b, s.cols.t[s.n - 1]);
  }
  for (const f of frames) {
    const m = f.light ? midOf(f) : null;
    if (m === null) continue;
    a = Math.min(a, m);
    b = Math.max(b, m);
  }
  return Number.isFinite(a) ? [a, b] : null;
}

// -- Copy data (TSV) -----------------------------------------------------------------------------

const full = (v: number) => (Number.isFinite(v) ? String(v) : '');
const flagCell = (f: number) => [f & FLAG_SUSPECT ? 'suspect' : '', f & FLAG_SATURATED ? 'saturated' : ''].filter(Boolean).join(',');

export const CELL_TSV_HEADER = ['utc', 'jd_utc', 'bjd_tdb', 'plotted', 'mag', 'mag_err', 'formal_mag_err', 'sigma_syst', 'relative_flux', 'relative_flux_err', 'airmass', 'comps_used', 'flags'] as const;

/**
 * One star cell's data, full precision (the numbers as the server sent them, the CSV's),
 * plus `plotted`: the value the cell draws (mag, check − V, Δ from the comparison's median,
 * or the relative flux).
 */
export function cellTsv(s: StarCurve, mode: YMode): { header: string[]; rows: string[][] } {
  const c = s.cols;
  let plotted: (i: number) => number;
  if (mode === 'flux') {
    const b = baselineOf(s);
    plotted = s.role === 'comparison' ? (i) => c.flux[i] / b - 1 : (i) => c.flux[i] / b;
  } else if (s.role === 'comparison') {
    const m = magBaselineOf(s);
    plotted = (i) => c.mag[i] - m;
  } else if (s.role === 'check' && s.catalogue !== null) {
    const cat = s.catalogue;
    plotted = (i) => c.mag[i] - cat;
  } else plotted = (i) => c.mag[i];
  const rows: string[][] = [];
  for (let i = 0; i < c.n; i++) {
    rows.push([isoMs(c.t[i]), String(c.jd[i]), full(c.bjd[i]), full(plotted(i)), full(c.mag[i]), full(c.err[i]), full(c.formal[i]), full(c.syst[i]), full(c.flux[i]), full(c.fluxErr[i]), full(c.airmass[i]), full(c.comps[i]), flagCell(c.flags[i])]);
  }
  return { header: [...CELL_TSV_HEADER], rows };
}

/** The Conditions cell's data: one row per light frame. */
export function metricTsv(series: MetricSeries, metric: MetricId): { header: string[]; rows: string[][] } {
  const def = METRICS[metric];
  const name = `${def.label.toLowerCase()}${def.unit ? `_${def.unit.replace('°', '').toLowerCase()}` : ''}`;
  const rows: string[][] = [];
  for (let i = 0; i < series.n; i++) rows.push([isoMs(series.x[i]), full(series.y[i])]);
  return { header: ['utc_mid_exposure', name], rows };
}
