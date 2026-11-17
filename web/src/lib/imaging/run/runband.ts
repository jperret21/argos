/**
 * Observe Run mode, the pure part (wave 6b; web/lab/PROPOSAL.md 3.1, 3.2 and 6, W6 rows;
 * BRAND 10 and 11.1): which attention rules the live curve draws, the thresholds the run's
 * sparklines draw, the time window of the mini charts, the layout of the mini column, the
 * band's one-row summary, and when to propose Run mode (never switch to it, D1).
 *
 * The rules run on the server (argos/server/protocol.md "Night (wave 6b)"); the band only
 * draws them, read-only, with "Change rule…" to Settings › Alerts (PROPOSAL 3.2). A drawn
 * threshold is the server's own number when its item carries one (`values.threshold`), else
 * factor × the server's baseline for the run (AttentionState.baselines: carried from an earlier
 * run of the server session, the HFD's for the same object and filter, the star count's for the
 * same object, filter, exposure and gain, or the run's own first B subs; protocol "Baselines
 * carried over runs"), else the rule's definition applied to the run's subs: factor ×
 * the median of the first B Light subs (alerts.hfd_factor, alerts.star_factor,
 * alerts.baseline_frames; protocol table "hfd_rise", "star_drop").
 */

import { timeOf, type BaselineOrigin, type RunBaseline } from '../../api/attention';
import type { SequenceState } from '../../api/sequence';
import { clockUtc } from '../../format/time';

/** An attention item as the band needs it (structurally a subset of api/attention's AttentionItem). */
export interface RunAttention {
  id: string;
  rule: string;
  ruleLabel?: string;
  level: 'critical' | 'attention' | 'info';
  /** Unix s when its cause began (null: unknown). */
  since: number | null;
  /** Unix s when it cleared (null: it holds). */
  cleared?: number | null;
  active?: boolean;
  runId?: string | null;
  values?: Record<string, unknown> | null;
}

/** A rule period on the curve (LightCurvePlot `rules`). */
export interface CurveRuleSpan {
  id: string;
  from: number;
  to: number | null;
  label: string;
}

/** Rules whose period is a stretch of doubtful photometry: drawn on the light curve. */
export const CURVE_RULES: ReadonlySet<string> = new Set(['hfd_rise', 'star_drop', 'comps_low', 'tracker_lost']);

/** The rule behind each mini chart that has one (its threshold is drawn there). */
export const METRIC_RULE = { hfd: 'hfd_rise', stars: 'star_drop' } as const;
export type RuleMetric = keyof typeof METRIC_RULE;

/** Rule defaults (protocol "alerts.*"; functional-spaces 4.10), used until the server says. */
export const RULE_DEFAULTS = { hfd_factor: 1.5, star_factor: 0.7, baseline_frames: 20 } as const;

const WORDS: Record<string, string> = {
  hfd_rise: 'HFD rise',
  star_drop: 'Star count drop',
  comps_low: 'Too few comparisons',
  tracker_lost: 'Tracker lost',
};

/** The Settings › Alerts key "Change rule…" opens on, per rule (protocol "alerts.*"). */
const RULE_KEY: Record<string, string> = {
  hfd_rise: 'alerts.hfd_factor',
  star_drop: 'alerts.star_factor',
  comps_low: 'alerts.comparisons_min',
  tracker_lost: 'alerts.consecutive_frames',
  no_frame: 'alerts.no_frame_factor',
  altitude: 'alerts.altitude_warn_min',
  disk: 'alerts.disk_minutes',
};

/** The alerts key of a rule ("Change rule…"), else the category's first key. */
export function ruleKey(rule: string): string {
  return RULE_KEY[rule] ?? 'alerts.sound';
}

export function ruleName(a: Pick<RunAttention, 'rule' | 'ruleLabel'>): string {
  return a.ruleLabel || WORDS[a.rule] || a.rule;
}

/** The items of the run on screen: its run id, else raised since it started. */
export function runItems(items: readonly RunAttention[], seq: Pick<SequenceState, 'run_id' | 'started_t'> | null): RunAttention[] {
  if (!seq) return [];
  return items.filter((a) => (a.runId && seq.run_id ? a.runId === seq.run_id : seq.started_t !== null && a.since !== null && a.since >= seq.started_t - 1));
}

/** The rule periods the curve draws (oldest first, one per item). */
export function curveRules(items: readonly RunAttention[]): CurveRuleSpan[] {
  return items
    .filter((a) => CURVE_RULES.has(a.rule) && a.since !== null)
    .map((a) => ({ id: a.id, from: a.since as number, to: a.active === false || (a.cleared ?? null) !== null ? (a.cleared ?? a.since) : null, label: ruleName(a) }))
    .sort((x, y) => x.from - y.from);
}

