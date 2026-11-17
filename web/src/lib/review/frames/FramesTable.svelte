<!--
  The Review Frames drawer tab (07 1.6, 2.2 row 1.6, WF-C; README M90, 3.5; PROPOSAL 6 W7:
  the virtual table promoted from src/lab/research/table): the session's frames, read-only.

  - A click (or ↑ ↓) selects a frame: `onselect` puts the time cursor on every plot at it.
  - Enter or a double click opens it in the frame inspector (R2) via `onactivate`; a missing
    frame never opens: `onmissing` says "File not found: {filename}" (the caller's toast).
  - ⌘/Ctrl+C copies the selected row (or every row) as TSV; the tab row's Copy copies the
    rows shown.
  - Missing frames stay listed, dimmed, with "missing" in the File column.
  - The file name keeps its end (the frame counter) with a middle ellipsis; the full name is
    in the tooltip and in the copy.
-->
<script lang="ts">
  import { tooltip } from '../../components/tooltip';
  import VirtualTable from '../../components/VirtualTable.svelte';
  import { cellText, type Column } from '../../components/table';
  import { middleEllipsis } from '../../format/path';
  import { openReason, type FrameRow } from './frames';
  import type { FramesView } from './frames.svelte';

  interface Props {
    view: FramesView;
    /** Height of the table (the drawer's body). */
    height?: string;
    /** A row became the selection (null: none): the plots' time cursor follows. */
    onselect?: (row: FrameRow | null) => void;
    /** Enter / double click on a frame whose FITS is on disk: open R2 there. */
    onactivate?: (row: FrameRow) => void;
    /** Enter / double click on a missing frame: the reason, for a toast. */
    onmissing?: (row: FrameRow, reason: string) => void;
    oncopy?: (tsv: string, rows: number) => void;
    /** Loading: the session is opening (the rows come with it). */
    loading?: boolean;
    /** Empty-state text (an imported CSV has no frames). */
    empty?: string;
  }

  let { view, height = '100%', onselect, onactivate, onmissing, oncopy, loading = false, empty = 'No frame recorded in this session.' }: Props = $props();

  function activate(row: FrameRow): void {
    const why = openReason(row);
    if (why) onmissing?.(row, why);
    else onactivate?.(row);
  }
</script>

<div class="frames" aria-busy={loading || undefined}>
  <VirtualTable
    label="Frames of the session"
    columns={view.columns}
    rows={view.shown}
    rowKey={(r) => r.key}
    bind:selected={view.selected}
    bind:sort={() => view.sort, (s) => view.setSort(s)}
    {height}
    empty={loading ? 'Reading the session…' : view.rows.length ? 'No frame matches the filter.' : empty}
    muted={(r) => r.missing}
    {onselect}
    onactivate={activate}
    {oncopy}
  >
    {#snippet cell(row: FrameRow, col: Column<FrameRow>)}
      {#if col.id === 'file'}
        <span class="file" use:tooltip={{ text: row.path ?? row.filename, reason: openReason(row), placement: 'top' }}>
          <span class="name num">{middleEllipsis(row.filename, 40)}</span>
          {#if row.missing}<span class="tag">missing</span>{/if}
        </span>
      {:else}
        {cellText(col, row)}
      {/if}
    {/snippet}
  </VirtualTable>
</div>

<style>
  .frames {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .file {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-2);
    max-width: 100%;
    min-width: 0;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }
  .tag {
    flex: none;
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: var(--tracking-caps);
  }
</style>
