/**
 * Mount jog: the pure part of JogPad.svelte, unit-tested. Promoted from
 * src/lab/controls/jog.ts (web/lab/PROPOSAL.md 3.3 and 6, W3) and extended
 * with the client side of the server's dead-man (argos/server/protocol.md
 * "Mount: geometry, jog with a dead-man", A29-A30) and the 0.5.0 fix H3
 * (notes/release_0_5_0.md: "The jog dialog stops every axis it moves").
 *
 * - Two axes, tracked separately (H3): Alt+ and Az+ held together jog
 *   diagonally; releasing Alt+ stops altitude only. On one axis the newest
 *   press wins; releasing it falls back to the opposite direction if that is
 *   still held (no stuck axis, no surprise).
 * - Sources are named ("key:ArrowUp", "pointer:north") so a key and a pointer
 *   on the same direction release independently.
 * - Every command carries an increasing `seq`, taken from the transport
 *   (one counter per page, `nextSeq`) so a remounted pad never restarts at 0
 *   below what the server already saw (review of wave 3); the server compares
 *   numbers per axis and never drops a stop. Each moving axis is renewed
 *   every RENEW_MS with `renew: true` (a renewal never restarts an axis the
 *   server stopped), and never while the previous request of that axis is
 *   still unanswered; the server stops an axis not renewed within DEADMAN_MS,
 *   or when this client's event socket closes or sends {"type":"jog_stop"}.
 * - The server says how it handled each command (`jog_command`): an ignored
 *   one never refreshes the dead-man meter; a renewal ignored because the
 *   server stopped the axis stalls it; a start dropped as `late` (it waited
 *   behind a slow MoveAxis longer than the dead-man) is sent again once.
 * - stopAll() releases every hold and stops BOTH axes "whatever the server
 *   believes" (POST /api/mount/jog/stop without an axis, the Qt ■). A stop the
 *   HTTP layer could not deliver is retried (STOP_RETRIES, STOP_RETRY_MS);
 *   blur and a hidden tab also send the socket message, which does not wait
 *   for HTTP. The server itself retries a MoveAxis(…, 0) the driver refused
 *   (`stop_pending`).
 * - An axis the SERVER stopped while it was held (dead-man, socket) is
 *   stalled: it is not restarted by the next renewal (a renewal with the same
 *   rate would start it again); the observer releases and presses again.
 */

import type { JogAxis, MountAlignment, MountJogView } from './types';

export type Direction = 'north' | 'south' | 'east' | 'west';
export type { JogAxis };

/** Renewal period of a moving axis (protocol.md: "renews each moving axis every 250 ms"). */
export const RENEW_MS = 250;
/** The server's dead-man (protocol.md `deadman_s`: 1.0 s). */
export const DEADMAN_MS = 1000;
/** Undelivered stops are retried this many times, this far apart. */
export const STOP_RETRIES = 3;
export const STOP_RETRY_MS = 250;
/**
 * A server stop reported this soon after this client stopped the same axis
 * is taken for the echo of that stop (the event can arrive after a new press).
 */
export const OWN_STOP_ECHO_MS = 1000;

/**
 * N up, S down, W left, E right, as the Qt pad (manual_control_dialog.py:49-58).
 * Primary = azimuth (alt-az) or RA / hour angle (EQ); secondary = altitude or
 * declination; a positive rate is north / east (protocol.md "Axes").
 */
export const DIRECTIONS: Record<Direction, { axis: JogAxis; sign: 1 | -1; key: string }> = {
  north: { axis: 'secondary', sign: 1, key: 'ArrowUp' },
  south: { axis: 'secondary', sign: -1, key: 'ArrowDown' },
  east: { axis: 'primary', sign: 1, key: 'ArrowRight' },
  west: { axis: 'primary', sign: -1, key: 'ArrowLeft' },
};

export const AXES: readonly JogAxis[] = ['primary', 'secondary'];

export function directionOfKey(key: string): Direction | null {
  for (const [d, v] of Object.entries(DIRECTIONS)) if (v.key === key) return d as Direction;
  return null;
}

export interface KeyWords {
  /** Visible on the key ("Alt+", "N"). */
  short: string;
  /** Accessible name and tooltip ("Altitude +", "North"). */
  label: string;
}

/**
 * Words per direction from the mount's geometry (README Q-O4, accepted): on an
 * alt-az mount (the Seestar) the keys say which axis they drive, Alt+ / Alt−
 * / Az− / Az+; on an equatorial one N / S / W / E. Unknown geometry: the axis
 * words too (they are true on every mount; compass words are not).
 */
