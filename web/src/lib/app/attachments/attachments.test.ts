import { describe, expect, it, vi } from 'vitest';
import { defaultWheelFactor, gestures, MOVE_SLOP, pinchOf } from './gestures';
import { handleKey, valueHandle } from './handle';
import { clampSplit, snapSplit, splitter, splitterKey } from './splitter';

/** An element good enough for the attachments: events, pointer capture, a box. */
class FakeEl extends EventTarget {
  captured = new Set<number>();
  rect = { left: 10, top: 20, width: 400, height: 300 };
  setPointerCapture(id: number): void {
    this.captured.add(id);
  }
  releasePointerCapture(id: number): void {
    this.captured.delete(id);
  }
  hasPointerCapture(id: number): boolean {
    return this.captured.has(id);
  }
  getBoundingClientRect(): DOMRect {
    return this.rect as DOMRect;
  }
}

/** An event with the fields the handlers read (Node has no PointerEvent). */
function ev(type: string, fields: Record<string, unknown> = {}): Event {
  const e = new Event(type, { cancelable: true });
  for (const [k, v] of Object.entries(fields)) Object.defineProperty(e, k, { value: v });
  return e;
}
const pointer = (type: string, x: number, y: number, extra: Record<string, unknown> = {}) =>
  ev(type, { pointerId: 1, pointerType: 'mouse', button: 0, clientX: x, clientY: y, ...extra });
const key = (k: string, extra: Record<string, unknown> = {}) =>
  ev('keydown', { key: k, shiftKey: false, altKey: false, ...extra });

describe('splitter', () => {
  it('clamps, rounds and snaps', () => {
    const o = { min: 36, max: () => 500 };
    expect(clampSplit(o, 12)).toBe(36);
    expect(clampSplit(o, 612.6)).toBe(500);
    expect(clampSplit(o, 100.4)).toBe(100);
    expect(snapSplit(291, [295])).toBe(295);
    expect(snapSplit(280, [295])).toBe(280);
  });

  it('follows the WAI-ARIA keys of a bottom pane (invert: ArrowUp grows it)', () => {
    const o = { axis: 'y' as const, invert: true, min: 36, max: () => 600, reset: 295 };
    expect(splitterKey(o, 'ArrowUp', false, 200)).toBe(208);
    expect(splitterKey(o, 'ArrowDown', true, 200)).toBe(160);
    expect(splitterKey(o, 'Home', false, 200)).toBe(36);
    expect(splitterKey(o, 'End', false, 200)).toBe(600);
    expect(splitterKey(o, 'Enter', false, 200)).toBe(295);
    expect(splitterKey(o, 'a', false, 200)).toBeNull();
    // A right rail: ArrowLeft widens it.
    expect(splitterKey({ ...o, axis: 'x' }, 'ArrowLeft', false, 400)).toBe(408);
  });

  it('drags with pointer capture, exactly, and reports the drag', () => {
    let v = 295;
    const drag = vi.fn();
    const el = new FakeEl();
    const detach = splitter({
      axis: 'y',
      invert: true,
      get: () => v,
      set: (x) => (v = x),
      min: 36,
      max: () => 600,
      reset: 295,
      snaps: [295],
      ondrag: drag,
    })(el as unknown as HTMLElement) as () => void;
    el.dispatchEvent(pointer('pointerdown', 0, 500));
    expect(el.captured.has(1)).toBe(true);
    expect(drag).toHaveBeenLastCalledWith(true);
    el.dispatchEvent(pointer('pointermove', 0, 450)); // up 50 px: the bottom band grows
    expect(v).toBe(345);
    el.dispatchEvent(pointer('pointermove', 0, 496)); // within 8 px of the detent
    expect(v).toBe(295);
    el.dispatchEvent(pointer('pointerup', 0, 496));
    expect(el.captured.size).toBe(0);
    expect(drag).toHaveBeenLastCalledWith(false);
    el.dispatchEvent(key('ArrowUp', { shiftKey: true }));
    expect(v).toBe(335);
    el.dispatchEvent(ev('dblclick'));
    expect(v).toBe(295);
    detach();
    el.dispatchEvent(key('Home'));
    expect(v).toBe(295); // listeners removed
  });
});

