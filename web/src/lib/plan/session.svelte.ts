/**
 * The Plan screen's long-lived state, one per app (kept across section changes, so a
 * looked-up planet or an open draft survive a visit to Observe): the plan store, the transit
 * planner, the run (the app's SequenceStore when it has one, else one held here) and the
 * visibility of the observation's target for the night shown.
 *
 *   const s = planSession(app);   // the same object on every mount
 *   await s.refresh();             // on mount and after a reconnection
 */

import { ApiError } from '../api/client';
import { PlanApi } from '../api/plan';
import { sequenceApi, type Visibility } from '../api/sequence';
import type { ArgosApp } from '../app/state.svelte';
import type { VisibilityEmpty } from '../charts/VisibilityTimeline.svelte';
import { SequenceStore } from '../run/sequence.svelte';
import { nightOf } from './model';
import { PlanStore } from './plan.svelte';
import { TransitPlanner } from './transit.svelte';

export class PlanSession {
  readonly api: PlanApi;
  readonly store: PlanStore;
  readonly transit: TransitPlanner;
  readonly run: SequenceStore;
  /** Visibility of the target over the night shown (A65), or why there is none. */
  vis: Visibility | null = $state.raw(null);
  visEmpty: VisibilityEmpty | null = $state.raw({ kind: 'source' });
  private visKey = '';
  private visCtl: AbortController | null = null;

  constructor(private readonly app: ArgosApp) {
    this.api = new PlanApi(app.client);
    // The run is the app's (one store for Plan, the Run card, the status bar and the palette);
    // a test app without one gets its own on the same events.
    const shared = (app as { sequence?: SequenceStore }).sequence;
    if (shared) {
      this.run = shared;
    } else {
      this.run = new SequenceStore();
      this.run.attach(app.events, app.client);
    }
    this.store = new PlanStore(this.api, () => this.run.state);
    this.store.attach(app.events);
    this.transit = new TransitPlanner(this.api);
  }

  async refresh(): Promise<void> {
    await Promise.all([this.store.load(), this.store.loadPresets(), this.run.loadPreflight(this.app.client), this.readRun()]);
  }

  /** The run's snapshot (A63 `GET /api/sequence`): a page opened mid-run, or after one, shows it at once. */
  private async readRun(): Promise<void> {
    try {
      this.run.ingest(await this.app.client.request<unknown>('GET', '/api/sequence'));
    } catch {
      /* the `sequence` event brings it too */
    }
  }

  /**
   * The visibility of (ra, dec) over `night` (the transit's night, else tonight: before
   * local noon still last night, Q-P6 / P3). No site: no curve, the reason (P4).
   */
  async loadVisibility(target: { ra_hours: number; dec_deg: number } | null, night: string | null): Promise<void> {
    if (!target) {
      this.visKey = '';
      this.vis = null;
      this.visEmpty = { kind: 'source' };
      return;
    }
    const n = night ?? nightOf(new Date());
    const key = `${target.ra_hours.toFixed(5)}|${target.dec_deg.toFixed(4)}|${n}`;
    if (key === this.visKey && this.vis) return;
    this.visKey = key;
    this.visCtl?.abort();
    const ctl = new AbortController();
    this.visCtl = ctl;
    this.visEmpty = { kind: 'loading' };
    try {
      const v = await sequenceApi.visibility(this.app.client, { ra_hours: target.ra_hours, dec_deg: target.dec_deg, night: n, step_min: 10 }, { signal: ctl.signal });
      if (ctl.signal.aborted) return;
      this.vis = v;
      this.visEmpty = v ? null : { kind: 'error', message: 'The server sent no usable altitudes for this night.' };
    } catch (err) {
      if (ctl.signal.aborted) return;
      this.vis = null;
      this.visKey = '';
      const site = err instanceof ApiError && err.code === 'site_missing';
      this.visEmpty = site ? { kind: 'site', message: err.message } : { kind: 'error', message: err instanceof Error ? err.message : String(err) };
    }
  }
}

const sessions = new WeakMap<ArgosApp, PlanSession>();

export function planSession(app: ArgosApp): PlanSession {
  let s = sessions.get(app);
  if (!s) {
    s = new PlanSession(app);
    sessions.set(app, s);
  }
  return s;
}
