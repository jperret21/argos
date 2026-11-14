/**
 * Attention items on the wire (wave 6b; PROPOSAL §7, functional-spaces §4.10, BRAND §13;
 * contract in argos/server/protocol.md "attention"). The rules run on the SERVER, on every
 * frame, so every client agrees and one acknowledgement is shared; the client only shows
 * the items, sounds them and sends the acknowledgement.
 *
 * Read tolerantly (a newer server may add fields; an item without an id, a level or a text
 * is refused, never guessed) and normalised once for the views: times are unix seconds,
 * levels are the three of BRAND §8.
 *
 * The server sends a SNAPSHOT (protocol.md "Night (wave 6b)", AttentionState): the WS
 * `attention` event on every change and once to a client that connects, `GET
 * /api/attention`, and the answer of `POST /api/attention/{id}/ack` and `…/ack-all` are all
 *   {"active": [AttentionItem], "history": [AttentionItem], "counts": {…},
 *    "sound": {"level", "info", "repeat_s"}, "thresholds": {…}, "last_change": {…}, "revision"}
 * An item: {id, rule, cause, name, level, kind, title, short, detail, values, since,
 * raised_utc, updated_utc, frame, run_id, action: {to, label} | null, active, cleared_utc,
 * cleared_reason, acked, acked_utc, acked_by, occurrences, tone, sound, repeat_s}.
 * One item alone ({"item": …} or a bare item) is read too (tests, a future delta event).
 */

import type { RequestOptions } from './client';

export type AttentionLevel = 'critical' | 'attention' | 'info';
export const ATTENTION_LEVELS: readonly AttentionLevel[] = ['critical', 'attention', 'info'];

/** Where a suggested next step leads (the app maps it to a mode, a view or a screen). */
export type AttentionTarget = 'framing' | 'focus' | 'field' | 'run' | 'watch' | 'plan' | 'settings' | 'devices';
const TARGETS: ReadonlySet<string> = new Set(['framing', 'focus', 'field', 'run', 'watch', 'plan', 'settings', 'devices']);

export interface AttentionItem {
  /** Stable id: one item per rule and episode (the server's). */
  id: string;
  level: AttentionLevel;
  /** Rule id ("hfd_rise", "no_frame", …), as the server names it. */
  rule: string;
  /** The rule in words ("HFD rise"): the server's `name`. */
  ruleLabel: string;
  /** "condition" clears itself when its cause ends; "event" stays until acknowledged. */
  kind: 'condition' | 'event';
  /** The list's line: the rule's numbers ("HFD 17.5 px = 2.8× the first 20 frames"). */
  title: string;
  /** Watch's headline, read from 2 m: the value and the factor only. */
  short: string;
  /** The rule and its numbers in full (the list's second line). */
  detail: string | null;
  /** Unix seconds when the rule fired. */
  since: number | null;
  /** Frame that fired it (1-based, as the run counts), when there is one. */
  frame: number | null;
  runId: string | null;
  /** The condition still holds (false once the server cleared it, with hysteresis). */
  active: boolean;
  cleared: number | null;
  /** "resolved", "run_ended", "new_run", "acknowledged" (the server's). */
  clearedReason: string | null;
  /** 1, +1 each time the same cause fires again soon after its clear (reopened). */
  occurrences: number;
  /** 1, +1 at a reopen that sounds again (the server keeps a flapping non-critical
   * item quiet for 15 min after its last tone); older servers: `occurrences`. */
  tone: number;
  /** The server says the item sounds when it appears (info: alerts.sound_info); null: not said. */
  sound: boolean | null;
  /** Critical: repeat the tone every N s while active and open (0: once); null: not said. */
  repeatS: number | null;
  acked: boolean;
  ackedAt: number | null;
  ackedBy: string | null;
  action: { to: AttentionTarget; label: string } | null;
  /** The rule's numbers, as sent (thresholds, values); shown only through the texts. */
  values: Record<string, unknown> | null;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() !== '' ? v : null);
const int = (v: unknown): number | null => (typeof v === 'number' && Number.isInteger(v) ? v : null);

/** Unix seconds from an ISO 8601 string or a finite number of seconds; null otherwise (never "now"). */
export function timeOf(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v !== 'string' || !v) return null;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

export function isLevel(v: unknown): v is AttentionLevel {
  return v === 'critical' || v === 'attention' || v === 'info';
}

/** "hfd_rise" -> "HFD rise" when the server sends no label (acronyms the rules use kept upper case). */
export function ruleWords(rule: string): string {
  const ACRONYMS: Record<string, string> = { hfd: 'HFD', fwhm: 'FWHM', snr: 'SNR', af: 'AF' };
  const words = rule.split(/[_\s-]+/).filter(Boolean);
  const out = words.map((w, i) => ACRONYMS[w.toLowerCase()] ?? (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w));
  return out.join(' ');
}

