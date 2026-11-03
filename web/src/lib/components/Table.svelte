<!--
  Read-only data table (README 3.5): 24 px rows (compact) or 28 px, sticky
  header, numbers right-aligned in Plex Mono with tabular figures, text left.

  - Sorting: click a sortable header (or Enter / Space on it): ascending,
    descending, then the table's own order. aria-sort carries the state;
    the `sort` glyph is drawn mirrored for descending. Remembered per viewer
    under `persist` (argos.table.<persist>).
  - Selection: one row; click, ↑ ↓, Home / End move it; Enter (or a double
    click) activates the row's default action; ⌘/Ctrl+C copies the selected
    row, or the whole table when none is selected, as TSV (header included).
    A click on a control inside a row (a row action) never selects the row.
    `selectable={false}`: a table whose rows have no default action (the
    Devices table): no selection and no brass edge; ↑ ↓ still move the
    keyboard focus between rows.
  - A row-level problem (danger edge) is never covered: when the row is
    also selected, the danger edge stays outermost.
  - Empty: one row in --text-muted saying what will appear and how.
    Loading: skeleton rows, aria-busy.
  - `cell` renders custom cells (state badges, row actions); a control in a
    cell keeps its own keys (the row keys only act on the row itself).
-->
<script lang="ts" generics="T">
  import { type Snippet, untrack } from 'svelte';
  import { loadPref, savePref } from '../app/prefs';
  import Icon, { hasIcon } from './Icon.svelte';
  import {
    applySort,
    ariaSort,
    cellText,
    type Column,
    isSortable,
    isSortState,
    nextSort,
    type SortState,
    toTsv,
  } from './table';
  import { tooltip } from './tooltip';

  interface Props {
    /** Accessible name (caption read by screen readers). */
    label: string;
    columns: readonly Column<T>[];
    rows: readonly T[];
    rowKey: (row: T) => string;
    selected?: string | null;
    sort?: SortState | null;
    /** Remember the sort under argos.table.<persist>. */
    persist?: string;
    density?: 'compact' | 'comfortable';
    empty?: string;
    loading?: boolean;
    /** Rows a row-level problem marks (danger edge), by key. */
    problem?: (row: T) => boolean;
    cell?: Snippet<[T, Column<T>]>;
    onselect?: (row: T | null) => void;
    onactivate?: (row: T) => void;
    /** Height of the scrolling body; the header stays visible. */
    maxHeight?: string;
    /** Called with the TSV after a copy (e.g. a "Copied" toast). */
    oncopy?: (tsv: string, rows: number) => void;
    /** Rows can be selected (default). False: focus moves, nothing is selected. */
    selectable?: boolean;
  }

  let {
    label,
    columns,
    rows,
    rowKey,
    selected = $bindable(null),
    sort = $bindable(null),
    persist,
    density = 'compact',
    empty = 'Nothing to show.',
    loading = false,
    problem,
    cell,
    onselect,
    onactivate,
    maxHeight,
    oncopy,
    selectable = true,
  }: Props = $props();

  const uid = `tbl-${Math.random().toString(36).slice(2, 9)}`;
  const sortGlyph = hasIcon('sort');

  untrack(() => {
    if (persist) sort = loadPref(`argos.table.${persist}`, isSortState, sort);
  });

  const shown = $derived(applySort(rows, columns, sort));
  /** Row the keyboard moved to in a table without selection. */
  let cursor: string | null = $state(null);
  /** The row that holds the tab stop: the selected one (or the keyboard's), else the first. */
  const focusKey = $derived.by(() => {
    const held = selectable ? selected : cursor;
    if (held !== null && shown.some((r) => rowKey(r) === held)) return held;
    return shown.length ? rowKey(shown[0]) : null;
  });

  let body: HTMLTableSectionElement | undefined = $state();

  function setSort(column: string): void {
    sort = nextSort(sort, column);
    if (persist) savePref(`argos.table.${persist}`, sort);
  }

  function select(row: T | null, focus = false): void {
    const key = row ? rowKey(row) : null;
    if (!selectable) {
      cursor = key;
    } else if (key !== selected) {
      selected = key;
      onselect?.(row);
    }
    if (focus && key !== null) {
      queueMicrotask(() => body?.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`)?.focus());
    }
  }

  /** A click on a row selects it, unless it was meant for a control in the row. */
  function onRowClick(e: MouseEvent, row: T): void {
    const target = e.target as Element | null;
    if (target?.closest?.('button, a, input, select, textarea, label, [role="button"]')) return;
    if (selectable) select(row);
  }

  async function copy(): Promise<void> {
    const sel = !selectable || selected === null ? null : shown.find((r) => rowKey(r) === selected);
    const subset = sel ? [sel] : shown;
    const tsv = toTsv(columns, subset);
    try {
      await navigator.clipboard.writeText(tsv);
      oncopy?.(tsv, subset.length);
    } catch {
      /* clipboard refused (permissions): nothing copied, nothing claimed */
    }
  }

  function onRowKey(e: KeyboardEvent, row: T): void {
    if (e.target !== e.currentTarget) return; // a control inside the row keeps its keys
    const i = shown.indexOf(row);
    let next: number | null = null;
    switch (e.key) {
      case 'ArrowDown':
        next = Math.min(shown.length - 1, i + 1);
        break;
      case 'ArrowUp':
        next = Math.max(0, i - 1);
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = shown.length - 1;
        break;
      case 'PageDown':
        next = Math.min(shown.length - 1, i + 10);
        break;
      case 'PageUp':
        next = Math.max(0, i - 10);
        break;
      case 'Enter':
        e.preventDefault();
        e.stopPropagation();
        select(row);
        onactivate?.(row);
        return;
      case ' ':
        e.preventDefault();
        e.stopPropagation();
        if (selectable) select(row);
        return;
      default:
        if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 'c') {
          if (window.getSelection()?.toString()) return; // the observer selected text: native copy
          e.preventDefault();
          e.stopPropagation();
          void copy();
        }
        return;
    }
    e.preventDefault();
    e.stopPropagation();
    if (next !== null && shown[next]) select(shown[next], true);
  }
</script>

<div class="table-wrap" style:max-height={maxHeight} aria-busy={loading || undefined}>
  <table class="table {density}" role="grid" aria-label={label} aria-readonly="true" aria-rowcount={shown.length + 1}>
    <thead>
      <tr>
        {#each columns as col (col.id)}
          {@const sortable = isSortable(col)}
          {@const state = ariaSort(sort, col.id)}
          <th
            scope="col"
            class:numeric={col.numeric}
            style:width={col.width}
            aria-sort={sortable ? state : undefined}
          >
            {#if col.hideLabel}
              <span class="visually-hidden">{col.label}</span>
            {:else if sortable}
              <button
                type="button"
                class="sort"
                class:sorted={state !== 'none'}
                onclick={() => setSort(col.id)}
                use:tooltip={{ text: col.title ?? `Sort by ${col.label.toLowerCase()}`, placement: 'top' }}
              >
                <span class="th-label">{col.label}</span>
                <span class="sort-mark" class:desc={state === 'descending'} class:none={state === 'none'} aria-hidden="true">
                  {#if sortGlyph}<Icon name="sort" size={12} />{:else}<span class="caret"></span>{/if}
                </span>
              </button>
            {:else}
              <span class="th-label plain" use:tooltip={{ text: col.title ?? '', placement: 'top', disabled: !col.title }}>
                {col.label}
              </span>
            {/if}
          </th>
        {/each}
      </tr>
    </thead>
    <tbody bind:this={body}>
      {#if loading && !shown.length}
        {#each [0, 1, 2] as i (i)}
          <tr class="skeleton" aria-hidden="true">
            {#each columns as col (col.id)}<td><span class="bar"></span></td>{/each}
          </tr>
        {/each}
      {:else if !shown.length}
        <tr class="empty">
          <td colspan={columns.length}>{empty}</td>
        </tr>
      {:else}
        {#each shown as row (rowKey(row))}
          {@const key = rowKey(row)}
          <tr
            id="{uid}-{key}"
            data-key={key}
            class:selected={selectable && key === selected}
            class:problem={problem?.(row)}
            aria-selected={selectable ? key === selected : undefined}
            tabindex={key === focusKey ? 0 : -1}
            onclick={(e) => onRowClick(e, row)}
            ondblclick={() => onactivate?.(row)}
            onkeydown={(e) => onRowKey(e, row)}
          >
            {#each columns as col (col.id)}
              <td class:numeric={col.numeric} class:wrap={col.wrap}>
                {#if cell}{@render cell(row, col)}{:else}{cellText(col, row)}{/if}
              </td>
            {/each}
          </tr>
        {/each}
      {/if}
    </tbody>
  </table>
</div>

<style>
  .table-wrap {
    min-height: 0;
    overflow: auto;
  }

  /* Row height follows the density token (--row-h: 24 px Compact, 28 px
     Comfortable, Settings › Appearance); `density="comfortable"` forces 28. */
  .table {
    --t-row: var(--row-h, 24px);
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: var(--text-s);
    color: var(--fg);
  }
  .comfortable {
    --t-row: 28px;
  }

  th {
    position: sticky;
    top: 0;
    z-index: 1;
    height: var(--t-row);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    text-align: left;
    white-space: nowrap;
  }
  th.numeric {
    text-align: right;
  }

  .sort {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 20px;
    margin: 0 calc(-1 * var(--space-1));
    padding: 0 var(--space-1);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  th.numeric .sort {
    flex-direction: row-reverse;
  }
  .sort:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .sort.sorted {
    color: var(--fg);
  }

  .sort-mark {
    display: inline-flex;
    width: 12px;
    height: 12px;
    align-items: center;
    justify-content: center;
    color: var(--fg-muted);
  }
  .sort-mark.desc {
    transform: scaleY(-1);
  }
  /* No glyph in the table's own order (README 5): keep the room, show nothing. */
  .sort-mark.none {
    visibility: hidden;
  }
  .sort:hover .sort-mark.none {
    visibility: visible;
    opacity: 0.6;
  }
  /* Until the design team's `sort` icon lands: a drawn caret (ascending = up). */
  .caret {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid currentColor;
  }

  td {
    height: var(--t-row);
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border-soft);
    white-space: nowrap;
  }
  td.wrap {
    padding-top: 3px;
    padding-bottom: 3px;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  td.numeric {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    text-align: right;
  }

  tbody tr {
    cursor: default;
    outline: none;
  }
  tbody tr:not(.empty):not(.skeleton):hover {
    background: var(--hover-bg);
  }
  /* Selection: one brass mark (BRAND 3), the row fill stays neutral. */
  tr.selected {
    background: var(--toggled-bg);
  }
  tr.selected td:first-child {
    box-shadow: inset 2px 0 0 var(--accent);
  }
  tr.problem td:first-child {
    box-shadow: inset 2px 0 0 var(--danger);
  }
  /* The danger edge stays outermost: brass never covers a problem. */
  tr.selected.problem td:first-child {
    box-shadow:
      inset 2px 0 0 var(--danger),
      inset 4px 0 0 var(--accent);
  }
  tbody tr:focus-visible td {
    box-shadow: inset 0 var(--focus-ring-w) 0 var(--focus-ring), inset 0 calc(-1 * var(--focus-ring-w)) 0 var(--focus-ring);
  }
  tbody tr:focus-visible td:first-child {
    box-shadow:
      inset var(--focus-ring-w) 0 0 var(--focus-ring),
      inset 0 var(--focus-ring-w) 0 var(--focus-ring),
      inset 0 calc(-1 * var(--focus-ring-w)) 0 var(--focus-ring);
  }
  tbody tr:focus-visible td:last-child {
    box-shadow:
      inset calc(-1 * var(--focus-ring-w)) 0 0 var(--focus-ring),
      inset 0 var(--focus-ring-w) 0 var(--focus-ring),
      inset 0 calc(-1 * var(--focus-ring-w)) 0 var(--focus-ring);
  }

  .empty td {
    color: var(--text-muted);
    white-space: normal;
    padding-top: var(--space-2);
    padding-bottom: var(--space-2);
  }

  .skeleton .bar {
    display: block;
    width: 60%;
    height: 8px;
    border-radius: var(--radius-s);
    background: var(--surface);
  }
</style>
