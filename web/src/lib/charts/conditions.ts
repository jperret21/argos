/**
 * Conditions of the night as typed-array columns (decision D6; server row A37,
 * argos/server/protocol.md "Conditions (A37)": one row per metered camera
 * frame, live and single, not autofocus samples nor opened files).
 *
 * Big data stays OUT of Svelte's reactive graph (web/lab/PROPOSAL.md 3.4:
 * reading 100 000 numbers through a $state proxy cost 276 ms against 0.5 ms
 * raw): the columns are plain Float64Arrays grown by doubling, a component
 * reads `subarray(0, n)` views and hands them to uPlot without a copy, and
 * the reactive store (conditions.svelte.ts) only exposes a version counter.
 *
 * - Rows are ordered and deduplicated by the server's `seq`; a hole in `seq`
 *   (a message dropped under backpressure) is reported so the owner re-reads
 *   `GET /api/session/conditions?since_seq=<last>`; a new `boot_id` (server
 *   restarted) starts the columns again.
 * - Missing values (null in the record) are NaN: uPlot leaves a gap and the
 *   statistics skip them; nothing is interpolated.
 * - Times are unix seconds of the exposure midpoint (the row's `t`).
 * - At most `cap` rows (the server keeps 20 000): the oldest tenth is dropped
 *   in one copy when full, so an append stays O(1) amortised.
 */

export interface ConditionsRow {
  seq: number;
  frame_seq?: number;
  /** Exposure midpoint, ISO 8601 UTC. */
  t: string;
  origin?: 'single' | 'live' | string;
  exposure_s?: number | null;
  gain?: number | null;
  frame_type?: string | null;
  filter?: string | null;
  hfd_px?: number | null;
  fwhm_px?: number | null;
  star_count?: number | null;
  sky_adu?: number | null;
  peak_adu?: number | null;
  airmass_mount?: number | null;
  airmass_target?: number | null;
  sensor_temp_c?: number | null;
  focuser_temp_c?: number | null;
  focuser_position?: number | null;
}

export interface ConditionsPage {
  rows: ConditionsRow[];
  first_seq: number | null;
  last_seq: number | null;
  truncated?: boolean;
  boot_id?: string;
}

/** Column names (numeric, unix seconds for `t`). */
export const COLUMN_NAMES = [
  't',
  'seq',
  'frameSeq',
  'exposure',
  'hfd',
  'fwhm',
  'stars',
  'sky',
  'peak',
  'airmassMount',
  'airmassTarget',
  'sensorC',
  'focuserC',
  'focuser',
] as const;
export type Column = (typeof COLUMN_NAMES)[number];

const FIELD: Record<Exclude<Column, 't'>, keyof ConditionsRow> = {
  seq: 'seq',
  frameSeq: 'frame_seq',
  exposure: 'exposure_s',
  hfd: 'hfd_px',
  fwhm: 'fwhm_px',
  stars: 'star_count',
  sky: 'sky_adu',
  peak: 'peak_adu',
  airmassMount: 'airmass_mount',
  airmassTarget: 'airmass_target',
  sensorC: 'sensor_temp_c',
  focuserC: 'focuser_temp_c',
  focuser: 'focuser_position',
};

export const MAX_ROWS = 20_000;

export type AppendResult = 'appended' | 'duplicate' | 'gap' | 'invalid';

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : NaN;
}

/** Is this a conditions row of the contract (seq and a parseable t)? */
export function isConditionsRow(v: unknown): v is ConditionsRow {
  if (typeof v !== 'object' || v === null) return false;
  const r = v as Record<string, unknown>;
  return typeof r.seq === 'number' && Number.isInteger(r.seq) && typeof r.t === 'string' && Number.isFinite(Date.parse(r.t));
}

export class ConditionsColumns {
  n = 0;
  /** The `seq` of the newest row held (null: none yet). */
  lastSeq: number | null = null;
  /** Server process the rows came from (`boot_id`). */
  bootId: string | null = null;
  readonly cap: number;
  private capacity: number;
  cols: Record<Column, Float64Array>;

  constructor(cap = MAX_ROWS, initial = 256) {
    this.cap = cap;
    this.capacity = Math.min(initial, cap);
    this.cols = this.alloc(this.capacity);
  }

  private alloc(size: number): Record<Column, Float64Array> {
    const out = {} as Record<Column, Float64Array>;
    for (const c of COLUMN_NAMES) out[c] = new Float64Array(size);
    return out;
  }

  /** Every column as a view of the valid prefix (no copy). */
  view(c: Column): Float64Array {
    return this.cols[c].subarray(0, this.n);
  }

  clear(): void {
    this.n = 0;
    this.lastSeq = null;
  }

  private ensureRoom(): void {
    if (this.n < this.capacity) return;
    if (this.capacity < this.cap) {
      const next = Math.min(this.cap, this.capacity * 2);
      const cols = this.alloc(next);
      for (const c of COLUMN_NAMES) cols[c].set(this.cols[c].subarray(0, this.n));
      this.cols = cols;
      this.capacity = next;
      return;
    }
    // Full: forget the oldest tenth in one copy.
    const drop = Math.max(1, Math.floor(this.cap / 10));
    for (const c of COLUMN_NAMES) this.cols[c].copyWithin(0, drop, this.n);
    this.n -= drop;
  }

