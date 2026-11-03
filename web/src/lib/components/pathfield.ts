/**
 * `use:middlePath={value}` on a path input (02 section 2.2): while the field
 * is not focused it shows the path with the middle cut and the last segment
 * whole (format/path.ts), the full path in the token tooltip (never a native
 * title, which is grey in Night Red); on focus it shows the raw value with
 * the caret and the view at its end. The input's real value is only
 * replaced for display: the caller keeps the raw value (bind:value or its
 * own state) and the action restores it before any edit.
 */
import type { Action } from 'svelte/action';
import { middleEllipsis } from '../format/path';
import { tooltip } from './tooltip';

let ctx: CanvasRenderingContext2D | null = null;

function charWidth(node: HTMLInputElement): number {
  const cs = getComputedStyle(node);
  try {
    ctx ??= document.createElement('canvas').getContext('2d');
  } catch {
    ctx = null;
  }
  if (!ctx) return parseFloat(cs.fontSize) * 0.6 || 8;
  ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  // Paths are set in Plex Mono: one width for every character. An average
  // over a sample keeps it close for a proportional face too.
  return ctx.measureText('/Users/observer/Desktop/argos-0123').width / 34 || 8;
}

export interface MiddlePathOptions {
  value: string | null | undefined;
  /** False: the action does nothing (a text field that is not a path). */
  enabled?: boolean;
}

export const middlePath: Action<HTMLInputElement, MiddlePathOptions> = (node, initial) => {
  let raw = initial.value ?? '';
  let enabled = initial.enabled ?? true;
  let shortened = false;
  const tip = tooltip(node, { text: '', disabled: true, placement: 'top' });

  const room = (): number => {
    const cs = getComputedStyle(node);
    const inner = node.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    return Math.max(0, Math.floor(inner / charWidth(node)));
  };

  const apply = () => {
    if (document.activeElement === node) return;
    if (!enabled) {
      if (shortened) node.value = raw;
      shortened = false;
      tip?.update?.({ text: raw, disabled: true, placement: 'top' });
      return;
    }
    const max = room();
    const shown = max > 0 ? middleEllipsis(raw, max) : raw;
    shortened = shown !== raw;
    if (node.value !== shown) node.value = shown;
    tip?.update?.({ text: raw, disabled: !shortened, placement: 'top' });
  };

  const onFocus = () => {
    if (shortened || node.value !== raw) node.value = raw;
    shortened = false;
    // The end of a path is what the observer edits (the file name).
    const end = node.value.length;
    try {
      node.setSelectionRange(end, end);
    } catch {
      /* not a text input */
    }
    node.scrollLeft = node.scrollWidth;
  };
  const onBlur = () => queueMicrotask(apply);

  node.addEventListener('focus', onFocus);
  node.addEventListener('blur', onBlur);
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => apply()) : null;
  ro?.observe(node);
  queueMicrotask(apply);

  return {
    update(next) {
      raw = next.value ?? '';
      enabled = next.enabled ?? true;
      queueMicrotask(apply);
    },
    destroy() {
      node.removeEventListener('focus', onFocus);
      node.removeEventListener('blur', onBlur);
      ro?.disconnect();
      tip?.destroy?.();
    },
  };
};
