/**
 * The desktop shell's bridge (W8): Tauri v2 IPC with no `@tauri-apps/api` package (owner
 * decision: no new npm runtime dependency). A browser tab has no bridge; every call is then
 * a no-op and `available` is false.
 *
 * Detection: Tauri v2 injects `window.__TAURI_INTERNALS__` (`invoke`, `transformCallback`,
 * `metadata`) into every page of its webviews, whatever `withGlobalTauri` says; a browser
 * never has it. That object is the test (`isDesktopShell`; `isDesktopApp` in
 * app/shortcuts.ts is the same test). No query flag is needed: a `?desktop=1` typed into a
 * browser could not reach the shell anyway. The UI opened by the shell before its server
 * is ready has no `?api=` (desktop.svelte.ts: "waiting" start-up).
 *
 * Contract with web/src-tauri (the core event plugin: `plugin:event|listen`, `|unlisten`,
 * `|emit`, all in `core:event:default`, part of `core:default`; payloads are JSON):
 *
 * shell -> UI
 *   argos://server-state     {phase: "starting"|"ready"|"failed"|"stopped", api?, token?,
 *                             title?, cause?, details?, log_dir?, status?, version?}
 *                            on every change, and in answer to argos://ui-ready.
 *                            "ready" carries api ("http://127.0.0.1:<port>") and token;
 *                            "failed" (start-up) and "stopped" (the server ended without
 *                            being asked) carry the cause, the last stderr lines
 *                            (details), the log folder and the exit status.
 *   argos://quit-requested   Cmd+Q, the app menu's Quit, the Dock's Quit, a close request:
 *                            the shell prevents the exit and lets the UI run the quit flow
 *                            (A7, the Quit dialog when something runs).
 *   argos://menu             {id}: an item of the native app menu (Q-G10); `id` is a
 *                            command id of MENU_COMMANDS.
 *   argos://download         {status: "saved"|"failed", path?, name?}: a download of the
 *                            UI (`<a download>`: log, plot, view, export, support bundle)
 *                            ended; the shell saves it in the Downloads folder under a
 *                            free name (a webview has no download bar).
 *   argos://window           {fullscreen, double_click: "zoom"|"minimize"|"none"}: the
 *                            window's full-screen state (on every change and in answer
 *                            to argos://ui-ready: the title bar hides in full screen) and
 *                            the system's "double-click a window's title bar" setting.
 * UI -> shell
 *   argos://ui-ready         the UI listens now: answer with argos://server-state.
 *   argos://quit             {now?}: exit: the server shut down through A7, or is gone, or
 *                            the observer chose "Quit now" (now: true, the shell stops a
 *                            live sidecar at once instead of waiting its shutdown bound).
 *   argos://restart-server   start the sidecar again (start-up failure, crash notice); the
 *                            shell answers with argos://server-state "starting", then
 *                            "ready" (the UI reloads itself on the new address) or "failed".
 *   argos://reset-window-state  "Reset all layouts": default size, centred, the saved
 *                            window state forgotten (tauri-plugin-window-state).
 *   argos://open-log-folder  the server's log folder in the file manager (works with no
 *                            server, unlike A12).
 *   argos://reveal           {path}: A12's fallback when the server has no reveal route.
 *   argos://toggle-fullscreen  enter or leave full screen (the palette, the Help menu).
 *   argos://theme            {theme, bg}: the UI's theme and its --bg (#rrggbb), on start
 *                            and on every change: the shell paints the window behind the
 *                            page with it and themes its own pages (Night Red, BRAND 4.3).
 *
 * Window commands of the custom title bar (decorations off, Q-G14), through the core window
 * plugin; the capability must allow them: `core:window:allow-start-dragging`,
 * `core:window:allow-minimize`, `core:window:allow-toggle-maximize`.
 */

/** What `__TAURI_INTERNALS__` offers (the subset used here). */
export interface TauriInternals {
  invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
  transformCallback: (callback: (response: unknown) => void, once?: boolean) => number;
  metadata?: { currentWindow?: { label?: string }; currentWebview?: { label?: string } };
}

export const SHELL_EVENTS = {
  serverState: 'argos://server-state',
  quitRequested: 'argos://quit-requested',
  menu: 'argos://menu',
  uiReady: 'argos://ui-ready',
  quit: 'argos://quit',
  restartServer: 'argos://restart-server',
  resetWindowState: 'argos://reset-window-state',
  openLogFolder: 'argos://open-log-folder',
  reveal: 'argos://reveal',
  download: 'argos://download',
  window: 'argos://window',
  toggleFullscreen: 'argos://toggle-fullscreen',
  theme: 'argos://theme',
} as const;

/**
 * Native app menu items (Q-G10: App, File, View, Help, mirroring the in-window commands,
 * nothing more). The shell sends the id; the UI runs the command of the same id (the
 * keymap's ids where a key exists).
 */
export const MENU_COMMANDS = [
  'help.about',
  'nav.settings.mod',
  'app.quit',
  'file.open-fits',
  'review.sessions',
  'help.bundle',
  'nav.connection',
  'nav.observe',
  'nav.plan',
  'nav.review',
  'nav.settings',
  'log.toggle',
  'palette.open',
  'theme.cycle',
  'layout.reset-all',
  'help.shortcuts',
  'help.docs',
] as const;

export type MenuCommand = (typeof MENU_COMMANDS)[number];

export function isMenuCommand(id: unknown): id is MenuCommand {
  return typeof id === 'string' && (MENU_COMMANDS as readonly string[]).includes(id);
}

