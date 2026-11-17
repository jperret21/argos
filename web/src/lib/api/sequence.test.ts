import { describe, expect, it } from 'vitest';
import { resolveConfig } from '../config';
import { ApiError, ArgosClient } from './client';
import { checkPreflight, checkSequence, checkVisibility, isoOf, isRunActive, sequenceApi, unixOf } from './sequence';

const STEP = { enabled: true, frame_type: 'Light', filter_name: 'LP', exposure_s: 30, gain: 80, count: 10, interval_s: 0, cadence_s: null, dither_every: 0 };
const PLAN = { schema: 2, object_name: 'T CrB', repeat: 2, autofocus_every_n: 20, autofocus_on_filter_change: false, on_complete: 'Park mount', base_dir: null, metadata: {}, start_at_utc: null, steps: [STEP, STEP, { ...STEP, frame_type: 'Dark', filter_name: 'Dark' }] };

// A SequenceState as protocol.md "API 2 routes, wave 6a: sequences" writes it.
const RUNNING = {
  type: 'sequence',
  state: 'running',
  active: true,
  run_id: '20261101T204502Z',
  run_root: '/data/sessions/20261101T204502Z_T_CrB',
  object_name: 'T CrB',
  plan: PLAN,
  start_at_utc: null,
  started_utc: '2026-11-01T20:45:02Z',
  step_index: 1,
  step: STEP,
  pass_index: 1,
  repeat: 2,
  frames_done: 37,
  frames_total: 60,
  eta_s: 390,
  end_utc: '2026-11-01T21:51:30Z',
  current: { frame_type: 'Light', image_type: 'Light Frame', filter: 'LP', exposure_s: 30, gain: 80, index: 38, step_index: 1, started_utc: '2026-11-01T21:45:00Z' },
  last_frame_utc: '2026-11-01T21:44:28Z',
  last_saved_utc: '2026-11-01T21:44:59Z',
  last_frame_name: 'T_CrB_LP_Light_e30000ms_g80_00037.fit',
  cadence_s: 33,
  observed_cadence_s: 32.4,
  next_autofocus: { reason: 'every_n', in_frames: 3 },
  autofocus_runs: 1,
  paused_by: null,
  end_action: 'Park mount',
  last_result: null,
  revision: 41,
  future_field: 'ignored',
};

describe('the sequence record (A63)', () => {
  it('reads every field: times in unix seconds, indices 0-based, the plan frozen', () => {
    const s = checkSequence(RUNNING)!;
    expect(s.state).toBe('running');
    expect(s.active).toBe(true);
    expect(s.step_index).toBe(1);
    expect(s.steps_total).toBe(3);
    expect(s.pass_index).toBe(1); // 1-based, as on the wire
    expect(s.step?.filter_name).toBe('LP');
    expect(s.started_t).toBe(Date.UTC(2026, 10, 1, 20, 45, 2) / 1000);
    expect(s.end_t).toBe(Date.UTC(2026, 10, 1, 21, 51, 30) / 1000);
    expect(s.current).toEqual({ exposure_s: 30, started_t: Date.UTC(2026, 10, 1, 21, 45, 0) / 1000, filter: 'LP', frame_type: 'Light', index: 38 });
    expect(s.last_frame_t).toBe(Date.UTC(2026, 10, 1, 21, 44, 28) / 1000);
    expect([s.cadence_s, s.observed_cadence_s, s.next_autofocus_in, s.autofocus_every_n, s.autofocus_runs]).toEqual([33, 32.4, 3, 20, 1]);
    expect(s.on_complete).toBe('Park mount');
    expect(s.revision).toBe(41);
    // A 6a record has no mid-run autofocus fields: none shown.
    expect([s.af_step, s.af_marks]).toEqual([null, []]);
  });

  it('reads the mid-run autofocus sweep and the run’s passes (wave 6b: afStep, the marks)', () => {
    const s = checkSequence({
      ...RUNNING,
      state: 'autofocus',
      autofocus: { started_utc: '2026-11-01T21:46:00Z', stage: 'sweep', step: 4, total: 9, position: 12010 },
      autofocus_passes: [
        { started_utc: '2026-11-01T21:10:00Z', ended_utc: '2026-11-01T21:12:30Z', state: 'done', position: 12000, hfd_px: 2.1, message: null, frames_done: 20 },
        { started_utc: '2026-11-01T21:46:00Z', ended_utc: null, state: 'not_started', position: null, hfd_px: null, message: null, frames_done: 37 },
        { started_utc: 'not a time' },
      ],
    })!;
    expect(s.af_step).toEqual({ done: 4, total: 9 });
    expect(s.af_marks).toEqual([Date.UTC(2026, 10, 1, 21, 10, 0) / 1000, Date.UTC(2026, 10, 1, 21, 46, 0) / 1000]);
    expect(checkSequence({ ...RUNNING, autofocus: { step: 2, total: 0 } })!.af_step).toBeNull();
  });

  it('keeps the wire state of a scheduled start (Q-P2)', () => {
    const s = checkSequence({ ...RUNNING, state: 'waiting', start_at_utc: '2026-11-02T00:12:00Z', frames_done: 0 })!;
    expect(s.state).toBe('waiting');
    expect(s.start_at_t).toBe(Date.UTC(2026, 10, 2, 0, 12) / 1000);
  });

  it('refuses a record it cannot trust: unknown state, missing counts, the status summary', () => {
    expect(checkSequence({ ...RUNNING, state: 'flying' })).toBeNull();
    expect(checkSequence({ ...RUNNING, frames_done: undefined })).toBeNull();
    expect(checkSequence({ type: 'status', sequence: { state: 'running', active: true, run_id: 'x', object_name: 'T CrB' } })).toBeNull();
    expect(checkSequence(null)).toBeNull();
  });

  it('reads the last result with its words and the end action', () => {
    const s = checkSequence({
      ...RUNNING,
      state: 'idle',
      active: false,
      last_result: { completed: false, reason: 'camera_error', message: 'Exposure timeout after 45s', frames_saved: 12, frames_total: 60, run_root: RUNNING.run_root, started_utc: RUNNING.started_utc, ended_utc: '2026-11-01T22:00:00Z' },
    })!;
    expect(s.last_result).toMatchObject({ completed: false, reason: 'camera_error', message: 'Exposure timeout after 45s', frames_saved: 12, frames_total: 60, on_complete: 'Park mount', ended_t: Date.UTC(2026, 10, 1, 22) / 1000 });
  });
});