export function keyWords(alignment: MountAlignment | undefined): Record<Direction, KeyWords> {
  if (alignment === 'eq' || alignment === 'eq_gem') {
    return {
      north: { short: 'N', label: 'North' },
      south: { short: 'S', label: 'South' },
      west: { short: 'W', label: 'West' },
      east: { short: 'E', label: 'East' },
    };
  }
  return {
    north: { short: 'Alt+', label: 'Altitude +' },
    south: { short: 'Alt−', label: 'Altitude −' },
    west: { short: 'Az−', label: 'Azimuth −' },
    east: { short: 'Az+', label: 'Azimuth +' },
  };
}

/** The pad's own frame: equatorial axes on an EQ mount, alt-az otherwise (as the key words). */
export function isEquatorial(alignment: MountAlignment | undefined | null): boolean {
  return alignment === 'eq' || alignment === 'eq_gem';
}

/** Scales of the offset scope, degrees at the rim: the smallest that holds every point. */
export const SCOPE_RANGES = [2, 10, 45, 180] as const;

export function scopeRange(maxAbsDeg: number): number {
  for (const r of SCOPE_RANGES) if (maxAbsDeg <= r) return r;
  return SCOPE_RANGES[SCOPE_RANGES.length - 1];
}

const minus = (v: number) => (v < 0 ? '−' : '+');

/** ΔRA as time, compact like the ±7-character Az readout ("+12.4s", "−3m05s", "+1h08m"), from hours. */
export function formatDeltaRA(dHours: number): string {
  const t = Math.abs(dHours) * 3600;
  if (t < 60) return `${minus(dHours)}${t.toFixed(1)}s`;
  if (t < 3600) {
    const m = Math.floor(t / 60);
    return `${minus(dHours)}${m}m${String(Math.round(t - m * 60)).padStart(2, '0')}s`;
  }
  const h = Math.floor(t / 3600);
  return `${minus(dHours)}${h}h${String(Math.round((t - h * 3600) / 60)).padStart(2, '0')}m`;
}

/** ΔDec in arcminutes under a degree ("+3.2′"), else degrees ("−1.25°"). */
export function formatDeltaDec(dDeg: number): string {
  const a = Math.abs(dDeg);
  return a < 1 ? `${minus(dDeg)}${(a * 60).toFixed(1)}′` : `${minus(dDeg)}${a.toFixed(2)}°`;
}

export type JogRate = 'slow' | 'normal' | 'fast';

/** The Qt speeds (manual_control_dialog.py, protocol.md "The Qt speeds were 0.5, 2 and 5 °/s"). */
export const JOG_RATES: readonly { value: JogRate; label: string; deg: number }[] = [
  { value: 'slow', label: 'Slow', deg: 0.5 },
  { value: 'normal', label: 'Normal', deg: 2 },
  { value: 'fast', label: 'Fast', deg: 5 },
];

/** °/s of a rate id, never above the server's limit (max_rate_deg_s, 5). */
export function rateDeg(rate: JogRate, maxRate = 5): number {
  const deg = JOG_RATES.find((r) => r.value === rate)?.deg ?? 2;
  return Math.min(deg, maxRate > 0 ? maxRate : deg);
}

interface Hold {
  source: string;
  direction: Direction;
  at: number;
}

/** What is held right now, per axis (the newest hold of an axis wins). */
export class JogHolds {
  private holds: Hold[] = [];
  private n = 0;

  press(source: string, direction: Direction): void {
    this.holds = this.holds.filter((h) => h.source !== source);
    this.holds.push({ source, direction, at: ++this.n });
  }

  release(source: string): void {
    this.holds = this.holds.filter((h) => h.source !== source);
  }

  releaseAll(): void {
    this.holds = [];
  }

  has(source: string): boolean {
    return this.holds.some((h) => h.source === source);
  }

  /** Signed direction of an axis: +1, −1 or 0. */
  sign(axis: JogAxis): -1 | 0 | 1 {
    let best: Hold | null = null;
    for (const h of this.holds) {
      if (DIRECTIONS[h.direction].axis !== axis) continue;
      if (!best || h.at > best.at) best = h;
    }
    return best ? DIRECTIONS[best.direction].sign : 0;
  }

  /** The direction an axis is held in, if any. */
  active(axis: JogAxis): Direction | null {
    return directionOf(axis, this.sign(axis));
  }

