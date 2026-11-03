/**
 * Undo after an immediate change (web/spec/README.md 3.3 and 3.8): a
 * reversible action (remove a saved site, reset a setting to its default,
 * remove a step) is applied at once, and a toast offers Undo for a few
 * seconds (6 s by default) instead of asking first.
 *
 * - The window pauses while the pointer is over the toast or focus is in it
 *   (WCAG 2.2.1: the observer can take the time they need), and resumes
 *   with the time that was left.
 * - Undo runs the caller's inverse once; a failure keeps the toast with the
 *   server's words until it is dismissed (an undo that silently failed
 *   would leave the observer believing the change was reverted).
 * - Pure state + timers (an injectable clock), no DOM; unit-tested.
 *   UndoToast.svelte draws one entry, UndoToasts.svelte a queue.
 */

import { refusalText } from './commit.svelte';

export const UNDO_MS = 6000;
/** How long "Undone" stays before the toast leaves. */
export const UNDONE_MS = 1500;
/** At most this many undo toasts at once; the oldest is committed (dropped). */
export const MAX_UNDO = 3;

export type UndoState = 'open' | 'undoing' | 'undone' | 'failed';

export interface UndoRequest {
  /** What was done, in words ("Removed the saved site Paris"). */
  title: string;
  detail?: string;
  /** The inverse; reject with the server's words when it cannot be undone. */
  undo: () => Promise<unknown> | unknown;
  durationMs?: number;
}

export interface UndoEntry {
  id: number;
  title: string;
  detail: string | null;
  state: UndoState;
  error: string | null;
  durationMs: number;
  /** ms left when paused, else null. */
  pausedLeft: number | null;
  /** Clock time when the window ends (meaningful while not paused). */
  endsAt: number;
}

export interface UndoClock {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

const realClock: UndoClock = {
  now: () => performance.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

export class UndoQueue {
  entries: UndoEntry[] = $state([]);

  private nextId = 1;
  private readonly clock: UndoClock;
  private readonly inverses = new Map<number, UndoRequest['undo']>();
  private readonly timers = new Map<number, unknown>();

  constructor(clock: UndoClock = realClock) {
    this.clock = clock;
  }

  /** Offer Undo for a change that has already been applied. */
  push(req: UndoRequest): number {
    const id = this.nextId++;
    const durationMs = req.durationMs ?? UNDO_MS;
    const entry: UndoEntry = {
      id,
      title: req.title,
      detail: req.detail ?? null,
      state: 'open',
      error: null,
      durationMs,
      pausedLeft: null,
      endsAt: this.clock.now() + durationMs,
    };
    this.inverses.set(id, req.undo);
    this.entries = [...this.entries, entry];
    while (this.entries.filter((e) => e.state === 'open').length > MAX_UNDO) {
      const oldest = this.entries.find((e) => e.state === 'open');
      if (!oldest) break;
      this.dismiss(oldest.id);
    }
    this.arm(id, durationMs);
    return id;
  }

  private find(id: number): UndoEntry | undefined {
    return this.entries.find((e) => e.id === id);
  }

  private patch(id: number, change: Partial<UndoEntry>): void {
    this.entries = this.entries.map((e) => (e.id === id ? { ...e, ...change } : e));
  }

  private arm(id: number, ms: number): void {
    this.disarm(id);
    this.timers.set(
      id,
      this.clock.setTimeout(() => this.dismiss(id), ms),
    );
  }

  private disarm(id: number): void {
    const t = this.timers.get(id);
    if (t !== undefined) this.clock.clearTimeout(t);
    this.timers.delete(id);
  }

  /** Fraction of the window elapsed (0..1), for the time ring. */
  elapsed(id: number, now = this.clock.now()): number {
    const e = this.find(id);
    if (!e) return 1;
    const left = e.pausedLeft ?? Math.max(0, e.endsAt - now);
    return e.durationMs > 0 ? Math.min(1, Math.max(0, 1 - left / e.durationMs)) : 1;
  }

  /** Whole seconds left ("6 s"), rounded up. */
  secondsLeft(id: number, now = this.clock.now()): number {
    const e = this.find(id);
    if (!e) return 0;
    const left = e.pausedLeft ?? Math.max(0, e.endsAt - now);
    return Math.ceil(left / 1000);
  }

  /** Pointer over the toast or focus inside: the window stops running. */
  pause(id: number): void {
    const e = this.find(id);
    if (!e || e.state !== 'open' || e.pausedLeft !== null) return;
    this.disarm(id);
    this.patch(id, { pausedLeft: Math.max(0, e.endsAt - this.clock.now()) });
  }

  resume(id: number): void {
    const e = this.find(id);
    if (!e || e.state !== 'open' || e.pausedLeft === null) return;
    const left = e.pausedLeft;
    this.patch(id, { pausedLeft: null, endsAt: this.clock.now() + left });
    this.arm(id, left);
  }

  /** Run the inverse. Resolves true when undone. */
  async undo(id: number): Promise<boolean> {
    const e = this.find(id);
    const inverse = this.inverses.get(id);
    if (!e || !inverse || (e.state !== 'open' && e.state !== 'failed')) return false;
    this.disarm(id);
    this.patch(id, { state: 'undoing', error: null, pausedLeft: null });
    try {
      await inverse();
    } catch (err) {
      if (!this.find(id)) return false;
      this.patch(id, { state: 'failed', error: refusalText(err) });
      return false;
    }
    if (!this.find(id)) return true;
    this.inverses.delete(id);
    this.patch(id, { state: 'undone' });
    this.timers.set(
      id,
      this.clock.setTimeout(() => this.remove(id), UNDONE_MS),
    );
    return true;
  }

  /** The change stays (the window ran out, or the observer closed the toast). */
  dismiss(id: number): void {
    const e = this.find(id);
    if (!e || e.state === 'undoing') return;
    this.remove(id);
  }

  private remove(id: number): void {
    this.disarm(id);
    this.inverses.delete(id);
    this.entries = this.entries.filter((e) => e.id !== id);
  }

  dispose(): void {
    for (const id of [...this.timers.keys()]) this.disarm(id);
    this.inverses.clear();
    this.entries = [];
  }
}
