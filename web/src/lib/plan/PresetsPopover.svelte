<!--
  Presets popover (06 §2.2 rows 1.8 #2, 1.11, "delete preset", §2.3.4; M75, M77; Q-P4): the
  toolbar's [bookmark Presets] opens the server's list (the presets folder, Qt's format).

  - A filter field, then one row per preset: its name, what it holds (object, frames,
    estimate) and its date; Enter or a click opens it as the draft (the screen asks first
    when that replaces unsaved steps), Delete or the row's [remove] deletes it (Undo toast).
    A file Qt cannot read is listed with the reason and cannot be opened.
  - Footer: [open-file Open file…] (FilePicker, A61).
  - While a run is active opening is refused with the reason (Q-P9); deleting stays.
-->
<script lang="ts">
  import type { PresetInfo } from '../api/plan';
  import Control from '../components/Control.svelte';
  import Popover from '../components/Popover.svelte';
  import SearchField from '../components/SearchField.svelte';
  import { tooltip } from '../components/tooltip';
  import { middleEllipsis } from '../format/path';
  import { duration } from '../format/time';

  interface Props {
    presets: readonly PresetInfo[];
    directory?: string | null;
    error?: string | null;
    /** Why a preset cannot be opened now (a run is active). */
    openReason?: string | null;
    /** The preset being opened or deleted (its row is busy). */
    busy?: string | null;
    onopen: (name: string) => void;
    ondelete: (name: string) => void;
    onfile: () => void;
    onshow?: () => void;
    open?: boolean;
    preview?: boolean;
    /** Gallery: the filter text. */
    filter?: string;
  }

  let { presets, directory = null, error = null, openReason = null, busy = null, onopen, ondelete, onfile, onshow, open = $bindable(false), preview = false, filter = $bindable('') }: Props = $props();

  const id = `presets-${Math.random().toString(36).slice(2, 8)}`;
  let button: HTMLElement | undefined = $state();
  let list: HTMLUListElement | undefined = $state();

  const shown = $derived.by(() => {
    const q = filter.trim().toLowerCase();
    return q ? presets.filter((p) => p.name.toLowerCase().includes(q) || (p.object_name ?? '').toLowerCase().includes(q)) : presets;
  });

  const what = (p: PresetInfo) =>
    [p.object_name || null, p.total_frames !== null ? `${p.total_frames} frame${p.total_frames === 1 ? '' : 's'}` : null, p.estimate_s !== null ? `≈ ${duration(p.estimate_s)}` : null]
      .filter(Boolean)
      .join(' · ');
  const date = (iso: string | null) => (iso ? iso.slice(0, 10) : '');

  function onRowKey(e: KeyboardEvent, p: PresetInfo, i: number): void {
    const rows = list ? [...list.querySelectorAll<HTMLElement>('li[data-row] .open')] : [];
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      rows[Math.max(0, Math.min(rows.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus();
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      ondelete(p.name);
    }
  }
</script>

{#snippet body()}
  <div class="body">
    <SearchField label="Filter presets" placeholder="Filter presets" bind:value={filter} count={filter ? `${shown.length} of ${presets.length}` : null} />
    {#if error}
      <p class="msg bad" role="alert">{error}</p>
    {:else if !presets.length}
      <p class="msg">No presets yet. Save the current plan with Save…, or open a preset file.</p>
    {:else if !shown.length}
      <p class="msg">No preset matches “{filter.trim()}”.</p>
    {:else}
      <ul class="list" bind:this={list} aria-label="Presets">
        {#each shown as p, i (p.name)}
          {@const blocked = p.error ? `cannot be read: ${p.error}` : openReason}
          <li data-row class:bad-row={!!p.error}>
            <button
              type="button"
              class="open"
              aria-disabled={blocked ? true : undefined}
              aria-busy={busy === p.name || undefined}
              aria-describedby="{id}-w{i}"
              onkeydown={(e) => onRowKey(e, p, i)}
              onclick={() => {
                if (!blocked) onopen(p.name);
              }}
              use:tooltip={{ text: `Open ${p.name} as the plan`, reason: blocked, placement: 'left' }}
            >
              <span class="name">{p.name}</span>
              <span class="date num">{date(p.modified_utc)}</span>
              <span class="what" class:bad={!!p.error} id="{id}-w{i}">{p.error ? p.error : what(p)}</span>
            </button>
            <span class="act">
              <Control icon="remove" label="Delete preset {p.name}" size="xs" variant="ghost" tooltip="left" tooltipText="Delete (Undo for 6 s)" busy={busy === p.name} onclick={() => ondelete(p.name)} />
            </span>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/snippet}

{#snippet footer()}
  <div class="foot">
    <Control icon="open-file" label="Open file…" showLabel size="s" variant="ghost" disabledReason={openReason} onclick={onfile} />
    {#if directory}<span class="dir" use:tooltip={{ text: directory, placement: 'top' }}>{middleEllipsis(directory, 34)}</span>{/if}
  </div>
{/snippet}

{#if preview}
  <Popover open title="Presets" preview width={360} {footer}>{@render body()}</Popover>
{:else}
  <span bind:this={button} class="anchor">
    <Control
      icon="bookmark"
      label="Presets"
      showLabel
      size="s"
      variant="ghost"
      tooltip="none"
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls={id}
      onclick={() => {
        open = !open;
        if (open) onshow?.();
      }}
    />
  </span>
  <Popover bind:open anchor={button} title="Presets" {id} width={360} placement="bottom-start" {footer}>{@render body()}</Popover>
{/if}

<style>
  .anchor {
    display: inline-flex;
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .msg {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-s);
    line-height: var(--leading-relaxed);
  }
  .msg.bad,
  .bad {
    color: var(--fg);
  }
  .list {
    max-height: 300px;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }
  li {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    border-radius: var(--radius-s);
  }
  li:hover {
    background: var(--hover-bg);
  }
  .open {
    display: grid;
    flex: 1;
    min-width: 0;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: 'name date' 'what what';
    align-items: center;
    column-gap: var(--space-2);
    padding: var(--space-1) var(--space-1) var(--space-1) var(--space-2);
    border: 0;
    border-radius: var(--radius-s);
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .open:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: -2px;
  }
  .open[aria-disabled='true'] {
    cursor: default;
  }
  .open[aria-disabled='true'] .name {
    color: var(--fg-muted);
  }
  .name {
    grid-area: name;
    overflow: hidden;
    color: var(--fg);
    font-size: var(--text-m);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .date {
    grid-area: date;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .what {
    grid-area: what;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .act {
    flex: none;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: var(--numeric);
  }
  .foot {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .dir {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
