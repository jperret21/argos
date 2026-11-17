/**
 * Tooltip, refreshed (proposal over lib/components/tooltip.ts, same timing):
 * label + key caps on the first line, then at most one muted line that says
 * WHY (disabled reason, failure) or HOW (a gesture: "Hold to park").
 *
 * - Hover: shown after 500 ms; once one has been seen, neighbours show at
 *   once for 300 ms (scan a row of icon tools without waiting).
 * - Keyboard focus: at once.
 * - NEW: a press on an unavailable control (aria-disabled) shows its reason
 *   at once. Waiting 500 ms on a control that "does nothing" is the moment
 *   the observer most needs the reason; the click is otherwise swallowed.
 * - One shared element on <body> (never clipped by a scrolling rail), text
 *   set with textContent only, aria-hidden: the control carries the same
 *   information (aria-label, aria-keyshortcuts, aria-describedby).
 *
 * Usage: <button use:tip={{ text: 'Slew', reason: 'Unpark the mount first' }}>
 */

import type { Action } from 'svelte/action';
import { formatShortcut } from '../../lib/app/shortcuts';

export type TipPlacement = 'top' | 'bottom' | 'left' | 'right';

export interface TipOptions {
  text: string;
  /** One spec or several ("Mod+K", ["ArrowUp", "ArrowDown"]). */
  shortcut?: string | readonly string[];
  /** Why it is unavailable (hollow ring) ... */
  reason?: string | null;
  /** ... or what failed last time (danger dot). */
  error?: string | null;
  /** How to use it, when it is not a plain click. */
  hint?: string | null;
  placement?: TipPlacement;
  disabled?: boolean;
}

const HOVER_DELAY_MS = 500;
const WARM_MS = 300;
const GAP = 6;
const MARGIN = 8;

let el: HTMLDivElement | null = null;
let owner: HTMLElement | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
let hiddenAt = -Infinity;

function tipEl(): HTMLDivElement {
  if (el && el.isConnected) return el;
  el = document.createElement('div');
  el.className = 'ctl-tip floating';
  el.setAttribute('aria-hidden', 'true');
  document.body.appendChild(el);
  return el;
}

function cancel(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
}

export function hideTip(from?: HTMLElement): void {
  if (from && owner !== from) return;
  cancel();
  if (owner) hiddenAt = performance.now();
  owner = null;
  if (el) el.dataset.open = 'false';
}

function fill(tip: HTMLDivElement, o: TipOptions): void {
  tip.replaceChildren();
  const row = document.createElement('span');
  row.className = 'row';
  const label = document.createElement('span');
  label.textContent = o.text;
  row.appendChild(label);
  const keys = o.shortcut === undefined ? [] : typeof o.shortcut === 'string' ? [o.shortcut] : o.shortcut;
  if (keys.length && !o.reason) {
    const wrap = document.createElement('span');
    wrap.className = 'keys';
    for (const k of keys) {
      const kbd = document.createElement('kbd');
      kbd.className = 'cap';
      kbd.textContent = formatShortcut(k);
      wrap.appendChild(kbd);
    }
    row.appendChild(wrap);
  }
  tip.appendChild(row);
  const second = o.error ?? o.reason ?? o.hint;
  if (second) {
    const line = document.createElement('span');
    line.className = o.error ? 'reason error' : o.reason ? 'reason' : 'reason hint';
    line.textContent = second;
    tip.appendChild(line);
  }
}

function place(node: HTMLElement, tip: HTMLDivElement, placement: TipPlacement): void {
  const r = node.getBoundingClientRect();
  const t = tip.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const fits: Record<TipPlacement, boolean> = {
    bottom: r.bottom + GAP + t.height <= vh - MARGIN,
    top: r.top - GAP - t.height >= MARGIN,
    right: r.right + GAP + t.width <= vw - MARGIN,
    left: r.left - GAP - t.width >= MARGIN,
  };
  const opposite: Record<TipPlacement, TipPlacement> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };
  const side = fits[placement] || !fits[opposite[placement]] ? placement : opposite[placement];
  let x: number;
  let y: number;
  if (side === 'top' || side === 'bottom') {
    x = r.left + r.width / 2 - t.width / 2;
    y = side === 'bottom' ? r.bottom + GAP : r.top - GAP - t.height;
  } else {
    x = side === 'right' ? r.right + GAP : r.left - GAP - t.width;
    y = r.top + r.height / 2 - t.height / 2;
  }
  x = Math.min(Math.max(MARGIN, x), vw - MARGIN - t.width);
  y = Math.min(Math.max(MARGIN, y), vh - MARGIN - t.height);
  tip.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}

function show(node: HTMLElement, o: TipOptions): void {
  cancel();
  if (o.disabled || !o.text) return;
  const tip = tipEl();
  fill(tip, o);
  owner = node;
  tip.dataset.open = 'true';
  place(node, tip, o.placement ?? 'bottom');
}

function unavailable(node: HTMLElement): boolean {
  return node.getAttribute('aria-disabled') === 'true' || node.hasAttribute('disabled');
}

export const tip: Action<HTMLElement, TipOptions> = (node, initial) => {
  let o = initial;

  const onEnter = () => {
    cancel();
    const warm = owner !== null || performance.now() - hiddenAt < WARM_MS;
    if (warm) return show(node, o);
    timer = setTimeout(() => show(node, o), HOVER_DELAY_MS);
  };
  const onLeave = () => {
    if (owner === node && node.matches(':focus-visible')) return;
    cancel();
    hideTip(node);
  };
  const onFocus = () => {
    if (node.matches(':focus-visible')) show(node, o);
  };
  const onBlur = () => hideTip(node);
  const onDown = () => {
    // An unavailable control explains itself at once; any other press hides.
    if (unavailable(node) && (o.reason || o.error)) show(node, o);
    else hideTip(node);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') hideTip(node);
  };

  node.addEventListener('pointerenter', onEnter);
  node.addEventListener('pointerleave', onLeave);
  node.addEventListener('focus', onFocus);
  node.addEventListener('blur', onBlur);
  node.addEventListener('pointerdown', onDown);
  node.addEventListener('keydown', onKey);

  return {
    update(next: TipOptions) {
      o = next;
      if (owner === node) {
        if (o.disabled) hideTip(node);
        else show(node, o);
      }
    },
    destroy() {
      node.removeEventListener('pointerenter', onEnter);
      node.removeEventListener('pointerleave', onLeave);
      node.removeEventListener('focus', onFocus);
      node.removeEventListener('blur', onBlur);
      node.removeEventListener('pointerdown', onDown);
      node.removeEventListener('keydown', onKey);
      if (owner === node) hideTip(node);
      cancel();
    },
  };
};
