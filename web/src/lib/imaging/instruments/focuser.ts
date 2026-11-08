/**
 * Focuser and autofocus: the pure part of FocuserControl.svelte, unit-tested.
 * Promoted from src/lab/controls/instruments/FocuserControl.svelte (web/lab/
 * PROPOSAL.md 3.3 and 6, W3; spec 05 §2.2-2.4) onto the server's records
 * (argos/server/protocol.md "Focuser (A34, A35)" and "Autofocus (A36)") and
 * the 0.5.0 fixes (notes/release_0_5_0.md):
 *
 * - H10: Out, In, Go to and Move are refused while autofocus owns the
 *   focuser (also while a stopped autofocus returns to its start); Go to is
 *   bounded by MaxStep and never clamped (the server answers 400 out of
 *   range); a STEP past the travel end is clamped by the server and reported.
 * - D9 (owner): taps during a move are queued and sent as ONE move when the
 *   current one ends ("+300 queued"); no Move is sent while moving. The
 *   server keeps the queue (`queued`); this client also coalesces the taps
 *   made while one request is in flight (TapQueue), so a held In key sends
 *   one request at a time, never a burst.
 * - S23: Stop AF = cancel and return to the start; Halt = stop where it is,
 *   available whenever the focuser is connected, autofocus included.
 * - S22: the autofocus frames use the gain shown in the hint (the server
 *   applies it).
 */

import { fixed, int, seconds, signed, signedInt } from '../../format/number';
import type { AutofocusView, FocuserView } from './types';

/** Step sizes of the segmented control (spec 05 1.4 #1). */
export const FOCUS_STEPS: readonly number[] = [1, 10, 50, 100, 500, 1000];

/** Temperature change since the last autofocus that marks refocusing as due (lab rule of thumb). */
export const DRIFT_WARN_C = 1.5;

export function focuserOnline(f: FocuserView | null | undefined): boolean {
  return !!f && f.state !== 'disconnected' && f.position !== null && f.position !== undefined;
}

/** The autofocus record says the sweep (or its return to the start) still owns the focuser. */
export function autofocusActive(af: AutofocusView | null | undefined): boolean {
  return !!af && (af.state === 'running' || af.state === 'stopping');
}

/**
 * Where the focuser is going: the queued target, else the move in progress,
 * else the polled position. A step adds to this (protocol.md: "from the
 * queued or current target").
 */
export function commandedTarget(f: FocuserView): number | null {
  return f.queued ?? f.target ?? f.position ?? null;
}

/** Steps queued behind the move in progress (server queue + this client's taps in flight). */
export function queuedDelta(f: FocuserView, localPending = 0): number {
  const server = f.queued !== null && f.queued !== undefined && f.target !== null && f.target !== undefined ? f.queued - f.target : 0;
  return server + localPending;
}

/** Why manual motion (Out, In, Go to) cannot be sent now, or null. */
export function manualReason(f: FocuserView | null | undefined, af?: AutofocusView | null): string | null {
  if (!focuserOnline(f)) return 'Connect the focuser first';
  if (f!.locked_by === 'autofocus' || autofocusActive(af)) {
    return af?.state === 'stopping' ? 'Autofocus is returning the focuser to its start' : 'Autofocus owns the focuser';
  }
  if (f!.state === 'error') return f!.message ?? 'The focuser reports an error';
  return null;
}

/**
 * Why a step in `dir` cannot be sent: the common reason, or the travel end
 * already reached. A step that would pass the end is allowed: the server
 * clamps it to the end and says so (H10).
 */
export function stepReason(
  dir: 1 | -1,
  f: FocuserView | null | undefined,
  af?: AutofocusView | null,
  localPending = 0,
): string | null {
  const common = manualReason(f, af);
  if (common) return common;
  const base = (commandedTarget(f!) ?? 0) + localPending;
  if (dir < 0 && base <= 0) return 'At the travel limit 0';
  const max = f!.max_step;
  if (dir > 0 && max !== null && max !== undefined && base >= max) return `At the travel limit ${int(max)} (MaxStep)`;
  return null;
}

