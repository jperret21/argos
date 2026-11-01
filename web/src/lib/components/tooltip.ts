/**
 * Tooltips (BRAND.md section 7): label + shortcut, shown after ~500 ms of
 * hover and immediately on keyboard focus. Once one has been shown, moving
 * to a neighbour within WARM_MS shows the next one at once, so a row of
 * icon-only tools can be scanned without waiting at every button.
 *
 * One shared element is positioned in the viewport (position: fixed on
 * <body>), so a tooltip is never clipped by a scrolling card rail or a toolbar
 * with overflow. It is aria-hidden: the control already carries the same
 * information as aria-label / aria-keyshortcuts, and a tooltip never holds
 * information found nowhere else. Text goes in with textContent only.
 *
 * Usage: <button use:tooltip={{ text: 'Zoom in', shortcut: '+' }}>
 */

import type { Action } from 'svelte/action';
import { formatShortcut } from '../app/shortcuts';

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right';

export interface TooltipOptions {
  text: string;
  /** Shortcut spec ("E", "Shift+A", "Escape"); shown as a key cap. */
  shortcut?: string;
  placement?: TooltipPlacement;
  /** Turn the tooltip off without removing the action. */
  disabled?: boolean;
}

export const HOVER_DELAY_MS = 500;
/** After a tooltip hides, the next hover within this window shows at once. */
export const WARM_MS = 300;
const GAP = 6;
const MARGIN = 8;

let tipEl: HTMLDivElement | null = null;
let owner: HTMLElement | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
/** Element whose hover delay is running. */
let pending: HTMLElement | null = null;
/** performance.now() when the last tooltip hid (-Infinity: none yet). */
let hiddenAt = -Infinity;

function element(): HTMLDivElement {
  if (tipEl && tipEl.isConnected) return tipEl;
  tipEl = document.createElement('div');
  tipEl.className = 'argos-tip';
  tipEl.setAttribute('aria-hidden', 'true');
  document.body.appendChild(tipEl);
  return tipEl;
}

function cancelTimer(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  pending = null;
}

export function hideTooltip(from?: HTMLElement): void {
  if (from && owner !== from) return;
  cancelTimer();
  if (owner) hiddenAt = performance.now();
  owner = null;
  if (tipEl) tipEl.dataset.open = 'false';
}

/** Hover delay for the next tooltip: none while the previous one was just seen. */
export function hoverDelay(now: number, lastHidden: number, open: boolean): number {
  return open || now - lastHidden < WARM_MS ? 0 : HOVER_DELAY_MS;
}

function place(node: HTMLElement, tip: HTMLDivElement, placement: TooltipPlacement): void {
  const r = node.getBoundingClientRect();
  const t = tip.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const fits = {
    bottom: r.bottom + GAP + t.height <= vh - MARGIN,
    top: r.top - GAP - t.height >= MARGIN,
    right: r.right + GAP + t.width <= vw - MARGIN,
    left: r.left - GAP - t.width >= MARGIN,
  };
  const opposite: Record<TooltipPlacement, TooltipPlacement> = {
    top: 'bottom',
    bottom: 'top',
    left: 'right',
    right: 'left',
  };
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
  tip.dataset.side = side;
}

function show(node: HTMLElement, opts: TooltipOptions): void {
  cancelTimer();
  if (opts.disabled || !opts.text) return;
  const tip = element();
  tip.replaceChildren();
  const label = document.createElement('span');
  label.textContent = opts.text;
  tip.appendChild(label);
  if (opts.shortcut) {
    const kbd = document.createElement('kbd');
    kbd.textContent = formatShortcut(opts.shortcut);
    tip.appendChild(kbd);
  }
  owner = node;
  tip.dataset.open = 'true';
  place(node, tip, opts.placement ?? 'bottom');
}

export const tooltip: Action<HTMLElement, TooltipOptions> = (node, initial) => {
  let opts = initial;

  const onEnter = () => {
    const delay = hoverDelay(performance.now(), hiddenAt, owner !== null);
    cancelTimer();
    if (delay === 0) return show(node, opts);
    pending = node;
    timer = setTimeout(() => show(node, opts), delay);
  };
  const onLeave = () => {
    if (owner === node && node.matches(':focus-visible')) return; // keyboard user still there
    cancelTimer();
    hideTooltip(node);
  };
  const onFocus = () => {
    if (node.matches(':focus-visible')) show(node, opts);
  };
  const onBlur = () => hideTooltip(node);
  const onDown = () => hideTooltip(node);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') hideTooltip(node);
  };

  node.addEventListener('pointerenter', onEnter);
  node.addEventListener('pointerleave', onLeave);
  node.addEventListener('focus', onFocus);
  node.addEventListener('blur', onBlur);
  node.addEventListener('pointerdown', onDown);
  node.addEventListener('keydown', onKey);

  return {
    update(next: TooltipOptions) {
      opts = next;
      if (owner === node) {
        if (opts.disabled) hideTooltip(node);
        else show(node, opts); // label changed while visible (e.g. a toggle)
      }
    },
    destroy() {
      node.removeEventListener('pointerenter', onEnter);
      node.removeEventListener('pointerleave', onLeave);
      node.removeEventListener('focus', onFocus);
      node.removeEventListener('blur', onBlur);
      node.removeEventListener('pointerdown', onDown);
      node.removeEventListener('keydown', onKey);
      if (owner === node) hideTooltip(node);
      else if (pending === node) cancelTimer();
    },
  };
};
