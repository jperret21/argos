import { describe, expect, it } from 'vitest';
import { checkDoubleClick, isDesktopShell, isMenuCommand, revealLabel, ShellBridge, SHELL_EVENTS, shellPlatform, tauriInternals, titleBarPress } from './bridge';

interface Call {
  cmd: string;
  args?: Record<string, unknown>;
}

/** A fake `__TAURI_INTERNALS__`: records invokes, keeps the callbacks by id. */
function fakeHost(opts: { failInvoke?: boolean } = {}) {
  const calls: Call[] = [];
  const callbacks = new Map<number, (r: unknown) => void>();
  const unregistered: [string, unknown][] = [];
  let nextId = 1;
  let nextEvent = 100;
  const host = {
    __TAURI_INTERNALS__: {
      metadata: { currentWindow: { label: 'main' } },
      transformCallback(cb: (r: unknown) => void) {
        const id = nextId++;
        callbacks.set(id, cb);
        return id;
      },
      invoke(cmd: string, args?: Record<string, unknown>) {
        calls.push({ cmd, args });
        if (opts.failInvoke) return Promise.reject(new Error('not allowed'));
        if (cmd === 'plugin:event|listen') return Promise.resolve(nextEvent++);
        return Promise.resolve(null);
      },
    },
    __TAURI_EVENT_PLUGIN_INTERNALS__: {
      unregisterListener(event: string, id: unknown) {
        unregistered.push([event, id]);
      },
    },
  };
  return { host, calls, callbacks, unregistered };
}

describe('detection', () => {
  it('needs __TAURI_INTERNALS__ with invoke and transformCallback', () => {
    expect(isDesktopShell({})).toBe(false);
    expect(isDesktopShell({ __TAURI_INTERNALS__: {} })).toBe(false);
    expect(isDesktopShell({ __TAURI_INTERNALS__: { invoke: () => 0 } })).toBe(false);
    expect(isDesktopShell(fakeHost().host)).toBe(true);
    expect(tauriInternals({ __TAURI_INTERNALS__: null })).toBeNull();
    expect(isDesktopShell()).toBe(false); // vitest runs in node: no shell
  });

  it('names the platform and its file manager', () => {
    expect(shellPlatform({ platform: 'MacIntel', userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15' })).toBe('macos');
    expect(shellPlatform({ platform: 'Win32', userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' })).toBe('windows');
    expect(shellPlatform({ platform: 'Linux x86_64', userAgent: 'Mozilla/5.0 (X11; Linux x86_64)' })).toBe('linux');
    expect(shellPlatform({})).toBe('linux');
    expect(['macos', 'windows', 'linux'].map((p) => revealLabel(p as 'macos'))).toEqual(['Reveal in Finder', 'Show in Explorer', 'Show in folder']);
  });

  it('knows the app menu commands', () => {
    expect(isMenuCommand('app.quit')).toBe(true);
    expect(isMenuCommand('nav.observe')).toBe(true);
    expect(isMenuCommand('rm -rf')).toBe(false);
    expect(isMenuCommand(3)).toBe(false);
  });
});

describe('ShellBridge', () => {
  it('is a no-op in a browser', async () => {
    const b = new ShellBridge({});
    expect(b.available).toBe(false);
    expect(await b.emit('x')).toBe(false);
    const off = await b.listen('x', () => {});
    off();
    await b.minimize();
  });

  it('emits through the core event plugin', async () => {
    const { host, calls } = fakeHost();
    const b = new ShellBridge(host);
    expect(await b.quit()).toBe(true);
    await b.reveal('/tmp/a.zip');
    await b.resetWindowState();
    expect(calls).toEqual([
      { cmd: 'plugin:event|emit', args: { event: SHELL_EVENTS.quit, payload: undefined } },
      { cmd: 'plugin:event|emit', args: { event: 'argos://reveal', payload: { path: '/tmp/a.zip' } } },
      { cmd: 'plugin:event|emit', args: { event: 'argos://reset-window-state', payload: undefined } },
    ]);
  });

  it('listens with a transformed callback, hands the payload over, unlistens', async () => {
    const { host, calls, callbacks, unregistered } = fakeHost();
    const b = new ShellBridge(host);
    const seen: unknown[] = [];
    const off = await b.listen(SHELL_EVENTS.serverState, (p) => seen.push(p));
    const listen = calls[0];
    expect(listen.cmd).toBe('plugin:event|listen');
    expect(listen.args).toMatchObject({ event: 'argos://server-state', target: { kind: 'Any' } });
    const handler = listen.args?.handler as number;
    callbacks.get(handler)?.({ event: 'argos://server-state', id: 100, payload: { phase: 'ready' } });
    expect(seen).toEqual([{ phase: 'ready' }]);
    off();
    expect(unregistered).toEqual([['argos://server-state', 100]]);
    expect(calls[1]).toEqual({ cmd: 'plugin:event|unlisten', args: { event: 'argos://server-state', eventId: 100 } });
  });

  it('drives the window through the core window plugin', async () => {
    const { host, calls } = fakeHost();
    const b = new ShellBridge(host);
    await b.startDragging();
    await b.minimize();
    await b.toggleMaximize();
    expect(calls.map((c) => [c.cmd, c.args?.label])).toEqual([
      ['plugin:window|start_dragging', 'main'],
      ['plugin:window|minimize', 'main'],
      ['plugin:window|toggle_maximize', 'main'],
    ]);
  });

  it('never throws when the shell refuses (a missing permission)', async () => {
    const { host } = fakeHost({ failInvoke: true });
    const b = new ShellBridge(host);
    expect(await b.quit()).toBe(false);
    await expect(b.minimize()).resolves.toBeUndefined();
    const off = await b.listen('x', () => {});
    expect(() => off()).not.toThrow();
  });
});

describe('title bar presses', () => {
  it('drags on the main button, zooms on its second click, ignores controls', () => {
    expect(titleBarPress({ button: 0, detail: 1, onControl: false })).toBe('drag');
    expect(titleBarPress({ button: 0, detail: 2, onControl: false })).toBe('zoom');
    expect(titleBarPress({ button: 0, detail: 1, onControl: true })).toBeNull();
    expect(titleBarPress({ button: 2, detail: 1, onControl: false })).toBeNull();
    // The system's double-click setting (AppleActionOnDoubleClick).
    expect(titleBarPress({ button: 0, detail: 2, onControl: false }, 'minimize')).toBe('minimize');
    expect(titleBarPress({ button: 0, detail: 2, onControl: false }, 'none')).toBe('drag');
    expect(titleBarPress({ button: 0, detail: 1, onControl: false }, 'minimize')).toBe('drag');
    expect(checkDoubleClick('minimize')).toBe('minimize');
    expect(checkDoubleClick('none')).toBe('none');
    expect(checkDoubleClick(undefined)).toBe('zoom');
    expect(checkDoubleClick('Fill')).toBe('zoom');
  });
});
