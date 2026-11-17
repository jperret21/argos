/**
 * Attention on the client, the pure part (wave 6b; BRAND §8 and §13, functional-spaces
 * §4.10): ordering, what needs the observer, the status-bar chip's line, the default next
 * step of a rule, and which tone sounds when. The rules themselves are the server's
 * (src/lab/workspace/model/rules.ts is their test oracle); nothing here re-evaluates a
 * frame.
 *
 * - Needs the observer: a Critical or Attention item still active, not yet acknowledged
 *   (the server's `counts.unacked`). Info items are records (run started, autofocus done):
 *   listed, never counted, never acknowledged.
 * - Order: needing the observer first, then the level (critical, attention, info), then the
 *   item still active before a cleared one, then the newest.
 * - Sound (BRAND §13: Critical 3 tones, Attention 2, Info 1; Off / Soft / Normal): a NEW item
 *   sounds once, the highest level of a batch only (no storm when a replay or several rules
 *   arrive together); a Critical item still active and not acknowledged repeats every 30 s
 *   (functional-spaces §4.10); Info sounds only when the observer asked for it (off by
 *   default). Tones never carry information found nowhere else: every tone has its item on
 *   screen.
 */

import type { AttentionItem, AttentionLevel, AttentionTarget } from '../../api/attention';

export type SoundLevel = 'off' | 'soft' | 'normal';
export const SOUND_LEVELS: readonly SoundLevel[] = ['off', 'soft', 'normal'];
export const SOUND_LABEL: Record<SoundLevel, string> = { off: 'Off', soft: 'Soft', normal: 'Normal' };

export function isSoundLevel(v: unknown): v is SoundLevel {
  return v === 'off' || v === 'soft' || v === 'normal';
}

/** The config keys Settings › Alerts holds (config meta, category "alerts"). */
export const ALERT_KEYS = {
  sound: 'alerts.sound',
  soundInfo: 'alerts.sound_info',
  repeat: 'alerts.repeat_critical_s',
  keepAwake: 'alerts.keep_awake',
} as const;

/** The level in a word, always beside its mark (BRAND §8). */
export const LEVEL_WORD: Record<AttentionLevel, string> = { critical: 'Critical', attention: 'Attention', info: 'Info' };

/** Seconds between two soundings of a Critical item not yet acknowledged. */
export const CRITICAL_REPEAT_S = 30;
/** Shortest gap between two tones (a burst of items sounds once). */
export const TONE_GAP_S = 2;

export function levelRank(l: AttentionLevel): number {
  return l === 'critical' ? 0 : l === 'attention' ? 1 : 2;
}

/**
 * A Critical or Attention item still active that nobody acknowledged yet: the server's
 * `counts.unacked`. A condition cleared before anyone acknowledged it is in the history
 * (`active: false`): it needs nobody, and the server ignores an ack of it.
 */
export function needsObserver(a: AttentionItem): boolean {
  return a.active && a.level !== 'info' && !a.acked;
}

export function compareItems(a: AttentionItem, b: AttentionItem): number {
  return (
    Number(needsObserver(b)) - Number(needsObserver(a)) ||
    levelRank(a.level) - levelRank(b.level) ||
    Number(b.active) - Number(a.active) ||
    (b.since ?? 0) - (a.since ?? 0) ||
    a.id.localeCompare(b.id)
  );
}

export function sortItems(items: Iterable<AttentionItem>): AttentionItem[] {
  return [...items].sort(compareItems);
}

/** The items that need the observer, most urgent first. */
export function openItems(items: Iterable<AttentionItem>): AttentionItem[] {
  return sortItems([...items].filter(needsObserver));
}

export interface ChipView {
  /** Nothing to show: the server lists no item at all (active or history). */
  hidden: boolean;
  /** Level of the most urgent open item; null when nothing needs the observer. */
  level: AttentionLevel | null;
  count: number;
  /** The most urgent item's headline ("HFD 18.3 px · 1.5× baseline"). */
  text: string;
  /** Accessible name and tooltip: the count and the headline in words. */
  label: string;
}

export function chipView(items: Iterable<AttentionItem>): ChipView {
  const all = [...items];
  const open = openItems(all);
  if (!open.length) {
    const n = all.length;
    return {
      hidden: n === 0,
      level: null,
      count: 0,
      text: '',
      label: n ? `Attention list: nothing needs you · ${n} ${n === 1 ? 'item' : 'items'} listed` : 'Attention list: empty',
    };
  }
  const top = open[0];
  const more = open.length > 1 ? ` · ${open.length - 1} more` : '';
  return {
    hidden: false,
    level: top.level,
    count: open.length,
    text: top.short,
    label: `${LEVEL_WORD[top.level]}: ${top.short}${more}. Open the attention list`,
  };
}

