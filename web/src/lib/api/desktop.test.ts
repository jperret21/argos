import { describe, expect, it } from 'vitest';
import { ApiError, ArgosClient, errorFromResponse } from './client';
import { busyItemsOf, checkBusyItem, checkShutdownEvent, isMissingRoute, normaliseKind, requestShutdown, revealPath } from './desktop';
import { resolveConfig } from '../config';

/** A client whose fetch answers with `status` and `body` (and records the calls). */
function clientAnswering(status: number, body: string, calls: { url: string; init?: RequestInit }[] = []): ArgosClient {
  return new ArgosClient(resolveConfig('?api=http://127.0.0.1:8781&token=t'), {
    fetch: async (url, init) => {
      calls.push({ url, init });
      return new Response(status === 204 ? null : body, { status, statusText: 'x' });
    },
  });
}

function refusingClient(err: unknown): ArgosClient {
  return new ArgosClient(resolveConfig('?api=http://127.0.0.1:8781&token=t'), {
    fetch: async () => {
      throw err;
    },
  });
}

describe('A7 POST /api/app/shutdown', () => {
  it('sends force and reads 202 (with or without a body) as accepted', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const started = { state: 'shutting_down', forced: false, what: [], stages: [{ id: 'sequence', label: 'Stopping the sequence' }, { id: 'exit', label: 'Stopping the ARGOS server' }], budget_s: 60 };
    expect(await requestShutdown(clientAnswering(202, JSON.stringify(started), calls), false)).toEqual({
      outcome: 'accepted',
      stages: [
        { id: 'sequence', label: 'Stopping the sequence' },
        { id: 'exit', label: 'Stopping the ARGOS server' },
      ],
      budgetS: 60,
    });
    expect(calls[0].url).toBe('http://127.0.0.1:8781/api/app/shutdown');
    expect(calls[0].init?.method).toBe('POST');
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ force: false });
    expect(await requestShutdown(clientAnswering(202, ''), true)).toEqual({ outcome: 'accepted', stages: [], budgetS: null });
  });

  it('reads 409 busy with what in the error or in its details', async () => {
    const body = JSON.stringify({ error: { code: 'busy', message: 'A sequence is running.', what: ['sequence', { kind: 'exposing', label: 'Exposing 10 s' }] } });
    expect(await requestShutdown(clientAnswering(409, body), false)).toEqual({
      outcome: 'busy',
      message: 'A sequence is running.',
      items: [
        { kind: 'sequence', label: null, detail: null },
        { kind: 'exposure', label: 'Exposing 10 s', detail: null },
      ],
    });
    const nested = JSON.stringify({ error: { code: 'busy', message: 'Busy', details: { what: ['live', 'live', 'slewing'] } } });
    const answer = await requestShutdown(clientAnswering(409, nested), false);
    expect(answer.outcome === 'busy' && answer.items.map((i) => i.kind)).toEqual(['live', 'slew']);
  });

  it("reads the server's BusyItem: its sentence, a job by its own kind", async () => {
    const what = [
      { kind: 'run', text: 'A sequence is running: SS Cyg, 34 of 120 frames.', job_id: null, job_kind: null },
      { kind: 'job', text: 'Plate-solving the frame.', job_id: 'j1', job_kind: 'field_solve' },
      { kind: 'job', text: 'Scanning the sessions folder.', job_id: 'j2', job_kind: 'sessions_scan' },
      { kind: 'write', text: 'A FITS file is being written.', job_id: null, job_kind: null },
      { kind: 'write', text: 'Writing an export file.', job_id: 'j3', job_kind: 'export' },
    ];
    const body = JSON.stringify({ error: { code: 'busy', message: 'Quitting now would stop this: …', details: { what } } });
    const answer = await requestShutdown(clientAnswering(409, body), false);
    expect(answer.outcome === 'busy' && answer.items.map((i) => [i.kind, i.label])).toEqual([
      ['sequence', 'A sequence is running: SS Cyg, 34 of 120 frames.'],
      ['solve', 'Plate-solving the frame.'],
      ['sessions_scan', 'Scanning the sessions folder.'],
      ['write', 'A FITS file is being written.'],
      ['export', 'Writing an export file.'],
    ]);
  });

  it('treats a shutdown already under way as accepted', async () => {
    const body = JSON.stringify({ error: { code: 'shutting_down', message: 'Already stopping' } });
    expect(await requestShutdown(clientAnswering(409, body), false)).toEqual({ outcome: 'accepted', stages: [], budgetS: null });
    expect(await requestShutdown(clientAnswering(503, body), false)).toEqual({ outcome: 'accepted', stages: [], budgetS: null });
  });

  it('a server without the route is unsupported; no server is unreachable', async () => {
    const missing = JSON.stringify({ error: { code: 'not_found', message: 'Not Found' } });
    expect(await requestShutdown(clientAnswering(404, missing), false)).toEqual({ outcome: 'unsupported' });
    expect(await requestShutdown(clientAnswering(405, '{"detail":"Method Not Allowed"}'), false)).toEqual({ outcome: 'unsupported' });
    const gone = await requestShutdown(refusingClient(new TypeError('Load failed')), false);
    expect(gone.outcome).toBe('unreachable');
  });

  it('throws any other refusal with the server words', async () => {
    const body = JSON.stringify({ error: { code: 'internal_error', message: 'Boom' } });
    await expect(requestShutdown(clientAnswering(500, body), false)).rejects.toMatchObject({ status: 500, code: 'internal_error', message: 'Boom' });
  });
});

