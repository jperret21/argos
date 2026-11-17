import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { checkPlan, checkPlanDoc, checkPrediction, checkPresetList, PlanApi, type PlanDoc, type PlanRequest, type PlanStep, type SequencePlan } from '../api/plan';
import { PlanStore } from './plan.svelte';
import { roleCounts, targetSetTsv } from './targets';
import { altitudeText, coverageText, dateProblem, planetFacts, skippedText, spansOf, transitNote } from './transit.svelte';

const step = (over: Partial<PlanStep> = {}): PlanStep => ({
  enabled: true,
  frame_type: 'Light',
  filter_name: 'IR',
  exposure_s: 10,
  gain: 80,
  count: 10,
  interval_s: 0,
  cadence_s: null,
  dither_every: 0,
  ...over,
});

const planOf = (steps: PlanStep[]): SequencePlan => ({
  object_name: 'T CrB',
  repeat: 1,
  autofocus_every_n: 0,
  autofocus_on_filter_change: false,
  on_complete: 'Nothing',
  base_dir: null,
  metadata: {},
  start_at_utc: null,
  steps,
});

/** The wire record the server would answer for a plan (issues on exposures above 600 s). */
function record(plan: SequencePlan, revision: number): Record<string, unknown> {
  const issues = plan.steps.flatMap((s, i) => (s.exposure_s > 600 ? [{ step: i, field: 'exposure_s', code: 'out_of_range', level: 'error', message: `Exposure ${s.exposure_s} s is outside 0.01-600 s.` }] : []));
  return {
    plan: { schema: 2, ...plan },
    derived: { total_frames: plan.steps.reduce((a, s) => a + (s.enabled ? s.count : 0), 0), estimate_s: 0, per_step_s: plan.steps.map(() => 0), start_utc: '2026-11-12T20:00:00Z', end_utc: '2026-11-12T20:10:00Z' },
    issues,
    ready: !issues.length,
    locked: false,
    locked_reason: null,
    notes: [],
    filters: { names: ['Dark', 'IR', 'LP'], source: 'wheel' },
    limits: { exposure_s: [0.01, 600], gain: [0, 600], source: 'camera' },
    path: null,
    revision,
  };
}

/** A fake server holding the draft; `gate` holds PUT answers until released. */
class FakeServer implements PlanRequest {
  plan: SequencePlan = planOf([step()]);
  revision = 1;
  calls: { method: string; path: string; body: unknown }[] = [];
  refuse: ApiError | null = null;
  gate: (() => void)[] = [];
  holding = false;

