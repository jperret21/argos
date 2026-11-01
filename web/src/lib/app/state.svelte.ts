/**
 * Application state of the ARGOS web UI, shared through Svelte context.
 *
 * One instance per page (App.svelte creates it, components call useApp()).
 * It owns the server link (REST client, /ws/events, /ws/frames), the
 * observer's settings (exposure, gain, connection form), the display state
 * (stretch, crosshair, theme) and the user-facing feedback (toasts, log).
 *
 * Every hardware action goes through run(): it marks the action busy, applies
 * the REST answer immediately (the WebSocket echo follows), and turns any
 * failure into a toast plus a log line, so no error is silent and none is
 * modal.
 *
 * Exposure and gain: the fields follow the server's camera record whenever
 * it changes (first status, a live update taking effect, another client), so
 * the number on screen is the one in use. While live, a committed change is
 * sent at once (PATCH /api/camera/live) and applies from the next frame;
 * until the server's record matches, the change is "pending" and shown so.
 */

import { getContext, setContext, untrack } from 'svelte';
import { ApiError, ArgosClient } from '../api/client';
import { ArgosEvents } from '../api/events.svelte';
import { type DecodedFrame, FrameStream } from '../api/frames';
import type { LinkState } from '../api/socket';
import type { CameraState, ConnectionState, MountState } from '../api/types';
import { type ArgosConfig, loadConfig } from '../config';
import { isRotationMode, type RotationMode } from '../viewer/rotation';
import type { StretchMode, StretchParams } from '../viewer/stretch';
import type { DisplayInfo, PointerInfo } from '../viewer/types';
import { type FitMode, isFitMode } from '../viewer/view';
import { type FrameMetrics, FrameRateMeter } from './metrics';
import { isBoolean, loadPref, savePref } from './prefs';
import { loadTheme, nextTheme, parseCssColor, saveTheme, type Theme } from './theme';

export type Section = 'connection' | 'imaging' | 'sequencer' | 'analyze' | 'configuration';

export type ActionKey =
  | 'connection'
  | 'capture'
  | 'live'
  | 'liveSettings'
  | 'cameraStop'
  | 'goto'
  | 'mountStop'
  | 'park'
  | 'unpark'
  | 'tracking';

export type ToastLevel = 'info' | 'warning' | 'error';

export interface Toast {
  id: number;
  level: ToastLevel;
  title: string;
  message: string;
  /** Identical toasts are merged; this counts the repeats. */
  count: number;
}

/** Observer-facing titles for the server's error codes (protocol.md). */
const ERROR_TITLES: Record<string, string> = {
  not_connected: 'No equipment connected',
  not_live: 'Live view is not running',
  busy: 'Device busy',
  parked: 'Mount is parked',
  invalid_argument: 'Value refused',
  invalid_fits: 'Not a FITS image',
  not_found: 'Not found',
  unauthorized: 'Token rejected',
  connection_failed: 'Connection failed',
  device_error: 'Device error',
  network_error: 'Server unreachable',
  timeout: 'No answer from the server',
  bad_response: 'Unexpected server answer',
  internal_error: 'Server error',
  forbidden_origin: 'Refused by the server',
  forbidden_host: 'Refused by the server',
};

const TOAST_MS: Record<ToastLevel, number> = { info: 4000, warning: 6000, error: 8000 };
const MAX_TOASTS = 3;

export const EXPOSURE_LIMITS = { min: 0.001, max: 3600 } as const;
export const GAIN_LIMITS = { min: 0, max: 1000 } as const;

export class ArgosApp {
  readonly config: ArgosConfig;
  readonly client: ArgosClient;
  readonly events: ArgosEvents;
  private readonly frames: FrameStream;
  private readonly meter = new FrameRateMeter();

  // -- Server link ------------------------------------------------------------
  framesLink: LinkState = $state('idle');
  serverVersion: string | null = $state(null);
  /** Last frame received from /ws/frames (the viewer may coalesce several). */
  frame: DecodedFrame | null = $state.raw(null);
  /** performance.now() of the last frame received, for the live progress bar. */
  lastFrameAt: number | null = $state(null);
  /** Wall clock (epoch ms), ticked once a second: frame age and staleness. */
  clock = $state(Date.now());

  // -- Navigation and actions -------------------------------------------------
  section: Section = $state('imaging');
  busy: Partial<Record<ActionKey, boolean>> = $state({});

