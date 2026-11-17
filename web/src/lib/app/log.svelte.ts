/**
 * Reactive activity log (one store for the whole UI, D17): the Log tab of
 * every drawer, the Connection log region and the status-bar badge read it.
 *
 * (The file is `.svelte.ts` because runes only compile in .svelte /
 * .svelte.ts modules; import it as "./log.svelte".)
 *
 * Feeding it:
 *   store.ingest(msg)            // a /ws/events "log" message (v1 or v2)
 *   store.ingestPage(page)       // GET /api/logs?after=… (LogPage)
 *   store.push('error', text, { topic: 'connection' })   // client-side line
 * `ingest` returns `{gap, gapAfter}` when a server seq was skipped: re-read
 * `GET /api/logs?after=<gapAfter>` and pass the answer to `ingestPage`.
 *
 * Cost: a busy night logs many lines a second and the views hold up to
 * 5 000. The buffer changes at once, but `version` (what views depend on)
 * moves at most once per animation frame, so a burst of lines costs one
 * re-render, not one per line; and `filtered()` is computed once per
 * (version, filter), so the Connection log, its controls and the drawer
 * share the same result.
 */

import { isBoolean, loadPref, savePref } from './prefs';
import {
  type LevelFilter,
  LOG_CAP,
  LogBuffer,
  type LogFilterSpec,
  type LogInput,
  type LogLevel,
  type LogRecord,
  isProblem,
  matchesLog,
  parseLogRecord,
  type PushResult,
} from './log';

export interface LogPageLike {
  entries?: unknown;
  truncated?: unknown;
}

export class LogStore {
  /** Bumped on every change: read it to depend on the log. */
  version = $state(0);
  /** uid of the newest line the observer has seen (drawer open on the Log tab). */
  private seenUid = $state(0);
  /** The server had already dropped lines older than what this client holds. */
  truncated = $state(false);
  private readonly buffer: LogBuffer;
  /** A version bump is scheduled for the next animation frame. */
  private bumpPending = false;
  /** What the cached views were computed from: version and buffer state. */
  private cacheStamp = '';
  private readonly cache = new Map<string, LogRecord[]>();

  constructor(cap: number = LOG_CAP) {
    this.buffer = new LogBuffer(cap);
  }

  /**
   * Tell the views the log changed: once per animation frame in a browser,
   * at once elsewhere (tests, a hidden tab's timers still bump on the next
   * frame it paints).
   */
  private bump(): void {
    if (typeof requestAnimationFrame !== 'function') {
      this.version++;
      return;
    }
    if (this.bumpPending) return;
    this.bumpPending = true;
    requestAnimationFrame(() => {
      this.bumpPending = false;
      this.version++;
    });
  }

  get cap(): number {
    return this.buffer.cap;
  }

  /** The lines, oldest first (re-read when `version` changes). */
  get entries(): readonly LogRecord[] {
    void this.version;
    return this.buffer.entries();
  }

  get length(): number {
    void this.version;
    return this.buffer.length;
  }

  get dropped(): number {
    void this.version;
    return this.buffer.dropped;
  }

  /** uid of the newest line (0 when none): views count newer lines as new. */
  get lastUid(): number {
    void this.version;
    return this.buffer.lastUid;
  }

  get lastSeq(): number | null {
    void this.version;
    return this.buffer.lastSeq;
  }

  /** A server log line (WS message or LogPage entry). Unknown shapes are ignored. */
  ingest(raw: unknown): PushResult {
    const input = parseLogRecord(raw);
    if (!input) return { added: false, gap: false, gapAfter: null };
    return this.add(input);
  }

  /** The answer of `GET /api/logs`: lines oldest first. */
  ingestPage(page: LogPageLike): number {
    let added = 0;
    if (Array.isArray(page.entries)) {
      for (const raw of page.entries) {
        const input = parseLogRecord(raw);
        if (input && this.buffer.push(input).added) added++;
      }
    }
    if (page.truncated === true) this.truncated = true;
    if (added) this.bump();
    return added;
  }