describe('preflight (A64)', () => {
  it('keeps the known levels, drops what it cannot read, keeps the summary', () => {
    const p = checkPreflight({
      checks: [
        { id: 'camera', level: 'ok', message: 'connected' },
        { id: 'disk', level: 'note', message: '3.1 GB needed, 3.6 GB free' },
        { id: 'output', level: 'block', message: 'not writable' },
        { id: 'x', level: 'maybe', message: '?' },
        'junk',
      ],
      level: 'block',
      can_start: false,
      frames_total: 60,
      estimate_s: 1980,
      start_utc: '2026-11-01T20:45:00Z',
      end_utc: '2026-11-01T21:18:00Z',
      bytes_needed: 3.1e9,
      bytes_free: 3.6e9,
    })!;
    expect(p.checks.map((i) => [i.id, i.level])).toEqual([
      ['camera', 'ok'],
      ['disk', 'note'],
      ['output', 'block'],
    ]);
    expect([p.level, p.can_start, p.frames_total, p.bytes_needed]).toEqual(['block', false, 60, 3.1e9]);
    expect(p.end_t).toBe(Date.UTC(2026, 10, 1, 21, 18) / 1000);
  });

  it('reads a bare list, the level from its worst check', () => {
    const p = checkPreflight([{ id: 'focuser', level: 'note', message: 'no focuser' }])!;
    expect([p.level, p.can_start]).toEqual(['note', true]);
    expect(checkPreflight(42)).toBeNull();
  });
});

