/**
 * The one commit model of value fields (web/lab/PROPOSAL.md 3.3 "ScrubField",
 * BRAND 8 "Device value fields", README 3.4): nothing is sent per keystroke
 * or per pixel of drag; Enter, a released drag, blur or a settle pause after
 * arrow / wheel steps send ONE value. Every state is visible and double-coded
 * by the field that renders it:
 *
 *   idle       the field shows the applied value
 *   dirty      not sent: dashed edge, "Enter sends"
 *   sending    spinner in the unit slot, aria-busy
 *   applied    "Applied · <when it takes effect>" for `appliedMs`
 *   refused    the server's (device's) words; the field keeps the rejected
 *              value until Esc reverts it
 *
 * `invalid` (typed text that is not a value, or out of range: never clamped
 * silently) and `unavailable` (a reason) belong to the field, not to this
 * model, because they are about text, not values.
 *
 * Sync (README 3.4): a value that arrives from elsewhere (the `config` event
 * of another client, a device echo) replaces the shown value only while the
 * field holds nothing of its own; otherwise it is kept in `elsewhere` and the
 * field says "Changed elsewhere · Reload". The echo of our own commit is
 * recognised and never reported as a change from elsewhere.
 *
 * Promoted from the lab's ScrubField state (src/lab/controls/components/
 * ScrubField.svelte); pure state + timers, no DOM, unit-tested.
 */

export type CommitPhase = 'idle' | 'dirty' | 'sending' | 'applied' | 'refused';

export interface CommitOptions<T> {
  /**
   * Send one value; reject (or throw) with the server's words to refuse it.
   * Without it the value is applied at once (a local preference, a display
   * value) and the field never shows "Sending" or "Applied".
   */
  send?: (v: T) => Promise<unknown> | unknown;
  /** Value equality (default Object.is; numbers compare by value). */
  equals?: (a: T, b: T) => boolean;
  /** How long "Applied" stays (default 2000 ms, README 3.4 "Saved for 2 s"). */
  appliedMs?: number;
  /** Called once a value is applied (after `send` resolved). */
  onapplied?: (v: T) => void;
}

/** The observer-facing text of a refusal (an ApiError, an Error, a string). */
export function refusalText(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'string' && err) return err;
  if (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string') {
    return err.message;
  }
  return 'The server refused this value';
}

/** One value on its way to the server, and who waits for its answer. */
interface Pending<T> {
  v: T;
  done: ((ok: boolean) => void)[];
}

export class CommitModel<T> {
  /** The last value known to be applied (server, device or caller). */
  value: T = $state() as T;
  /** What the field holds when it is not `value` (typed, stepped, refused). */
  draft: T | null = $state(null);
  hasDraft = $state(false);
  phase: CommitPhase = $state('idle');
  /** The server's words for the last refusal. */
  refused: string | null = $state(null);
  /** A newer value from elsewhere, kept while the field holds its own. */
  elsewhere: { v: T } | null = $state(null);

  private readonly opts: CommitOptions<T>;
  private settleTimer: ReturnType<typeof setTimeout> | null = null;
  private appliedTimer: ReturnType<typeof setTimeout> | null = null;
  /** Increments on revert / refuse / dispose: an answer still on its way no longer changes the field. */
  private ticket = 0;
  /**
   * The value on its way (one request at a time) and the one committed while
   * it was (sent once the first is answered, so the server ends with the last
   * commit: two concurrent PATCHes could arrive out of order). Kept apart from
   * the draft: the observer may edit again while a value is in flight.
   */
  private sendingValue: Pending<T> | null = null;
  private queued: Pending<T> | null = null;

  constructor(initial: T, opts: CommitOptions<T> = {}) {
    this.value = initial;
    this.opts = opts;
  }

  private eq(a: T, b: T): boolean {
    return this.opts.equals ? this.opts.equals(a, b) : Object.is(a, b) || a === b;
  }

  /** The value the field shows: its own draft, else the applied value. */
  get current(): T {
    return this.hasDraft ? (this.draft as T) : this.value;
  }

  get busy(): boolean {
    return this.phase === 'sending';
  }