/** A rule setting from the server's `thresholds` (keys with or without "alerts."), else its default. */
export function ruleSetting(thresholds: Record<string, unknown> | null | undefined, key: keyof typeof RULE_DEFAULTS): number {
  const v = thresholds?.[key] ?? thresholds?.[`alerts.${key}`];
  return typeof v === 'number' && Number.isFinite(v) ? v : RULE_DEFAULTS[key];
}

/** Median of the first `count` finite values at t ≥ from (null before `count` of them). */
export function baselineMedian(t: ArrayLike<number>, v: ArrayLike<number>, n: number, from: number, count: number): number | null {
  const got: number[] = [];
  for (let i = 0; i < n && got.length < count; i++) if (t[i] >= from && Number.isFinite(v[i])) got.push(v[i]);
  if (got.length < count || !got.length) return null;
  got.sort((a, b) => a - b);
  const m = got.length >> 1;
  return got.length % 2 ? got[m] : (got[m - 1] + got[m]) / 2;
}

/**
 * The server's baseline the run's rule lines use: the one of `filter` (the filter being taken,
 * compared without case), or the only one when the filter is not known; null when none fits (the
 * lines fall back to the run's own subs). Another filter's baseline is never drawn: with IR's
 * baseline set and LP's not yet, LP subs got IR's threshold line.
 */
export function pickBaseline(baselines: readonly RunBaseline[] | null | undefined, filter: string | null | undefined): RunBaseline | null {
  if (!baselines?.length) return null;
  if (!filter) return baselines.length === 1 ? baselines[0] : null;
  const want = filter.toLowerCase();
  return baselines.find((b) => b.filter.toLowerCase() === want) ?? null;
}

/** Where a carried baseline comes from ("baseline from the run of 05:01 UTC"); null: the run's own. */
export function baselineFrom(b: Pick<BaselineOrigin, 'carried' | 'runT'> | null | undefined): string | null {
  if (!b?.carried) return null;
  return b.runT !== null ? `baseline from the run of ${clockUtc(b.runT, false)} UTC` : 'baseline from an earlier run';
}

export interface Threshold {
  value: number;
  /** "the server's" (an item said it) or "the rule's" (factor × baseline here). */
  source: 'server' | 'rule';
  /** Words for the row and its tooltip: "rule 1.5 × 2.07 px = 3.10 px". */
  text: string;
}

/**
 * The threshold a mini chart draws for its rule: the newest item's `values.threshold` (or
 * `threshold_px`, `threshold_stars`), else factor × the server's `baseline` for the run (see
 * pickBaseline), else factor × the median of the run's first B subs.
 */
export function metricThreshold(
  metric: RuleMetric,
  items: readonly RunAttention[],
  thresholds: Record<string, unknown> | null | undefined,
  cols: { t: ArrayLike<number>; v: ArrayLike<number>; n: number },
  from: number | null,
  baseline: RunBaseline | null = null,
): Threshold | null {
  const rule = METRIC_RULE[metric];
  const unit = metric === 'hfd' ? ' px' : '';
  const digits = metric === 'hfd' ? 2 : 0;
  for (let i = items.length - 1; i >= 0; i--) {
    const a = items[i];
    if (a.rule !== rule || !a.values) continue;
    // The server's item (attention.py): hfd_rise {baseline_px, factor}, star_drop {baseline, factor};
    // the line is the server's own baseline × factor (per filter), never recomputed here.
    const base = metric === 'hfd' ? a.values.baseline_px : a.values.baseline;
    const f = a.values.factor;
    if (typeof base === 'number' && typeof f === 'number' && Number.isFinite(base * f)) {
      const value = base * f;
      const whence = baselineFrom({ carried: a.values.baseline_origin === 'earlier_run', runT: timeOf(a.values.baseline_run_utc) });
      return { value, source: 'server', text: `rule ${f} × ${base.toFixed(digits)}${unit} = ${value.toFixed(digits)}${unit}${whence ? ` · ${whence}` : ''}` };
    }
    const v = a.values.threshold;
    if (typeof v === 'number' && Number.isFinite(v)) return { value: v, source: 'server', text: `rule ${v.toFixed(digits)}${unit}` };
  }
  const factor = ruleSetting(thresholds, metric === 'hfd' ? 'hfd_factor' : 'star_factor');
  const srv = baseline ? (metric === 'hfd' ? baseline.hfdPx : baseline.stars) : null;
  if (srv !== null && srv > 0) {
    const value = factor * srv;
    const whence = baselineFrom(baseline ? (metric === 'hfd' ? baseline.hfdFrom : baseline.starsFrom) : null);
    return { value, source: 'server', text: `rule ${factor} × ${srv.toFixed(digits)}${unit} = ${value.toFixed(digits)}${unit}${whence ? ` · ${whence}` : ''}` };
  }
  if (from === null) return null;
  const count = Math.round(ruleSetting(thresholds, 'baseline_frames'));
  const base = baselineMedian(cols.t, cols.v, cols.n, from, count);
  if (base === null) return null;
  const value = factor * base;
  return { value, source: 'rule', text: `rule ${factor} × ${base.toFixed(digits)}${unit} = ${value.toFixed(digits)}${unit}` };
}

