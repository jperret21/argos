import { describe, expect, it } from 'vitest';
import type { SessionPage, SessionSummary } from '../../api/types';
import {
  baseName,
  curvesSpoken,
  curvesText,
  emptyText,
  filterSessions,
  filtersText,
  forget,
  isRecentList,
  MAX_RECENT,
  pagingNote,
  parentPath,
  pathRecent,
  remember,
  sessionRecent,
  startedText,
} from './landing';
import { LandingStore } from './landing.svelte';

const S = (folder: string, extra: Partial<SessionSummary> = {}): SessionSummary => ({
  path: `/data/sessions/${folder}`,
  folder,
  object: folder.split('_').slice(1).join(' '),
  started_utc: '2026-09-25T20:04:56.567116+00:00',
  frames: 195,
  lights: 195,
  filters: { IR: 195 },
  image_types: { 'Light Frame': 195 },
  missing_frames: 0,
  curves: { target: 1, comparison: 6, check: 0 },
  has_quality: true,
  has_targets: true,
  issues: [],
  ...extra,
});

describe('R0 landing model', () => {
  it('formats the start, filters and curves', () => {
    expect(startedText('2026-09-25T20:04:56.567116+00:00')).toBe('2026-09-25 20:04:56');
    expect(startedText('2026-09-07T04:07:23')).toBe('2026-09-07 04:07:23');
    expect(startedText('')).toBe('—');
    expect(startedText('garbage')).toBe('garbage');
    expect(filtersText({ IR: 3, LP: 10 })).toBe('LP · IR');
    expect(filtersText({ '—': 4 })).toBe('—');
    expect(filtersText({ '—': 4, IR: 2 })).toBe('IR');
    expect(filtersText({})).toBe('—');
    expect(curvesText({ target: 1, comparison: 6, check: 0 })).toBe('1 T · 6 C');
    expect(curvesText({ target: 1, comparison: 6, check: 1 })).toBe('1 T · 6 C · 1 K');
    expect(curvesText({ target: 0, comparison: 0, check: 0 })).toBe('none');
    expect(curvesSpoken({ target: 1, comparison: 6, check: 1 })).toBe('1 target, 6 comparisons, 1 check star');
  });

  it('filters by words and scope', () => {
    const list = [
      S('20260925T200453Z_RR_Lyr'),
      S('20260907T040723Z_XX_Cyg', { started_utc: '2026-09-07T04:07:23+00:00' }),
      S('20260619_m42', { curves: { target: 0, comparison: 0, check: 0 }, issues: ['No light frames were recorded.'], filters: { '—': 3 } }),
    ];
    expect(filterSessions(list, '').length).toBe(3);
    expect(filterSessions(list, 'rr lyr').map((s) => s.folder)).toEqual(['20260925T200453Z_RR_Lyr']);
    expect(filterSessions(list, '2026-09-07').map((s) => s.folder)).toEqual(['20260907T040723Z_XX_Cyg']);
    expect(filterSessions(list, 'IR').length).toBe(2);
    expect(filterSessions(list, '', 'photometry').length).toBe(2);
    expect(filterSessions(list, '', 'issues').map((s) => s.folder)).toEqual(['20260619_m42']);
    expect(filterSessions(list, 'cyg', 'issues')).toEqual([]);
  });

  it('keeps recent items unique, newest first, bounded', () => {
    let r = remember([], pathRecent('import', '/a/target_RR_Lyr_ir_000-BCG-719.csv', 1));
    r = remember(r, pathRecent('fits', '/a/f.fit', 2));
    r = remember(r, pathRecent('import', '/a/target_RR_Lyr_ir_000-BCG-719.csv', 3));
    expect(r.map((i) => [i.kind, i.t])).toEqual([
      ['import', 3],
      ['fits', 2],
    ]);
    expect(r[0].label).toBe('target_RR_Lyr_ir_000-BCG-719.csv');
    // Same path, another kind: two entries.
    r = remember(r, pathRecent('session', '/a/f.fit', 4));
    expect(r.length).toBe(3);
    for (let i = 0; i < 20; i++) r = remember(r, pathRecent('fits', `/x/${i}.fit`, 10 + i));
    expect(r.length).toBe(MAX_RECENT);
    expect(forget(r, { kind: 'fits', path: '/x/19.fit' }).length).toBe(MAX_RECENT - 1);
    expect(isRecentList(r)).toBe(true);
    expect(isRecentList([{ kind: 'zip', path: '/a', label: 'a', t: 1 }])).toBe(false);
    expect(isRecentList([{ kind: 'import', path: '', label: 'a', t: 1 }])).toBe(false);
  });

  it('labels a session recent entry by object and start', () => {
    expect(sessionRecent(S('20260925T200453Z_RR_Lyr'), 5)).toEqual({
      kind: 'session',
      path: '/data/sessions/20260925T200453Z_RR_Lyr',
      label: 'RR Lyr · 2026-09-25 20:04',
      t: 5,
    });
    expect(sessionRecent({ ...S('x'), object: '' }).label).toBe('x');
  });

  it('splits paths', () => {
    expect(baseName('/a/b/c/')).toBe('c');
    expect(baseName('c.csv')).toBe('c.csv');
    expect(parentPath('/a/b/c.csv')).toBe('/a/b');
    expect(parentPath('/c')).toBe('');
  });

  it('says why the list is empty and when it is paged', () => {
    expect(emptyText('/data/sessions', true, false)).toBe('No sessions in /data/sessions');
    expect(emptyText('/data/sessions', false, false)).toBe('The sessions folder /data/sessions does not exist');
    expect(emptyText(null, true, false)).toBe('No sessions folder is set');
    expect(emptyText('/d', true, true)).toBe('No session matches the filter.');
    expect(pagingNote(812, 500)).toBe('Showing the newest 500 of 812 sessions');
    expect(pagingNote(12, 12)).toBeNull();
  });
});

describe('LandingStore', () => {
  const page = (n: number): SessionPage => ({
    root: '/data/sessions',
    exists: true,
    total: n,
    offset: 0,
    limit: 500,
    sessions: Array.from({ length: n }, (_, i) => S(`2026090${i}T000000Z_X_${i}`)),
    scanned_utc: '2026-11-15T10:00:00Z',
  });

  it('loads, keeps the last list on an error, and supersedes older calls', async () => {
    let fail = false;
    const calls: number[] = [];
    const store = new LandingStore(async (q) => {
      calls.push(q.limit ?? 0);
      if (fail) throw new Error('Cannot reach the ARGOS server');
      return page(3);
    }, false);
    await store.load();
    expect(store.page?.sessions.length).toBe(3);
    expect(calls).toEqual([500]);
    fail = true;
    await store.load();
    expect(store.error).toBe('Cannot reach the ARGOS server');
    expect(store.page?.sessions.length).toBe(3);
    expect(store.loading).toBe(false);
  });

  it('remembers opened sources by their session label, not the live run', async () => {
    const store = new LandingStore(async () => page(2), false);
    await store.load();
    const first = store.page!.sessions[0];
    store.opened({ kind: 'session', path: first.path }, 7);
    store.opened({ kind: 'live' }, 8);
    store.opened({ kind: 'fits', path: '/a/b/frame_00007.fit' }, 9);
    expect(store.recent.map((r) => r.label)).toEqual(['frame_00007.fit', `${first.object} · 2026-09-25 20:04`]);
    store.forget(store.recent[0]);
    expect(store.recent.length).toBe(1);
  });
});
