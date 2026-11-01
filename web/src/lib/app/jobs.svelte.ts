/**
 * Reactive jobs (README 4.2): the reducer of jobs.ts behind $state.
 *
 *   const jobs = new JobStore({ cancel: (id) => client.request('DELETE', `/api/jobs/${id}`) });
 *   jobs.ingest(msg)           // a /ws/events "job" message
 *   jobs.snapshot(answer.jobs) // GET /api/jobs after (re)connecting
 *   jobs.latest('discovery')   // the job a screen shows inline
 *   await jobs.cancel(id)      // DELETE /api/jobs/{id}; the final state comes as an event
 */

import {
  EMPTY_JOBS,
  type Job,
  type JobAction,
  type JobEntry,
  type JobsState,
  activeJobs,
  jobList,
  jobsReducer,
  latestOfKind,
  parseJob,
} from './jobs';

export interface JobStoreOptions {
  /** Sends the cancel request; resolves with the server's Job, rejects on failure. */
  cancel?: (id: string) => Promise<unknown>;
}

export class JobStore {
  state: JobsState = $state.raw(EMPTY_JOBS);
  private readonly cancelRequest: ((id: string) => Promise<unknown>) | null;

  constructor(options: JobStoreOptions = {}) {
    this.cancelRequest = options.cancel ?? null;
  }

  dispatch(action: JobAction): void {
    this.state = jobsReducer(this.state, action);
  }

  /** A WS `job` event (or a bare Job). Returns the parsed job, or null. */
  ingest(raw: unknown): Job | null {
    const job = parseJob(raw);
    if (job) this.dispatch({ type: 'event', job });
    return job;
  }

  /** The seq of every held job, taken when GET /api/jobs is sent (see `snapshot`). */
  marks(): Record<string, number> {
    const out: Record<string, number> = {};
    for (const [id, job] of Object.entries(this.state.byId)) out[id] = job.seq;
    return out;
  }

  /**
   * The answer of GET /api/jobs. Pass the `marks()` taken when it was sent:
   * a job whose WS event arrived meanwhile is never declared lost by an
   * answer older than that event.
   */
  snapshot(jobs: readonly unknown[], before?: Record<string, number>): void {
    const parsed = jobs.map(parseJob).filter((j): j is Job => j !== null);
    this.dispatch({ type: 'snapshot', jobs: parsed, before });
  }

  get(id: string): JobEntry | null {
    return this.state.byId[id] ?? null;
  }

  latest(kind: string): JobEntry | null {
    return latestOfKind(this.state, kind);
  }

  get all(): JobEntry[] {
    return jobList(this.state);
  }

  get active(): JobEntry[] {
    return activeJobs(this.state);
  }

  get canCancel(): boolean {
    return this.cancelRequest !== null;
  }

  async cancel(id: string): Promise<void> {
    const job = this.get(id);
    if (!job || !this.cancelRequest) return;
    this.dispatch({ type: 'cancel-requested', id });
    try {
      const answer = await this.cancelRequest(id);
      const echoed = parseJob(answer);
      if (echoed) this.dispatch({ type: 'event', job: echoed });
    } catch (err) {
      this.dispatch({
        type: 'cancel-failed',
        id,
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }

  dismiss(id: string): void {
    this.dispatch({ type: 'dismiss', id });
  }
}
