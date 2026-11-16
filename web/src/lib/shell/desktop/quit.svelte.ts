/**
 * The quit flow of the desktop app (M18; 01 2.3.7, 2.4.1 "Quit", 2.4.3; A7): Quit (Mod+Q,
 * the Help menu, the title bar's close button, the app menu, the Dock) asks the server to
 * shut down; when something runs the server refuses with what (`409 busy`) and the Quit
 * dialog says so; "Quit ARGOS" there (a confirmation with text buttons, BRAND 7) forces it.
 * A shutdown under way shows the scrim with the server's stages, then the window closes.
 *
 * Phases:
 *   idle      nothing
 *   checking  the first `POST /api/app/shutdown {force: false}` is in flight (no UI yet:
 *             an idle server answers at once and the scrim follows)
 *   confirm   the Quit dialog: `busy` lists what runs; Cancel, or Quit ARGOS
 *   forcing   `{force: true}` in flight (the dialog's Quit ARGOS button is busy)
 *   stopping  the scrim: the server's stages (WS `shutdown`), each with its elapsed time;
 *             after STUCK_MS "Quit now" ends it at once (the shell stops the server)
 *   closing   the server is done (last stage, or the link closed): the shell is asked to
 *             exit; after CLOSE_STALL_MS the scrim says the window did not close
 *   remote    another client asked the server to shut down (stages shown, no request here)
 *   stopped   that server is gone; this page reconnects when it runs again (browser), or
 *             the crash notice offers Restart (desktop)
 *
 * Fallbacks, so the observer can always quit: a server without A7 (older than W8) is
 * checked against what the UI sees running (`activity`), and forcing then quits through
 * the shell (its SIGTERM is the graceful shutdown); a server that does not answer is gone,
 * so the window closes at once; any other refusal shows in the dialog, where Quit ARGOS
 * still quits.
 */

import { ApiError } from '../../api/client';
import type { BusyItem, ShutdownAnswer, ShutdownEvent } from '../../api/desktop';
import { busySentence, type LocalActivity, localBusy, stageLabel } from './words';

export type QuitPhase = 'idle' | 'checking' | 'confirm' | 'forcing' | 'stopping' | 'closing' | 'remote' | 'stopped';

export interface StageRow {
  id: string;
  label: string;
  /** Local clock (ms) when the stage began (null: planned, not reached yet) / ended. */
  from: number | null;
  to: number | null;
}

export interface QuitDeps {
  /** A7. */
  shutdown(force: boolean): Promise<ShutdownAnswer>;
  /** Ask the shell to exit (argos://quit); `now`: "Quit now", stop the server at once. */
  exit(now?: boolean): void;
  /** What the UI sees running (dialog words; the list when the server has no A7). */
  activity(): LocalActivity;
  /** Inside the desktop shell (Quit exists). */
  desktop: boolean;
  /** Clock (ms), injectable for tests. */
  now?: () => number;
}

/** After this long without the end of the shutdown, the scrim offers "Quit now". */
export const STUCK_MS = 20_000;
/** After this long in `closing`, the scrim says the window did not close. */
export const CLOSE_STALL_MS = 5_000;
/**
 * A local quit (stopping, closing) shows the scrim's panel only after this long: an idle
 * quit is over in about 0.5 s, and a panel up for a moment would be a modal flash (BRAND 9).
 * The app is inert at once (App.svelte).
 */
export const SCRIM_DELAY_MS = 400;

export class QuitFlow {
  phase: QuitPhase = $state('idle');
  /** What runs (dialog), already in words order. */
  busy: BusyItem[] = $state.raw([]);
  /** The server's refusal text (`409 busy` message). */
  message: string | null = $state(null);
  /** A refusal that is not `busy` (shown in the dialog; Quit ARGOS still quits). */
  error: string | null = $state(null);
  stages: StageRow[] = $state.raw([]);
  /** Local clock (ms) when the shutdown began. */
  startedAt: number | null = $state(null);
  /** The shutdown runs past STUCK_MS: "Quit now". */
  stuck = $state(false);
  /** `closing` for CLOSE_STALL_MS and the window is still here. */
  closeStalled = $state(false);
  /** The server shut down on request (here or from another client): not a crash. */
  sawShutdown = $state(false);
  /** The server's bound for the whole shutdown (s), when it said it. */
  budgetS: number | null = $state(null);

  private readonly deps: QuitDeps;
  /** The server has no A7: forcing quits through the shell. */
  private fallback = false;
  private stuckTimer: ReturnType<typeof setTimeout> | null = null;
  private closeTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(deps: QuitDeps) {
    this.deps = deps;
  }

