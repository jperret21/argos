/**
 * Transient layers (menus, popovers, list boxes, dialogs, sheets): one stack
 * shared by the whole page, so that
 * - Escape closes the topmost layer only (and still reaches the shortcut
 *   registry, which aborts mount motion: D21);
 * - a pointer press outside closes the non-modal layers above the one that
 *   was hit (a menu opened from a popover closes alone);
 * - while a modal layer is open, the app and the layers under it are
 *   `inert` (no focus, no clicks, hidden from screen readers);
 * - one modal at a time, a confirmation may stack once over it (README 3.2).
 *
 * Plus the Svelte actions the overlay components share: `portal` (move the
 * element to <body>, out of clipping ancestors), `layer` (register in the
 * stack) and `floating` (position next to an anchor, flip and clamp).
 */

import type { Action } from 'svelte/action';
import { type Placement, placeFloating } from './position';

export type LayerKind = 'menu' | 'popover' | 'listbox' | 'dialog' | 'sheet';
export type CloseReason = 'escape' | 'outside' | 'action' | 'tab' | 'close';

export interface LayerEntry {
  id: number;
  kind: LayerKind;
  modal: boolean;
  element: HTMLElement;
  anchor: HTMLElement | null;
  close: (reason: CloseReason) => void;
}

const stack: LayerEntry[] = [];
let nextId = 1;
let installed = false;
const madeInert = new Set<HTMLElement>();
/** Keys the app binds whose browser default must not run under a layer (F5 reload, F1 help). */
let reserved: ((e: KeyboardEvent) => boolean) | null = null;

/** The shortcut registry tells which keys are the app's (ArgosApp sets it). */
export function setReservedKeys(test: ((e: KeyboardEvent) => boolean) | null): void {
  reserved = test;
}

/**
 * Which layers a pointer press closes: the non-modal ones above the highest
 * layer that contains the press (or its anchor), stopping at a modal layer.
 * `hit` is that layer's index, -1 when the press is outside every layer.
 */
export function layersToClose<T extends { modal: boolean }>(layers: readonly T[], hit: number): T[] {
  const out: T[] = [];
  for (let i = layers.length - 1; i > hit; i--) {
    if (layers[i].modal) break;
    out.push(layers[i]);
  }
  return out;
}

/** Index of the topmost modal layer, or -1. */
export function topModalIndex<T extends { modal: boolean }>(layers: readonly T[]): number {
  for (let i = layers.length - 1; i >= 0; i--) if (layers[i].modal) return i;
  return -1;
}

function onKeyDown(e: KeyboardEvent): void {
  if (e.isComposing || !stack.length) return;
  if (e.key !== 'Escape') {
    // A layer holds the keys (no shortcut runs), but an app key (F1-F5…)
    // must not fall through to the browser: F5 would reload the page.
    if (reserved?.(e)) e.preventDefault();
    return;
  }
  // A field that holds something Escape reverts (a value not sent, a refusal)
  // takes this Escape; the next one closes the layer (README 3.4).
  if (ownsEscape(e.target)) return;
  e.preventDefault();
  stack[stack.length - 1].close('escape');
}

/**
 * True when the key's target (or an ancestor) is marked
 * `data-escape="local"`: NumberField and the other value fields set it while
 * they hold a draft or a refusal, so Escape reverts the field before it
 * closes the sheet or dialog around it. The shortcut registry still sees the
 * key (Escape aborts mount motion from any focus, D21).
 */
export function ownsEscape(target: EventTarget | null): boolean {
  const el = target as { closest?: (s: string) => unknown } | null;
  return !!el && typeof el.closest === 'function' && !!el.closest('[data-escape="local"]');
}

function onPointerDown(e: PointerEvent): void {
  if (!stack.length) return;
  const target = e.target as Node | null;
  let hit = -1;
  for (let i = stack.length - 1; i >= 0; i--) {
    const l = stack[i];
    if (target && (l.element.contains(target) || l.anchor?.contains(target))) {
      hit = i;
      break;
    }
  }
  for (const l of layersToClose(stack, hit)) l.close('outside');
}