  /** What the server will hold once the requests on their way are answered (null: none). */
  private target(): Pending<T> | null {
    return this.queued ?? this.sendingValue;
  }

  private clearSettle(): void {
    if (this.settleTimer !== null) clearTimeout(this.settleTimer);
    this.settleTimer = null;
  }

  private clearApplied(): void {
    if (this.appliedTimer !== null) clearTimeout(this.appliedTimer);
    this.appliedTimer = null;
  }

  private wait(p: Pending<T>): Promise<boolean> {
    return new Promise((resolve) => p.done.push(resolve));
  }

  private static settle<V>(p: Pending<V> | null, ok: boolean): void {
    if (!p) return;
    for (const d of p.done.splice(0)) d(ok);
  }

  /** Forget what is on its way (revert, refuse, dispose): its answer is ignored. */
  private drop(): void {
    this.ticket++;
    CommitModel.settle(this.queued, false);
    this.queued = null;
    this.sendingValue = null;
  }

  /** The field now holds `v` (typed or stepped); nothing is sent. */
  edit(v: T): void {
    this.clearSettle();
    this.clearApplied();
    this.refused = null;
    const target = this.target();
    if (target) {
      // A value is on its way: compare with it, not with the applied value
      // (going back to the applied value is a change once it lands).
      this.draft = v;
      this.hasDraft = true;
      this.phase = this.eq(v, target.v) ? 'sending' : 'dirty';
      return;
    }
    if (this.eq(v, this.value)) {
      this.draft = null;
      this.hasDraft = false;
      this.phase = 'idle';
      return;
    }
    this.draft = v;
    this.hasDraft = true;
    this.phase = 'dirty';
  }

  /** Hold `v` and send it after `settleMs` without a further change (null: only on commit()). */
  offer(v: T, settleMs: number | null): void {
    this.edit(v);
    if (settleMs !== null && this.hasDraft && this.phase === 'dirty') {
      this.settleTimer = setTimeout(() => {
        this.settleTimer = null;
        void this.commit();
      }, settleMs);
    }
  }

  /** Text that is not a value: the field is "not what the device has", nothing to send. */
  markDirty(): void {
    this.clearSettle();
    this.clearApplied();
    this.refused = null;
    this.phase = 'dirty';
  }

  /**
   * Send `v` (default: the draft). Resolves true when applied, false when
   * refused or superseded; an unchanged value just returns to idle. While a
   * value is on its way the new one waits for its answer, then is sent.
   */
  async commit(v?: T): Promise<boolean> {
    this.clearSettle();
    const next = v !== undefined ? v : this.hasDraft ? (this.draft as T) : this.value;
    const target = this.target();
    if (target) {
      this.clearApplied();
      this.refused = null;
      this.draft = next;
      this.hasDraft = true;
      this.phase = 'sending';
      if (this.eq(next, target.v)) return this.wait(target); // already on its way
      CommitModel.settle(this.queued, false); // superseded before it was sent
      if (this.sendingValue && this.eq(next, this.sendingValue.v)) {
        this.queued = null;
        return this.wait(this.sendingValue);
      }
      this.queued = { v: next, done: [] };
      return this.wait(this.queued);
    }
    if (this.eq(next, this.value)) {
      // Back to what is applied, nothing on its way: nothing to send (a refusal is dropped with it).
      this.draft = null;
      this.hasDraft = false;
      this.refused = null;
      this.phase = this.phase === 'applied' ? 'applied' : 'idle';
      return true;
    }
    this.clearApplied();
    this.refused = null;
    this.draft = next;
    this.hasDraft = true;
    if (!this.opts.send) {
      this.adopt(next);
      this.phase = 'idle';
      this.opts.onapplied?.(next);
      return true;
    }
    this.phase = 'sending';
    const first: Pending<T> = { v: next, done: [] };
    const answer = this.wait(first);
    void this.run(first, this.ticket);
    return answer;
  }

