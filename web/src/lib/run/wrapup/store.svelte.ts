/**
 * The last run's wrap-up on the client (wave 6b, D2): the `wrapup` of each `sequence`
 * record (null at the moment a run ends, then the record once the last points are
 * measured; kept until the next Start), and `GET /api/sequence/wrapup` after a
 * (re)connection. One instance in the app state; the Run card's ended branch reads it.
 *
 *   const wrap = new WrapUpStore();
 *   const off = wrap.attach(events, client);
 *   await wrap.refresh();                      // after each (re)connection
 *   wrap.view;                                 // WrapUpView | null
 *   const { replaced } = await wrap.prepare(); // POST /api/sequence/calibration-plan
 */

import type { SequencePlan } from '../../api/plan';
import { checkWrapUp, wrapupApi, type WrapClient, type WrapUpView } from './wrapup';

export interface WrapEvents {
  on(type: string, fn: (msg: Record<string, unknown>) => void): () => void;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

export class WrapUpStore {
  view: WrapUpView | null = $state.raw(null);
  private client: WrapClient | null = null;

  attach(events: WrapEvents, client: WrapClient | null = null): () => void {
    this.client = client;
    return events.on('sequence', (m) => this.ingest(m));
  }

  /** One `sequence` message: its `wrapup` (a record without the key leaves the view as it is). */
  ingest(m: unknown): void {
    if (!isObj(m)) return;
    const v = isObj(m.sequence) ? m.sequence : m;
    if (!('wrapup' in v)) return;
    this.view = checkWrapUp(v.wrapup);
  }

  async refresh(client: WrapClient | null = this.client): Promise<void> {
    if (!client) return;
    try {
      this.view = await wrapupApi.get(client);
    } catch {
      // 404 before any run ended (or an older server): nothing to wrap up.
    }
  }

  /** Replace the Plan draft with tonight's calibration; resolves to the draft replaced (Undo). Rejects with the server's words. */
  async prepare(counts: { darks?: number; biases?: number } = {}): Promise<{ replaced: SequencePlan | null }> {
    if (!this.client) throw new Error('No server link');
    return wrapupApi.calibrationPlan(this.client, counts);
  }
}