describe('visibility (A65)', () => {
  const wire = {
    site: { name: 'Home', latitude_deg: 0, longitude_deg: 0, elevation_m: 0 },
    target: { ra_hours: 15.99, dec_deg: 25.92 },
    night: { date: '2026-11-01', dusk_utc: '2026-11-01T18:05:00Z', dawn_utc: '2026-11-02T05:00:00Z' },
    samples: [
      { t_utc: '2026-11-01T18:00:00Z', alt_deg: 20, sun_alt_deg: -17 },
      { t_utc: '2026-11-01T18:10:00Z', alt_deg: 25, sun_alt_deg: -19 },
      { t_utc: 'not a time', alt_deg: 25, sun_alt_deg: -19 },
    ],
    peak: { t_utc: '2026-11-01T18:10:00Z', alt_deg: 25 },
    window: null,
    windows: [],
    min_alt_deg: 30,
    min_alt_source: 'site',
    step_min: 10,
    notes: ['A note.'],
  };

  it('converts to typed arrays and unix seconds; a bad sample is dropped, not guessed', () => {
    const v = checkVisibility(wire)!;
    expect(Array.from(v.t)).toEqual([Date.UTC(2026, 10, 1, 18) / 1000, Date.UTC(2026, 10, 1, 18, 10) / 1000]);
    expect(Array.from(v.alt)).toEqual([20, 25]);
    expect(Array.from(v.sun!)).toEqual([-17, -19]);
    expect([v.siteName, v.night, v.window, v.notes]).toEqual(['Home', '2026-11-01', null, ['A note.']]);
    expect(v.dark).toEqual({ start: Date.UTC(2026, 10, 1, 18, 5) / 1000, end: Date.UTC(2026, 10, 2, 5) / 1000 });
  });

  it('no night where the Sun never gets 18° below; no Sun array when a sample lacks it; no curve under two samples', () => {
    expect(checkVisibility({ ...wire, night: { date: '2026-06-21', dusk_utc: null, dawn_utc: null } })!.dark).toBeNull();
    expect(checkVisibility({ ...wire, samples: [wire.samples[0], { t_utc: '2026-11-01T18:10:00Z', alt_deg: 25 }] })!.sun).toBeNull();
    expect(checkVisibility({ ...wire, samples: [wire.samples[0]] })).toBeNull();
  });
});

describe('calls', () => {
  const config = resolveConfig('?api=http://127.0.0.1:8762&token=dev');
  const calls: { url: string; init: RequestInit }[] = [];
  const client = new ArgosClient(config, {
    fetch: async (url, init = {}) => {
      calls.push({ url, init });
      if (url.includes('/api/mount/goto')) return new Response(JSON.stringify({ error: { code: 'run_active', message: 'A sequence is running.' } }), { status: 409 });
      return new Response('{}', { status: 200 });
    },
  });
  const sent = () => calls.map((c) => [c.url.replace('http://127.0.0.1:8762', ''), c.init.method, c.init.body ?? null]);

  it('start: {} keeps the draft time, null starts now, a time schedules (Q-P2)', async () => {
    calls.length = 0;
    await sequenceApi.start(client);
    await sequenceApi.start(client, null);
    await sequenceApi.start(client, Date.UTC(2026, 10, 12, 23, 30) / 1000);
    expect(sent()).toEqual([
      ['/api/sequence/start', 'POST', '{}'],
      ['/api/sequence/start', 'POST', '{"start_at_utc":null}'],
      ['/api/sequence/start', 'POST', '{"start_at_utc":"2026-11-12T23:30:00Z"}'],
    ]);
  });

  it('pause, resume, stop, state and preflight', async () => {
    calls.length = 0;
    await sequenceApi.pause(client);
    await sequenceApi.resume(client);
    await sequenceApi.stop(client);
    await sequenceApi.state(client);
    await sequenceApi.preflight(client);
    await sequenceApi.preflight(client, Date.UTC(2026, 10, 12, 23, 30) / 1000);
    expect(sent().map((c) => `${c[1]} ${c[0]}`)).toEqual([
      'POST /api/sequence/pause',
      'POST /api/sequence/resume',
      'POST /api/sequence/stop',
      'GET /api/sequence',
      'GET /api/sequence/preflight',
      'GET /api/sequence/preflight?start_at_utc=2026-11-12T23%3A30%3A00Z',
    ]);
  });

  it('asks visibility for the client-chosen night (S26)', async () => {
    calls.length = 0;
    await sequenceApi.visibility(client, { ra_hours: 15.99, dec_deg: 25.92, night: '2026-11-01', step_min: 10 });
    expect(calls[0].url).toBe('http://127.0.0.1:8762/api/visibility?ra_hours=15.99&dec_deg=25.92&night=2026-11-01&step_min=10');
  });

  it('recognises the interlock refusal', async () => {
    const err = await client.request('POST', '/api/mount/goto', {}).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(isRunActive(err)).toBe(true);
    expect(isRunActive(new ApiError(409, 'busy', 'x'))).toBe(false);
  });
});

describe('time helpers', () => {
  it('round-trip ISO UTC and refuse unreadable times', () => {
    expect(isoOf(Date.UTC(2026, 10, 12, 23, 30, 5) / 1000)).toBe('2026-11-12T23:30:05Z');
    expect(unixOf('2026-11-12T23:30:05Z')).toBe(Date.UTC(2026, 10, 12, 23, 30, 5) / 1000);
    expect(unixOf('')).toBeNull();
    expect(unixOf('soon')).toBeNull();
    expect(unixOf(12)).toBeNull();
  });
});
