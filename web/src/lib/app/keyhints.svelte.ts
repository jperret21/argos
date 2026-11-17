/**
 * Key hints (web/lab/PROPOSAL.md 3.3, BRAND 7 amendment; promoted from
 * src/lab/controls/hints.svelte.ts): hold the platform modifier ALONE (Cmd
 * on macOS, Ctrl elsewhere, as the shortcut registry decides) for HOLD_MS and
 * every available control that has a shortcut shows its key cap in place.
 * Releasing the modifier, pressing any other key (a real chord such as
 * Mod+K never flashes the hints), the window losing focus or the page being
 * hidden clears them.
 *
 * Why: BRAND 7 makes frequent tools icon-only; their shortcuts live in the
 * tooltips (one at a time) and the "?" sheet (away from the controls).
 * Holding a key to see them all, where they act, teaches the keyboard path
 * without a modal. Holding Mod alone does nothing else in the app.
 *
 * The caps are neutral (--fg on --surface, --border edge), never brass: they
 * appear on every control at once. The keys come from the controls'
 * `shortcut` props, which the screens take from the W1 registry
 * (`app.shortcuts.keyFor(id)`), so a cap is always a binding that works.
 *
 * `keyHints.pinned` shows them without the key (gallery and screenshots).
 * WebKit: the Meta key-up must still arrive while Cmd is held (PROPOSAL 9);
 * blur and visibilitychange clear the hints if it does not.
 */

import { detectMac } from './shortcuts';

export const HOLD_MS = 450;

export const keyHints = $state({ held: false, pinned: false });

/** True while the caps are shown. */
export function keyHintsVisible(): boolean {
  return keyHints.held || keyHints.pinned;
}

/** The fields of a KeyboardEvent the hints read. */
export interface HintKey {
  key: string;
  repeat?: boolean;
  shiftKey: boolean;
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
}

/** Is this key-down the platform modifier pressed on its own? */
export function isLoneModifier(e: HintKey, mac: boolean): boolean {
  if (e.shiftKey || e.altKey) return false;
  if (mac) return (e.key === 'Meta' || e.key === 'OS') && !e.ctrlKey;
  return e.key === 'Control' && !e.metaKey;
}

/** Where the hints listen: a window (or a fake one in tests). */
export type KeyHintTarget = Pick<EventTarget, 'addEventListener' | 'removeEventListener'>;

export interface KeyHintOptions {
  /** Cmd (macOS) or Ctrl: pass the registry's `mac` so the hints and the shortcuts agree. */
  mac?: boolean;
  /** Where visibilitychange is listened to (default: document when there is one). */
  doc?: KeyHintTarget | null;
  holdMs?: number;
}

/**
 * Listen on a window (key events in the capture phase, so a component that
 * stops propagation cannot leave the caps up). Returns the detach.
 * `installKeyHints(window, { mac: app.shortcuts.mac })` once in the shell.
 */
export function installKeyHints(target: KeyHintTarget, opts: KeyHintOptions = {}): () => void {
  const mac = opts.mac ?? detectMac();
  const holdMs = opts.holdMs ?? HOLD_MS;
  const doc = opts.doc === undefined ? ((globalThis.document as KeyHintTarget | undefined) ?? null) : opts.doc;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const modKey = mac ? 'Meta' : 'Control';

  const clear = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    keyHints.held = false;
  };
  const down = (ev: Event) => {
    const e = ev as unknown as HintKey;
    if (isLoneModifier(e, mac)) {
      if (e.repeat || timer !== null || keyHints.held) return; // already waiting or shown
      timer = setTimeout(() => {
        timer = null;
        keyHints.held = true;
      }, holdMs);
      return;
    }
    clear(); // any other key: a chord, not a request for hints
  };
  const up = (ev: Event) => {
    const e = ev as unknown as HintKey;
    if (e.key === modKey || (mac && e.key === 'OS')) clear();
  };
  const hidden = () => clear();

  target.addEventListener('keydown', down, true);
  target.addEventListener('keyup', up, true);
  target.addEventListener('blur', hidden);
  doc?.addEventListener('visibilitychange', hidden);
  return () => {
    clear();
    target.removeEventListener('keydown', down, true);
    target.removeEventListener('keyup', up, true);
    target.removeEventListener('blur', hidden);
    doc?.removeEventListener('visibilitychange', hidden);
  };
}

let autoDetach: (() => void) | null = null;

/**
 * Install the hints on `window` once, from the first control that has a
 * shortcut (Control.svelte calls it on mount), so every screen gets them
 * without wiring. The platform test is the registry's default
 * (`detectMac()`), so the caps and the shortcuts agree.
 */
export function ensureKeyHints(): void {
  if (autoDetach || typeof window === 'undefined') return;
  autoDetach = installKeyHints(window);
}

/** Remove the automatic installation (tests, hot reload). */
export function resetKeyHints(): void {
  autoDetach?.();
  autoDetach = null;
  keyHints.held = false;
}
