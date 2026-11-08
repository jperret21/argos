import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BUNDLE_CONTENTS,
  BUNDLE_REDACTION,
  bundleCreatedText,
  bundleProblem,
  bundleRequest,
  defaultBundleName,
  sessionLabel,
  zipPath,
} from './supportbundle';
import { explainsOnPress, tipContent } from './tooltip';
import { MAX_UNDO, UNDO_MS, UNDONE_MS, UndoQueue } from './undo.svelte';

describe('tooltip v2 content', () => {
  it('label + caps, then one second line: error over reason over hint', () => {
    expect(tipContent({ text: 'Zoom in', shortcut: '+' })).toEqual({ text: 'Zoom in', keys: ['+'], second: null });
    expect(tipContent({ text: 'Slew', shortcut: 'G', reason: 'Unpark the mount first' })).toEqual({
      text: 'Slew',
      keys: [], // it cannot act: no key to teach
      second: { kind: 'reason', text: 'Unpark the mount first' },
    });
    expect(tipContent({ text: 'Park', hint: 'Hold to park', error: 'Mount did not answer' }).second).toEqual({
      kind: 'error',
      text: 'Mount did not answer',
    });
    expect(tipContent({ text: 'Jog', shortcut: ['ArrowUp', 'ArrowDown'] }).keys).toEqual(['ArrowUp', 'ArrowDown']);
  });

  it('a press explains only an unavailable control that has something to say', () => {
    expect(explainsOnPress(true, { text: 'Slew', reason: 'Unpark first' })).toBe(true);
    expect(explainsOnPress(false, { text: 'Slew', reason: 'Unpark first' })).toBe(false);
    expect(explainsOnPress(true, { text: 'Slew' })).toBe(false);
    expect(explainsOnPress(true, { text: 'Slew', reason: 'x', disabled: true })).toBe(false);
  });
});

describe('support bundle', () => {
  it('states the parts of the ZIP the server writes (protocol.md A5) and what it replaces', () => {
    expect(BUNDLE_CONTENTS.map((c) => c.part)).toEqual(['base', 'logs', 'crash', 'session']);
    expect(BUNDLE_CONTENTS[3].detail).toMatch(/Never FITS/);
    expect(BUNDLE_REDACTION).toMatch(/token/);
    expect(BUNDLE_REDACTION).toMatch(/site coordinates/);
  });

  it('proposes a name with the UTC time, so a second bundle never overwrites', () => {
    expect(defaultBundleName('0.5.0', new Date(Date.UTC(2026, 10, 2, 19, 34, 5)))).toBe(
      'argos-support-0.5.0-20261102T193405Z.zip',
    );
    expect(zipPath('/tmp/bundle')).toBe('/tmp/bundle.zip');
    expect(zipPath('/tmp/bundle.ZIP')).toBe('/tmp/bundle.ZIP');
    // Appended, never swapped (the server does the same).
    expect(zipPath('/tmp/c.tar.gz')).toBe('/tmp/c.tar.gz.zip');
  });

  it('sends no session unless one is ticked and chosen (Q-G17)', () => {
    const base = { destination: '~/Desktop/a.zip', includeSession: false, sessionDir: '/s/1' };
    // Defaults: no session, no site coordinates, crash reports in, never overwrite.
    expect(bundleRequest(base)).toEqual({
      destination: '~/Desktop/a.zip',
      include_session: false,
      session_dir: null,
      include_site: false,
      include_crash_reports: true,
      overwrite: false,
    });
    expect(bundleRequest({ ...base, includeSession: true, overwrite: true })).toMatchObject({
      session_dir: '/s/1',
      include_session: true,
      overwrite: true,
    });
    expect(bundleProblem({ ...base, includeSession: true, sessionDir: null })).toMatch(/choose the session/);
    expect(bundleProblem({ ...base, destination: 'relative.zip' })).toMatch(/absolute/);
    expect(bundleProblem({ ...base, destination: null })).toBeNull(); // browser download
  });

  it('labels sessions and the result', () => {
    expect(sessionLabel({ path: '/s/20261031T200453Z_SS_Cyg', object: 'SS Cyg', started_utc: '2026-10-31T20:04:53Z', frames: 412 })).toBe(
      '2026-10-31 · SS Cyg · 412 frames',
    );
    expect(bundleCreatedText({ path: '/Users/me/Desktop/argos-support.zip', files: ['README.txt', 'manifest.json'] })).toBe(
      'Support bundle created: argos-support.zip, 2 files. ARGOS did not upload it.',
    );
    expect(bundleCreatedText({ path: null, name: 'argos-support-0.5.0-20261102T193405Z.zip', files: ['README.txt'], download: true })).toBe(
      'Support bundle created: argos-support-0.5.0-20261102T193405Z.zip, 1 file. ARGOS did not upload it.',
    );
  });
});

