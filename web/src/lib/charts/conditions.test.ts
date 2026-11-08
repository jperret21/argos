import { describe, expect, it } from 'vitest';
import { ConditionsColumns, liveness, observedCadence, overdueAfter, timeRange, type ConditionsRow } from './conditions';
import { ConditionsStore } from './conditions.svelte';

const T0 = Date.parse('2026-11-08T21:00:00Z') / 1000;
function row(seq: number, dt = 2, extra: Partial<ConditionsRow> = {}): ConditionsRow {
  return {
    seq,
    frame_seq: 100 + seq,
    t: new Date((T0 + seq * dt) * 1000).toISOString(),
    origin: 'live',
    exposure_s: 2,
    hfd_px: 2 + seq / 100,
    fwhm_px: null,
    star_count: 200 + seq,
    sky_adu: 1800,
    peak_adu: 40000,
    airmass_mount: 1.2,
    airmass_target: null,
    sensor_temp_c: 12,
    focuser_temp_c: null,
    focuser_position: 5000,
    ...extra,
  };
}

describe('conditions columns (typed arrays, D6)', () => {
  it('appends in seq order, ignores repeats, turns null into NaN, and grows', () => {
    const c = new ConditionsColumns(1000, 4);
    for (let i = 1; i <= 10; i++) expect(c.append(row(i))).toBe('appended');
    expect(c.append(row(5))).toBe('duplicate');
    expect(c.n).toBe(10);
    expect(c.view('t')[0]).toBe(T0 + 2);
    expect(c.view('hfd')[9]).toBeCloseTo(2.1, 9);
    expect(Number.isNaN(c.view('fwhm')[0])).toBe(true);
    expect(c.view('stars').length).toBe(10);
    expect(c.last('stars')).toBe(210);
    expect(c.extent('hfd')).toEqual([2.01, 2.1]);
    expect(c.append(row(12))).toBe('gap');
  });

  it('drops the oldest tenth when full, in one copy', () => {
    const c = new ConditionsColumns(50, 8);
    for (let i = 1; i <= 51; i++) c.append(row(i));
    expect(c.n).toBe(46); // 50 - 5 + 1
    expect(c.view('seq')[0]).toBe(6);
    expect(c.view('seq')[45]).toBe(51);
  });

  it('merges a REST page and restarts on a new server process', () => {
    const c = new ConditionsColumns();
    expect(c.fill({ rows: [row(3), row(1), row(2)], first_seq: 1, last_seq: 3, boot_id: 'a' })).toBe(3);
    expect(Array.from(c.view('seq'))).toEqual([1, 2, 3]);
    expect(c.fill({ rows: [row(1)], first_seq: 1, last_seq: 1, boot_id: 'b' })).toBe(1);
    expect(c.n).toBe(1);
  });

  it('finds rows by time and measures the cadence robustly', () => {
    const c = new ConditionsColumns();
    for (let i = 1; i <= 10; i++) c.append(row(i, 2));
    c.append(row(11, 2, { t: new Date((T0 + 11 * 2 + 30) * 1000).toISOString() })); // one slow frame
    expect(c.indexAt(T0 + 7)).toBe(3);
    expect(observedCadence(c.cols.t, c.n)).toBe(2);
    expect(overdueAfter(2)).toBe(62);
    expect(overdueAfter(null)).toBe(120);
  });

  it('says a run is overdue only while frames are expected', () => {
    const c = new ConditionsColumns();
    for (let i = 1; i <= 5; i++) c.append(row(i, 2));
    const last = T0 + 10;
    expect(liveness(c, last + 30, true)).toMatchObject({ age: 30, cadence: 2, limit: 62, overdue: false });
    expect(liveness(c, last + 90, true).overdue).toBe(true);
    expect(liveness(c, last + 90, false).overdue).toBe(false);
    expect(liveness(new ConditionsColumns(), last, true).age).toBeNull();
  });

  it('runs the time range to now, with a minimum span', () => {
    const c = new ConditionsColumns();
    for (let i = 1; i <= 5; i++) c.append(row(i, 2));
    const now = T0 + 20;
    expect(timeRange(c, now, null)).toEqual([now - 600, now]);
    expect(timeRange(c, now, 1800)).toEqual([now - 1800, now]);
  });
});

describe('conditions store', () => {
  it('reads what a hole in seq lost, then follows the stream', async () => {
    const server = [1, 2, 3, 4, 5, 6].map((s) => row(s));
    const asked: (number | null)[] = [];
    const store = new ConditionsStore(async (since) => {
      asked.push(since);
      const rows = server.filter((r) => since === null || r.seq > since);
      return { rows, first_seq: rows[0]?.seq ?? null, last_seq: rows.at(-1)?.seq ?? null, boot_id: 'x' };
    });
    store.ingest(row(1));
    store.ingest(row(2));
    const v = store.version;
    store.ingest(row(5)); // 3 and 4 were dropped
    await store.sync();
    expect(asked[0]).toBe(2);
    expect(Array.from(store.cols.view('seq'))).toEqual([1, 2, 3, 4, 5, 6]);
    expect(store.version).toBeGreaterThan(v);
    store.ingest(row(7));
    expect(store.n).toBe(7);
  });

  it('keeps the history when a live row arrives while the page is being read (review W3)', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const store = new ConditionsStore(async () => {
      await gate;
      const rows = Array.from({ length: 500 }, (_, i) => row(i + 1));
      return { rows, first_seq: 1, last_seq: 500, boot_id: 'x' };
    });
    const reading = store.sync(null); // page load: the whole session
    store.ingest(row(501)); // a live row before the page arrives
    store.ingest(row(502));
    release();
    await reading;
    expect(store.n).toBe(502);
    expect(store.cols.lastSeq).toBe(502);
    store.ingest(row(503));
    expect(store.n).toBe(503);
  });

  it('keeps the rows and says why when the snapshot read fails', async () => {
    const store = new ConditionsStore(async () => {
      throw new Error('Server unreachable');
    });
    store.ingest(row(1));
    await store.sync();
    expect(store.error).toBe('Server unreachable');
    expect(store.n).toBe(1);
  });
});

describe('frameless intervals (review of wave 3)', () => {
  it('breaks the series where no frame came, and names the cause', async () => {
    const { gapsOf, gapLabel } = await import('./conditions');
    const t = [0, 2, 4, 6, 8, 200, 202, 204];
    expect(gapsOf(t, t.length)).toEqual([4]);
    expect(gapLabel(8, 200, [{ from: 60, to: 140, label: 'autofocus 13:36–13:38' }])).toBe('autofocus 13:36–13:38');
    expect(gapLabel(8, 200, [])).toBe('no frame');
    expect(gapLabel(8, 200, [{ from: 300, to: 400, label: 'later' }])).toBe('no frame');
  });
});
