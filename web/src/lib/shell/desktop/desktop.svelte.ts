/**
 * The desktop app's side of the UI (W8; web/spec/01-shell-and-global.md 2.3.7, 2.3.8,
 * 2.4.1, 2.4.6; README rows A7, A12, M18): one object the app state holds
 * (`ArgosApp.desktop`), inert in a browser tab (`available` false: no title bar, no Quit,
 * no Reveal; a remote shutdown still shows its scrim).
 *
 * - Start-up (01 2.3.8): the shell may open the UI before its server is ready, with no
 *   `?api=` in the URL ("waiting"): the start-up screen then shows "Starting the ARGOS
 *   server…" in the observer's theme (the shell's own page shows only until the UI has
 *   loaded), and the shell's `argos://server-state` drives it: "ready" points the UI at
 *   the server's address and token in place (`adopt`: no reload, about 0.3 s sooner; the
 *   address goes into the URL for a later reload), else reloads the UI there; "failed" is
 *   the start-up failure (cause, last stderr lines, log folder; Open log folder and Retry
 *   go to the shell).
 * - Crash notice: once the UI runs, a server that ends without being asked ("stopped")
 *   is shown in the UI, in its theme (CrashNotice), instead of the shell's failure page;
 *   Restart asks the shell, which reloads the UI on the new server.
 * - Quit (QuitFlow): A7, the Quit dialog, the shutdown scrim, then `argos://quit`.
 * - Reveal (A12): the server's route, else the shell's opener (`argos://reveal`).
 * - Reset all layouts also forgets the window state (`argos://reset-window-state`).
 * - The native app menu's items arrive as command ids (`onmenu`).
 * - Full screen (`argos://window`): the title bar hides (its controls do nothing in a
 *   full-screen space); Enter / Exit full screen asks the shell. The system's title-bar
 *   double-click setting comes the same way.
 * - The theme (`argos://theme`): the shell paints the window behind the page with the
 *   theme's --bg (a resize sliver, a reload) and themes its own pages.
 */

import { untrack } from 'svelte';
import { requestShutdown, revealPath, checkShutdownEvent } from '../../api/desktop';
import type { ArgosClient } from '../../api/client';
import type { LinkState } from '../../api/socket';
import { isLoopbackBase, normalizeApiBase, type ArgosConfig } from '../../config';
import type { StartupFailure } from '../../app/startup';
import {
  checkDoubleClick,
  type DoubleClickAction,
  isMenuCommand,
  type MenuCommand,
  ShellBridge,
  SHELL_EVENTS,
  type ShellPlatform,
  shellPlatform,
  revealLabel,
} from './bridge';
import { QuitFlow } from './quit.svelte';
import type { LocalActivity } from './words';

export type ServerPhase = 'starting' | 'ready' | 'failed' | 'stopped';

/** The shell's `argos://server-state` payload. */
export interface ServerState {
  phase: ServerPhase;
  api: string | null;
  token: string | null;
  title: string | null;
  cause: string | null;
  /** The server's last stderr lines (traceback). */
  details: string | null;
  logDir: string | null;
  /** Exit status, as the shell words it ("exit status 1", "signal 9"). */
  status: string | null;
  version: string | null;
}

function s(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null;
}

export function checkServerState(p: unknown): ServerState | null {
  if (typeof p !== 'object' || p === null) return null;
  const o = p as Record<string, unknown>;
  const phase = o.phase;
  if (phase !== 'starting' && phase !== 'ready' && phase !== 'failed' && phase !== 'stopped') return null;
  return {
    phase,
    api: s(o.api),
    token: s(o.token),
    title: s(o.title),
    cause: s(o.cause),
    details: s(o.details),
    logDir: s(o.log_dir) ?? s(o.logDir),
    status: s(o.status),
    version: s(o.version),
  };
}

/** The shell's `argos://download`: a download of the UI ended (Downloads folder). */
export interface DownloadDone {
  saved: boolean;
  path: string | null;
  name: string | null;
}

