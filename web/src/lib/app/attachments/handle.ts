/**
 * A draggable value handle as a Svelte 5 attachment, for a value drawn over
 * a chart (the histogram's black, midtones and white levels, a threshold):
 * {@attach valueHandle({ axis: 'x', toValue, get, set, keyStep })}.
 *
 * Promoted from src/lab/research/curve/handle.ts and the handles of
 * src/lab/charts/charts/HistogramStretch.svelte (web/lab/PROPOSAL.md
 * section 6, W3), with an axis option.
 *
 * - Pointer: pointer capture, so the drag keeps working when the pointer
 *   leaves the 14 px handle or the chart; the value follows the pointer
 *   exactly (no spring: the number and the line agree at all times).
 * - Keyboard: the element carries role="slider" and tabindex 0; arrows move
 *   by one step, Shift+arrows by `bigFactor` steps (BRAND 8 modifiers:
 *   Shift = x10), Alt+arrows by a tenth when the value is continuous;
 *   Home / End go to the bounds. `keyStep` may give a custom step per key
 *   (the midtones balance steps in its own unit).
 * - Touch: `touch-action: none` on the element (set by the component).
 */

import type { Attachment } from 'svelte/attachments';

export interface ValueHandleOptions {
  axis: 'x' | 'y';
  /** Pointer client coordinate -> value, or null when the chart is not ready. */
  toValue: (client: number) => number | null;
  get: () => number;
  set: (v: number) => void;
  /** One keyboard step; Shift multiplies it by `bigFactor` (10). */
  step: number | (() => number);
  bigFactor?: number;
  /** Alt divides the step by 10 (continuous values only). */
  fine?: boolean;
  min: () => number;
  max: () => number;
  ondrag?: (active: boolean) => void;
}

/** The value a key asks for (ArrowRight / ArrowUp increase), or null. */
export function handleKey(
  o: Pick<ValueHandleOptions, 'step' | 'bigFactor' | 'fine' | 'min' | 'max'>,
  key: string,
  mods: { shift: boolean; alt: boolean },
  current: number,
): number | null {
  const base = typeof o.step === 'function' ? o.step() : o.step;
  let s = base;
  if (mods.shift) s = base * (o.bigFactor ?? 10);
  else if (mods.alt && o.fine) s = base / 10;
  if (key === 'ArrowUp' || key === 'ArrowRight') return current + s;
  if (key === 'ArrowDown' || key === 'ArrowLeft') return current - s;
  if (key === 'Home') return o.min();
  if (key === 'End') return o.max();
  return null;
}

type HandleElement = Pick<
  HTMLElement,
  'addEventListener' | 'removeEventListener' | 'setPointerCapture' | 'releasePointerCapture' | 'hasPointerCapture'
>;

export function valueHandle(o: ValueHandleOptions): Attachment<HTMLElement> {
  return (node) => {
    const el = node as HandleElement;
    let active: number | null = null;
    const clamp = (v: number) => Math.min(o.max(), Math.max(o.min(), v));
    const coord = (e: PointerEvent) => (o.axis === 'x' ? e.clientX : e.clientY);

    const down = (e: PointerEvent) => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation(); // not a pan or a drag-zoom of what is underneath
      el.setPointerCapture(e.pointerId);
      active = e.pointerId;
      o.ondrag?.(true);
    };
    const move = (e: PointerEvent) => {
      if (active !== e.pointerId) return;
      const v = o.toValue(coord(e));
      if (v !== null && Number.isFinite(v)) o.set(clamp(v));
    };
    const up = (e: PointerEvent) => {
      if (active !== e.pointerId) return;
      active = null;
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      o.ondrag?.(false);
    };
    const key = (e: KeyboardEvent) => {
      const v = handleKey(o, e.key, { shift: e.shiftKey, alt: e.altKey }, o.get());
      if (v === null) return;
      e.preventDefault();
      e.stopPropagation(); // the arrows belong to the handle, not to a pan below
      o.set(clamp(v));
    };

    el.addEventListener('pointerdown', down as EventListener);
    el.addEventListener('pointermove', move as EventListener);
    el.addEventListener('pointerup', up as EventListener);
    el.addEventListener('pointercancel', up as EventListener);
    el.addEventListener('lostpointercapture', up as EventListener);
    el.addEventListener('keydown', key as EventListener);
    return () => {
      if (active !== null) o.ondrag?.(false);
      el.removeEventListener('pointerdown', down as EventListener);
      el.removeEventListener('pointermove', move as EventListener);
      el.removeEventListener('pointerup', up as EventListener);
      el.removeEventListener('pointercancel', up as EventListener);
      el.removeEventListener('lostpointercapture', up as EventListener);
      el.removeEventListener('keydown', key as EventListener);
    };
  };
}