  /** Append one row in `seq` order; older or repeated rows are ignored. */
  append(row: ConditionsRow): AppendResult {
    if (!isConditionsRow(row)) return 'invalid';
    if (this.lastSeq !== null && row.seq <= this.lastSeq) return 'duplicate';
    const gap = this.lastSeq !== null && row.seq > this.lastSeq + 1;
    this.ensureRoom();
    const i = this.n;
    this.cols.t[i] = Date.parse(row.t) / 1000;
    for (const [c, f] of Object.entries(FIELD) as [Exclude<Column, 't'>, keyof ConditionsRow][]) {
      this.cols[c][i] = num(row[f]);
    }
    this.n = i + 1;
    this.lastSeq = row.seq;
    return gap ? 'gap' : 'appended';
  }

  /**
   * A REST page (oldest first). A page from another server process (boot_id)
   * replaces everything; otherwise its rows are merged in seq order.
   * Returns the number of rows added.
   */
  fill(page: ConditionsPage): number {
    if (page.boot_id && this.bootId !== null && page.boot_id !== this.bootId) this.clear();
    if (page.boot_id) this.bootId = page.boot_id;
    let added = 0;
    const rows = [...page.rows].sort((a, b) => a.seq - b.seq);
    for (const r of rows) {
      const res = this.append(r);
      if (res === 'appended' || res === 'gap') added++;
    }
    return added;
  }

  /** Index of the first row at or after time `t` (binary search; n when none). */
  indexAt(t: number): number {
    let lo = 0;
    let hi = this.n;
    const ts = this.cols.t;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (ts[mid] < t) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  /** Last finite value of a column (NaN when none). */
  last(c: Column): number {
    const a = this.cols[c];
    for (let i = this.n - 1; i >= 0; i--) if (Number.isFinite(a[i])) return a[i];
    return NaN;
  }

  /** Finite min and max of a column over rows with t >= since (NaN, NaN when none). */
  extent(c: Column, since = -Infinity): [number, number] {
    const a = this.cols[c];
    let lo = Infinity;
    let hi = -Infinity;
    for (let i = this.indexAt(since); i < this.n; i++) {
      const v = a[i];
      if (!Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    return Number.isFinite(lo) ? [lo, hi] : [NaN, NaN];
  }
}

/**
 * Observed cadence: the median interval between the last `k` frames
 * (seconds), so a single slow frame does not move it. Null under 3 rows.
 */
export function observedCadence(t: ArrayLike<number>, n: number, k = 12): number | null {
  if (n < 3) return null;
  const d: number[] = [];
  for (let i = Math.max(1, n - k); i < n; i++) {
    const dt = t[i] - t[i - 1];
    if (dt > 0 && Number.isFinite(dt)) d.push(dt);
  }
  if (!d.length) return null;
  d.sort((a, b) => a - b);
  const m = d.length >> 1;
  return d.length % 2 ? d[m] : (d[m - 1] + d[m]) / 2;
}

/** After this many seconds without a frame, a run that expects frames is overdue (PROPOSAL principle 2). */
export function overdueAfter(cadence: number | null): number {
  return cadence !== null ? Math.max(2 * cadence, cadence + 60) : 120;
}

/**
 * Intervals with no frame (review of wave 3): the indices i whose next row
 * comes later than overdueAfter(cadence of the whole series). The timeline
 * breaks every series there (a null point) and draws the interval as a
 * period, so a straight line never invents a trend that was not measured.
 */
export function gapsOf(t: ArrayLike<number>, n: number): number[] {
  if (n < 2) return [];
  const cadence = observedCadence(t, n, n);
  const limit = overdueAfter(cadence);
  const out: number[] = [];
  for (let i = 0; i + 1 < n; i++) if (t[i + 1] - t[i] > limit) out.push(i);
  return out;
}

/** A period drawn on the timeline (an autofocus run), unix seconds. */
export interface TimelinePeriod {
  from: number;
  to: number;
  label: string;
}

/** What to call the frameless interval [a, b]: the period inside it that covers most of it, else "no frame". */
export function gapLabel(a: number, b: number, periods: readonly TimelinePeriod[]): string {
  let best: TimelinePeriod | null = null;
  let bestCover = 0;
  for (const p of periods) {
    const cover = Math.min(b, p.to) - Math.max(a, p.from);
    if (cover > bestCover) {
      best = p;
      bestCover = cover;
    }
  }
  return best ? best.label : 'no frame';
}

export interface Liveness {
  /** Seconds since the newest row (null: no row). */
  age: number | null;
  cadence: number | null;
  limit: number;
  /** Frames are expected (live view running) and none came for longer than `limit`. */
  overdue: boolean;
}

export function liveness(cols: ConditionsColumns, now: number, expecting: boolean): Liveness {
  const n = cols.n;
  const cadence = observedCadence(cols.cols.t, n);
  const limit = overdueAfter(cadence);
  const age = n ? Math.max(0, now - cols.cols.t[n - 1]) : null;
  return { age, cadence, limit, overdue: expecting && age !== null && age > limit };
}

/**
 * x range of the timeline: from the first row in the window to NOW (the gap
 * after the newest point is the age of the last frame), with a minimum span
 * so two frames do not fill the width.
 */
export function timeRange(cols: ConditionsColumns, now: number, windowS: number | null, minSpan = 600): [number, number] {
  const end = Math.max(now, cols.n ? cols.cols.t[cols.n - 1] : now);
  let start = windowS !== null ? end - windowS : cols.n ? cols.cols.t[0] : end - minSpan;
  if (end - start < minSpan) start = end - minSpan;
  return [start, end];
}
