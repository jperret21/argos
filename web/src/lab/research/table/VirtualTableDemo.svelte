<!--
  Demo 6: the Review "Frames" drawer table at night scale (spec 3.5).

  - 10 000 rows, 24 px, sticky header, constant DOM size (rowWindow), rows
    kept in $state.raw (immutable records, no deep proxy on 10 000 objects).
  - Keyboard: a single tab stop (role="grid"), arrows / PageUp / PageDown /
    Home / End move the selection and scroll it into view; Enter opens.
  - Sort by header (aria-sort), numeric columns right-aligned in mono.
  - HFD as a data bar from zero (truthful length), flags with a word.
  - Filter matches painted with the CSS Custom Highlight API (no DOM
    rewriting); a <mark> split is the fallback where it is missing.
  - Cells come from a snippet per column: one table component, any record.
-->
<script lang="ts">
  import { tick, type Snippet } from 'svelte';
  import Icon from '../../../lib/components/Icon.svelte';
  import { frameRows, type FrameRow } from '../synth';
  import { rowWindow, scrollToRow } from './virtual';

  const ROW_H = 24;
  const HEAD_H = 26;
  const COUNT = 10000;

  const all = $state.raw<FrameRow[]>(frameRows(COUNT));
  type Key = 'n' | 't' | 'filter' | 'hfd' | 'stars' | 'sky' | 'airmass' | 'fwhm' | 'flag' | 'file';
  let sort = $state<{ key: Key; dir: 1 | -1 }>({ key: 'n', dir: 1 });
  let query = $state('');
  let selected = $state(0);
  let scrollTop = $state(0);
  let viewport = $state(400);
  let scroller: HTMLDivElement;
  let renderMs = $state(0);
  let domRows = $state(0);

  const hasHighlight = typeof CSS !== 'undefined' && 'highlights' in CSS && typeof Highlight !== 'undefined';

  const rows = $derived.by(() => {
    const q = query.trim().toLowerCase();
    const list = q ? all.filter((r) => r.file.toLowerCase().includes(q) || r.flag.includes(q)) : all;
    const { key, dir } = sort;
    return [...list].sort((a, b) => {
      const x = a[key];
      const y = b[key];
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });
  });
  const win = $derived(rowWindow(scrollTop, viewport - HEAD_H, ROW_H, rows.length, 8));
  const visible = $derived(rows.slice(win.start, win.end));
  const maxHfd = 4;

  interface Col {
    key: Key;
    label: string;
    unit?: string;
    num?: boolean;
    width: string;
    cell: Snippet<[FrameRow]>;
  }

  function setSort(key: Key): void {
    sort = sort.key === key ? { key, dir: sort.dir === 1 ? -1 : 1 } : { key, dir: 1 };
  }

  async function select(i: number): Promise<void> {
    selected = Math.max(0, Math.min(rows.length - 1, i));
    const next = scrollToRow(selected, scroller.scrollTop, scroller.clientHeight, ROW_H, HEAD_H);
    if (next !== scroller.scrollTop) scroller.scrollTop = next;
    await tick();
  }

  function key(e: KeyboardEvent): void {
    const page = Math.floor((viewport - HEAD_H) / ROW_H) - 1;
    const map: Record<string, number> = {
      ArrowDown: selected + 1,
      ArrowUp: selected - 1,
      PageDown: selected + page,
      PageUp: selected - page,
      Home: 0,
      End: rows.length - 1,
    };
    if (e.key in map) {
      e.preventDefault();
      void select(map[e.key]);
    }
  }

  // Render time: from a change of the window to the DOM being updated.
  let t0 = 0;
  $effect.pre(() => {
    void visible;
    t0 = performance.now();
  });
  $effect(() => {
    void visible;
    renderMs = performance.now() - t0;
    domRows = scroller.querySelectorAll('[role="row"]').length - 1;
  });

  // Filter matches via the Custom Highlight API: ranges over the rendered text nodes.
  $effect(() => {
    void visible;
    const q = query.trim().toLowerCase();
    if (!hasHighlight) return;
    const ranges: Range[] = [];
    if (q) {
      for (const el of scroller.querySelectorAll<HTMLElement>('[data-hl]')) {
        const node = el.firstChild;
        if (!node || node.nodeType !== Node.TEXT_NODE) continue;
        const text = (node.textContent ?? '').toLowerCase();
        let at = text.indexOf(q);
        while (at >= 0) {
          const r = new Range();
          r.setStart(node, at);
          r.setEnd(node, at + q.length);
          ranges.push(r);
          at = text.indexOf(q, at + q.length);
        }
      }
    }
    CSS.highlights.set('lab-match', new Highlight(...ranges));
    return () => CSS.highlights.delete('lab-match');
  });

  function splitMatch(text: string): [string, string, string] | null {
    const q = query.trim().toLowerCase();
    if (!q || hasHighlight) return null;
    const at = text.toLowerCase().indexOf(q);
    if (at < 0) return null;
    return [text.slice(0, at), text.slice(at, at + q.length), text.slice(at + q.length)];
  }

  const utc = (t: number) => new Date(t * 1000).toISOString().slice(11, 19);

  // Snippets declared at the top level of the markup are usable here.
  const cols: Col[] = [
    { key: 'n', label: '#', num: true, width: '64px', cell: nCell },
    { key: 't', label: 'UTC', num: true, width: '86px', cell: tCell },
    { key: 'filter', label: 'Filter', width: '64px', cell: filterCell },
    { key: 'hfd', label: 'HFD', unit: 'px', num: true, width: '120px', cell: hfdCell },
    { key: 'stars', label: 'Stars', num: true, width: '64px', cell: starsCell },
    { key: 'sky', label: 'Sky', unit: 'ADU', num: true, width: '80px', cell: skyCell },
    { key: 'airmass', label: 'Airmass', num: true, width: '80px', cell: amCell },
    { key: 'fwhm', label: 'FWHM', unit: '″', num: true, width: '76px', cell: fwhmCell },
    { key: 'flag', label: 'Flag', width: '86px', cell: flagCell },
    { key: 'file', label: 'File', width: 'minmax(240px, 1fr)', cell: fileCell },
  ];
