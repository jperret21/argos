/**
 * The activity log, client side (web/spec/README.md sections 3.8 and 4.3 A2;
 * protocol.md "Logs (A2)"): one bounded buffer fed by the server's log lines
 * (v1 `{level, message, t}` and v2 `{id, seq, level, source, topic, message,
 * t}`) and by client-side failures, plus the pure helpers the log views use
 * (filters, UTC / local time, text export, follow / pause).
 *
 * - Levels: debug (hidden by default), cmd, info, ok, warning, error.
 * - Bounded: at most `cap` lines (5 000, the server ring's size); the oldest
 *   are dropped first and counted.
 * - No duplicates: a server line with a `seq` already held is ignored (the
 *   server replays its last 200 lines to every new socket); a v1 line
 *   without `seq` is recognised by (t, level, message).
 * - Order: server lines are kept in `seq` order even when a gap is filled
 *   later from `GET /api/logs?after=`; client lines stay where they arrived.
 * - Clear empties the view only: lines already received are not brought back
 *   by a replay.
 * - Server restart: a new server process numbers its lines from 1 again.
 *   The page learns it from the `boot_id` of the first `status` (API 2) and
 *   calls `restart()`. Without that id, two signs mean the same: a line whose
 *   `seq` is already held with another time or text, or a line whose `seq`
 *   is below the newest one, not held, and whose time is later than every
 *   line held (a gap fill or a reordered line is never later). Either way the
 *   buffer starts a new seq space (a marker line says so) instead of dropping
 *   the new server's lines as duplicates or burying them as late lines.
 */

export const SERVER_RESTART_TEXT = 'The ARGOS server restarted: the lines below come from the new server process.';

export const LOG_LEVELS = ['debug', 'cmd', 'info', 'ok', 'warning', 'error'] as const;
export type LogLevel = (typeof LOG_LEVELS)[number];

/** Short tags, as in the Qt log (CMD, INFO, OK, WARN, ERROR). */
export const LEVEL_TAGS: Record<LogLevel, string> = {
  debug: 'DEBUG',
  cmd: 'CMD',
  info: 'INFO',
  ok: 'OK',
  warning: 'WARN',
  error: 'ERROR',
};

export const LEVEL_NAMES: Record<LogLevel, string> = {
  debug: 'Debug',
  cmd: 'Command',
  info: 'Information',
  ok: 'Success',
  warning: 'Warning',
  error: 'Error',
};

/** Default client-side cap, equal to the server's ring (protocol.md A2). */
export const LOG_CAP = 5000;

export interface LogInput {
  level: LogLevel;
  message: string;
  /** ISO 8601 UTC. */
  t: string;
  /** Server sequence number (v2), null for v1 and client lines. */
  seq?: number | null;
  source?: string | null;
  topic?: string | null;
  /** Written by this client (a failed request), not by the server. */
  local?: boolean;
}

export interface LogRecord {
  /** Unique, increasing in arrival order: the key of keyed lists. */
  uid: number;
  seq: number | null;
  level: LogLevel;
  message: string;
  t: string;
  source: string | null;
  topic: string | null;
  local: boolean;
  /** Server process this line belongs to (bumped at each detected restart). */
  epoch: number;
  /** The line separating two server processes: shown in every view, whatever its topics. */
  marker?: boolean;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

const LEVEL_ALIASES: Record<string, LogLevel> = {
  warn: 'warning',
  critical: 'error',
  fatal: 'error',
  success: 'ok',
  command: 'cmd',
};

export function parseLevel(raw: unknown): LogLevel | null {
  if (typeof raw !== 'string') return null;
  const v = raw.toLowerCase();
  if ((LOG_LEVELS as readonly string[]).includes(v)) return v as LogLevel;
  return LEVEL_ALIASES[v] ?? null;
}

/**
 * One server log line (the WebSocket message, with or without its `type`, or
 * an entry of `GET /api/logs`), or null when it does not match the contract.
 */
export function parseLogRecord(raw: unknown): LogInput | null {
  if (!isObject(raw)) return null;
  if (raw.type !== undefined && raw.type !== 'log') return null;
  const level = parseLevel(raw.level);
  if (!level || typeof raw.message !== 'string') return null;
  const t = typeof raw.t === 'string' ? raw.t : new Date().toISOString();
  const seqRaw = raw.seq ?? raw.id;
  const seq = typeof seqRaw === 'number' && Number.isFinite(seqRaw) ? seqRaw : null;
  return {
    level,
    message: raw.message,
    t,
    seq,
    source: typeof raw.source === 'string' ? raw.source : null,
    topic: typeof raw.topic === 'string' ? raw.topic : null,
  };
}

export interface PushResult {
  added: boolean;
  /**
   * The line's seq jumps over lines this client never received: re-read
   * `GET /api/logs?after=<gapAfter>` to fill the hole.
   */
  gap: boolean;
  gapAfter: number | null;
  /** The line revealed a new server process (its seq space started again). */
  restarted?: boolean;
}

export class LogBuffer {
  readonly cap: number;
  /** Lines dropped because the buffer was full (oldest first). */
  dropped = 0;
  private items: LogRecord[] = [];
  private nextUid = 1;
  /** Held server seqs with their (time, text), to tell a replay from a restarted server. */
  private seenSeq = new Map<number, string>();
  private seenSeqOrder: number[] = [];
  /** Server process of the newest lines. */
  epoch = 0;
  private seenKeys = new Set<string>();
  private seenKeyOrder: string[] = [];
  /** Highest server seq received (kept across clear()). */
  lastSeq: number | null = null;
  /** Latest time (epoch ms) of a server line of the current process. */
  private newestServerMs: number | null = null;

