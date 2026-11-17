/**
 * Viewer gestures as a Svelte 5 attachment ({@attach gestures({...})}):
 * drag to pan (pointer capture, so the drag survives leaving the canvas),
 * wheel and trackpad pinch to zoom about the pointer, two-finger pinch on a
 * touch screen, double-click / double-tap to fit, long-press (touch, pen) or
 * right-click (mouse) for the context menu.
 *
 * Engine notes (stack-capabilities.md, "Pointer events and gestures"):
 * - A trackpad pinch arrives as `wheel` with ctrlKey in Chromium and in
 *   WebKit on macOS. WebKit also fires its non-standard gesturestart /
 *   gesturechange; while such a gesture is active the ctrl+wheel events are
 *   ignored so a pinch is never applied twice.
 * - The wheel listener is registered on the element with passive: false
 *   (WebKit makes document-level wheel listeners passive for apps linked on
 *   a recent SDK), otherwise preventDefault is ignored and the page scrolls.
 * - `touch-action: none` on the element is required, or the browser takes
 *   the pinch for page zoom.
 */

import type { Attachment } from 'svelte/attachments';

export interface GestureHandlers {
  pan?: (dx: number, dy: number) => void;
  /** factor > 1 zooms in; x, y in CSS px relative to the element. */
  zoom?: (factor: number, x: number, y: number) => void;
  fit?: () => void;
  menu?: (x: number, y: number) => void;
  /** Pointer position for readouts (null when it leaves). */
  hover?: (x: number, y: number) => void;
}

const LONG_PRESS_MS = 500;
const MOVE_SLOP = 6;

interface GestureEventLike extends UIEvent {
  scale: number;
  clientX: number;
  clientY: number;
}

export function gestures(h: GestureHandlers): Attachment<HTMLElement> {
  return (el) => {
    const pts = new Map<number, { x: number; y: number }>();
    let press: { id: number; x: number; y: number; timer: ReturnType<typeof setTimeout> | null } | null = null;
    let pinchDist = 0;
    let pinchMid = { x: 0, y: 0 };
    let webkitGesture = false;
    let lastGestureScale = 1;

    const local = (e: { clientX: number; clientY: number }) => {
      const r = el.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };
    const cancelPress = () => {
      if (press?.timer) clearTimeout(press.timer);
      press = null;
    };
    const twoFinger = () => {
      const [a, b] = [...pts.values()];
      return { d: Math.hypot(a.x - b.x, a.y - b.y), m: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } };
    };

    const down = (e: PointerEvent) => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
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
      if (!press) h.pan?.(p.x - prev.x, p.y - prev.y);
    };

    const up = (e: PointerEvent) => {
      pts.delete(e.pointerId);
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
      if (press?.id === e.pointerId) cancelPress();
      if (pts.size < 2) pinchDist = 0;
    };

    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      if (e.ctrlKey && webkitGesture) return;
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
      const k = e.ctrlKey ? 0.01 : 0.0018; // pinch deltas are small and frequent
      const p = local(e);
      h.zoom?.(Math.exp(-e.deltaY * unit * k), p.x, p.y);
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
      h.zoom?.(g.scale / lastGestureScale, p.x, p.y);
      lastGestureScale = g.scale;
    };
    const gend = (e: Event) => {
      e.preventDefault();
      webkitGesture = false;
    };

    const dbl = () => h.fit?.();
    const ctx = (e: MouseEvent) => {
      e.preventDefault(); // never the native (grey) menu: Night Red
      const p = local(e);
      cancelPress();
      h.menu?.(p.x, p.y);
    };
    const leave = () => h.hover?.(NaN, NaN);

    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    el.addEventListener('pointerleave', leave);
    el.addEventListener('wheel', wheel, { passive: false });
    el.addEventListener('dblclick', dbl);
    el.addEventListener('contextmenu', ctx);
    el.addEventListener('gesturestart', gstart);
    el.addEventListener('gesturechange', gchange);
    el.addEventListener('gestureend', gend);
    return () => {
      cancelPress();
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      el.removeEventListener('pointerleave', leave);
      el.removeEventListener('wheel', wheel);
      el.removeEventListener('dblclick', dbl);
      el.removeEventListener('contextmenu', ctx);
      el.removeEventListener('gesturestart', gstart);
      el.removeEventListener('gesturechange', gchange);
      el.removeEventListener('gestureend', gend);
    };
  };
}