  private now(): number {
    return (this.deps.now ?? Date.now)();
  }

  /** The phase now (after an await: events may have moved it on). */
  private at(): QuitPhase {
    return this.phase;
  }

  /** The dialog's lines: each busy item in words, with what the UI knows. */
  get sentences(): string[] {
    const a = this.deps.activity();
    return this.busy.map((it) => busySentence(it, a));
  }

  /** The scrim is up (the app is inert behind it). */
  get scrim(): boolean {
    return this.phase === 'stopping' || this.phase === 'closing' || this.phase === 'remote' || this.phase === 'stopped';
  }

  /** The stage running now. */
  get current(): StageRow | null {
    return this.stages.find((s) => s.from !== null && s.to === null) ?? null;
  }

  /** Quit: Mod+Q, the Help menu, the title bar, the app menu, argos://quit-requested. */
  async request(): Promise<void> {
    if (!this.deps.desktop) return;
    if (this.phase === 'closing') {
      // The window is still here after the server stopped: ask the shell again.
      this.deps.exit();
      return;
    }
    if (this.phase === 'remote') {
      // Another client is shutting the server down: quit once it is gone.
      this.phase = 'stopping';
      return;
    }
    if (this.phase !== 'idle' && this.phase !== 'stopped') return;
    if (this.phase === 'stopped') {
      this.finish();
      return;
    }
    this.phase = 'checking';
    this.error = null;
    let answer: ShutdownAnswer;
    try {
      answer = await this.deps.shutdown(false);
    } catch (err) {
      if (this.phase !== 'checking') return;
      this.confirm(this.localItems(), null);
      this.error = errorText(err);
      return;
    }
    if (this.at() !== 'checking') {
      // The shutdown events came first: still take the server's plan of stages.
      if (this.at() === 'stopping' && answer.outcome === 'accepted') this.begin(answer.stages, answer.budgetS);
      return;
    }
    switch (answer.outcome) {
      case 'accepted':
        this.begin(answer.stages, answer.budgetS);
        break;
      case 'busy':
        this.confirm(answer.items.length ? answer.items : this.localItems(), answer.message);
        break;
      case 'unsupported': {
        this.fallback = true;
        const items = this.localItems();
        if (items.length) this.confirm(items, null);
        else this.finish();
        break;
      }
      case 'unreachable':
        // Nothing answers: there is nothing left to stop gracefully.
        this.finish();
        break;
    }
  }

  /** Cancel in the dialog (Escape, the Cancel button). */
  cancel(): void {
    if (this.phase !== 'confirm') return;
    this.phase = 'idle';
    this.busy = [];
    this.message = null;
    this.error = null;
  }

  /**
   * "Quit ARGOS" in the dialog: force the shutdown. Always ends in quitting; a
   * refusal of the forced request quits through the shell (SIGTERM, graceful).
   */
  async force(): Promise<void> {
    if (this.phase !== 'confirm') return;
    if (this.fallback) {
      this.finish();
      return;
    }
    this.phase = 'forcing';
    this.error = null;
    let answer: ShutdownAnswer | null = null;
    try {
      answer = await this.deps.shutdown(true);
    } catch {
      answer = null;
    }
    if (this.at() === 'stopping' && answer?.outcome === 'accepted') this.begin(answer.stages, answer.budgetS);
    if (this.at() !== 'forcing') return;
    if (answer?.outcome === 'accepted') this.begin(answer.stages, answer.budgetS);
    else this.finish();
  }

  /** "Quit now" on a stuck scrim: the shell stops the server at once (SIGTERM, SIGKILL 2 s later). */
  quitNow(): void {
    if (this.phase === 'stopping' || this.phase === 'closing' || this.phase === 'remote' || this.phase === 'stopped') this.finish(true);
  }

  /** Quit with no server left to ask (the crash notice): the window closes at once. */
  exitNow(): void {
    if (!this.deps.desktop) return;
    this.finish();
  }

  /** A WS `shutdown` stage. */
  onShutdownEvent(ev: ShutdownEvent): void {
    this.sawShutdown = true;
    const now = this.now();
    if (this.phase === 'idle' || this.phase === 'confirm' || this.phase === 'checking' || this.phase === 'forcing' || this.phase === 'stopped') {
      // Here: the request is under way (its 202 may come after the first event).
      if (this.phase === 'checking' || this.phase === 'forcing') this.begin([], null, true);
      else {
        // Another client asked for it.
        this.phase = 'remote';
        this.busy = [];
        this.startedAt = now;
        this.stages = [];
        this.armStuck();
      }
    }
    this.stages = advance(this.stages, ev.stage, stageLabel(ev.stage, ev.label), ev.done, now);
    if (ev.done) this.serverGone();
  }

