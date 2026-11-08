<!--
  Virtual table (README 3.5; promoted from src/lab/research/table/VirtualTableDemo.svelte,
  web/lab/PROPOSAL.md 3.4 and 6, W4): the same column model, sorting, selection and look as
  Table.svelte, for lists that can hold thousands of rows (the field's Gaia stars reach
  `catalog.identification_max_objects`, up to 5 000; Frames in W7). The DOM holds only the
  rows in view plus an overscan (rowWindow), whatever the row count; rows are read from a
  plain array (pass `$state.raw` data: no deep proxy on thousands of records).

  - One tab stop (role="grid", aria-activedescendant): ↑ ↓, PageUp / PageDown, Home / End
    move the active row and scroll it into view; Enter (or a double click) activates;
    ⌘/Ctrl+C copies the active row, or every row when none is active, as TSV.
  - Sort by header (aria-sort): ascending, descending, the list's own order.
  - `onhover` reports the row under the pointer (or null), so a list can mark its star on
    the image; `highlight` marks a row from outside (the star hovered on the image).
  - Selection: one brass edge (BRAND 3), the fill stays neutral.
-->
<script lang="ts" generics="T">
  import { type Snippet, tick } from 'svelte';
  import Icon, { hasIcon } from './Icon.svelte';
  import { applySort, ariaSort, cellText, type Column, isSortable, nextSort, type SortState, toTsv } from './table';
  import { tooltip } from './tooltip';
  import { rowWindow, scrollToRow } from './virtual';

  interface Props {
    label: string;
    columns: readonly Column<T>[];
    rows: readonly T[];
    rowKey: (row: T) => string;
    selected?: string | null;
    sort?: SortState | null;
    /** A row marked from outside (hover on the image). */
    highlight?: string | null;
    /** Height of the whole table (header included); the body scrolls. */
    height?: string;
    empty?: string;
    cell?: Snippet<[T, Column<T>]>;
    onselect?: (row: T | null) => void;
    onactivate?: (row: T) => void;
    onhover?: (row: T | null) => void;
    oncopy?: (tsv: string, rows: number) => void;
    /** Rows kept rendered above and below the view. */
    overscan?: number;
  }

  let {
    label,
    columns,
    rows,
    rowKey,
    selected = $bindable(null),
    sort = $bindable(null),
    highlight = null,
    height = '100%',
    empty = 'Nothing to show.',
    cell,
    onselect,
    onactivate,
    onhover,
    oncopy,
    overscan = 8,
  }: Props = $props();

  const uid = `vt-${Math.random().toString(36).slice(2, 9)}`;
  const sortGlyph = hasIcon('sort');

  let scroller: HTMLDivElement | undefined = $state();
  let scrollTop = $state(0);
  let viewport = $state(240);
  let rowH = $state(24);
  let headH = $state(24);

  const shown = $derived(applySort(rows, columns, sort));
  const win = $derived(rowWindow(scrollTop, Math.max(0, viewport - headH), rowH, shown.length, overscan));
  const visible = $derived(shown.slice(win.start, win.end));
  const template = $derived(columns.map((c) => c.width ?? 'minmax(0, 1fr)').join(' '));

  /** Index of the active row in `shown` (the selected one, else none). */
  const active = $derived.by(() => {
    if (selected === null) return -1;
    return shown.findIndex((r) => rowKey(r) === selected);
  });

  // The row height follows the density token (--row-h): read once the grid exists, and again
  // when the density changes at runtime (Settings › Appearance sets data-density on <html>).
  $effect(() => {
    const el = scroller;
    if (!el) return;
    const read = () => {
      const v = parseFloat(getComputedStyle(el).getPropertyValue('--row-h'));
      if (Number.isFinite(v) && v > 0) rowH = v;
      const head = el.querySelector<HTMLElement>('.head');
      if (head) headH = head.offsetHeight || rowH;
    };
    read();
    const watch = new MutationObserver(read);
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-density', 'class', 'style'] });
    return () => watch.disconnect();
  });

  function setSort(column: string): void {
    sort = nextSort(sort, column);
  }

  async function moveTo(i: number): Promise<void> {
    if (!shown.length || !scroller) return;
    const j = Math.max(0, Math.min(shown.length - 1, i));
    const row = shown[j];
    const key = rowKey(row);
    if (key !== selected) {
      selected = key;
      onselect?.(row);
    }
    const next = scrollToRow(j, scroller.scrollTop, scroller.clientHeight, rowH, headH);
    if (next !== scroller.scrollTop) scroller.scrollTop = next;
    await tick();
  }

  function onKey(e: KeyboardEvent): void {
    if (e.target !== e.currentTarget) return;
    const page = Math.max(1, Math.floor((viewport - headH) / rowH) - 1);
    const i = active;
    const map: Record<string, number> = {
      ArrowDown: i + 1,
      ArrowUp: Math.max(0, i - 1),
      PageDown: i + page,
      PageUp: i - page,
      Home: 0,
      End: shown.length - 1,
    };
    if (e.key in map) {
      e.preventDefault();
      void moveTo(map[e.key]);
      return;
    }
    if (e.key === 'Enter' && i >= 0) {
      e.preventDefault();
      onactivate?.(shown[i]);
      return;
    }
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 'c') {
      if (window.getSelection()?.toString()) return;
      e.preventDefault();
      void copy();
    }
  }

  async function copy(): Promise<void> {
    const subset = active >= 0 ? [shown[active]] : shown;
    const tsv = toTsv(columns, subset);
    try {
      await navigator.clipboard.writeText(tsv);
      oncopy?.(tsv, subset.length);
    } catch {
      /* clipboard refused: nothing copied, nothing claimed */
    }
  }

  function click(row: T): void {
    const key = rowKey(row);
    if (key !== selected) {
      selected = key;
      onselect?.(row);
    }
  }
