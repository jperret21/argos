/**
 * Resizable split as a Svelte 5 attachment on the separator element:
 * {@attach splitter({ axis: 'y', get, set, min, max, reset })}.
 *
 * Promoted from src/lab/research/space/splitter.ts (web/lab/PROPOSAL.md
 * section 6, W3): the Observe band, drawer and right-panel separators.
 *
 * - Pointer: pointer capture, so the drag continues over canvases and out
 *   of the window; the value follows the pointer exactly (no easing: a
 *   separator is a measurement of the layout, BRAND 9).
 * - Snap: within `snapPx` (8) of a detent the value sticks to it (the
 *   band's "fits the image" height, the drawer's default).
 * - Keyboard (WAI-ARIA window splitter): arrows `step` (8 px), Shift+arrows
 *   `bigStep` (40 px), Home / End = min / max, Enter = reset; double-click =
 *   reset. The element carries role="separator", aria-orientation,
 *   tabindex 0 and aria-valuenow / min / max (the component renders them).
 * - `invert`: dragging towards +x / +y shrinks the pane (a right rail, a
 *   bottom band or drawer), so ArrowUp grows a bottom pane.
 */

import type { Attachment } from 'svelte/attachments';

export interface SplitterOptions {
  axis: 'x' | 'y';
  get: () => number;
  set: (v: number) => void;
  min: number;
  max: () => number;
  /** The value Enter and a double-click restore. */
  reset: number | (() => number);
  invert?: boolean;
  /** Detents the drag sticks to. */
  snaps?: readonly number[] | (() => readonly number[]);
  snapPx?: number;
  step?: number;
  bigStep?: number;
  /** A drag started (true) or ended (false): the screen shows the cost meanwhile. */
  ondrag?: (active: boolean) => void;
}

const SNAP_PX = 8;

/** The element surface the attachment needs (a fake in tests). */
export type SplitterElement = Pick<
  HTMLElement,
  'addEventListener' | 'removeEventListener' | 'setPointerCapture' | 'releasePointerCapture' | 'hasPointerCapture'
>;

/** Clamp to [min, max()] and round to a whole CSS pixel. */
export function clampSplit(o: Pick<SplitterOptions, 'min' | 'max'>, v: number): number {
  const hi = Math.max(o.min, o.max());
  return Math.round(Math.min(hi, Math.max(o.min, v)));
}

/** The detent within `px` of `v`, else `v`. */
export function snapSplit(v: number, snaps: readonly number[], px = SNAP_PX): number {
  for (const s of snaps) if (Math.abs(v - s) <= px) return s;
  return v;
}

/** The value a key asks for, or null when the key does not belong to the splitter. */
export function splitterKey(
  o: Pick<SplitterOptions, 'axis' | 'invert' | 'min' | 'max' | 'reset' | 'step' | 'bigStep'>,
  key: string,
  shift: boolean,
  current: number,
): number | null {
  const step = shift ? (o.bigStep ?? 40) : (o.step ?? 8);
  const grow = o.axis === 'x' ? (o.invert ? 'ArrowLeft' : 'ArrowRight') : o.invert ? 'ArrowUp' : 'ArrowDown';
  const shrink = o.axis === 'x' ? (o.invert ? 'ArrowRight' : 'ArrowLeft') : o.invert ? 'ArrowDown' : 'ArrowUp';
  if (key === grow) return current + step;
  if (key === shrink) return current - step;
  if (key === 'Home') return o.min;
  if (key === 'End') return o.max();
  if (key === 'Enter') return typeof o.reset === 'function' ? o.reset() : o.reset;
  return null;
}

export function splitter(o: SplitterOptions): Attachment<HTMLElement> {
  return (node) => {
    const el = node as SplitterElement;
    let start: { id: number; p: number; v: number } | null = null;
    const snaps = () => (typeof o.snaps === 'function' ? o.snaps() : (o.snaps ?? []));
    const pos = (e: PointerEvent) => (o.axis === 'x' ? e.clientX : e.clientY);
    const resetValue = () => (typeof o.reset === 'function' ? o.reset() : o.reset);

    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      start = { id: e.pointerId, p: pos(e), v: o.get() };
      o.ondrag?.(true);
    };
    const move = (e: PointerEvent) => {
      if (!start || e.pointerId !== start.id) return;
      const d = (pos(e) - start.p) * (o.invert ? -1 : 1);
      o.set(clampSplit(o, snapSplit(start.v + d, snaps(), o.snapPx ?? SNAP_PX)));
    };
    const up = (e: PointerEvent) => {
      if (!start || e.pointerId !== start.id) return;
      start = null;
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      o.ondrag?.(false);
    };
    const key = (e: KeyboardEvent) => {
      const v = splitterKey(o, e.key, e.shiftKey, o.get());
      if (v === null) return;
      e.preventDefault();
      o.set(clampSplit(o, v));
    };
    const dbl = () => o.set(clampSplit(o, resetValue()));

    el.addEventListener('pointerdown', down as EventListener);
    el.addEventListener('pointermove', move as EventListener);
    el.addEventListener('pointerup', up as EventListener);
    el.addEventListener('pointercancel', up as EventListener);
    el.addEventListener('lostpointercapture', up as EventListener);
    el.addEventListener('keydown', key as EventListener);
    el.addEventListener('dblclick', dbl);
    return () => {
      if (start) o.ondrag?.(false);
      el.removeEventListener('pointerdown', down as EventListener);
      el.removeEventListener('pointermove', move as EventListener);
      el.removeEventListener('pointerup', up as EventListener);
      el.removeEventListener('pointercancel', up as EventListener);
      el.removeEventListener('lostpointercapture', up as EventListener);
      el.removeEventListener('keydown', key as EventListener);
      el.removeEventListener('dblclick', dbl);
    };
  };
}
