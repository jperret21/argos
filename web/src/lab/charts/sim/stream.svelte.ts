/**
 * The lab's simulated clock and the live frame stream it reveals.
 *
 * - The whole night is synthesized once (night.ts); "live" means the clock
 *   reveals the frames whose time has come. Charts read `subarray(0, n)`
 *   views of the columns: no copy, no Svelte proxy on thousands of numbers
 *   (stack-capabilities 2.1). Only `n` and `now` are reactive, for text.
 * - Charts subscribe with onAppend() and coalesce updates to one setData per
 *   animation frame (several frames may land between two paints at x600).
 * - `stalled` stops revealing frames while the clock runs: the "no new
 *   frame" state the Conditions now-line and the age chips must make visible.
 */

import { FAST_CADENCE, REAL_CADENCE, RUN_END, RUN_START, schedule, synthesizeNight, type NightColumns } from './night';

export type Speed = 1 | 10 | 60 | 600;

type Listener = (n: number, previous: number) => void;

export class FrameStream {
  readonly cols: NightColumns;
  n = $state(0);
  private listeners = new Set<Listener>();

  constructor(cols: NightColumns) {
    this.cols = cols;
  }

  get total(): number {
    return this.cols.n;
  }

  /** Reveal every frame with t <= now (or rewind). Returns true when n changed. */
  revealUntil(now: number): boolean {
    const t = this.cols.t;
    let k = this.n;
    if (k > 0 && t[k - 1] > now) {
      while (k > 0 && t[k - 1] > now) k--;
    } else {
      while (k < this.cols.n && t[k] <= now) k++;
    }
    return this.setCount(k);
  }

  setCount(k: number): boolean {
    k = Math.max(0, Math.min(this.cols.n, k));
    if (k === this.n) return false;
    const prev = this.n;
    this.n = k;
    for (const l of this.listeners) l(k, prev);
    return true;
  }

  onAppend(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  /** Index of the last frame at or before t (or -1). */
  indexAt(t: number): number {
    const a = this.cols.t;
    let lo = 0;
    let hi = this.n - 1;
    if (hi < 0 || a[0] > t) return -1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (a[mid] <= t) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }
}

/** Median start-to-start interval of the last `k` frames, s. */
export function observedCadence(s: FrameStream, k = 15): number | null {
  const n = s.n;
  if (n < 3) return null;
  const a: number[] = [];
  for (let i = Math.max(1, n - k); i < n; i++) a.push(s.cols.t[i] - s.cols.t[i - 1]);
  a.sort((x, y) => x - y);
  return a[a.length >> 1];
}

class SimClock {
  /** Simulated UTC, unix seconds. */
  now = $state(Date.UTC(2026, 10, 1, 22, 41, 7) / 1000);
  speed = $state<Speed>(60);
  playing = $state(true);
  stalled = $state(false);
  readonly night: FrameStream;
  private raf = 0;
  private last = 0;
  private started = false;

  constructor() {
    this.night = new FrameStream(synthesizeNight(schedule(REAL_CADENCE)));
    this.night.revealUntil(this.now);
  }

  /** Start the clock loop (idempotent). */
  start(): void {
    if (this.started) return;
    this.started = true;
    this.last = performance.now();
    const loop = (ts: number) => {
      const dt = Math.min(0.5, (ts - this.last) / 1000);
      this.last = ts;
      if (this.playing) {
        this.now = Math.min(RUN_END + 1800, this.now + dt * this.speed);
        if (!this.stalled) this.night.revealUntil(this.now);
      }
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop(): void {
    cancelAnimationFrame(this.raf);
    this.started = false;
  }

  seek(t: number): void {
    this.now = Math.max(RUN_START - 1800, Math.min(RUN_END + 1800, t));
    this.night.revealUntil(this.now);
  }
}

export const clock = new SimClock();

/** The 4 s cadence stress run (~6 700 frames), built on first use. */
let fast: NightColumns | null = null;
export function fastNight(): NightColumns {
  fast ??= synthesizeNight(schedule(FAST_CADENCE), 17);
  return fast;
}

export const SCENES: { id: string; label: string; t: number }[] = [
  { id: 'start', label: '18:58', t: Date.UTC(2026, 10, 1, 18, 58, 20) / 1000 },
  { id: 'cloud', label: '21:12', t: Date.UTC(2026, 10, 1, 21, 12, 40) / 1000 },
  { id: 'focus', label: '22:41', t: Date.UTC(2026, 10, 1, 22, 41, 7) / 1000 },
  { id: 'late', label: '01:47', t: Date.UTC(2026, 10, 2, 1, 47, 30) / 1000 },
];
