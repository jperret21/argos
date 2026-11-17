/**
 * Deterministic fixtures of the Plan screen for the gallery (development only): a T CrB plan
 * (two Light steps and a Dark step), the same plan with the issues the server would list, a
 * running state, the preset list, a transit prediction of HD 189733 b. Synthetic: the numbers
 * are shaped like the server's (A59, A60, A66), not computed by it.
 */

import { checkPlanDoc, checkPrediction, type PlanDoc, type PlanIssue, type PlanStep, type PresetInfo, type SequencePlan, type TransitPrediction } from '../../api/plan';
import type { Observation } from '../../api/types';
import { indexIssues, type RowRun } from '../model';

export const STEP = (over: Partial<PlanStep> = {}): PlanStep => ({
  enabled: true,
  frame_type: 'Light',
  filter_name: 'IR',
  exposure_s: 10,
  gain: 80,
  count: 30,
  interval_s: 0,
  cadence_s: null,
  dither_every: 0,
  ...over,
});

export const STEPS: PlanStep[] = [
  STEP({ exposure_s: 10, count: 30 }),
  STEP({ filter_name: 'LP', exposure_s: 30, count: 10 }),
  STEP({ enabled: false, frame_type: 'Dark', filter_name: 'Dark', exposure_s: 30, count: 10 }),
];

/** Per step: count × (cadence, else exposure + interval + 3 s); 0 when disabled (sequencer.py). */
export const PER_STEP = (steps: readonly PlanStep[]) => steps.map((s) => (s.enabled ? s.count * (s.cadence_s ?? s.exposure_s + s.interval_s + 3) : 0));

/** Steps with what the server flags: a value out of range kept as typed, a short cadence, a
 * filter the wheel does not have, a Light step on the opaque slot. */
export const BAD_STEPS: PlanStep[] = [
  STEP({ exposure_s: 9999, count: 30 }),
  STEP({ filter_name: 'LP', exposure_s: 30, count: 10, cadence_s: 20, interval_s: 2 }),
  STEP({ filter_name: 'Ha', exposure_s: 60, count: 5 }),
  STEP({ filter_name: 'Dark', exposure_s: 10, count: 5 }),
];

export const BAD_ISSUES: PlanIssue[] = [
  { step: 0, field: 'exposure_s', code: 'out_of_range', level: 'error', message: 'Exposure 9999 s is outside the camera range 0.01-600 s.' },
  { step: 1, field: 'cadence_s', code: 'cadence_short', level: 'error', message: 'Cadence 20 s is shorter than the 30 s exposure.' },
  { step: 1, field: 'interval_s', code: 'interval_ignored', level: 'warning', message: 'A cadence is set: the interval is not used.' },
  { step: 2, field: 'filter_name', code: 'unknown_filter', level: 'error', message: 'Ha is not a slot of the wheel (Dark, IR, LP).' },
  { step: 3, field: 'filter_name', code: 'dark_slot', level: 'warning', message: 'A Light step on the opaque Dark slot takes black frames.' },
  { step: null, field: 'repeat', code: 'out_of_range', level: 'error', message: 'Repeat 0 is outside 1-999.' },
  { step: null, field: 'object_name', code: 'no_object', level: 'warning', message: 'No object name: frames and the run folder will say Unknown.' },
];

export const ISSUES_OK = indexIssues([]);
export const ISSUES_BAD = indexIssues(BAD_ISSUES);

export const PLAN: SequencePlan = {
  object_name: 'T CrB',
  repeat: 1,
  autofocus_every_n: 0,
  autofocus_on_filter_change: false,
  on_complete: 'Park mount',
  base_dir: null,
  metadata: {},
  start_at_utc: null,
  steps: STEPS,
};

export const PLAN_BAD: SequencePlan = { ...PLAN, object_name: '', repeat: 0, autofocus_every_n: 20, autofocus_on_filter_change: true, on_complete: 'Nothing', steps: BAD_STEPS };

export const DOC: PlanDoc = checkPlanDoc({
  plan: PLAN,
  derived: { total_frames: 40, estimate_s: 720, per_step_s: PER_STEP(STEPS), start_utc: '2026-11-12T20:30:00Z', end_utc: '2026-11-12T20:42:00Z' },
  issues: [],
  ready: true,
  locked: false,
  locked_reason: null,
  notes: [],
  filters: { names: ['Dark', 'IR', 'LP'], source: 'wheel' },
  limits: { exposure_s: [0.01, 600], gain: [0, 600], source: 'camera' },
  path: null,
  revision: 3,
}) as PlanDoc;

