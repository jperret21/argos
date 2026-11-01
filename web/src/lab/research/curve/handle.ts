/**
 * A draggable value handle as a Svelte 5 attachment, for annotations drawn
 * over a uPlot chart (a quality threshold, a level, a time marker):
 * {@attach valueHandle({ toValue, get, set, step })}.
 *
 * - Pointer: pointer capture, so the drag keeps working when the pointer
 *   leaves the 14 px handle or the chart; the value follows the pointer
 *   exactly (no spring: the number and the line must agree at all times).
 * - Keyboard: the element carries role="slider"; arrows move by `step`,
 *   Shift+arrows by 5 steps, Home / End to the bounds.
 * - Touch: `touch-action: none` on the element (set by the component), or
 *   the browser scrolls the page instead of dragging.
 */

import type { Attachment } from 'svelte/attachments';

export interface ValueHandleOptions {
  /** Pointer clientY -> value, or null when the chart is not ready. */
  toValue: (clientY: number) => number | null;
  get: () => number;
  set: (v: number) => void;
  step: number;
  min: () => number;
  max: () => number;
  ondrag?: (active: boolean) => void;
}

export function valueHandle(o: ValueHandleOptions): Attachment<HTMLElement> {
  return (el) => {
    let active = false;
    const clamp = (v: number) => Math.min(o.max(), Math.max(o.min(), v));

    const down = (e: PointerEvent) => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation(); // not a drag-zoom on the chart underneath
      el.setPointerCapture(e.pointerId);
      active = true;
      o.ondrag?.(true);
    };
    const move = (e: PointerEvent) => {
      if (!active) return;
      const v = o.toValue(e.clientY);
      if (v !== null) o.set(clamp(v));
    };
    const up = (e: PointerEvent) => {
      if (!active) return;
      active = false;
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      o.ondrag?.(false);
    };
    const key = (e: KeyboardEvent) => {
      const s = o.step * (e.shiftKey ? 5 : 1);
      let v: number | null = null;
      if (e.key === 'ArrowUp' || e.key === 'ArrowRight') v = o.get() + s;
      else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') v = o.get() - s;
      else if (e.key === 'Home') v = o.min();
      else if (e.key === 'End') v = o.max();
      if (v === null) return;
      e.preventDefault();
      o.set(clamp(v));
    };

    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    el.addEventListener('keydown', key);
    return () => {
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      el.removeEventListener('keydown', key);
    };
  };
}
