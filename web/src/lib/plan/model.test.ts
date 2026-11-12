import { describe, expect, it } from 'vitest';
import type { PlanDoc, PlanIssue, PlanStep, SequencePlan } from '../api/plan';
import {
  addStep,
  duplicateStep,
  indexIssues,
  issueTitle,
  lightSlots,
  localHm,
  moveStep,
  newStep,
  nightOf,
  optionsWith,
  planBlock,
  removeStep,
  rowProgress,
  runActive,
  samePlan,
  stepKeyCommand,
  timeTitle,
  usesFilter,
  utcHm,
  wallHm,
} from './model';

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

const plan = (steps: PlanStep[], over: Partial<SequencePlan> = {}): SequencePlan => ({
  object_name: 'T CrB',
  repeat: 1,
  autofocus_every_n: 0,
  autofocus_on_filter_change: false,
  on_complete: 'Nothing',
  base_dir: null,
  metadata: {},
  start_at_utc: null,
  steps,
  ...over,
});

const doc = (steps: PlanStep[], issues: PlanIssue[] = []): PlanDoc => ({
  plan: plan(steps),
  derived: { total_frames: 0, estimate_s: 0, per_step_s: [], start_utc: null, end_utc: null },
  issues,
  ready: !issues.some((i) => i.level === 'error'),
  locked: false,
  locked_reason: null,
  notes: [],
  filters: { names: ['Dark', 'IR', 'LP'], source: 'wheel' },
  limits: { exposure_s: [0.01, 600], gain: [0, 600], source: 'camera' },
  path: null,
  revision: 1,
});

const issue = (step: number | null, field: string, message: string, level: 'error' | 'warning' = 'error', code = 'out_of_range'): PlanIssue => ({ step, field, code, level, message });

describe('steps', () => {
  it('a new step never defaults to the opaque slot (S7)', () => {
    expect(lightSlots(['Dark', 'IR', 'LP'])).toEqual(['IR', 'LP']);
    expect(newStep(null, ['Dark', 'IR']).filter_name).toBe('IR');
    expect(newStep(null, ['Dark']).filter_name).toBe('');
    expect(newStep(null, []).frame_type).toBe('Light');
  });

  it('adds after the selection, else at the end, copying the selected step', () => {
    const s = [step({ exposure_s: 5 }), step({ exposure_s: 30, filter_name: 'LP', enabled: false })];
    const a = addStep(s, 1, ['IR']);
    expect(a.selected).toBe(2);
    expect(a.steps[2]).toMatchObject({ exposure_s: 30, filter_name: 'LP', enabled: true });
    const b = addStep(s, null, ['IR']);
    expect(b.selected).toBe(2);
    expect(b.steps[2].exposure_s).toBe(10);
    expect(addStep([], null, ['IR']).steps).toHaveLength(1);
  });

  it('duplicates right after the source and needs a selection (P19)', () => {
    const s = [step({ count: 1 }), step({ count: 2 })];
    expect(duplicateStep(s, null)).toBeNull();
    const d = duplicateStep(s, 0);
    expect(d?.steps.map((x) => x.count)).toEqual([1, 1, 2]);
    expect(d?.selected).toBe(1);
  });

  it('removes any step, the last one too, and keeps a selection when rows remain', () => {
    const s = [step({ count: 1 }), step({ count: 2 })];
    expect(removeStep(s, null)).toBeNull();
    const r = removeStep(s, 1);
    expect(r?.steps.map((x) => x.count)).toEqual([1]);
    expect(r?.selected).toBe(0);
    expect(r?.removed.count).toBe(2);
    const last = removeStep([step()], 0);
    expect(last?.steps).toEqual([]);
    expect(last?.selected).toBeNull();
  });

  it('moves within bounds only', () => {
    const s = [step({ count: 1 }), step({ count: 2 }), step({ count: 3 })];
    expect(moveStep(s, 0, -1)).toBeNull();
    expect(moveStep(s, 2, 3)).toBeNull();
    expect(moveStep(s, null, 1)).toBeNull();
    expect(moveStep(s, 0, 2)?.steps.map((x) => x.count)).toEqual([2, 3, 1]);
    expect(moveStep(s, 2, 1)?.selected).toBe(1);
  });

  it('keeps an unknown value in a menu, flagged (never the first entry, P11)', () => {
    const o = optionsWith(['IR', 'LP'], 'Ha', 'not in the wheel');
    expect(o.map((x) => x.value)).toEqual(['IR', 'LP', 'Ha']);
    expect(o[2].detail).toBe('not in the wheel');
    expect(optionsWith(['IR'], 'IR', 'x')).toHaveLength(1);
    expect(usesFilter('Dark')).toBe(false);
    expect(usesFilter('Flat')).toBe(true);
  });
});