  async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    this.calls.push({ method, path, body });
    if (method === 'PUT' && path === '/api/sequence/plan') {
      if (this.holding) await new Promise<void>((r) => this.gate.push(r));
      if (this.refuse) throw this.refuse;
      this.plan = body as SequencePlan;
      this.revision++;
      return record(this.plan, this.revision) as T;
    }
    if (method === 'GET' && path === '/api/sequence/plan') return record(this.plan, this.revision) as T;
    if (method === 'POST' && path === '/api/sequence/plan/import') {
      this.plan = planOf([step({ count: 3 }), step({ count: 4 })]);
      this.revision++;
      return record(this.plan, this.revision) as T;
    }
    if (path.startsWith('/api/sequence/presets')) return { directory: '/p', presets: [{ name: 'a', modified_utc: '2026-11-01T00:00:00Z' }] } as T;
    throw new Error(`unexpected ${method} ${path}`);
  }

  release(): void {
    this.holding = false;
    for (const r of this.gate.splice(0)) r();
  }
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe('PlanStore', () => {
  it('loads the draft and writes edits in order, each on the newest plan', async () => {
    const srv = new FakeServer();
    const store = new PlanStore(new PlanApi(srv));
    await store.load();
    expect(store.steps).toHaveLength(1);
    srv.holding = true;
    const a = store.editStep(0, { exposure_s: 30 });
    const b = store.editStep(0, { gain: 120 });
    await tick();
    // The edit shows at once; the second waits for the first answer.
    expect(store.steps[0].exposure_s).toBe(30);
    expect(store.pending).toBe(1);
    srv.release();
    await a;
    srv.release();
    await b;
    expect(srv.plan.steps[0]).toMatchObject({ exposure_s: 30, gain: 120 });
    expect(store.doc?.revision).toBe(3);
    expect(store.pending).toBe(0);
  });

  it('keeps a value out of range as typed, with the server issue (no silent clamp)', async () => {
    const srv = new FakeServer();
    const store = new PlanStore(new PlanApi(srv));
    await store.load();
    await store.editStep(0, { exposure_s: 9999 });
    expect(store.steps[0].exposure_s).toBe(9999);
    expect(store.doc?.issues[0]).toMatchObject({ step: 0, field: 'exposure_s', code: 'out_of_range' });
    expect(store.doc?.ready).toBe(false);
  });

  it('puts back the last accepted plan when the server refuses a write', async () => {
    const srv = new FakeServer();
    const store = new PlanStore(new PlanApi(srv));
    await store.load();
    srv.refuse = new ApiError(400, 'invalid_argument', 'gain must be an integer');
    await expect(store.editStep(0, { gain: 80.5 })).rejects.toThrow('gain must be an integer');
    expect(store.steps[0].gain).toBe(80);
  });

  it('adds, duplicates, moves and removes on the selection, with stable row keys and Undo', async () => {
    const srv = new FakeServer();
    const store = new PlanStore(new PlanApi(srv));
    await store.load();
    const first = store.ids[0];
    expect(store.duplicate()).toBeNull(); // nothing selected: no row action (P19)
    store.selected = 0;
    await store.add(['Dark', 'IR']);
    expect(store.selected).toBe(1);
    await store.editStep(1, { count: 5 });
    await store.duplicate();
    expect(store.steps.map((s) => s.count)).toEqual([10, 5, 5]);
    await store.move(-1);
    expect(store.selected).toBe(1);
    expect(store.ids).toHaveLength(3);
    expect(store.ids[0]).toBe(first);
    const r = store.remove();
    expect(r?.at).toBe(1);
    await r?.done;
    expect(store.steps).toHaveLength(2);
    await store.restore(r!.removed, r!.at);
    expect(store.steps.map((s) => s.count)).toEqual([10, 5, 5]);
    expect(new Set(store.ids).size).toBe(3);
  });

  it('opens a preset as the draft and remembers it for the unsaved check', async () => {
    const srv = new FakeServer();
    const store = new PlanStore(new PlanApi(srv));
    await store.load();
    expect(store.unsaved).toBe(true);
    await store.importPlan({ preset: 'Darks' });
    expect(srv.calls.at(-1)).toMatchObject({ method: 'POST', path: '/api/sequence/plan/import', body: { preset: 'Darks' } });
    expect(store.steps.map((s) => s.count)).toEqual([3, 4]);
    expect(store.unsaved).toBe(false);
    await store.editStep(0, { count: 7 });
    expect(store.unsaved).toBe(true);
  });

  it('follows another client through sequence_plan, newer revisions only, never over a pending write', async () => {
    const srv = new FakeServer();
    const store = new PlanStore(new PlanApi(srv));
    const handlers = new Map<string, (m: Record<string, unknown>) => void>();
    store.attach({ on: (t, fn) => (handlers.set(t, fn), () => handlers.delete(t)) });
    await store.load();
    handlers.get('sequence_plan')?.({ type: 'sequence_plan', ...record(planOf([step({ count: 1 })]), 0) });
    expect(store.steps[0].count).toBe(10);
    handlers.get('sequence_plan')?.({ type: 'sequence_plan', ...record(planOf([step({ count: 2 }), step()]), 9), locked: true, locked_reason: 'A sequence is running (T CrB).' });
    expect(store.steps.map((s) => s.count)).toEqual([2, 10]);
    expect(store.locked).toBe(true);
    expect(store.lockedReason).toMatch(/running/);
  });

  it('locks from the run snapshot too (Q-P9)', async () => {
    let state: { state: string } = { state: 'idle' };
    const store = new PlanStore(new PlanApi(new FakeServer()), () => state as never);
    await store.load();
    expect(store.locked).toBe(false);
    state = { state: 'paused' };
    expect(store.locked).toBe(true);
  });
});

