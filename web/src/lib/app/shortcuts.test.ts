import { describe, expect, it, vi } from 'vitest';
import { KEYMAP } from './keymap';
import {
  ariaShortcut,
  chordOf,
  type DispatchEvent,
  formatShortcut,
  matchesShortcut,
  parseShortcut,
  scopeActive,
  scopesOverlap,
  ShortcutConflictError,
  type ShortcutDef,
  ShortcutRegistry,
} from './shortcuts';

const ev = (key: string, extra: Partial<DispatchEvent> = {}): DispatchEvent & { prevented: boolean } => {
  const e = {
    key,
    shiftKey: false,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    defaultPrevented: false,
    prevented: false,
    preventDefault() {
      e.prevented = true;
      e.defaultPrevented = true;
    },
    ...extra,
  };
  return e;
};

/** A text field as the event target (isTypingTarget looks for closest('input…')). */
const textField = { closest: (s: string) => (s.includes('input') ? {} : null) } as unknown as EventTarget;
const button = { closest: () => null } as unknown as EventTarget;

describe('shortcut specs with modifiers', () => {
  it('parses Mod, Shift, Alt and the plus key', () => {
    expect(parseShortcut('Mod+Shift+O')).toEqual({ key: 'O', mod: true, shift: true, alt: false });
    expect(parseShortcut('Alt+ArrowLeft')).toEqual({ key: 'ArrowLeft', mod: false, shift: false, alt: true });
    expect(parseShortcut('Ctrl+,')).toEqual({ key: ',', mod: true, shift: false, alt: false });
    expect(parseShortcut('+').key).toBe('+');
    expect(parseShortcut('Mod++')).toEqual({ key: '+', mod: true, shift: false, alt: false });
    expect(parseShortcut('Esc').key).toBe('Escape');
    expect(parseShortcut('Space').key).toBe(' ');
  });

  it('formats with macOS glyphs in Apple order, or words elsewhere', () => {
    expect(formatShortcut('Mod+Shift+O', true)).toBe('⇧⌘O');
    expect(formatShortcut('Mod+Shift+O', false)).toBe('Ctrl+Shift+O');
    expect(formatShortcut('Mod+,', true)).toBe('⌘,');
    expect(formatShortcut('Alt+ArrowLeft', true)).toBe('⌥←');
    expect(formatShortcut('Alt+ArrowLeft', false)).toBe('Alt+←');
    expect(formatShortcut('Mod+Q', false)).toBe('Ctrl+Q');
    expect(formatShortcut('PageDown', false)).toBe('PgDn');
  });

  it('builds aria-keyshortcuts with Meta on macOS and Control elsewhere', () => {
    expect(ariaShortcut('Mod+Shift+O', true)).toBe('Meta+Shift+O');
    expect(ariaShortcut('Mod+O', false)).toBe('Control+O');
    expect(ariaShortcut('Alt+ArrowLeft', false)).toBe('Alt+ArrowLeft');
    expect(ariaShortcut('Space', false)).toBe('Space');
  });

  it('matches Cmd on macOS and Ctrl elsewhere, exactly', () => {
    expect(matchesShortcut(ev('o', { metaKey: true }), 'Mod+O', true)).toBe(true);
    expect(matchesShortcut(ev('o', { ctrlKey: true }), 'Mod+O', true)).toBe(false);
    expect(matchesShortcut(ev('o', { ctrlKey: true }), 'Mod+O', false)).toBe(true);
    expect(matchesShortcut(ev('o', { metaKey: true }), 'Mod+O', false)).toBe(false);
    // The single key never fires with a modifier, and the chord never without it.
    expect(matchesShortcut(ev('o', { metaKey: true }), 'O', true)).toBe(false);
    expect(matchesShortcut(ev('o'), 'Mod+O', true)).toBe(false);
  });

  it('tells Mod+O and Mod+Shift+O apart (Shift exact on letters)', () => {
    expect(matchesShortcut(ev('O', { metaKey: true, shiftKey: true }), 'Mod+Shift+O', true)).toBe(true);
    expect(matchesShortcut(ev('o', { metaKey: true, shiftKey: true }), 'Mod+Shift+O', true)).toBe(true);
    expect(matchesShortcut(ev('O', { metaKey: true, shiftKey: true }), 'Mod+O', true)).toBe(false);
  });

  it('matches Alt chords on the physical key when Option changes the character', () => {
    // macOS Option+N types "˜": the code still says KeyN.
    expect(matchesShortcut(ev('˜', { altKey: true, code: 'KeyN' }), 'Alt+N', true)).toBe(true);
    expect(matchesShortcut(ev('ArrowLeft', { altKey: true }), 'Alt+ArrowLeft', true)).toBe(true);
    expect(matchesShortcut(ev('ArrowLeft'), 'Alt+ArrowLeft', true)).toBe(false);
  });

  it('matches digits by the physical key too (AZERTY 1 without Shift, Cmd+1)', () => {
    expect(matchesShortcut(ev('&', { code: 'Digit1' }), '1', false)).toBe(true);
    expect(matchesShortcut(ev('&', { code: 'Digit1', metaKey: true }), 'Mod+1', true)).toBe(true);
    expect(matchesShortcut(ev('1', { metaKey: true, code: 'Digit1' }), '1', true)).toBe(false);
  });

  it('matches symbols whether or not the layout needs Shift', () => {
    expect(matchesShortcut(ev('?', { shiftKey: true }), '?', false)).toBe(true);
    expect(matchesShortcut(ev('?'), '?', false)).toBe(true);
    expect(matchesShortcut(ev(',', { metaKey: true }), 'Mod+,', true)).toBe(true);
  });

  it('gives one chord identity to equivalent specs', () => {
    expect(chordOf('Shift+1')).toBe(chordOf('1'));
    expect(chordOf('Cmd+o')).toBe(chordOf('Mod+O'));
    expect(chordOf('Shift+A')).not.toBe(chordOf('A'));
  });
});

