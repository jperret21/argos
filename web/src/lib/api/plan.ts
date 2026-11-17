/**
 * Plan, client side of API 2 wave 6a (README 4.3 rows A42, A59-A61, A65, A66; contract in
 * argos/server/protocol.md "API 2 routes, wave 6a (Plan)"). The run itself (A62-A64: start,
 * pause, resume, stop, the `sequence` event, preflight) is api/sequence.ts.
 *
 * - The plan is the server's: every edit is one `PUT /api/sequence/plan` of the whole plan;
 *   the answer (PlanRecord) is the plan as stored (never clamped: a value out of range stays
 *   as typed and comes back as an issue), the derived totals, the issues, the lock, the
 *   wheel's names and the camera's limits.
 * - Bodies are strict on the server: the client only ever sends the Plan keys it received
 *   (an unknown key is a 400), so records are rebuilt key by key here.
 * - Records are checked at the edge; a malformed answer is refused with the route's name.
 */

import type { RequestOptions } from './client';

/** The request function of the shared client (ArgosClient.request). */
export interface PlanRequest {
  request<T>(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown, options?: RequestOptions): Promise<T>;
}

// -- Records -------------------------------------------------------------------------------------

/** The frame types of a step (sequencer.py FRAME_TYPES). */
export const FRAME_TYPES = ['Light', 'Dark', 'Flat', 'Bias'] as const;

/** End-of-run mount actions (sequencer.py ON_COMPLETE_CHOICES). */
export const ON_COMPLETE = ['Nothing', 'Stop tracking', 'Park mount'] as const;

/** Name of the wheel's opaque slot (sequencer.py DARK_FILTER_NAME). */
export const DARK_SLOT = 'Dark';

/** One step (SequenceStep, sequencer.py:28-57). Strings stay as the server holds them: an
 * unknown type or filter is shown and flagged, never substituted (06 P11). */
export interface PlanStep {
  enabled: boolean;
  frame_type: string;
  filter_name: string;
  exposure_s: number;
  gain: number;
  count: number;
  interval_s: number;
  /** Start-to-start period (transit series); null = off, then `interval_s` applies. */
  cadence_s: number | null;
  /** Nudge the mount every N frames of the run; 0 = off (Q-P5: column hidden by default). */
  dither_every: number;
}

export type MetaValue = string | number | boolean | null;

/** Plan (protocol "Plan (A59)"): SequencePlan as `plan_to_dict` writes it, `schema`, `start_at_utc`. */
export interface SequencePlan {
  schema?: number;
  object_name: string;
  repeat: number;
  autofocus_every_n: number;
  autofocus_on_filter_change: boolean;
  on_complete: string;
  base_dir: string | null;
  /** Science hand-off (a transit's ephemeris): kept so the run writes observation.json (S5). */
  metadata: Record<string, MetaValue>;
  /** Scheduled start (Q-P2), web only. */
  start_at_utc: string | null;
  steps: PlanStep[];
}

export interface PlanDerived {
  total_frames: number;
  estimate_s: number;
  /** One pass, in plan order; 0 for a step that does not run. */
  per_step_s: number[];
  /** `start_at_utc` when in the future, else now. */
  start_utc: string | null;
  /** start + estimate. */
  end_utc: string | null;
}

/** One problem of the plan, on its field (A59). */
export interface PlanIssue {
  /** 0-based step index, or null for a plan-level field. */
  step: number | null;
  /** "exposure_s", "repeat", "steps", … */
  field: string | null;
  code: string;
  /** "error" blocks Start; "warning" is said and does not block. */
  level: 'error' | 'warning';
  message: string;
}

/** PlanRecord (protocol "Plan (A59)"); also the WS `sequence_plan` snapshot. */
export interface PlanDoc {
  plan: SequencePlan;
  derived: PlanDerived;
  issues: PlanIssue[];
  /** No issue of level "error". */
  ready: boolean;
  /** A run is active: PUT, import and transit plan answer 409 run_active (Q-P9). */
  locked: boolean;
  locked_reason: string | null;
  /** What the last change did ("Planning metadata dropped: …"), in words. */
  notes: string[];
  /** The names a filter cell offers: the wheel's, else the profile's, else Qt's defaults. */
  filters: { names: string[]; source: 'wheel' | 'profile' | 'default' | string };
  /** Exposure and gain ranges the issues use (the camera's, the last camera's, Qt's defaults). */
  limits: { exposure_s: [number, number] | null; gain: [number, number] | null; source: string | null };
  /** sequence_draft.json, null in memory. */
  path: string | null;
  revision: number;
}

