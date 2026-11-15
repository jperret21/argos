import { describe, expect, it } from 'vitest';
import type { JobEntry } from '../app/jobs';
import { countText, etaSeconds, etaText, stripJob } from './jobstrip';

const NNBSP = ' ';
const T0 = Date.parse('2026-11-15T20:00:00Z');

const J = (id: string, kind: string, state: JobEntry['state'], extra: Partial<JobEntry> = {}): JobEntry => ({
  id,
  kind,
  state,
  done: 0,
  total: null,
  stage: null,
  message: null,
  started_utc: '2026-11-15T20:00:00Z',
  ended_utc: null,
  result: null,
  error: null,
  cancellable: true,
  cancel_requested: false,
  seq: 1,
  cancelling: false,
  cancelError: null,
  ...extra,
});

describe('job strip', () => {
  it('shows the newest active job of its kinds and counts the others', () => {
    const jobs = [J('a', 'rerun', 'running'), J('b', 'export', 'done'), J('c', 'export', 'running'), J('d', 'discover', 'running')];
    expect(stripJob(jobs, ['rerun', 'export'])).toEqual({ job: jobs[2], others: 1 });
    expect(stripJob(jobs, null).job?.id).toBe('d');
    expect(stripJob(jobs, null).others).toBe(2);
  });

  it('keeps the newest finished job when none runs (a failure is never only a toast)', () => {
    const jobs = [J('a', 'rerun', 'done'), J('b', 'export', 'failed')];
    expect(stripJob(jobs, ['rerun', 'export'])).toEqual({ job: jobs[1], others: 0 });
    expect(stripJob(jobs, ['file_solve'])).toEqual({ job: null, others: 0 });
  });

  it('gives an ETA only after two units and three seconds, never for an indeterminate job', () => {
    const run = J('a', 'rerun', 'running', { done: 37, total: 195 });
    expect(etaSeconds(run, T0 + 2000)).toBeNull();
    expect(etaSeconds({ ...run, done: 1 }, T0 + 10_000)).toBeNull();
    expect(etaSeconds(run, T0 + 37_000)).toBeCloseTo(158, 6);
    expect(etaText(run, T0 + 37_000)).toBe('ETA 2m 38s');
    expect(etaSeconds({ ...run, total: null }, T0 + 37_000)).toBeNull();
    expect(etaSeconds({ ...run, state: 'done' }, T0 + 37_000)).toBeNull();
    expect(etaSeconds({ ...run, started_utc: null }, T0 + 37_000)).toBeNull();
  });

  it('counts with grouped digits and a unit', () => {
    expect(countText({ done: 37, total: 1950 }, 'frames')).toBe(`37 / 1${NNBSP}950 frames`);
    expect(countText({ done: 3, total: 5 })).toBe('3 / 5');
    expect(countText({ done: 0, total: null })).toBeNull();
    expect(countText({ done: 0, total: 0 })).toBeNull();
  });
});
