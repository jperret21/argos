/**
 * Viewer gestures as a Svelte 5 attachment ({@attach gestures({...})}):
 * drag to pan (pointer capture, so the drag survives leaving the canvas),
 * wheel and trackpad pinch to zoom about the pointer, two-finger pinch on a
 * touch screen, double-click to fit, long-press (touch, pen) or right-click
 * (mouse) for a context menu, and the pointer position for readouts.
 *
 * Promoted from src/lab/research/frame/gestures.ts (web/lab/PROPOSAL.md
 * section 6, W3). Engine notes (lab/research/stack-capabilities.md):
 * - A trackpad pinch arrives as `wheel` with ctrlKey in Chromium and in
 *   WebKit on macOS. WebKit also fires its non-standard gesturestart /
 *   gesturechange; while such a gesture is active the ctrl+wheel events are
 *   ignored so a pinch is never applied twice.
 * - The wheel listener is registered with passive: false (WebKit makes
 *   document-level wheel listeners passive for apps linked on a recent
 *   SDK), otherwise preventDefault is ignored and the page scrolls.
 * - The element needs `touch-action: none`, or the browser takes the pinch
 *   for a page zoom.
 * - The native context menu is always suppressed (it is grey: Night Red).
 *
 * Positions are CSS px relative to the element. Touch and trackpad pinch
 * were not exercised on hardware (PROPOSAL section 9); mouse, wheel and
 * keyboard were.
 */

import type { Attachment } from 'svelte/attachments';

export interface GestureHandlers {
  /** Incremental pan, CSS px since the last call. */
  pan?: (dx: number, dy: number) => void;
  /** A drag (pan) started or ended: the cursor shows "grabbing" meanwhile. */
  panning?: (active: boolean) => void;
  /** factor > 1 zooms in; x, y in CSS px relative to the element. */
  zoom?: (factor: number, x: number, y: number) => void;
  fit?: () => void;
  menu?: (x: number, y: number) => void;
  /** Pointer position for readouts; NaN, NaN when it leaves. */
  hover?: (x: number, y: number) => void;
  /** Wheel event -> zoom factor (default: exp(-deltaY * k), pinch gain when ctrlKey). */
  wheelFactor?: (deltaY: number, deltaMode: number, ctrlKey: boolean) => number;
  /** Mouse buttons that pan (default [0]; the viewer adds the middle button). */
  buttons?: readonly number[];
  /** Nothing to act on yet (no image): pointer down and wheel are ignored. */
  enabled?: () => boolean;
}

export const LONG_PRESS_MS = 500;
/** Travel (CSS px) that turns a press into a drag (and cancels a long-press). */
export const MOVE_SLOP = 6;

interface GestureEventLike extends UIEvent {
  scale: number;
  clientX: number;
  clientY: number;
}

/** The lab's wheel law: line and page deltas in px, a stronger gain for a pinch. */
export function defaultWheelFactor(deltaY: number, deltaMode: number, ctrlKey: boolean): number {
  const unit = deltaMode === 1 ? 16 : deltaMode === 2 ? 400 : 1;
  const k = ctrlKey ? 0.01 : 0.0018;
  return Math.exp(-deltaY * unit * k);
}

/** Distance and midpoint of two pointers (pinch). */
export function pinchOf(a: { x: number; y: number }, b: { x: number; y: number }): { d: number; m: { x: number; y: number } } {
  return { d: Math.hypot(a.x - b.x, a.y - b.y), m: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } };
}

/** The element surface the attachment needs (a fake in tests). */
export type GestureElement = Pick<
  HTMLElement,
  | 'addEventListener'
  | 'removeEventListener'
  | 'setPointerCapture'
  | 'releasePointerCapture'
  | 'hasPointerCapture'
  | 'getBoundingClientRect'
>;