  get empty(): boolean {
    return this.holds.length === 0;
  }
}

export function directionOf(axis: JogAxis, sign: number): Direction | null {
  if (sign === 0) return null;
  const s = sign > 0 ? 1 : -1;
  return (Object.keys(DIRECTIONS) as Direction[]).find((d) => DIRECTIONS[d].axis === axis && DIRECTIONS[d].sign === s) ?? null;
}

/** True when the server must have stopped the axis: no renewal within the dead-man window. */
export function deadmanExpired(lastRenew: number, now: number, limit = DEADMAN_MS): boolean {
  return now - lastRenew > limit;
}

/** Is the server moving `direction` now (its own report, not the finger)? */
export function reportedMoving(report: MountJogView | null | undefined, direction: Direction): boolean {
  if (!report) return false;
  const { axis, sign } = DIRECTIONS[direction];
  const r = report[axis];
  return typeof r === 'number' && r !== 0 && Math.sign(r) === sign;
}

/** Which axes a server `last_stop.axis` names ("primary", "secondary", or both). */
export function stoppedAxes(axis: string): JogAxis[] {
  if (axis === 'primary' || axis === 'secondary') return [axis];
  return ['primary', 'secondary'];
}

// -- The driver ------------------------------------------------------------------------------

/** How the server handled a jog command (protocol.md A30 `jog_command`). */
export interface JogCommandResult {
  outcome: 'started' | 'renewed' | 'pending' | 'ignored';
  why: 'stale' | 'stopped' | 'late' | null;
}

/** The `jog_command` of a jog answer, if the server sent one. */
export function commandOf(answer: unknown): JogCommandResult | null {
  const c = (answer as { jog_command?: JogCommandResult } | null | undefined)?.jog_command;
  return c && typeof c.outcome === 'string' ? c : null;
}

/** Starts dropped as `late` are sent again at most this many times. */
export const LATE_RETRIES = 2;

/** The REST and socket calls of the jog (protocol.md A30). Rejections carry the server's words. */
export interface JogTransport {
  /** POST /api/mount/jog {axis, rate_deg_s, client, seq, renew}: starts, or with the same rate renews. */
  start(axis: JogAxis, rateDegS: number, seq: number, renew?: boolean): Promise<unknown>;
  /** The page-wide command counter (shared by every pad of the page); a local one otherwise. */
  nextSeq?(): number;
  /** POST /api/mount/jog/stop {axis?, client, seq}: null stops both axes whatever the server believes. */
  stop(axis: JogAxis | null, seq: number): Promise<unknown>;
  /** Send {"type":"jog_stop"} on /ws/events: stops every axis of this client without HTTP. */
  socketStop?(): void;
}

export interface JogTimers {
  now(): number;
  setInterval(fn: () => void, ms: number): unknown;
  clearInterval(id: unknown): void;
  setTimeout(fn: () => void, ms: number): unknown;
}

const realTimers: JogTimers = {
  now: () => (typeof performance !== 'undefined' ? performance.now() : Date.now()),
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: (id) => clearInterval(id as ReturnType<typeof setInterval>),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
};

export type StopReason = 'release' | 'button' | 'escape' | 'blur' | 'hidden' | 'socket' | 'disarm' | 'blocked' | 'dispose';

function wordsOf(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return 'no answer';
}

/**
 * Turns holds into commands. One per pad. `onchange` fires after every state
 * change the pad draws (sent rates, stalls, messages).
 */
export class JogDriver {
  readonly holds = new JogHolds();
  /** °/s applied to new and moving axes. */
  rate = 2;
  /** What this client asked the server for, per axis (0 = stop sent). */
  readonly sent: Record<JogAxis, number> = { primary: 0, secondary: 0 };
  /** When the server last answered a start or renewal of the axis (its dead-man clock). */
  readonly renewedAt: Record<JogAxis, number> = { primary: 0, secondary: 0 };
  /** The held value that the server refused or stopped: not resent until the hold changes. */
  readonly stalled: Record<JogAxis, number> = { primary: 0, secondary: 0 };
  /** The last problem in words (a refused start, a stop not delivered, a server stop). */
  message: string | null = null;
  /** 'error' for a stop that could not be delivered, else 'info'. */
  messageKind: 'info' | 'error' = 'info';

