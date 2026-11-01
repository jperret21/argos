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
    // API 2 levels are accepted; an unknown level is not.
    for (const level of ['debug', 'cmd', 'ok']) {
      expect(parseEventMessage(JSON.stringify({ type: 'log', level, message: 'x', seq: 3 }))).not.toBeNull();
    }
    expect(parseEventMessage(JSON.stringify({ type: 'log', level: 'trace', message: 'x' }))).toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'future_thing' }))).toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'status', connection: {} }))).toBeNull();
    expect(parseEventMessage('not json')).toBeNull();
    expect(parseEventMessage(new ArrayBuffer(4))).toBeNull();
  });

  it('accepts the API 2 snapshot and stream events', () => {
    const accepted = [
      { type: 'devices', devices: {} },
      { type: 'network', seestar: null, internet: null, host: null, port: null, t: null, internet_t: null },
      { type: 'activity', text: 'Connecting mount 192.168.1.42:32323…', source: 'mount', t: 'x' },
      { type: 'config', changed: { 'alpaca.port': 1 }, values: {}, revision: 2, source: 'api' },
      { type: 'job', job: { id: 'j1', kind: 'discovery', state: 'running' } },
    ];
    for (const m of accepted) expect(parseEventMessage(JSON.stringify(m))).not.toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'devices' }))).toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'job', job: { kind: 'x' } }))).toBeNull();
    expect(parseEventMessage(JSON.stringify({ type: 'config', changed: {} }))).toBeNull();
  });
});

describe('ArgosEvents', () => {
  const config = {
    apiBase: 'http://127.0.0.1:8742',
    wsBase: 'ws://127.0.0.1:8742',
    token: 't',
    source: { api: 'default', token: 'default' },
  } as const;
  const status = (devices?: unknown) =>
    JSON.stringify({
      type: 'status',
      connection: { state: 'disconnected', mode: null, device_name: null, message: null },
      camera: { state: 'idle', exposure_s: 2, gain: 80, last_frame_seq: null, sensor: null },
      mount: { state: 'idle', ra_hours: 0, dec_deg: 0, alt_deg: null, az_deg: null, tracking: false, pier_side: null, target: null },
      ...(devices ? { devices, profile: { key: 's30pro', name: 'ZWO Seestar S30 Pro', validated: true } } : {}),
    });

  it('forwards every log line (v1 and v2) to onLog; the log store deduplicates', async () => {
    const { ArgosEvents } = await import('./events.svelte');
    const seen: unknown[] = [];
    const events = new ArgosEvents({ ...config, source: { ...config.source } }, { onLog: (m) => seen.push(m) });
    const feed = (data: unknown) => (events as unknown as { handle(d: unknown): void }).handle(data);
    feed(JSON.stringify({ type: 'log', level: 'info', message: 'Connected', t: '2026-11-01T21:00:00.000Z' }));
    feed(
      JSON.stringify({
        type: 'log',
        id: 7,
        seq: 7,
        level: 'ok',
        source: 'mount',
        topic: 'connection',
        message: 'Mount connected: Seestar',
        t: '2026-11-01T21:00:01.000Z',
      }),
    );
    expect(seen).toHaveLength(2);
    expect(seen[1]).toMatchObject({ seq: 7, level: 'ok', source: 'mount', topic: 'connection' });
  });

  it('keeps devices and profile from the status record and fires onFirstStatus once per connection', async () => {
    const { ArgosEvents } = await import('./events.svelte');
    let firsts = 0;
    const events = new ArgosEvents({ ...config, source: { ...config.source } }, { onFirstStatus: () => firsts++ });
    const feed = (data: unknown) => (events as unknown as { handle(d: unknown): void }).handle(data);
    const dev = { state: 'disconnected', name: null, info: null, error: null, retrying: false, warnings: [], link: null, since: 'x' };
    feed(status({ mount: dev, camera: dev, filterwheel: dev, focuser: dev }));
    feed(status({ mount: dev, camera: dev, filterwheel: dev, focuser: dev }));
    expect(firsts).toBe(1);
    expect(events.devices?.focuser.state).toBe('disconnected');
    expect(events.profile?.key).toBe('s30pro');
    feed(JSON.stringify({ type: 'devices', devices: { mount: { ...dev, state: 'connecting' }, camera: dev, filterwheel: dev, focuser: dev } }));
    expect(events.devices?.mount.state).toBe('connecting');
    feed(JSON.stringify({ type: 'network', seestar: false, internet: null, host: '10.0.0.1', port: 32323, t: 'x', internet_t: null }));
    expect(events.network).toMatchObject({ seestar: false, host: '10.0.0.1' });
    expect((events.network as unknown as Record<string, unknown>).type).toBeUndefined();
  });
});

describe('ArgosClient API 2 routes', () => {
  function recorder() {
    const calls: { url: string; method: string; body: unknown }[] = [];
    const fetch = async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return new Response('{}', { status: 200 });
    };
    return { calls, fetch };
  }

  it('sends the documented methods, paths and bodies', async () => {
    const { ArgosClient } = await import('./client');
    const r = recorder();
    const c = new ArgosClient(
      { apiBase: 'http://h:1', wsBase: 'ws://h:1', token: 't', source: { api: 'default', token: 'default' } },
      { fetch: r.fetch },
    );
    await c.connectDevice('camera', { mode: 'alpaca', host: '10.0.0.1', port: 32323 });
    await c.disconnectDevice('mount');
    await c.connectAll({ mode: 'simulator' });
    await c.disconnectAll();
    await c.startDiscovery();
    await c.setProfile('s50');
    await c.checkNetwork(true);
    await c.cancelJob('a/b');
    await c.logs({ after: 12, limit: 5000 });
    await c.patchConfig({ 'alpaca.host': '10.0.0.1' });
    expect(r.calls.map((x) => `${x.method} ${x.url.replace('http://h:1', '')}`)).toEqual([
      'POST /api/devices/camera/connect',
      'DELETE /api/devices/mount',
      'POST /api/devices/connect-all',
      'DELETE /api/devices',
      'POST /api/discovery',
      'PUT /api/profile',
      'POST /api/network/check',
      'DELETE /api/jobs/a%2Fb',
      'GET /api/logs?after=12&limit=5000',
      'PATCH /api/config',
    ]);
    expect(r.calls[0].body).toEqual({ mode: 'alpaca', host: '10.0.0.1', port: 32323 });
    expect(r.calls[5].body).toEqual({ key: 's50' });
    expect(r.calls[6].body).toEqual({ internet: true });
  });

  it('keeps the API 2 error extras (fields, owner)', async () => {
    const e = errorFromResponse(
      409,
      'Conflict',
      JSON.stringify({ error: { code: 'busy', message: 'Discovery is running', owner: 'job-1' } }),
    );
    expect(e.owner).toBe('job-1');
    const f = errorFromResponse(
      400,
      'Bad Request',
      JSON.stringify({ error: { code: 'invalid_argument', message: 'x', fields: { 'alpaca.port': 'Range 1–65535' } } }),
    );
    expect(f.fields).toEqual({ 'alpaca.port': 'Range 1–65535' });
  });
});
