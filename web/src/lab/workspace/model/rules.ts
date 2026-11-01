/**
 * Attention rules for unattended runs (functional-spaces.md 4.10), as pure
 * functions over the frame records. In the product the SERVER computes them
 * on every frame, so every client agrees and an acknowledgement is shared;
 * the lab runs the same logic in the browser to drive the prototype.
 *
 * Every message states the rule and the numbers, never an interpretation
 * alone ("HFD 17.5 px = 2.8× the first 20 frames", not "Focus is bad").
 */

import { fixed, int, utc } from './format';
import { median, medianCadence, type FrameRecord } from './night';

export type Level = 'critical' | 'attention' | 'info';

export interface AttentionItem {
  /** Stable id: one item per rule and start frame. */
  id: string;
  level: Level;
  rule: string;
  title: string;
  /** Headline for the Watch view (read from 2 m): the value and the factor only. */
  short: string;
  detail: string;
  /** Unix seconds when the rule fired. */
  since: number;
  /** Frame that fired it, when there is one. */
  frame?: number;
  /** Suggested next step (a mode or a view), shown as a button. */
  action?: { label: string; icon: string; to: 'focus' | 'field' | 'run' | 'watch' };
}

export const RULES = {
  baselineFrames: 20,
  hfdFactor: 1.5,
  starFactor: 0.7,
  compsMin: 3,
  consecutive: 3,
} as const;

/** First index where `pred` holds for `k` consecutive records (index of the k-th), or -1. */
export function firstRun(records: readonly FrameRecord[], pred: (r: FrameRecord) => boolean, k: number, from = 0): number {
  let streak = 0;
  for (let i = from; i < records.length; i++) {
    streak = pred(records[i]) ? streak + 1 : 0;
    if (streak >= k) return i;
  }
  return -1;
}

/** Silence threshold for "no new frame": max(2 x median cadence, median + 60 s). */
export function silenceLimit(records: readonly FrameRecord[]): number {
  const c = medianCadence(records);
  if (!Number.isFinite(c)) return Infinity;
  return Math.max(2 * c, c + 60);
}

export interface RuleContext {
  /** Simulated "now", unix seconds. */
  now: number;
  /** A run is exposing (silence only matters then). */
  running: boolean;
}

export function evaluate(records: readonly FrameRecord[], ctx: RuleContext): AttentionItem[] {
  const out: AttentionItem[] = [];
  const n = records.length;
  if (!n) return out;
  const k = RULES.consecutive;

  // Liveness first: a frozen run looks exactly like a healthy one between frames.
  const last = records[n - 1];
  const limit = silenceLimit(records);
  if (ctx.running && ctx.now - last.t > limit) {
    out.push({
      id: `silence-${last.n}`,
      level: 'critical',
      rule: 'No new frame',
      title: `No new frame for ${Math.round(ctx.now - last.t)} s`,
      short: `No frame for ${Math.round(ctx.now - last.t)} s`,
      detail: `Last frame #${last.n} at ${utc(last.t)} UTC; limit ${Math.round(limit)} s = max(2 × cadence ${fixed(medianCadence(records), 1)} s, cadence + 60 s).`,
      since: last.t + limit,
      frame: last.n,
      action: { label: 'Watch', icon: 'lab-watch', to: 'watch' },
    });
  }

  if (n >= RULES.baselineFrames) {
    const base = records.slice(0, RULES.baselineFrames);
    const hfd0 = median(base.map((r) => r.hfd));
    const i = firstRun(records, (r) => r.hfd > RULES.hfdFactor * hfd0, k, RULES.baselineFrames);
    if (i >= 0) {
      const r = records[i];
      const tail = records.slice(i - k + 1, i + 1).map((x) => fixed(x.hfd, 1));
      out.push({
        id: `hfd-${r.n}`,
        level: 'attention',
        rule: 'HFD rise',
        title: `HFD ${fixed(r.hfd, 1)} px = ${fixed(r.hfd / hfd0, 1)}× the first ${RULES.baselineFrames} frames`,
        short: `HFD ${fixed(r.hfd, 1)} px · ${fixed(r.hfd / hfd0, 1)}× baseline`,
        detail: `Rule: HFD above ${RULES.hfdFactor} × ${fixed(hfd0, 2)} px for ${k} frames in a row (${tail.join(', ')} px, frames ${r.n - k + 1}-${r.n}).`,
        since: r.t,
        frame: r.n,
        action: { label: 'Focus view', icon: 'focuser', to: 'focus' },
      });
    }
    const stars0 = median(base.map((r) => r.stars));
    const j = firstRun(records, (r) => r.stars < RULES.starFactor * stars0, k, RULES.baselineFrames);
    if (j >= 0) {
      const r = records[j];
      out.push({
        id: `stars-${r.n}`,
        level: 'attention',
        rule: 'Star count drop',
        title: `${int(r.stars)} stars = ${fixed(r.stars / stars0, 2)}× the first ${RULES.baselineFrames} frames`,
        short: `${int(r.stars)} stars · ${fixed(r.stars / stars0, 2)}× baseline`,
        detail: `Rule: fewer than ${RULES.starFactor} × ${int(stars0)} stars for ${k} frames in a row.`,
        since: r.t,
        frame: r.n,
      });
    }
  }

  const c = firstRun(records, (r) => r.compsUsed < RULES.compsMin, k);
  if (c >= 0) {
    const r = records[c];
    out.push({
      id: `comps-${r.n}`,
      level: 'attention',
      rule: 'Comparisons used',
      title: `${r.compsUsed} comparisons used for ${k} frames`,
      short: `${r.compsUsed} comparisons used`,
      detail: `Rule: fewer than ${RULES.compsMin} comparisons kept after clipping, ${k} frames in a row.`,
      since: r.t,
      frame: r.n,
      action: { label: 'Field view', icon: 'plate-solve', to: 'field' },
    });
  }

  out.push({
    id: 'run-started',
    level: 'info',
    rule: 'Run started',
    title: 'Run started · RR Lyr',
    short: 'Run started',
    detail: `First frame at ${utc(records[0].t)} UTC.`,
    since: records[0].t,
    frame: 1,
  });

  return out.sort((a, b) => levelRank(a.level) - levelRank(b.level) || b.since - a.since);
}

export function levelRank(l: Level): number {
  return l === 'critical' ? 0 : l === 'attention' ? 1 : 2;
}