/** Is the metric past its threshold on the newest value (a word beside the mark, never colour alone). */
export function pastThreshold(metric: RuleMetric, value: number | null, th: Threshold | null): boolean {
  if (value === null || !th) return false;
  return metric === 'hfd' ? value > th.value : value < th.value;
}

/** The newest finite value of a column's valid prefix. */
export function latestFinite(v: ArrayLike<number>, n: number): number | null {
  for (let i = n - 1; i >= 0; i--) if (Number.isFinite(v[i])) return v[i];
  return null;
}

/**
 * The mini charts' time window: the curve's view when it has one (the sparklines line up
 * with the curve above them), else the run from its start to now.
 */
export function miniWindow(view: [number, number] | null, startedT: number | null, firstT: number | null, now: number): [number, number] | null {
  if (view && view[1] > view[0]) return view;
  const a = startedT ?? firstT;
  if (a === null || !Number.isFinite(a)) return null;
  return [a, Math.max(now, a + 60)];
}

export interface MiniLayout {
  /** 'stack': key and value over a full-width sparkline; 'row': key, value and a short sparkline on one line. */
  kind: 'stack' | 'row';
  /** Sparkline height, CSS px. */
  sparkH: number;
}

/** Five rows (run, last frame, HFD, stars, sky) in the band's content height. */
export function miniLayout(height: number): MiniLayout {
  const rows = 5;
  const per = height / rows;
  if (per >= 44) return { kind: 'stack', sparkH: Math.min(28, Math.floor(per - 26)) };
  return { kind: 'row', sparkH: Math.max(10, Math.min(16, Math.floor(per - 8))) };
}

/** Width of the mini column at a band width (CSS px): the curve keeps the room. */
export function miniWidth(bandW: number): number {
  return bandW >= 900 ? 216 : bandW >= 640 ? 184 : 0;
}

/**
 * A run of the sequencer just started exposing (D1: the app proposes Run mode with a chip,
 * never switches): the record went to running, pausing or autofocus from another run or
 * from no run (idle, waiting, scheduled).
 */
export function runStarted(prev: Pick<SequenceState, 'state' | 'run_id'> | null, next: Pick<SequenceState, 'state' | 'run_id'> | null): boolean {
  if (!next) return false;
  const live = (s: Pick<SequenceState, 'state'> | null) => !!s && (s.state === 'running' || s.state === 'pausing' || s.state === 'autofocus' || s.state === 'paused');
  if (!live(next)) return false;
  if (!live(prev)) return true;
  return !!next.run_id && !!prev?.run_id && next.run_id !== prev.run_id;
}

/**
 * Frames n / N of the run on screen: the record's while a run is engaged; once it ended
 * (idle, the record's counts back to 0 / 0) the last result's, so the band keeps the run it
 * shows; else the subs this client saw.
 */
export function runCounts(seq: Pick<SequenceState, 'state' | 'frames_done' | 'frames_total' | 'last_result'> | null, seen: number): { done: number; total: number } {
  if (!seq) return { done: seen, total: 0 };
  const r = seq.state === 'idle' ? seq.last_result : null;
  if (r) return { done: r.frames_saved, total: r.frames_total ?? r.frames_saved };
  return { done: seq.frames_done, total: seq.frames_total };
}

/** The suggestion chip's words when a run starts ("Run started · RR Lyr · 195 frames"). */
export function runSuggestion(s: Pick<SequenceState, 'object_name' | 'frames_total'>): string {
  const n = s.frames_total;
  return ['Run started', s.object_name || null, n ? `${n} frame${n === 1 ? '' : 's'}` : null].filter(Boolean).join(' · ');
}

/** The autofocus sweep in words for the run row ("Autofocus · 4 of 9"). */
export function afText(afStep: { done: number; total: number } | null | undefined): string | null {
  if (!afStep || !(afStep.total > 0)) return null;
  return `Autofocus · ${Math.min(afStep.done, afStep.total)} of ${afStep.total}`;
}