export function checkDownload(p: unknown): DownloadDone | null {
  if (typeof p !== 'object' || p === null) return null;
  const o = p as Record<string, unknown>;
  if (o.status !== 'saved' && o.status !== 'failed') return null;
  return { saved: o.status === 'saved', path: s(o.path), name: s(o.name) };
}

/** The crash notice (01 2.4.1): the server ended while the UI ran. */
export interface CrashView {
  kind: 'crash' | 'requested' | 'restarting' | 'failed';
  title: string;
  message: string;
  detail: string | null;
  logPath: string | null;
}

export function crashView(server: ServerState | null, sawShutdown: boolean): CrashView | null {
  if (!server || server.phase === 'ready') return null;
  const base = { detail: server.details, logPath: server.logDir };
  if (server.phase === 'starting') {
    return { kind: 'restarting', title: 'Restarting the ARGOS server…', message: 'The window reloads once it answers.', detail: null, logPath: server.logDir };
  }
  if (server.phase === 'failed') {
    return {
      kind: 'failed',
      title: server.title ?? 'ARGOS could not start',
      message: server.cause ?? 'The ARGOS server did not start.',
      ...base,
    };
  }
  if (sawShutdown) {
    // A deliberate stop (another window or tab asked): the scrim's words, no error mark,
    // no log (the exit is a clean one).
    return { kind: 'requested', title: REQUESTED_TITLE, message: requestedText(true), detail: null, logPath: null };
  }
  return {
    kind: 'crash',
    title: 'The ARGOS server stopped unexpectedly',
    message: `It ended${server.status ? ` (${server.status})` : ''}. Restart server starts it again; a sequence that was running stopped with it, and the frames already saved are on disk.`,
    ...base,
  };
}

/** A shutdown asked by another client (scrim and crash notice say it the same way). */
export const REQUESTED_TITLE = 'The ARGOS server was shut down';

export function requestedText(desktop: boolean): string {
  return `Another ARGOS window or browser tab asked it to stop. ${desktop ? 'Restart server starts it again.' : 'This page reconnects when the server runs again.'}`;
}

/** The UI's URL on a new server (other query parameters kept). Null when unusable. */
export function readyUrl(href: string, api: string | null, token: string | null): string | null {
  const base = normalizeApiBase(api);
  if (!base || !isLoopbackBase(base) || !token) return null;
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return null;
  }
  url.searchParams.set('api', base);
  url.searchParams.set('token', token);
  return url.toString();
}

export interface DesktopDeps {
  client: Pick<ArgosClient, 'request'>;
  config: Pick<ArgosConfig, 'apiBase' | 'token' | 'source'>;
  /** What the UI sees running (the Quit dialog). */
  activity: () => LocalActivity;
  /** A native app menu item. */
  onmenu?: (id: MenuCommand) => void;
  /** A download ended (saved in the Downloads folder, or failed). */
  ondownload?: (done: DownloadDone) => void;
  /** The page's query string (default: location.search). */
  search?: string;
  /** Reload the UI on another URL (default: location.replace). */
  navigate?: (url: string) => void;
  /**
   * A waiting UI's server is ready: run on it in place (the app sets its address and token
   * and starts). Without it, the UI reloads on the server's URL.
   */
  adopt?: (api: string, token: string) => void;
  /** The global object (tests). */
  host?: object;
}

export class DesktopShell {
  readonly bridge: ShellBridge;
  /** Inside the Tauri shell. */
  readonly available: boolean;
  readonly platform: ShellPlatform;
  /** Opened before the server was ready: wait for argos://server-state (false once adopted). */
  waiting = $state(false);
  /** Draw the custom title bar (decorations off, Q-G14). `?chrome=native` turns it off. */
  readonly titleBar: boolean;
  readonly quit: QuitFlow;
  /** The shell's last server state. */
  server: ServerState | null = $state.raw(null);
  /** The window has the focus (the title bar dims otherwise). */
  focused = $state(true);
  /** The window is in full screen (the title bar hides). */
  fullscreen = $state(false);
  /** The system's title-bar double-click setting. */
  doubleClick: DoubleClickAction = $state('zoom');
  private readonly deps: DesktopDeps;
  private reloading = false;

