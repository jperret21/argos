/**
 * Segmented choice: the pure part of Segmented.svelte (keyboard targets,
 * which segment can act and why, the roving tab stop). No DOM, unit-tested.
 *
 * Promoted from src/lab/controls/components/Seg.svelte (web/lab/PROPOSAL.md
 * 3.3 and 6, W3): manual activation for hardware choices (the filter wheel,
 * the jog rate): the arrows move focus only, Space / Enter chooses, so
 * walking across the wheel's slots never moves the wheel three times.
 * Automatic activation (the WAI-ARIA radio-group default) stays for display
 * choices, where following the focus is harmless.
 */

export interface SegmentOption<V extends string = string> {
  value: V;
  label: string;
  /** Icon id (icon-inventory.json) before the label, or alone with `iconOnly`. */
  icon?: string;
  /** Mono detail after the label ("0.5°/s"). */
  detail?: string;
  /** Show only the icon: the label becomes the accessible name and the tooltip. */
  iconOnly?: boolean;
  /** Why this one segment cannot be chosen now. */
  disabledReason?: string | null;
}

export type Activation = 'auto' | 'manual';

/** What a key does on segment `index` of `count`: move focus to an index, choose, or nothing. */
export type SegmentKeyResult = { move: number } | { choose: true } | null;

/**
 * The keyboard rule of a segmented control. Both arrow pairs move (the
 * radio-group pattern), wrapping; Home / End jump; Space and Enter choose
 * the focused segment.
 */
export function segmentKey(key: string, index: number, count: number): SegmentKeyResult {
  if (count <= 0) return null;
  switch (key) {
    case 'ArrowLeft':
    case 'ArrowUp':
      return { move: (index - 1 + count) % count };
    case 'ArrowRight':
    case 'ArrowDown':
      return { move: (index + 1) % count };
    case 'Home':
      return { move: 0 };
    case 'End':
      return { move: count - 1 };
    case ' ':
    case 'Enter':
      return { choose: true };
    default:
      return null;
  }
}

/** Does moving the focus also choose? Only with automatic activation (display choices). */
export function choosesOnMove(activation: Activation): boolean {
  return activation === 'auto';
}

export interface ReasonContext {
  /** The whole control is unavailable, with this reason. */
  disabledReason?: string | null;
  /** The value being applied now (the wheel turning to it). */
  busyValue?: string | null;
  /** Why the other segments wait ("The wheel is turning to IR"). */
  busyReason?: string;
}

export const DEFAULT_BUSY_REASON = 'Wait for the change to finish';

/**
 * Why a segment cannot be chosen now, or null when it can. The control's
 * reason wins, then the busy rule (every segment but the busy one waits),
 * then the segment's own reason.
 */
export function segmentReason(o: SegmentOption, ctx: ReasonContext): string | null {
  if (ctx.disabledReason) return ctx.disabledReason;
  if (ctx.busyValue !== null && ctx.busyValue !== undefined && o.value !== ctx.busyValue) {
    return ctx.busyReason ?? DEFAULT_BUSY_REASON;
  }
  return o.disabledReason ?? null;
}

/**
 * The one tab stop of the group: the focused segment while focus is inside,
 * else the selected one, else the first.
 */
export function tabStop(focusIndex: number, selectedIndex: number, count: number): number {
  if (count <= 0) return -1;
  if (focusIndex >= 0 && focusIndex < count) return focusIndex;
  return selectedIndex >= 0 && selectedIndex < count ? selectedIndex : 0;
}

/**
 * Should choosing `value` do anything? Not when it is the value already in
 * effect (nor the one already requested), nor when the segment says why it
 * cannot.
 */
export function canChoose(o: SegmentOption, current: string, ctx: ReasonContext): boolean {
  if (segmentReason(o, ctx)) return false;
  if (ctx.busyValue !== null && ctx.busyValue !== undefined && o.value === ctx.busyValue) return false;
  return o.value !== current;
}