/** "0–100 000" (the Go to range, from MaxStep). */
export function travelText(f: FocuserView | null | undefined): string {
  const max = f?.max_step;
  return max === null || max === undefined ? '0–?' : `0–${int(max)}`;
}

export type BadgeTone = 'idle' | 'ok' | 'busy' | 'error' | 'active';

/** The Focuser card header badge (a word and a shape, never colour alone). */
export function focuserBadge(f: FocuserView | null | undefined, af?: AutofocusView | null): { tone: BadgeTone; label: string } {
  if (!f || f.state === 'disconnected') return { tone: 'idle', label: 'Offline' };
  if (f.state === 'error') return { tone: 'error', label: 'Error' };
  if (af?.state === 'running') return { tone: 'active', label: 'Autofocus' };
  if (af?.state === 'stopping') return { tone: 'busy', label: 'Returning' };
  if (f.state === 'moving') return { tone: 'busy', label: 'Moving' };
  if (af?.state === 'rejected') return { tone: 'error', label: 'Rejected' };
  if (af?.state === 'failed') return { tone: 'error', label: 'AF failed' };
  return { tone: 'ok', label: 'Ready' };
}

const STAGE_WORDS: Record<string, string> = { coarse: 'Coarse sweep', fine: 'Fine sweep', verify: 'Verifying', returning: 'Returning' };

/** Elapsed fraction of the sweep (step / total), or null. */
export function autofocusProgress(af: AutofocusView | null | undefined): number | null {
  if (!af || af.state !== 'running') return null;
  const total = af.total ?? 0;
  if (!(total > 0)) return 0;
  return Math.min(1, Math.max(0, (af.step ?? 0) / total));
}

export interface StatusLine {
  /** plain = --fg; muted = how it works; reason = why not; bad = what failed (danger dot). */
  kind: 'plain' | 'muted' | 'reason' | 'bad';
  text: string;
}

/** The autofocus frames, as the server takes them (spec 05 §2.3 D: the hidden coupling of P8, S22). */
export function afFramesText(frames: { exposure_s: number; gain: number } | null | undefined): string {
  if (!frames) return 'Autofocus frames: exposure and gain of the Camera card';
  return `AF frames: ${seconds(frames.exposure_s)}, gain ${int(frames.gain)}`;
}

/**
 * The one line under the actions: what the autofocus is doing or how it
 * ended, else the last command's result, else how the AF frames are taken.
 * Only "done" reads as a success (fixes P43: no "complete" after a cancel or
 * a rejection).
 */
export function focuserLine(
  f: FocuserView | null | undefined,
  af: AutofocusView | null | undefined,
  o: { lastResult?: string | null; lastError?: string | null; frames?: { exposure_s: number; gain: number } | null } = {},
): StatusLine {
  if (o.lastError) return { kind: 'bad', text: o.lastError };
  if (af?.state === 'running') {
    // One home per value (design review W3): the step, the samples and the vertex are the
    // Focus band's; the card says in words what the focuser is doing.
    const stage = (STAGE_WORDS[af.stage ?? ''] ?? 'Sweep').toLowerCase();
    return { kind: 'plain', text: `Autofocus ${stage}: the focuser moves on its own. Stop AF returns it to its start.` };
  }
  if (af?.state === 'stopping') {
    const to = af.start_position !== null && af.start_position !== undefined ? ` to ${int(af.start_position)}` : ' to the start';
    return { kind: 'plain', text: `Stopping autofocus: returning${to}…` };
  }
  if (o.lastResult) return { kind: 'plain', text: o.lastResult };
  if (af?.state === 'done' && af.best) {
    const b = af.best;
    const hfd = b.hfd_px !== null && b.hfd_px !== undefined ? `${fixed(b.hfd_px, 2)} px` : '—';
    const method = b.method && b.method !== 'none' ? ` · ${b.method}` : '';
    return { kind: 'plain', text: `Best focus ${hfd} at ${int(b.position)}${method} · measured` };
  }
  if (af?.state === 'rejected') return { kind: 'reason', text: af.message ?? 'Autofocus rejected: focus unchanged' };
  if (af?.state === 'cancelled') return { kind: 'plain', text: af.message ?? 'Autofocus cancelled' };
  if (af?.state === 'failed') return { kind: 'bad', text: af.message ?? 'Autofocus failed' };
  if (f?.state === 'error') return { kind: 'bad', text: f.message ?? 'The focuser reports an error' };
  if (!focuserOnline(f)) return { kind: 'muted', text: 'Connect the focuser to move it or run autofocus' };
  return { kind: 'muted', text: afFramesText(o.frames) };
}

