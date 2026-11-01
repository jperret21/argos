/**
 * Live server state from WS /ws/events, as Svelte 5 reactive state.
 *
 * (The file is `.svelte.ts` because runes only compile in .svelte /
 * .svelte.ts modules; import it as "./events.svelte".)
 *
 * Usage:
 *   const events = new ArgosEvents(config);
 *   events.start();          // in onMount / $effect
 *   events.mount?.ra_hours   // reactive in any component
 *   events.stop();           // on teardown
 *
 * The last known state is kept across a dropped link (link !== "open"), so
 * the UI can grey it out as stale instead of blanking the screen.
 *
 * On every (re)connection the server replays its recent log lines after the
 * first status; lines already shown (same time, level and text) are dropped.
 */

import type { ArgosConfig } from '../config';
import { type LinkState, ReconnectingSocket, type BackoffOptions, withToken } from './socket';
import type {
  CameraState,
  ConnectionState,
  LogLevel,
  MountState,
  ServerEvent,
  Status,
} from './types';

export interface LogEntry {
  level: LogLevel;
  message: string;
  /** ISO 8601 UTC from the server. */
  t: string;
  /** Monotonic id for keyed lists. */
  id: number;
}

/** Keep the log bounded: the UI shows the tail, the server keeps files. */
export const MAX_LOG_ENTRIES = 500;

const LOG_LEVELS: ReadonlySet<string> = new Set(['info', 'warning', 'error']);

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
  switch (msg.type) {
    case 'status':
      return isObject(msg.connection) && isObject(msg.camera) && isObject(msg.mount)
        ? (msg as unknown as ServerEvent)
        : null;
    case 'mount':
      return isObject(msg.mount) ? (msg as unknown as ServerEvent) : null;
    case 'camera':
      return isObject(msg.camera) ? (msg as unknown as ServerEvent) : null;
    case 'log':
      return typeof msg.message === 'string' && typeof msg.level === 'string' && LOG_LEVELS.has(msg.level)
        ? (msg as unknown as ServerEvent)
        : null;
    default:
      return null;
  }
}

export interface ArgosEventsOptions {
  backoff?: BackoffOptions;
  maxLogs?: number;
}

export class ArgosEvents {
  /** State of the WebSocket link itself (not of the telescope). */
  link: LinkState = $state('idle');
  // Objects are replaced wholesale on every message, so $state.raw (no deep
  // proxy) is enough and cheaper at the 4 Hz mount rate.
  connection: ConnectionState | null = $state.raw(null);
  camera: CameraState | null = $state.raw(null);
  mount: MountState | null = $state.raw(null);
  logs: LogEntry[] = $state.raw([]);
  /** performance.now() of the last message, for staleness indicators. */
  lastMessageAt: number | null = $state(null);

  private readonly socket: ReconnectingSocket;
  private readonly maxLogs: number;
  private nextLogId = 1;
  /** Keys of server log lines already received (bounded FIFO), against replays. */
  private seenLogs = new Set<string>();
  private seenOrder: string[] = [];

  constructor(config: ArgosConfig, options: ArgosEventsOptions = {}) {
    this.maxLogs = options.maxLogs ?? MAX_LOG_ENTRIES;
    this.socket = new ReconnectingSocket({
      url: withToken(`${config.wsBase}/ws/events`, config.token),
      backoff: options.backoff,
      onMessage: (data) => this.handle(data),
      onState: (state) => {
        this.link = state;
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
  }

  /** Add a client-side entry to the log (e.g. a failed REST call). */
  pushLog(level: LogLevel, message: string, t: string = new Date().toISOString()): void {
    const entry: LogEntry = { level, message, t, id: this.nextLogId++ };
    const keep = this.logs.length >= this.maxLogs ? this.logs.slice(1 - this.maxLogs) : this.logs;
    this.logs = [...keep, entry];
  }

  clearLogs(): void {
    this.logs = [];
  }

  private handle(data: unknown): void {
    const msg = parseEventMessage(data);
    if (!msg) return;
    this.lastMessageAt = performance.now();
    switch (msg.type) {
      case 'status':
        this.connection = msg.connection;
        this.camera = msg.camera;
        this.mount = msg.mount;
        break;
      case 'mount':
        this.mount = msg.mount;
        break;
      case 'camera':
        this.camera = msg.camera;
        break;
      case 'log': {
        const key = `${msg.t}\u0000${msg.level}\u0000${msg.message}`;
        if (this.seenLogs.has(key)) break; // replayed after a reconnection
        this.seenLogs.add(key);
        this.seenOrder.push(key);
        if (this.seenOrder.length > 2 * this.maxLogs) this.seenLogs.delete(this.seenOrder.shift()!);
        this.pushLog(msg.level, msg.message, msg.t);
        break;
      }
    }
  }
}
