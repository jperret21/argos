/**
 * Tooltips, v2 (BRAND.md section 7; web/lab/PROPOSAL.md 3.3, promoted from
 * src/lab/controls/tip.ts): the label and its key caps on the first line,
 * then at most one muted second line that says WHY (the reason a control is
 * unavailable, hollow ring; what failed last time, danger dot) or HOW (a
 * gesture: "Hold to park").
 *
 * - Hover: shown after ~500 ms; once one has been seen, moving to a
 *   neighbour within WARM_MS shows the next one at once, so a row of
 *   icon-only tools can be scanned without waiting at every button.
 * - Keyboard focus: at once.
 * - A press on an unavailable control (aria-disabled) shows its reason at
 *   once: the moment a control "does nothing" is when the observer most
 *   needs the reason, and the click itself is swallowed.
 *
 * One shared element is positioned in the viewport (position: fixed on
 * <body>), so a tooltip is never clipped by a scrolling card rail or a toolbar
 * with overflow. It is aria-hidden: the control already carries the same
 * information (aria-label, aria-keyshortcuts, aria-describedby), and a
 * tooltip never holds information found nowhere else. Text goes in with
 * textContent only.
 *
 * Usage: <button use:tooltip={{ text: 'Slew', reason: 'Unpark the mount first' }}>
 */

import type { Action } from 'svelte/action';
import { formatShortcut } from '../app/shortcuts';
import './tooltip.css';

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right';

export interface TooltipOptions {
  text: string;
  /** Shortcut spec(s) ("E", "Shift+A", ["ArrowUp", "ArrowDown"]); shown as key caps. */
  shortcut?: string | readonly string[];
  /** Why the control is unavailable now (second line, hollow ring; hides the key caps). */
  reason?: string | null;
  /** What failed on the last attempt (second line, danger dot). */
  error?: string | null;
  /** How to use it when it is not a plain click (second line, unmarked). */
  hint?: string | null;
  placement?: TooltipPlacement;
  /** Turn the tooltip off without removing the action. */
  disabled?: boolean;
}

export type TipSecondKind = 'reason' | 'error' | 'hint';

export interface TipContent {
  text: string;
  /** Key specs to draw as caps (none while a reason is shown: the control cannot act). */
  keys: string[];
  second: { kind: TipSecondKind; text: string } | null;
}

export const HOVER_DELAY_MS = 500;
/** After a tooltip hides, the next hover within this window shows at once. */
export const WARM_MS = 300;
const GAP = 6;
const MARGIN = 8;

/** What a tooltip shows, from its options (pure, unit-tested). Error wins over reason over hint. */
export function tipContent(o: TooltipOptions): TipContent {
  const reason = o.reason || null;
  const raw = o.shortcut === undefined ? [] : typeof o.shortcut === 'string' ? [o.shortcut] : [...o.shortcut];
  const keys = reason ? [] : raw.filter(Boolean);
  let second: TipContent['second'] = null;
  if (o.error) second = { kind: 'error', text: o.error };
  else if (reason) second = { kind: 'reason', text: reason };
  else if (o.hint) second = { kind: 'hint', text: o.hint };
  return { text: o.text, keys, second };
}

/** Does a press show the tooltip at once? Only on an unavailable control that has something to say. */
export function explainsOnPress(unavailable: boolean, o: TooltipOptions): boolean {
  return unavailable && !o.disabled && !!o.text && !!(o.reason || o.error);
}

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
  tipEl.dataset.v2 = '';
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

function fill(tip: HTMLDivElement, c: TipContent): void {
  tip.replaceChildren();
  const row = document.createElement('span');
  row.className = 'tip-row';
  const label = document.createElement('span');
  label.textContent = c.text;
  row.appendChild(label);
  if (c.keys.length) {
    const wrap = document.createElement('span');
    wrap.className = 'tip-keys';
    for (const k of c.keys) {
      const kbd = document.createElement('kbd');
      kbd.textContent = formatShortcut(k);
      wrap.appendChild(kbd);
    }
    row.appendChild(wrap);
  }
  tip.appendChild(row);
  if (c.second) {
    const line = document.createElement('span');
    line.className = `tip-second ${c.second.kind}`;
    line.textContent = c.second.text;
    tip.appendChild(line);
  }
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
  fill(tip, tipContent(opts));
  owner = node;
  tip.dataset.open = 'true';
  place(node, tip, opts.placement ?? 'bottom');
}

function unavailable(node: HTMLElement): boolean {
  return node.getAttribute('aria-disabled') === 'true' || node.hasAttribute('disabled');
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
  const onDown = () => {
    // An unavailable control explains itself at once; any other press hides.
    if (explainsOnPress(unavailable(node), opts)) show(node, opts);
    else hideTooltip(node);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') hideTooltip(node);
    // Enter / Space on an unavailable control: the same explanation as a press.
    else if ((e.key === 'Enter' || e.key === ' ') && explainsOnPress(unavailable(node), opts)) show(node, opts);
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
