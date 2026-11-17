/**
 * The conditions store of the session (A37): typed-array columns
 * (conditions.ts) plus ONE reactive version counter, so a chart re-reads the
 * columns when a row arrives without the numbers ever entering a $state
 * proxy (web/lab/PROPOSAL.md 3.4).
 *
 * Fed by the `conditions` events of /ws/events (`ingest`) and by
 * `GET /api/session/conditions?since_seq=` (`sync`): once per (re)connection,
 * and whenever a hole in `seq` shows a dropped message (backpressure). One
 * read at a time; a hole found while a read runs asks for one more read.
 * Rows that arrive live while a read runs are held and merged after it, so
 * the page's older rows are never rejected as duplicates of a newer live one
 * (review of wave 3: the history was lost on load or reconnection).
 *
 *   const store = new ConditionsStore((since) => client.request('GET', `/api/session/conditions?since_seq=${since}`));
 *   store.ingest(row); store.version; store.cols.view('hfd');
 */

import { ConditionsColumns, isConditionsRow, type ConditionsPage, type ConditionsRow } from './conditions';

export type ConditionsFetch = (sinceSeq: number | null) => Promise<ConditionsPage>;

export class ConditionsStore {
  /** Bumped once per change: the only reactive part. */
  version = $state(0);
  /** A read of the REST snapshot failed (its words), null when fine. */
  error: string | null = $state(null);
  readonly cols: ConditionsColumns;
  private readonly fetchPage: ConditionsFetch | null;
  private reading: Promise<void> | null = null;
  private again = false;
  /** Live rows received while a read runs: merged after the page. */
  private held: ConditionsRow[] = [];

  constructor(fetchPage: ConditionsFetch | null = null, cols = new ConditionsColumns()) {
    this.fetchPage = fetchPage;
    this.cols = cols;
  }

  get n(): number {
    void this.version;
    return this.cols.n;
  }

  /** One `conditions` event. A hole in seq triggers a REST read of what is missing. */
  ingest(raw: unknown): void {
    const row = raw as ConditionsRow;
    if (!isConditionsRow(row)) return;
    if (this.reading) {
      this.held.push(row);
      return;
    }
    const last = this.cols.lastSeq;
    if (this.fetchPage && last !== null && row.seq > last + 1) {
      // Rows are missing before this one: read them (this row comes with them),
      // never append past the hole, or the missing rows could not be merged in order.
      void this.sync(last);
      return;
    }
    const res = this.cols.append(row);
    if (res === 'appended' || res === 'gap') this.version++;
  }

  /** Read the rows after `since` (default: the newest held) and merge them. */
  sync(since: number | null = this.cols.lastSeq): Promise<void> {
    if (!this.fetchPage) return Promise.resolve();
    if (this.reading) {
      this.again = true;
      return this.reading;
    }
    const run = async (from: number | null): Promise<void> => {
      try {
        const page = await this.fetchPage!(from);
        const hadBoot = this.cols.bootId;
        let added = this.cols.fill(page);
        this.error = null;
        added += this.mergeHeld();
        if (added > 0 || hadBoot !== this.cols.bootId) this.version++;
      } catch (err) {
        this.error = err instanceof Error ? err.message : String(err);
        if (this.mergeHeld() > 0) this.version++;
      }
    };
    this.reading = (async () => {
      await run(since);
      while (this.again) {
        this.again = false;
        await run(this.cols.lastSeq);
      }
      this.reading = null;
    })();
    return this.reading;
  }

  /** Append the rows held during a read, in order; a hole asks for one more read. */
  private mergeHeld(): number {
    if (!this.held.length) return 0;
    const rows = this.held.sort((a, b) => a.seq - b.seq);
    this.held = [];
    let added = 0;
    for (const row of rows) {
      const last = this.cols.lastSeq;
      if (last !== null && row.seq <= last) continue;
      if (last !== null && row.seq > last + 1) {
        this.again = true; // the next read brings this row and the ones before it
        break;
      }
      const res = this.cols.append(row);
      if (res === 'appended' || res === 'gap') added++;
    }
    return added;
  }

  /** Forget everything (a test, or a server that lost its rows). */
  clear(): void {
    this.cols.clear();
    this.version++;
  }
}