</script>

<div
  class="vt"
  bind:this={scroller}
  bind:clientHeight={viewport}
  style:height
  style:--vt-cols={template}
  role="grid"
  aria-label={label}
  aria-readonly="true"
  aria-rowcount={shown.length + 1}
  aria-colcount={columns.length}
  aria-activedescendant={active >= 0 && active >= win.start && active < win.end ? `${uid}-r${active}` : undefined}
  tabindex="0"
  onscroll={() => (scrollTop = scroller?.scrollTop ?? 0)}
  onkeydown={onKey}
  onpointerleave={() => onhover?.(null)}
>
  <div class="head" role="row" aria-rowindex="1">
    {#each columns as col (col.id)}
      {@const sortable = isSortable(col)}
      {@const state = ariaSort(sort, col.id)}
      <div class="th" class:numeric={col.numeric} role="columnheader" aria-sort={sortable ? state : undefined}>
        {#if col.hideLabel}
          <span class="visually-hidden">{col.label}</span>
        {:else if sortable}
          <button
            type="button"
            class="sort"
            class:sorted={state !== 'none'}
            tabindex="-1"
            onclick={() => setSort(col.id)}
            use:tooltip={{ text: col.title ?? `Sort by ${col.label.toLowerCase()}`, placement: 'top' }}
          >
            <span class="th-label">{col.label}</span>
            <span class="sort-mark" class:desc={state === 'descending'} class:none={state === 'none'} aria-hidden="true">
              {#if sortGlyph}<Icon name="sort" size={12} />{:else}<span class="caret"></span>{/if}
            </span>
          </button>
        {:else}
          <span class="th-label" use:tooltip={{ text: col.title ?? '', placement: 'top', disabled: !col.title }}>{col.label}</span>
        {/if}
      </div>
    {/each}
  </div>
  {#if !shown.length}
    <div class="empty" role="row"><span role="gridcell">{empty}</span></div>
  {:else}
    <div class="body" style:height="{win.total}px">
      <div class="win" style:transform="translateY({win.offset}px)">
        {#each visible as row, i (rowKey(row))}
          {@const key = rowKey(row)}
          {@const n = win.start + i}
          <!-- The grid holds the keyboard (aria-activedescendant): rows are not tab stops. -->
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div
            tabindex="-1"
            id="{uid}-r{n}"
            class="tr"
            class:selected={key === selected}
            class:hl={key === highlight}
            role="row"
            aria-rowindex={n + 2}
            aria-selected={key === selected}
            onclick={() => click(row)}
            ondblclick={() => onactivate?.(row)}
            onpointerenter={() => onhover?.(row)}
          >
            {#each columns as col (col.id)}
              <div class="td" class:numeric={col.numeric} role="gridcell">
                {#if cell}{@render cell(row, col)}{:else}{cellText(col, row)}{/if}
              </div>
            {/each}
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .vt {
    position: relative;
    min-height: 0;
    overflow: auto;
    outline: none;
    font-size: var(--text-s);
    color: var(--fg);
  }
  .vt:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: calc(-1 * var(--focus-ring-w));
  }
  .head,
  .tr {
    display: grid;
    grid-template-columns: var(--vt-cols);
    align-items: center;
  }
  .head {
    position: sticky;
    top: 0;
    z-index: 1;
    height: var(--row-h, 24px);
    border-bottom: var(--border-w) solid var(--border);
    background: var(--bg-2);
  }
  .th {
    padding: 0 var(--space-3);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    white-space: nowrap;
    overflow: hidden;
  }
  .th.numeric {
    text-align: right;
  }
  .sort {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: 20px;
    max-width: 100%;
    margin: 0 calc(-1 * var(--space-1));
    padding: 0 var(--space-1);
    border: none;
    border-radius: var(--radius-s);
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .th.numeric .sort {
    flex-direction: row-reverse;
  }
  .sort:hover,
  .sort.sorted {
    color: var(--fg);
  }
  .sort:hover {
    background: var(--hover-bg);
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
  .sort-mark.none {
    visibility: hidden;
  }
  .caret {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid currentColor;
  }
  .body {
    position: relative;
  }
  .win {
    position: absolute;
    inset: 0 0 auto 0;
  }
  .tr {
    height: var(--row-h, 24px);
    box-sizing: border-box;
    border-bottom: var(--border-w) solid var(--border-soft);
    cursor: default;
  }
  .tr:hover,
  .tr.hl {
    background: var(--hover-bg);
  }
  .tr.selected {
    background: var(--toggled-bg);
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .td {
    padding: 0 var(--space-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .td.numeric {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
    text-align: right;
  }
  .empty {
    padding: var(--space-2) var(--space-3);
    color: var(--text-muted);
  }
</style>
