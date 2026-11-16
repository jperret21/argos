/**
 * The desktop app's two routes (W8; web/spec/README.md section 4.3, rows A7 and A12;
 * 01 sections 1.14, 2.3.7 and 2.5):
 *
 * - A7 `POST /api/app/shutdown` `{force}`: `202` the server shuts down (WS `shutdown`
 *   events carry the stages, then the link closes); `409 busy` with the list of what runs
 *   (`what`) unless `force`; nothing is stopped by a refused request.
 * - A12 `POST /api/fs/reveal` `{path}`: the server shows the file or folder in the file
 *   manager of this computer (Finder on macOS). Desktop app only: the UI never offers it
 *   in a browser tab.
 *
 * The server's contract: argos/server/protocol.md "Desktop app (wave 8)" (BusyItem
 * `{kind: run|exposure|slew|job|write, text, job_id, job_kind}`, ShutdownStarted
 * `{state, forced, what, stages: [{id, label}], budget_s}`, the event
 * `{type: "shutdown", stage, label, index, count, forced, budget_s, t}`; reveal answers
 * `{path, method}`, `403 desktop_only` from a server the shell did not start). Read
 * tolerantly all the same: `what` from `error.what` or `error.details.what`, an item may be
 * a bare kind; a route the server does not have (FastAPI's own `404 Not Found`) is
 * "unsupported", and the callers fall back (the quit flow checks what the UI sees running,
 * reveal goes through the shell).
 */

import { ApiError, BAD_RESPONSE, NETWORK_ERROR, TIMEOUT, type ArgosClient, type RequestOptions } from './client';

/** One thing that runs and that quitting would stop. */
export interface BusyItem {
  /**
   * Normalised kind: sequence (the server's `run`), exposure, live, autofocus, slew, write
   * (a FITS being written), or the job's own kind for `job` / `write` items (solve, rerun,
   * export, support_bundle, discovery, …).
   */
  kind: string;
  /** The server's own words for it, when it sent any. */
  label: string | null;
  /** A second line (object, frames), when known. */
  detail: string | null;
}

export type ShutdownAnswer =
  /** `202`: the server is shutting down; stages follow on /ws/events. `stages`: the plan, when sent. */
  | { outcome: 'accepted'; stages: { id: string; label: string }[]; budgetS: number | null }
  /** `409 busy`: nothing was stopped; `items` lists what runs. */
  | { outcome: 'busy'; items: BusyItem[]; message: string }
  /** The server has no A7 (older than W8). */
  | { outcome: 'unsupported' }
  /** No answer at all: the server is gone (or not answering). */
  | { outcome: 'unreachable'; message: string };

/** One stage of the server's shutdown (WS `{"type": "shutdown", "stage", "t"}`). */
export interface ShutdownEvent {
  stage: string;
  /** The server's words for the stage, when it sent any (`label`, `text` or `message`). */
  label: string | null;
  /** Server time (epoch s), when sent. */
  t: number | null;
  /** 1-based position of the stage and the number of stages, when sent. */
  index: number | null;
  count: number | null;
  /** The last stage: the server is about to exit. */
  done: boolean;
}

type Requester = Pick<ArgosClient, 'request'>;

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v.trim() : null;
}

/** Kinds the server (or the busy summary of 01 2.5) may spell differently. */
const KIND_ALIASES: Record<string, string> = {
  run: 'sequence',
  sequencer: 'sequence',
  exposing: 'exposure',
  downloading: 'exposure',
  capture: 'exposure',
  single: 'exposure',
  live_view: 'live',
  slewing: 'slew',
  goto: 'slew',
  solving: 'solve',
  field_solve: 'solve',
  file_solve: 'solve',
  plate_solve: 'solve',
  batch: 'rerun',
  focus: 'focuser',
  filter_wheel: 'filterwheel',
  wheel: 'filterwheel',
};

export function normaliseKind(kind: string): string {
  const k = kind.trim().toLowerCase().replace(/[\s-]+/g, '_');
  return KIND_ALIASES[k] ?? k;
}

/** One `what` entry: a kind, or an object with a kind and words. Null when unusable. */
export function checkBusyItem(v: unknown): BusyItem | null {
  if (typeof v === 'string') return v.trim() ? { kind: normaliseKind(v), label: null, detail: null } : null;
  if (!isObj(v)) return null;
  const raw = str(v.kind) ?? str(v.id) ?? str(v.what) ?? str(v.type);
  if (!raw) return null;
  // A job (or a write job) is named by its own kind: its icon and its words.
  const kind = (raw === 'job' || raw === 'write') && str(v.job_kind) ? (str(v.job_kind) as string) : raw;
  return {
    kind: normaliseKind(kind),
    label: str(v.label) ?? str(v.text) ?? str(v.message),
    detail: str(v.detail),
  };
}