describe('value handle', () => {
  it('steps by one, Shift x10, Alt /10 when fine, Home / End to the bounds', () => {
    const o = { step: 16, min: () => 0, max: () => 65535 };
    expect(handleKey(o, 'ArrowRight', { shift: false, alt: false }, 100)).toBe(116);
    expect(handleKey(o, 'ArrowLeft', { shift: true, alt: false }, 1000)).toBe(840);
    expect(handleKey(o, 'ArrowLeft', { shift: false, alt: true }, 1000)).toBe(984); // not fine: plain step
    expect(handleKey({ ...o, step: 0.01, fine: true }, 'ArrowUp', { shift: false, alt: true }, 0.25)).toBeCloseTo(0.251);
    expect(handleKey(o, 'End', { shift: false, alt: false }, 3)).toBe(65535);
    expect(handleKey(o, 'x', { shift: false, alt: false }, 3)).toBeNull();
  });

  it('follows the pointer while captured and clamps to the bounds', () => {
    let v = 500;
    const el = new FakeEl();
    valueHandle({
      axis: 'x',
      toValue: (cx) => cx * 10,
      get: () => v,
      set: (x) => (v = x),
      step: 1,
      min: () => 0,
      max: () => 4000,
    })(el as unknown as HTMLElement);
    el.dispatchEvent(pointer('pointermove', 30, 0));
    expect(v).toBe(500); // not grabbed yet
    el.dispatchEvent(pointer('pointerdown', 50, 0));
    el.dispatchEvent(pointer('pointermove', 30, 0));
    expect(v).toBe(300);
    el.dispatchEvent(pointer('pointermove', 900, 0));
    expect(v).toBe(4000);
    el.dispatchEvent(pointer('pointerup', 900, 0));
    el.dispatchEvent(pointer('pointermove', 10, 0));
    expect(v).toBe(4000);
  });
});

describe('gestures', () => {
  it('pans by the pointer travel, reports the drag, and hovers in element coordinates', () => {
    const el = new FakeEl();
    const pans: [number, number][] = [];
    const hover = vi.fn();
    const panning = vi.fn();
    gestures({ pan: (dx, dy) => pans.push([dx, dy]), hover, panning })(el as unknown as HTMLElement);
    el.dispatchEvent(pointer('pointermove', 110, 120));
    expect(hover).toHaveBeenLastCalledWith(100, 100);
    el.dispatchEvent(pointer('pointerdown', 110, 120));
    expect(panning).toHaveBeenLastCalledWith(true);
    el.dispatchEvent(pointer('pointermove', 113, 124));
    el.dispatchEvent(pointer('pointermove', 120, 124));
    expect(pans).toEqual([
      [3, 4],
      [7, 0],
    ]);
    el.dispatchEvent(pointer('pointerup', 120, 124));
    expect(panning).toHaveBeenLastCalledWith(false);
    el.dispatchEvent(ev('pointerleave'));
    expect(hover).toHaveBeenLastCalledWith(NaN, NaN);
  });

  it('ignores the buttons it was not given and does nothing while disabled', () => {
    const el = new FakeEl();
    const pan = vi.fn();
    let on = false;
    gestures({ pan, buttons: [0, 1], enabled: () => on })(el as unknown as HTMLElement);
    el.dispatchEvent(pointer('pointerdown', 0, 0, { button: 1 }));
    el.dispatchEvent(pointer('pointermove', 5, 0));
    expect(pan).not.toHaveBeenCalled();
    on = true;
    el.dispatchEvent(pointer('pointerdown', 0, 0, { button: 2 }));
    el.dispatchEvent(pointer('pointermove', 5, 0));
    expect(pan).not.toHaveBeenCalled();
    el.dispatchEvent(pointer('pointerdown', 0, 0, { button: 1 }));
    el.dispatchEvent(pointer('pointermove', 5, 0));
    expect(pan).toHaveBeenCalledWith(5, 0);
  });

  it('zooms about the pointer on the wheel, with the factor the caller gives', () => {
    const el = new FakeEl();
    const zoom = vi.fn();
    gestures({ zoom, wheelFactor: (dy) => (dy < 0 ? 2 : 0.5) })(el as unknown as HTMLElement);
    const w = ev('wheel', { deltaY: -100, deltaMode: 0, ctrlKey: false, clientX: 60, clientY: 70 });
    el.dispatchEvent(w);
    expect(w.defaultPrevented).toBe(true);
    expect(zoom).toHaveBeenCalledWith(2, 50, 50);
  });

  it('never lets the native context menu through, and pinches with two pointers', () => {
    const el = new FakeEl();
    const zoom = vi.fn();
    const menu = vi.fn();
    gestures({ zoom, menu })(el as unknown as HTMLElement);
    const c = ev('contextmenu', { clientX: 20, clientY: 30 });
    el.dispatchEvent(c);
    expect(c.defaultPrevented).toBe(true);
    expect(menu).toHaveBeenCalledWith(10, 10);
    const touch = (type: string, id: number, x: number) =>
      ev(type, { pointerId: id, pointerType: 'touch', button: 0, clientX: x, clientY: 20 });
    el.dispatchEvent(touch('pointerdown', 1, 110));
    el.dispatchEvent(touch('pointerdown', 2, 210));
    el.dispatchEvent(touch('pointermove', 2, 310)); // distance 100 -> 200
    expect(zoom).toHaveBeenCalledWith(2, 200, 0); // about the new midpoint
  });

  it('keeps the wheel law and the pinch maths of the lab', () => {
    expect(defaultWheelFactor(0, 0, false)).toBe(1);
    expect(defaultWheelFactor(-100, 0, false)).toBeCloseTo(Math.exp(0.18));
    expect(defaultWheelFactor(1, 1, false)).toBeCloseTo(Math.exp(-16 * 0.0018));
    expect(pinchOf({ x: 0, y: 0 }, { x: 3, y: 4 })).toEqual({ d: 5, m: { x: 1.5, y: 2 } });
    expect(MOVE_SLOP).toBe(6);
  });
});
