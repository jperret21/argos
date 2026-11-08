/**
 * Toolbar built from data (Toolbar.svelte): the pure part, unit-tested.
 * Promoted from src/lab/controls/overflow.ts and types.ts (web/lab/PROPOSAL.md
 * 3.3 and 6, W3), with the two changes art direction asked for: natural
 * widths are measured once (or declared), not from a hidden inert copy of
 * every tool, and the row has ONE tab stop (roving tabindex).
 *
 * - Tools carry a priority. Infinity = never moved to the overflow menu
 *   (Capture, Live, Stop: the run-critical ones). Lower priorities leave
 *   first; among equal priorities the rightmost leaves first, so a group
 *   shrinks from its end.
 * - A group whose tools are all hidden also drops its separator.
 * - When anything is hidden, the overflow trigger's width is reserved; the
 *   trigger shows HOW MANY tools it holds, so nothing disappears silently.
 * - Then a hidden tool that still fits comes back (backfill), so a wide tool
 *   leaving does not leave a dead band beside the trigger.
 * - Hidden tools keep their order in the menu, grouped like the toolbar;
 *   toggles keep their state (check marks) and every tool its shortcut.
 */

import type { MenuEntry } from './menu';

/** One tool of a toolbar: a button, a toggle, a split button or a readout. */
export interface ToolDef {
  id: string;
  /** Tools of one group stay together; groups are separated by a rule. */
  group: string;
  kind: 'button' | 'toggle' | 'split' | 'readout';
  icon: string;
  label: string;
  /** Shortcut spec from the registry ("E", "Shift+A"). */
  shortcut?: string;
  /** Higher stays longer; Infinity is never moved to the overflow menu. */
  priority: number;
  /** Declared natural width in px (skips the measure). */
  width?: number;
  pressed?: boolean;
  layoutToggle?: boolean;
  showLabel?: boolean;
  /** Visible text when shorter than the accessible label ("Stop AF" for "Stop autofocus"). */
  buttonText?: string;
  variant?: 'ghost' | 'secondary' | 'primary' | 'danger';
  glyphTone?: 'danger';
  disabledReason?: string | null;
  busy?: boolean;
  progress?: number | null;
  progressText?: string;
  error?: string | null;
  /** Readout text ("48 %") or the split button's options in use ("2.0 s"). */
  text?: string;
  /**
   * The widest `text` this tool can show ("Flat · 120.0 s"): its width is
   * reserved, so the toolbar's layout never depends on the value in use.
   */
  textMin?: string;
  /** Split button options. */
  items?: readonly MenuEntry[];
  /** A split button whose main part stops the action while it runs (Stop AF). */
  stoppable?: boolean;
  /** Why a split button's options cannot change now. */
  optionsReason?: string | null;
  /** Placed after the flexible space, at the toolbar's right end. */
  end?: boolean;
}

export interface FitItem {
  id: string;
  group: string;
  width: number;
  priority: number;
}

export interface FitOptions {
  available: number;
  /** Space between two tools of a group. */
  gap: number;
  /** Separator between groups, including its margins. */
  separator: number;
  /** The overflow trigger, including its margin. */
  overflow: number;
}

export interface FitResult {
  visible: Set<string>;
  hidden: string[];
  width: number;
}

/** Width of a row showing `shown`, plus the overflow trigger when `withOverflow`. */
export function rowWidth(items: readonly FitItem[], shown: Set<string>, o: FitOptions, withOverflow: boolean): number {
  let w = 0;
  let groups = 0;
  let prevGroup: string | null = null;
  let inGroup = 0;
  for (const it of items) {
    if (!shown.has(it.id)) continue;
    if (it.group !== prevGroup) {
      if (prevGroup !== null) groups++;
      prevGroup = it.group;
      inGroup = 0;
    }
    w += it.width + (inGroup > 0 ? o.gap : 0);
    inGroup++;
  }
  w += groups * o.separator;
  if (withOverflow) w += o.overflow;
  return w;
}