  /** The event link's state: a closed link during a shutdown is its end. */
  onLink(open: boolean): void {
    if (open) {
      // A server answers again (restarted): a finished remote shutdown is over.
      if (this.phase === 'stopped') this.reset();
      return;
    }
    if (this.phase === 'stopping' || this.phase === 'remote') this.serverGone();
  }

  /** Back to idle (the server is up again). */
  reset(): void {
    this.clearTimers();
    this.phase = 'idle';
    // A later stop of this new server is not the shutdown seen before.
    this.sawShutdown = false;
    this.busy = [];
    this.message = null;
    this.error = null;
    this.stages = [];
    this.startedAt = null;
    this.stuck = false;
    this.closeStalled = false;
  }

  dispose(): void {
    this.clearTimers();
  }

  // -- internals ----------------------------------------------------------------------------

  private localItems(): BusyItem[] {
    return localBusy(this.deps.activity());
  }

  private confirm(items: BusyItem[], message: string | null): void {
    this.busy = items;
    this.message = message;
    this.phase = 'confirm';
  }

  /**
   * The shutdown runs: the scrim, with the server's plan when it sent one. `byEvent`: a
   * stage event came first (its own row starts the list).
   */
  private begin(planned: readonly { id: string; label: string }[] = [], budgetS: number | null = null, byEvent = false): void {
    if (this.phase === 'stopping') {
      // Events came before the 202: add the plan's stages still to come.
      const missing = planned.filter((p) => !this.stages.some((s) => s.id === p.id));
      this.stages = [...this.stages, ...missing.map((p) => ({ id: p.id, label: stageLabel(p.id, p.label), from: null, to: null }))];
      this.budgetS ??= budgetS;
      return;
    }
    this.phase = 'stopping';
    this.sawShutdown = true;
    this.busy = [];
    this.budgetS = budgetS;
    this.startedAt = this.now();
    this.stages = planned.length
      ? planned.map((p) => ({ id: p.id, label: stageLabel(p.id, p.label), from: null, to: null }))
      : byEvent
        ? []
        : [{ id: 'requested', label: stageLabel('requested'), from: this.startedAt, to: null }];
    this.armStuck();
  }

  private armStuck(): void {
    this.stuck = false;
    if (this.stuckTimer) clearTimeout(this.stuckTimer);
    this.stuckTimer = setTimeout(() => {
      if (this.phase === 'stopping' || this.phase === 'remote') this.stuck = true;
    }, STUCK_MS);
  }

  /** The server finished (last stage) or its link closed. */
  private serverGone(): void {
    const now = this.now();
    // Running stages end here; planned ones the server never reached stay unmarked.
    this.stages = this.stages.map((s) => (s.from !== null && s.to === null ? { ...s, to: now } : s));
    if (this.phase === 'remote') {
      this.clearTimers();
      this.stuck = false;
      this.phase = 'stopped';
      return;
    }
    if (this.phase === 'stopping') this.finish();
  }

  /** Close the app (desktop): the shell exits and stops whatever is left (`now`: at once). */
  private finish(now = false): void {
    if (this.stuckTimer) clearTimeout(this.stuckTimer);
    this.stuck = false;
    this.phase = 'closing';
    this.startedAt ??= this.now();
    this.deps.exit(now);
    if (this.closeTimer) clearTimeout(this.closeTimer);
    this.closeTimer = setTimeout(() => {
      if (this.phase === 'closing') this.closeStalled = true;
    }, CLOSE_STALL_MS);
  }

  private clearTimers(): void {
    if (this.stuckTimer) clearTimeout(this.stuckTimer);
    if (this.closeTimer) clearTimeout(this.closeTimer);
    this.stuckTimer = null;
    this.closeTimer = null;
  }
}

/**
 * The rows after the event `id`: the stages before it end now (a planned one the server
 * passed without a word is marked done at once), `id` runs (or is done, for the last one);
 * an unplanned stage is added after the others.
 */
export function advance(rows: readonly StageRow[], id: string, label: string, done: boolean, now: number): StageRow[] {
  const at = rows.findIndex((r) => r.id === id);
  if (at < 0) {
    const out = rows.map((r) => (r.from !== null && r.to === null ? { ...r, to: now } : r));
    out.push({ id, label, from: now, to: done ? now : null });
    return out;
  }
  return rows.map((r, i) => {
    if (i < at) return r.to !== null ? r : { ...r, from: r.from ?? now, to: now };
    if (i === at) return { ...r, label, from: r.from ?? now, to: done ? now : r.to };
    return r;
  });
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : String(err);
}