  // -- Observer settings ------------------------------------------------------
  exposure = $state(2);
  gain = $state(80);
  /** The Camera card fields hold text that is not a valid value. */
  exposureInvalid = $state(false);
  gainInvalid = $state(false);
  connectMode: 'simulator' | 'alpaca' = $state('simulator');
  alpacaHost = $state('');
  alpacaPort = $state(32323);
  /** The port field holds text that is not a valid port (alpacaPort keeps the last valid one). */
  alpacaPortInvalid = $state(false);

  // -- Display ----------------------------------------------------------------
  theme: Theme = $state(loadTheme());
  viewerTint: [number, number, number] = $state.raw([1, 1, 1]);
  autoStretch = $state(true);
  /** Manual levels; used while autoStretch is off. */
  manual: StretchParams | null = $state.raw(null);
  crosshair = $state(false);
  /** Levels strip under the image (H); remembered per viewer. */
  stripOpen: boolean = $state(loadPref('argos.levels-strip', isBoolean, true));
  /** How "fit" frames the image: whole frame, or filling the viewer (cropped). */
  fitMode: FitMode = $state(loadPref('argos.fit-mode', isFitMode, 'fit'));
  /** The viewer currently shows the fitted view (not a zoom or pan of the observer's). */
  fitted = $state(true);
  /** Connection card unfolded; a reveal (toolbar chip) also focuses it. */
  connectionOpen = $state(true);
  connectionReveal = $state(false);
  /** Display rotation of the viewer (BRAND 11.1: auto turns portrait frames landscape). */
  rotation: RotationMode = $state(loadPref('argos.rotation', isRotationMode, 'auto'));
  /** Right rail of cards shown (P); remembered per viewer. */
  railOpen: boolean = $state(loadPref('argos.rail-open', isBoolean, true));
  /** Where the image sits in the viewer, CSS px (frame chips anchor to it). */
  imageRect: { left: number; top: number; width: number; height: number } | null = $state.raw(null);
  zoom = $state(1);
  pointer: PointerInfo | null = $state.raw(null);
  shown: DisplayInfo | null = $state.raw(null);
  metrics: FrameMetrics = $state.raw({ fps: null, latencyMs: null, frames: 0 });

  // -- Feedback -----------------------------------------------------------------
  toasts: Toast[] = $state([]);
  logOpen = $state(false);
  /** Log length when the drawer was last open: newer warnings/errors are "unseen". */
  logSeen = $state(0);
  private nextToastId = 1;
  private toastTimers = new Map<number, ReturnType<typeof setTimeout>>();

  constructor(config: ArgosConfig = loadConfig()) {
    this.config = config;
    this.client = new ArgosClient(config);
    this.events = new ArgosEvents(config);
    this.frames = new FrameStream(config, {
      onFrame: (f) => {
        this.frame = f;
        this.lastFrameAt = performance.now();
      },
      onState: (s) => (this.framesLink = s),
      onError: (err) => this.events.pushLog('warning', `Frame dropped: ${err.message}`),
    });
  }

  // -- Derived views of the server state --------------------------------------

  get connection(): ConnectionState | null {
    return this.events.connection;
  }

  get camera(): CameraState | null {
    return this.events.camera;
  }

  get mount(): MountState | null {
    return this.events.mount;
  }

  get linkOpen(): boolean {
    return this.events.link === 'open';
  }

  get connected(): boolean {
    return this.events.connection?.state === 'connected';
  }

  /**
   * The server link is down: every record on screen is the last one received,
   * not the current state. Readouts grey out and hardware actions are refused.
   */
  get stale(): boolean {
    return this.events.link !== 'open';
  }

  /** Hardware commands can be sent (link up and equipment connected). */
  get canCommand(): boolean {
    return !this.stale && this.connected;
  }

  get live(): boolean {
    return this.events.camera?.state === 'live';
  }

  get cameraBusy(): boolean {
    const s = this.events.camera?.state;
    return s === 'exposing' || s === 'downloading' || s === 'live';
  }

  get slewing(): boolean {
    return this.connected && this.events.mount?.state === 'slewing';
  }

  /**
   * The frame on screen is not a current camera frame: equipment
   * disconnected, server link down, or no new frame for max(5 s, three
   * exposures). Files are files, never "stale".
   */
  get frameStale(): boolean {
    const h = this.shown?.frame.header;
    if (!h || h.source === 'file') return false;
    if (!this.canCommand) return true;
    const t = Date.parse(h.timestamp);
    if (!Number.isFinite(t)) return false;
    const exposure = Math.max(h.exposure_s, this.cameraBusy ? (this.camera?.exposure_s ?? 0) : 0);
    return this.clock - t > Math.max(5000, 3000 * exposure);
  }

