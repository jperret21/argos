/**
 * Live server state from WS /ws/events, as Svelte 5 reactive state
 * (contract: argos/server/protocol.md, API 2).
 *
 * (The file is `.svelte.ts` because runes only compile in .svelte /
 * .svelte.ts modules; import it as "./events.svelte".)
 *
 * Usage:
 *   const events = new ArgosEvents(config, { onLog, onJob, onConfig, onFirstStatus });
 *   events.start();          // in onMount / $effect
 *   events.mount?.ra_hours   // reactive in any component
 *   events.devices?.camera   // API 2: per-device states
 *   events.stop();           // on teardown
 *
 * The last known state is kept across a dropped link (link !== "open"), so
 * the UI can grey it out as stale instead of blanking the screen.
 *
 * Snapshot messages (status, camera, mount, devices, network, activity,
 * stellarium, site_check; wave 3: filterwheel, focuser, autofocus,
 * observation, target_suggestions) replace the held record. Stream messages are handed to the owner of the
 * matching store, which deduplicates and orders them by their sequence
 * numbers: `log` lines to the activity log (the server replays its last 200
 * lines after the first status of every connection), `job` events to the
 * job store, `config` events to the configuration holder.
 * `onFirstStatus` fires once per (re)connection, after its first `status`:
 * the moment to re-read the REST snapshots (jobs, older log lines).
 */

import type { ArgosConfig } from '../config';
import { type LinkState, ReconnectingSocket, type BackoffOptions, withToken } from './socket';
import type {
  ActivityEvent,
  AutofocusState,
  CameraState,
  FilterWheelState,
  FocuserState,
  Observation,
  TargetSuggestions,
  ConfigEvent,
  ConnectionState,
  DevicesState,
  JobEvent,
  LogEvent,
  MountState,
  NetworkState,
  ProfileSummary,
  ServerEvent,
  SiteCheck,
  Status,
  StellariumState,
} from './types';

/** Levels of API 1 and API 2 log lines (protocol.md "Logs (A2)"). */
const LOG_LEVELS: ReadonlySet<string> = new Set(['debug', 'cmd', 'info', 'ok', 'warning', 'error']);

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/**
 * Parse one text message of /ws/events. Returns null for anything that does
 * not match the contract (unknown types are ignored, not fatal, so a newer
 * server can add event types without breaking an older UI).
 */
export function parseEventMessage(data: unknown): ServerEvent | null {
  if (typeof data !== 'string') return null;
  let msg: unknown;
  try {
    msg = JSON.parse(data);
  } catch {
    return null;
  }
  return checkEventMessage(msg);
}

/** The typed check of an already parsed message (one JSON.parse per message, review W3). */
export function checkEventMessage(msg: unknown): ServerEvent | null {
  if (!isObject(msg)) return null;
  const ok = msg as unknown as ServerEvent;
  switch (msg.type) {
    case 'status':
      return isObject(msg.connection) && isObject(msg.camera) && isObject(msg.mount) ? ok : null;
    case 'mount':
      return isObject(msg.mount) ? ok : null;
    case 'camera':
      return isObject(msg.camera) ? ok : null;
    case 'log':
      return typeof msg.message === 'string' && typeof msg.level === 'string' && LOG_LEVELS.has(msg.level)
        ? ok
        : null;
    case 'devices':
      return isObject(msg.devices) ? ok : null;
    case 'network':
      return 'seestar' in msg ? ok : null;
    case 'activity':
      return typeof msg.text === 'string' ? ok : null;
    case 'config':
      return isObject(msg.values) && isObject(msg.changed) ? ok : null;
    case 'job':
      return isObject(msg.job) && typeof msg.job.id === 'string' ? ok : null;
    case 'stellarium':
      return typeof msg.running === 'boolean' && typeof msg.clients === 'number' ? ok : null;
    case 'site_check':
      return typeof msg.state === 'string' && typeof msg.message === 'string' ? ok : null;
    // Wave 3 snapshots (protocol.md "API 2 routes, wave 3").
    case 'filterwheel':
      return typeof msg.state === 'string' && Array.isArray(msg.slots) ? ok : null;
    case 'focuser':
      return typeof msg.state === 'string' && 'position' in msg ? ok : null;
    case 'autofocus':
      return typeof msg.state === 'string' && Array.isArray(msg.samples) ? ok : null;
    case 'observation':
      return typeof msg.object_name === 'string' ? ok : null;
    case 'target_suggestions':
      return typeof msg.state === 'string' && Array.isArray(msg.candidates) ? ok : null;
    default:
      return null;
  }
}