describe('busy items', () => {
  it('normalises the kinds the busy summary spells otherwise', () => {
    expect(['slewing', 'solving', 'batch', 'downloading', 'Field-Solve', 'filter_wheel'].map(normaliseKind)).toEqual(['slew', 'solve', 'rerun', 'exposure', 'solve', 'filterwheel']);
  });

  it('reads strings and objects, drops unusable entries', () => {
    expect(checkBusyItem('  ')).toBeNull();
    expect(checkBusyItem(3)).toBeNull();
    expect(checkBusyItem({ label: 'no kind' })).toBeNull();
    expect(checkBusyItem({ id: 'rerun', text: 'Re-run of SS Cyg', detail: '120 frames' })).toEqual({ kind: 'rerun', label: 'Re-run of SS Cyg', detail: '120 frames' });
    expect(busyItemsOf(null)).toEqual([]);
    expect(busyItemsOf({ what: 'sequence' })).toEqual([]);
  });

  it('keeps the whole error member on ApiError', () => {
    const err = errorFromResponse(409, 'Conflict', JSON.stringify({ error: { code: 'busy', message: 'm', what: ['live'] } }));
    expect(err.body).toEqual({ code: 'busy', message: 'm', what: ['live'] });
    expect(new ApiError(0, 'network_error', 'x').body).toBeNull();
  });

  it('tells a missing route from a missing file', () => {
    expect(isMissingRoute(new ApiError(404, 'not_found', 'Not Found'))).toBe(true);
    expect(isMissingRoute(new ApiError(404, 'http_404', 'whatever'))).toBe(true);
    expect(isMissingRoute(new ApiError(404, 'not_found', 'No file at /tmp/x.zip'))).toBe(false);
    expect(isMissingRoute(new Error('Not Found'))).toBe(false);
  });
});

describe('WS shutdown events', () => {
  it('reads a stage, its words and the end', () => {
    expect(checkShutdownEvent({ type: 'shutdown', stage: 'Sequence', t: 12.5 })).toEqual({ stage: 'sequence', label: null, t: 12.5, index: null, count: null, done: false });
    expect(
      checkShutdownEvent({ type: 'shutdown', stage: 'devices', label: 'Closing the equipment connections', index: 3, count: 5, forced: false, budget_s: 60, t: '2026-11-15T21:04:11Z' }),
    ).toEqual({ stage: 'devices', label: 'Closing the equipment connections', t: Date.parse('2026-11-15T21:04:11Z') / 1000, index: 3, count: 5, done: false });
    expect(checkShutdownEvent({ type: 'shutdown', stage: 'exit', label: 'Stopping the ARGOS server', index: 5, count: 5 })?.done).toBe(true);
    expect(checkShutdownEvent({ type: 'shutdown', stage: 'devices', message: 'Disconnecting the mount' })?.label).toBe('Disconnecting the mount');
    expect(checkShutdownEvent({ type: 'shutdown', stage: 'done' })?.done).toBe(true);
    expect(checkShutdownEvent({ type: 'shutdown', stage: 'server', done: true })?.done).toBe(true);
  });

  it('ignores other messages', () => {
    expect(checkShutdownEvent({ type: 'status' })).toBeNull();
    expect(checkShutdownEvent({ type: 'shutdown' })).toBeNull();
    expect(checkShutdownEvent('shutdown')).toBeNull();
  });
});

describe('A12 POST /api/fs/reveal', () => {
  it('sends the path; 204 and JSON answers both reveal', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    expect(await revealPath(clientAnswering(204, '', calls), '/Users/o/Desktop/a.zip')).toBe('revealed');
    expect(calls[0].url).toBe('http://127.0.0.1:8781/api/fs/reveal');
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ path: '/Users/o/Desktop/a.zip' });
    expect(await revealPath(clientAnswering(200, '{"path":"/x"}'), '/x')).toBe('revealed');
  });

  it('is unsupported without the route, and throws the server words otherwise', async () => {
    expect(await revealPath(clientAnswering(404, '{"error":{"code":"not_found","message":"Not Found"}}'), '/x')).toBe('unsupported');
    await expect(revealPath(clientAnswering(404, '{"error":{"code":"not_found","message":"No file or folder at /x"}}'), '/x')).rejects.toThrow('No file or folder at /x');
    await expect(revealPath(clientAnswering(403, '{"error":{"code":"forbidden_path","message":"Outside the allowed folders"}}'), '/etc')).rejects.toMatchObject({ code: 'forbidden_path' });
    // A server the shell did not start (development): the shell reveals instead.
    expect(await revealPath(clientAnswering(403, '{"error":{"code":"desktop_only","message":"Desktop app only"}}'), '/x')).toBe('unsupported');
  });
});
