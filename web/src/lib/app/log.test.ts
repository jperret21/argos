import { describe, expect, it } from 'vitest';
import {
  filterLog,
  FollowState,
  isAtBottom,
  levelVisible,
  localClock,
  LogBuffer,
  type LogFilterSpec,
  logFileName,
  logLine,
  parseLogRecord,
  SERVER_RESTART_TEXT,
  utcClock,
  utcFull,
} from './log';

const T = '2026-11-01T21:34:05.000Z';
const v2 = (seq: number, level = 'info', message = `line ${seq}`, extra: Record<string, unknown> = {}) => ({
  type: 'log',
  id: seq,
  seq,
  level,
  source: 'mount',
  topic: 'connection',
  message,
  t: T,
  ...extra,
});
const all: LogFilterSpec = { level: 'all', debug: false, query: '', topics: null };

describe('parseLogRecord', () => {
  it('reads v2 lines (seq, source, topic, the six levels)', () => {
    expect(parseLogRecord(v2(7, 'cmd'))).toEqual({
      level: 'cmd',
      message: 'line 7',
      t: T,
      seq: 7,
      source: 'mount',
      topic: 'connection',
    });
    for (const level of ['debug', 'cmd', 'info', 'ok', 'warning', 'error']) {
      expect(parseLogRecord(v2(1, level))?.level).toBe(level);
    }
  });

  it('reads v1 lines and refuses what does not match the contract', () => {
    expect(parseLogRecord({ type: 'log', level: 'warning', message: 'x', t: T })).toMatchObject({
      level: 'warning',
      seq: null,
      source: null,
      topic: null,
    });
    expect(parseLogRecord({ type: 'log', level: 'warn', message: 'x', t: T })?.level).toBe('warning');
    expect(parseLogRecord({ type: 'status' })).toBeNull();
    expect(parseLogRecord({ level: 'loud', message: 'x' })).toBeNull();
    expect(parseLogRecord({ level: 'info' })).toBeNull();
    expect(parseLogRecord('info')).toBeNull();
  });
});

