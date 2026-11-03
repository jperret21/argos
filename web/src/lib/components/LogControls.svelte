<!--
  Tools of a log view, on one row (a drawer header or a panel header): line
  count with "UTC", level filter (All | Warnings | Errors), a Debug toggle
  when debug lines exist, search, then Copy visible lines, Save as text and
  Clear (the view only: the server keeps its log). README 3.8, 01 2.3.9.
-->
<script lang="ts">
  import type { LogFilter, LogStore } from '../app/log.svelte';
  import { type LevelFilter, LEVEL_FILTER_LABELS, logFileName, logToText } from '../app/log';
  import { int } from '../format/number';
  import IconButton from './IconButton.svelte';
  import SearchField from './SearchField.svelte';
  import Segmented from './Segmented.svelte';

  interface Props {
    store: LogStore;
    filter: LogFilter;
    /** Hide the search field (narrow regions). */
    compact?: boolean;
  }

  let { store, filter, compact = false }: Props = $props();

  const lines = $derived(store.filtered(filter.spec));
  const total = $derived(store.length);
  const hasDebug = $derived(store.counts().debug > 0 || filter.debug);
  let note = $state('');
  let noteTimer: ReturnType<typeof setTimeout> | undefined;

  const LEVELS = (['all', 'warnings', 'errors'] as const).map((value) => ({
    value,
    label: LEVEL_FILTER_LABELS[value],
  }));

  const fmt = int; // U+202F grouping from 1 000 (BRAND 5, D5)

  function say(text: string): void {
    note = text;
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => (note = ''), 2000);
  }

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(logToText(lines));
      say(`Copied ${fmt(lines.length)} lines`);
    } catch {
      say('Copy refused by the browser');
    }
  }

  function save(): void {
    const blob = new Blob([logToText(lines)], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = logFileName();
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    say(`Saved ${fmt(lines.length)} lines`);
  }
</script>

<div class="controls">
  <span class="meta num" aria-live="polite">
    {#if note}{note}{:else if lines.length !== total}{fmt(lines.length)} of {fmt(total)} · UTC{:else}{fmt(total)}
      {total === 1 ? 'line' : 'lines'} · UTC{/if}
  </span>
  <Segmented
    label="Log level"
    size="s"
    options={LEVELS}
    value={filter.level}
    onchange={(v: LevelFilter) => filter.setLevel(v)}
  />
  {#if hasDebug}
    <button
      type="button"
      class="chip"
      aria-pressed={filter.debug}
      onclick={() => filter.setDebug(!filter.debug)}>Debug</button
    >
  {/if}
  {#if !compact}
    <SearchField label="Search the log" bind:value={filter.query} width="180px" />
  {/if}
  <span class="actions">
    <IconButton
      icon="copy"
      label="Copy the visible lines"
      variant="ghost"
      size="s"
      tooltip="top"
      disabledReason={lines.length ? null : 'nothing to copy'}
      onclick={() => void copy()}
    />
    <IconButton
      icon="save"
      label="Save the visible lines as text"
      variant="ghost"
      size="s"
      tooltip="top"
      disabledReason={lines.length ? null : 'nothing to save'}
      onclick={save}
    />
    <IconButton
      icon="clear"
      label="Clear the view"
      tooltipText="Clear the view (the server keeps its log)"
      variant="ghost"
      size="s"
      tooltip="top"
      disabledReason={total ? null : 'the log is empty'}
      onclick={() => store.clear()}
    />
  </span>
</div>

<style>
  .controls {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
  }

  .meta {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .chip {
    height: 22px;
    padding: 0 var(--space-2);
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-s);
    background: var(--bg-2);
    color: var(--text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    cursor: pointer;
  }
  .chip:hover {
    color: var(--fg);
  }
  .chip[aria-pressed='true'] {
    border-color: var(--border);
    background: var(--toggled-bg);
    color: var(--fg);
  }
  .chip:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }

  .actions {
    display: inline-flex;
  }
  .actions :global(.icon-button) {
    height: 26px;
    min-width: 26px;
    padding: 0 var(--space-1);
  }
</style>
