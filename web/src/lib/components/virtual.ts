/**
 * Row windowing for fixed-height virtual tables (README 3.5: virtualised above 500 rows).
 * Promoted unchanged from src/lab/research/table/virtual.ts (web/lab/PROPOSAL.md 6, W4:
 * the variables and Gaia lists). Pure: the component feeds scrollTop and the viewport
 * height.
 */

export interface RowWindow {
  /** First rendered row (inclusive). */
  start: number;
  /** Last rendered row (exclusive). */
  end: number;
  /** translateY of the first rendered row, px. */
  offset: number;
  /** Full scroll height, px. */
  total: number;
}

export function rowWindow(scrollTop: number, viewport: number, rowH: number, count: number, overscan = 6): RowWindow {
  const total = count * rowH;
  if (count <= 0 || rowH <= 0) return { start: 0, end: 0, offset: 0, total: 0 };
  const top = Math.max(0, Math.min(scrollTop, Math.max(0, total - viewport)));
  const first = Math.floor(top / rowH);
  const visible = Math.ceil(viewport / rowH) + 1;
  const start = Math.max(0, first - overscan);
  const end = Math.min(count, first + visible + overscan);
  return { start, end, offset: start * rowH, total };
}

/** scrollTop that brings row `i` fully into view (unchanged when it already is). */
export function scrollToRow(i: number, scrollTop: number, viewport: number, rowH: number, header = 0): number {
  const top = i * rowH;
  const bottom = top + rowH;
  const visTop = scrollTop;
  const visBottom = scrollTop + viewport - header;
  if (top < visTop) return top;
  if (bottom > visBottom) return bottom - (viewport - header);
  return scrollTop;
}
