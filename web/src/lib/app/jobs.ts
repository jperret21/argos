/**
 * Long-running jobs, client side (web/spec/README.md section 4.2, protocol.md
 * "Jobs (A80)"): a pure reducer over the server's `job` events and the
 * `GET /api/jobs` snapshot, plus the helpers JobProgress uses.
 *
 * Rules:
 * - A job event replaces the held record only when its `seq` is newer:
 *   events can arrive after a snapshot that already holds a later state.
 * - A cancel is optimistic in the UI only ("Cancelling…"); the server's
 *   final `cancelled` (or `done` / `failed`, when it finished first) decides.
 * - After a reconnection the snapshot is the truth: an active job the server
 *   no longer lists is marked failed ("lost"), never left spinning.
 * - Finished jobs stay until dismissed, at most MAX_FINISHED of them.
 */

export const JOB_STATES = ['queued', 'running', 'done', 'failed', 'cancelled'] as const;
export type JobPhase = (typeof JOB_STATES)[number];

export interface JobError {
  code: string;
  message: string;
}

export interface Job {
  id: string;
  kind: string;
  state: JobPhase;
  done: number;
  /** null = indeterminate. */
  total: number | null;
  stage: string | null;
  message: string | null;
  started_utc: string | null;
  ended_utc: string | null;
  result: unknown;
  error: JobError | null;
  cancellable: boolean;
  cancel_requested: boolean;
  seq: number;
}

export interface JobEntry extends Job {
  /** Cancel asked by this client, final state not received yet. */
  cancelling: boolean;
  /** The cancel request itself failed (409 unsupported, network): its message. */
  cancelError: string | null;
}

export interface JobsState {
  byId: Readonly<Record<string, JobEntry>>;
  /** Ids, oldest first. */
  order: readonly string[];
}

export type JobAction =
  | { type: 'event'; job: Job }
  /**
   * GET /api/jobs answered. `before`: the seq of each job this page held
   * when the request was sent (JobStore.marks()); absent = trust the answer
   * for every held job.
   */
  | { type: 'snapshot'; jobs: readonly Job[]; before?: Readonly<Record<string, number>> }
  | { type: 'cancel-requested'; id: string }
  | { type: 'cancel-failed'; id: string; message: string }
  | { type: 'dismiss'; id: string };

export const MAX_FINISHED = 20;

export const EMPTY_JOBS: JobsState = { byId: {}, order: [] };

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** A Job from the wire (the `job` member of a WS event, or a REST answer), or null. */
export function parseJob(raw: unknown): Job | null {
  const j = isObject(raw) && isObject(raw.job) ? raw.job : raw;
  if (!isObject(j)) return null;
  const id = str(j.id);
  const kind = str(j.kind);
  const state = str(j.state);
  if (!id || !kind || !state || !(JOB_STATES as readonly string[]).includes(state)) return null;
  let error: JobError | null = null;
  if (isObject(j.error)) {
    error = { code: str(j.error.code) ?? 'error', message: str(j.error.message) ?? 'Failed' };
  } else if (typeof j.error === 'string') {
    error = { code: 'error', message: j.error };
  }
  return {
    id,
    kind,
    state: state as JobPhase,
    done: num(j.done) ?? 0,
    total: num(j.total),
    stage: str(j.stage),
    message: str(j.message),
    started_utc: str(j.started_utc),
    ended_utc: str(j.ended_utc),
    result: j.result ?? null,
    error,
    cancellable: j.cancellable !== false,
    cancel_requested: j.cancel_requested === true,
    seq: num(j.seq) ?? 0,
  };
}

export function isActive(job: Pick<Job, 'state'>): boolean {
  return job.state === 'queued' || job.state === 'running';
}

export function isFinished(job: Pick<Job, 'state'>): boolean {
  return !isActive(job);
}

/** 0…1 when the total is known, null for an indeterminate job. */
export function progressFraction(job: Pick<Job, 'done' | 'total' | 'state'>): number | null {
  if (job.state === 'done') return 1;
  if (job.total === null || !(job.total > 0)) return null;
  return Math.min(1, Math.max(0, job.done / job.total));
}

