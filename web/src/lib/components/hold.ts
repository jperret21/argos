/**
 * Hold-to-confirm (HoldButton.svelte): the pure part, unit-tested.
 * web/lab/PROPOSAL.md 3.1 and 3.3 (owner D4), BRAND 7 "Physical action that is
 * hard to undo at night", promoted from src/lab/controls/components/
 * HoldButton.svelte (the ring version; it replaces the workspace lab's fill
 * version, whose label changed while held).
 *
 * - Pointer: press and hold for --hold-duration (700 ms). The time ring
 *   fills with the exact elapsed fraction, linear. Releasing or sliding off
 *   before the end sends NOTHING and says so; a quick tap teaches the
 *   gesture instead ("Hold to park, or press Enter").
 * - Keyboard and assistive technology: Enter / Space never start a timed
 *   hold (hard for some users); they open the inline two-button
 *   confirmation, focus on Cancel (README 3.3).
 * - The label never changes while held; the caption under the button does.
 */

export type HoldPhase = 'rest' | 'holding' | 'confirm' | 'busy' | 'released' | 'tapped' | 'done' | 'failed';

/** --hold-duration (tokens.css): kept under reduced motion, it carries information. */
export const HOLD_MS = 700;
/** A release before this fraction of the hold is a tap (it teaches the gesture). */
export const TAP_FRACTION = 0.18;
/** --hold-drain: the ring empties after an early release (0 under reduced motion). */
export const DRAIN_MS = 150;
/** How long "Released · nothing sent" / the tap lesson stay before the rest caption. */
export const RELEASED_MS = 1800;
/** How long the done caption stays. */
export const DONE_MS = 2200;
/** Pointer slop around the button before a slide-off cancels the hold. */
export const SLOP_PX = 8;

/** Elapsed fraction of a hold, clamped to 0..1. */
export function holdFraction(elapsedMs: number, holdMs = HOLD_MS): number {
  if (!(holdMs > 0)) return 1;
  return Math.min(1, Math.max(0, elapsedMs / holdMs));
}

/** What an early release means: a tap (teach the gesture) or an abandoned hold. */
export function releaseOutcome(fraction: number): 'tapped' | 'released' {
  return fraction < TAP_FRACTION ? 'tapped' : 'released';
}

/** Did the pointer slide off the button (with the slop)? A slide-off cancels the hold. */
export function slidOff(
  rect: { left: number; right: number; top: number; bottom: number },
  x: number,
  y: number,
  slop = SLOP_PX,
): boolean {
  return x < rect.left - slop || x > rect.right + slop || y < rect.top - slop || y > rect.bottom + slop;
}

/** Can a pointer hold start now? Never while the action runs or the confirmation is open. */
export function canStartHold(phase: HoldPhase, unavailable: boolean): boolean {
  return !unavailable && phase !== 'busy' && phase !== 'confirm' && phase !== 'holding';
}

/** Can Enter / Space open the inline confirmation now? */
export function canOpenConfirm(phase: HoldPhase, unavailable: boolean): boolean {
  return !unavailable && phase !== 'busy' && phase !== 'holding';
}

export interface CaptionContext {
  /** Verb for the captions: "park" gives "Hold 0.7 s to park". */
  verb: string;
  label: string;
  holdMs?: number;
  /** Seconds still to hold (while holding). */
  remainingS?: number;
  busyLabel?: string;
  doneLabel?: string;
  failure?: string | null;
  disabledReason?: string | null;
}

export interface Caption {
  text: string;
  tone: 'muted' | 'plain' | 'reason' | 'failed';
  /** Seconds left, drawn after the text in mono (holding only). */
  count?: string;
}

/** One decimal, the hold time in words ("0.7 s"). */
function tenths(s: number): string {
  return `${(Math.round(s * 10) / 10).toFixed(1)} s`;
}

/** The how-to line of the tooltip and of the rest caption. */
export function holdHint(verb: string, holdMs = HOLD_MS): string {
  return `Hold ${tenths(holdMs / 1000)} to ${verb} · Enter to confirm`;
}

/** The caption under the button, per phase (the label itself never changes). */
export function holdCaption(phase: HoldPhase, c: CaptionContext): Caption {
  if (c.disabledReason) return { text: c.disabledReason, tone: 'reason' };
  switch (phase) {
    case 'holding':
      return { text: 'Keep holding', tone: 'plain', count: tenths(Math.max(0, c.remainingS ?? 0)) };
    case 'busy':
      return { text: c.busyLabel ?? `${c.label}…`, tone: 'plain' };
    case 'released':
      return { text: 'Released · nothing sent', tone: 'plain' };
    case 'tapped':
      return { text: `Hold to ${c.verb}, or press Enter`, tone: 'plain' };
    case 'done':
      return { text: c.doneLabel ?? 'Done', tone: 'plain' };
    case 'failed':
      return { text: c.failure ?? `${c.label} failed`, tone: 'failed' };
    case 'confirm':
    case 'rest':
    default:
      return { text: holdHint(c.verb, c.holdMs), tone: 'muted' };
  }
}
