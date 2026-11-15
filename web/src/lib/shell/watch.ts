/**
 * Watch, the pure part (owner D3; functional-spaces §4.7; PROPOSAL §2.3): what the view
 * reads from 2 m, as display strings, from plain inputs the app maps from its stores (the
 * sequence record, the run's subs, the live photometry, the conditions). The view never
 * computes a magnitude: the photometry is the server's.
 *
 * Truthful: values change when a frame arrives; the last-frame age is a clock (it ticks
 * once a second); a value older than 1.5 cadences turns muted with "as of 22:41" (the lab's
 * margin: a frame in download is not late); past max(2 × cadence, cadence + 60 s) while
 * frames are expected the age says "overdue" (the server's "No new frame" rule fires there
 * too). No cadence yet: no claim of lateness.
 */

import type { SeqStateName } from '../api/sequence';
import type { Tone } from '../app/status';
import { overdueAfter } from '../charts/conditions';
import { DASH, fixed, int, PLUS_MINUS } from '../format/number';
import { clockUtc, duration } from '../format/time';

export interface WatchLink {
  label: string;
  tone: Tone;
  /** The state in a word ("connected", "lost"): Night Red dots fall below 3:1. */
  word: string;
  /** A folded group ("All linked", "2 linked"): `word` lists its members for the tooltip. */
  group?: boolean;
}

/** What Watch shows; every field may be missing (no run, no photometry yet). */
export interface WatchData {
  /** The sequence's state; null when no run is engaged (Watch then shows "Idle"). */
  state: SeqStateName | null;
  object: string | null;
  /** "step 1 of 1 · TG · 10.0 s" (run.ts stepLine). */
  stepLine?: string | null;
  framesDone: number | null;
  framesTotal: number | null;
  /** DATE-OBS of the newest sub, unix s (SequenceStore.lastFrameAt). */
  lastFrameAt: number | null;
  /** Observed cadence, s (SequenceStore.cadence). */
  cadence: number | null;
  /** The camera works for the run now (running, pausing): only then can the age be late. */
  expecting: boolean;
  /** `band`: the photometric band (TG); `filter`: the frames' filter by name (IR), S49. */
  target: { name: string; mag: number | null; err: number | null; band: string | null; filter?: string | null } | null;
  /** The check star: σ of its last `n` points (present.ts trailingStats). */
  check: { name: string; sigma: number | null; n: number } | null;
  comps: { used: number | null; total: number | null; verdict: string | null } | null;
  /** End of the run, unix s (run.ts endAt). */
  end: number | null;
  /** Star count and HFD per sub, oldest first (the run's saves). */
  stars: readonly number[];
  hfd: readonly number[];
  /** The HFD rule's threshold (px) drawn on the sparkline, when the server says it. */
  hfdRef?: number | null;
  /** The HFD rule holds (an open "hfd_rise" item). */
  hfdFlag?: boolean;
  alt: number | null;
  altLimit: number | null;
  /** When the target sinks below the limit, unix s. */
  altUntil?: number | null;
  links: readonly WatchLink[];
  /** The server's keep-awake record (status.keep_awake): the COMPUTER kept awake during the run. */
  computer?: { state: string; method: string | null; message: string | null } | null;
  /** The run that just ended (no run engaged): its outcome replaces "IDLE" (D2: the wrap-up waits). */
  ended?: { word: string; at: number | null } | null;
  /** The alert sound (Settings › Alerts), and whether a gesture armed it. */
  sound?: { level: 'off' | 'soft' | 'normal'; armed: boolean } | null;
}

/** The headline word of a run's outcome (sequence.last_result.reason). */
export function endedWord(reason: string | null | undefined): string {
  if (reason === 'completed') return 'COMPLETE';
  if (reason === 'stopped') return 'STOPPED';
  if (reason === 'cancelled') return 'CANCELLED';
  return 'FAILED';
}

/** The footer's sound line: an observer at 2 m must know a Critical would be silent. */
export function soundLine(s: WatchData['sound']): { text: string; warn: boolean } | null {
  if (!s) return null;
  if (s.level === 'off') return { text: 'Sound off', warn: true };
  if (!s.armed) return { text: 'Sound not armed: press any key', warn: true };
  return { text: s.level === 'soft' ? 'Sound Soft' : 'Sound Normal', warn: false };
}

/** Off → Soft → Normal → Off (a click on the footer's sound line, as the palette's commands). */
export function nextSound(level: 'off' | 'soft' | 'normal'): 'off' | 'soft' | 'normal' {
  return level === 'off' ? 'soft' : level === 'soft' ? 'normal' : 'off';
}

/**
 * The footer's links: one "All linked" when every link is up; else each link that is not, by
 * its name and state, then the others folded into "2 linked" (their names in the tooltip).
 * Three links by name were cut mid-word at 1 280 px ("● Came ○ Mount not conn ● Serv").
 */