export interface ArgosEventsOptions {
  backoff?: BackoffOptions;
  /** Every log line (v1 or v2), as received; the log store deduplicates. */
  onLog?: (msg: LogEvent) => void;
  onJob?: (msg: JobEvent) => void;
  onConfig?: (msg: ConfigEvent) => void;
  /**
   * Once per (re)connection, after its first `status` message; `restarted`
   * when that status names another server process than the previous one
   * (API 2 `boot_id`): its log numbering started again at 1.
   */
  onFirstStatus?: (info: { restarted: boolean }) => void;
}

export class ArgosEvents {
  /** State of the WebSocket link itself (not of the telescope). */
  link: LinkState = $state('idle');
  // Objects are replaced wholesale on every message, so $state.raw (no deep
  // proxy) is enough and cheaper at the 4 Hz mount rate.
  connection: ConnectionState | null = $state.raw(null);
  camera: CameraState | null = $state.raw(null);
  mount: MountState | null = $state.raw(null);
  /** API 2: the four devices (null before the first status, or from an API 1 server). */
  devices: DevicesState | null = $state.raw(null);
  /** API 2: the active telescope profile. */
  profile: ProfileSummary | null = $state.raw(null);
  /** API 2: Seestar reachability and the last on-demand internet check. */
  network: NetworkState | null = $state.raw(null);
  /** API 2: the last action started or ended (status-bar activity text). */
  activity: ActivityEvent | null = $state.raw(null);
  /** API 2: the Stellarium bridge (A19). */
  stellarium: StellariumState | null = $state.raw(null);
  /** API 2, wave 2: the Settings site against the mount (status.site_check, `site_check` events). */
  siteCheck: SiteCheck | null = $state.raw(null);
  /** Wave 3: the filter wheel (A28; status.filterwheel, `filterwheel` events). */
  filterwheel: FilterWheelState | null = $state.raw(null);
  /** Wave 3: the focuser (A34). */
  focuser: FocuserState | null = $state.raw(null);
  /** Wave 3: the autofocus run (A36). */
  autofocus: AutofocusState | null = $state.raw(null);
  /** Wave 3: the observation identity (A38, D11). */
  observation: Observation | null = $state.raw(null);
  /** Wave 3: names near the last Stellarium GoTo (A20). */
  suggestions: TargetSuggestions | null = $state.raw(null);
  /** API 2: the server process of the last `status` (a restart changes it). */
  bootId: string | null = $state(null);
  /** performance.now() of the last message, for staleness indicators. */
  lastMessageAt: number | null = $state(null);
  /** A `status` message arrived on the current connection. */
  statusSeen = $state(false);
  /** A `status` message arrived on any connection since start(). */
  everStatus = $state(false);

  private readonly socket: ReconnectingSocket;
  private readonly options: ArgosEventsOptions;
  /** Raw listeners by message type (wave 3 streams and snapshots: see `on`). */
  private readonly listeners = new Map<string, Set<(msg: Record<string, unknown>) => void>>();

  /**
   * This page's id on /ws/events (`?client=`, wave 3): the server stops the
   * axes this client jogs when this socket closes (the jog dead-man, A30).
   */
  readonly clientId: string;