describe('scopes', () => {
  it('overlap when global, equal, or nested', () => {
    expect(scopesOverlap('global', 'imaging')).toBe(true);
    expect(scopesOverlap('analyze', 'analyze.r1')).toBe(true);
    expect(scopesOverlap('analyze.r1', 'analyze.r2')).toBe(false);
    expect(scopesOverlap('imaging', 'sequencer')).toBe(false);
  });

  it('a section scope is active while one of its sub-scopes is', () => {
    expect(scopeActive('analyze', ['global', 'analyze.r1'])).toBe(true);
    expect(scopeActive('analyze.r2', ['global', 'analyze.r1'])).toBe(false);
    expect(scopeActive('global', [])).toBe(true);
  });
});

describe('ShortcutRegistry', () => {
  const defs: ShortcutDef[] = [
    { id: 'log', keys: ['L'], label: 'Log', scope: 'global' },
    { id: 'nav', keys: ['F2'], label: 'Observe', scope: 'global', inText: true },
    { id: 'open', keys: ['Mod+O'], label: 'Open', scope: 'global' },
    { id: 'abort', keys: ['Escape'], label: 'Abort', scope: 'global', inText: true, evenIfHandled: true },
    { id: 'obs.fit', keys: ['F'], label: 'Fit', scope: 'imaging' },
    { id: 'r1.fit', keys: ['F'], label: 'Fit plots', scope: 'analyze.r1' },
    { id: 'copy', keys: ['Mod+C'], label: 'Copy', scope: 'global' },
  ];
  const make = () => new ShortcutRegistry(defs, { mac: true, desktop: false });

  it('detects a chord used twice in overlapping scopes', () => {
    const r = make();
    expect(() => r.define({ id: 'labels', keys: ['L'], label: 'Labels', scope: 'imaging' })).toThrow(
      ShortcutConflictError,
    );
    expect(() => r.define({ id: 'plan.fit', keys: ['F'], label: 'Fit', scope: 'analyze' })).toThrow(
      /F is both/,
    );
    // Same key in disjoint scopes is fine; redefining an id replaces it.
    expect(() => r.define({ id: 'plan.f', keys: ['F'], label: 'Fit', scope: 'sequencer' })).not.toThrow();
    expect(() => r.define({ id: 'log', keys: ['L'], label: 'Activity log', scope: 'global' })).not.toThrow();
  });

  it('keeps the whole keymap of README 3.10 conflict-free', () => {
    expect(ShortcutRegistry.conflictsOf(KEYMAP)).toEqual([]);
    expect(() => new ShortcutRegistry(KEYMAP, { mac: false, desktop: true })).not.toThrow();
  });

  it('dispatches only bound, active bindings, most specific scope first', () => {
    const r = make();
    const fit = vi.fn();
    const plots = vi.fn();
    r.handle('obs.fit', fit);
    r.handle('r1.fit', plots);
    r.setScopes(['analyze', 'analyze.r1']);
    const e = ev('f', { target: button });
    expect(r.dispatch(e)).toBe(true);
    expect(plots).toHaveBeenCalledTimes(1);
    expect(fit).not.toHaveBeenCalled();
    expect(e.prevented).toBe(true);
    r.setScopes(['connection']);
    expect(r.dispatch(ev('f', { target: button }))).toBe(false);
  });

  it('suppresses single keys in a text field but not F-keys, Mod chords or Escape', () => {
    const r = make();
    const log = vi.fn();
    const nav = vi.fn();
    const open = vi.fn();
    const abort = vi.fn();
    r.handle('log', log);
    r.handle('nav', nav);
    r.handle('open', open);
    r.handle('abort', abort);
    expect(r.dispatch(ev('l', { target: textField }))).toBe(false);
    expect(r.dispatch(ev('F2', { target: textField }))).toBe(true);
    expect(r.dispatch(ev('o', { metaKey: true, target: textField }))).toBe(true);
    expect(r.dispatch(ev('Escape', { target: textField }))).toBe(true);
    expect([log, nav, open, abort].map((f) => f.mock.calls.length)).toEqual([0, 1, 1, 1]);
  });

  it('reserves the bound F-keys and Mod chords (not letters, not editing chords) for layers to swallow', () => {
    const r = make();
    expect(r.reserves(ev('F2'))).toBe(false); // nothing bound yet
    r.handle('nav', vi.fn());
    r.handle('open', vi.fn());
    r.handle('log', vi.fn());
    r.handle('copy', vi.fn());
    expect(r.reserves(ev('F2'))).toBe(true);
    expect(r.reserves(ev('o', { metaKey: true }))).toBe(true);
    expect(r.reserves(ev('l'))).toBe(false); // typing an L in a dialog field stays typing
    expect(r.reserves(ev('c', { metaKey: true }))).toBe(false); // copy stays the browser's
    expect(r.reserves(ev('F11'))).toBe(false); // not the app's: full screen stays
  });

  it('leaves the editing chords to text fields (Mod+C copies the text)', () => {
    const r = make();
    const copy = vi.fn();
    r.handle('copy', copy);
    expect(r.dispatch(ev('c', { metaKey: true, target: textField }))).toBe(false);
    expect(r.dispatch(ev('c', { metaKey: true, target: button }))).toBe(true);
  });

  it('skips keys a component already handled, except the safety key', () => {
    const r = make();
    const log = vi.fn();
    const abort = vi.fn();
    r.handle('log', log);
    r.handle('abort', abort);
    expect(r.dispatch(ev('l', { defaultPrevented: true }))).toBe(false);
    expect(r.dispatch(ev('Escape', { defaultPrevented: true }))).toBe(true);
    expect(abort).toHaveBeenCalledTimes(1);
  });

  it('only lets the safety key through while a modal is open', () => {
    let modal = true;
    const r = new ShortcutRegistry(defs, { mac: true, desktop: false, blocked: () => modal });
    const log = vi.fn();
    const abort = vi.fn();
    r.handle('log', log);
    r.handle('abort', abort);
    expect(r.dispatch(ev('l'))).toBe(false);
    expect(r.dispatch(ev('Escape'))).toBe(true);
    modal = false;
    expect(r.dispatch(ev('l'))).toBe(true);
  });

  it('ignores auto-repeat unless the binding allows it, and IME composition', () => {
    const r = make();
    const log = vi.fn();
    r.handle('log', log);
    expect(r.dispatch(ev('l', { repeat: true }))).toBe(false);
    expect(r.dispatch(ev('l', { isComposing: true }))).toBe(false);
    expect(r.dispatch(ev('l'))).toBe(true);
  });

  it('runs the newest handler and falls back when it is unbound', () => {
    const r = make();
    const first = vi.fn();
    const second = vi.fn();
    r.handle('log', first);
    const off = r.handle('log', second);
    r.dispatch(ev('l'));
    off();
    r.dispatch(ev('l'));
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('respects a `when` guard', () => {
    const r = make();
    let ready = false;
    const log = vi.fn();
    r.handle('log', log, () => ready);
    expect(r.dispatch(ev('l'))).toBe(false);
    ready = true;
    expect(r.dispatch(ev('l'))).toBe(true);
  });

  it('lists the sheet without planned rows and desktop-only rows in a browser', () => {
    const browser = new ShortcutRegistry(KEYMAP, { mac: true, desktop: false });
    const rows = browser.sheet().flatMap((g) => g.rows.map((r) => r.id));
    expect(rows).toContain('log.toggle');
    expect(rows).toContain('help.shortcuts');
    expect(rows).not.toContain('file.open-fits'); // planned
    expect(rows).not.toContain('nav.observe.desktop'); // desktop only
    const desktop = new ShortcutRegistry(KEYMAP, { mac: true, desktop: true });
    expect(desktop.sheet().flatMap((g) => g.rows.map((r) => r.id))).toContain('nav.observe.desktop');
    expect(browser.keyFor('file.open-fits')).toBeUndefined();
    expect(browser.keyFor('log.toggle')).toBe('L');
  });

  it('refuses a handler for an id the keymap does not define', () => {
    expect(() => make().handle('nope', () => {})).toThrow(/not defined/);
  });
});