export function fitToolbar(items: readonly FitItem[], o: FitOptions): FitResult {
  const shown = new Set(items.map((i) => i.id));
  if (rowWidth(items, shown, o, false) <= o.available) {
    return { visible: shown, hidden: [], width: rowWidth(items, shown, o, false) };
  }
  // Leaving order: lowest priority first, rightmost first among equals.
  const order = items
    .map((it, index) => ({ it, index }))
    .filter(({ it }) => Number.isFinite(it.priority))
    .sort((a, b) => a.it.priority - b.it.priority || b.index - a.index);
  for (const { it } of order) {
    shown.delete(it.id);
    if (rowWidth(items, shown, o, true) <= o.available) break;
  }
  // Backfill: a hidden tool that fits in the room left comes back (highest
  // priority first, then leftmost), so a wide tool leaving never strands a
  // dead band while the trigger counts a small one (BRAND 11.1).
  const back = order
    .filter(({ it }) => !shown.has(it.id))
    .sort((a, b) => b.it.priority - a.it.priority || a.index - b.index);
  for (const { it } of back) {
    shown.add(it.id);
    const stillHidden = items.some((i) => !shown.has(i.id));
    if (rowWidth(items, shown, o, stillHidden) > o.available) shown.delete(it.id);
  }
  const hidden = items.filter((i) => !shown.has(i.id)).map((i) => i.id);
  return { visible: shown, hidden, width: rowWidth(items, shown, o, hidden.length > 0) };
}

/**
 * The measured width of a tool depends on what it shows: an icon-only tool
 * never changes, a labelled one or a readout changes with its text. The key
 * says when a cached width is stale.
 */
export function widthKey(t: Pick<ToolDef, 'id' | 'kind' | 'text' | 'textMin' | 'showLabel' | 'label' | 'buttonText'>): string {
  const label = t.showLabel ? (t.buttonText ?? t.label) : '';
  const text = t.textMin ?? t.text ?? '';
  const shown = t.kind === 'readout' ? text : t.kind === 'split' ? `${label}|${text}` : label;
  return `${t.id}|${t.kind}|${shown}`;
}

/** Fallback before a tool was measured: the control height for an icon, plus about 7 px per character. */
export function estimateWidth(t: ToolDef, controlPx: number): number {
  if (t.width !== undefined) return t.width;
  const label = t.showLabel ? (t.buttonText ?? t.label) : '';
  const text = t.textMin ?? t.text ?? '';
  const chars = t.kind === 'readout' ? text.length : t.kind === 'split' ? label.length + text.length : label.length;
  const base = t.kind === 'readout' ? 16 : controlPx;
  const chevron = t.kind === 'split' ? 19 : 0;
  return Math.round(base + chevron + (chars ? 8 + chars * 7 : 0));
}

/** The overflow menu: the hidden tools in toolbar order, a separator between groups. */
export function overflowItems(hidden: readonly ToolDef[]): MenuEntry[] {
  const out: MenuEntry[] = [];
  let group: string | null = null;
  for (const t of hidden) {
    if (t.group !== group) {
      if (group !== null) out.push({ kind: 'separator', id: `sep-${t.id}` });
      group = t.group;
    }
    const reason = t.disabledReason ?? null;
    if (t.kind === 'toggle') {
      out.push({ kind: 'checkbox', id: t.id, label: t.label, checked: !!t.pressed, shortcut: t.shortcut, disabledReason: reason });
    } else {
      const label = t.kind === 'readout' && t.text ? `${t.label}: ${t.text}` : t.kind === 'split' && t.text ? `${t.label} · ${t.text}` : t.label;
      out.push({ id: t.id, label, icon: t.icon, shortcut: t.shortcut, disabledReason: reason });
    }
  }
  return out;
}

/**
 * Roving focus inside a horizontal toolbar (WAI-ARIA toolbar pattern): ← →
 * move between the focusable parts (wrapping), Home / End jump. Up and Down
 * are left to the part (a split button opens its options on ↓).
 */
export function rovingTarget(key: string, index: number, count: number): number | null {
  if (count <= 0) return null;
  switch (key) {
    case 'ArrowLeft':
      return (index - 1 + count) % count;
    case 'ArrowRight':
      return (index + 1) % count;
    case 'Home':
      return 0;
    case 'End':
      return count - 1;
    default:
      return null;
  }
}
