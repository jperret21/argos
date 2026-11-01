/**
 * Typed REST client for the ARGOS server.
 *
 * Every call sends the bearer token (except /api/health, which the server
 * leaves open so the UI can tell "server down" from "bad token"). Failures of
 * any kind surface as one error type, ApiError, so callers only need a single
 * catch branch: HTTP errors carry the server's {"error": {code, message}},
 * transport problems use the synthetic codes below with status 0.
 */

import type { ArgosConfig } from '../config';
import type {
  CameraState,
  ConnectRequest,
  ConnectionState,
  ErrorBody,
  ExposureRequest,
  Health,
  MountState,
  Status,
} from './types';

/** Synthetic codes for failures that never reached a server answer. */
export const NETWORK_ERROR = 'network_error';
export const TIMEOUT = 'timeout';
export const ABORTED = 'aborted';
export const BAD_RESPONSE = 'bad_response';

export class ApiError extends Error {
  /** HTTP status, or 0 when the request never got an HTTP answer. */
  readonly status: number;
  /** Server error code (snake_case, e.g. "not_connected") or a synthetic one. */
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }
}

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== 'object' || value === null) return false;
  const err = (value as { error?: unknown }).error;
  return (
    typeof err === 'object' &&
    err !== null &&
    typeof (err as { code?: unknown }).code === 'string' &&
    typeof (err as { message?: unknown }).message === 'string'
  );
}

/**
 * Build an ApiError from a non-2xx response. Exported for tests: the body may
 * be the contract's JSON, some other JSON, plain text or empty (e.g. a proxy).
 */
export function errorFromResponse(status: number, statusText: string, bodyText: string): ApiError {
  let parsed: unknown = undefined;
  try {
    parsed = bodyText ? JSON.parse(bodyText) : undefined;
  } catch {
    parsed = undefined;
  }
  if (isErrorBody(parsed)) {
    return new ApiError(status, parsed.error.code, parsed.error.message);
  }
  const fallbackCode = status === 401 ? 'unauthorized' : `http_${status}`;
  const message = bodyText.trim().slice(0, 200) || statusText || `HTTP ${status}`;
  return new ApiError(status, fallbackCode, message);
}

export interface RequestOptions {
  /** Abort after this many milliseconds (default: client default). */
  timeoutMs?: number;
  /** External cancellation (e.g. component unmount). */
  signal?: AbortSignal;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface ClientOptions {
  /** Default per-request timeout. */
  timeoutMs?: number;
  /** Injected fetch (tests). */
  fetch?: FetchLike;
}

export class ArgosClient {
  private readonly config: ArgosConfig;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchLike;

  constructor(config: ArgosConfig, options: ClientOptions = {}) {
    this.config = config;
    this.timeoutMs = options.timeoutMs ?? 15_000;
    this.fetchImpl = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  }

  /** Low-level typed request. `path` starts with "/api/". */
  async request<T>(
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    path: string,
    body?: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (path !== '/api/health') headers.Authorization = `Bearer ${this.config.token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    const timeoutMs = options.timeoutMs ?? this.timeoutMs;
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const onExternalAbort = () => controller.abort();
    options.signal?.addEventListener('abort', onExternalAbort, { once: true });

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.config.apiBase}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (err) {
      if (timedOut) throw new ApiError(0, TIMEOUT, `No answer from the server after ${timeoutMs} ms`);
      if (options.signal?.aborted) throw new ApiError(0, ABORTED, 'Request cancelled');
      const detail = err instanceof Error ? err.message : String(err);
      throw new ApiError(0, NETWORK_ERROR, `Cannot reach the ARGOS server at ${this.config.apiBase} (${detail})`);
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', onExternalAbort);
    }

    const text = await response.text();
    if (!response.ok) throw errorFromResponse(response.status, response.statusText, text);
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError(response.status, BAD_RESPONSE, `Invalid JSON from ${method} ${path}`);
    }
  }

  // -- Server ---------------------------------------------------------------

  health(options?: RequestOptions): Promise<Health> {
    return this.request('GET', '/api/health', undefined, options);
  }

  status(options?: RequestOptions): Promise<Status> {
    return this.request('GET', '/api/status', undefined, options);
  }

  // -- Connection -----------------------------------------------------------

  connect(body: ConnectRequest, options?: RequestOptions): Promise<ConnectionState> {
    // Alpaca discovery + handshake can take a while on a field Wi-Fi.
    return this.request('POST', '/api/connection', body, { timeoutMs: 60_000, ...options });
  }

  connectSimulator(options?: RequestOptions): Promise<ConnectionState> {
    return this.connect({ mode: 'simulator' }, options);
  }

  disconnect(options?: RequestOptions): Promise<ConnectionState> {
    return this.request('DELETE', '/api/connection', undefined, options);
  }

  // -- Camera ---------------------------------------------------------------

  capture(body: ExposureRequest, options?: RequestOptions): Promise<CameraState> {
    return this.request('POST', '/api/camera/capture', body, options);
  }

  startLive(body: ExposureRequest, options?: RequestOptions): Promise<CameraState> {
    return this.request('POST', '/api/camera/live', body, options);
  }

  /**
   * Change the running live view's exposure and gain. They apply from the next
   * frame: the answer still shows the settings of the exposure in progress, and
   * a `camera` event follows when the new ones are in use (409 not_live if
   * live view is not running).
   */
  updateLive(body: ExposureRequest, options?: RequestOptions): Promise<CameraState> {
    return this.request('PATCH', '/api/camera/live', body, options);
  }

  stopCamera(options?: RequestOptions): Promise<CameraState> {
    return this.request('POST', '/api/camera/stop', undefined, options);
  }

  openFits(path: string, options?: RequestOptions): Promise<CameraState> {
    return this.request('POST', '/api/camera/open-fits', { path }, options);
  }

  // -- Mount ----------------------------------------------------------------

  goto(target: { ra_hours: number; dec_deg: number }, options?: RequestOptions): Promise<MountState> {
    return this.request('POST', '/api/mount/goto', target, options);
  }

  stopMount(options?: RequestOptions): Promise<MountState> {
    return this.request('POST', '/api/mount/stop', undefined, options);
  }

  park(options?: RequestOptions): Promise<MountState> {
    return this.request('POST', '/api/mount/park', undefined, options);
  }

  unpark(options?: RequestOptions): Promise<MountState> {
    return this.request('POST', '/api/mount/unpark', undefined, options);
  }

  setTracking(enabled: boolean, options?: RequestOptions): Promise<MountState> {
    return this.request('POST', '/api/mount/tracking', { enabled }, options);
  }
}
