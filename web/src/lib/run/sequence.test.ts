import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { MountInterlock, interlockText } from './interlock.svelte';
import { checkSaved, SequenceStore } from './sequence.svelte';

const ROOT = '/data/sessions/20261101T204502Z_T_CrB';
const rec = (over: Record<string, unknown> = {}) => ({ type: 'sequence', state: 'running', run_id: 'r1', run_root: ROOT, frames_done: 1, frames_total: 50, ...over });
const save = (seq: number, t: string, over: Record<string, unknown> = {}) => ({
  type: 'frame_saved',
  seq,
  source: 'sequence',
  path: `${ROOT}/lights/T_CrB_LP_Light_e30000ms_g80_${String(seq).padStart(5, '0')}.fit`,
  name: `T_CrB_LP_Light_e30000ms_g80_${String(seq).padStart(5, '0')}.fit`,
  t,
  record: { hfd: 2.1, fwhm: 2.6, star_count: 143 },
  ...over,
});

function bus() {
  const subs = new Map<string, Set<(m: Record<string, unknown>) => void>>();
  return {
    on(type: string, fn: (m: Record<string, unknown>) => void) {
      if (!subs.has(type)) subs.set(type, new Set());
      subs.get(type)!.add(fn);
      return () => subs.get(type)!.delete(fn);
    },
    emit(m: Record<string, unknown>) {
      for (const fn of subs.get(m.type as string) ?? []) fn(m);
    },
  };
}

describe('saved subs of the run', () => {
  it('keeps the sequence saves inside the run folder only', () => {
    expect(checkSaved(save(1, '2026-11-01T20:46:00Z'), ROOT)?.hfd).toBe(2.1);
    expect(checkSaved(save(1, '2026-11-01T20:46:00Z', { source: 'single' }), ROOT)).toBeNull();
    expect(checkSaved(save(1, '2026-11-01T20:46:00Z', { path: '/elsewhere/x.fit' }), ROOT)).toBeNull();
    expect(checkSaved(save(1, 'later'), ROOT)).toBeNull();
  });
});

describe('SequenceStore', () => {
  it('follows the WS record, the status record and the saves; a new run starts again', () => {
    const s = new SequenceStore();
    const b = bus();
    s.attach(b);
    b.emit({ type: 'status', sequence: rec() });
    expect(s.state?.state).toBe('running');
    b.emit(save(1, '2026-11-01T20:46:00Z'));
    b.emit(save(2, '2026-11-01T20:46:32Z'));
    b.emit(save(2, '2026-11-01T20:46:32Z')); // a replay: once
    b.emit(save(3, '2026-11-01T20:47:04Z', { source: 'single' }));
    expect(s.frameTimes.length).toBe(2);
    expect(s.lastSaved?.seq).toBe(2);
    expect(s.lastFrameAt).toBe(Date.UTC(2026, 10, 1, 20, 46, 32) / 1000);
    b.emit(rec({ run_id: 'r2', run_root: `${ROOT}_2` }));
    expect(s.frameTimes).toEqual([]);
    expect(s.lastSaved).toBeNull();
  });

  it('keeps the subs once the run ends, so the strip and the card still show them', () => {
    const s = new SequenceStore();
    s.ingest(rec());
    s.ingestSaved(save(1, '2026-11-01T20:46:00Z'));
    s.ingest(rec({ state: 'idle', last_result: { completed: true, frames_saved: 1, ended_utc: '2026-11-01T20:47:00Z' } }));
    expect(s.frameTimes.length).toBe(1);
    expect(s.outcomeVisible).toBe(true);
    s.dismissOutcome();
    expect(s.outcomeVisible).toBe(false);
    // The next run's end brings the outcome back.
    s.ingest(rec({ run_id: 'r2', state: 'running', last_result: null }));
    s.ingest(rec({ run_id: 'r2', state: 'idle', last_result: { completed: false, reason: 'stopped', frames_saved: 4, ended_utc: '2026-11-01T22:00:00Z' } }));
    expect(s.outcomeVisible).toBe(true);
  });

  it('never adopts the saves of an older run while waiting, idle, or before its folder is known', () => {
    const s = new SequenceStore();
    expect(s.ingestSaved(save(1, '2026-11-01T20:46:00Z'))).toBe(false); // no record yet
    s.ingest(rec({ run_id: 'r9', state: 'waiting', run_root: null, started_utc: null }));
    expect(s.ingestSaved(save(1, '2026-11-01T20:46:00Z'))).toBe(false);
    s.ingest(rec({ run_id: 'r9', state: 'running', run_root: null, started_utc: '2026-11-01T21:00:00Z' }));
    expect(s.ingestSaved(save(2, '2026-11-01T20:46:32Z', { path: '/old/run/a.fit' }))).toBe(false); // before the start
    expect(s.ingestSaved(save(3, '2026-11-01T21:00:05Z', { path: '/new/run/lights/b.fit' }))).toBe(true);
    expect(s.frameTimes.length).toBe(1);
  });

  it('reads back missed saves after a reconnection, in time order', async () => {
    const s = new SequenceStore();
    s.ingest(rec());
    s.ingestSaved(save(3, '2026-11-01T20:47:04Z'));
    const asked: string[] = [];
    const client = {
      request: async <T,>(method: string, path: string): Promise<T> => {
        asked.push(`${method} ${path}`);
        if (path === '/api/sequence') return rec({ frames_done: 3 }) as T;
        return { saves: [save(1, '2026-11-01T20:46:00Z'), save(2, '2026-11-01T20:46:32Z'), save(3, '2026-11-01T20:47:04Z')] } as T;
      },
    };
    await s.refresh(client);
    expect(asked).toEqual(['GET /api/sequence', 'GET /api/camera/saved']);
    expect(s.state?.frames_done).toBe(3);
    expect(s.frameTimes.map((t) => t - s.frameTimes[0])).toEqual([0, 32, 64]);
    expect(s.cadence).toBe(32);
  });

  it('sends the transport to the server and rejects with its words', async () => {
    const paths: string[] = [];
    const client = {
      request: async <T,>(_m: string, path: string, body?: unknown): Promise<T> => {
        paths.push(`${path} ${JSON.stringify(body ?? null)}`);
        if (path.endsWith('/start')) throw new ApiError(409, 'not_connected', 'Connect the camera before running a sequence.');
        return {} as T;
      },
    };
    const s = new SequenceStore();
    await expect(s.start(null, client)).rejects.toThrow('Connect the camera before running a sequence.');
    await s.pause(client);
    await s.resume(client);
    await s.stop(client);
    expect(paths).toEqual(['/api/sequence/start {"start_at_utc":null}', '/api/sequence/pause {}', '/api/sequence/resume {}', '/api/sequence/stop {}']);
    await expect(new SequenceStore().pause()).rejects.toThrow('Not connected');
  });
});