  private seq = 0;
  /** A request of this axis is unanswered: no renewal is queued behind it. */
  private readonly inflight: Record<JogAxis, boolean> = { primary: false, secondary: false };
  private timer: unknown = null;
  private readonly ownStopAt: Record<JogAxis, number> = { primary: -Infinity, secondary: -Infinity };
  private lastStopKey: string | null | undefined = undefined;
  private disposed = false;

  constructor(
    private transport: JogTransport,
    private onchange: () => void = () => {},
    private timers: JogTimers = realTimers,
  ) {}

  get moving(): boolean {
    return this.sent.primary !== 0 || this.sent.secondary !== 0;
  }

  /** Age of the oldest renewal among the moving axes (ms), or null when nothing moves. */
  renewalAge(now = this.timers.now()): number | null {
    let oldest: number | null = null;
    for (const a of AXES) {
      if (this.sent[a] === 0) continue;
      oldest = oldest === null ? this.renewedAt[a] : Math.min(oldest, this.renewedAt[a]);
    }
    return oldest === null ? null : Math.max(0, now - oldest);
  }

  press(source: string, direction: Direction): void {
    if (this.disposed) return;
    this.holds.press(source, direction);
    this.apply();
  }

  release(source: string): void {
    this.holds.release(source);
    this.apply();
  }

  setRate(deg: number): void {
    if (deg === this.rate) return;
    this.rate = deg;
    this.apply();
  }

  /** Release everything and stop both axes; blur and a hidden tab also use the socket path. */
  stopAll(reason: StopReason): void {
    this.holds.releaseAll();
    for (const a of AXES) this.stalled[a] = 0;
    const wasMoving = this.moving;
    this.sent.primary = 0;
    this.sent.secondary = 0;
    this.syncTimer();
    if (reason === 'blur' || reason === 'hidden' || reason === 'socket' || reason === 'dispose') {
      if (wasMoving) this.transport.socketStop?.();
    }
    // The pad's stop button and Esc always send (the Qt ■: both axes, whatever is believed);
    // the automatic paths send only when this client moved something.
    if (wasMoving || reason === 'button' || reason === 'escape') this.sendStop(null, 0);
    this.onchange();
  }

  /**
   * Reconcile with the server's report (MountState.jog). A new `last_stop`
   * on an axis this client is still driving, that the report shows stopped,
   * means the server stopped it (dead-man, Abort, Park, a GoTo from any
   * client): that axis is stalled until its hold changes, so the next
   * renewal (same rate = a start) cannot set it moving again. The echo of
   * this client's own recent stop is not one.
   */
  observe(report: MountJogView | null | undefined): void {
    const ls = report?.last_stop ?? null;
    const key = ls ? `${ls.t}|${ls.axis}|${ls.reason}` : null;
    if (this.lastStopKey === undefined) {
      this.lastStopKey = key; // the first report only sets the baseline
      return;
    }
    if (key === this.lastStopKey) return;
    this.lastStopKey = key;
    if (!ls) return;
    let changed = false;
    const now = this.timers.now();
    for (const a of stoppedAxes(ls.axis)) {
      if (this.sent[a] === 0) continue;
      if (report && report[a] !== 0) continue; // already moving again for this client
      if (now - this.ownStopAt[a] < OWN_STOP_ECHO_MS) continue;
      this.stalled[a] = this.sent[a];
      this.sent[a] = 0;
      changed = true;
    }
    if (changed) {
      this.message = `Jog stopped by the server: ${ls.reason}. Release and press again.`;
      this.messageKind = 'info';
      this.syncTimer();
      this.onchange();
    }
  }

  dispose(): void {
    if (this.moving) this.stopAll('dispose');
    this.disposed = true;
    this.syncTimer();
  }

  private apply(): void {
    for (const a of AXES) {
      const desired = this.holds.sign(a) * this.rate;
      if (this.stalled[a] !== 0 && desired !== this.stalled[a]) this.stalled[a] = 0;
      if (this.stalled[a] !== 0) continue;
      if (desired === this.sent[a]) continue;
      if (desired === 0) {
        this.sent[a] = 0;
        this.sendStop(a, 0);
      } else {
        const fresh = this.sent[a] === 0;
        this.sent[a] = desired;
        if (fresh) this.renewedAt[a] = this.timers.now();
        this.message = null;
        this.sendStart(a, desired);
      }
    }
    this.syncTimer();
    this.onchange();
  }

  private nextSeq(): number {
    return this.transport.nextSeq ? this.transport.nextSeq() : ++this.seq;
  }