  /** Rate and latency, only while they describe a running stream. */
  get liveMetrics(): FrameMetrics {
    if (this.frameStale || !this.canCommand) return { ...this.metrics, fps: null, latencyMs: null };
    return this.metrics;
  }

  /**
   * Live view runs with other settings than the fields: the change applies
   * from the next frame (or was refused).
   */
  get livePending(): boolean {
    const cam = this.camera;
    if (!this.live || !cam) return false;
    return Math.abs(cam.exposure_s - this.exposure) > 1e-9 || cam.gain !== Math.round(this.gain);
  }

  /** Levels currently drawn (auto levels of the shown frame, or the manual ones). */
  get levels(): StretchParams | null {
    if (!this.autoStretch && this.manual) return this.manual;
    return this.shown?.auto ?? null;
  }

  /** Warnings and errors logged since the drawer was last opened. */
  get unseenProblems(): number {
    let n = 0;
    const logs = this.events.logs;
    for (let i = Math.max(0, this.logSeen); i < logs.length; i++) {
      if (logs[i].level !== 'info') n++;
    }
    return n;
  }

  // -- Lifecycle ------------------------------------------------------------------

  start(): () => void {
    this.applyTheme(this.theme);
    this.events.start();
    this.frames.start();
    this.client
      .health()
      .then((h) => (this.serverVersion = h.version))
      .catch(() => (this.serverVersion = null));
    const tick = setInterval(() => (this.clock = Date.now()), 1000);
    const stopEffects = $effect.root(() => {
      $effect(() => {
        const cam = this.events.camera;
        untrack(() => this.followCamera(cam));
      });
    });
    return () => {
      clearInterval(tick);
      stopEffects();
      this.events.stop();
      this.frames.stop();
      for (const t of this.toastTimers.values()) clearTimeout(t);
      this.toastTimers.clear();
    };
  }

  private seenSettings: string | null = null;

  /** Adopt the server's exposure and gain whenever they change there. */
  private followCamera(cam: CameraState | null): void {
    if (!cam) return;
    const key = `${cam.exposure_s}|${cam.gain}`;
    if (key === this.seenSettings) return;
    this.seenSettings = key;
    this.exposure = cam.exposure_s;
    this.gain = cam.gain;
    this.exposureInvalid = false;
    this.gainInvalid = false;
  }

  /** Retry both sockets now (e.g. after the server was restarted). */
  reconnect(): void {
    this.events.restart();
    this.frames.restart();
    this.client
      .health()
      .then((h) => (this.serverVersion = h.version))
      .catch(() => (this.serverVersion = null));
  }

  // -- Theme ------------------------------------------------------------------------

  setTheme(theme: Theme): void {
    this.theme = theme;
    saveTheme(theme);
    this.applyTheme(theme);
  }

  cycleTheme(): void {
    this.setTheme(nextTheme(this.theme));
  }

  private applyTheme(theme: Theme): void {
    const root = globalThis.document?.documentElement;
    if (!root) return;
    root.dataset.theme = theme;
    const token = getComputedStyle(root).getPropertyValue('--viewer-tint');
    this.viewerTint = parseCssColor(token) ?? [1, 1, 1];
  }

  // -- Display ------------------------------------------------------------------------

  onDisplay(info: DisplayInfo): void {
    this.shown = info;
    // The server replays its latest frame to every new socket: an old frame
    // shown again is not a measure of the live rate or latency.
    const h = info.frame.header;
    const age = Date.now() - Date.parse(h.timestamp);
    if (Number.isFinite(age) && age > Math.max(5000, 3000 * h.exposure_s)) return;
    this.metrics = this.meter.record(Date.now(), h.timestamp, h.seq);
  }

  setAutoStretch(on: boolean): void {
    if (on) {
      this.autoStretch = true;
      return;
    }
    // Freeze the levels on screen, then let the observer adjust them.
    this.manual = this.levels ? { ...this.levels } : this.manual;
    this.autoStretch = false;
  }

  /** Change one level; leaves auto-stretch, starting from the levels on screen. */
  setLevel(patch: Partial<Omit<StretchParams, 'mode'>> & { mode?: StretchMode }): void {
    const base = this.levels;
    if (!base) return;
    const next = { ...base, ...patch };
    if (next.white <= next.black) {
      if (patch.black !== undefined) next.black = next.white - 1;
      else next.white = next.black + 1;
    }
    this.manual = next;
    this.autoStretch = false;
  }