/** The next step a rule suggests when the server names none (the server's own wins). */
export const DEFAULT_ACTION: Record<string, { to: AttentionTarget; label: string }> = {
  hfd_rise: { to: 'focus', label: 'Focus mode' },
  autofocus_failed: { to: 'focus', label: 'Focus mode' },
  comps_low: { to: 'field', label: 'Field mode' },
  tracker_lost: { to: 'field', label: 'Field mode' },
  altitude: { to: 'run', label: 'Run mode' },
  device_lost: { to: 'devices', label: 'Devices' },
};

export function actionOf(a: AttentionItem): { to: AttentionTarget; label: string } | null {
  return a.action ?? DEFAULT_ACTION[a.rule] ?? null;
}

/** "22:16 UTC · frame 152" (the item's time and frame), "" when neither is known. */
export function whenLine(a: AttentionItem, clock: (t: number) => string): string {
  const parts: string[] = [];
  if (a.since !== null) parts.push(`${clock(a.since)} UTC`);
  if (a.frame !== null) parts.push(`frame ${a.frame}`);
  return parts.join(' · ');
}

// -- Sound --------------------------------------------------------------------------------------

export interface ToneState {
  /** Ids already sounded (or present when the list was first read: a replay never sounds). */
  heard: Set<string>;
  /** Unix s of the last tone per Critical id (repeats). */
  lastCritical: Map<string, number>;
  /** Unix s and level of the last tone of any kind. */
  lastTone: number;
  lastLevel: AttentionLevel | null;
}

export function newToneState(): ToneState {
  return { heard: new Set(), lastCritical: new Map(), lastTone: -Infinity, lastLevel: null };
}

export interface SoundPrefs {
  level: SoundLevel;
  /** Info items sound one soft tone (off by default). */
  info: boolean;
  /** Repeat of an open Critical item, s (alerts.repeat_critical_s; 0: once). */
  repeatS?: number;
}

/**
 * The tone to play now (or null); updates `st`. `items` is the whole list; `quiet` marks a
 * replay (a client joining mid-run, a reconnection): its items are remembered as heard and
 * never sound, except a Critical item still active and open, whose sound repeats until it
 * is acknowledged (BRAND §8) on every client. With the sound Off the state still advances,
 * so turning it on later never replays old items.
 */
export function nextTone(items: readonly AttentionItem[], st: ToneState, prefs: SoundPrefs, now: number, quiet = false): AttentionLevel | null {
  // An item reopened by the server is new again when it sounds again (tone + 1; a
  // flapping non-critical item stays quiet for 15 min after its last tone).
  const key = (a: AttentionItem) => `${a.id}#${a.tone}`;
  const fresh = items.filter((a) => !st.heard.has(key(a)));
  for (const a of fresh) st.heard.add(key(a));
  for (const id of [...st.lastCritical.keys()]) {
    const a = items.find((x) => x.id === id);
    if (!a || a.acked || !a.active) st.lastCritical.delete(id);
  }
  let best: AttentionLevel | null = null;
  const pick = (l: AttentionLevel) => {
    if (best === null || levelRank(l) < levelRank(best)) best = l;
  };
  // The server says whether an item sounds (info: alerts.sound_info); else the level decides.
  const sounds = (a: AttentionItem) => a.sound ?? (a.level !== 'info' || prefs.info);
  if (!quiet) for (const a of fresh) if (!a.acked && a.active && sounds(a)) pick(a.level);
  for (const a of items) {
    if (a.level !== 'critical' || a.acked || !a.active || !sounds(a)) continue;
    const every = a.repeatS ?? prefs.repeatS ?? CRITICAL_REPEAT_S;
    const last = st.lastCritical.get(a.id);
    if (last === undefined) {
      st.lastCritical.set(a.id, now);
      pick('critical');
    } else if (every > 0 && now - last >= every) {
      st.lastCritical.set(a.id, now);
      pick('critical');
    }
  }
  if (best === null || prefs.level === 'off') return null;
  // A burst sounds once; a more urgent level is never held back by a lesser tone.
  const held = st.lastLevel !== null && levelRank(best) >= levelRank(st.lastLevel);
  if (held && now - st.lastTone < TONE_GAP_S) return null;
  st.lastTone = now;
  st.lastLevel = best;
  return best;
}

/** The sound preferences from the config values (Settings › Alerts); defaults when a key is absent. */
export function prefsFrom(values: Record<string, unknown> | null | undefined): SoundPrefs {
  const level = values?.[ALERT_KEYS.sound];
  const rep = values?.[ALERT_KEYS.repeat];
  return { level: isSoundLevel(level) ? level : 'normal', info: values?.[ALERT_KEYS.soundInfo] === true, ...(typeof rep === 'number' && Number.isFinite(rep) ? { repeatS: rep } : {}) };
}
