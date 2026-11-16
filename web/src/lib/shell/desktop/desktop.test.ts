import { describe, expect, it } from 'vitest';
import { ApiError } from '../../api/client';
import { resolveConfig } from '../../config';
import { checkDownload, checkServerState, crashView, DesktopShell, readyUrl } from './desktop.svelte';

interface Call {
  cmd: string;
  args?: Record<string, unknown>;
}

function fakeShell(platform = 'MacIntel') {
  const calls: Call[] = [];
  const callbacks = new Map<number, (r: unknown) => void>();
  let id = 1;
  let eventId = 50;
  const host = {
    navigator: { platform, userAgent: '' },
    __TAURI_INTERNALS__: {
      transformCallback(cb: (r: unknown) => void) {
        callbacks.set(id, cb);
        return id++;
      },
      invoke(cmd: string, args?: Record<string, unknown>) {
        calls.push({ cmd, args });
        return Promise.resolve(cmd === 'plugin:event|listen' ? eventId++ : null);
      },
    },
  };
  /** Deliver a shell event to the UI's listener. */
  const send = (event: string, payload?: unknown) => {
    const listen = calls.find((c) => c.cmd === 'plugin:event|listen' && c.args?.event === event);
    callbacks.get(listen?.args?.handler as number)?.({ event, id: 0, payload });
  };
  const emitted = () => calls.filter((c) => c.cmd === 'plugin:event|emit').map((c) => c.args?.event);
  return { host, calls, send, emitted };
}

