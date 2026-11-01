/**
 * Key hints (proposal): hold the platform modifier alone (Cmd on macOS,
 * Ctrl elsewhere) for HOLD_MS and every control that has a shortcut shows
 * its key cap in place; release hides them. Pressing any other key during
 * the wait cancels (a real chord such as Mod+K never flashes the hints).
 *
 * Why: BRAND 7 makes frequent tools icon-only; their shortcuts live in the
 * tooltips (one at a time) and the "?" sheet (away from the controls).
 * Holding a key to see them all, where they act, teaches the keyboard path
 * without a modal. Holding Mod alone does nothing in the app today.
 *
 * `pinned` shows them without the key (screenshots, the specimen's toggle).
 */

import { detectMac } from '../../lib/app/shortcuts';

export const HOLD_MS = 450;

export const hints = $state({ held: false, pinned: false });

export function hintsVisible(): boolean {
  return hints.held || hints.pinned;
}

export function installHints(target: Window = window): () => void {
  const mac = detectMac();
  const modKey = mac ? 'Meta' : 'Control';
  let timer: ReturnType<typeof setTimeout> | null = null;

  const clear = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
  const down = (e: KeyboardEvent) => {
    if (e.key === modKey && !e.repeat && !e.shiftKey && !e.altKey) {
      clear();
      timer = setTimeout(() => (hints.held = true), HOLD_MS);
      return;
    }
    // Any other key: a chord, not a request for hints.
    clear();
    hints.held = false;
  };
  const up = (e: KeyboardEvent) => {
    if (e.key === modKey) {
      clear();
      hints.held = false;
    }
  };
  const blur = () => {
    clear();
    hints.held = false;
  };

  target.addEventListener('keydown', down, true);
  target.addEventListener('keyup', up, true);
  target.addEventListener('blur', blur);
  return () => {
    clear();
    target.removeEventListener('keydown', down, true);
    target.removeEventListener('keyup', up, true);
    target.removeEventListener('blur', blur);
  };
}
