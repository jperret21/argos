/**
 * Keyboard navigation of menus and list boxes (WAI-ARIA APG patterns):
 * arrows move and wrap, Home / End jump, items that cannot take the cursor
 * (separators, group headers, and disabled options of a select) are skipped,
 * and typing letters jumps to the next item starting with them (type-ahead).
 * Pure, tested without a browser.
 */

export type Skip = (index: number) => boolean;

const never: Skip = () => false;

/** First / last index that is not skipped, or -1. */
export function edgeIndex(count: number, edge: 'first' | 'last', skip: Skip = never): number {
  if (edge === 'first') {
    for (let i = 0; i < count; i++) if (!skip(i)) return i;
  } else {
    for (let i = count - 1; i >= 0; i--) if (!skip(i)) return i;
  }
  return -1;
}

/**
 * Index after moving `delta` steps (±1) from `current`, skipping skipped
 * items; wraps around when `wrap`, else stops at the ends. From -1 (nothing
 * active), +1 goes to the first item and -1 to the last.
 */
export function moveIndex(count: number, current: number, delta: number, wrap = true, skip: Skip = never): number {
  if (count <= 0) return -1;
  if (current < 0 || current >= count) return edgeIndex(count, delta >= 0 ? 'first' : 'last', skip);
  const step = delta >= 0 ? 1 : -1;
  let i = current;
  for (let n = 0; n < count; n++) {
    i += step;
    if (i < 0 || i >= count) {
      if (!wrap) return current;
      i = (i + count) % count;
    }
    if (!skip(i)) return i;
  }
  return current;
}

/** Keys the list navigation consumes, mapped to a move. */
export function navTarget(
  key: string,
  count: number,
  current: number,
  skip: Skip = never,
  opts: { wrap?: boolean; page?: number } = {},
): number | null {
  const wrap = opts.wrap ?? true;
  switch (key) {
    case 'ArrowDown':
      return moveIndex(count, current, 1, wrap, skip);
    case 'ArrowUp':
      return moveIndex(count, current, -1, wrap, skip);
    case 'Home':
      return edgeIndex(count, 'first', skip);
    case 'End':
      return edgeIndex(count, 'last', skip);
    case 'PageDown': {
      let i = current;
      for (let n = 0; n < (opts.page ?? 10); n++) i = moveIndex(count, i, 1, false, skip);
      return i;
    }
    case 'PageUp': {
      let i = current;
      for (let n = 0; n < (opts.page ?? 10); n++) i = moveIndex(count, i, -1, false, skip);
      return i;
    }
    default:
      return null;
  }
}

/** A printable character that starts or extends a type-ahead search. */
export function isTypeaheadKey(e: { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): boolean {
  return e.key.length === 1 && e.key !== ' ' && !e.ctrlKey && !e.metaKey && !e.altKey;
}

/**
 * Type-ahead: letters typed within `timeoutMs` of each other form one
 * search string. Repeating one letter cycles through the items that start
 * with it ("s", "s" -> second item starting with S).
 */
export class Typeahead {
  private buffer = '';
  private last = -Infinity;

  constructor(
    private readonly timeoutMs = 500,
    private readonly now: () => number = () => globalThis.performance?.now() ?? Date.now(),
  ) {}

  /** Index of the item to activate, or -1 when nothing matches. */
  push(char: string, labels: readonly string[], current: number, skip: Skip = never): number {
    const t = this.now();
    if (t - this.last > this.timeoutMs) this.buffer = '';
    this.last = t;
    this.buffer += char.toLowerCase();
    const sameLetter = this.buffer.length > 1 && [...this.buffer].every((c) => c === this.buffer[0]);
    const query = sameLetter ? this.buffer[0] : this.buffer;
    const count = labels.length;
    // A new or repeated letter starts after the current item; a longer word
    // may still match the current one.
    const start = query.length === 1 ? current + 1 : Math.max(current, 0);
    for (let n = 0; n < count; n++) {
      const i = (((start + n) % count) + count) % count;
      if (!skip(i) && labels[i].trim().toLowerCase().startsWith(query)) return i;
    }
    return -1;
  }

  reset(): void {
    this.buffer = '';
    this.last = -Infinity;
  }
}