/** The result of a step or a move in words ("Queued: +300, sent when the move ends"). */
export function commandText(r: { requested: number | null; sent: number | null; clamped: boolean; queued: boolean }, maxStep?: number | null): string | null {
  if (r.clamped) {
    const end = r.requested !== null && r.requested <= 0 ? '0' : maxStep !== null && maxStep !== undefined ? int(maxStep) : 'the travel end';
    return `Clamped to ${end}: the end of the travel (MaxStep)`;
  }
  if (r.queued && r.requested !== null) return `Queued: to ${int(r.requested)} when the move in progress ends`;
  return null;
}

/** Temperature change since the reference (the last autofocus), or null. */
export function driftSinceAf(now: number | null | undefined, atAf: number | null | undefined): number | null {
  if (now === null || now === undefined || atAf === null || atAf === undefined) return null;
  if (!Number.isFinite(now) || !Number.isFinite(atAf)) return null;
  return now - atAf;
}

export function driftText(drift: number | null): string {
  return drift === null ? '' : `${signed(drift, 1)} °C since AF`;
}

/**
 * Remembers the focuser temperature when an autofocus run ends `done` (the
 * record carries no temperature): the reference of "since AF". Keyed by
 * `run`, so the same ending is recorded once.
 */
export function afReference(
  prev: { run: number; temperature_c: number } | null,
  af: AutofocusView | null | undefined,
  f: FocuserView | null | undefined,
): { run: number; temperature_c: number } | null {
  if (!af || af.state !== 'done' || af.run === undefined) return prev;
  if (prev && prev.run === af.run) return prev;
  const t = f?.temperature_c;
  if (t === null || t === undefined || !Number.isFinite(t)) return prev;
  return { run: af.run, temperature_c: t };
}

/** "+300 queued" (signed, grouped; nothing when zero). */
export function queuedText(delta: number): string {
  return delta === 0 ? '' : `${signedInt(delta)} queued`;
}

/**
 * Coalesces taps while a request is in flight: the taps made meanwhile are
 * sent as one step when it answers (the server queues them behind a move in
 * progress, D9). A refused step drops the taps behind it (they were relative
 * to a refused one) and reports the refusal.
 */
export class TapQueue {
  /** Taps not yet sent. */
  pending = 0;
  /** The step on its way to the server (not yet in its record). */
  inflightDelta = 0;
  private inflight = false;

  constructor(
    private send: (delta: number) => Promise<unknown>,
    private onchange: () => void = () => {},
    private onresult: (r: unknown) => void = () => {},
    private onerror: (err: unknown) => void = () => {},
  ) {}

  get busy(): boolean {
    return this.inflight;
  }

  /** Taps the server's record does not hold yet: shown with its queue ("+300 queued"). */
  get unsent(): number {
    return this.pending + this.inflightDelta;
  }

  tap(delta: number): void {
    if (delta === 0) return;
    this.pending += delta;
    this.onchange();
    void this.flush();
  }

  /** Forget the taps not yet sent (Halt clears the queue). */
  clear(): void {
    this.pending = 0;
    this.onchange();
  }

  private async flush(): Promise<void> {
    if (this.inflight || this.pending === 0) return;
    const delta = this.pending;
    this.pending = 0;
    this.inflightDelta = delta;
    this.inflight = true;
    this.onchange();
    try {
      this.onresult(await this.send(delta));
    } catch (err) {
      this.pending = 0;
      this.onerror(err);
    } finally {
      this.inflight = false;
      this.inflightDelta = 0;
      this.onchange();
      void this.flush();
    }
  }
}