/** One preset of the list (A60). */
export interface PresetInfo {
  name: string;
  modified_utc: string | null;
  object_name: string | null;
  steps: number | null;
  total_frames: number | null;
  estimate_s: number | null;
  /** The file cannot be read (Qt's own reasons): listed, not openable. */
  error: string | null;
}

export interface PresetList {
  directory: string | null;
  presets: PresetInfo[];
}

/** Exoplanet (A42, exoplanets.py ExoplanetTarget). */
export interface ExoplanetTarget {
  planet_name: string;
  host_name: string;
  ra_hours: number;
  dec_deg: number;
  period_days: number;
  epoch_bjd_tdb: number;
  duration_hours: number | null;
  depth_percent: number | null;
  period_error_days: number | null;
  epoch_error_days: number | null;
  epoch_system: string;
  source: string;
  retrieved_utc: string | null;
}

/** The five instants of a transit window, by key (UTC ISO, degrees). */
export interface TransitInstants<T> {
  coverage_start: T;
  ingress: T;
  mid: T;
  egress: T;
  coverage_end: T;
}

export interface TransitBody {
  planet_name: string;
  baseline_minutes: number;
  /** Search from that night (YYYY-MM-DD, its solar noon). */
  date?: string;
  /** This transit exactly (plan what was predicted). */
  epoch_number?: number;
  /** Skip transits in daylight or below the limit (Q-P10; server default true). */
  observable_only?: boolean;
}

export interface TransitPlanBody extends TransitBody {
  exposure_s: number;
  cadence_s: number;
  gain: number;
  filter_name: string;
}

/** TransitPrediction (A66). */
export interface TransitPrediction {
  planet: ExoplanetTarget;
  window: {
    epoch_number: number;
    mid_bjd_tdb: number;
    ingress_bjd_tdb: number;
    egress_bjd_tdb: number;
    coverage_start_bjd_tdb: number;
    coverage_end_bjd_tdb: number;
    baseline_minutes: number;
    coverage_hours: number;
  };
  utc: TransitInstants<string>;
  altitude_deg: TransitInstants<number | null>;
  sun_alt_deg: TransitInstants<number | null> | null;
  night: { date: string; dusk_utc: string | null; dawn_utc: string | null } | null;
  observable: { transit: boolean; coverage: boolean };
  /** The part of the coverage dark and above the limit. */
  usable: { start_utc: string; end_utc: string } | null;
  skipped: { epoch_number: number; mid_utc: string; reason: string }[];
  skipped_count: number;
  min_alt_deg: number;
}

// -- Checks --------------------------------------------------------------------------------------

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const numOr = (v: unknown, d: number): number => (isNum(v) ? v : d);
const numOrNull = (v: unknown): number | null => (isNum(v) ? v : null);
const strOrNull = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const pair = (v: unknown): [number, number] | null => (Array.isArray(v) && v.length === 2 && isNum(v[0]) && isNum(v[1]) ? [v[0], v[1]] : null);

/** A wire step rebuilt key by key (only the Step keys: the PUT body is strict). */
export function checkStep(m: unknown): PlanStep | null {
  if (!isObj(m)) return null;
  if (typeof m.enabled !== 'boolean' || typeof m.frame_type !== 'string' || typeof m.filter_name !== 'string') return null;
  if (!isNum(m.exposure_s) || !isNum(m.gain) || !isNum(m.count)) return null;
  return {
    enabled: m.enabled,
    frame_type: m.frame_type,
    filter_name: m.filter_name,
    exposure_s: m.exposure_s,
    gain: m.gain,
    count: m.count,
    interval_s: numOr(m.interval_s, 0),
    cadence_s: numOrNull(m.cadence_s),
    dither_every: numOr(m.dither_every, 0),
  };
}