describe('MountInterlock (D2)', () => {
  it('turns 409 run_active into the question, and the way through sends pause_run', async () => {
    const lock = new MountInterlock();
    const sent: boolean[] = [];
    const goto = async (pauseRun: boolean) => {
      sent.push(pauseRun);
      if (!pauseRun) throw new ApiError(409, 'run_active', 'A sequence is running: the mount stays on target.');
      return 'slewing';
    };
    expect(await lock.run({ action: 'GoTo' }, goto)).toBeUndefined();
    expect(lock.pending?.message).toBe('A sequence is running: the mount stays on target.');
    expect(interlockText(lock.pending!).confirm).toBe('Pause the run and slew');
    // The words say what happens without quoting the button (design review W6a).
    const words = interlockText(lock.pending!, 10);
    expect(words.body).toBe('GoTo would move the field under the run. Pausing lets the 10 s sub in progress finish and be saved; the mount then moves, and the run stays paused until you resume it.');
    expect(words.holdVerb).toBe('pause the run and slew');
    await lock.confirm();
    expect(sent).toEqual([false, true]);
    expect(lock.pending).toBeNull();
  });

  it('passes the answer through when there is no run, and rethrows any other refusal', async () => {
    const lock = new MountInterlock();
    expect(await lock.run({ action: 'GoTo' }, async () => 'ok')).toBe('ok');
    await expect(lock.run({ action: 'Park', verb: 'park' }, async () => Promise.reject(new ApiError(409, 'busy', 'Slewing')))).rejects.toThrow('Slewing');
    expect(lock.pending).toBeNull();
  });

  it('a jog refused during a run only pauses the run (a dead-man jog is never resent)', async () => {
    const lock = new MountInterlock();
    const done: string[] = [];
    lock.ask({ action: 'Jog', verb: 'jog', through: async () => done.push('pause') }, 'A sequence is running — Jog would move the field under it.', async () => done.push('jog'));
    const text = interlockText(lock.pending!);
    expect(text.confirm).toBe('Pause the run');
    expect(text.title).toBe('A sequence is running');
    expect(text.body).toMatch(/^Jog would move the field under the run\. Pausing lets the sub in progress finish and be saved; jog again once the run shows Paused\./);
    await lock.confirm();
    expect(done).toEqual(['pause']);
    expect(lock.pending).toBeNull();
  });

  it('keeps the question open when the retry is refused, and Cancel sends nothing', async () => {
    const lock = new MountInterlock();
    let calls = 0;
    await lock.run({ action: 'Park', verb: 'park' }, async (p) => {
      calls++;
      throw p ? new ApiError(409, 'busy', 'The run is stopping') : new ApiError(409, 'run_active', 'A sequence is running.');
    });
    await expect(lock.confirm()).rejects.toThrow('The run is stopping');
    expect(lock.pending?.verb).toBe('park');
    lock.cancel();
    expect(lock.pending).toBeNull();
    expect(calls).toBe(2);
  });
});