describe('undo queue', () => {
  let t = 0;
  const clock = {
    now: () => t,
    setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
    clearTimeout: (h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>),
  };
  beforeEach(() => {
    vi.useFakeTimers();
    t = 0;
  });
  afterEach(() => vi.useRealTimers());
  const advance = (ms: number) => {
    t += ms;
    vi.advanceTimersByTime(ms);
  };

  it('offers Undo for 6 s, then the change stays', () => {
    const q = new UndoQueue(clock);
    const id = q.push({ title: 'Removed Paris', undo: vi.fn() });
    expect(q.secondsLeft(id)).toBe(6);
    advance(1500);
    expect(q.elapsed(id)).toBeCloseTo(0.25, 6);
    advance(UNDO_MS - 1500);
    expect(q.entries).toHaveLength(0);
  });

  it('pauses while the observer is on the toast', () => {
    const q = new UndoQueue(clock);
    const id = q.push({ title: 'Removed Paris', undo: vi.fn() });
    advance(2000);
    q.pause(id);
    advance(60_000);
    expect(q.entries).toHaveLength(1);
    expect(q.secondsLeft(id)).toBe(4);
    q.resume(id);
    advance(3999);
    expect(q.entries).toHaveLength(1);
    advance(1);
    expect(q.entries).toHaveLength(0);
  });

  it('runs the inverse once, says "Undone", then leaves', async () => {
    const q = new UndoQueue(clock);
    const inverse = vi.fn(async () => undefined);
    const id = q.push({ title: 'Removed Paris', undo: inverse });
    expect(await q.undo(id)).toBe(true);
    expect(await q.undo(id)).toBe(false);
    expect(inverse).toHaveBeenCalledTimes(1);
    expect(q.entries[0].state).toBe('undone');
    advance(UNDONE_MS);
    expect(q.entries).toHaveLength(0);
  });

  it('keeps a failed undo with the server words until dismissed', async () => {
    const q = new UndoQueue(clock);
    const id = q.push({ title: 'Reset', undo: () => Promise.reject(new Error('not writable')) });
    expect(await q.undo(id)).toBe(false);
    expect(q.entries[0]).toMatchObject({ state: 'failed', error: 'not writable' });
    advance(60_000);
    expect(q.entries).toHaveLength(1);
    q.dismiss(id);
    expect(q.entries).toHaveLength(0);
  });

  it('merges the changes of one group into one toast, undone newest first', async () => {
    const q = new UndoQueue(clock);
    const order: string[] = [];
    q.push({ title: 'Comparison: A', group: 'roles', undo: () => order.push('A') });
    q.push({ title: 'Removed Paris', undo: vi.fn() });
    const id = q.push({ title: 'Check star: B', group: 'roles', undo: () => order.push('B') });
    expect(q.entries.map((e) => e.title)).toEqual(['Removed Paris', '2 changes']);
    expect(q.entries[1]).toMatchObject({ detail: 'Check star: B', count: 2 });
    expect(q.secondsLeft(id)).toBe(6);
    expect(await q.undo(id)).toBe(true);
    expect(order).toEqual(['B', 'A']);
  });

  it(`keeps at most ${MAX_UNDO} open`, () => {
    const q = new UndoQueue(clock);
    for (let i = 0; i < MAX_UNDO + 2; i++) q.push({ title: `change ${i}`, undo: vi.fn() });
    expect(q.entries.map((e) => e.title)).toEqual(['change 2', 'change 3', 'change 4']);
  });
});
