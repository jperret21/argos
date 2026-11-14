/**
 * The end-of-night wrap-up, the client part (owner D2; PROPOSAL 3.1 "End-of-night wrap-up";
 * functional-spaces §4.14; contract protocol.md "Night (wave 6b)", WrapUp). The SERVER
 * builds the record when a run ends, after its last point is measured: the outcome, the
 * frames and points, the run's attention items, the session folder and its size, the mount
 * after the end action, and the calibration of tonight's lights (darks per (exposure,
 * gain), biases per gain, each with the time it takes at tonight's MEASURED cost per frame:
 * the Seestar's overhead is tens of seconds, finding 1). The record rides on the `sequence`
 * record (`wrapup`) and `GET /api/sequence/wrapup`; "Prepare in Plan" is `POST
 * /api/sequence/calibration-plan` (it replaces the draft and returns the draft it replaced,
 * for an Undo; nothing starts).
 *
 * Here: the tolerant check of the record and the words the card shows. No calibration
 * number is computed on the client.
 */

import type { RequestOptions } from '../../api/client';
import type { SequencePlan } from '../../api/plan';
import type { SequenceResult } from '../../api/sequence';
import type { MountPhase } from '../../api/types';
import { int, seconds } from '../../format/number';
import { clockUtc, duration } from '../../format/time';

export interface CalibEntry {
  kind: 'dark' | 'bias';
  exposure_s: number;
  gain: number;
  count: number;
  /** Frames of this kind already taken tonight (the preflight's count). */
  existing: number;
  estimate_s: number | null;
}

export interface WrapUpView {
  runId: string | null;
  objectName: string | null;
  started: number | null;
  ended: number | null;
  /** `lights`: the Light frames saved (frames.by_type.Light), null when the server does not say. */
  frames: { saved: number; total: number | null; lights: number | null };
  points: { target: number; all: number; flagged: number; measured: number; skipped: { field_lost: number; lock_lost: number; other: number } } | null;
  attention: { critical: number; attention: number; info: number } | null;
  runRoot: string | null;
  runFolder: string | null;
  runBytes: number | null;
  mount: { connected: boolean; state: string | null; tracking: boolean | null; endAction: string | null } | null;
  calibration: { entries: CalibEntry[]; overhead: number | null; cadence: number | null; darkSlot: boolean; note: string | null } | null;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const int0 = (v: unknown): number => (typeof v === 'number' && Number.isInteger(v) ? v : 0);
const str = (v: unknown): string | null => (typeof v === 'string' && v !== '' ? v : null);
const timeOf = (v: unknown): number | null => {
  if (typeof v !== 'string' || !v) return null;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? ms / 1000 : null;
};

function entries(v: unknown, kind: 'dark' | 'bias'): CalibEntry[] {
  if (!Array.isArray(v)) return [];
  const out: CalibEntry[] = [];
  for (const e of v) {
    if (!isObj(e)) continue;
    const exp = num(e.exposure_s);
    const gain = num(e.gain);
    const count = num(e.count);
    if (exp === null || gain === null || count === null) continue;
    out.push({ kind, exposure_s: exp, gain, count, existing: int0(e.existing), estimate_s: num(e.estimate_s) });
  }
  return out;
}

/**
 * The server's WrapUp (the `wrapup` of a `sequence` record, or the record itself), or null
 * (absent, or `null` for the moment the server measures the last frames).
 */
export function checkWrapUp(m: unknown): WrapUpView | null {
  if (!isObj(m)) return null;
  const v = isObj(m.wrapup) ? m.wrapup : isObj(m.sequence) && isObj(m.sequence.wrapup) ? m.sequence.wrapup : m;
  const fr = isObj(v.frames) ? v.frames : null;
  if (!fr || num(fr.saved) === null || typeof v.ended_utc !== 'string') return null;
  const pt = isObj(v.points) ? v.points : null;
  const sk = pt && isObj(pt.frames_skipped) ? pt.frames_skipped : {};
  const at = isObj(v.attention) ? v.attention : null;
  const mo = isObj(v.mount) ? v.mount : null;
  const ca = isObj(v.calibration) ? v.calibration : null;
  return {
    runId: str(v.run_id),
    objectName: str(v.object_name),
    started: timeOf(v.started_utc),
    ended: timeOf(v.ended_utc),
    frames: { saved: int0(fr.saved), total: num(fr.total), lights: isObj(fr.by_type) ? num(fr.by_type.Light) : null },
    points: pt
      ? { target: int0(pt.target), all: int0(pt.all), flagged: int0(pt.flagged), measured: int0(pt.frames_measured), skipped: { field_lost: int0(sk.field_lost), lock_lost: int0(sk.lock_lost), other: int0(sk.other) } }
      : null,
    attention: at ? { critical: int0(at.critical), attention: int0(at.attention), info: int0(at.info) } : null,
    runRoot: str(v.run_root),
    runFolder: str(v.run_folder),
    runBytes: num(v.run_bytes),
    mount: mo ? { connected: mo.connected === true, state: str(mo.state), tracking: typeof mo.tracking === 'boolean' ? mo.tracking : null, endAction: str(mo.end_action) } : null,
    calibration: ca
      ? { entries: [...entries(ca.darks, 'dark'), ...entries(ca.biases, 'bias')], overhead: num(ca.overhead_s), cadence: num(ca.cadence_s), darkSlot: ca.dark_slot === true, note: str(ca.note) }
      : null,
  };
}

/** What the calls need from ArgosClient (tests pass a fake). */
export interface WrapClient {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown, options?: RequestOptions): Promise<T>;
}