/** A wire Plan rebuilt key by key (the keys of protocol "Plan", nothing else). */
export function checkPlan(m: unknown): SequencePlan | null {
  if (!isObj(m) || !Array.isArray(m.steps)) return null;
  const steps: PlanStep[] = [];
  for (const s of m.steps) {
    const step = checkStep(s);
    if (!step) return null;
    steps.push(step);
  }
  const metadata: Record<string, MetaValue> = {};
  if (isObj(m.metadata)) {
    for (const [k, v] of Object.entries(m.metadata)) {
      if (v === null || typeof v === 'string' || typeof v === 'boolean' || isNum(v)) metadata[k] = v;
    }
  }
  return {
    ...(isNum(m.schema) ? { schema: m.schema } : {}),
    object_name: typeof m.object_name === 'string' ? m.object_name : '',
    repeat: numOr(m.repeat, 1),
    autofocus_every_n: numOr(m.autofocus_every_n, 0),
    autofocus_on_filter_change: m.autofocus_on_filter_change === true,
    on_complete: typeof m.on_complete === 'string' ? m.on_complete : 'Nothing',
    base_dir: strOrNull(m.base_dir),
    metadata,
    start_at_utc: strOrNull(m.start_at_utc),
    steps,
  };
}

function checkIssue(m: unknown): PlanIssue | null {
  if (!isObj(m) || typeof m.message !== 'string') return null;
  return {
    step: isNum(m.step) ? m.step : null,
    field: typeof m.field === 'string' && m.field ? m.field : null,
    code: typeof m.code === 'string' ? m.code : 'invalid',
    level: m.level === 'warning' ? 'warning' : 'error',
    message: m.message,
  };
}

/** PlanRecord (A59 answer, WS `sequence_plan`); null when the plan is not one. */
export function checkPlanDoc(m: unknown): PlanDoc | null {
  if (!isObj(m)) return null;
  const plan = checkPlan(m.plan);
  if (!plan) return null;
  const d = isObj(m.derived) ? m.derived : {};
  const f = isObj(m.filters) ? m.filters : {};
  const l = isObj(m.limits) ? m.limits : {};
  const issues = Array.isArray(m.issues) ? m.issues.map(checkIssue).filter((i): i is PlanIssue => i !== null) : [];
  return {
    plan,
    derived: {
      total_frames: numOr(d.total_frames, 0),
      estimate_s: numOr(d.estimate_s, 0),
      per_step_s: Array.isArray(d.per_step_s) ? d.per_step_s.map((v) => numOr(v, 0)) : [],
      start_utc: strOrNull(d.start_utc),
      end_utc: strOrNull(d.end_utc),
    },
    issues,
    ready: typeof m.ready === 'boolean' ? m.ready : !issues.some((i) => i.level === 'error'),
    locked: m.locked === true,
    locked_reason: strOrNull(m.locked_reason),
    notes: Array.isArray(m.notes) ? m.notes.filter((n): n is string => typeof n === 'string') : [],
    filters: {
      names: Array.isArray(f.names) ? f.names.filter((n): n is string => typeof n === 'string') : [],
      source: typeof f.source === 'string' ? f.source : 'default',
    },
    limits: { exposure_s: pair(l.exposure_s), gain: pair(l.gain), source: strOrNull(l.source) },
    path: strOrNull(m.path),
    revision: numOr(m.revision, 0),
  };
}

export function checkPresetList(m: unknown): PresetList {
  const list = isObj(m) && Array.isArray(m.presets) ? m.presets : [];
  return {
    directory: isObj(m) ? strOrNull(m.directory) : null,
    presets: list
      .filter((p): p is Record<string, unknown> => isObj(p) && typeof p.name === 'string')
      .map((p) => ({
        name: p.name as string,
        modified_utc: strOrNull(p.modified_utc),
        object_name: strOrNull(p.object_name),
        steps: numOrNull(p.steps),
        total_frames: numOrNull(p.total_frames),
        estimate_s: numOrNull(p.estimate_s),
        error: strOrNull(p.error),
      })),
  };
}