export function linksView(links: readonly WatchLink[]): WatchLink[] {
  const up = links.filter((l) => l.tone === 'ok');
  const word = up.map((l) => `${l.label} ${l.word}`).join(', ');
  if (links.length && up.length === links.length) return [{ label: 'All linked', tone: 'ok', word, group: true }];
  const down = links.filter((l) => l.tone !== 'ok');
  return up.length ? [...down, { label: `${up.length} linked`, tone: 'ok', word, group: true }] : down;
}

/**
 * `status.keep_awake` (protocol.md "Keep-awake", KeepAwake) read tolerantly; null when the
 * status carries none (an older server) or it is not one. A `status` listener feeds Watch:
 *   events.on('status', (m) => (keepAwake = checkKeepAwake(m.keep_awake)))
 */
export function checkKeepAwake(v: unknown): { state: string; method: string | null; message: string | null; since: number | null; reason: string | null } | null {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return null;
  const r = v as Record<string, unknown>;
  const state = r.state;
  if (state !== 'off' && state !== 'held' && state !== 'failed' && state !== 'unsupported' && state !== 'disabled') return null;
  const s = (x: unknown) => (typeof x === 'string' && x !== '' ? x : null);
  const ms = typeof r.since === 'string' ? Date.parse(r.since) : NaN;
  return { state, method: s(r.method), message: s(r.message), since: Number.isFinite(ms) ? ms / 1000 : null, reason: s(r.reason) };
}

/** The footer's line about the computer's sleep (the screen's is the wake lock's). */
export function computerLine(c: WatchData['computer']): { text: string; warn: boolean } | null {
  if (!c) return null;
  switch (c.state) {
    case 'held':
      return { text: `Computer awake${c.method ? ` (${c.method})` : ''}`, warn: false };
    case 'failed':
    case 'unsupported':
      return { text: `Computer may sleep${c.message ? `: ${c.message}` : ''}`, warn: true };
    case 'disabled':
      return { text: 'Computer may sleep: keep-awake off (Settings › Alerts)', warn: true };
    default:
      return null;
  }
}

const STATE_WORD: Record<SeqStateName, string> = {
  idle: 'IDLE',
  waiting: 'SCHEDULED',
  scheduled: 'SCHEDULED',
  running: 'RUNNING',
  pausing: 'PAUSING',
  paused: 'PAUSED',
  autofocus: 'AUTOFOCUS',
  stopping: 'STOPPING',
};

export function stateWord(s: SeqStateName | null): string {
  return s ? STATE_WORD[s] : 'IDLE';
}

/** Hold-to-pause is offered while the run exposes (no Stop, no mount action in Watch). */
export function canPause(s: SeqStateName | null): boolean {
  return s === 'running' || s === 'autofocus';
}

export interface AgeView {
  /** "12 s", "2m 05s", "—". */
  value: string;
  /** Older than 1.5 cadences: the values on screen are muted, "as of". */
  late: boolean;
  /** Past the overdue limit while frames are expected. */
  overdue: boolean;
  /** "last frame · every 51 s", "last frame · as of 22:41 · overdue". */
  note: string;
}

export function ageView(lastAt: number | null, now: number, cadence: number | null, expecting: boolean): AgeView {
  if (lastAt === null) return { value: DASH, late: false, overdue: false, note: 'no frame yet' };
  const age = Math.max(0, now - lastAt);
  const late = expecting && cadence !== null && age > 1.5 * cadence;
  const overdue = expecting && cadence !== null && age > overdueAfter(cadence);
  const parts = ['last frame'];
  if (late) parts.push(`as of ${clockUtc(lastAt, false)}`);
  if (overdue) parts.push('overdue');
  else if (cadence !== null) parts.push(`every ${fixed(cadence, 0)} s`);
  return { value: duration(age), late, overdue, note: parts.join(' · ') };
}

/** "160 / 195" or "—". */
export function framesText(done: number | null, total: number | null): string {
  if (done === null) return DASH;
  return total ? `${int(done)} / ${int(total)}` : int(done);
}

/** The ENDS tile: "22:54" and "UTC · in 30 min", or "—". */
export function endsView(end: number | null, now: number, ended?: { at: number | null } | null): { value: string; note: string } {
  // A run that ended: its end time, never "after the first frames" (wave 6b fixer).
  if (ended) return ended.at !== null && Number.isFinite(ended.at) ? { value: clockUtc(ended.at, false), note: 'UTC · ended' } : { value: DASH, note: 'ended' };
  if (end === null || !Number.isFinite(end)) return { value: DASH, note: 'after the first frames' };
  const left = end - now;
  return { value: clockUtc(end, false), note: left > 0 ? `UTC · in ${duration(left)}` : 'UTC · now' };
}

