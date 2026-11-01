/**
 * Resizable split as a Svelte 5 attachment on the separator element:
 * {@attach splitter({ axis: 'x', get, set, min, max, reset })}.
 *
 * - Pointer: pointer capture, so the drag continues over iframes, canvases
 *   and outside the window; the value follows the pointer exactly.
 * - Snap: within 8 px of a detent the value sticks to it (the rail's 420 /
 *   500 / 580 px, the drawer's default).
 * - Keyboard (WAI-ARIA window splitter): arrows 8 px, Shift+arrows 40 px,
 *   Home / End = min / max, Enter = reset; double-click = reset.
 * - The element must carry role="separator", aria-orientation and
 *   aria-valuenow/min/max (the component renders them from the value).
 */

import type { Attachment } from 'svelte/attachments';

export interface SplitterOptions {
  axis: 'x' | 'y';
  get: () => number;
  set: (v: number) => void;
  min: number;
  max: () => number;
  reset: number;
  /** Dragging towards +x / +y shrinks the pane (a right rail, a bottom drawer). */
  invert?: boolean;
  snaps?: number[];
  ondrag?: (active: boolean) => void;
}

const SNAP_PX = 8;

export function splitter(o: SplitterOptions): Attachment<HTMLElement> {
  return (el) => {
    let start: { p: number; v: number } | null = null;
    const clamp = (v: number) => Math.round(Math.min(o.max(), Math.max(o.min, v)));
    const snap = (v: number) => {
      for (const s of o.snaps ?? []) if (Math.abs(v - s) <= SNAP_PX) return s;
      return v;
    };
    const pos = (e: PointerEvent) => (o.axis === 'x' ? e.clientX : e.clientY);

    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      start = { p: pos(e), v: o.get() };
      o.ondrag?.(true);
    };
    const move = (e: PointerEvent) => {
      if (!start) return;
      const d = (pos(e) - start.p) * (o.invert ? -1 : 1);
      o.set(clamp(snap(start.v + d)));
    };
    const up = (e: PointerEvent) => {
      if (!start) return;
      start = null;
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      o.ondrag?.(false);
    };
    const key = (e: KeyboardEvent) => {
      const step = e.shiftKey ? 40 : 8;
      const grow = o.axis === 'x' ? (o.invert ? 'ArrowLeft' : 'ArrowRight') : o.invert ? 'ArrowUp' : 'ArrowDown';
      const shrink = o.axis === 'x' ? (o.invert ? 'ArrowRight' : 'ArrowLeft') : o.invert ? 'ArrowDown' : 'ArrowUp';
      let v: number | null = null;
      if (e.key === grow) v = o.get() + step;
      else if (e.key === shrink) v = o.get() - step;
      else if (e.key === 'Home') v = o.min;
      else if (e.key === 'End') v = o.max();
      else if (e.key === 'Enter') v = o.reset;
      if (v === null) return;
      e.preventDefault();
      o.set(clamp(v));
    };
    const dbl = () => o.set(clamp(o.reset));

    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    el.addEventListener('keydown', key);
    el.addEventListener('dblclick', dbl);
    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      el.removeEventListener('keydown', key);
      el.removeEventListener('dblclick', dbl);
    };
  };
}
