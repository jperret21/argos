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
 * Wave 1 shell infrastructure lives here too: the one activity log store
 * (`log`, D17: log v2 lines from /ws/events, older lines and gaps from
 * GET /api/logs), the jobs (`jobs`, README 4.2: `job` events, GET /api/jobs
 * on every (re)connection), the shortcut registry (`shortcuts`, README 3.10)
 * with its global bindings (F1-F5, ?, L, Mod+, and Escape = abort motion,
 * D21), and the API 2 records the shell and the Connection screen show:
 * devices, telescope profiles, network reachability, the activity text, the
 * configuration values and the application info (start-up screen, Help).
 *
 * Equipment (API 2, per device): connectAll / disconnectAll / connectDevice /
 * disconnectDevice use the link chosen on the Connection screen (Simulator,
 * or a Seestar address saved to the config on commit). The server answers
 * each request once the device is connected or failed, never blocking its
 * other routes, so the UI stays live while an address times out.
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
import type {
  AppInfo,
  CameraState,
  ConfigEvent,
  ConfigValue,
  ConnectionState,
  DeviceConnectBody,
  DeviceId,
  DevicesState,
  KeyMeta,
  LogEvent,
  MountState,
  NetworkState,
  ProfilesState,
} from '../api/types';
import { type ArgosConfig, loadConfig } from '../config';
import {
  currentLink,
  DEVICE_IDS,
  DEVICE_LABELS,
  deviceAddress,
  devicesSummary,
  type DevicesSummary,
  parseDiscoveryResult,
  type RunningState,
} from '../connection/model';
import { isRotationMode, type RotationMode } from '../viewer/rotation';
import type { StretchMode, StretchParams } from '../viewer/stretch';
import type { DisplayInfo, PointerInfo } from '../viewer/types';
import { type FitMode, isFitMode } from '../viewer/view';
import { openLayers, setReservedKeys, topModalIndex } from '../components/layers';
import { JobStore } from './jobs.svelte';
import { KEYMAP } from './keymap';
import { LogStore } from './log.svelte';
import { type FrameMetrics, FrameRateMeter } from './metrics';
import { isBoolean, loadPref, savePref } from './prefs';
import { ShortcutRegistry } from './shortcuts';
import { type StartupFailure, startupView, type StartupView } from './startup';
import { deviceUsable } from './status';
import { loadTheme, nextTheme, parseCssColor, saveTheme, type Theme } from './theme';

export const SECTIONS = ['connection', 'imaging', 'sequencer', 'analyze', 'configuration'] as const;
export type Section = (typeof SECTIONS)[number];
const isSection = (v: unknown): v is Section => typeof v === 'string' && (SECTIONS as readonly string[]).includes(v);

export type ConnectMode = 'simulator' | 'alpaca';
const isConnectMode = (v: unknown): v is ConnectMode => v === 'simulator' || v === 'alpaca';

export type ActionKey =
  | 'connectAll'
  | 'disconnectAll'
  | `device.${DeviceId}`
  | `release.${DeviceId}`
  | 'discover'
  | 'profile'
  | 'address'
  | 'network'
  | 'stellarium'
  | 'capture'
  | 'live'
  | 'liveSettings'
  | 'cameraStop'
  | 'goto'
  | 'mountStop'
  | 'park'
  | 'unpark'
  | 'tracking';

/** Outcome of a config commit: the server's per-key messages when it refused. */
export interface CommitResult {
  ok: boolean;
  message?: string;
  fields?: Record<string, string>;
  warnings?: { key: string; message: string }[];
}

/** Server health as the start-up screen sees it. */
export type HealthState = 'pending' | 'ok' | 'failed';

