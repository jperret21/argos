/**
 * Table logic (web/spec/README.md section 3.5): column model, sorting, and
 * the TSV the table copies. Pure, tested without a browser.
 *
 * Sorting: stable; numbers compare numerically, text with a natural order
 * ("Comp 2" before "Comp 10", case-insensitive); missing values (null,
 * undefined, NaN, "") always go last, whatever the direction, so a sort never
 * buries the measured rows under empty ones. A header click cycles
 * ascending -> descending -> the table's own order (catalogue order).
 */

export type SortDir = 'asc' | 'desc';

export interface SortState {
  column: string;
  dir: SortDir;
}

export type CellValue = string | number | boolean | null | undefined;

export interface Column<T> {
  id: string;
  label: string;
  /** Value used to sort and to copy (and to display when `format` is absent). */
  value?: (row: T) => CellValue;
  /** Text shown in the cell (and copied). */
  format?: (row: T) => string;
  /** Right-aligned, mono, tabular figures (BRAND 5). Default: false. */
  numeric?: boolean;
  /** Default true when `value` is given. */
  sortable?: boolean;
  /** CSS width ("12ch", "96px", "1fr" is not allowed in a table: use auto). */
  width?: string;
  /** Header tooltip: the full name or the unit. */
  title?: string;
  /** Header read by screen readers only (an actions column). */
  hideLabel?: boolean;
  /** Let long text wrap (an error reason) instead of staying on one line. */
  wrap?: boolean;
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

function missing(v: CellValue): boolean {
  return v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v));
}

export function compareValues(a: CellValue, b: CellValue): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b);
  return collator.compare(String(a), String(b));
}

export function sortRows<T>(rows: readonly T[], value: (row: T) => CellValue, dir: SortDir): T[] {
  const indexed = rows.map((row, i) => ({ row, i, v: value(row) }));
  const sign = dir === 'asc' ? 1 : -1;
  indexed.sort((x, y) => {
    const mx = missing(x.v);
    const my = missing(y.v);
    if (mx || my) return mx === my ? x.i - y.i : mx ? 1 : -1;
    const c = compareValues(x.v, y.v);
    return c !== 0 ? sign * c : x.i - y.i;
  });
  return indexed.map((e) => e.row);
}

/** The value a column sorts and copies by. */
export function cellValue<T>(col: Column<T>, row: T): CellValue {
  if (col.value) return col.value(row);
  if (col.format) return col.format(row);
  return (row as Record<string, CellValue>)[col.id];
}

export function cellText<T>(col: Column<T>, row: T): string {
  if (col.format) return col.format(row);
  const v = cellValue(col, row);
  return missing(v) ? '—' : String(v);
}

export function isSortable<T>(col: Column<T>): boolean {
  return col.sortable ?? true;
}

/** Apply a sort state; unknown or unsortable columns leave the order as given. */
export function applySort<T>(rows: readonly T[], columns: readonly Column<T>[], sort: SortState | null): T[] {
  if (!sort) return [...rows];
  const col = columns.find((c) => c.id === sort.column);
  if (!col || !isSortable(col)) return [...rows];
  return sortRows(rows, (r) => cellValue(col, r), sort.dir);
}

/** Next sort after a click on `column`: asc -> desc -> none (the table's own order). */
export function nextSort(current: SortState | null, column: string): SortState | null {
  if (!current || current.column !== column) return { column, dir: 'asc' };
  if (current.dir === 'asc') return { column, dir: 'desc' };
  return null;
}

export function ariaSort(sort: SortState | null, column: string): 'ascending' | 'descending' | 'none' {
  if (!sort || sort.column !== column) return 'none';
  return sort.dir === 'asc' ? 'ascending' : 'descending';
}

export function isSortState(v: unknown): v is SortState | null {
  if (v === null) return true;
  if (typeof v !== 'object') return false;
  const o = v as Record<string, unknown>;
  return typeof o.column === 'string' && (o.dir === 'asc' || o.dir === 'desc');
}

function tsvCell(text: string): string {
  return text.replace(/[\t\r\n]+/g, ' ');
}

/** Header line + one line per row, tab-separated (README 3.5 "Copy as TSV"). */
export function toTsv<T>(columns: readonly Column<T>[], rows: readonly T[]): string {
  const cols = columns.filter((c) => !c.hideLabel);
  const lines = [cols.map((c) => tsvCell(c.label)).join('\t')];
  for (const row of rows) lines.push(cols.map((c) => tsvCell(cellText(c, row))).join('\t'));
  return lines.join('\n') + '\n';
}
