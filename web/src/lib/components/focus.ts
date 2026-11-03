/**
 * Focus management for overlays: the Tab trap of modal dialogs and the
 * return of focus to the control that opened a layer.
 *
 * The logic is written against small interfaces (FocusTarget, FocusDoc), so
 * the trap and the restore can be tested without a browser; the DOM
 * helpers below plug real elements into them.
 */

export interface FocusTarget {
  focus(options?: FocusOptions): void;
  /** False once the element left the document. */
  isConnected?: boolean;
}

export interface FocusDoc {
  activeElement: unknown;
}

/**
 * Index to focus after Tab (or Shift+Tab) in a trapped list of `count`
 * focusables, from `current` (-1 when focus is outside the list): wraps at
 * both ends, so focus never leaves a modal dialog.
 */
export function trapStep(count: number, current: number, backwards: boolean): number {
  if (count <= 0) return -1;
  if (current < 0 || current >= count) return backwards ? count - 1 : 0;
  if (backwards) return current === 0 ? count - 1 : current - 1;
  return current === count - 1 ? 0 : current + 1;
}

export interface TrapKey {
  key: string;
  shiftKey: boolean;
  preventDefault(): void;
}

/**
 * Handle a keydown inside a focus trap. `items` are the focusables in
 * document order, `active` the focused element. When the list is empty the
 * container itself keeps focus. Returns true when the key was handled.
 */
export function handleTrapKey<T extends FocusTarget>(
  e: TrapKey,
  items: readonly T[],
  active: unknown,
  container: FocusTarget,
): boolean {
  if (e.key !== 'Tab') return false;
  e.preventDefault();
  if (!items.length) {
    container.focus();
    return true;
  }
  const next = trapStep(items.length, items.indexOf(active as T), e.shiftKey);
  items[next].focus();
  return true;
}

/**
 * Remembers what had focus when a layer opened and gives it back when the
 * layer closes, unless that element is gone (then `fallback`, if any).
 */
export class FocusReturn {
  private readonly saved: FocusTarget | null;

  constructor(doc: FocusDoc | null = globalThis.document ?? null, explicit?: FocusTarget | null) {
    const active = explicit ?? (doc?.activeElement as FocusTarget | null | undefined) ?? null;
    this.saved = active && typeof active.focus === 'function' ? active : null;
  }

  get target(): FocusTarget | null {
    return this.saved;
  }

  /** Returns the element that received focus, or null. */
  restore(fallback?: FocusTarget | null): FocusTarget | null {
    const candidates = [this.saved, fallback ?? null];
    for (const el of candidates) {
      if (!el || el.isConnected === false) continue;
      el.focus({ preventScroll: true });
      return el;
    }
    return null;
  }
}

// -- DOM helpers ---------------------------------------------------------------

export const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(',');

/** Visible, enabled, tabbable elements inside `root`, in document order. */
export function focusableIn(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)].filter(
    (el) => el.tabIndex >= 0 && !el.closest('[inert]') && el.getClientRects().length > 0,
  );
}

/**
 * Initial focus inside a layer: an explicit selector, then the first
 * [data-autofocus] element, then the first focusable, then the container.
 */
export function initialFocus(root: HTMLElement, selector?: string | null): HTMLElement {
  if (selector) {
    const el = root.querySelector<HTMLElement>(selector);
    if (el) return el;
  }
  const marked = root.querySelector<HTMLElement>('[data-autofocus]');
  if (marked) return marked;
  return focusableIn(root)[0] ?? root;
}

/** The element itself when it can take focus, else its first focusable descendant (a wrapper around a button). */
export function focusTargetOf(el: HTMLElement | null | undefined): HTMLElement | null {
  if (!el) return null;
  if (el.matches(FOCUSABLE_SELECTOR) && el.tabIndex >= 0) return el;
  return el.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
}

/**
 * Keep the keys typed inside a layer away from the window's listeners (the
 * shortcut registry: "E" typed in a field is not an exposure), WITHOUT
 * stopping them at the layer itself. Svelte 5 delegates `onkeydown` to the
 * document, so a `stopPropagation()` on the layer element would silently
 * disable every keydown handler inside it (Enter in a NumberField, the
 * FilePicker list). This listener sits on the document and runs after
 * Svelte's (registered at mount, before any layer opens: same node, so the
 * delegated handlers still run), then stops the event before the window.
 * Escape always travels on (it aborts mount motion, D21). Returns the detach.
 */
export function keepKeysInside(node: HTMLElement, doc: Document = document): () => void {
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'Escape' && e.target instanceof Node && node.contains(e.target)) e.stopPropagation();
  };
  doc.addEventListener('keydown', onKey);
  return () => doc.removeEventListener('keydown', onKey);
}
