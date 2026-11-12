/**
 * Sequences on the wire (API 2, wave 6a; README section 4.3 rows A62-A65; contract in
 * argos/server/protocol.md "API 2 routes, wave 6a: sequences" and "Visibility"): the run
 * transport, the `sequence` state, the preflight and the night's visibility. The plan,
 * presets, import / export, exoplanets and transits are api/plan.ts.
 *
 * The wire records are checked tolerantly (a newer server may add fields; a record that
 * lacks a required one is refused, never guessed) and normalised once for the views:
 * - times are unix seconds (`*_t`) beside nothing else: the views never parse dates;
 * - state names and indices are the wire's: `waiting` is a scheduled start (Q-P2),
 *   `step_index` is 0-based, `pass_index` 1-based.
 * Calls go through ArgosClient.request (token, timeouts, ApiError: `409 run_active`,
 * `409 busy` with `owner`, `409 preflight_blocked`, `409 not_running`, `409 site_missing`,
 * `400 invalid_argument`; the server's sentence is shown verbatim).
 */

import type { ApiError, RequestOptions } from './client';
import { checkPlan, checkStep, type PlanStep, type SequencePlan } from './plan';

/** What the calls need from ArgosClient (tests pass a fake). */
export interface SeqClient {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown, options?: RequestOptions): Promise<T>;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const int = (v: unknown): number | null => (typeof v === 'number' && Number.isInteger(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v !== '' ? v : null);

/** Unix seconds of an ISO 8601 UTC time; null when absent or unreadable (never "now"). */
export function unixOf(iso: unknown): number | null {
  if (typeof iso !== 'string' || !iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** ISO 8601 UTC of unix seconds, to the second ("2026-11-12T21:30:00Z"). */
export function isoOf(t: number): string {
  return new Date(Math.round(t) * 1000).toISOString().replace('.000Z', 'Z');
}

// -- Run state (A63) --------------------------------------------------------------------------------

/**
 * The wire's states (`waiting`: a scheduled start, Q-P2). `scheduled` is never produced: it
 * stays in the union only while the Plan screen's model still tests for it (an early name).
 */
export type SeqStateName = 'idle' | 'waiting' | 'scheduled' | 'running' | 'pausing' | 'paused' | 'autofocus' | 'stopping';
const STATES: Record<string, SeqStateName> = {
  idle: 'idle',
  waiting: 'waiting',
  scheduled: 'waiting',
  running: 'running',
  pausing: 'pausing',
  paused: 'paused',
  autofocus: 'autofocus',
  stopping: 'stopping',
};

/** RunResult: how the last run ended, kept until the next start. */
export interface SequenceResult {
  completed: boolean;
  /** "completed" | "stopped" | "cancelled" | "camera_error" | "device_lost" | "wheel_error" | "save_error" | "autofocus_timeout" | "refused" | "shutdown". */
  reason: string | null;
  /** For the observer, shown verbatim. */
  message: string | null;
  frames_saved: number;
  frames_total: number | null;
  run_root: string | null;
  started_t: number | null;
  ended_utc: string | null;
  ended_t: number | null;
  /** The plan's end action (from the record holding the result). */
  on_complete: string | null;
}

export type SequenceStep = PlanStep;

export interface SequenceState {
  state: SeqStateName;
  /** The plan is locked (state != idle). */
  active: boolean;
  object_name: string | null;
  run_id: string | null;
  run_root: string | null;
  /** The plan the run executes, frozen at start. */
  plan: SequencePlan | null;
  /** 0-based index in plan.steps. */
  step_index: number | null;
  steps_total: number | null;
  step: SequenceStep | null;
  /** 1-based pass of the plan (`repeat`), as on the wire. */
  pass_index: number | null;
  repeat: number | null;
  frames_done: number;
  frames_total: number;
  /** Time left, s (time per frame x frames left, pauses and autofocus excluded). */
  eta_s: number | null;
  /** The server's end time (now + eta; scheduled: start + estimate). */
  end_t: number | null;
  started_t: number | null;
  /** A scheduled start (Q-P2). */
  start_at_t: number | null;
  /** The sub exposing. */
  current: { exposure_s: number; started_t: number | null; filter: string | null; frame_type: string | null; index: number | null } | null;
  /** DATE-OBS of the newest saved sub, when it was written, its file. */
  last_frame_t: number | null;
  last_saved_t: number | null;
  last_frame_name: string | null;
  /** Planned start-to-start of the current step (its cadence, else exposure + interval + 3 s). */
  cadence_s: number | null;
  /** Median start-to-start of the step's last subs, pauses and autofocus excluded; null before two. */
  observed_cadence_s: number | null;
  autofocus_every_n: number | null;
  /** Subs before the next periodic autofocus (null: none planned or countable). */
  next_autofocus_in: number | null;
  autofocus_runs: number;
  paused_by: 'observer' | 'motion' | null;
  /** "Nothing" | "Stop tracking" | "Park mount". */
  on_complete: string | null;
  last_result: SequenceResult | null;
  revision: number | null;
}

function checkResult(v: unknown, onComplete: string | null): SequenceResult | null {
  if (!isObj(v)) return null;
  const ended = str(v.ended_utc);
  return {
    completed: v.completed === true,
    reason: str(v.reason),
    message: str(v.message),
    frames_saved: int(v.frames_saved) ?? 0,
    frames_total: int(v.frames_total),
    run_root: str(v.run_root),
    started_t: unixOf(v.started_utc),
    ended_utc: ended,
    ended_t: unixOf(ended),
    on_complete: onComplete,
  };
}

/**
 * The `sequence` record (the WS message, `{"sequence": …}`, or `GET /api/sequence`). Null when
 * it is not one: unknown state, missing counts (the status record's summary has none).
 */
export function checkSequence(m: unknown): SequenceState | null {
  if (!isObj(m)) return null;
  const v = isObj(m.sequence) ? m.sequence : m;
  const state = typeof v.state === 'string' ? STATES[v.state] : undefined;
  const done = int(v.frames_done);
  const total = int(v.frames_total);
  if (!state || done === null || total === null) return null;
  const plan = checkPlan(v.plan);
  const cur = isObj(v.current) ? v.current : null;
  const curExp = cur ? num(cur.exposure_s) : null;
  const af = isObj(v.next_autofocus) ? v.next_autofocus : null;
  const onComplete = str(v.end_action) ?? plan?.on_complete ?? null;
  const paused = v.paused_by === 'observer' || v.paused_by === 'motion' ? v.paused_by : null;
  return {
    state,
    active: typeof v.active === 'boolean' ? v.active : state !== 'idle',
    object_name: str(v.object_name),
    run_id: str(v.run_id),
    run_root: str(v.run_root),
    plan,
    step_index: int(v.step_index),
    steps_total: plan ? plan.steps.length : null,
    step: checkStep(v.step),
    pass_index: int(v.pass_index),
    repeat: int(v.repeat) ?? plan?.repeat ?? null,
    frames_done: done,
    frames_total: total,
    eta_s: num(v.eta_s),
    end_t: unixOf(v.end_utc),
    started_t: unixOf(v.started_utc),
    start_at_t: unixOf(v.start_at_utc),
    current:
      cur && curExp !== null
        ? { exposure_s: curExp, started_t: unixOf(cur.started_utc), filter: str(cur.filter), frame_type: str(cur.frame_type), index: int(cur.index) }
        : null,
    last_frame_t: unixOf(v.last_frame_utc),
    last_saved_t: unixOf(v.last_saved_utc),
    last_frame_name: str(v.last_frame_name),
    cadence_s: num(v.cadence_s),
    observed_cadence_s: num(v.observed_cadence_s),
    autofocus_every_n: plan ? plan.autofocus_every_n : int(v.autofocus_every_n),
    next_autofocus_in: af ? int(af.in_frames) : null,
    autofocus_runs: int(v.autofocus_runs) ?? 0,
    paused_by: paused,
    on_complete: onComplete,
    last_result: checkResult(v.last_result, onComplete),
    revision: int(v.revision),
  };
}

// -- Preflight (A64) --------------------------------------------------------------------------------

export type PreflightLevel = 'ok' | 'note' | 'block';
const LEVELS: ReadonlySet<string> = new Set(['ok', 'note', 'block']);

/** One check: run, camera, plan, start_at, object, mount, site, wheel, focuser, altitude, output, disk, calibration, lid. */
export interface PreflightItem {
  id: string;
  level: PreflightLevel;
  /** The check's name in words when the server gives one; the client names the known ids. */
  label: string | null;
  message: string;
}

export interface Preflight {
  checks: PreflightItem[];
  /** The worst level (the server's, else the checks'). */
  level: PreflightLevel;
  can_start: boolean;
  frames_total: number | null;
  estimate_s: number | null;
  start_t: number | null;
  end_t: number | null;
  bytes_needed: number | null;
  bytes_free: number | null;
}

function checkItem(r: unknown): PreflightItem | null {
  if (!isObj(r) || typeof r.id !== 'string' || typeof r.level !== 'string' || !LEVELS.has(r.level)) return null;
  return { id: r.id, level: r.level as PreflightLevel, label: str(r.label), message: typeof r.message === 'string' ? r.message : '' };
}

/** The preflight answer; a bare list of checks is read too. Null when it is neither. */
export function checkPreflight(v: unknown): Preflight | null {
  const list = isObj(v) && Array.isArray(v.checks) ? v.checks : Array.isArray(v) ? v : null;
  if (!list) return null;
  const checks = list.map(checkItem).filter((c): c is PreflightItem => c !== null);
  const o = isObj(v) ? v : {};
  const worst: PreflightLevel = checks.some((c) => c.level === 'block') ? 'block' : checks.some((c) => c.level === 'note') ? 'note' : 'ok';
  const level = typeof o.level === 'string' && LEVELS.has(o.level) ? (o.level as PreflightLevel) : worst;
  return {
    checks,
    level,
    can_start: typeof o.can_start === 'boolean' ? o.can_start : level !== 'block',
    frames_total: int(o.frames_total),
    estimate_s: num(o.estimate_s),
    start_t: unixOf(o.start_utc),
    end_t: unixOf(o.end_utc),
    bytes_needed: num(o.bytes_needed),
    bytes_free: num(o.bytes_free),
  };
}

// -- Visibility (A65) -------------------------------------------------------------------------------

export interface TimeSpan {
  start: number;
  end: number;
}

/** A65 checked: unix seconds and degrees in typed arrays (one allocation per answer). */
export interface Visibility {
  siteName: string | null;
  /** The evening's date (YYYY-MM-DD; the night runs from solar noon to solar noon, S26). */
  night: string | null;
  t: Float64Array;
  alt: Float64Array;
  /** Sun altitude per sample (twilight steps); null when a sample lacks it. */
  sun: Float64Array | null;
  peak: { t: number; alt: number } | null;
  /** The longest part above the limit in the astronomical night, and every part. */
  window: TimeSpan | null;
  windows: TimeSpan[];
  minAlt: number;
  /** Astronomical dusk to dawn (Q-P6); null where the Sun never gets 18° below. */
  dark: TimeSpan | null;
  /** The server's notes, verbatim ("the Sun never gets 18° below the horizon…"). */
  notes: string[];
}

function span(v: unknown, a = 'start_utc', b = 'end_utc'): TimeSpan | null {
  if (!isObj(v)) return null;
  const s = unixOf(v[a]);
  const e = unixOf(v[b]);
  return s !== null && e !== null && e > s ? { start: s, end: e } : null;
}

export function checkVisibility(v: unknown): Visibility | null {
  if (!isObj(v) || !Array.isArray(v.samples)) return null;
  const rows = v.samples.filter((s): s is Record<string, unknown> => isObj(s) && unixOf(s.t_utc) !== null && num(s.alt_deg) !== null);
  if (rows.length < 2) return null;
  const n = rows.length;
  const t = new Float64Array(n);
  const alt = new Float64Array(n);
  const hasSun = rows.every((s) => num(s.sun_alt_deg) !== null);
  const sun = hasSun ? new Float64Array(n) : null;
  rows.forEach((s, i) => {
    t[i] = unixOf(s.t_utc) as number;
    alt[i] = s.alt_deg as number;
    if (sun) sun[i] = s.sun_alt_deg as number;
  });
  const pk = isObj(v.peak) ? { t: unixOf(v.peak.t_utc), alt: num(v.peak.alt_deg) } : null;
  const night = isObj(v.night) ? v.night : null;
  return {
    siteName: isObj(v.site) ? str(v.site.name) : null,
    night: night ? str(night.date) : str(v.night),
    t,
    alt,
    sun,
    peak: pk && pk.t !== null && pk.alt !== null ? { t: pk.t, alt: pk.alt } : null,
    window: span(v.window),
    windows: Array.isArray(v.windows) ? v.windows.map((w) => span(w)).filter((w): w is TimeSpan => w !== null) : [],
    minAlt: num(v.min_alt_deg) ?? 30,
    dark: span(night, 'dusk_utc', 'dawn_utc'),
    notes: Array.isArray(v.notes) ? v.notes.filter((x): x is string => typeof x === 'string' && x !== '') : [],
  };
}

/** A transit as a timeline draws it (unix s): coverage (baselines included) and the transit itself. */
export interface TransitSpans {
  coverageStart: number;
  ingress: number;
  mid: number;
  egress: number;
  coverageEnd: number;
}

// -- Calls ------------------------------------------------------------------------------------------

const q = encodeURIComponent;

/** The `409 run_active` refusal (a mount motion, a geometry change or a plan edit while a run is active). */
export function isRunActive(err: unknown): err is ApiError {
  return isObj(err) && (err as { status?: unknown }).status === 409 && (err as { code?: unknown }).code === 'run_active';
}

export const sequenceApi = {
  /** A63 snapshot (also sent on the socket to a client that connects). */
  state: async (c: SeqClient, o?: RequestOptions) => checkSequence(await c.request<unknown>('GET', '/api/sequence', undefined, o)),
  /** A62. Without `startAt` the draft's own start time applies; null starts now; a time schedules (Q-P2). */
  start: (c: SeqClient, startAt?: number | null, o?: RequestOptions) =>
    c.request<unknown>('POST', '/api/sequence/start', startAt === undefined ? {} : { start_at_utc: startAt === null ? null : isoOf(startAt) }, o),
  pause: (c: SeqClient, o?: RequestOptions) => c.request<unknown>('POST', '/api/sequence/pause', {}, o),
  resume: (c: SeqClient, o?: RequestOptions) => c.request<unknown>('POST', '/api/sequence/resume', {}, o),
  stop: (c: SeqClient, o?: RequestOptions) => c.request<unknown>('POST', '/api/sequence/stop', {}, o),
  /** A64, for a start now or at `startAt`. */
  preflight: async (c: SeqClient, startAt: number | null = null, o?: RequestOptions) =>
    checkPreflight(await c.request<unknown>('GET', `/api/sequence/preflight${startAt !== null ? `?start_at_utc=${q(isoOf(startAt))}` : ''}`, undefined, o)),
  /** A65 for the client-chosen night (S26); `min_alt_deg` only to preview another limit. */
  visibility: async (c: SeqClient, p: { ra_hours: number; dec_deg: number; night?: string | null; step_min?: number; min_alt_deg?: number }, o?: RequestOptions) => {
    const qs = [`ra_hours=${p.ra_hours}`, `dec_deg=${p.dec_deg}`];
    if (p.night) qs.push(`night=${q(p.night)}`);
    if (p.step_min) qs.push(`step_min=${p.step_min}`);
    if (p.min_alt_deg !== undefined) qs.push(`min_alt_deg=${p.min_alt_deg}`);
    return checkVisibility(await c.request<unknown>('GET', `/api/visibility?${qs.join('&')}`, undefined, o));
  },
};
