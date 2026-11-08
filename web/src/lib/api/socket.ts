/**
 * A WebSocket that reconnects by itself (exponential backoff + jitter).
 *
 * Shared by the events and frames streams. The server authenticates sockets
 * with "?token=…" (browsers cannot set headers on a WebSocket) and closes
 * with code 4401 on a bad token, 4403 on a page origin it refuses: retrying
 * cannot fix either, so the socket parks in "unauthorized" / "forbidden"
 * until restart() is called.
 *
 * The server accepts a socket before closing it (so the browser sees the
 * code), and closes with 1001/1011/1013 while shutting down or overloaded:
 * an open alone is no proof of health, so the backoff only resets once the
 * socket has delivered a message.
 */

/** Close code the ARGOS server uses for a missing/wrong token. */
export const WS_UNAUTHORIZED = 4401;
/** Close code for a page origin (or Host) the server refuses. */
export const WS_FORBIDDEN = 4403;

export type LinkState =
  | 'idle' // never started, or stopped by the caller
  | 'connecting' // first attempt in flight
  | 'open'
  | 'reconnecting' // waiting for / running a retry after a drop
  | 'unauthorized' // server rejected the token: no automatic retry
  | 'forbidden'; // server refused this page's origin: no automatic retry

export interface BackoffOptions {
  /** First retry delay. */
  initialMs: number;
  /** Ceiling of the delay. */
  maxMs: number;
  /** Growth per failed attempt. */
  factor: number;
  /** +/- fraction of random spread, so clients do not retry in lockstep. */
  jitter: number;
}

export const DEFAULT_BACKOFF: BackoffOptions = {
  initialMs: 500,
  maxMs: 10_000,
  factor: 2,
  jitter: 0.2,
};

/** Delay before retry number `attempt` (0-based). Pure, unit-tested. */
export function backoffDelay(
  attempt: number,
  options: BackoffOptions = DEFAULT_BACKOFF,
  random: () => number = Math.random,
): number {
  const base = Math.min(options.maxMs, options.initialMs * options.factor ** Math.max(0, attempt));
  const spread = base * options.jitter * (2 * random() - 1);
  return Math.max(0, Math.round(base + spread));
}

/** Append the token query parameter to a ws:// URL. */
export function withToken(url: string, token: string): string {
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

/** Minimal structural type so tests can inject a fake. */
export interface WebSocketLike {
  binaryType: BinaryType;
  readonly readyState: number;
  onopen: ((ev: Event) => unknown) | null;
  onclose: ((ev: CloseEvent) => unknown) | null;
  onerror: ((ev: Event) => unknown) | null;
  onmessage: ((ev: MessageEvent) => unknown) | null;
  close(code?: number, reason?: string): void;
  /** Optional in test fakes: the client messages of /ws/events (wave 3 `jog_stop`). */
  send?(data: string): void;
}

export type WebSocketFactory = (url: string) => WebSocketLike;

export interface ReconnectingSocketOptions {
  url: string;
  binaryType?: BinaryType;
  backoff?: BackoffOptions;
  onMessage: (data: unknown) => void;
  onState?: (state: LinkState, detail?: { code?: number; reason?: string }) => void;
  /** Injected for tests; defaults to the browser WebSocket. */
  createSocket?: WebSocketFactory;
  /** Injected for tests; defaults to setTimeout/clearTimeout. */
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

export class ReconnectingSocket {
  private readonly opts: ReconnectingSocketOptions;
  private socket: WebSocketLike | null = null;
  private timer: unknown = null;
  private attempt = 0;
  private wanted = false;
  private _state: LinkState = 'idle';

  constructor(options: ReconnectingSocketOptions) {
    this.opts = options;
  }

  get state(): LinkState {
    return this._state;
  }

  /** Start (or keep) the connection alive. Idempotent. */
  start(): void {
    if (this.wanted) return;
    this.wanted = true;
    this.attempt = 0;
    this.open('connecting');
  }

  /** Close and stop retrying. */
  stop(): void {
    this.wanted = false;
    this.clearRetry();
    this.dropSocket();
    this.setState('idle');
  }

  /**
   * Send one text message on the open socket (wave 3: `{"type":"jog_stop"}`).
   * Returns false when no socket is open: the caller has an HTTP path too.
   */
  send(data: string): boolean {
    const ws = this.socket;
    if (!ws || this._state !== 'open' || typeof ws.send !== 'function') return false;
    try {
      ws.send(data);
      return true;
    } catch {
      return false;
    }
  }

  /** Stop then start again (e.g. after the token was fixed). */
  restart(): void {
    this.stop();
    this.start();
  }

  private open(phase: 'connecting' | 'reconnecting'): void {
    this.setState(phase);
    const create = this.opts.createSocket ?? ((url: string) => new WebSocket(url));
    let ws: WebSocketLike;
    try {
      ws = create(this.opts.url);
    } catch {
      // Malformed URL or a browser refusing the socket: treat as a drop.
      this.scheduleRetry();
      return;
    }
    ws.binaryType = this.opts.binaryType ?? 'blob';
    this.socket = ws;

    ws.onopen = () => {
      if (this.socket !== ws) return;
      this.setState('open');
    };
    ws.onmessage = (ev) => {
      if (this.socket !== ws) return;
      this.attempt = 0; // a working link, not just an accepted socket
      this.opts.onMessage(ev.data);
    };
    ws.onerror = () => {
      // Always followed by onclose; nothing to do here.
    };
    ws.onclose = (ev) => {
      if (this.socket !== ws) return;
      this.socket = null;
      if (!this.wanted) return;
      if (ev.code === WS_UNAUTHORIZED || ev.code === WS_FORBIDDEN) {
        this.wanted = false;
        const state = ev.code === WS_UNAUTHORIZED ? 'unauthorized' : 'forbidden';
        this.setState(state, { code: ev.code, reason: ev.reason });
        return;
      }
      this.scheduleRetry(ev.code, ev.reason);
    };
  }

  private scheduleRetry(code?: number, reason?: string): void {
    this.clearRetry();
    const delay = backoffDelay(this.attempt, this.opts.backoff ?? DEFAULT_BACKOFF);
    this.attempt += 1;
    this.setState('reconnecting', { code, reason });
    const setTimer = this.opts.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
    this.timer = setTimer(() => {
      this.timer = null;
      if (this.wanted) this.open('reconnecting');
    }, delay);
  }

  private clearRetry(): void {
    if (this.timer === null) return;
    const clearTimer = this.opts.clearTimer ?? ((h: unknown) => clearTimeout(h as number));
    clearTimer(this.timer);
    this.timer = null;
  }

  private dropSocket(): void {
    const ws = this.socket;
    this.socket = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      try {
        ws.close(1000, 'client stop');
      } catch {
        // Already closing: ignore.
      }
    }
  }

  private setState(state: LinkState, detail?: { code?: number; reason?: string }): void {
    if (state === this._state && !detail) return;
    this._state = state;
    this.opts.onState?.(state, detail);
  }
}