/** The `what` list of a `409 busy` body (`error.what` or `error.details.what`); exact repeats dropped. */
export function busyItemsOf(body: Record<string, unknown> | null): BusyItem[] {
  if (!body) return [];
  const raw = Array.isArray(body.what) ? body.what : isObj(body.details) && Array.isArray(body.details.what) ? body.details.what : [];
  const out: BusyItem[] = [];
  for (const v of raw) {
    const item = checkBusyItem(v);
    if (item && !out.some((o) => o.kind === item.kind && o.label === item.label)) out.push(item);
  }
  return out;
}

/** The planned stages of a ShutdownStarted body. */
function plannedStages(body: unknown): { id: string; label: string }[] {
  if (!isObj(body) || !Array.isArray(body.stages)) return [];
  const out: { id: string; label: string }[] = [];
  for (const st of body.stages) {
    const id = isObj(st) ? str(st.id) : null;
    if (id && isObj(st)) out.push({ id: id.toLowerCase(), label: str(st.label) ?? id });
  }
  return out;
}

/** A missing route: FastAPI's own 404 (the server's handler maps it to `not_found` "Not Found"). */
export function isMissingRoute(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  if (err.status === 405) return true;
  return err.status === 404 && (err.code === 'http_404' || (err.code === 'not_found' && /^not found$/i.test(err.message.trim())));
}

/** No HTTP answer: the server is gone (refused connection) or does not answer. */
function isUnreachable(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 0 && (err.code === NETWORK_ERROR || err.code === TIMEOUT);
}

/** A7: ask the server to shut down. Throws ApiError for any other refusal. */
export async function requestShutdown(client: Requester, force: boolean, options: RequestOptions = { timeoutMs: 8000 }): Promise<ShutdownAnswer> {
  try {
    const body = await client.request<unknown>('POST', '/api/app/shutdown', { force }, options);
    const budget = isObj(body) && typeof body.budget_s === 'number' && body.budget_s > 0 ? body.budget_s : null;
    return { outcome: 'accepted', stages: plannedStages(body), budgetS: budget };
  } catch (err) {
    // `202` with an empty body is still an acceptance.
    if (err instanceof ApiError && err.code === BAD_RESPONSE && err.status >= 200 && err.status < 300) return { outcome: 'accepted', stages: [], budgetS: null };
    if (err instanceof ApiError && err.status === 409 && err.code === 'busy') {
      return { outcome: 'busy', items: busyItemsOf(err.body), message: err.message };
    }
    // A second request while the first one runs: the shutdown is under way.
    if (err instanceof ApiError && (err.status === 409 || err.status === 503) && (err.code === 'shutting_down' || err.code === 'stopping')) {
      return { outcome: 'accepted', stages: [], budgetS: null };
    }
    if (isMissingRoute(err)) return { outcome: 'unsupported' };
    if (isUnreachable(err)) return { outcome: 'unreachable', message: err.message };
    throw err;
  }
}

/** One WS `shutdown` message, or null when it is not one. */
export function checkShutdownEvent(msg: unknown): ShutdownEvent | null {
  if (!isObj(msg) || msg.type !== 'shutdown') return null;
  const stage = str(msg.stage);
  if (!stage) return null;
  const id = stage.toLowerCase();
  const iso = typeof msg.t === 'string' ? Date.parse(msg.t) / 1000 : NaN;
  const int = (v: unknown) => (typeof v === 'number' && Number.isInteger(v) && v > 0 ? v : null);
  return {
    stage: id,
    label: str(msg.label) ?? str(msg.text) ?? str(msg.message),
    t: typeof msg.t === 'number' && Number.isFinite(msg.t) ? msg.t : Number.isFinite(iso) ? iso : null,
    index: int(msg.index),
    count: int(msg.count),
    done: msg.done === true || id === 'done' || id === 'stopped' || id === 'exit',
  };
}

export type RevealAnswer = 'revealed' | 'unsupported';

/**
 * A12: show `path` in the file manager. Throws ApiError with the server's words
 * (`not_found`, `forbidden_path`, `reveal_failed`); "unsupported" when the server has no
 * A12 or was not started by the shell (`403 desktop_only`, e.g. a development server).
 */
export async function revealPath(client: Requester, path: string, options: RequestOptions = { timeoutMs: 8000 }): Promise<RevealAnswer> {
  try {
    await client.request<unknown>('POST', '/api/fs/reveal', { path }, options);
    return 'revealed';
  } catch (err) {
    // `204 No Content` is a success with no JSON.
    if (err instanceof ApiError && err.code === BAD_RESPONSE && err.status >= 200 && err.status < 300) return 'revealed';
    if (isMissingRoute(err) || (err instanceof ApiError && err.code === 'desktop_only')) return 'unsupported';
    throw err;
  }
}