/** One wire item, or null when it is not one. */
export function checkAttentionItem(v: unknown): AttentionItem | null {
  if (!isObj(v)) return null;
  const id = str(v.id) ?? (typeof v.id === 'number' && Number.isFinite(v.id) ? String(v.id) : null);
  const level = isLevel(v.level) ? v.level : null;
  const title = str(v.title) ?? str(v.message);
  if (!id || !level || !title) return null;
  const rule = str(v.rule) ?? 'rule';
  const ackedAt = timeOf(v.acked_utc ?? v.acked_t);
  const ackedBy = str(v.acked_by);
  const acked = v.acked === true || ackedAt !== null || ackedBy !== null;
  const cleared = timeOf(v.cleared_utc ?? v.cleared_t);
  const a = isObj(v.action) ? v.action : null;
  const to = a && typeof a.to === 'string' && TARGETS.has(a.to) ? (a.to as AttentionTarget) : null;
  return {
    id,
    level,
    rule,
    ruleLabel: str(v.name) ?? str(v.rule_label) ?? ruleWords(rule),
    kind: v.kind === 'event' ? 'event' : 'condition',
    title,
    short: str(v.short) ?? str(v.headline) ?? title,
    detail: str(v.detail),
    since: timeOf(v.since_utc ?? v.since ?? v.t),
    frame: int(v.frame),
    runId: str(v.run_id),
    active: typeof v.active === 'boolean' ? v.active : cleared === null,
    cleared,
    clearedReason: str(v.cleared_reason),
    occurrences: int(v.occurrences) ?? 1,
    tone: int(v.tone) ?? int(v.occurrences) ?? 1,
    sound: typeof v.sound === 'boolean' ? v.sound : null,
    repeatS: int(v.repeat_s),
    acked,
    ackedAt,
    ackedBy,
    action: to ? { to, label: str(a?.label) ?? to.charAt(0).toUpperCase() + to.slice(1) } : null,
    values: isObj(v.values) ? v.values : null,
  };
}

export interface AttentionBatch {
  /** Items carried by the message (one, or a snapshot's whole list). */
  items: AttentionItem[];
  /** The message replaces the client's list (a snapshot), not just adds to it. */
  replace: boolean;
  /** The snapshot's revision (newer wins), when sent. */
  revision: number | null;
  /** The sound settings in force on the server (alerts.sound, sound_info, repeat_critical_s). */
  sound: { level: 'off' | 'soft' | 'normal'; info: boolean; repeatS: number | null } | null;
  /** Active, not acknowledged, level ≠ info: the server's count for the chip. */
  unacked: number | null;
  /** The alerts.* values in force on the server (the Run band draws the rules with them); null: not sent. */
  thresholds: Record<string, unknown> | null;
}

function listOf(v: unknown): AttentionItem[] {
  return Array.isArray(v) ? v.map(checkAttentionItem).filter((x): x is AttentionItem => x !== null) : [];
}

/**
 * The items of a WS `attention` message, of the `attention` part of a `status` record or of
 * `GET /api/attention`. Null when the message carries none of the accepted shapes.
 */
export function checkAttentionBatch(m: unknown): AttentionBatch | null {
  if (!isObj(m)) return null;
  const lists = ['items', 'active', 'history'].filter((k) => Array.isArray(m[k]));
  if (lists.length) {
    const seen = new Map<string, AttentionItem>();
    // "history" first, then the newer views: a later list's copy of an id wins.
    for (const k of ['history', 'items', 'active']) for (const it of listOf(m[k])) seen.set(it.id, it);
    const snd = isObj(m.sound) ? m.sound : null;
    const level = snd?.level === 'off' || snd?.level === 'soft' || snd?.level === 'normal' ? snd.level : null;
    const counts = isObj(m.counts) ? m.counts : null;
    return {
      items: [...seen.values()],
      replace: m.replay !== false,
      revision: int(m.revision),
      sound: level ? { level, info: snd?.info === true, repeatS: int(snd?.repeat_s) } : null,
      unacked: counts ? int(counts.unacked) : null,
      thresholds: isObj(m.thresholds) ? m.thresholds : null,
    };
  }
  const one = checkAttentionItem(isObj(m.item) ? m.item : m);
  return one ? { items: [one], replace: false, revision: null, sound: null, unacked: null, thresholds: null } : null;
}

/** What the calls need from ArgosClient (tests pass a fake). */
export interface AttentionClient {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown, options?: RequestOptions): Promise<T>;
}

export const attentionApi = {
  /** The active items and the run's history (a client joining mid-run). */
  list: async (c: AttentionClient, o?: RequestOptions): Promise<AttentionBatch | null> =>
    checkAttentionBatch(await c.request<unknown>('GET', '/api/attention', undefined, o)),
  /** Acknowledge one item for every client (404 not_found: unknown id); resolves to the new snapshot. */
  ack: async (c: AttentionClient, id: string, by?: string, o?: RequestOptions): Promise<AttentionBatch | null> =>
    checkAttentionBatch(await c.request<unknown>('POST', `/api/attention/${encodeURIComponent(id)}/ack`, by ? { by } : {}, o)),
  /** Acknowledge every active item. */
  ackAll: async (c: AttentionClient, by?: string, o?: RequestOptions): Promise<AttentionBatch | null> =>
    checkAttentionBatch(await c.request<unknown>('POST', '/api/attention/ack-all', by ? { by } : {}, o)),
};