  constructor(deps: DesktopDeps) {
    this.deps = deps;
    const host = deps.host ?? globalThis;
    this.bridge = new ShellBridge(host);
    this.available = this.bridge.available;
    this.platform = shellPlatform((host as { navigator?: Navigator }).navigator);
    const params = new URLSearchParams(deps.search ?? (typeof location === 'undefined' ? '' : location.search));
    this.waiting = this.available && !params.get('api');
    this.titleBar = this.available && params.get('chrome') !== 'native';
    this.quit = new QuitFlow({
      desktop: this.available,
      // Waiting (no ?api= yet): the client still points at the default address, maybe
      // another server; nothing of ours answers there, so quit asks the shell only.
      shutdown: (force) =>
        this.waiting ? Promise.resolve({ outcome: 'unreachable', message: 'The ARGOS server is still starting.' }) : requestShutdown(deps.client, force),
      exit: (now) => void this.bridge.quit(now),
      activity: deps.activity,
    });
  }

  /** The custom title bar is drawn now (not in full screen). */
  get showTitleBar(): boolean {
    return this.titleBar && !this.fullscreen;
  }

  /** "Reveal in Finder" (macOS), "Show in Explorer", "Show in folder". */
  get revealLabel(): string {
    return revealLabel(this.platform);
  }

  /** The sidecar stage of the start-up screen (startupView's `sidecar`). */
  get sidecar(): 'starting' | 'ready' | 'failed' {
    if (!this.waiting) return 'ready';
    if (this.server?.phase === 'failed' || this.server?.phase === 'stopped') return 'failed';
    return this.server?.phase === 'ready' ? 'ready' : 'starting';
  }

  /** The shell's start-up failure (waiting mode), for the start-up screen. */
  get startupFailure(): StartupFailure | null {
    if (!this.waiting || !this.server || (this.server.phase !== 'failed' && this.server.phase !== 'stopped')) return null;
    return {
      title: this.server.title ?? 'ARGOS could not start',
      message: this.server.cause ?? 'The ARGOS server stopped during start-up.',
      detail: this.server.details,
      logPath: this.server.logDir,
    };
  }

  /**
   * The crash notice, once the UI runs on a server (not while quitting). A shutdown asked
   * by another client keeps the scrim's own "shut down" panel when the shell then reports
   * the exit: one notice per event.
   */
  get crash(): CrashView | null {
    if (!this.available || this.waiting) return null;
    if (this.quit.phase === 'stopping' || this.quit.phase === 'closing') return null;
    const view = crashView(this.server, this.quit.sawShutdown);
    if (view?.kind === 'requested' && this.quit.scrim) return null;
    return view;
  }

  /** The version the shell reports (start-up screen before the server answers). */
  get version(): string | null {
    return this.server?.version ?? null;
  }