export function checkExoplanet(m: unknown): ExoplanetTarget | null {
  if (!isObj(m) || typeof m.planet_name !== 'string' || !isNum(m.ra_hours) || !isNum(m.dec_deg)) return null;
  if (!isNum(m.period_days) || !isNum(m.epoch_bjd_tdb)) return null;
  return {
    planet_name: m.planet_name,
    host_name: typeof m.host_name === 'string' ? m.host_name : m.planet_name,
    ra_hours: m.ra_hours,
    dec_deg: m.dec_deg,
    period_days: m.period_days,
    epoch_bjd_tdb: m.epoch_bjd_tdb,
    duration_hours: numOrNull(m.duration_hours),
    depth_percent: numOrNull(m.depth_percent),
    period_error_days: numOrNull(m.period_error_days),
    epoch_error_days: numOrNull(m.epoch_error_days),
    epoch_system: typeof m.epoch_system === 'string' ? m.epoch_system : '',
    source: typeof m.source === 'string' ? m.source : '',
    retrieved_utc: strOrNull(m.retrieved_utc),
  };
}

const INSTANTS = ['coverage_start', 'ingress', 'mid', 'egress', 'coverage_end'] as const;

function instants<T>(m: unknown, pick: (v: unknown) => T | null): TransitInstants<T> | null {
  if (!isObj(m)) return null;
  const out: Partial<TransitInstants<T>> = {};
  for (const k of INSTANTS) {
    const v = pick(m[k]);
    if (v === null) return null;
    out[k] = v;
  }
  return out as TransitInstants<T>;
}

export function checkPrediction(m: unknown): TransitPrediction | null {
  if (!isObj(m)) return null;
  const planet = checkExoplanet(m.planet);
  const w = isObj(m.window) ? m.window : null;
  const utc = instants(m.utc, strOrNull);
  if (!planet || !w || !utc || !isNum(w.epoch_number) || !isNum(w.mid_bjd_tdb)) return null;
  const alt = instants(m.altitude_deg, (v) => (isNum(v) ? v : v === null ? (null as unknown as number) : null));
  const sun = instants(m.sun_alt_deg, (v) => (isNum(v) ? v : v === null ? (null as unknown as number) : null));
  const nightObj = isObj(m.night) && typeof m.night.date === 'string' ? m.night : null;
  const obs = isObj(m.observable) ? m.observable : {};
  const usable = isObj(m.usable) && typeof m.usable.start_utc === 'string' && typeof m.usable.end_utc === 'string' ? { start_utc: m.usable.start_utc, end_utc: m.usable.end_utc } : null;
  return {
    planet,
    window: {
      epoch_number: w.epoch_number,
      mid_bjd_tdb: w.mid_bjd_tdb,
      ingress_bjd_tdb: numOr(w.ingress_bjd_tdb, w.mid_bjd_tdb),
      egress_bjd_tdb: numOr(w.egress_bjd_tdb, w.mid_bjd_tdb),
      coverage_start_bjd_tdb: numOr(w.coverage_start_bjd_tdb, w.mid_bjd_tdb),
      coverage_end_bjd_tdb: numOr(w.coverage_end_bjd_tdb, w.mid_bjd_tdb),
      baseline_minutes: numOr(w.baseline_minutes, 0),
      coverage_hours: numOr(w.coverage_hours, 0),
    },
    utc,
    altitude_deg: alt ?? { coverage_start: null, ingress: null, mid: null, egress: null, coverage_end: null },
    sun_alt_deg: sun,
    night: nightObj ? { date: nightObj.date as string, dusk_utc: strOrNull(nightObj.dusk_utc), dawn_utc: strOrNull(nightObj.dawn_utc) } : null,
    observable: { transit: obs.transit === true, coverage: obs.coverage === true },
    usable,
    skipped: Array.isArray(m.skipped)
      ? m.skipped
          .filter((s): s is Record<string, unknown> => isObj(s) && isNum(s.epoch_number) && typeof s.mid_utc === 'string')
          .map((s) => ({ epoch_number: s.epoch_number as number, mid_utc: s.mid_utc as string, reason: typeof s.reason === 'string' ? s.reason : '' }))
      : [],
    skipped_count: numOr(m.skipped_count, 0),
    min_alt_deg: numOr(m.min_alt_deg, 30),
  };
}

/** Refuse an answer that does not match the contract, naming the route. */
function must<T>(value: T | null, route: string): T {
  if (value === null) throw new Error(`Unexpected answer from ${route}`);
  return value;
}

// -- Routes --------------------------------------------------------------------------------------

const enc = encodeURIComponent;
/** Two NASA queries of up to 12 s each (A42), with room for the prediction. */
const SLOW = 30_000;