/** Consecutive failed health checks before the start-up screen reports a failure. */
const HEALTH_FAILURES_BEFORE_REPORT = 3;
const HEALTH_RETRY_MS = 1500;
/** Health answered but /ws/events sent no status: report after this long. */
const FIRST_STATUS_TIMEOUT_MS = 10_000;

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
  /** API level reported by GET /api/health (1, or 2 once wave 1 ships). */
  serverApi: number | null = $state(null);
  /** Last frame received from /ws/frames (the viewer may coalesce several). */
  frame: DecodedFrame | null = $state.raw(null);
  /** performance.now() of the last frame received, for the live progress bar. */
  lastFrameAt: number | null = $state(null);
  /** Wall clock (epoch ms), ticked once a second: frame age and staleness. */
  clock = $state(Date.now());

  // -- Navigation and actions -------------------------------------------------
  /**
   * Q-G19 (Qt rule): the last section, except Observe, which opens as
   * Connection until a device is connected or a frame is shown.
   */
  section: Section = $state(initialSection());
  private readonly savedSection: Section = loadPref('argos.section', isSection, 'connection');
  private navigated = false;
  busy: Partial<Record<ActionKey, boolean>> = $state({});

  // -- API 2 records (Connection screen, shell) --------------------------------
  appInfo: AppInfo | null = $state.raw(null);
  profiles: ProfilesState | null = $state.raw(null);
  /** Values of GET /api/config, kept current by `config` events. */
  configValues: Record<string, ConfigValue> | null = $state.raw(null);
  configMeta: Record<string, KeyMeta> | null = $state.raw(null);
  /** Id of the discovery job this page shows (started here, or found running). */
  discoveryJobId: string | null = $state(null);
  /** Discovery finished with several devices: the choice popover lists them. */
  discoveryChoices: { host: string; port: number; name: string | null }[] = $state.raw([]);
  /** One-line outcome under Discover ("Found 192.168.1.42:32323", "No Alpaca devices found…"). */
  discoveryNote: { tone: 'info' | 'warning' | 'error'; text: string } | null = $state.raw(null);

  // -- Start-up screen (01 2.3.8) ----------------------------------------------
  health: HealthState = $state('pending');
  private healthError: string | null = $state(null);
  private healthFailures = 0;
  private firstStatusTimedOut = $state(false);
  /** The start-up screen has finished once; it never comes back (link losses show in the status bar). */
  started = $state(false);

  // -- Observer settings ------------------------------------------------------
  exposure = $state(2);
  gain = $state(80);
  /** The Camera card fields hold text that is not a valid value. */
  exposureInvalid = $state(false);
  gainInvalid = $state(false);
  /** Link chosen on the Connection screen (web only); follows the devices' link while one is held. */
  connectMode: ConnectMode = $state(loadPref('argos.connection.mode', isConnectMode, 'simulator'));
  /** `alpaca.host` / `alpaca.port` of the server config (written on commit, never per keystroke). */
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
  /**
   * The Connection screen's log shows every topic (L there): the Connection
   * screen has its own log region, so L widens it in place instead of
   * stacking the drawer's copy of the same lines under it.
   */
  connectionLogAll = $state(false);
  /** The one activity log of the UI (server lines + client failures), 5 000 lines. */
  readonly log = new LogStore();
  /** Long-running jobs (discovery, …): progress, cancel, outcome. */
  readonly jobs: JobStore;
  /** The one shortcut registry: keymap, conflict check, dispatch, the "?" sheet. */
  readonly shortcuts = new ShortcutRegistry(KEYMAP, { blocked: () => topModalIndex(openLayers()) >= 0 });
  /** Keyboard shortcuts sheet ("?", Help menu). */
  shortcutSheetOpen = $state(false);
  /** A GET /api/logs is running (fills a gap or the history after a (re)connection). */
  private logFetch: Promise<void> | null = null;
  private nextToastId = 1;
  private toastTimers = new Map<number, ReturnType<typeof setTimeout>>();

  constructor(config: ArgosConfig = loadConfig()) {
    this.config = config;
    this.client = new ArgosClient(config);
    this.events = new ArgosEvents(config, {
      onLog: (msg) => this.onLogLine(msg),
      onJob: (msg) => this.onJobEvent(msg.job),
      onConfig: (msg) => this.applyConfigEvent(msg),
      onFirstStatus: ({ restarted }) => this.onLinkUp(restarted),
    });
    this.frames = new FrameStream(config, {
      onFrame: (f) => {
        this.frame = f;
        this.lastFrameAt = performance.now();
      },
      onState: (s) => (this.framesLink = s),
      onError: (err) => this.log.push('warning', `Frame dropped: ${err.message}`, { source: 'web', topic: 'camera' }),
    });
    this.jobs = new JobStore({ cancel: (id) => this.client.cancelJob(id) });
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

  /** At least one of the camera and the mount is connected (v1 record): "some equipment". */
  get connected(): boolean {
    return this.events.connection?.state === 'connected';
  }

  /** The mount itself is connected (its own device record): its readouts are real. */
  get mountReady(): boolean {
    return deviceUsable(this.events.devices, 'mount', this.events.connection);
  }

  /** The camera itself is connected (its own device record). */
  get cameraReady(): boolean {
    return deviceUsable(this.events.devices, 'camera', this.events.connection);
  }

  get devices(): DevicesState | null {
    return this.events.devices;
  }

  get network(): NetworkState | null {
    return this.events.network;
  }

  /** "n of 4 devices ready", and whether a link is held (profile and link locked). */
  get equipment(): DevicesSummary {
    return devicesSummary(this.events.devices);
  }

  /** What runs on the equipment now (a disconnection would stop it). */
  get running(): RunningState {
    const cam = this.events.camera?.state;
    return { live: cam === 'live', exposing: cam === 'exposing' || cam === 'downloading', slewing: this.slewing };
  }

  /** The start-up screen's stages and outcome (01 2.3.8). */
  get startup(): StartupView {
    return startupView({
      desktop: false,
      health: this.health,
      firstStatus: this.events.everStatus,
      failure: this.startupFailure(),
    });
  }

  private startupFailure(): StartupFailure | null {
    const logPath = this.appInfo?.paths.log_file ?? null;
    const link = this.events.link;
    if (link === 'unauthorized') {
      return {
        title: 'The server rejected the token',
        message: 'Open the UI with ?token=… as printed by the server (ARGOS_TOKEN=…).',
        detail: `WebSocket closed with code 4401 by ${this.config.apiBase}`,
        logPath,
      };
    }
    if (link === 'forbidden') {
      return {
        title: 'The server refused this page',
        message: 'Open the UI from localhost or 127.0.0.1: the server only answers local pages.',
        detail: `WebSocket closed with code 4403 by ${this.config.apiBase}`,
        logPath,
      };
    }
    if (this.health === 'failed') {
      return {
        title: 'ARGOS could not reach its server',
        message: `No answer from ${this.config.apiBase}. Start it with "python -m argos.server"; this page keeps trying.`,
        detail: this.healthError,
        logPath,
      };
    }
    if (this.firstStatusTimedOut && !this.events.everStatus) {
      return {
        title: 'The server sends no state',
        message: 'GET /api/health answers, but /ws/events sent no status within 10 s.',
        detail: `Event link: ${link}`,
        logPath,
      };
    }
    return null;
  }

  /**
   * The server link is down: every record on screen is the last one received,
   * not the current state. Readouts grey out and hardware actions are refused.
   */
  get stale(): boolean {
    return this.events.link !== 'open';
  }

  /** Camera commands can be sent (link up and the camera connected). */
  get canCamera(): boolean {
    return !this.stale && this.cameraReady;
  }

  /** Mount commands can be sent (link up and the mount connected). */
  get canMount(): boolean {
    return !this.stale && this.mountReady;
  }

  get live(): boolean {
    return this.events.camera?.state === 'live';
  }

  get cameraBusy(): boolean {
    const s = this.events.camera?.state;
    return s === 'exposing' || s === 'downloading' || s === 'live';
  }

  get slewing(): boolean {
    return this.mountReady && this.events.mount?.state === 'slewing';
  }

  /**
   * The frame on screen is not a current camera frame: equipment
   * disconnected, server link down, or no new frame for max(5 s, three
   * exposures). Files are files, never "stale".
   */
  get frameStale(): boolean {
    const h = this.shown?.frame.header;
    if (!h || h.source === 'file') return false;
    if (!this.canCamera) return true;
    const t = Date.parse(h.timestamp);
    if (!Number.isFinite(t)) return false;
    const exposure = Math.max(h.exposure_s, this.cameraBusy ? (this.camera?.exposure_s ?? 0) : 0);
    return this.clock - t > Math.max(5000, 3000 * exposure);
  }

  /** Rate and latency, only while they describe a running stream. */
  get liveMetrics(): FrameMetrics {
    if (this.frameStale || !this.canCamera) return { ...this.metrics, fps: null, latencyMs: null };
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

  /** Warnings and errors logged since the log was last seen. */
  get unseenProblems(): number {
    return this.log.unseenProblems;
  }

  // -- Lifecycle ------------------------------------------------------------------

  start(): () => void {
    this.applyTheme(this.theme);
    this.events.start();
    this.frames.start();
    this.readHealth();
    const tick = setInterval(() => (this.clock = Date.now()), 1000);
    const statusTimer = setTimeout(() => (this.firstStatusTimedOut = true), FIRST_STATUS_TIMEOUT_MS);
    const stopEffects = $effect.root(() => {
      $effect(() => {
        const cam = this.events.camera;
        untrack(() => this.followCamera(cam));
      });
      $effect(() => {
        this.shortcuts.setScopes([this.section]);
      });
      // The link held by connected devices decides the mode shown.
      $effect(() => {
        const link = currentLink(this.events.devices);
        if (link) untrack(() => this.setConnectMode(link.mode));
      });
      // Q-G19: back to Observe once the equipment or a frame is there.
      $effect(() => {
        const ready = this.connected || !!this.frame;
        untrack(() => {
          if (ready && !this.navigated && this.savedSection === 'imaging' && this.section === 'connection') {
            this.section = 'imaging';
          }
        });
      });
      $effect(() => {
        if (this.startup.ready) untrack(() => (this.started = true));
      });
    });
    const stopKeys = this.bindShortcuts();
    return () => {
      clearInterval(tick);
      clearTimeout(statusTimer);
      clearTimeout(this.healthTimer);
      stopEffects();
      stopKeys();
      this.events.stop();
      this.frames.stop();
      for (const t of this.toastTimers.values()) clearTimeout(t);
      this.toastTimers.clear();
    };
  }

  /** Change section (rail, F-keys, links): the observer chose, so Q-G19 no longer overrides it. */
  go(section: Section): void {
    this.navigated = true;
    this.section = section;
    savePref('argos.section', section);
  }

  /**
   * After the first `status` of every (re)connection: re-read what the
   * socket does not replay (README 3.7 "Reconnect"): jobs, the log history
   * beyond the 200 replayed lines, the configuration, profiles, network and
   * application info.
   */
  private onLinkUp(restarted = false): void {
    this.health = 'ok';
    this.healthFailures = 0;
    // A new server process (boot_id changed): its log seq starts again at 1.
    // Mark it before its replayed lines arrive, then read its whole ring.
    if (restarted) this.log.restart();
    const quiet = (what: string) => (err: unknown) => {
      // An API 1 server has none of these routes: keep the v1 behaviour.
      if (err instanceof ApiError && err.status === 404) return;
      this.log.push('warning', `${what}: ${err instanceof Error ? err.message : String(err)}`, {
        source: 'web',
        topic: 'app',
      });
    };
    void this.client
      .appInfo()
      .then((info) => (this.appInfo = info))
      .catch(quiet('Application info'));
    const jobMarks = this.jobs.marks();
    void this.client
      .jobs()
      .then((answer) => {
        this.jobs.snapshot(answer.jobs, jobMarks);
        this.adoptRunningDiscovery();
      })
      .catch(quiet('Jobs'));
    // A (re)connection may reach a restarted server, whose revision starts at 0 again.
    this.configRevision = null;
    void this.reloadConfig().catch(quiet('Configuration'));
    void this.reloadProfiles().catch(quiet('Telescope profiles'));
    void this.client
      .network()
      .then((n) => this.events.applyNetwork(n))
      .catch(quiet('Network'));
    void this.fillLog(restarted ? 0 : (this.log.lastSeq ?? 0), restarted);
  }

  // -- Log v2 ---------------------------------------------------------------------

  private onLogLine(msg: LogEvent): void {
    const r = this.log.ingest(msg);
    // A restarted server numbers its lines from 1 again: read its whole ring.
    if (r.restarted) void this.fillLog(0, true);
    else if (r.gap && r.gapAfter !== null) void this.fillLog(r.gapAfter);
  }

  /** GET /api/logs?after= and merge (the store orders by seq and drops duplicates). */
  private fillLog(after: number, force = false): Promise<void> {
    if (this.logFetch && !force) return this.logFetch;
    this.logFetch = this.client
      .logs({ after, limit: 5000 })
      .then((page) => {
        this.log.ingestPage(page);
      })
      .catch(() => {
        /* an API 1 server, or the link dropped: the replay still brought the last lines */
      })
      .finally(() => (this.logFetch = null));
    return this.logFetch;
  }

  // -- Configuration -------------------------------------------------------------------

  /** Revision of the values held (config events and answers of this connection). */
  private configRevision: number | null = null;

  private async reloadConfig(): Promise<void> {
    const snap = await this.client.getConfig();
    this.configMeta = snap.meta;
    // A config event may have arrived while the GET was in flight: never go back.
    this.adoptConfigValues(snap.values, snap.revision);
  }

  private applyConfigEvent(msg: ConfigEvent): void {
    this.adoptConfigValues(msg.values, msg.revision);
    if ('hardware.profile' in msg.changed || Object.keys(msg.changed).some((k) => k.startsWith('hardware.'))) {
      void this.reloadProfiles().catch(() => {});
    }
    if ('astrometry.astap_path' in msg.changed) {
      void this.client
        .appInfo()
        .then((info) => (this.appInfo = info))
        .catch(() => {});
    }
  }

  private adoptConfigValues(values: Record<string, ConfigValue>, revision?: number): void {
    if (typeof revision === 'number') {
      if (this.configRevision !== null && revision < this.configRevision) return;
      this.configRevision = revision;
    }
    this.configValues = values;
    if (typeof values['alpaca.host'] === 'string') this.alpacaHost = values['alpaca.host'];
    if (typeof values['alpaca.port'] === 'number') {
      this.alpacaPort = values['alpaca.port'];
      this.alpacaPortInvalid = false;
    }
  }

  /** One config commit (PATCH /api/config): the server validates every key or none. */
  async commitConfig(changes: Record<string, ConfigValue>): Promise<CommitResult> {
    try {
      const r = await this.client.patchConfig(changes);
      this.adoptConfigValues(r.values, r.revision);
      for (const w of r.warnings) this.toast('warning', w.key, w.message);
      return { ok: true, warnings: r.warnings };
    } catch (err) {
      const api = err instanceof ApiError ? err : null;
      if (api?.fields) return { ok: false, message: api.message, fields: api.fields };
      this.reportError('Save setting', err);
      return { ok: false, message: err instanceof Error ? err.message : String(err) };
    }
  }

  /** Save the Seestar address (Link card fields, on commit). */
  async saveAddress(host: string, port: number): Promise<CommitResult> {
    const changes: Record<string, ConfigValue> = {};
    if (host.trim() !== this.alpacaHost) changes['alpaca.host'] = host.trim();
    if (port !== this.alpacaPort) changes['alpaca.port'] = port;
    if (!Object.keys(changes).length) return { ok: true };
    this.busy.address = true;
    try {
      return await this.commitConfig(changes);
    } finally {
      this.busy.address = false;
    }
  }

  // -- Profiles (A17) -----------------------------------------------------------------

  private async reloadProfiles(): Promise<void> {
    this.profiles = await this.client.profiles();
  }

  /** The telescope profile; refused by the server while equipment is connected. */
  setProfile(key: string): Promise<unknown> {
    return this.run('profile', 'Telescope profile', async () => {
      this.profiles = await this.client.setProfile(key);
    });
  }

  // -- Stellarium bridge (A19) --------------------------------------------------------

  /** Start the bridge on the configured host and port (the server saves them). */
  startStellarium(): Promise<unknown> {
    return this.run('stellarium', 'Stellarium bridge', async () => {
      try {
        this.events.applyStellarium(await this.client.startStellarium());
      } catch (err) {
        // A bind error is also in the bridge's record (shown on the card): refresh it.
        void this.client
          .stellarium()
          .then((st) => this.events.applyStellarium(st))
          .catch(() => {});
        throw err;
      }
    });
  }

  stopStellarium(): Promise<unknown> {
    return this.run('stellarium', 'Stellarium bridge', async () => {
      this.events.applyStellarium(await this.client.stopStellarium());
    });
  }

  // -- Network (A18) ------------------------------------------------------------------

  /** Re-probe the Seestar, and check the internet: on request only (Q-G13). */
  checkNetwork(internet: boolean): Promise<unknown> {
    return this.run('network', internet ? 'Internet check' : 'Seestar check', async () => {
      this.events.applyNetwork(await this.client.checkNetwork(internet));
    });
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
    this.readHealth();
  }

  private healthTimer: ReturnType<typeof setTimeout> | undefined;

  /**
   * GET /api/health (open route: tells "server down" from "bad token"). Until
   * it answers, it is retried; after three failures the start-up screen says
   * so, and the retries go on (the page connects as soon as the server is up).
   */
  private readHealth(): void {
    clearTimeout(this.healthTimer);
    this.client
      .health({ timeoutMs: 4000 })
      .then((h) => {
        this.serverVersion = h.version;
        this.serverApi = h.api;
        this.health = 'ok';
        this.healthError = null;
        this.healthFailures = 0;
      })
      .catch((err) => {
        this.serverVersion = null;
        this.serverApi = null;
        this.healthFailures += 1;
        this.healthError = err instanceof Error ? err.message : String(err);
        if (this.healthFailures >= HEALTH_FAILURES_BEFORE_REPORT) this.health = 'failed';
        this.healthTimer = setTimeout(() => this.readHealth(), HEALTH_RETRY_MS);
      });
  }

  /** Start-up screen "Retry": reconnect at once. */
  retryStartup(): void {
    this.healthFailures = 0;
    this.health = 'pending';
    this.firstStatusTimedOut = false;
    this.reconnect();
  }

  /**
   * Global bindings of the registry, dispatched from one window listener:
   * F1-F5 (Mod+1…5 in the desktop app), ?, L, Mod+, and Escape. Section
   * keys are bound by their screen (ImagingScreen binds the Observe keys)
   * while it is mounted.
   */
  private bindShortcuts(): () => void {
    const nav: [string, Section][] = [
      ['nav.connection', 'connection'],
      ['nav.observe', 'imaging'],
      ['nav.plan', 'sequencer'],
      ['nav.review', 'analyze'],
      ['nav.settings', 'configuration'],
      ['nav.connection.desktop', 'connection'],
      ['nav.observe.desktop', 'imaging'],
      ['nav.plan.desktop', 'sequencer'],
      ['nav.review.desktop', 'analyze'],
      ['nav.settings.desktop', 'configuration'],
    ];
    const off = [
      ...nav.map(([id, section]) => this.shortcuts.handle(id, () => this.go(section))),
      this.shortcuts.handle('help.shortcuts', () => (this.shortcutSheetOpen = true)),
      this.shortcuts.handle('log.toggle', () => this.toggleLog()),
      this.shortcuts.handle('nav.settings.mod', () => this.go('configuration')),
      this.shortcuts.handle('motion.abort', () => this.abortMotion()),
    ];
    const detach = typeof window === 'undefined' ? () => {} : this.shortcuts.attach(window);
    setReservedKeys((e) => this.shortcuts.reserves(e));
    return () => {
      setReservedKeys(null);
      detach();
      for (const f of off) f();
    };
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
    this.log.markSeen();
  }

  /** The full activity log is on screen: the drawer, or on Connection its log region widened to every topic. */
  get logShown(): boolean {
    return this.section === 'connection' ? this.connectionLogAll : this.logOpen;
  }

  /** L and the status-bar Log button: the whole log, wherever the observer is. */
  toggleLog(): void {
    if (this.section === 'connection') {
      this.connectionLogAll = !this.connectionLogAll;
      this.log.markSeen();
    } else {
      this.setLogOpen(!this.logOpen);
    }
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
    if (!api || api.status < 500) this.log.push('error', `${what}: ${message}`, { source: 'web' });
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

  // -- Equipment (API 2: A13-A16) -------------------------------------------------------

  setConnectMode(mode: ConnectMode): void {
    if (this.connectMode === mode) return;
    this.connectMode = mode;
    savePref('argos.connection.mode', mode);
  }

  /** Why a device cannot be connected with the Connection screen's choices, or null. */
  connectProblem(): string | null {
    if (!this.linkOpen) return 'the ARGOS server is not reachable';
    if (this.connectMode === 'alpaca' && !this.alpacaHost.trim()) return 'enter the Seestar address';
    if (this.connectMode === 'alpaca' && this.alpacaPortInvalid) return 'fix the Alpaca port';
    return null;
  }

  /** Body of the connect routes for the chosen link. */
  private linkBody(): DeviceConnectBody {
    return this.connectMode === 'alpaca'
      ? { mode: 'alpaca', host: this.alpacaHost.trim(), port: Math.round(this.alpacaPort) }
      : { mode: 'simulator' };
  }

  /** "Connecting mount…" is in flight from this page, or the server says so. */
  deviceBusy(id: DeviceId): boolean {
    return !!this.busy[`device.${id}`] || this.events.devices?.[id]?.state === 'connecting';
  }

  /** Connect all: the four devices, skipping those already connected (A15). */
  connectAll(): Promise<unknown> {
    if (this.connectProblem()) return Promise.resolve(undefined);
    return this.run('connectAll', 'Connect all', async () => {
      const devices = await this.client.connectAll(this.linkBody());
      this.events.applyDevices(devices);
      this.reportDeviceFailures(devices);
    });
  }

  disconnectAll(): Promise<unknown> {
    for (const id of DEVICE_IDS) if (this.busy[`device.${id}`]) this.released.add(id);
    return this.run('disconnectAll', 'Disconnect all', async () => {
      this.events.applyDevices(await this.client.disconnectAll());
    });
  }

  connectDevice(id: DeviceId): Promise<unknown> {
    if (this.connectProblem()) return Promise.resolve(undefined);
    this.released.delete(id);
    return this.run(`device.${id}`, `Connect ${DEVICE_LABELS[id].toLowerCase()}`, async () => {
      try {
        this.events.applyDevices(await this.client.connectDevice(id, this.linkBody()));
      } catch (err) {
        // The observer cancelled this attempt (row "Cancel", Disconnect all):
        // the server answers 409 "… was disconnected while connecting", which
        // is the outcome asked for, not a failure to report.
        if (err instanceof ApiError && err.code === 'not_connected' && this.released.has(id)) return;
        throw err;
      }
    });
  }

  /** Devices released by the observer while a connect of theirs was in flight. */
  private readonly released = new Set<DeviceId>();

  /**
   * Disconnect one device; for a mount in auto-retry it is "Stop retrying",
   * for a device still connecting it cancels the attempt (its own action
   * key, so it is never blocked by the connect request it cancels).
   */
  disconnectDevice(id: DeviceId): Promise<unknown> {
    if (this.busy[`device.${id}`]) this.released.add(id);
    return this.run(`release.${id}`, `Disconnect ${DEVICE_LABELS[id].toLowerCase()}`, async () => {
      this.events.applyDevices(await this.client.disconnectDevice(id));
    });
  }

  /**
   * Connect-all answers 200 with every state: failures are in the rows and
   * the log (server ERROR lines); a toast says it from any section.
   */
  private reportDeviceFailures(devices: DevicesState): void {
    const failed = DEVICE_IDS.filter((id) => devices[id]?.state === 'error');
    if (!failed.length) return;
    const names = failed.map((id) => DEVICE_LABELS[id]).join(', ');
    const first = devices[failed[0]];
    const title = failed.length === 1 ? `${names} did not connect` : `${failed.length} devices did not connect`;
    this.toast('error', title, `${failed.length > 1 ? `${names}: ` : ''}${first?.error ?? 'see the Connection log'}`);
  }

  /** v1 names used by the Observe screen: the toolbar equipment button and the viewer prompt (D10). */
  connect(): Promise<unknown> {
    return this.connectAll();
  }

  disconnect(): Promise<unknown> {
    return this.disconnectAll();
  }

  // -- Discovery (A16, job) ------------------------------------------------------------

  /** The discovery job shown under Discover (latest of this page, or one found running). */
  get discoveryJob() {
    return this.discoveryJobId ? this.jobs.get(this.discoveryJobId) : null;
  }

  get discovering(): boolean {
    const job = this.discoveryJob;
    return !!job && (job.state === 'queued' || job.state === 'running');
  }

  startDiscovery(): Promise<unknown> {
    this.discoveryNote = null;
    this.discoveryChoices = [];
    return this.run('discover', 'Discovery', async () => {
      try {
        const answer = await this.client.startDiscovery();
        this.jobs.ingest(answer.job);
        this.discoveryJobId = answer.job_id;
        this.ownDiscovery.add(answer.job_id);
        // The WS may have delivered the end before this answer: settle it as ours.
        if (this.settledJobs.delete(answer.job_id)) this.settleDiscovery(answer.job_id);
      } catch (err) {
        // Already running (another page started it): show that one.
        if (err instanceof ApiError && err.code === 'busy' && err.owner) {
          this.discoveryJobId = err.owner;
          const job = await this.client.job(err.owner).catch(() => null);
          if (job) this.jobs.ingest(job);
          return;
        }
        throw err;
      }
    });
  }

  cancelDiscovery(): void {
    if (this.discoveryJobId) void this.jobs.cancel(this.discoveryJobId);
  }

  /** Jobs this page started: only these fill the address when they finish. */
  private readonly ownDiscovery = new Set<string>();
  private readonly settledJobs = new Set<string>();

  private onJobEvent(raw: unknown): void {
    const job = this.jobs.ingest(raw);
    if (!job) return;
    if (job.kind === 'discovery') {
      if (job.state === 'queued' || job.state === 'running') {
        // Started elsewhere (another page): show it here too.
        if (!this.discovering) this.discoveryJobId = job.id;
      } else {
        this.settleDiscovery(job.id);
      }
    }
  }

  /** After a reconnection, show a discovery that is still running. */
  private adoptRunningDiscovery(): void {
    const running = this.jobs.active.find((j) => j.kind === 'discovery');
    if (running) this.discoveryJobId = running.id;
    if (this.discoveryJobId) this.settleDiscovery(this.discoveryJobId);
  }

  /**
   * A discovery ended: one device fills the address (as Qt did), several
   * open the choice, none says so under the button (02 W2).
   */
  private settleDiscovery(id: string): void {
    const job = this.jobs.get(id);
    if (!job || job.state === 'queued' || job.state === 'running' || this.settledJobs.has(id)) return;
    this.settledJobs.add(id);
    if (id !== this.discoveryJobId) return;
    if (job.state === 'cancelled') {
      this.discoveryNote = { tone: 'info', text: 'Discovery cancelled.' };
      return;
    }
    if (job.state === 'failed') {
      this.discoveryNote = { tone: 'error', text: `Discovery: ${job.error?.message ?? 'failed'}` };
      return;
    }
    const result = parseDiscoveryResult(job.result);
    const found = result?.devices ?? [];
    if (!found.length) {
      this.discoveryNote = { tone: 'warning', text: 'No Alpaca devices found (broadcast, direct probes and subnet scan).' };
      return;
    }
    if (found.length === 1) {
      const d = found[0];
      this.discoveryNote = { tone: 'info', text: `Found ${deviceAddress(d)}${d.name ? ` (${d.name})` : ''}` };
      if (this.ownDiscovery.has(id)) void this.useDiscovered(d.host, d.port);
      return;
    }
    this.discoveryNote = { tone: 'info', text: `Found ${found.length} devices: choose one.` };
    if (this.ownDiscovery.has(id)) this.discoveryChoices = found;
  }

  /** Take a discovered address: Seestar mode, saved to the config (the server never fills it). */
  async useDiscovered(host: string, port: number): Promise<CommitResult> {
    const several = this.discoveryChoices.length;
    this.discoveryChoices = [];
    if (this.equipment.anyLinked) {
      return { ok: false, message: 'Disconnect the equipment before changing the address.' };
    }
    this.setConnectMode('alpaca');
    const r = await this.saveAddress(host, port);
    if (r.ok && several > 1) {
      this.discoveryNote = { tone: 'info', text: `Found ${several} devices · using ${host}:${port}` };
    }
    return r;
  }

  /** The choice popover was closed without a choice: say so where it stood. */
  dismissDiscoveryChoice(): void {
    const several = this.discoveryChoices.length;
    this.discoveryChoices = [];
    if (several > 1) {
      this.discoveryNote = { tone: 'info', text: `Found ${several} devices · none chosen (Discover again to choose)` };
    }
  }

  /** Forget the last discovery's outcome (its line under Discover). */
  dismissDiscovery(): void {
    this.discoveryChoices = [];
    this.discoveryNote = null;
    if (this.discoveryJobId && !this.discovering) {
      this.jobs.dismiss(this.discoveryJobId);
      this.discoveryJobId = null;
    }
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

/** Q-G19: the last section, except Observe, which opens as Connection (restored when the equipment is there). */
function initialSection(): Section {
  const saved = loadPref('argos.section', isSection, 'connection');
  return saved === 'imaging' ? 'connection' : saved;
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