  /**
   * Listen to the shell and to the server's shutdown stages; returns the teardown.
   * `events`: the app's ArgosEvents (raw `on` and the link state).
   */
  start(events: { on(type: string, fn: (msg: Record<string, unknown>) => void): () => void; readonly link: LinkState }): () => void {
    const offs: (() => void)[] = [];
    offs.push(
      events.on('shutdown', (m) => {
        const ev = checkShutdownEvent(m);
        if (ev) this.quit.onShutdownEvent(ev);
      }),
    );
    const stopLink = $effect.root(() => {
      $effect(() => {
        const open = events.link === 'open';
        untrack(() => this.quit.onLink(open));
      });
    });
    offs.push(stopLink);

    if (this.available) {
      const win = typeof window === 'undefined' ? null : window;
      if (win) {
        const onFocus = () => (this.focused = true);
        const onBlur = () => (this.focused = false);
        win.addEventListener('focus', onFocus);
        win.addEventListener('blur', onBlur);
        offs.push(() => {
          win.removeEventListener('focus', onFocus);
          win.removeEventListener('blur', onBlur);
        });
      }
      let alive = true;
      const listening = Promise.all([
        this.bridge.listen(SHELL_EVENTS.serverState, (p) => this.onServerState(p)),
        this.bridge.listen(SHELL_EVENTS.quitRequested, () => void this.quit.request()),
        this.bridge.listen(SHELL_EVENTS.menu, (p) => {
          const id = (p as { id?: unknown } | null)?.id;
          if (isMenuCommand(id)) this.deps.onmenu?.(id);
        }),
        this.bridge.listen(SHELL_EVENTS.download, (p) => {
          const done = checkDownload(p);
          if (done) this.deps.ondownload?.(done);
        }),
        this.bridge.listen(SHELL_EVENTS.window, (p) => this.onWindow(p)),
      ]).then((unlisten) => {
        if (!alive) unlisten.forEach((u) => u());
        else void this.bridge.uiReady();
        return unlisten;
      });
      offs.push(() => {
        alive = false;
        void listening.then((unlisten) => unlisten.forEach((u) => u()));
      });
    }
    return () => {
      for (const off of offs) off();
      this.quit.dispose();
    };
  }

  /** argos://window: full screen and the double-click setting. */
  onWindow(payload: unknown): void {
    if (typeof payload !== 'object' || payload === null) return;
    const o = payload as Record<string, unknown>;
    if (typeof o.fullscreen === 'boolean') this.fullscreen = o.fullscreen;
    if ('double_click' in o) this.doubleClick = checkDoubleClick(o.double_click);
  }

  /** Enter or leave full screen (⌃⌘F; the palette, the Help menu). */
  toggleFullscreen(): void {
    void this.bridge.toggleFullscreen();
  }

  /** Tell the shell the theme and its --bg (start, every change). */
  themeChanged(theme: string): void {
    if (!this.available || typeof document === 'undefined') return;
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
    if (/^#[0-9a-f]{6}$/i.test(bg)) void this.bridge.theme(theme, bg);
  }

  /** argos://server-state. */
  onServerState(payload: unknown): void {
    const state = checkServerState(payload);
    if (!state) return;
    this.server = state;
    if (state.phase !== 'ready' || this.reloading) return;
    // Ready on another address or token (first start of a waiting UI, or a restart):
    // reload the UI there. The same server (the answer to ui-ready) changes nothing.
    const sameServer = normalizeApiBase(state.api) === this.deps.config.apiBase && state.token === this.deps.config.token;
    if (sameServer && !this.waiting) return;
    // The first start of a waiting UI: nothing ran yet, so it starts in place.
    const base = normalizeApiBase(state.api);
    if (this.waiting && this.deps.adopt && base && isLoopbackBase(base) && state.token) {
      this.waiting = false;
      this.deps.adopt(base, state.token);
      return;
    }
    const href = typeof location === 'undefined' ? 'http://localhost/' : location.href;
    const url = readyUrl(href, state.api, state.token);
    if (!url) return;
    this.reloading = true;
    (this.deps.navigate ?? ((u: string) => location.replace(u)))(url);
  }

  /** Retry (start-up failure) and Restart (crash notice). */
  restartServer(): void {
    this.server = this.server ? { ...this.server, phase: 'starting', cause: null, details: null } : null;
    void this.bridge.restartServer();
  }

  openLogFolder(): void {
    void this.bridge.openLogFolder();
  }

  /** "Reset all layouts" also restores the window's default size and place. */
  resetWindowState(): void {
    void this.bridge.resetWindowState();
  }

  /**
   * A12: show `path` in the file manager. Rejects with the server's words (not found,
   * outside the allowed folders); a server without the route falls back to the shell.
   */
  async reveal(path: string): Promise<void> {
    if (!this.available) throw new Error('Reveal works in the desktop app only.');
    const answer = await revealPath(this.deps.client, path);
    if (answer === 'unsupported' && !(await this.bridge.reveal(path))) {
      throw new Error('The desktop app could not open the file manager.');
    }
  }
}
