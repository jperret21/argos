import { describe, expect, it } from 'vitest';
import {
  EMPTY_JOBS,
  type Job,
  jobDuration,
  jobList,
  jobsReducer,
  type JobsState,
  latestOfKind,
  MAX_FINISHED,
  parseJob,
  progressFraction,
} from './jobs';

const job = (patch: Partial<Job> = {}): Job => ({
  id: 'j1',
  kind: 'discovery',
  state: 'running',
  done: 0,
  total: 3,
  stage: 'broadcast',
  message: null,
  started_utc: '2026-11-01T21:00:00Z',
  ended_utc: null,
  result: null,
  error: null,
  cancellable: true,
  cancel_requested: false,
  seq: 1,
  ...patch,
});

const apply = (state: JobsState, ...jobs: Job[]) =>
  jobs.reduce((s, j) => jobsReducer(s, { type: 'event', job: j }), state);

describe('parseJob', () => {
  it('reads a WS job event or a bare Job (protocol.md A80)', () => {
    const wire = { type: 'job', job: { ...job(), error: null } };
    expect(parseJob(wire)).toEqual(job());
    expect(parseJob(job({ state: 'failed', error: { code: 'timeout', message: 'No answer' } }))?.error).toEqual({
      code: 'timeout',
      message: 'No answer',
    });
  });

  it('refuses unknown states and missing ids', () => {
    expect(parseJob({ ...job(), state: 'paused' })).toBeNull();
    expect(parseJob({ ...job(), id: 3 })).toBeNull();
    expect(parseJob(null)).toBeNull();
  });
});

describe('job state reducer', () => {
  it('follows progress to the end', () => {
    let s = apply(EMPTY_JOBS, job(), job({ done: 1, stage: 'probe', seq: 2 }));
    expect(s.byId.j1).toMatchObject({ done: 1, stage: 'probe' });
    expect(progressFraction(s.byId.j1)).toBeCloseTo(1 / 3);
    s = apply(s, job({ state: 'done', done: 3, seq: 5, ended_utc: '2026-11-01T21:00:12Z', result: { devices: [] } }));
    expect(s.byId.j1.state).toBe('done');
    expect(progressFraction(s.byId.j1)).toBe(1);
  });

  it('ignores an event older than the state it holds (out of order, snapshot first)', () => {
    let s = jobsReducer(EMPTY_JOBS, { type: 'snapshot', jobs: [job({ done: 2, seq: 7 })] });
    s = apply(s, job({ done: 1, seq: 4 }));
    expect(s.byId.j1.done).toBe(2);
    const same = apply(s, job({ done: 9, seq: 7 }));
    expect(same).toBe(s);
  });

  it('shows a cancel as pending until the server ends the job', () => {
    let s = apply(EMPTY_JOBS, job());
    s = jobsReducer(s, { type: 'cancel-requested', id: 'j1' });
    expect(s.byId.j1.cancelling).toBe(true);
    // The DELETE answer echoes the job with cancel_requested: still running.
    s = apply(s, job({ seq: 2, cancel_requested: true }));
    expect(s.byId.j1).toMatchObject({ state: 'running', cancelling: true });
    s = apply(s, job({ seq: 3, state: 'cancelled', ended_utc: '2026-11-01T21:00:03Z' }));
    expect(s.byId.j1).toMatchObject({ state: 'cancelled', cancelling: false });
  });

  it('says why a cancel failed and lets the job run on', () => {
    let s = apply(EMPTY_JOBS, job({ cancellable: false }));
    s = jobsReducer(s, { type: 'cancel-requested', id: 'j1' });
    s = jobsReducer(s, { type: 'cancel-failed', id: 'j1', message: 'This job cannot be cancelled' });
    expect(s.byId.j1).toMatchObject({ cancelling: false, cancelError: 'This job cannot be cancelled', state: 'running' });
    // Cancelling a finished job does nothing.
    const done = apply(s, job({ seq: 9, state: 'done' }));
    expect(jobsReducer(done, { type: 'cancel-requested', id: 'j1' })).toBe(done);
  });

  it('marks an active job the server no longer lists as lost, never left spinning', () => {
    let s = apply(EMPTY_JOBS, job(), job({ id: 'j2', state: 'done', seq: 3 }));
    s = jobsReducer(s, { type: 'snapshot', jobs: [job({ id: 'j3', started_utc: '2026-11-01T21:05:00Z' })] });
    expect(s.byId.j1.state).toBe('failed');
    expect(s.byId.j1.error?.code).toBe('lost');
    expect(s.byId.j2.state).toBe('done');
    expect(jobList(s).map((j) => j.id)).toEqual(['j1', 'j2', 'j3']);
  });

  it('an answer older than an event never declares that job lost (review repro: event seq 5, then an empty snapshot)', () => {
    // GET /api/jobs was sent while nothing was held; the job's event arrived before the answer.
    const marks = {};
    let s = apply(EMPTY_JOBS, job({ id: 'j1', seq: 5 }));
    s = jobsReducer(s, { type: 'snapshot', jobs: [], before: marks });
    expect(s.byId.j1.state).toBe('running');
    // Held at request time with the same seq, and still absent: lost.
    s = jobsReducer(s, { type: 'snapshot', jobs: [], before: { j1: 5 } });
    expect(s.byId.j1.state).toBe('failed');
    expect(s.byId.j1.error?.code).toBe('lost');
  });

  it('a job that moved on after the request is not lost either', () => {
    let s = apply(EMPTY_JOBS, job({ id: 'j1', seq: 5 }));
    const marks = { j1: 5 };
    s = apply(s, job({ id: 'j1', seq: 6, done: 1 }));
    s = jobsReducer(s, { type: 'snapshot', jobs: [], before: marks });
    expect([s.byId.j1.state, s.byId.j1.done]).toEqual(['running', 1]);
  });

  it('dismisses finished jobs only, and keeps at most MAX_FINISHED of them', () => {
    let s = apply(EMPTY_JOBS, job());
    expect(jobsReducer(s, { type: 'dismiss', id: 'j1' })).toBe(s);
    s = apply(s, job({ seq: 2, state: 'failed', error: { code: 'x', message: 'y' } }));
    expect(jobsReducer(s, { type: 'dismiss', id: 'j1' }).order).toEqual([]);
    let many = EMPTY_JOBS;
    for (let i = 0; i < MAX_FINISHED + 5; i++) many = apply(many, job({ id: `d${i}`, state: 'done', seq: i + 1 }));
    many = apply(many, job({ id: 'live' }));
    expect(many.order).toHaveLength(MAX_FINISHED + 1);
    expect(many.order[0]).toBe('d5');
    expect(many.byId.live.state).toBe('running');
  });

  it('finds the newest job of a kind and its duration', () => {
    const s = apply(EMPTY_JOBS, job({ id: 'a', state: 'done' }), job({ id: 'b' }), job({ id: 'c', kind: 'export' }));
    expect(latestOfKind(s, 'discovery')?.id).toBe('b');
    expect(latestOfKind(s, 'site_search')).toBeNull();
    expect(jobDuration(job(), Date.parse('2026-11-01T21:00:12Z'))).toBe('12 s');
    expect(jobDuration(job({ ended_utc: '2026-11-01T21:03:05Z' }))).toBe('3m 05s');
    expect(progressFraction(job({ total: null }))).toBeNull();
  });
});