/** "± 0.035 TG" under the target magnitude. */
export function errLine(err: number | null, band: string | null): string {
  return `${PLUS_MINUS} ${fixed(err, 3)}${band ? ` ${band}` : ''}`;
}

/** "comps 5 / 6 · consistent". */
export function compsLine(c: WatchData['comps']): string {
  if (!c) return 'comps —';
  const n = c.used === null ? DASH : int(c.used);
  return `comps ${n}${c.total ? ` / ${int(c.total)}` : ''}${c.verdict ? ` · ${c.verdict}` : ''}`;
}

/** The ALT tile's value: "41°", or "—" (no degree sign on a missing value). */
export function altValue(alt: number | null): string {
  return alt === null || !Number.isFinite(alt) ? DASH : `${fixed(alt, 0)}°`;
}

/** The ALT tile's second line: "limit 30° · until 01:10" / "below the limit". */
export function altLine(alt: number | null, limit: number | null, until: number | null | undefined): string {
  if (alt === null) return 'mount not connected';
  if (limit === null) return 'no limit set';
  if (alt !== null && alt < limit) return `below the ${fixed(limit, 0)}° limit`;
  return `limit ${fixed(limit, 0)}°${until != null ? ` · until ${clockUtc(until, false)}` : ''}`;
}

/**
 * One column of the conditions store for Watch's sparklines: the finite values of the subs
 * taken since `from` (the run's start, unix s; null: every row), oldest first, at most `max`
 * (the newest kept). `t` and `v` are the store's columns, `n` its row count.
 */
export function runSeries(t: ArrayLike<number>, v: ArrayLike<number>, n: number, from: number | null, max = 2000): number[] {
  const out: number[] = [];
  for (let i = 0; i < n; i++) if ((from === null || t[i] >= from) && Number.isFinite(v[i])) out.push(v[i]);
  return out.length > max ? out.slice(out.length - max) : out;
}

/**
 * The HFD rule's threshold for Watch's sparkline (px): the server's own numbers when an
 * `hfd_rise` item carries them (`values.baseline_px` × `values.factor`, protocol table), else
 * `alerts.hfd_factor` × the server's HFD baseline for the run (`baseline`: AttentionState.baselines,
 * carried from an earlier run of the same object, filter, exposure and gain, or the run's own;
 * runband pickBaseline), else the rule's definition on the run's subs: `alerts.hfd_factor` × the
 * median of the first `alerts.baseline_frames` HFD values (the server takes the baseline per
 * filter: a run with two filters may differ until the item fires). Null before a baseline exists.
 */
export function hfdRule(items: readonly { rule: string; active: boolean; values: Record<string, unknown> | null }[], thresholds: Record<string, unknown> | null | undefined, hfd: readonly number[], baseline: { hfdPx: number | null } | null = null): number | null {
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
  for (const a of items) {
    if (a.rule !== 'hfd_rise' || !a.active || !a.values) continue;
    const base = num(a.values.baseline_px);
    const f = num(a.values.factor);
    if (base !== null && f !== null) return base * f;
  }
  const factor = num(thresholds?.['alerts.hfd_factor']) ?? 1.5;
  const srv = num(baseline?.hfdPx);
  if (srv !== null && srv > 0) return factor * srv;
  const count = Math.round(num(thresholds?.['alerts.baseline_frames']) ?? 20);
  if (count < 1 || hfd.length < count) return null;
  const first = hfd.slice(0, count).sort((x, y) => x - y);
  const mid = first.length >> 1;
  const median = first.length % 2 ? first[mid] : (first[mid - 1] + first[mid]) / 2;
  return factor * median;
}

export const DIM_LEVELS = [100, 60, 30] as const;
export type DimLevel = (typeof DIM_LEVELS)[number];

export function isDim(v: unknown): v is DimLevel {
  return v === 100 || v === 60 || v === 30;
}

/**
 * Watch's keys (owner D3: only W, Esc, ? and Mod+K act). `mac` picks ⌘ over Ctrl. Returns
 * what the key does, or null for a key Watch ignores (every other shortcut is held).
 */
export function watchKey(e: { key: string; code?: string; metaKey?: boolean; ctrlKey?: boolean; altKey?: boolean; shiftKey?: boolean }, mac: boolean): 'close' | 'help' | 'palette' | null {
  const mod = mac ? e.metaKey : e.ctrlKey;
  if (mod && !e.altKey && (e.key === 'k' || e.key === 'K')) return 'palette';
  if (e.metaKey || e.ctrlKey || e.altKey) return null;
  if (e.key === 'Escape') return 'close';
  // Letters follow the layout (app/shortcuts.ts keyMatches): on AZERTY the KeyW position
  // types "z". The physical KeyW counts only when the key types no Latin letter.
  if (e.key === 'w' || e.key === 'W') return 'close';
  if (e.code === 'KeyW' && !/^[a-z]$/i.test(e.key)) return 'close';
  if (e.key === '?') return 'help';
  return null;
}