/** `__TAURI_INTERNALS__` when it is usable, else null. */
export function tauriInternals(host: object = globalThis): TauriInternals | null {
  const t = (host as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  if (!t || typeof t !== 'object') return null;
  const o = t as Partial<TauriInternals>;
  return typeof o.invoke === 'function' && typeof o.transformCallback === 'function' ? (o as TauriInternals) : null;
}

/** True inside the Tauri desktop shell. */
export function isDesktopShell(host: object = globalThis): boolean {
  return tauriInternals(host) !== null;
}

export type ShellPlatform = 'macos' | 'windows' | 'linux';

/** The platform, for the title bar's layout and the file manager's name. */
export function shellPlatform(nav: { platform?: string; userAgent?: string } | undefined = globalThis.navigator): ShellPlatform {
  const p = `${nav?.platform ?? ''} ${nav?.userAgent ?? ''}`;
  if (/mac|iphone|ipad/i.test(p)) return 'macos';
  if (/win(32|64|dows)/i.test(p)) return 'windows';
  return 'linux';
}

/** "Reveal in Finder" and its equivalents (A12's action label). */
export function revealLabel(platform: ShellPlatform): string {
  return platform === 'macos' ? 'Reveal in Finder' : platform === 'windows' ? 'Show in Explorer' : 'Show in folder';
}

/** The system's "double-click a window's title bar to" setting (macOS AppleActionOnDoubleClick). */
export type DoubleClickAction = 'zoom' | 'minimize' | 'none';

export function checkDoubleClick(v: unknown): DoubleClickAction {
  return v === 'minimize' || v === 'none' ? v : 'zoom';
}

/**
 * What a press on the title bar's free area does (Tauri's own drag script follows the same
 * rule): the main button drags, its second click does what the system setting says (zoom
 * by default; macOS hands the following events to the window drag, so a `dblclick` would
 * never arrive); presses on controls do nothing.
 */
export function titleBarPress(
  e: { button: number; detail: number; onControl: boolean },
  doubleClick: DoubleClickAction = 'zoom',
): 'drag' | 'zoom' | 'minimize' | null {
  if (e.button !== 0 || e.onControl) return null;
  if (e.detail < 2 || doubleClick === 'none') return 'drag';
  return doubleClick;
}

type Unlisten = () => void;

export class ShellBridge {
  private readonly t: TauriInternals | null;
  private readonly host: object;

  constructor(host: object = globalThis) {
    this.host = host;
    this.t = tauriInternals(host);
  }

  get available(): boolean {
    return this.t !== null;
  }

  /** This window's label ("main", D27: one window). */
  get label(): string {
    return this.t?.metadata?.currentWindow?.label ?? 'main';
  }

  private call(cmd: string, args: Record<string, unknown> = {}): Promise<unknown> {
    if (!this.t) return Promise.resolve(undefined);
    try {
      return this.t.invoke(cmd, args);
    } catch (err) {
      return Promise.reject(err);
    }
  }

  /** Send an event to the shell (and any listener); never throws. */
  async emit(event: string, payload?: unknown): Promise<boolean> {
    if (!this.t) return false;
    try {
      await this.call('plugin:event|emit', { event, payload });
      return true;
    } catch {
      return false;
    }
  }

  /** Listen to a shell event; the handler gets the payload. Resolves to the unlisten function. */
  async listen(event: string, handler: (payload: unknown) => void): Promise<Unlisten> {
    const t = this.t;
    if (!t) return () => {};
    const callback = t.transformCallback((message) => {
      handler(isObject(message) && 'payload' in message ? message.payload : undefined);
    });
    let eventId: unknown;
    try {
      eventId = await this.call('plugin:event|listen', { event, target: { kind: 'Any' }, handler: callback });
    } catch {
      return () => {};
    }
    return () => {
      const plugin = (this.host as { __TAURI_EVENT_PLUGIN_INTERNALS__?: { unregisterListener?: (e: string, id: unknown) => void } })
        .__TAURI_EVENT_PLUGIN_INTERNALS__;
      try {
        plugin?.unregisterListener?.(event, eventId);
      } catch {
        /* the page is going away */
      }
      void this.call('plugin:event|unlisten', { event, eventId }).catch(() => {});
    };
  }

  // -- Window (custom title bar) ----------------------------------------------------------

  startDragging(): Promise<unknown> {
    return this.call('plugin:window|start_dragging', { label: this.label }).catch(() => undefined);
  }

  minimize(): Promise<unknown> {
    return this.call('plugin:window|minimize', { label: this.label }).catch(() => undefined);
  }

  /** The zoom button and a double click on the title bar. */
  toggleMaximize(): Promise<unknown> {
    return this.call('plugin:window|toggle_maximize', { label: this.label }).catch(() => undefined);
  }

  // -- App ------------------------------------------------------------------------------------

  uiReady(): Promise<boolean> {
    return this.emit(SHELL_EVENTS.uiReady);
  }

  quit(now = false): Promise<boolean> {
    return this.emit(SHELL_EVENTS.quit, now ? { now: true } : undefined);
  }

  restartServer(): Promise<boolean> {
    return this.emit(SHELL_EVENTS.restartServer);
  }

  resetWindowState(): Promise<boolean> {
    return this.emit(SHELL_EVENTS.resetWindowState);
  }

  openLogFolder(): Promise<boolean> {
    return this.emit(SHELL_EVENTS.openLogFolder);
  }

  reveal(path: string): Promise<boolean> {
    return this.emit(SHELL_EVENTS.reveal, { path });
  }

  toggleFullscreen(): Promise<boolean> {
    return this.emit(SHELL_EVENTS.toggleFullscreen);
  }

  theme(theme: string, bg: string): Promise<boolean> {
    return this.emit(SHELL_EVENTS.theme, { theme, bg });
  }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}