function install(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  // Capture: the layer closes before any shortcut handler sees the key.
  window.addEventListener('keydown', onKeyDown, true);
  document.addEventListener('pointerdown', onPointerDown, true);
}

function appRoot(): HTMLElement | null {
  return globalThis.document?.getElementById('app') ?? null;
}

function updateInert(): void {
  const top = topModalIndex(stack);
  const want = new Set<HTMLElement>();
  if (top >= 0) {
    const root = appRoot();
    if (root) want.add(root);
    for (let i = 0; i < top; i++) want.add(stack[i].element);
  }
  for (const el of madeInert) {
    if (!want.has(el)) {
      el.inert = false;
      madeInert.delete(el);
    }
  }
  for (const el of want) {
    if (!el.inert) {
      el.inert = true;
      madeInert.add(el);
    }
  }
}

export function openLayers(): readonly LayerEntry[] {
  return stack;
}

export function isTopLayer(element: HTMLElement): boolean {
  return stack.length > 0 && stack[stack.length - 1].element === element;
}

export interface LayerOptions {
  kind: LayerKind;
  modal?: boolean;
  anchor?: HTMLElement | null;
  onclose: (reason: CloseReason) => void;
}

/** Register the element as an open layer for as long as it is mounted. */
export const layer: Action<HTMLElement, LayerOptions> = (node, opts) => {
  install();
  const entry: LayerEntry = {
    id: nextId++,
    kind: opts.kind,
    modal: opts.modal ?? (opts.kind === 'dialog' || opts.kind === 'sheet'),
    element: node,
    anchor: opts.anchor ?? null,
    close: opts.onclose,
  };
  stack.push(entry);
  updateInert();
  return {
    update(next: LayerOptions) {
      entry.anchor = next.anchor ?? null;
      entry.close = next.onclose;
    },
    destroy() {
      const i = stack.indexOf(entry);
      if (i >= 0) stack.splice(i, 1);
      updateInert();
    },
  };
};

/**
 * Move the element to <body> (or `target`), so no ancestor's overflow or
 * stacking context clips it. Use it on the only element of an {#if} block:
 * Svelte then removes exactly that element when the block closes.
 */
export const portal: Action<HTMLElement, HTMLElement | undefined> = (node, target) => {
  (target ?? document.body).appendChild(node);
  return {
    destroy() {
      node.remove();
    },
  };
};

export interface FloatingOptions {
  anchor?: HTMLElement | null;
  /** A point instead of an element (context menus). */
  point?: { x: number; y: number } | null;
  placement?: Placement;
  gap?: number;
  /** At least as wide as the anchor (select lists). */
  matchWidth?: boolean;
}

/** Keep a fixed-position layer next to its anchor while it is open. */
export const floating: Action<HTMLElement, FloatingOptions> = (node, initial) => {
  let opts = initial;
  node.style.position = 'fixed';
  node.style.left = '0';
  node.style.top = '0';

  const place = () => {
    const anchorEl = opts.anchor;
    let box: { left: number; top: number; width: number; height: number };
    if (anchorEl) {
      const r = anchorEl.getBoundingClientRect();
      box = { left: r.left, top: r.top, width: r.width, height: r.height };
      if (opts.matchWidth) node.style.minWidth = `${Math.round(r.width)}px`;
    } else if (opts.point) {
      box = { left: opts.point.x, top: opts.point.y, width: 0, height: 0 };
    } else {
      return;
    }
    const size = node.getBoundingClientRect();
    const p = placeFloating({
      anchor: box,
      floating: { width: size.width, height: size.height },
      viewport: { width: window.innerWidth, height: window.innerHeight },
      placement: opts.placement,
      gap: opts.gap,
    });
    node.style.transform = `translate(${p.x}px, ${p.y}px)`;
    node.dataset.side = p.side;
  };

  place();
  const raf = requestAnimationFrame(place);
  const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(place) : null;
  ro?.observe(node);
  window.addEventListener('resize', place);
  window.addEventListener('scroll', place, true);

  return {
    update(next: FloatingOptions) {
      opts = next;
      place();
    },
    destroy() {
      cancelAnimationFrame(raf);
      ro?.disconnect();
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    },
  };
};