  constructor(cap: number = LOG_CAP) {
    this.cap = Math.max(1, Math.floor(cap));
  }

  get length(): number {
    return this.items.length;
  }

  /** The lines, oldest first. Do not mutate. */
  entries(): readonly LogRecord[] {
    return this.items;
  }

  /** uid of the newest line, 0 when empty. */
  get lastUid(): number {
    return this.nextUid - 1;
  }

  private remember<T>(set: Set<T>, order: T[], value: T): void {
    set.add(value);
    order.push(value);
    if (order.length > 2 * this.cap) set.delete(order.shift()!);
  }

  private rememberSeq(seq: number, key: string): void {
    this.seenSeq.set(seq, key);
    this.seenSeqOrder.push(seq);
    if (this.seenSeqOrder.length > 2 * this.cap) this.seenSeq.delete(this.seenSeqOrder.shift()!);
  }

  /**
   * A new server process (its `boot_id` changed, or a line proved it): forget
   * the old seq space, keep its lines, and say so with a marker line when
   * lines of the old process are on screen.
   */
  restart(t: string = new Date().toISOString()): void {
    const held = this.lastSeq !== null;
    this.seenSeq.clear();
    this.seenSeqOrder = [];
    this.lastSeq = null;
    this.newestServerMs = null;
    this.epoch++;
    if (!held) return;
    this.items.push({
      uid: this.nextUid++,
      seq: null,
      level: 'warning',
      message: SERVER_RESTART_TEXT,
      t,
      source: 'web',
      topic: 'app',
      local: true,
      epoch: this.epoch,
      marker: true,
    });
  }

  push(input: LogInput): PushResult {
    const seq = input.seq ?? null;
    let restarted = false;
    const ms = Date.parse(input.t);
    if (seq !== null) {
      const held = this.seenSeq.get(seq);
      if (held !== undefined) {
        if (held === `${input.t}\u0000${input.message}`) return { added: false, gap: false, gapAfter: null };
        this.restart(input.t);
        restarted = true;
      } else if (
        this.lastSeq !== null &&
        seq < this.lastSeq &&
        this.newestServerMs !== null &&
        Number.isFinite(ms) &&
        ms > this.newestServerMs
      ) {
        // Numbered below lines already held, yet newer than all of them: a
        // new server process whose seq space started again (the old one
        // numbered more lines than this page remembers).
        this.restart(input.t);
        restarted = true;
      }
    } else if (!input.local) {
      const key = `${input.t}\u0000${input.level}\u0000${input.message}`;
      if (this.seenKeys.has(key)) return { added: false, gap: false, gapAfter: null };
      this.remember(this.seenKeys, this.seenKeyOrder, key);
    }
    const record: LogRecord = {
      uid: this.nextUid++,
      seq,
      level: input.level,
      message: input.message,
      t: input.t,
      source: input.source ?? null,
      topic: input.topic ?? null,
      local: !!input.local,
      epoch: this.epoch,
    };
    let gap = false;
    let gapAfter: number | null = null;
    if (seq !== null) {
      this.rememberSeq(seq, `${input.t}\u0000${input.message}`);
      if (Number.isFinite(ms) && (this.newestServerMs === null || ms > this.newestServerMs)) this.newestServerMs = ms;
      if (this.lastSeq !== null && seq > this.lastSeq + 1) {
        gap = true;
        gapAfter = this.lastSeq;
      }
      if (this.lastSeq === null || seq > this.lastSeq) {
        this.lastSeq = seq;
        this.items.push(record);
      } else {
        // A late line (gap filled from GET /api/logs): keep seq order, within
        // the lines of the same server process.
        let i = this.items.length;
        while (i > 0) {
          const prev = this.items[i - 1];
          if (prev.epoch !== this.epoch || (prev.seq !== null && prev.seq < seq)) break;
          i--;
        }
        this.items.splice(i, 0, record);
      }
    } else {
      this.items.push(record);
    }
    if (this.items.length > this.cap) {
      const excess = this.items.length - this.cap;
      this.items.splice(0, excess);
      this.dropped += excess;
    }
    return restarted ? { added: true, gap, gapAfter, restarted } : { added: true, gap, gapAfter };
  }