describe('LogBuffer', () => {
  it('stays bounded, dropping the oldest lines and counting them', () => {
    const b = new LogBuffer(5);
    for (let i = 1; i <= 12; i++) b.push(parseLogRecord(v2(i))!);
    expect(b.length).toBe(5);
    expect(b.entries().map((r) => r.seq)).toEqual([8, 9, 10, 11, 12]);
    expect(b.dropped).toBe(7);
    expect(b.lastSeq).toBe(12);
  });

  it('defaults to the server ring size (5 000 lines)', () => {
    const b = new LogBuffer();
    for (let i = 1; i <= 5003; i++) b.push(parseLogRecord(v2(i))!);
    expect(b.length).toBe(5000);
    expect(b.entries()[0].seq).toBe(4);
  });

  it('ignores the replay of lines it holds (same seq), even after a clear', () => {
    const b = new LogBuffer(100);
    for (let i = 1; i <= 3; i++) b.push(parseLogRecord(v2(i))!);
    expect(b.push(parseLogRecord(v2(2))!).added).toBe(false);
    b.clear();
    expect(b.length).toBe(0);
    for (let i = 1; i <= 3; i++) expect(b.push(parseLogRecord(v2(i))!).added).toBe(false);
    expect(b.push(parseLogRecord(v2(4))!).added).toBe(true);
    expect(b.entries().map((r) => r.seq)).toEqual([4]);
  });

  it('drops v1 replays by (time, level, text) but keeps client lines', () => {
    const b = new LogBuffer(100);
    const line = { level: 'info' as const, message: 'Connected', t: T };
    expect(b.push(line).added).toBe(true);
    expect(b.push(line).added).toBe(false);
    expect(b.push({ ...line, local: true }).added).toBe(true);
    expect(b.push({ ...line, local: true }).added).toBe(true);
  });

  it('reports a seq gap and puts the late lines back in order', () => {
    const b = new LogBuffer(100);
    b.push(parseLogRecord(v2(1))!);
    b.push({ level: 'error', message: 'client', t: T, local: true });
    const r = b.push(parseLogRecord(v2(5))!);
    expect(r).toEqual({ added: true, gap: true, gapAfter: 1 });
    // GET /api/logs?after=1 brings 2..5; 5 is already held.
    for (let i = 2; i <= 5; i++) b.push(parseLogRecord(v2(i))!);
    // Late server lines go right after the server line that precedes them.
    expect(b.entries().map((e) => e.seq)).toEqual([1, 2, 3, 4, null, 5]);
    expect(b.lastSeq).toBe(5);
  });

  it('a restarted server (seq from 1 again, other times) is kept, after a marker line', () => {
    const b = new LogBuffer();
    for (let i = 1; i <= 5; i++) b.push(parseLogRecord(v2(i))!);
    // The same lines replayed by the same server: duplicates.
    expect(b.push(parseLogRecord(v2(3))!).added).toBe(false);
    // A new server process: seq 1 again, a later time, another text.
    const later = '2026-11-01T21:40:00.000Z';
    const r = b.push(parseLogRecord(v2(1, 'info', 'Server started', { t: later }))!);
    expect(r).toMatchObject({ added: true, restarted: true, gap: false });
    b.push(parseLogRecord(v2(2, 'ok', 'Mount connected', { t: later }))!);
    const msgs = b.entries().map((e) => e.message);
    expect(msgs.slice(0, 5)).toEqual(['line 1', 'line 2', 'line 3', 'line 4', 'line 5']);
    expect(msgs[5]).toBe(SERVER_RESTART_TEXT);
    expect(msgs.slice(6)).toEqual(['Server started', 'Mount connected']);
    expect(b.lastSeq).toBe(2);
    // The new server's replay of its own lines is a duplicate again.
    expect(b.push(parseLogRecord(v2(2, 'ok', 'Mount connected', { t: later }))!).added).toBe(false);
    // A late line of the new server never lands among the old server's lines.
    b.push(parseLogRecord(v2(5, 'info', 'five', { t: later }))!);
    b.push(parseLogRecord(v2(4, 'info', 'four', { t: later }))!);
    expect(b.entries().map((e) => e.message).slice(6)).toEqual(['Server started', 'Mount connected', 'four', 'five']);
  });

  it('a restarted server whose old numbering ran past what the page remembers is still seen (review repro)', () => {
    // 12 000 lines of the old server: the page holds the last 5 000 lines and remembers
    // 10 000 seq numbers, so the new server's 1, 2, 3 collide with nothing.
    const b = new LogBuffer();
    const old = (i: number) => new Date(Date.parse(T) + i).toISOString();
    for (let i = 1; i <= 12_000; i++) b.push(parseLogRecord(v2(i, 'info', `old ${i}`, { t: old(i) }))!);
    const later = '2026-11-01T22:00:00.000Z';
    const r = b.push(parseLogRecord(v2(1, 'info', 'Connecting focuser…', { t: later }))!);
    expect(r).toMatchObject({ added: true, restarted: true });
    b.push(parseLogRecord(v2(2, 'ok', 'Focuser connected', { t: later }))!);
    b.push(parseLogRecord(v2(3, 'cmd', 'Connecting mount…', { t: later }))!);
    const tail = b.entries().slice(-4).map((e) => e.message);
    expect(tail).toEqual([SERVER_RESTART_TEXT, 'Connecting focuser…', 'Focuser connected', 'Connecting mount…']);
    expect(b.lastSeq).toBe(3);
  });

  it('a late line (gap fill) or a reordered line is never taken for a restart', () => {
    const b = new LogBuffer();
    const at = (ms: number) => new Date(Date.parse(T) + ms).toISOString();
    b.push(parseLogRecord(v2(1, 'info', 'a', { t: at(0) }))!);
    b.push(parseLogRecord(v2(3, 'info', 'c', { t: at(20) }))!);
    // seq 2 arrives after 3, stamped before it (or in the same millisecond).
    expect(b.push(parseLogRecord(v2(2, 'info', 'b', { t: at(20) }))!).restarted).toBeUndefined();
    expect(b.entries().map((e) => e.message)).toEqual(['a', 'b', 'c']);
    expect(b.epoch).toBe(0);
  });

  it('restart() (boot id changed) starts a new seq space, with a marker only after old lines', () => {
    const fresh = new LogBuffer();
    fresh.restart(T);
    expect(fresh.length).toBe(0); // nothing to separate yet
    const b = new LogBuffer();
    for (let i = 1; i <= 3; i++) b.push(parseLogRecord(v2(i))!);
    b.restart(T);
    expect(b.entries().at(-1)?.message).toBe(SERVER_RESTART_TEXT);
    // The marker shows in a topic-filtered view too (the Connection log).
    const connection: LogFilterSpec = { level: 'all', debug: false, query: '', topics: ['connection'] };
    expect(filterLog(b.entries(), connection).map((r) => r.message)).toContain(SERVER_RESTART_TEXT);
    // The new server's replay starts at 1 with the very same times: not duplicates.
    expect(b.push(parseLogRecord(v2(1))!).added).toBe(true);
    expect(b.push(parseLogRecord(v2(2))!).added).toBe(true);
    expect(b.lastSeq).toBe(2);
  });

  it('gives every line a unique, increasing uid', () => {
    const b = new LogBuffer(10);
    b.push(parseLogRecord(v2(1))!);
    b.push(parseLogRecord(v2(3))!);
    b.push(parseLogRecord(v2(2))!);
    const uids = b.entries().map((e) => e.uid);
    expect(new Set(uids).size).toBe(3);
    expect(b.lastUid).toBe(3);
  });
});