  /** A line written by this client (a failed request, a local event). */
  push(
    level: LogLevel,
    message: string,
    opts: { topic?: string | null; source?: string | null; t?: string } = {},
  ): void {
    this.add({
      level,
      message,
      t: opts.t ?? new Date().toISOString(),
      topic: opts.topic ?? null,
      source: opts.source ?? null,
      local: true,
    });
  }

  add(input: LogInput): PushResult {
    const result = this.buffer.push(input);
    if (result.added) this.bump();
    return result;
  }

  /**
   * The server process changed (its `boot_id`): its log numbering starts
   * again at 1. A marker line separates the two processes' lines.
   */
  restart(): void {
    this.buffer.restart();
    this.version++;
  }

  /** Empty the view (the server keeps its log; a replay does not restore the lines). */
  clear(): void {
    this.buffer.clear();
    this.seenUid = this.buffer.lastUid;
    this.version++;
  }

  /** Warnings and errors that arrived since the log was last seen. */
  get unseenProblems(): number {
    void this.version;
    let n = 0;
    // Full scan: a line inserted late (gap filled) sits before newer ones.
    for (const r of this.buffer.entries()) if (r.uid > this.seenUid && isProblem(r.level)) n++;
    return n;
  }

  markSeen(): void {
    this.seenUid = this.buffer.lastUid;
  }

  /** The lines a view shows (shared between views with the same filter). */
  filtered(filter: LogFilterSpec): LogRecord[] {
    // The buffer may run ahead of `version` until the next frame: the stamp
    // includes its state, so a cached view never lags the buffer.
    const stamp = `${this.version}:${this.buffer.lastUid}:${this.buffer.length}:${this.buffer.epoch}`;
    if (stamp !== this.cacheStamp) {
      this.cache.clear();
      this.cacheStamp = stamp;
    }
    const key = `${filter.level}\u0000${filter.debug}\u0000${filter.query}\u0000${filter.topics?.join(',') ?? '*'}`;
    let lines = this.cache.get(key);
    if (!lines) {
      lines = this.buffer.entries().filter((r) => matchesLog(r, filter));
      this.cache.set(key, lines);
    }
    return lines;
  }

  /** How many lines of each level are held (for counts in filters). */
  counts(): Record<LogLevel, number> {
    void this.version;
    const out: Record<LogLevel, number> = { debug: 0, cmd: 0, info: 0, ok: 0, warning: 0, error: 0 };
    for (const r of this.buffer.entries()) out[r.level]++;
    return out;
  }
}

const isLevelFilter = (v: unknown): v is LevelFilter => v === 'all' || v === 'warnings' || v === 'errors';

/**
 * What one log view shows: level filter, debug lines, search text, topics.
 * The level choice and the debug toggle are remembered per viewer under
 * `persist` (e.g. "argos.log.filter"); the search text is not.
 */
export class LogFilter implements LogFilterSpec {
  level: LevelFilter = $state('all');
  debug = $state(false);
  query = $state('');
  /** Topics kept (null = every topic); the Connection log switches it (L). */
  topics: readonly string[] | null = $state.raw(null);
  private readonly persist: string | null;

  constructor(opts: { topics?: readonly string[] | null; persist?: string | null; level?: LevelFilter } = {}) {
    this.topics = opts.topics ?? null;
    this.persist = opts.persist ?? null;
    this.level = this.persist ? loadPref(`${this.persist}.level`, isLevelFilter, opts.level ?? 'all') : (opts.level ?? 'all');
    this.debug = this.persist ? loadPref(`${this.persist}.debug`, isBoolean, false) : false;
  }

  setLevel(level: LevelFilter): void {
    this.level = level;
    if (this.persist) savePref(`${this.persist}.level`, level);
  }

  setDebug(on: boolean): void {
    this.debug = on;
    if (this.persist) savePref(`${this.persist}.debug`, on);
  }

  /** A plain snapshot (for $derived computations and tests). */
  get spec(): LogFilterSpec {
    return { level: this.level, debug: this.debug, query: this.query, topics: this.topics };
  }
}
