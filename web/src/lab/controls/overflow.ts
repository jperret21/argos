/**
 * Toolbar overflow (pure, unit-tested): which tools stay in the row at a
 * given width, which go to the overflow menu.
 *
 * - Tools carry a priority. Infinity = never hidden (Capture, Live, Stop:
 *   the run-critical ones). Lower priorities leave first; among equal
 *   priorities the rightmost leaves first, so a group shrinks from its end.
 * - A group whose tools are all hidden also drops its separator.
 * - When anything is hidden, the overflow button's width is reserved.
 * - Hidden tools keep their order in the menu (grouped like the toolbar).
 */

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
  const hidden = items.filter((i) => !shown.has(i.id)).map((i) => i.id);
  return { visible: shown, hidden, width: rowWidth(items, shown, o, hidden.length > 0) };
}
