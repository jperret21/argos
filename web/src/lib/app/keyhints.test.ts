import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOLD_MS, installKeyHints, isLoneModifier, keyHints, keyHintsVisible } from './keyhints.svelte';

/** A minimal EventTarget for the window and the document. */
class FakeTarget implements Pick<EventTarget, 'addEventListener' | 'removeEventListener'> {
  listeners = new Map<string, Set<(e: Event) => void>>();
  addEventListener(type: string, fn: EventListenerOrEventListenerObject | null): void {
    if (typeof fn !== 'function') return;
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(fn);
  }
  removeEventListener(type: string, fn: EventListenerOrEventListenerObject | null): void {
    if (typeof fn === 'function') this.listeners.get(type)?.delete(fn);
  }
  fire(type: string, e: Partial<KeyboardEvent> = {}): void {
    const ev = { shiftKey: false, altKey: false, ctrlKey: false, metaKey: false, repeat: false, ...e } as Event;
    for (const fn of this.listeners.get(type) ?? []) fn(ev);
  }
  count(): number {
    let n = 0;
    for (const s of this.listeners.values()) n += s.size;
    return n;
  }
}

let win: FakeTarget;
let doc: FakeTarget;
let detach: () => void;

beforeEach(() => {
  vi.useFakeTimers();
  win = new FakeTarget();
  doc = new FakeTarget();
  keyHints.held = false;
  keyHints.pinned = false;
});
afterEach(() => {
  detach?.();
  vi.useRealTimers();
});

describe('key hints (hold Mod alone)', () => {
  it('Cmd on macOS, Ctrl elsewhere, alone', () => {
    const k = (key: string, mods: Partial<KeyboardEvent> = {}) =>
      ({ key, shiftKey: false, altKey: false, ctrlKey: false, metaKey: false, ...mods }) as KeyboardEvent;
    expect(isLoneModifier(k('Meta', { metaKey: true }), true)).toBe(true);
    expect(isLoneModifier(k('Control', { ctrlKey: true }), true)).toBe(false);
    expect(isLoneModifier(k('Control', { ctrlKey: true }), false)).toBe(true);
    expect(isLoneModifier(k('Meta', { metaKey: true, shiftKey: true }), true)).toBe(false);
  });

  it('shows after 450 ms of holding, clears on key-up', () => {
    detach = installKeyHints(win, { mac: true, doc });
    win.fire('keydown', { key: 'Meta', metaKey: true });
    vi.advanceTimersByTime(HOLD_MS - 1);
    expect(keyHintsVisible()).toBe(false);
    vi.advanceTimersByTime(1);
    expect(keyHintsVisible()).toBe(true);
    win.fire('keyup', { key: 'Meta' });
    expect(keyHintsVisible()).toBe(false);
  });

  it('a chord (Mod+K) never flashes the hints', () => {
    detach = installKeyHints(win, { mac: false, doc });
    win.fire('keydown', { key: 'Control', ctrlKey: true });
    vi.advanceTimersByTime(200);
    win.fire('keydown', { key: 'k', ctrlKey: true });
    vi.advanceTimersByTime(1000);
    expect(keyHintsVisible()).toBe(false);
  });

  it('any other key, blur or a hidden page clears them', () => {
    detach = installKeyHints(win, { mac: true, doc });
    for (const clear of [
      () => win.fire('keydown', { key: 'a', metaKey: true }),
      () => win.fire('blur'),
      () => doc.fire('visibilitychange'),
    ]) {
      win.fire('keydown', { key: 'Meta', metaKey: true });
      vi.advanceTimersByTime(HOLD_MS);
      expect(keyHintsVisible()).toBe(true);
      clear();
      expect(keyHintsVisible()).toBe(false);
      win.fire('keyup', { key: 'Meta' });
    }
  });

  it('key repeat does not restart the wait', () => {
    detach = installKeyHints(win, { mac: true, doc });
    win.fire('keydown', { key: 'Meta', metaKey: true });
    vi.advanceTimersByTime(300);
    win.fire('keydown', { key: 'Meta', metaKey: true, repeat: true });
    vi.advanceTimersByTime(150);
    expect(keyHintsVisible()).toBe(true);
  });

  it('pinned shows them without the key (gallery), detach removes every listener', () => {
    keyHints.pinned = true;
    expect(keyHintsVisible()).toBe(true);
    detach = installKeyHints(win, { mac: true, doc });
    expect(win.count()).toBe(3);
    expect(doc.count()).toBe(1);
    detach();
    expect(win.count()).toBe(0);
    expect(doc.count()).toBe(0);
  });
});