describe('issues', () => {
  const list = [
    issue(1, 'cadence_s', 'Cadence 5 s is shorter than the 10 s exposure.', 'error', 'cadence_short'),
    issue(1, 'interval_s', 'The cadence wins: the interval is not used.', 'warning', 'interval_ignored'),
    issue(null, 'repeat', 'Repeat must be 1 to 999.'),
    issue(null, 'object_name', 'No object name.', 'warning', 'no_object'),
  ];

  it('maps each issue to its field, its step and the plan', () => {
    const ix = indexIssues(list);
    expect(ix.field(1, 'cadence_s').map((i) => i.code)).toEqual(['cadence_short']);
    expect(ix.field(0, 'cadence_s')).toEqual([]);
    expect(ix.step(1)).toHaveLength(2);
    expect(ix.plan('repeat')[0].message).toMatch(/Repeat/);
    expect(ix.errors).toHaveLength(2);
    expect(ix.warnings).toHaveLength(2);
  });

  it('names the place in words', () => {
    expect(issueTitle(list[0])).toBe('Step 2 · Cadence');
    expect(issueTitle(list[2])).toBe('Repeat');
    expect(issueTitle({ ...list[2], field: null })).toBe('Plan');
  });

  it('blocks Start on the first error, never on a warning', () => {
    expect(planBlock(null)).toMatch(/not loaded/);
    expect(planBlock(doc([]))).toBe('add a step or open a preset');
    expect(planBlock(doc([step({ enabled: false })]))).toBe('enable at least one step');
    expect(planBlock(doc([step(), step()], list))).toBe('fix step 2: cadence 5 s is shorter than the 10 s exposure.');
    expect(planBlock(doc([step()], [list[1], list[3]]))).toBeNull();
    // A name or an acronym keeps its capital.
    expect(planBlock(doc([step()], [issue(0, 'filter_name', 'IR is not a slot of the wheel.')]))).toBe('fix step 1: IR is not a slot of the wheel.');
  });
});

describe('run', () => {
  const p = plan([step({ count: 3 }), step({ count: 2, enabled: false }), step({ count: 4 })], { repeat: 2 });
  const seq = (over: Record<string, unknown>) => ({ state: 'running', step_index: 0, pass_index: 1, frames_done: 0, ...over }) as Parameters<typeof rowProgress>[1];

  it('is locked in every state but idle (Q-P9)', () => {
    expect(runActive(null)).toBe(false);
    expect(runActive({ state: 'idle' })).toBe(false);
    for (const s of ['waiting', 'running', 'pausing', 'paused', 'autofocus', 'stopping']) expect(runActive({ state: s })).toBe(true);
  });

  it('gives each row its progress in the current pass (1-based pass on the wire)', () => {
    expect(rowProgress(p, seq({ state: 'idle' }))).toBeNull();
    expect(rowProgress(p, seq({ state: 'waiting' }))).toBeNull();
    const a = rowProgress(p, seq({ frames_done: 4, step_index: 2, pass_index: 1 }));
    expect(a?.map((r) => `${r.kind} ${r.done}/${r.total}`)).toEqual(['done 3/3', 'skipped 0/2', 'active 1/4']);
    // Second pass: 7 per pass, 9 done -> 2 of the first step.
    const b = rowProgress(p, seq({ frames_done: 9, step_index: 0, pass_index: 2 }));
    expect(b?.map((r) => `${r.kind} ${r.done}/${r.total}`)).toEqual(['active 2/3', 'skipped 0/2', 'waiting 0/4']);
  });
});