  /** The server stopped (or dropped) this held axis: not restarted until its hold changes. */
  private stall(axis: JogAxis, rate: number, message: string): void {
    this.sent[axis] = 0;
    this.stalled[axis] = rate;
    this.message = message;
    this.messageKind = 'info';
    this.syncTimer();
    this.onchange();
  }

  private sendStart(axis: JogAxis, rate: number, late = 0): void {
    const seq = this.nextSeq();
    this.inflight[axis] = true;
    this.transport.start(axis, rate, seq).then(
      (answer) => {
        this.inflight[axis] = false;
        if (this.sent[axis] !== rate) return; // stopped or changed meanwhile
        const cmd = commandOf(answer);
        if (cmd?.outcome === 'ignored') {
          if (cmd.why === 'late' && late < LATE_RETRIES) {
            this.sendStart(axis, rate, late + 1); // waited behind a slow mount: press again
            return;
          }
          this.stall(axis, rate, `Jog not started: the server ignored the command (${cmd.why ?? 'unknown'}). Release and press again.`);
          return;
        }
        this.renewedAt[axis] = this.timers.now();
        this.onchange();
      },
      (err: unknown) => {
        this.inflight[axis] = false;
        if (this.sent[axis] !== rate) return;
        // Refused (parked, slewing, not connected) or not delivered: not resent until the hold changes.
        this.sent[axis] = 0;
        this.stalled[axis] = rate;
        this.message = `Jog refused: ${wordsOf(err)}`;
        this.messageKind = 'info';
        this.syncTimer();
        this.onchange();
      },
    );
  }

  private sendStop(axis: JogAxis | null, attempt: number): void {
    const seq = this.nextSeq();
    for (const a of axis === null ? AXES : [axis]) this.ownStopAt[a] = this.timers.now();
    this.transport.stop(axis, seq).then(
      () => {
        if (attempt > 0 && this.messageKind === 'error') {
          this.message = null;
          this.messageKind = 'info';
          this.onchange();
        }
      },
      (err: unknown) => {
        // Restarted meanwhile: the new start (a higher seq) wins; a retry would stop it.
        if (axis === null ? this.moving : this.sent[axis] !== 0) return;
        if (attempt + 1 < STOP_RETRIES) {
          this.timers.setTimeout(() => {
            if (axis === null ? this.moving : this.sent[axis] !== 0) return; // restarted while waiting
            this.sendStop(axis, attempt + 1);
          }, STOP_RETRY_MS);
          return;
        }
        this.message = `Stop not confirmed (${wordsOf(err)}). The server stops a jog within 1 s without renewal; use Abort on the Mount card if the mount still moves.`;
        this.messageKind = 'error';
        this.onchange();
      },
    );
  }

  private renew(): void {
    for (const a of AXES) {
      const rate = this.sent[a];
      if (rate === 0 || this.inflight[a]) continue; // never queue a renewal behind an unanswered request
      const seq = this.nextSeq();
      this.inflight[a] = true;
      this.transport.start(a, rate, seq, true).then(
        (answer) => {
          this.inflight[a] = false;
          if (this.sent[a] !== rate) return;
          const cmd = commandOf(answer);
          if (cmd?.outcome === 'ignored') {
            // 'stopped': the server stopped this axis (dead-man, Abort…); a renewal never restarts it.
            if (cmd.why === 'stopped') this.stall(a, rate, 'Jog stopped by the server. Release and press again.');
            return; // never refreshes the dead-man meter
          }
          this.renewedAt[a] = this.timers.now();
          this.onchange();
        },
        () => {
          this.inflight[a] = false;
          // A lost renewal is what the dead-man is for: the meter drains, the server stops the axis.
        },
      );
    }
  }

  /** Release every keyboard hold (macOS sends no keyup for other keys while Cmd is down). */
  releaseKeys(): void {
    let changed = false;
    for (const d of Object.keys(DIRECTIONS) as Direction[]) {
      const source = `key:${DIRECTIONS[d].key}`;
      if (this.holds.has(source)) {
        this.holds.release(source);
        changed = true;
      }
    }
    if (changed) this.apply();
  }

  private syncTimer(): void {
    const want = this.moving && !this.disposed;
    if (want && this.timer === null) this.timer = this.timers.setInterval(() => this.renew(), RENEW_MS);
    else if (!want && this.timer !== null) {
      this.timers.clearInterval(this.timer);
      this.timer = null;
    }
  }
}