  /** Empty the view; lines already received stay known (a replay does not restore them). */
  clear(): void {
    this.items = [];
    this.dropped = 0;
  }
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

export type LevelFilter = 'all' | 'warnings' | 'errors';

export const LEVEL_FILTER_LABELS: Record<LevelFilter, string> = {
  all: 'All',
  warnings: 'Warnings',
  errors: 'Errors',
};

export interface LogFilterSpec {
  level: LevelFilter;
  /** Show debug lines (hidden by default, README 3.8). */
  debug: boolean;
  /** Case-insensitive text found in the message, source or topic. */
  query: string;
  /** Keep only these topics (the Connection log); null = every topic. */
  topics: readonly string[] | null;
}

export function levelVisible(level: LogLevel, filter: Pick<LogFilterSpec, 'level' | 'debug'>): boolean {
  switch (filter.level) {
    case 'errors':
      return level === 'error';
    case 'warnings':
      return level === 'warning' || level === 'error';
    default:
      return level !== 'debug' || filter.debug;
  }
}

export function matchesLog(r: LogRecord, filter: LogFilterSpec): boolean {
  if (!levelVisible(r.level, filter)) return false;
  // A restart marker belongs to every topic: the lines around it in any view changed process.
  if (filter.topics && !r.marker && (r.topic === null || !filter.topics.includes(r.topic))) return false;
  const q = filter.query.trim().toLowerCase();
  if (!q) return true;
  return (
    r.message.toLowerCase().includes(q) ||
    (r.source ?? '').toLowerCase().includes(q) ||
    (r.topic ?? '').toLowerCase().includes(q) ||
    LEVEL_TAGS[r.level].toLowerCase() === q
  );
}

export function filterLog(entries: readonly LogRecord[], filter: LogFilterSpec): LogRecord[] {
  return entries.filter((r) => matchesLog(r, filter));
}

export function isProblem(level: LogLevel): boolean {
  return level === 'warning' || level === 'error';
}

// ---------------------------------------------------------------------------
// Time and text
// ---------------------------------------------------------------------------

const pad = (n: number) => String(n).padStart(2, '0');

/** "21:34:05" in UTC (the log header says UTC, BRAND 5). */
export function utcClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--:--';
  return d.toISOString().slice(11, 19);
}

/** "2026-11-01 21:34:05 UTC". */
export function utcFull(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'unknown time';
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 19)} UTC`;
}

/**
 * Local time for the tooltip (Q-G18: UTC on screen, local time one hover
 * away): "22:34:05 local (UTC+01:00)". `offsetMin` is minutes east of UTC
 * (the opposite sign of Date.getTimezoneOffset), injectable for tests.
 */
export function localClock(iso: string, offsetMin?: number): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const off = offsetMin ?? -d.getTimezoneOffset();
  const local = new Date(d.getTime() + off * 60_000);
  const sign = off < 0 ? '−' : '+';
  const abs = Math.abs(off);
  const zone = `UTC${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
  const dayShift = local.getUTCDate() !== d.getUTCDate() ? ` ${local.toISOString().slice(0, 10)}` : '';
  return `${local.toISOString().slice(11, 19)} local${dayShift} (${zone})`;
}

/** One line of text per record, for Copy and Save as text. */
export function logLine(r: LogRecord): string {
  const where = r.source ? ` [${r.source}]` : '';
  return `${utcFull(r.t)}  ${LEVEL_TAGS[r.level].padEnd(5)}${where}  ${r.message}`;
}

export function logToText(entries: readonly LogRecord[]): string {
  return entries.map(logLine).join('\n') + (entries.length ? '\n' : '');
}

/** "argos-log-20261101T213405Z.txt". */
export function logFileName(now: Date = new Date()): string {
  const iso = now.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  return `argos-log-${iso}.txt`;
}

// ---------------------------------------------------------------------------
// Follow / pause
// ---------------------------------------------------------------------------

/** Within this many px of the bottom counts as "at the newest line". */
export const FOLLOW_SLACK_PX = 24;

export function isAtBottom(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
  slack: number = FOLLOW_SLACK_PX,
): boolean {
  return scrollHeight - scrollTop - clientHeight <= slack;
}

/**
 * Follow the newest line unless the observer scrolled up to read (fixes the
 * Qt log that jumped to the bottom on every line, 01 P28-P30). While paused,
 * the lines that arrived are counted for the "n new lines" button.
 */
export class FollowState {
  following = true;
  unseen = 0;

  /** The list was scrolled (by the observer or the browser). */
  scrolled(atBottom: boolean): void {
    this.following = atBottom;
    if (atBottom) this.unseen = 0;
  }

  /** `count` matching lines were appended. Returns true when the view should scroll to them. */
  appended(count: number): boolean {
    if (count <= 0) return false;
    if (this.following) return true;
    this.unseen += count;
    return false;
  }

  /** "Jump to the newest line". */
  jump(): void {
    this.following = true;
    this.unseen = 0;
  }
}