  /** Sends `entry`, then whatever was committed meanwhile, one request at a time. */
  private async run(entry: Pending<T>, ticket: number): Promise<void> {
    const send = this.opts.send!;
    for (;;) {
      this.sendingValue = entry;
      let ok = true;
      let err: unknown = null;
      try {
        await send(entry.v);
      } catch (e) {
        ok = false;
        err = e;
      }
      if (ticket !== this.ticket) {
        CommitModel.settle(entry, false); // reverted, refused or disposed meanwhile
        return;
      }
      this.sendingValue = null;
      if (ok) {
        this.value = entry.v;
        if (this.elsewhere && this.eq(this.elsewhere.v, entry.v)) this.elsewhere = null;
      }
      const queued = this.queued;
      this.queued = null;
      if (queued) {
        CommitModel.settle(entry, ok); // its own answer; the newer commit decides the field
        if (!this.eq(queued.v, this.value)) {
          entry = queued;
          continue;
        }
        this.finish(queued, true, null, false); // the newer commit is what is applied now
        return;
      }
      this.finish(entry, ok, err, true);
      return;
    }
  }

  private finish(entry: Pending<T>, ok: boolean, err: unknown, sent: boolean): void {
    if (!ok) {
      if (this.hasDraft && this.phase === 'dirty' && !this.eq(this.draft as T, entry.v)) {
        // Edited again while it was on its way: the newer draft stays, not sent.
        CommitModel.settle(entry, false);
        return;
      }
      this.refused = refusalText(err);
      this.phase = 'refused'; // the field keeps the rejected value until Esc
      CommitModel.settle(entry, false);
      return;
    }
    if (this.hasDraft && !this.eq(this.draft as T, entry.v)) {
      // Edited while it was on its way: keep the newer draft (Enter or blur sends it).
      this.phase = 'dirty';
    } else {
      this.draft = null;
      this.hasDraft = false;
      this.phase = sent ? 'applied' : 'idle';
      if (sent) {
        this.appliedTimer = setTimeout(() => {
          this.appliedTimer = null;
          if (this.phase === 'applied') this.phase = 'idle';
        }, this.opts.appliedMs ?? 2000);
      }
    }
    if (sent) this.opts.onapplied?.(entry.v);
    CommitModel.settle(entry, true);
  }

  private adopt(v: T): void {
    this.value = v;
    this.draft = null;
    this.hasDraft = false;
    if (this.elsewhere && this.eq(this.elsewhere.v, v)) this.elsewhere = null;
  }

  /** Esc: back to the applied value (the newer one from elsewhere when there is one). */
  revert(): void {
    this.clearSettle();
    this.drop(); // an answer still on its way no longer changes the field
    if (this.elsewhere) this.value = this.elsewhere.v;
    this.elsewhere = null;
    this.draft = null;
    this.hasDraft = false;
    this.refused = null;
    this.phase = 'idle';
  }

  /** A value from outside (bound prop, `config` event, device echo). */
  sync(external: T): void {
    const target = this.target();
    if (target && (this.eq(external, target.v) || (this.sendingValue && this.eq(external, this.sendingValue.v)))) {
      return; // our own echo
    }
    if (this.hasDraft && this.eq(external, this.draft as T)) {
      // The server now holds what the field shows (applied elsewhere or echoed).
      if (this.phase !== 'sending' && !target) {
        this.adopt(external);
        if (this.phase !== 'applied') this.phase = 'idle';
        this.refused = null;
      }
      return;
    }
    if (this.eq(external, this.value)) {
      this.elsewhere = null;
      return;
    }
    if (this.hasDraft || this.phase === 'sending' || this.phase === 'refused' || target) {
      this.elsewhere = { v: external };
      return;
    }
    this.value = external;
    this.elsewhere = null;
  }

  /** "Reload": take the value that changed elsewhere, dropping the field's own. */
  reload(): void {
    if (!this.elsewhere) return;
    const v = this.elsewhere.v;
    this.revert();
    this.value = v;
  }

  /** A refusal that came from outside (one PATCH for several keys). */
  refuse(message: string): void {
    this.clearSettle();
    this.drop();
    this.refused = message;
    this.phase = 'refused';
  }

  dispose(): void {
    this.clearSettle();
    this.clearApplied();
    this.drop();
  }
}
