<!--
  Command palette (Mod+K, functional-spaces P9): one field over every
  action, mode, panel, star, setting and the app's shortcut registry.
  Token-drawn (Night Red safe, no native list). Each row shows its shortcut
  (the palette teaches the keys) and, when it cannot run, why. A hardware
  action never runs on Enter alone: Enter opens its confirmation in place
  (the same words as the button), a second Enter confirms.
  Keys: Up / Down move, Enter runs, Esc closes (and still aborts motion).
-->
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { formatShortcut } from '../../../lib/app/shortcuts';
  import Button from '../../../lib/components/Button.svelte';
  import { GROUP_ORDER, rank, type Ranked } from '../model/commands';
  import { sim, ws } from '../model/app.svelte';
  import LabIcon from '../ui/LabIcon.svelte';
  import { buildIndex } from './commandIndex';

  interface Props {
    initial?: string;
  }
  let { initial = '' }: Props = $props();

  const RECENT_KEY = 'argos.lab.workspace.recent';
  function loadRecent(): string[] {
    try {
      const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
      return Array.isArray(v) ? v.filter((x) => typeof x === 'string').slice(0, 6) : [];
    } catch {
      return [];
    }
  }

  // svelte-ignore state_referenced_locally
  let query = $state(initial);
  let active = $state(0);
  let confirming: string | null = $state(null);
  let input: HTMLInputElement;
  let list: HTMLDivElement;
  const recent = loadRecent();

  const index = $derived(buildIndex(ws, sim));
  const ranked: Ranked[] = $derived(rank(query, index, recent).slice(0, 60));

  // Group for display: with an empty query, recent first then by group; with
  // a query, by score but headed by group in the order of the first hit.
  const groups = $derived.by(() => {
    const out: { name: string; rows: { r: Ranked; i: number }[] }[] = [];
    const byName = new Map<string, { name: string; rows: { r: Ranked; i: number }[] }>();
    const order = query.trim()
      ? [...new Set(ranked.map((r) => r.cmd.group))]
      : ['Recent', ...GROUP_ORDER];
    const rows = ranked.map((r, i) => ({ r, i }));
    for (const row of rows) {
      const name = !query.trim() && recent.includes(row.r.cmd.id) && row.r.score > 0 ? 'Recent' : row.r.cmd.group;
      if (!byName.has(name)) byName.set(name, { name, rows: [] });
      byName.get(name)!.rows.push(row);
    }
    for (const n of order) if (byName.has(n)) out.push(byName.get(n)!);
    return out;
  });
  const flat = $derived(groups.flatMap((g) => g.rows));

  $effect(() => {
    void query;
    active = 0;
    confirming = null;
  });

  function current(): Ranked | undefined {
    return flat[active]?.r;
  }

  function close(): void {
    ws.overlay = 'none';
  }

  function remember(id: string): void {
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...recent.filter((r) => r !== id)].slice(0, 6)));
    } catch {
      /* ignore */
    }
  }

  function run(r: Ranked | undefined): void {
    if (!r) return;
    const c = r.cmd;
    if (c.disabled) return;
    if (c.hardware && confirming !== c.id) {
      confirming = c.id;
      return;
    }
    remember(c.id);
    close();
    c.run();
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      active = Math.min(flat.length - 1, active + 1);
      confirming = null;
      void scroll();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = Math.max(0, active - 1);
      confirming = null;
      void scroll();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      run(current());
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (confirming) confirming = null;
      else close();
    }
  }

  async function scroll(): Promise<void> {
    await tick();
    list?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
  }

  function highlight(text: string, hits: number[]): { t: string; on: boolean }[] {
    if (!hits.length) return [{ t: text, on: false }];
    const set = new Set(hits);
    const out: { t: string; on: boolean }[] = [];
    for (let i = 0; i < text.length; i++) {
      const on = set.has(i);
      const last = out[out.length - 1];
      if (last && last.on === on) last.t += text[i];
      else out.push({ t: text[i], on });
    }
    return out;
  }

  onMount(() => {
    input.focus();
    input.setSelectionRange(query.length, query.length);
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="scrim" onclick={close}></div>
<div class="palette" role="dialog" aria-modal="true" aria-label="Command palette">
  <div class="field">
    <LabIcon name="search" size={20} />
    <input
      bind:this={input}
      bind:value={query}
      onkeydown={onKey}
      placeholder="Find an action, a mode, a star, a setting…"
      role="combobox"
      aria-expanded="true"
      aria-controls="palette-list"
      aria-activedescendant={flat[active] ? `cmd-${active}` : undefined}
      aria-autocomplete="list"
      spellcheck="false"
      autocomplete="off"
    />
    <kbd class="key">Esc</kbd>
  </div>
  <div class="list" id="palette-list" role="listbox" bind:this={list} aria-label="Commands">
    {#each groups as g (g.name)}
      <div class="group" role="presentation">
        <p class="gname lab-caps" role="presentation">{g.name}</p>
        {#each g.rows as { r, i } (r.cmd.id)}
          {@const c = r.cmd}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div
            class="row"
            class:active={i === active}
            class:disabled={!!c.disabled}
            data-active={i === active}
            id="cmd-{i}"
            role="option"
            aria-selected={i === active}
            aria-disabled={c.disabled ? 'true' : undefined}
            tabindex="-1"
            onmousemove={() => (active = i)}
            onclick={() => run(r)}
          >
            <span class="ico">{#if c.icon}<LabIcon name={c.icon} size={16} />{/if}</span>
            <span class="main">
              <span class="title">
                {#each highlight(c.title, r.hits) as part, j (j)}{#if part.on}<mark>{part.t}</mark>{:else}{part.t}{/if}{/each}
              </span>
              {#if c.disabled}<span class="why">{c.disabled}</span>{/if}
            </span>
            {#if c.hint && !c.disabled}<span class="hint">{c.hint}</span>{/if}
            {#if c.hardware && !c.disabled}<span class="hw">confirm</span>{/if}
            {#if c.keys}<kbd class="key">{formatShortcut(c.keys)}</kbd>{/if}
          </div>
          {#if confirming === c.id && c.hardware}
            <div class="confirm" role="group" aria-label={c.hardware.question}>
              <p><strong>{c.hardware.question}</strong> {c.hardware.consequence}</p>
              <div class="btns">
                <Button label="Cancel" size="s" onclick={() => (confirming = null)} />
                <Button label="{c.hardware.confirm} · Enter" size="s" variant="danger" onclick={() => run(r)} />
              </div>
            </div>
          {/if}
        {/each}
      </div>
    {:else}
      <p class="none">Nothing matches “{query}”.</p>
    {/each}
  </div>
  <footer>
    <span><kbd class="key">Up</kbd><kbd class="key">Down</kbd> move</span>
    <span><kbd class="key">Enter</kbd> run · hardware asks first</span>
    <span><kbd class="key">Esc</kbd> close (also aborts motion)</span>
    <span class="count num">{flat.length} of {index.length}</span>
  </footer>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    background: var(--scrim);
  }
  .palette {
    position: fixed;
    top: 11vh;
    left: 50%;
    z-index: calc(var(--z-modal) + 1);
    display: flex;
    flex-direction: column;
    width: min(680px, calc(100vw - 32px));
    max-height: 70vh;
    transform: translateX(-50%);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--lab-elev-float);
  }
  .field {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: 52px;
    padding: 0 var(--space-4);
    border-bottom: var(--border-w) solid var(--border-soft);
    color: var(--fg-muted);
  }
  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    border: none;
    outline: none;
    background: transparent;
    color: var(--fg);
    font-size: 16px;
  }
  input::placeholder {
    color: var(--text-muted);
  }
  .list {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--space-1) var(--space-2) var(--space-2);
    scrollbar-color: var(--border) var(--bg);
  }
  .gname {
    margin: var(--space-3) var(--space-2) var(--space-1);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 34px;
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-s);
    color: var(--fg);
    cursor: pointer;
  }
  .row.active {
    background: var(--surface);
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .ico {
    display: inline-flex;
    width: 16px;
    color: var(--fg-muted);
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .title {
    font-size: var(--text-m);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  mark {
    background: transparent;
    color: var(--fg);
    font-weight: var(--weight-semibold);
    text-decoration: underline;
    text-decoration-color: var(--fg-muted);
    text-underline-offset: 3px;
  }
  .disabled .title {
    color: var(--text-muted);
  }
  .why {
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .hint {
    color: var(--text-muted);
    font-size: var(--text-xs);
    white-space: nowrap;
    max-width: 240px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hw {
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .confirm {
    margin: var(--space-1) var(--space-2) var(--space-2) 34px;
    padding: var(--space-3);
    border: var(--border-w) solid var(--danger);
    border-radius: var(--radius-s);
    background: var(--surface);
  }
  .confirm p {
    margin: 0 0 var(--space-2);
    color: var(--fg);
    font-size: var(--text-s);
  }
  .btns {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
  }
  .none {
    padding: var(--space-5);
    color: var(--text-muted);
    text-align: center;
  }
  footer {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-2) var(--space-4);
    border-top: var(--border-w) solid var(--border-soft);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  footer .key {
    margin-right: 2px;
  }
  .count {
    margin-left: auto;
    font-family: var(--font-mono);
  }
</style>