describe('api/plan checks and routes', () => {
  it('rebuilds a plan key by key (the PUT body is strict)', () => {
    const p = checkPlan({ ...planOf([{ ...step(), extra: 1 } as unknown as PlanStep]), schema: 2, unknown_key: true, metadata: { planet_name: 'HD 189733 b', bad: { x: 1 } } });
    expect(p && Object.keys(p).sort()).toEqual(['autofocus_every_n', 'autofocus_on_filter_change', 'base_dir', 'metadata', 'object_name', 'on_complete', 'repeat', 'schema', 'start_at_utc', 'steps']);
    expect(p && Object.keys(p.steps[0]).sort()).toEqual(['cadence_s', 'count', 'dither_every', 'enabled', 'exposure_s', 'filter_name', 'frame_type', 'gain', 'interval_s']);
    expect(p?.metadata).toEqual({ planet_name: 'HD 189733 b' });
    expect(checkPlan({ steps: [{ enabled: 'yes' }] })).toBeNull();
  });

  it('reads a PlanRecord and refuses one without a plan', () => {
    const d = checkPlanDoc(record(planOf([step({ exposure_s: 900 })]), 4)) as PlanDoc;
    expect(d.revision).toBe(4);
    expect(d.ready).toBe(false);
    expect(d.filters.names).toEqual(['Dark', 'IR', 'LP']);
    expect(d.limits.exposure_s).toEqual([0.01, 600]);
    expect(d.issues[0].level).toBe('error');
    expect(checkPlanDoc({ derived: {} })).toBeNull();
  });

  it('calls the routes of the contract', async () => {
    const calls: unknown[][] = [];
    const api = new PlanApi({
      request: async <T>(...a: unknown[]) => {
        calls.push(a.slice(0, 3));
        return { ...record(planOf([]), 1), directory: '/d', presets: [], names: ['WASP-12 b'], path: '/x/y.json' } as T;
      },
    });
    await api.savePreset('T CrB nightly', true);
    await api.importPlan({ path: '/a/b.json' });
    await api.exportPlan('/a/c.json');
    expect(await api.exoplanetSuggest('WASP')).toEqual(['WASP-12 b']);
    await api.deletePreset('a/b');
    expect(calls).toEqual([
      ['PUT', '/api/sequence/presets/T%20CrB%20nightly?overwrite=true', undefined],
      ['POST', '/api/sequence/plan/import', { path: '/a/b.json' }],
      ['POST', '/api/sequence/plan/export', { path: '/a/c.json', overwrite: false }],
      ['GET', '/api/exoplanets/suggest?q=WASP&limit=8', undefined],
      ['DELETE', '/api/sequence/presets/a%2Fb'],
    ]);
  });

  it('reads the preset list with unreadable files', () => {
    const l = checkPresetList({ directory: '/p', presets: [{ name: 'ok', modified_utc: 'x', total_frames: 3 }, { name: 'bad', error: 'unknown step key' }, { nope: 1 }] });
    expect(l.presets.map((p) => p.name)).toEqual(['ok', 'bad']);
    expect(l.presets[1].error).toBe('unknown step key');
  });
});

