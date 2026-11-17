<!--
  The Frames tab's tools in the drawer's tab row (07 WF-C: "FRAMES (24 lights · 0 missing) ─
  [filter…] [copy] [columns ▾]"): the count line (mono), the text filter (file, type, filter;
  "12 of 195" while a query is set), Copy (the rows shown as TSV, header first, the table's
  ⌘/Ctrl+C copies the selected row), and the column menu (checkable entries, remembered per
  viewer; UTC and File always stay). Icons only with tooltips (frequent, reversible, BRAND 7).
-->
<script lang="ts">
  import IconButton from '../../components/IconButton.svelte';
  import Menu from '../../components/Menu.svelte';
  import type { MenuChoice, MenuEntry } from '../../components/menu';
  import SearchField from '../../components/SearchField.svelte';
  import { int } from '../../format/number';
  import { countsText, FRAME_COLUMNS, type FrameColumnId } from './frames';
  import type { FramesView } from './frames.svelte';

  interface Props {
    view: FramesView;
    /** After a copy: the caller's toast ("195 frames copied"). */
    oncopied?: (rows: number) => void;
    /** Gallery: open the column menu. */
    menuOpen?: boolean;
  }

  let { view, oncopied, menuOpen = $bindable(false) }: Props = $props();

  let colsBtn = $state<HTMLButtonElement | null>(null);

  const items = $derived<MenuEntry[]>([
    { kind: 'header', label: 'Columns' },
    ...FRAME_COLUMNS.map((c) => ({
      kind: 'checkbox' as const,
      id: c.id,
      label: c.title && c.id !== 'utc' ? `${c.label} · ${c.title.split(',')[0]}` : c.label,
      checked: c.id === 'utc' || c.id === 'file' || !view.hidden.has(c.id),
      disabledReason: c.id === 'utc' || c.id === 'file' ? 'always shown (the frame)' : null,
    })),
  ]);

  const countLabel = $derived(view.query.trim() ? `${int(view.shown.length)} of ${int(view.rows.length)}` : null);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(view.tsv());
      oncopied?.(view.shown.length);
    } catch {
      /* clipboard refused: nothing claimed */
    }
  }

  function choose(item: MenuChoice): void {
    if (item.kind === 'checkbox') view.toggleColumn(item.id as FrameColumnId, !item.checked);
  }
</script>

<span class="ft">
  <span class="counts num" aria-live="polite">{countsText(view.counts)}</span>
  <span class="spacer"></span>
  <SearchField label="Filter the frames" value={view.query} placeholder="Filter: file, type, filter…" width="220px" count={countLabel} oninput={(v) => (view.query = v)} />
  <IconButton label="Flagged frames only (the ⚑ column)" icon="attention" size="s" tooltip="bottom" pressed={/\bflagged\b/.test(view.query)} onclick={() => (view.query = /\bflagged\b/.test(view.query) ? view.query.replace(/\s*\bflagged\b\s*/, ' ').trim() : `${view.query} flagged`.trim())} />
  <IconButton
    icon="copy"
    label="Copy the frames (TSV)"
    size="s"
    tooltip="top"
    disabledReason={view.shown.length ? null : 'no frame to copy'}
    onclick={() => void copy()}
  />
  <IconButton
    bind:el={colsBtn}
    icon="disclosure"
    label="Columns"
    size="s"
    tooltip="top"
    aria-haspopup="menu"
    aria-expanded={menuOpen}
    onclick={() => (menuOpen = !menuOpen)}
  />
  <Menu
    bind:open={menuOpen}
    anchor={colsBtn}
    label="Frames columns"
    {items}
    keepOpenOnCheck
    placement="bottom-end"
    onselect={choose}
  />
</span>

<style>
  .ft {
    display: flex;
    flex: 1 1 0;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .counts {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-variant-numeric: var(--numeric);
    white-space: nowrap;
  }
  .spacer {
    flex: 1;
  }
</style>