describe('log filters', () => {
  const b = new LogBuffer(100);
  b.push(parseLogRecord(v2(1, 'debug', 'poll'))!);
  b.push(parseLogRecord(v2(2, 'cmd', 'Connecting mount 192.168.1.42:32323…'))!);
  b.push(parseLogRecord(v2(3, 'ok', 'Mount connected: Seestar S30 Pro'))!);
  b.push(parseLogRecord(v2(4, 'warning', 'Mount clock off by 4 s', { topic: 'mount' }))!);
  b.push(parseLogRecord(v2(5, 'error', 'Camera: timed out', { source: 'camera' }))!);
  b.push(parseLogRecord(v2(6, 'info', 'Discovery started', { topic: 'discovery', source: 'discovery' }))!);

  it('hides debug lines unless asked, and keeps the more severe levels', () => {
    expect(filterLog(b.entries(), all).map((r) => r.seq)).toEqual([2, 3, 4, 5, 6]);
    expect(filterLog(b.entries(), { ...all, debug: true })).toHaveLength(6);
    expect(filterLog(b.entries(), { ...all, level: 'warnings' }).map((r) => r.seq)).toEqual([4, 5]);
    expect(filterLog(b.entries(), { ...all, level: 'errors' }).map((r) => r.seq)).toEqual([5]);
    expect(levelVisible('debug', { level: 'warnings', debug: true })).toBe(false);
  });

  it('searches the message, the source and the topic, case-insensitively', () => {
    expect(filterLog(b.entries(), { ...all, query: 'MOUNT' }).map((r) => r.seq)).toEqual([2, 3, 4]);
    expect(filterLog(b.entries(), { ...all, query: 'camera' }).map((r) => r.seq)).toEqual([5]);
    expect(filterLog(b.entries(), { ...all, query: '  ' })).toHaveLength(5);
  });

  it('keeps only the topics of a view (the Connection log)', () => {
    const conn = { ...all, topics: ['connection', 'discovery', 'planetarium'] };
    expect(filterLog(b.entries(), conn).map((r) => r.seq)).toEqual([2, 3, 5, 6]);
  });
});

describe('log time and text', () => {
  it('shows UTC on screen and local time in the tooltip', () => {
    expect(utcClock(T)).toBe('21:34:05');
    expect(utcFull(T)).toBe('2026-11-01 21:34:05 UTC');
    expect(localClock(T, 60)).toBe('22:34:05 local (UTC+01:00)');
    expect(localClock(T, -330)).toBe('16:04:05 local (UTC−05:30)');
    expect(localClock('2026-11-01T23:30:00Z', 120)).toBe('01:30:00 local 2026-11-02 (UTC+02:00)');
    expect(utcClock('nonsense')).toBe('--:--:--');
  });

  it('writes one text line per record and a dated file name', () => {
    const b = new LogBuffer(10);
    b.push(parseLogRecord(v2(1, 'warning', 'Clock off'))!);
    expect(logLine(b.entries()[0])).toBe('2026-11-01 21:34:05 UTC  WARN  [mount]  Clock off');
    expect(logFileName(new Date(T))).toBe('argos-log-20261101T213405Z.txt');
  });
});

describe('follow / pause', () => {
  it('detects the bottom with a little slack', () => {
    expect(isAtBottom(780, 1000, 200)).toBe(true);
    expect(isAtBottom(776, 1000, 200)).toBe(true);
    expect(isAtBottom(775, 1000, 200)).toBe(false);
    expect(isAtBottom(700, 1000, 200)).toBe(false);
  });

  it('follows new lines until the observer scrolls up, then counts them', () => {
    const f = new FollowState();
    expect(f.appended(3)).toBe(true);
    f.scrolled(false);
    expect(f.following).toBe(false);
    expect(f.appended(2)).toBe(false);
    expect(f.appended(5)).toBe(false);
    expect(f.unseen).toBe(7);
    f.scrolled(true);
    expect(f.following).toBe(true);
    expect(f.unseen).toBe(0);
    f.scrolled(false);
    f.appended(4);
    f.jump();
    expect(f).toMatchObject({ following: true, unseen: 0 });
    expect(f.appended(0)).toBe(false);
  });
});