export const wrapupApi = {
  /** The last run's wrap-up (404 not_found before any run ended). */
  get: async (c: WrapClient, o?: RequestOptions): Promise<WrapUpView | null> => checkWrapUp(await c.request<unknown>('GET', '/api/sequence/wrapup', undefined, o)),
  /**
   * Replace the Plan draft with the calibration steps (409 run_active during a run; 400
   * invalid_argument without a Light step). Resolves to the draft it replaced (for Undo).
   */
  calibrationPlan: async (c: WrapClient, counts: { darks?: number; biases?: number } = {}, o?: RequestOptions): Promise<{ replaced: SequencePlan | null }> => {
    const r = await c.request<unknown>('POST', '/api/sequence/calibration-plan', counts, o);
    const replaced = isObj(r) && isObj(r.replaced) ? (r.replaced as unknown as SequencePlan) : null;
    return { replaced };
  },
};

// -- Words ---------------------------------------------------------------------------------------

/** "20 darks" / "30 biases". */
export function entryTitle(e: CalibEntry): string {
  const one = e.count === 1;
  return `${int(e.count)} ${e.kind === 'dark' ? (one ? 'dark' : 'darks') : one ? 'bias' : 'biases'}`;
}

/** "10.0 s · gain 80 · Dark slot" (biases: "shortest exposure 0.001 s"); tonight's count when some exist. */
export function entryLine(e: CalibEntry, darkSlot: boolean): string {
  const exp = e.kind === 'bias' ? `shortest exposure ${seconds(e.exposure_s)}` : seconds(e.exposure_s);
  const have = e.existing > 0 ? ` · ${int(e.existing)} taken tonight` : '';
  return `${exp} · gain ${e.gain} · ${darkSlot ? 'Dark slot' : 'lid on'}${have}`;
}

/** "≈ 1m 20s" / "≈ 1h 05m" / "time unknown": the Plan's Duration column, so the wrap-up and
 * the Plan it prepares say the same times (wave 6b design review). */
export function aboutText(s: number | null): string {
  if (s === null) return 'time unknown';
  return `≈ ${duration(Math.max(1, s))}`;
}

export function totalEstimate(list: readonly CalibEntry[]): number | null {
  if (!list.length || list.some((e) => e.estimate_s === null)) return null;
  return list.reduce((s, e) => s + (e.estimate_s ?? 0), 0);
}

/** What the mount does now, in one sentence ("Tracking is still on."). */
export function mountLine(mount: { state: MountPhase | string | null; tracking: boolean | null; connected?: boolean } | null, endAction: string | null): { text: string; tracking: boolean } {
  if (!mount || mount.connected === false) return { text: 'The mount is not connected.', tracking: false };
  if (mount.state === 'parked') return { text: 'The mount is parked.', tracking: false };
  if (mount.state === 'slewing') return { text: 'The mount is slewing.', tracking: !!mount.tracking };
  if (mount.tracking) return { text: endAction === 'Stop tracking' ? 'Tracking is still on (the end action did not stop it).' : 'Tracking is still on.', tracking: true };
  if (mount.tracking === false) return { text: 'Tracking is off.', tracking: false };
  return { text: 'The mount state is not known.', tracking: false };
}

/** "RR Lyr · 195 frames of 195 · 20:04–22:54 UTC". */
export function runLine(object: string | null, r: SequenceResult): string {
  const parts: string[] = [];
  if (object) parts.push(object);
  parts.push(`${int(r.frames_saved)} ${r.frames_saved === 1 ? 'frame' : 'frames'}${r.frames_total ? ` of ${int(r.frames_total)}` : ''}`);
  if (r.started_t !== null && r.ended_t !== null) parts.push(`${clockUtc(r.started_t, false)}–${clockUtc(r.ended_t, false)} UTC`);
  return parts.join(' · ');
}

/**
 * "193 target points · 3 flagged · frames without a point: 2 lock lost". With the Light
 * frames saved (`lights`), every frame is accounted for: the measured ones, the skipped ones
 * by reason, and "n not measured" for the rest (no solution yet, the run's last frame; 40
 * frames once read 37 points + 2 lock lost: wave 6b design review).
 */
export function pointsLine(p: WrapUpView['points'], lights: number | null = null): string | null {
  if (!p) return null;
  const parts = [`${int(p.target)} target ${p.target === 1 ? 'point' : 'points'}`];
  if (p.flagged) parts.push(`${int(p.flagged)} flagged`);
  const why: string[] = [];
  if (p.skipped.lock_lost) why.push(`${int(p.skipped.lock_lost)} lock lost`);
  if (p.skipped.field_lost) why.push(`${int(p.skipped.field_lost)} field lost`);
  if (p.skipped.other) why.push(`${int(p.skipped.other)} other`);
  const skipped = p.skipped.lock_lost + p.skipped.field_lost + p.skipped.other;
  const rest = lights !== null ? lights - p.measured - skipped : 0;
  if (rest > 0) why.push(`${int(rest)} not measured`);
  if (why.length) parts.push(`frames without a point: ${why.join(', ')}`);
  return parts.join(' · ');
}

/** "1 critical, 2 attention during the run" or null when none needed the observer. */
export function attentionLine(a: WrapUpView['attention']): string | null {
  if (!a || a.critical + a.attention === 0) return null;
  const parts: string[] = [];
  if (a.critical) parts.push(`${a.critical} critical`);
  if (a.attention) parts.push(`${a.attention} attention`);
  return `${parts.join(', ')} during the run`;
}

/** "3.0 GB" / "412 MB" (decimal units, as the preflight's disk row). */
export function sizeText(bytes: number | null): string | null {
  if (bytes === null || bytes < 0) return null;
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${Math.round(bytes / 1e6)} MB`;
  return `${Math.max(1, Math.round(bytes / 1e3))} kB`;
}
