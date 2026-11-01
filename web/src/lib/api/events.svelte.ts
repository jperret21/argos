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
 * Snapshot messages (status, camera, mount, devices, network, activity)
 * replace the held record. Stream messages are handed to the owner of the
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
  CameraState,
  ConfigEvent,
  ConnectionState,
  DevicesState,
  JobEvent,
  LogEvent,
  MountState,
  NetworkState,
  ProfileSummary,
  ServerEvent,
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

  constructor(config: ArgosConfig, options: ArgosEventsOptions = {}) {
    this.options = options;
    this.socket = new ReconnectingSocket({
      url: withToken(`${config.wsBase}/ws/events`, config.token),
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

  /** Apply a REST answer immediately (the WS echo will follow). */
  applyStatus(status: Partial<Status>): void {
    if (status.connection) this.connection = status.connection;
    if (status.camera) this.camera = status.camera;
    if (status.mount) this.mount = status.mount;
    if (status.devices) this.devices = status.devices;
    if (status.profile) this.profile = status.profile;
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

  private handle(data: unknown): void {
    const msg = parseEventMessage(data);
    if (!msg) return;
    this.lastMessageAt = performance.now();
    switch (msg.type) {
      case 'status': {
        this.connection = msg.connection;
        this.camera = msg.camera;
        this.mount = msg.mount;
        if (msg.devices) this.devices = msg.devices;
        if (msg.profile) this.profile = msg.profile;
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
        break;
      }
    }
  }
}