  /** "Reset stretch (linear)": full data range, neutral midtones. */
  resetStretch(): void {
    const h = this.shown?.histogram;
    this.manual = {
      black: h ? h.min : 0,
      white: h ? Math.max(h.max, h.min + 1) : 65535,
      midtones: 0.5,
      mode: 'linear',
    };
    this.autoStretch = false;
  }

  setRotation(mode: RotationMode): void {
    this.rotation = mode;
    savePref('argos.rotation', mode);
  }

  toggleRail(): void {
    this.railOpen = !this.railOpen;
    savePref('argos.rail-open', this.railOpen);
  }

  toggleStrip(): void {
    this.stripOpen = !this.stripOpen;
    savePref('argos.levels-strip', this.stripOpen);
  }

  setFitMode(mode: FitMode): void {
    this.fitMode = mode;
    savePref('argos.fit-mode', mode);
  }

  /** Unfold and focus the Connection card (toolbar connection chip). */
  revealConnection(): void {
    if (!this.railOpen) this.toggleRail();
    this.connectionOpen = true;
    this.connectionReveal = true;
  }

  // -- Feedback -------------------------------------------------------------------------

  toast(level: ToastLevel, title: string, message = ''): void {
    const same = this.toasts.find((t) => t.title === title && t.message === message);
    if (same) {
      same.count += 1;
      this.armToast(same.id, level);
      return;
    }
    const toast: Toast = { id: this.nextToastId++, level, title, message, count: 1 };
    this.toasts = [...this.toasts, toast].slice(-MAX_TOASTS);
    this.armToast(toast.id, level);
  }

  dismissToast(id: number): void {
    this.toasts = this.toasts.filter((t) => t.id !== id);
    const timer = this.toastTimers.get(id);
    if (timer) clearTimeout(timer);
    this.toastTimers.delete(id);
  }

  private armToast(id: number, level: ToastLevel): void {
    const old = this.toastTimers.get(id);
    if (old) clearTimeout(old);
    this.toastTimers.set(
      id,
      setTimeout(() => this.dismissToast(id), TOAST_MS[level]),
    );
  }

  setLogOpen(open: boolean): void {
    this.logOpen = open;
    this.logSeen = this.events.logs.length;
  }

  /**
   * Report an API failure: one toast, one log line. Device failures (5xx) are
   * already logged by the server on /ws/events, so they are not logged twice.
   */
  reportError(what: string, err: unknown): void {
    const api = err instanceof ApiError ? err : null;
    const title = api ? (ERROR_TITLES[api.code] ?? `${what} failed`) : `${what} failed`;
    const message = api ? api.message : err instanceof Error ? err.message : String(err);
    this.toast('error', title, message);
    if (!api || api.status < 500) this.events.pushLog('error', `${what}: ${message}`);
  }

  // -- Actions ------------------------------------------------------------------------------

  private async run<T>(key: ActionKey, what: string, fn: () => Promise<T>): Promise<T | undefined> {
    if (this.busy[key]) return undefined;
    this.busy[key] = true;
    try {
      return await fn();
    } catch (err) {
      this.reportError(what, err);
      return undefined;
    } finally {
      this.busy[key] = false;
    }
  }

  /** Why connect() cannot run with the Connection card's choices, or null. */
  connectProblem(): string | null {
    if (!this.linkOpen) return 'the ARGOS server is not reachable';
    if (this.connectMode === 'alpaca' && !this.alpacaHost.trim()) return 'enter the Seestar address';
    if (this.connectMode === 'alpaca' && this.alpacaPortInvalid) return 'fix the Alpaca port';
    return null;
  }

  connect(): Promise<unknown> {
    if (this.connectProblem()) return Promise.resolve(undefined);
    return this.run('connection', 'Connect', async () => {
      const body =
        this.connectMode === 'alpaca'
          ? ({ mode: 'alpaca', host: this.alpacaHost.trim(), port: Math.round(this.alpacaPort) } as const)
          : ({ mode: 'simulator' } as const);
      const connection = await this.client.connect(body);
      this.events.applyStatus({ connection });
    });
  }

  disconnect(): Promise<unknown> {
    return this.run('connection', 'Disconnect', async () => {
      const connection = await this.client.disconnect();
      this.events.applyStatus({ connection });
    });
  }

  private exposureRequest(): { exposure_s: number; gain: number } {
    return { exposure_s: this.exposure, gain: Math.round(this.gain) };
  }

  /** A committed Exposure field value (NumberField onchange). */
  setExposure(v: number): void {
    this.exposure = v;
    if (this.live) void this.applyLiveSettings();
  }

