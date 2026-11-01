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
  AppInfo,
  CameraState,
  ConfigPatchResult,
  ConfigSnapshot,
  ConfigValue,
  ConnectRequest,
  ConnectionState,
  DeviceConnectBody,
  DeviceId,
  DevicesState,
  DiscoveryBody,
  ErrorBody,
  ExposureRequest,
  Health,
  JobWire,
  LogPage,
  MountState,
  NetworkState,
  ProfilesState,
  Status,
  StellariumState,
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
  /** API 2: per-key messages of a refused `PATCH /api/config`. */
  readonly fields: Record<string, string> | null;
  /** API 2: id of the job holding the resource (`409 busy` on a job start). */
  readonly owner: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    extra: { fields?: Record<string, string> | null; owner?: string | null } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = extra.fields ?? null;
    this.owner = extra.owner ?? null;
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
    const { fields, owner } = parsed.error;
    return new ApiError(status, parsed.error.code, parsed.error.message, {
      fields: fields && typeof fields === 'object' ? fields : null,
      owner: typeof owner === 'string' ? owner : null,
    });
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
    method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
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

  // -- API 2: application, log, configuration --------------------------------

  appInfo(options?: RequestOptions): Promise<AppInfo> {
    return this.request('GET', '/api/app/info', undefined, options);
  }

  /** Log lines with `seq > after`, oldest first (protocol.md A2). */
  logs(query: { after?: number; limit?: number; level?: string } = {}, options?: RequestOptions): Promise<LogPage> {
    const q = new URLSearchParams();
    if (query.after !== undefined) q.set('after', String(Math.max(0, Math.floor(query.after))));
    if (query.limit !== undefined) q.set('limit', String(Math.floor(query.limit)));
    if (query.level) q.set('level', query.level);
    const qs = q.toString();
    return this.request('GET', `/api/logs${qs ? `?${qs}` : ''}`, undefined, options);
  }

  getConfig(options?: RequestOptions): Promise<ConfigSnapshot> {
    return this.request('GET', '/api/config', undefined, options);
  }

  /** One validated, all-or-nothing commit (400 with `fields` when a key is refused). */
  patchConfig(changes: Record<string, ConfigValue>, options?: RequestOptions): Promise<ConfigPatchResult> {
    return this.request('PATCH', '/api/config', changes, options);
  }

  // -- API 2: devices (A13-A15) ----------------------------------------------

  devices(options?: RequestOptions): Promise<DevicesState> {
    return this.request('GET', '/api/devices', undefined, options);
  }

  /**
   * Connect one device. The server answers once that device is connected or
   * failed (≤ connect-timeout + 10 s on Alpaca; it never blocks the other
   * routes meanwhile).
   */
  connectDevice(id: DeviceId, body?: DeviceConnectBody, options?: RequestOptions): Promise<DevicesState> {
    return this.request('POST', `/api/devices/${id}/connect`, body, { timeoutMs: 45_000, ...options });
  }

  disconnectDevice(id: DeviceId, options?: RequestOptions): Promise<DevicesState> {
    return this.request('DELETE', `/api/devices/${id}`, undefined, { timeoutMs: 30_000, ...options });
  }

  /** Connect the four devices in order, skipping those already connected; 200 with every state. */
  connectAll(body?: DeviceConnectBody, options?: RequestOptions): Promise<DevicesState> {
    return this.request('POST', '/api/devices/connect-all', body, { timeoutMs: 120_000, ...options });
  }

  disconnectAll(options?: RequestOptions): Promise<DevicesState> {
    return this.request('DELETE', '/api/devices', undefined, { timeoutMs: 30_000, ...options });
  }

  // -- API 2: discovery (A16), profiles (A17), network (A18), jobs (A80) ------

  /** Starts a cancellable `discovery` job (409 busy with `owner` while one runs). */
  startDiscovery(body?: DiscoveryBody, options?: RequestOptions): Promise<{ job_id: string; job: JobWire }> {
    return this.request('POST', '/api/discovery', body, options);
  }

  profiles(options?: RequestOptions): Promise<ProfilesState> {
    return this.request('GET', '/api/profiles', undefined, options);
  }

  /** 409 busy while a device is connected (the message says why). */
  setProfile(key: string, options?: RequestOptions): Promise<ProfilesState> {
    return this.request('PUT', '/api/profile', { key }, options);
  }

  network(options?: RequestOptions): Promise<NetworkState> {
    return this.request('GET', '/api/network', undefined, options);
  }

  /** Re-probe the Seestar; with `internet: true`, also check the internet (on demand only, Q-G13). */
  checkNetwork(internet = false, options?: RequestOptions): Promise<NetworkState> {
    return this.request('POST', '/api/network/check', { internet }, { timeoutMs: 20_000, ...options });
  }

  jobs(options?: RequestOptions): Promise<{ jobs: JobWire[] }> {
    return this.request('GET', '/api/jobs', undefined, options);
  }

  job(id: string, options?: RequestOptions): Promise<JobWire> {
    return this.request('GET', `/api/jobs/${encodeURIComponent(id)}`, undefined, options);
  }

  /** Asks for a cancel; the final `cancelled` state follows on /ws/events. */
  cancelJob(id: string, options?: RequestOptions): Promise<JobWire> {
    return this.request('DELETE', `/api/jobs/${encodeURIComponent(id)}`, undefined, options);
  }

  // -- API 2: Stellarium bridge (A19) ----------------------------------------------

  stellarium(options?: RequestOptions): Promise<StellariumState> {
    return this.request('GET', '/api/stellarium', undefined, options);
  }

  /** Start listening (host and port default to the config); 502 bind_failed with the reason. */
  startStellarium(body: { host?: string; port?: number } = {}, options?: RequestOptions): Promise<StellariumState> {
    return this.request('POST', '/api/stellarium', body, options);
  }

  stopStellarium(options?: RequestOptions): Promise<StellariumState> {
    return this.request('DELETE', '/api/stellarium', undefined, options);
  }
}