const PRED = {
  planet: { planet_name: 'HD 189733 b', host_name: 'HD 189733', ra_hours: 20.0, dec_deg: 22.7, period_days: 2.21857567, epoch_bjd_tdb: 2454279.436714, duration_hours: 1.84, depth_percent: 2.4, epoch_system: 'BJD_TDB', source: 'NASA', retrieved_utc: null },
  window: { epoch_number: 3254, mid_bjd_tdb: 2461347.412345, ingress_bjd_tdb: 2461347.374, egress_bjd_tdb: 2461347.45, coverage_start_bjd_tdb: 2461347.33, coverage_end_bjd_tdb: 2461347.49, baseline_minutes: 60, coverage_hours: 3.84 },
  utc: { coverage_start: '2026-11-13T00:12:00Z', ingress: '2026-11-13T01:12:00Z', mid: '2026-11-13T02:07:00Z', egress: '2026-11-13T03:02:00Z', coverage_end: '2026-11-13T04:02:00Z' },
  altitude_deg: { coverage_start: 41.2, ingress: 35, mid: 28.4, egress: 22, coverage_end: 18.6 },
  sun_alt_deg: { coverage_start: -40, ingress: -45, mid: -50, egress: -48, coverage_end: -40 },
  night: { date: '2026-11-12', dusk_utc: '2026-11-12T17:40:00Z', dawn_utc: '2026-11-13T05:30:00Z' },
  observable: { transit: false, coverage: false },
  usable: null,
  skipped: [{ epoch_number: 3252, mid_utc: 'x', reason: 'daylight' }, { epoch_number: 3253, mid_utc: 'y', reason: 'below_limit' }],
  skipped_count: 2,
  min_alt_deg: 30,
};

describe('transit words', () => {
  const p = checkPrediction(PRED)!;

  it('reads the prediction', () => {
    expect(p.window.epoch_number).toBe(3254);
    expect(checkPrediction({ ...PRED, utc: { mid: 'x' } })).toBeNull();
  });

  it('writes coverage, altitudes, what limits it and what was skipped', () => {
    expect(coverageText(p, 60)).toEqual({ local: '01:12 → 05:02', utc: '00:12 → 04:02', hours: '3.84 h' });
    expect(altitudeText(p)).toBe('start 41° · mid 28° · end 19°');
    expect(transitNote(p)).toBe('The transit itself is not observable: below 30° at mid, egress');
    expect(transitNote({ ...p, observable: { transit: true, coverage: false } })).toBe('Baseline cut: coverage ends below 30°');
    expect(transitNote({ ...p, observable: { transit: true, coverage: true } })).toBeNull();
    expect(skippedText(p)).toBe('2 earlier transits skipped (daylight 1, below 30° 1)');
    expect(skippedText({ ...p, skipped_count: 117 })).toBe('117 earlier transits skipped (of the first 2: daylight 1, below 30° 1)');
    expect(skippedText({ ...p, skipped: [], skipped_count: 0 })).toBeNull();
    expect(planetFacts(p.planet)).toBe('P 2.21857567 d · duration 1.84 h · depth 2.4 % · epoch BJD_TDB');
    const s = spansOf(p)!;
    expect(s.mid - s.coverageStart).toBe(6900);
  });

  it('checks the night field', () => {
    expect(dateProblem('')).toBeNull();
    expect(dateProblem('2026-11-12')).toBeNull();
    expect(dateProblem('12/11/2026')).toMatch(/YYYY-MM-DD/);
    expect(dateProblem('2026-02-30')).toMatch(/not a calendar date/);
  });
});

describe('target set words', () => {
  const stars = [
    { key: 'a', role: 'target', name: 'T CrB', display_name: 'T CrB', ra_hours: 15.99172, dec_deg: 25.92028, auid: '000-BBW-825', source: 'vsx', mags: { V: 10.2 }, chart_id: null, note: null },
    { key: 'b', role: 'comparison', name: '000-BBC-123', ra_hours: 16, dec_deg: 26, auid: '000-BBC-123', source: 'vsp', mags: { V: 10.81, B: 11.5 }, chart_id: null, note: null },
  ] as const;

  it('counts roles and copies the set as Qt did', () => {
    expect(roleCounts(stars as never)).toEqual({ target: 1, comparison: 1, check: 0 });
    const tsv = targetSetTsv(stars as never).split('\n');
    expect(tsv[0]).toBe('Role\tName\tRA\tDec\tMags');
    expect(tsv[1].split('\t')[0]).toBe('target');
    expect(tsv[2].split('\t')[4]).toBe('V 10.81  B 11.50');
  });
});