describe('keys', () => {
  const k = (key: string, mods: Partial<Record<'altKey' | 'metaKey' | 'ctrlKey' | 'shiftKey', boolean>> = {}) => ({ key, altKey: false, metaKey: false, ctrlKey: false, shiftKey: false, ...mods });

  it('maps the Steps keys (06 2.4)', () => {
    expect(stepKeyCommand(k('Insert'), true)).toBe('add');
    expect(stepKeyCommand(k('d', { metaKey: true }), true)).toBe('duplicate');
    expect(stepKeyCommand(k('d', { ctrlKey: true }), false)).toBe('duplicate');
    expect(stepKeyCommand(k('d', { ctrlKey: true }), true)).toBeNull();
    expect(stepKeyCommand(k('Delete'), false)).toBe('remove');
    expect(stepKeyCommand(k('Backspace'), false)).toBe('remove');
    expect(stepKeyCommand(k('ArrowUp', { altKey: true }), false)).toBe('up');
    expect(stepKeyCommand(k('ArrowDown', { altKey: true }), false)).toBe('down');
    expect(stepKeyCommand(k(' '), false)).toBe('toggle');
    expect(stepKeyCommand(k('ArrowDown'), false)).toBe('next');
    expect(stepKeyCommand(k('Home'), false)).toBe('first');
    expect(stepKeyCommand(k('End'), false)).toBe('last');
    expect(stepKeyCommand(k('a'), false)).toBeNull();
    expect(stepKeyCommand(k('Delete', { shiftKey: true }), false)).toBeNull();
  });
});

describe('times', () => {
  it('writes local and UTC clock times', () => {
    expect(localHm('2026-11-12T20:52:10Z', 60)).toBe('21:52');
    expect(localHm('2026-11-12T23:30:00Z', 120)).toBe('01:30');
    expect(localHm(null)).toBe('—');
    expect(utcHm('2026-11-12T20:52:10Z')).toBe('20:52');
    expect(wallHm('2026-11-13T01:12:00+01:00')).toBe('01:12');
    expect(timeTitle('2026-11-12T20:52:10Z', 60)).toBe('21:52 local · 20:52 UTC · 2026-11-12');
  });

  it('shows last night until local noon (P3, Q-P6)', () => {
    expect(nightOf(new Date('2026-11-12T01:30:00Z'), 60)).toBe('2026-11-11');
    expect(nightOf(new Date('2026-11-12T11:30:00Z'), 60)).toBe('2026-11-12');
    expect(nightOf(new Date('2026-11-12T22:00:00Z'), 60)).toBe('2026-11-12');
  });

  it('compares plans as the observer sees them', () => {
    const a = plan([step()]);
    expect(samePlan(a, plan([step()]))).toBe(true);
    expect(samePlan(a, plan([step({ count: 11 })]))).toBe(false);
    expect(samePlan(a, plan([step()], { metadata: { planet_name: 'x' } }))).toBe(false);
    expect(samePlan(a, null)).toBe(false);
  });
});

describe('issue words', () => {
  it('drops the step the row already shows, keeps the rest of the server sentence', async () => {
    const { issueText } = await import('./model');
    const i = (step: number | null, message: string): PlanIssue => ({ step, field: 'cadence_s', code: 'cadence_short', level: 'error', message });
    expect(issueText(i(1, 'Step 2: cadence 20 s is shorter than the 30 s exposure.'))).toBe('Cadence 20 s is shorter than the 30 s exposure.');
    expect(issueText(i(1, 'Cadence too short.'))).toBe('Cadence too short.');
    expect(issueText(i(0, 'Step 2: x'))).toBe('Step 2: x');
    expect(issueText(i(null, 'Repeat 0 is outside 1-999.'))).toBe('Repeat 0 is outside 1-999.');
    expect(planBlock(doc([step(), step()], [i(1, 'Step 2: cadence 20 s is shorter than the 30 s exposure.')]))).toBe('fix step 2: cadence 20 s is shorter than the 30 s exposure.');
  });
});
