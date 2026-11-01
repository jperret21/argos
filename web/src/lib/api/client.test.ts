import { describe, expect, it } from 'vitest';
import { resolveConfig } from '../config';
import { ApiError, ArgosClient, errorFromResponse, NETWORK_ERROR, TIMEOUT } from './client';
import { parseEventMessage } from './events.svelte';

const config = resolveConfig('?api=http://127.0.0.1:8761&token=dev');

interface Call {
  url: string;
  init: RequestInit;
}

function fakeFetch(respond: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetch = async (url: string, init: RequestInit = {}) => {
    const call = { url, init };
    calls.push(call);
    return respond(call);
  };
  return { calls, fetch };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('ArgosClient', () => {
  it('sends the bearer token and JSON body, returns the typed answer', async () => {
    const answer = { state: 'live', exposure_s: 1, gain: 80, last_frame_seq: null, sensor: null };
    const f = fakeFetch(() => json(200, answer));
    const client = new ArgosClient(config, { fetch: f.fetch });
    const res = await client.startLive({ exposure_s: 1, gain: 80 });

    expect(res).toEqual(answer);
    expect(f.calls[0]!.url).toBe('http://127.0.0.1:8761/api/camera/live');
    expect(f.calls[0]!.init.method).toBe('POST');
    const headers = f.calls[0]!.init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer dev');
    expect(headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(f.calls[0]!.init.body as string)).toEqual({ exposure_s: 1, gain: 80 });
  });

  it('does not send the token to /api/health', async () => {
    const f = fakeFetch(() => json(200, { ok: true, version: '0.4.2', api: 1 }));
    const client = new ArgosClient(config, { fetch: f.fetch });
    expect((await client.health()).api).toBe(1);
    const headers = f.calls[0]!.init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it('turns a contract error body into an ApiError', async () => {
    const f = fakeFetch(() => json(409, { error: { code: 'not_connected', message: 'Connect first' } }));
    const client = new ArgosClient(config, { fetch: f.fetch });
    const err = await client.capture({ exposure_s: 1, gain: 0 }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).code).toBe('not_connected');
    expect((err as ApiError).message).toBe('Connect first');
  });

  it('maps transport failures to status 0', async () => {
    const down = new ArgosClient(config, {
      fetch: () => Promise.reject(new TypeError('Failed to fetch')),
    });
    const err = (await down.status().catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe(NETWORK_ERROR);
    expect(err.status).toBe(0);
    expect(err.isNetwork).toBe(true);

    const slow = new ArgosClient(config, {
      timeoutMs: 10,
      fetch: (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    });
    const late = (await slow.status().catch((e: unknown) => e)) as ApiError;
    expect(late.code).toBe(TIMEOUT);
  });
});

describe('errorFromResponse', () => {
  it('falls back gracefully on non-contract bodies', () => {
    expect(errorFromResponse(401, 'Unauthorized', '').code).toBe('unauthorized');
    expect(errorFromResponse(401, 'Unauthorized', '').isUnauthorized).toBe(true);
    const e = errorFromResponse(502, 'Bad Gateway', '<html>proxy</html>');
    expect(e.code).toBe('http_502');
    expect(e.message).toBe('<html>proxy</html>');
    expect(errorFromResponse(500, '', '{"detail": "x"}').code).toBe('http_500');
  });
});

describe('parseEventMessage', () => {
  it('accepts contract messages and ignores everything else', () => {
    const mount = {
      state: 'tracking',
      ra_hours: 5.5,
      dec_deg: -5.4,
      alt_deg: 40,
      az_deg: 180,
      tracking: true,
      pier_side: 'west',
      target: null,
    };
    expect(parseEventMessage(JSON.stringify({ type: 'mount', mount }))).toEqual({ type: 'mount', mount });
    expect(
      parseEventMessage(JSON.stringify({ type: 'log', level: 'info', message: 'hi', t: '2026-11-01T00:00:00Z' })),
    ).not.toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'log', level: 'debug', message: 'x' }))).toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'future_thing' }))).toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'status', connection: {} }))).toBeNull();
    expect(parseEventMessage('not json')).toBeNull();
    expect(parseEventMessage(new ArrayBuffer(4))).toBeNull();
  });
});

describe('ArgosEvents log replay', () => {
  it('drops server log lines it already holds (replayed after a reconnection)', async () => {
    const { ArgosEvents } = await import('./events.svelte');
    const events = new ArgosEvents({
      apiBase: 'http://127.0.0.1:8742',
      wsBase: 'ws://127.0.0.1:8742',
      token: 't',
      source: { api: 'default', token: 'default' },
    });
    const feed = (data: unknown) => (events as unknown as { handle(d: unknown): void }).handle(data);
    const line = (message: string, t: string) => JSON.stringify({ type: 'log', level: 'info', message, t });
    feed(line('Connected', '2026-11-01T21:00:00.000Z'));
    feed(line('Live view: 1 s, gain 80', '2026-11-01T21:00:01.000Z'));
    // Reconnection: the server replays its history, then a new line.
    feed(line('Connected', '2026-11-01T21:00:00.000Z'));
    feed(line('Live view: 1 s, gain 80', '2026-11-01T21:00:01.000Z'));
    feed(line('Connected', '2026-11-01T21:05:00.000Z')); // same text, new event: kept
    expect(events.logs.map((l) => l.t)).toEqual([
      '2026-11-01T21:00:00.000Z',
      '2026-11-01T21:00:01.000Z',
      '2026-11-01T21:05:00.000Z',
    ]);
  });
});
