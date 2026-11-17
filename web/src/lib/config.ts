/**
 * Where the ARGOS server lives and how to authenticate against it.
 *
 * Resolution order (first hit wins), so a browser tab, `vite dev` and the
 * future Tauri shell can all point the UI at a server without a rebuild:
 *   1. page URL query: ?api=http://127.0.0.1:8742&token=dev
 *   2. build/dev env:  VITE_ARGOS_API / VITE_ARGOS_TOKEN
 *   3. default:        http://127.0.0.1:8742 and no token
 * The API and the token are resolved independently (e.g. API from the env,
 * token from the query), with one guard: a query `api` naming a host other
 * than this machine is ignored unless the token comes from the query too, so
 * a crafted link cannot send the build's own token to another host.
 */

export const DEFAULT_API_BASE = 'http://127.0.0.1:8742';

export interface ArgosConfig {
  /** HTTP base URL, no trailing slash, e.g. "http://127.0.0.1:8742". */
  apiBase: string;
  /** WebSocket base URL derived from apiBase ("ws://…" or "wss://…"). */
  wsBase: string;
  /** Bearer token ("" when none was given: every authenticated call will 401). */
  token: string;
  /** Where each value came from, for diagnostics in the UI. */
  source: { api: ConfigSource; token: ConfigSource };
}

export type ConfigSource = 'query' | 'env' | 'default';

export interface ConfigEnv {
  VITE_ARGOS_API?: string;
  VITE_ARGOS_TOKEN?: string;
}

/**
 * Normalise an API base URL: http(s) only, no path/query/fragment, no trailing
 * slash. Returns null for anything unusable so the caller can fall back.
 */
export function normalizeApiBase(raw: string | null | undefined): string | null {
  const text = raw?.trim();
  if (!text) return null;
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  // The server mounts its routes at /api and /ws from the root, so any path is
  // a user mistake (e.g. a pasted ".../api/health"): keep scheme://host:port.
  return `${url.protocol}//${url.host}`;
}

/** True for a base URL on this machine (127.0.0.1, localhost, [::1]). */
export function isLoopbackBase(base: string): boolean {
  try {
    const host = new URL(base).hostname;
    return host === '127.0.0.1' || host === 'localhost' || host === '[::1]' || host === '::1';
  } catch {
    return false;
  }
}

/** "http://h:p" -> "ws://h:p", "https://h:p" -> "wss://h:p". */
export function toWsBase(apiBase: string): string {
  return apiBase.replace(/^http(s?):\/\//, (_m, s: string) => `ws${s}://`);
}

/** Pure resolver (unit-tested): `search` is a location.search string. */
export function resolveConfig(search: string, env: ConfigEnv = {}): ArgosConfig {
  const params = new URLSearchParams(search);
  const queryToken = params.get('token')?.trim() ?? '';

  let api: string | null = normalizeApiBase(params.get('api'));
  if (api !== null && !queryToken && !isLoopbackBase(api)) api = null;
  let apiSource: ConfigSource = 'query';
  if (api === null) {
    api = normalizeApiBase(env.VITE_ARGOS_API);
    apiSource = 'env';
  }
  if (api === null) {
    api = DEFAULT_API_BASE;
    apiSource = 'default';
  }

  let token = queryToken;
  let tokenSource: ConfigSource = 'query';
  if (!token) {
    token = env.VITE_ARGOS_TOKEN?.trim() ?? '';
    tokenSource = token ? 'env' : 'default';
  }

  return {
    apiBase: api,
    wsBase: toWsBase(api),
    token,
    source: { api: apiSource, token: tokenSource },
  };
}

/** Config for the running page (query string + Vite env). */
export function loadConfig(): ArgosConfig {
  const search = typeof location === 'undefined' ? '' : location.search;
  return resolveConfig(search, {
    VITE_ARGOS_API: import.meta.env.VITE_ARGOS_API,
    VITE_ARGOS_TOKEN: import.meta.env.VITE_ARGOS_TOKEN,
  });
}