export const WHEEL = ['Dark', 'IR', 'LP'];

/** A run on step 2, frame 37 of 40 (06 2.3.2). */
export const PROGRESS: RowRun[] = [
  { kind: 'done', done: 30, total: 30 },
  { kind: 'active', done: 7, total: 10 },
  { kind: 'skipped', done: 0, total: 10 },
];

export const PRESETS: PresetInfo[] = [
  { name: 'T CrB nightly', modified_utc: '2026-10-28T21:02:00Z', object_name: 'T CrB', steps: 2, total_frames: 40, estimate_s: 720, error: null },
  { name: 'Darks 30 s x 20', modified_utc: '2026-10-12T08:40:00Z', object_name: null, steps: 1, total_frames: 20, estimate_s: 660, error: null },
  { name: 'Transit HD 189733 b', modified_utc: '2026-09-30T19:15:00Z', object_name: 'HD 189733', steps: 1, total_frames: 1063, estimate_s: 13819, error: null },
  { name: 'old-qt-preset', modified_utc: '2026-06-02T22:10:00Z', object_name: null, steps: null, total_frames: null, estimate_s: null, error: "unknown step key 'binning'" },
];

export const OBSERVATION: Observation = {
  object_name: 'T CrB',
  target: { name: 'T CrB', ra_hours: 15.99172, dec_deg: 25.92028, object_type: 'V*', type_label: 'Variable star', is_variable: true, source: 'CDS Sesame · cached', programme: 'variable' },
  photometry_target: null,
  locked: false,
  locked_reason: null,
  revision: 2,
};

const PLANET = {
  planet_name: 'HD 189733 b',
  host_name: 'HD 189733',
  ra_hours: 20.00692,
  dec_deg: 22.71083,
  period_days: 2.21857567,
  epoch_bjd_tdb: 2454279.436714,
  duration_hours: 1.84,
  depth_percent: 2.4,
  period_error_days: 1.5e-7,
  epoch_error_days: 1.5e-5,
  epoch_system: 'BJD_TDB',
  source: 'NASA Exoplanet Archive / PSCompPars',
  retrieved_utc: '2026-11-12T16:00:00Z',
};

export const PREDICTION: TransitPrediction = checkPrediction({
  planet: PLANET,
  window: { epoch_number: 3254, mid_bjd_tdb: 2461356.371234, ingress_bjd_tdb: 2461356.332901, egress_bjd_tdb: 2461356.409567, coverage_start_bjd_tdb: 2461356.291234, coverage_end_bjd_tdb: 2461356.451234, baseline_minutes: 60, coverage_hours: 3.84 },
  utc: { coverage_start: '2026-11-21T18:58:00Z', ingress: '2026-11-21T19:58:00Z', mid: '2026-11-21T20:53:00Z', egress: '2026-11-21T21:48:00Z', coverage_end: '2026-11-21T22:48:00Z' },
  altitude_deg: { coverage_start: 58.2, ingress: 52.1, mid: 45.6, egress: 38.9, coverage_end: 27.4 },
  sun_alt_deg: { coverage_start: -24, ingress: -33, mid: -41, egress: -49, coverage_end: -56 },
  night: { date: '2026-11-21', dusk_utc: '2026-11-21T17:39:00Z', dawn_utc: '2026-11-22T05:41:00Z' },
  observable: { transit: true, coverage: false },
  usable: { start_utc: '2026-11-21T18:58:00Z', end_utc: '2026-11-21T22:31:00Z' },
  skipped: [
    { epoch_number: 3250, mid_utc: '2026-11-12T19:00:00Z', reason: 'daylight' },
    { epoch_number: 3251, mid_utc: '2026-11-14T23:21:00Z', reason: 'below_limit' },
    { epoch_number: 3252, mid_utc: '2026-11-17T04:40:00Z', reason: 'daylight' },
  ],
  skipped_count: 3,
  min_alt_deg: 30,
}) as TransitPrediction;

export const PLANET_ONLY = PREDICTION.planet;