  setGain(v: number): void {
    this.gain = v;
    if (this.live) void this.applyLiveSettings();
  }

  private liveSettingsQueued = false;

  /** Send the fields to the running live view (they apply from its next frame). */
  async applyLiveSettings(): Promise<void> {
    if (this.exposureProblem()) return;
    if (this.busy.liveSettings) {
      this.liveSettingsQueued = true; // send the newest values once this one is answered
      return;
    }
    await this.run('liveSettings', 'Live settings', async () => {
      const camera = await this.client.updateLive(this.exposureRequest());
      this.events.applyStatus({ camera });
    });
    if (this.liveSettingsQueued) {
      this.liveSettingsQueued = false;
      if (this.live) await this.applyLiveSettings();
    }
  }

  /** Drop a pending change: back to the settings of the frame being taken. */
  revertLiveSettings(): void {
    const cam = this.camera;
    if (!cam) return;
    this.exposure = cam.exposure_s;
    this.gain = cam.gain;
    this.exposureInvalid = false;
    this.gainInvalid = false;
    if (this.live) void this.applyLiveSettings();
  }

  /** Why an exposure cannot start, or null. */
  exposureProblem(): string | null {
    if (this.exposureInvalid) return 'fix the exposure time';
    if (this.gainInvalid) return 'fix the gain';
    if (!Number.isFinite(this.exposure) || this.exposure < EXPOSURE_LIMITS.min || this.exposure > EXPOSURE_LIMITS.max) {
      return `Exposure must be between ${EXPOSURE_LIMITS.min} and ${EXPOSURE_LIMITS.max} s`;
    }
    if (!Number.isFinite(this.gain) || this.gain < GAIN_LIMITS.min || this.gain > GAIN_LIMITS.max) {
      return `Gain must be between ${GAIN_LIMITS.min} and ${GAIN_LIMITS.max}`;
    }
    return null;
  }

  capture(): Promise<unknown> {
    return this.run('capture', 'Capture', async () => {
      const camera = await this.client.capture(this.exposureRequest());
      this.events.applyStatus({ camera });
    });
  }

  startLive(): Promise<unknown> {
    return this.run('live', 'Live view', async () => {
      const camera = await this.client.startLive(this.exposureRequest());
      this.events.applyStatus({ camera });
    });
  }

  stopCamera(): Promise<unknown> {
    return this.run('cameraStop', 'Stop camera', async () => {
      const camera = await this.client.stopCamera();
      this.events.applyStatus({ camera });
    });
  }

  toggleLive(): Promise<unknown> {
    return this.live ? this.stopCamera() : this.startLive();
  }

  goto(raHours: number, decDeg: number): Promise<unknown> {
    return this.run('goto', 'Slew', async () => {
      const mount = await this.client.goto({ ra_hours: raHours, dec_deg: decDeg });
      this.events.applyStatus({ mount });
    });
  }

  stopMount(): Promise<unknown> {
    return this.run('mountStop', 'Stop slew', async () => {
      const mount = await this.client.stopMount();
      this.events.applyStatus({ mount });
    });
  }

  park(): Promise<unknown> {
    return this.run('park', 'Park', async () => {
      const mount = await this.client.park();
      this.events.applyStatus({ mount });
    });
  }

  unpark(): Promise<unknown> {
    return this.run('unpark', 'Unpark', async () => {
      const mount = await this.client.unpark();
      this.events.applyStatus({ mount });
    });
  }

  setTracking(enabled: boolean): Promise<unknown> {
    return this.run('tracking', 'Tracking', async () => {
      const mount = await this.client.setTracking(enabled);
      this.events.applyStatus({ mount });
    });
  }

  /** Toolbar Stop: stop whatever is running (exposure or live view, and a slew). */
  stopAll(): void {
    if (this.cameraBusy) void this.stopCamera();
    if (this.slewing) void this.stopMount();
  }

  /**
   * Escape = abort motion (BRAND 7, inventory "abort"). It never cancels an
   * exposure: Escape is also how a tooltip or a field is dismissed, and a
   * stray key press must not lose a frame.
   */
  abortMotion(): void {
    if (this.slewing) void this.stopMount();
  }
}

const KEY = Symbol('argos-app');

export function provideApp(app: ArgosApp): ArgosApp {
  return setContext(KEY, app);
}

export function useApp(): ArgosApp {
  const app = getContext<ArgosApp | undefined>(KEY);
  if (!app) throw new Error('useApp() called outside the ARGOS app context');
  return app;
}
