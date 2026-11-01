/**
 * Hold-to-confirm as a Svelte attachment (functional-spaces.md 4.11, P8):
 * {@attach hold({ ms: 700, onconfirm, onprogress })} on a button.
 *
 * - Pointer: press and hold for `ms`; releasing early, leaving the button or
 *   a pointer cancel sends nothing. The progress is elapsed time (linear),
 *   reported to the caller, which draws it; under reduced motion the caller
 *   steps it (4 steps) but the duration stays: it is information, not
 *   decoration.
 * - Keyboard: Enter / Space never confirm a hold; they call `onkey`, which
 *   opens the inline two-step confirmation instead (a timed hold is hard for
 *   some users and for assistive technologies).
 */

import type { Attachment } from 'svelte/attachments';

export interface HoldOptions {
  ms: number;
  onconfirm: () => void;
  onprogress: (fraction: number) => void;
  onkey?: () => void;
  disabled?: () => boolean;
}

export function hold(o: HoldOptions): Attachment<HTMLElement> {
  return (el) => {
    let raf = 0;
    let t0 = 0;
    let id: number | null = null;

    const stop = (confirmed: boolean) => {
      cancelAnimationFrame(raf);
      raf = 0;
      if (id !== null && el.hasPointerCapture(id)) el.releasePointerCapture(id);
      id = null;
      o.onprogress(confirmed ? 1 : 0);
      if (confirmed) {
        o.onconfirm();
        // Leave the full bar visible a moment, then reset.
        setTimeout(() => o.onprogress(0), 400);
      }
    };
    const frame = () => {
      const f = Math.min(1, (performance.now() - t0) / o.ms);
      o.onprogress(f);
      if (f >= 1) stop(true);
      else raf = requestAnimationFrame(frame);
    };
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || o.disabled?.()) return;
      e.preventDefault();
      id = e.pointerId;
      el.setPointerCapture(id);
      t0 = performance.now();
      raf = requestAnimationFrame(frame);
    };
    const up = () => {
      if (raf) stop(false);
    };
    const leave = (e: PointerEvent) => {
      // With capture the pointer never "leaves"; check it is still over the button.
      const r = el.getBoundingClientRect();
      if (raf && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)) stop(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      if (!o.disabled?.()) o.onkey?.();
    };
    const click = (e: MouseEvent) => e.preventDefault();

    el.addEventListener('pointerdown', down);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    el.addEventListener('pointermove', leave);
    el.addEventListener('keydown', key);
    el.addEventListener('click', click);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      el.removeEventListener('pointermove', leave);
      el.removeEventListener('keydown', key);
      el.removeEventListener('click', click);
    };
  };
}
