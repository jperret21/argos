/**
 * The mount-motion interlock on the client (PROPOSAL section 7 and 10 D2; README 3.3;
 * protocol.md "Mount-motion interlock"): while a run is running, pausing, in autofocus or
 * stopping, the server refuses every mount motion with `409 run_active` (GoTo, Centre,
 * Sync, Park, Unpark, tracking off, tracking rate, jog; the Stellarium bridge only logs). The UI does not
 * pre-empt that refusal: it sends the command, and on `run_active` asks once, offering the
 * one explicit way through, "Pause the run and slew", which sends the same command again
 * with `"pause_run": true`: the server pauses the run (the sub in progress completes and
 * is saved), waits for `paused`, moves, and leaves the run paused until Resume ("The run
 * did not pause in time — nothing moved." stays in the dialog). Cancel sends nothing.
 *
 * Usage (every mount control, through the integrator):
 *   const lock = new MountInterlock();
 *   await lock.run({ action: 'GoTo', verb: 'slew' }, (pauseRun) => client.goto({ …, pause_run: pauseRun || undefined }));
 *   <InterlockDialog {lock} />
 *
 * `run` resolves with the command's answer, or with `undefined` when the refusal was turned
 * into the question; any other error is rethrown unchanged (its toast and log as usual).
 */

import { isRunActive } from '../api/sequence';
import { fixed } from '../format/number';

export interface InterlockRequest {
  /** The command in words, as on its button ("GoTo", "Park", "Stop tracking", "Jog"). */
  action: string;
  /** The verb of the way through: "Pause the run and <verb>" (default "slew"). */
  verb?: string;
  /**
   * Another way through than resending the command with `pause_run` (the jog pad: a
   * dead-man jog resent after the dialog would move the mount with no hand on the key, so
   * its way through only pauses the run; the observer jogs again once it is paused).
   */
  through?: () => Promise<unknown>;
}

export interface PendingInterlock {
  action: string;
  verb: string;
  /** The server's sentence, verbatim. */
  message: string;
  retry: () => Promise<unknown>;
  /** The way through only pauses the run (`through`), it does not move the mount. */
  pauseOnly?: boolean;
}

export class MountInterlock {
  pending: PendingInterlock | null = $state.raw(null);

  async run<T>(req: InterlockRequest, call: (pauseRun: boolean) => Promise<T>): Promise<T | undefined> {
    try {
      return await call(false);
    } catch (err) {
      if (!isRunActive(err)) throw err;
      this.ask(req, err.message, () => call(true));
      return undefined;
    }
  }

  /** Ask about a refusal caught elsewhere (the jog pad keeps its own error path). */
  ask(req: InterlockRequest, message: string, retry: () => Promise<unknown>): void {
    this.pending = req.through
      ? { action: req.action, verb: req.verb ?? 'slew', message, retry: req.through, pauseOnly: true }
      : { action: req.action, verb: req.verb ?? 'slew', message, retry };
  }

  /** "Pause the run and slew": the same command with `pause_run`; a refusal stays in the dialog, in words. */
  async confirm(): Promise<void> {
    const p = this.pending;
    if (!p) return;
    await p.retry();
    if (this.pending === p) this.pending = null;
  }

  cancel(): void {
    this.pending = null;
  }
}

/**
 * The dialog's words (design review W6a): what the command would do to the run and what the
 * way through does, without quoting the button (the server's sentence goes to the log, it
 * said the same thing). `exposureS`: the sub in progress, when known.
 */
export function interlockText(
  p: Pick<PendingInterlock, 'action' | 'verb' | 'message' | 'pauseOnly'>,
  exposureS: number | null = null,
): { title: string; body: string; confirm: string; holdVerb: string } {
  const sub = exposureS !== null && exposureS > 0 ? `the ${fixed(exposureS, exposureS < 10 ? 1 : 0)} s sub in progress` : 'the sub in progress';
  const what = `${p.action} would move the field under the run.`;
  if (p.pauseOnly) {
    return {
      title: 'A sequence is running',
      body: `${what} Pausing lets ${sub} finish and be saved; ${p.verb} again once the run shows Paused. It stays paused until you resume it.`,
      confirm: 'Pause the run',
      holdVerb: 'pause the run',
    };
  }
  return {
    title: 'A sequence is running',
    body: `${what} Pausing lets ${sub} finish and be saved; the mount then moves, and the run stays paused until you resume it.`,
    confirm: `Pause the run and ${p.verb}`,
    holdVerb: `pause the run and ${p.verb}`,
  };
}