export function gestures(h: GestureHandlers): Attachment<HTMLElement> {
  return (node) => {
    const el = node as GestureElement;
    const pts = new Map<number, { x: number; y: number }>();
    let press: { id: number; x: number; y: number; timer: ReturnType<typeof setTimeout> | null } | null = null;
    let dragging = false;
    let pinchDist = 0;
    let pinchMid = { x: 0, y: 0 };
    let webkitGesture = false;
    let lastGestureScale = 1;
    const buttons = h.buttons ?? [0];
    const enabled = () => h.enabled?.() ?? true;

    const local = (e: { clientX: number; clientY: number }) => {
      const r = el.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };
    const cancelPress = () => {
      if (press?.timer) clearTimeout(press.timer);
      press = null;
    };
    const setDragging = (on: boolean) => {
      if (on === dragging) return;
      dragging = on;
      h.panning?.(on);
    };
    const twoFinger = () => {
      const [a, b] = [...pts.values()];
      return pinchOf(a, b);
    };

    const down = (e: PointerEvent) => {
      if (e.pointerType === 'mouse' && !buttons.includes(e.button)) return;
      if (!enabled()) return;
      e.preventDefault(); // no text selection, no native drag of the canvas
      el.setPointerCapture(e.pointerId);
      const p = local(e);
      pts.set(e.pointerId, p);
      if (pts.size === 1) {
        cancelPress();
        press = { id: e.pointerId, x: p.x, y: p.y, timer: null };
        if (e.pointerType !== 'mouse') {
          press.timer = setTimeout(() => {
            if (press) h.menu?.(press.x, press.y);
            press = null;
          }, LONG_PRESS_MS);
        }
        setDragging(true);
      } else if (pts.size === 2) {
        cancelPress();
        const t = twoFinger();
        pinchDist = t.d;
        pinchMid = t.m;
      }
    };

    const move = (e: PointerEvent) => {
      const p = local(e);
      h.hover?.(p.x, p.y);
      const prev = pts.get(e.pointerId);
      if (!prev) return;
      pts.set(e.pointerId, p);
      if (pts.size === 2) {
        const t = twoFinger();
        if (pinchDist > 0) h.zoom?.(t.d / pinchDist, t.m.x, t.m.y);
        h.pan?.(t.m.x - pinchMid.x, t.m.y - pinchMid.y);
        pinchDist = t.d;
        pinchMid = t.m;
        return;
      }
      if (press && Math.hypot(p.x - press.x, p.y - press.y) > MOVE_SLOP) cancelPress();
      // The pan follows the pointer from the first pixel (a 1 px drag moves 1 px).
      h.pan?.(p.x - prev.x, p.y - prev.y);
    };

    const up = (e: PointerEvent) => {
      if (!pts.has(e.pointerId)) return;
      pts.delete(e.pointerId);
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      if (press?.id === e.pointerId) cancelPress();
      if (pts.size < 2) pinchDist = 0;
      if (pts.size === 0) setDragging(false);
    };

    const wheel = (e: WheelEvent) => {
      if (!enabled()) return;
      e.preventDefault();
      if (e.ctrlKey && webkitGesture) return;
      const p = local(e);
      const f = (h.wheelFactor ?? defaultWheelFactor)(e.deltaY, e.deltaMode, e.ctrlKey);
      if (Number.isFinite(f) && f > 0 && f !== 1) h.zoom?.(f, p.x, p.y);
    };

    const gstart = (e: Event) => {
      e.preventDefault();
      webkitGesture = true;
      lastGestureScale = 1;
    };
    const gchange = (e: Event) => {
      e.preventDefault();
      const g = e as GestureEventLike;
      const p = local(g);
      if (g.scale > 0 && lastGestureScale > 0) h.zoom?.(g.scale / lastGestureScale, p.x, p.y);
      lastGestureScale = g.scale;
    };
    const gend = (e: Event) => {
      e.preventDefault();
      webkitGesture = false;
    };

    const dbl = (e: Event) => {
      e.preventDefault();
      h.fit?.();
    };
    const ctx = (e: MouseEvent) => {
      e.preventDefault(); // never the native (grey) menu: Night Red
      const p = local(e);
      cancelPress();
      h.menu?.(p.x, p.y);
    };
    const leave = () => {
      if (pts.size) return; // a captured drag keeps reporting
      h.hover?.(NaN, NaN);
    };

    const opts = { passive: false } as AddEventListenerOptions;
    el.addEventListener('pointerdown', down as EventListener);
    el.addEventListener('pointermove', move as EventListener);
    el.addEventListener('pointerup', up as EventListener);
    el.addEventListener('pointercancel', up as EventListener);
    el.addEventListener('lostpointercapture', up as EventListener);
    el.addEventListener('pointerleave', leave);
    el.addEventListener('wheel', wheel as EventListener, opts);
    el.addEventListener('dblclick', dbl);
    el.addEventListener('contextmenu', ctx as EventListener);
    el.addEventListener('gesturestart', gstart);
    el.addEventListener('gesturechange', gchange);
    el.addEventListener('gestureend', gend);
    return () => {
      cancelPress();
      el.removeEventListener('pointerdown', down as EventListener);
      el.removeEventListener('pointermove', move as EventListener);
      el.removeEventListener('pointerup', up as EventListener);
      el.removeEventListener('pointercancel', up as EventListener);
      el.removeEventListener('lostpointercapture', up as EventListener);
      el.removeEventListener('pointerleave', leave);
      el.removeEventListener('wheel', wheel as EventListener, opts);
      el.removeEventListener('dblclick', dbl);
      el.removeEventListener('contextmenu', ctx as EventListener);
      el.removeEventListener('gesturestart', gstart);
      el.removeEventListener('gesturechange', gchange);
      el.removeEventListener('gestureend', gend);
    };
  };
}