</script>

{#snippet num(v: string)}<span class="num">{v}</span>{/snippet}
{#snippet nCell(r: FrameRow)}{@render num(String(r.n))}{/snippet}
{#snippet tCell(r: FrameRow)}{@render num(utc(r.t))}{/snippet}
{#snippet filterCell(r: FrameRow)}<span class="tag">{r.filter}</span>{/snippet}
{#snippet hfdCell(r: FrameRow)}
  <span class="bar" style:--w="{Math.min(1, r.hfd / maxHfd) * 100}%"></span>{@render num(r.hfd.toFixed(2))}
{/snippet}
{#snippet starsCell(r: FrameRow)}{@render num(String(r.stars))}{/snippet}
{#snippet skyCell(r: FrameRow)}{@render num(r.sky.toFixed(0))}{/snippet}
{#snippet amCell(r: FrameRow)}{@render num(r.airmass.toFixed(3))}{/snippet}
{#snippet fwhmCell(r: FrameRow)}{@render num(r.fwhm.toFixed(2))}{/snippet}
{#snippet flagCell(r: FrameRow)}
  {#if r.flag}<span class="flag"><span class="lab-dot busy"></span><span data-hl>{r.flag}</span></span>{/if}
{/snippet}
{#snippet fileCell(r: FrameRow)}
  {@const parts = splitMatch(r.file)}
  {#if parts}<span class="file num">{parts[0]}<mark>{parts[1]}</mark>{parts[2]}</span>{:else}<span class="file num" data-hl>{r.file}</span>{/if}
{/snippet}

<div class="demo">
  <div class="toolbar">
    <span class="lab-eyebrow">Frames</span>
    <label class="search">
      <Icon name="search" size={16} />
      <input data-shot="filter" placeholder="Filter file or flag  ( / )" bind:value={query} aria-label="Filter frames" />
    </label>
    <span class="grow"></span>
    <ul class="lab-facts" data-lab-facts={JSON.stringify({ hasHighlight, domRows, renderMs })}>
      <li><b>{rows.length.toLocaleString('en-GB')}</b> rows</li>
      <li><b>{domRows}</b> in the DOM</li>
      <li>window update <b>{renderMs.toFixed(1)}</b> ms</li>
      <li class={hasHighlight ? 'yes' : 'no'}>highlights: <b>{hasHighlight ? 'CSS Custom Highlight API' : '<mark> fallback'}</b></li>
    </ul>
  </div>

  <div
    class="scroller"
    bind:this={scroller}
    bind:clientHeight={viewport}
    onscroll={() => (scrollTop = scroller.scrollTop)}
    style:--cols={cols.map((c) => c.width).join(' ')}
  >
    <div
      class="grid"
      role="grid"
      tabindex="0"
      aria-label="Frames of the session"
      aria-rowcount={rows.length + 1}
      aria-colcount={cols.length}
      aria-activedescendant="lab-row-{selected}"
      onkeydown={key}
      style:height="{win.total + HEAD_H}px"
    >
      <div class="row head" role="row" aria-rowindex={1}>
        {#each cols as c (c.key)}
          <span
            class="cell"
            class:right={c.num}
            role="columnheader"
            aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}
          >
            <button onclick={() => setSort(c.key)}>
              {c.label}{#if c.unit}<small>{c.unit}</small>{/if}
              {#if sort.key === c.key}<Icon name={sort.dir === 1 ? 'move-up' : 'move-down'} size={16} />{/if}
            </button>
          </span>
        {/each}
      </div>
      <div class="body" style:transform="translateY({win.offset}px)">
        {#each visible as r, j (r.n)}
          {@const i = win.start + j}
          <div
            class="row"
            class:sel={i === selected}
            class:flagged={!!r.flag}
            role="row"
            id="lab-row-{i}"
            aria-rowindex={i + 2}
            aria-selected={i === selected}
            tabindex="-1"
            onclick={() => void select(i)}
            onkeydown={key}
          >
            {#each cols as c (c.key)}
              <span class="cell" class:right={c.num} role="gridcell">{@render c.cell(r)}</span>
            {/each}
          </div>
        {/each}
      </div>
    </div>
  </div>
</div>

<style>
  .demo {
    display: flex;
    flex-direction: column;
    height: 100%;
    border-top: var(--border-w) solid var(--border);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 40px;
    padding: 0 var(--space-3);
    border-bottom: var(--border-w) solid var(--border);
    flex: none;
  }
  .grow {
    flex: 1;
  }
  .search {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 300px;
    height: var(--input-h);
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--fg-muted);
  }
  .search input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--fg);
    outline: none;
  }
  .search:focus-within {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  .search input::placeholder {
    color: var(--text-muted);
  }

  .scroller {
    flex: 1;
    min-height: 0;
    overflow: auto;
    background: var(--bg);
  }
  .grid {
    position: relative;
    min-width: 100%;
    font-size: var(--text-s);
  }
  .grid:focus-visible {
    outline-offset: -2px;
  }
  .row {
    display: grid;
    grid-template-columns: var(--cols);
    align-items: center;
    height: 24px;
    padding: 0 var(--space-3);
    border-bottom: 1px solid var(--border-soft);
    column-gap: var(--space-3);
  }
  .row.head {
    position: sticky;
    top: 0;
    z-index: 2;
    height: 26px;
    background: var(--bg-2);
    border-bottom: 1px solid var(--border);
  }
  .head button {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
    cursor: pointer;
  }
  .head [aria-sort='ascending'] button,
  .head [aria-sort='descending'] button {
    color: var(--fg);
  }
  .head small {
    margin-left: 3px;
    text-transform: none;
    letter-spacing: 0;
  }
  .body {
    will-change: transform;
  }
  .body .row:hover {
    background: var(--hover-bg);
  }
  .row.sel,
  .row.sel:hover {
    background: var(--selection-bg);
    color: var(--selection-fg);
  }
  .grid:focus-visible .row.sel {
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .cell {
    position: relative;
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    color: var(--fg);
  }
  .cell.right {
    text-align: right;
  }
  .head .cell.right {
    display: flex;
    justify-content: flex-end;
  }
  .tag {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .bar {
    position: absolute;
    left: 0;
    top: 50%;
    width: var(--w);
    height: 12px;
    margin-top: -6px;
    background: color-mix(in srgb, var(--fg-muted) 22%, transparent);
    border-right: 1px solid var(--fg-muted);
  }
  .bar + :global(.num) {
    position: relative;
  }
  .flag {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .file {
    color: var(--text-muted);
  }
  mark {
    background: color-mix(in srgb, var(--accent) 35%, transparent);
    color: var(--fg);
  }
</style>