function fakeEvents() {
  const handlers = new Map<string, (m: Record<string, unknown>) => void>();
  return {
    link: 'open' as 'open' | 'reconnecting',
    on(type: string, fn: (m: Record<string, unknown>) => void) {
      handlers.set(type, fn);
      return () => handlers.delete(type);
    },
    send(m: Record<string, unknown>) {
      handlers.get(String(m.type))?.(m);
    },
  };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

function make(search: string, shell = fakeShell()) {
  const navigated: string[] = [];
  const config = resolveConfig(search);
  const desktop = new DesktopShell({
    client: { request: () => Promise.reject(new Error('unused')) } as never,
    config,
    activity: () => ({}),
    search,
    host: shell.host,
    navigate: (u) => navigated.push(u),
  });
  return { desktop, navigated, shell };
}

describe('server state', () => {
  it('reads the shell payload', () => {
    expect(checkServerState({ phase: 'ready', api: 'http://127.0.0.1:9', token: 't', log_dir: '~/Library/Logs/Argos' })).toMatchObject({
      phase: 'ready',
      api: 'http://127.0.0.1:9',
      token: 't',
      logDir: '~/Library/Logs/Argos',
    });
    expect(checkServerState({ phase: 'exploded' })).toBeNull();
    expect(checkServerState(null)).toBeNull();
  });

  it('reloads only on a local address with a token, keeping the other parameters', () => {
    expect(readyUrl('tauri://localhost/index.html?perf', 'http://127.0.0.1:51234/', 'tok')).toBe('tauri://localhost/index.html?perf=&api=http%3A%2F%2F127.0.0.1%3A51234&token=tok');
    expect(readyUrl('tauri://localhost/index.html', 'http://10.0.0.2:8742', 'tok')).toBeNull();
    expect(readyUrl('tauri://localhost/index.html', 'http://127.0.0.1:8742', null)).toBeNull();
    expect(readyUrl('not a url', 'http://127.0.0.1:8742', 't')).toBeNull();
  });

  it('words the crash notice', () => {
    const base = { api: null, token: null, title: null, cause: null, details: 'Traceback', logDir: '~/L', status: 'exit status 1', version: null };
    expect(crashView({ ...base, phase: 'ready' }, false)).toBeNull();
    expect(crashView(null, false)).toBeNull();
    const crash = crashView({ ...base, phase: 'stopped' }, false);
    expect(crash).toMatchObject({ kind: 'crash', title: 'The ARGOS server stopped unexpectedly', detail: 'Traceback', logPath: '~/L' });
    expect(crash?.message).toContain('(exit status 1)');
    expect(crash?.message).toContain('Restart server starts it again');
    // A deliberate stop: the scrim's words, no log.
    expect(crashView({ ...base, phase: 'stopped' }, true)).toMatchObject({
      kind: 'requested',
      title: 'The ARGOS server was shut down',
      message: 'Another ARGOS window or browser tab asked it to stop. Restart server starts it again.',
      detail: null,
      logPath: null,
    });
    expect(crashView({ ...base, phase: 'starting' }, false)?.kind).toBe('restarting');
    expect(crashView({ ...base, phase: 'failed', cause: 'No module named astropy' }, false)).toMatchObject({ kind: 'failed', message: 'No module named astropy' });
  });
});

describe('DesktopShell', () => {
  it('in a browser: nothing desktop, the server is ready', () => {
    const d = new DesktopShell({ client: {} as never, config: resolveConfig(''), activity: () => ({}), search: '', host: {} });
    expect(d.available).toBe(false);
    expect(d.titleBar).toBe(false);
    expect(d.waiting).toBe(false);
    expect(d.sidecar).toBe('ready');
    expect(d.crash).toBeNull();
  });

  it('waiting start-up: the sidecar stage, then a reload on the server', async () => {
    const { desktop, navigated, shell } = make('');
    expect(desktop.available).toBe(true);
    expect(desktop.platform).toBe('macos');
    expect(desktop.revealLabel).toBe('Reveal in Finder');
    expect(desktop.waiting).toBe(true);
    expect(desktop.sidecar).toBe('starting');
    const stop = desktop.start(fakeEvents());
    await tick();
    expect(shell.emitted()).toEqual(['argos://ui-ready']);
    shell.send('argos://server-state', { phase: 'ready', api: 'http://127.0.0.1:51234', token: 'abc' });
    expect(navigated).toHaveLength(1);
    expect(navigated[0]).toContain('api=http%3A%2F%2F127.0.0.1%3A51234');
    expect(navigated[0]).toContain('token=abc');
    stop();
  });

  it('waiting start-up with adopt: the UI runs on the server in place (no reload)', async () => {
    const shell = fakeShell();
    const adopted: [string, string][] = [];
    const navigated: string[] = [];
    const desktop = new DesktopShell({
      client: { request: () => Promise.reject(new Error('unused')) } as never,
      config: resolveConfig(''),
      activity: () => ({}),
      search: '',
      host: shell.host,
      navigate: (u) => navigated.push(u),
      adopt: (api, token) => adopted.push([api, token]),
    });
    const stop = desktop.start(fakeEvents());
    await tick();
    expect(desktop.sidecar).toBe('starting');
    // Not a usable address: no adoption (and no reload either).
    shell.send('argos://server-state', { phase: 'ready', api: 'http://10.0.0.2:8742', token: 'abc' });
    expect(adopted).toEqual([]);
    shell.send('argos://server-state', { phase: 'ready', api: 'http://127.0.0.1:51234/', token: 'abc' });
    expect(adopted).toEqual([['http://127.0.0.1:51234', 'abc']]);
    expect(navigated).toEqual([]);
    expect(desktop.waiting).toBe(false);
    expect(desktop.sidecar).toBe('ready');
    stop();
  });

  it('waiting start-up failure: the shell words, Retry and the log folder go to the shell', async () => {
    const { desktop, shell } = make('');
    desktop.start(fakeEvents());
    await tick();
    shell.send('argos://server-state', { phase: 'failed', cause: 'The server did not start within 60 s.', details: 'last line', log_dir: '~/Library/Logs/Argos' });
    expect(desktop.sidecar).toBe('failed');
    expect(desktop.startupFailure).toEqual({ title: 'ARGOS could not start', message: 'The server did not start within 60 s.', detail: 'last line', logPath: '~/Library/Logs/Argos' });
    expect(desktop.crash).toBeNull(); // the start-up screen shows it, not the crash notice
    desktop.restartServer();
    desktop.openLogFolder();
    await tick();
    expect(shell.emitted()).toEqual(['argos://ui-ready', 'argos://restart-server', 'argos://open-log-folder']);
    expect(desktop.sidecar).toBe('starting');
  });

  it('waiting start-up: Quit asks the shell only, never the default address', async () => {
    let asked = 0;
    const shell = fakeShell();
    const desktop = new DesktopShell({
      client: { request: () => (asked++, Promise.reject(new Error('must not be called'))) } as never,
      config: resolveConfig(''),
      activity: () => ({}),
      search: '',
      host: shell.host,
    });
    await desktop.quit.request();
    await tick();
    expect(asked).toBe(0);
    expect(desktop.quit.phase).toBe('closing');
    expect(shell.emitted()).toEqual(['argos://quit']);
    desktop.quit.dispose();
  });

  it('running UI: the same server changes nothing; a crash shows the notice; a restart reloads', async () => {
    const { desktop, navigated, shell } = make('?api=http://127.0.0.1:8781&token=tok');
    expect(desktop.waiting).toBe(false);
    desktop.start(fakeEvents());
    await tick();
    shell.send('argos://server-state', { phase: 'ready', api: 'http://127.0.0.1:8781', token: 'tok' });
    expect(navigated).toEqual([]);
    expect(desktop.crash).toBeNull();
    shell.send('argos://server-state', { phase: 'stopped', status: 'signal 9', details: 'Killed' });
    expect(desktop.crash?.kind).toBe('crash');
    desktop.restartServer();
    expect(desktop.crash?.kind).toBe('restarting');
    shell.send('argos://server-state', { phase: 'ready', api: 'http://127.0.0.1:8790', token: 'new' });
    expect(navigated).toHaveLength(1);
  });

  it('a download ended: the shell says where (Downloads folder) or that it failed', async () => {
    const shell = fakeShell();
    const done: unknown[] = [];
    const desktop = new DesktopShell({
      client: {} as never,
      config: resolveConfig('?api=http://127.0.0.1:8781&token=tok'),
      activity: () => ({}),
      search: '?api=http://127.0.0.1:8781&token=tok',
      host: shell.host,
      ondownload: (d) => done.push(d),
    });
    desktop.start(fakeEvents());
    await tick();
    shell.send('argos://download', { status: 'saved', path: '/Users/o/Downloads/argos-log.txt', name: 'argos-log.txt' });
    shell.send('argos://download', { status: 'failed' });
    shell.send('argos://download', { status: 'odd' });
    expect(done).toEqual([
      { saved: true, path: '/Users/o/Downloads/argos-log.txt', name: 'argos-log.txt' },
      { saved: false, path: null, name: null },
    ]);
    expect(checkDownload(null)).toBeNull();
  });

  it('quit requests from the shell and the menu reach the UI', async () => {
    const shell = fakeShell('Linux x86_64');
    const menu: string[] = [];
    let asked = 0;
    const desktop = new DesktopShell({
      client: {
        request: () => {
          asked++;
          return Promise.resolve({});
        },
      } as never,
      config: resolveConfig('?api=http://127.0.0.1:8781&token=tok'),
      activity: () => ({}),
      search: '?api=http://127.0.0.1:8781&token=tok',
      host: shell.host,
      onmenu: (id) => menu.push(id),
    });
    expect(desktop.platform).toBe('linux');
    expect(desktop.revealLabel).toBe('Show in folder');
    desktop.start(fakeEvents());
    await tick();
    shell.send('argos://menu', { id: 'nav.observe' });
    shell.send('argos://menu', { id: 'evil' });
    expect(menu).toEqual(['nav.observe']);
    shell.send('argos://quit-requested');
    await tick();
    expect(asked).toBe(1);
    expect(desktop.quit.phase).toBe('stopping');
  });

  it('WS shutdown stages and the link feed the quit flow; no crash notice while quitting', async () => {
    const { desktop, shell } = make('?api=http://127.0.0.1:8781&token=tok');
    const events = fakeEvents();
    const stop = desktop.start(events);
    events.send({ type: 'shutdown', stage: 'sequence' });
    expect(desktop.quit.phase).toBe('remote');
    await tick();
    // The shell reports the exit while the scrim is up: the scrim keeps its panel.
    shell.send('argos://server-state', { phase: 'stopped', status: 'exit status 0' });
    expect(desktop.crash).toBeNull();
    desktop.quit.onLink(false);
    expect(desktop.quit.phase).toBe('stopped');
    expect(desktop.crash).toBeNull();
    stop();
  });

  it('?chrome=native keeps the OS title bar', () => {
    const { desktop } = make('?api=http://127.0.0.1:8781&token=t&chrome=native');
    expect(desktop.titleBar).toBe(false);
  });

  it('reveal: the server route, else the shell', async () => {
    const shell = fakeShell();
    const answers = [() => Promise.resolve({}), () => Promise.reject(new ApiError(404, 'not_found', 'Not Found')), () => Promise.reject(new Error('Not Found'))];
    const desktop = new DesktopShell({
      client: { request: () => answers.shift()?.() } as never,
      config: resolveConfig('?api=http://127.0.0.1:8781&token=t'),
      activity: () => ({}),
      search: '?api=http://127.0.0.1:8781&token=t',
      host: shell.host,
    });
    await desktop.reveal('/Users/o/a.zip');
    expect(shell.emitted()).toEqual([]);
    // A server without A12: the shell's opener.
    await desktop.reveal('/Users/o/b.zip');
    expect(shell.calls.at(-1)).toEqual({ cmd: 'plugin:event|emit', args: { event: 'argos://reveal', payload: { path: '/Users/o/b.zip' } } });
    // Anything else reaches the caller in its words.
    await expect(desktop.reveal('/Users/o/c.zip')).rejects.toThrow('Not Found');
    const browser = new DesktopShell({ client: {} as never, config: resolveConfig(''), activity: () => ({}), search: '', host: {} });
    await expect(browser.reveal('/x')).rejects.toThrow('desktop app only');
  });
});