  constructor(config: ArgosConfig, options: ArgosEventsOptions = {}) {
    this.options = options;
    this.clientId = `web-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
    this.socket = new ReconnectingSocket({
      url: `${withToken(`${config.wsBase}/ws/events`, config.token)}&client=${this.clientId}`,
      backoff: options.backoff,
      onMessage: (data) => this.handle(data),
      onState: (state) => {
        this.link = state;
        if (state !== 'open') this.statusSeen = false;
      },
    });
  }

  get status(): Status | null {
    if (!this.connection || !this.camera || !this.mount) return null;
    return { connection: this.connection, camera: this.camera, mount: this.mount };
  }

  start(): void {
    this.socket.start();
  }

  stop(): void {
    this.socket.stop();
  }

  restart(): void {
    this.socket.restart();
  }

  /** Send a client message on /ws/events (wave 3: `{"type":"jog_stop"}`); false when the link is down. */
  send(message: Record<string, unknown>): boolean {
    return this.socket.send(JSON.stringify(message));
  }

  /** Apply a REST answer immediately (the WS echo will follow). */
  applyStatus(status: Partial<Status>): void {
    if (status.connection) this.connection = status.connection;
    if (status.camera) this.camera = status.camera;
    if (status.mount) this.mount = status.mount;
    if (status.devices) this.devices = status.devices;
    if (status.profile) this.profile = status.profile;
    if (status.site_check) this.siteCheck = status.site_check;
    if (status.filterwheel) this.filterwheel = status.filterwheel;
    if (status.focuser) this.focuser = status.focuser;
    if (status.autofocus) this.autofocus = status.autofocus;
    if (status.observation) this.observation = status.observation;
  }

  applySiteCheck(check: SiteCheck): void {
    this.siteCheck = check;
  }

  applyDevices(devices: DevicesState): void {
    this.devices = devices;
  }

  applyNetwork(network: NetworkState): void {
    this.network = network;
  }

  applyStellarium(state: StellariumState): void {
    this.stellarium = state;
  }

  /**
   * Listen to every message of one `type` as it arrives, before any typed
   * parsing (wave 3: `conditions`, `frame_metrics`, `frame_saved`,
   * `autofocus`, … and the `status` record that carries their snapshots).
   * The owner validates its own messages; returns the unsubscribe function.
   */
  on(type: string, fn: (msg: Record<string, unknown>) => void): () => void {
    let set = this.listeners.get(type);
    if (!set) this.listeners.set(type, (set = new Set()));
    set.add(fn);
    return () => set.delete(fn);
  }

  private dispatch(msg: unknown): void {
    if (this.listeners.size === 0) return;
    if (!isObject(msg) || typeof msg.type !== 'string' || !this.listeners.has(msg.type)) return;
    for (const fn of this.listeners.get(msg.type) ?? []) {
      try {
        fn(msg);
      } catch (err) {
        console.error(`[events] ${msg.type} listener failed`, err);
      }
    }
  }

  private handle(data: unknown): void {
    if (typeof data !== 'string') return;
    let raw: unknown;
    try {
      raw = JSON.parse(data); // once: the raw listeners and the typed switch share it
    } catch {
      return;
    }
    this.dispatch(raw);
    const msg = checkEventMessage(raw);
    if (!msg) return;
    this.lastMessageAt = performance.now();
    switch (msg.type) {
      case 'status': {
        this.connection = msg.connection;
        this.camera = msg.camera;
        this.mount = msg.mount;
        if (msg.devices) this.devices = msg.devices;
        if (msg.profile) this.profile = msg.profile;
        if (msg.site_check) this.siteCheck = msg.site_check;
        if (msg.filterwheel) this.filterwheel = msg.filterwheel;
        if (msg.focuser) this.focuser = msg.focuser;
        if (msg.autofocus) this.autofocus = msg.autofocus;
        if (msg.observation) this.observation = msg.observation;
        const first = !this.statusSeen;
        let restarted = false;
        if (typeof msg.boot_id === 'string') {
          restarted = this.bootId !== null && this.bootId !== msg.boot_id;
          this.bootId = msg.boot_id;
        }
        this.statusSeen = true;
        this.everStatus = true;
        if (first) this.options.onFirstStatus?.({ restarted });
        break;
      }
      case 'mount':
        this.mount = msg.mount;
        break;
      case 'camera':
        this.camera = msg.camera;
        break;
      case 'devices':
        this.devices = msg.devices;
        break;
      case 'network': {
        const { type: _type, ...network } = msg;
        this.network = network;
        break;
      }
      case 'activity':
        this.activity = msg;
        break;
      case 'log':
        this.options.onLog?.(msg);
        break;
      case 'job':
        this.options.onJob?.(msg);
        break;
      case 'config':
        this.options.onConfig?.(msg);
        break;
      case 'stellarium': {
        const { type: _type, ...bridge } = msg;
        this.stellarium = bridge;
        if (bridge.suggestions !== undefined) this.suggestions = bridge.suggestions ?? null;
        break;
      }
      case 'site_check': {
        const { type: _type, ...check } = msg;
        this.siteCheck = check;
        break;
      }
      case 'filterwheel': {
        const { type: _type, ...wheel } = msg;
        this.filterwheel = wheel;
        break;
      }
      case 'focuser': {
        const { type: _type, ...focuser } = msg;
        this.focuser = focuser;
        break;
      }
      case 'autofocus': {
        const { type: _type, ...af } = msg;
        this.autofocus = af;
        break;
      }
      case 'observation': {
        const { type: _type, ...obs } = msg;
        this.observation = obs;
        break;
      }
      case 'target_suggestions': {
        const { type: _type, ...sugg } = msg;
        this.suggestions = sugg;
        break;
      }
    }
  }
}