export class PlanApi {
  constructor(private readonly client: PlanRequest) {}

  /** A59: the persisted draft (sequence_draft.json, Q-P3). */
  async plan(signal?: AbortSignal): Promise<PlanDoc> {
    return must(checkPlanDoc(await this.client.request<unknown>('GET', '/api/sequence/plan', undefined, { signal })), 'GET /api/sequence/plan');
  }

  /** A59: write the whole plan; the answer is the plan as stored, with derived values and issues. */
  async putPlan(plan: SequencePlan): Promise<PlanDoc> {
    return must(checkPlanDoc(await this.client.request<unknown>('PUT', '/api/sequence/plan', plan)), 'PUT /api/sequence/plan');
  }

  /** A60. */
  async presets(signal?: AbortSignal): Promise<PresetList> {
    return checkPresetList(await this.client.request<unknown>('GET', '/api/sequence/presets', undefined, { signal }));
  }

  /** Save the draft under a name (no body: the server's draft); `409 file_exists` unless `overwrite`. */
  async savePreset(name: string, overwrite: boolean, plan?: SequencePlan): Promise<PresetList> {
    return checkPresetList(await this.client.request<unknown>('PUT', `/api/sequence/presets/${enc(name)}${overwrite ? '?overwrite=true' : ''}`, plan));
  }

  /** A preset's plan (for Undo of a delete). */
  async preset(name: string): Promise<SequencePlan> {
    const m = await this.client.request<unknown>('GET', `/api/sequence/presets/${enc(name)}`);
    return must(checkPlan(isObj(m) ? m.plan : null), 'GET /api/sequence/presets/{name}');
  }

  async deletePreset(name: string): Promise<PresetList> {
    return checkPresetList(await this.client.request<unknown>('DELETE', `/api/sequence/presets/${enc(name)}`));
  }

  /** A61: a preset or a file becomes the draft (as Qt's Load preset: metadata not restored). */
  async importPlan(from: { preset: string } | { path: string }): Promise<PlanDoc> {
    return must(checkPlanDoc(await this.client.request<unknown>('POST', '/api/sequence/plan/import', from)), 'POST /api/sequence/plan/import');
  }

  /** A61: the draft in Qt's format; `409 file_exists` unless `overwrite`. */
  exportPlan(path: string, overwrite = false): Promise<{ path: string }> {
    return this.client.request('POST', '/api/sequence/plan/export', { path, overwrite });
  }

  /** A42: offline names (the cache) for the typed text. */
  async exoplanetSuggest(q: string, signal?: AbortSignal): Promise<string[]> {
    const m = await this.client.request<unknown>('GET', `/api/exoplanets/suggest?q=${enc(q)}&limit=8`, undefined, { signal });
    const names = isObj(m) && Array.isArray(m.names) ? m.names : [];
    return names.filter((n): n is string => typeof n === 'string');
  }

  /** A42: the cache, then the NASA Exoplanet Archive (up to 2 × 12 s). */
  async exoplanetLookup(q: string, signal?: AbortSignal): Promise<ExoplanetTarget> {
    return must(checkExoplanet(await this.client.request<unknown>('GET', `/api/exoplanets/lookup?q=${enc(q)}`, undefined, { signal, timeoutMs: SLOW })), 'GET /api/exoplanets/lookup');
  }

  /** A66: the transit to observe (that night's, or the next observable one, Q-P10). */
  async transitPredict(body: TransitBody, signal?: AbortSignal): Promise<TransitPrediction> {
    return must(checkPrediction(await this.client.request<unknown>('POST', '/api/transit/predict', body, { signal, timeoutMs: SLOW })), 'POST /api/transit/predict');
  }

  /** A66: the transit series becomes the draft, its ephemeris in `metadata` (S5). */
  async transitPlan(body: TransitPlanBody): Promise<{ plan: PlanDoc; prediction: TransitPrediction | null }> {
    const m = await this.client.request<unknown>('POST', '/api/transit/plan', body, { timeoutMs: SLOW });
    const plan = must(checkPlanDoc(isObj(m) ? m.plan : null), 'POST /api/transit/plan');
    return { plan, prediction: checkPrediction(isObj(m) ? m.prediction : null) };
  }
}