function prune(byId: Record<string, JobEntry>, order: string[]): string[] {
  const finished = order.filter((id) => isFinished(byId[id]));
  const excess = finished.length - MAX_FINISHED;
  if (excess <= 0) return order;
  const drop = new Set(finished.slice(0, excess));
  for (const id of drop) delete byId[id];
  return order.filter((id) => !drop.has(id));
}

function applyJob(byId: Record<string, JobEntry>, order: string[], job: Job): boolean {
  const held = byId[job.id];
  if (held && job.seq <= held.seq) return false;
  const finished = isFinished(job);
  byId[job.id] = {
    ...job,
    cancelling: finished ? false : (held?.cancelling ?? false) || job.cancel_requested,
    cancelError: finished ? null : (held?.cancelError ?? null),
  };
  if (!held) order.push(job.id);
  return true;
}

export function jobsReducer(state: JobsState, action: JobAction): JobsState {
  switch (action.type) {
    case 'event': {
      const byId = { ...state.byId };
      const order = [...state.order];
      if (!applyJob(byId, order, action.job)) return state;
      return { byId, order: prune(byId, order) };
    }
    case 'snapshot': {
      const byId = { ...state.byId };
      const order = [...state.order];
      // Only a job this page held when GET /api/jobs was sent, with nothing
      // newer heard of it since, can be declared lost by its absence: a job
      // whose event arrived after the request is newer than the answer.
      const before = action.before;
      const knownAtRequest = (id: string, seq: number) =>
        before === undefined || (id in before && seq <= before[id]);
      // Oldest first, so a new job's place in `order` follows its start.
      const incoming = [...action.jobs].sort((a, b) =>
        (a.started_utc ?? '').localeCompare(b.started_utc ?? ''),
      );
      const listed = new Set(incoming.map((j) => j.id));
      for (const job of incoming) applyJob(byId, order, job);
      for (const id of order) {
        const held = byId[id];
        if (held && isActive(held) && !listed.has(id) && knownAtRequest(id, held.seq)) {
          byId[id] = {
            ...held,
            state: 'failed',
            cancelling: false,
            ended_utc: held.ended_utc ?? new Date().toISOString(),
            error: {
              code: 'lost',
              message: 'The server no longer knows this job (it was restarted or the job expired).',
            },
          };
        }
      }
      return { byId, order: prune(byId, order) };
    }
    case 'cancel-requested': {
      const held = state.byId[action.id];
      if (!held || !isActive(held) || held.cancelling) return state;
      return { ...state, byId: { ...state.byId, [action.id]: { ...held, cancelling: true, cancelError: null } } };
    }
    case 'cancel-failed': {
      const held = state.byId[action.id];
      if (!held) return state;
      return {
        ...state,
        byId: { ...state.byId, [action.id]: { ...held, cancelling: false, cancelError: action.message } },
      };
    }
    case 'dismiss': {
      const held = state.byId[action.id];
      if (!held || isActive(held)) return state;
      const byId = { ...state.byId };
      delete byId[action.id];
      return { byId, order: state.order.filter((id) => id !== action.id) };
    }
  }
}

/** Jobs, oldest first. */
export function jobList(state: JobsState): JobEntry[] {
  return state.order.map((id) => state.byId[id]).filter(Boolean);
}

/** The newest job of a kind (the one a screen shows inline), or null. */
export function latestOfKind(state: JobsState, kind: string): JobEntry | null {
  for (let i = state.order.length - 1; i >= 0; i--) {
    const job = state.byId[state.order[i]];
    if (job?.kind === kind) return job;
  }
  return null;
}

export function activeJobs(state: JobsState): JobEntry[] {
  return jobList(state).filter(isActive);
}

/** Elapsed or total time of a job, "12 s", "3m 05s" (BRAND 5 durations). */
export function jobDuration(job: Pick<Job, 'started_utc' | 'ended_utc'>, now: number = Date.now()): string | null {
  const start = job.started_utc ? Date.parse(job.started_utc) : NaN;
  if (!Number.isFinite(start)) return null;
  const end = job.ended_utc ? Date.parse(job.ended_utc) : now;
  const s = Math.max(0, Math.round((end - start) / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, '0')}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
}
