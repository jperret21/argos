<!--
  Command palette (Mod+K; PROPOSAL 3.1 and 6 "W2 (end)", BRAND 7),
  promoted from src/lab/workspace/overlays/CommandPalette.svelte (copied
  and adapted: the app's index, the shared layer stack, Control, Icon).

  One field over every section, Settings category and key, shortcut of the
  registry and action that has no key on purpose. Token-drawn (Night Red
  safe, no native list). Each row shows its key (the palette teaches the
  shortcuts) and, when it cannot run, why, in the button's words. A
  hardware action never runs on Enter alone: Enter opens its confirmation
  in place, a second Enter (or the danger button) confirms.

  Keys: ↑ ↓ move, Enter runs, Esc cancels a confirmation, then closes (and,
  as everywhere, aborts mount motion: the registry still sees it, D21).
  Modal layer: the app behind is inert; focus returns where it was.
-->
<script lang="ts">
  import { tick, untrack } from 'svelte';
  import { formatShortcut } from '../app/shortcuts';
  import { useApp } from '../app/state.svelte';
  import Control from '../components/Control.svelte';
  import { FocusReturn, keepKeysInside } from '../components/focus';
  import Icon from '../components/Icon.svelte';
  import { layer, portal } from '../components/layers';
  import { buildIndex } from './commandIndex';
  import { layoutGroups, rank, type Ranked } from './commands';

  const app = useApp();

  const RECENT_KEY = 'argos.palette.recent';
  function loadRecent(): string[] {
    try {
      const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
      return Array.isArray(v) ? v.filter((x) => typeof x === 'string').slice(0, 6) : [];
    } catch {
      return [];
    }
  }

  let query = $state('');
  let active = $state(0);
  let confirming: string | null = $state(null);
  let input: HTMLInputElement | undefined = $state();
  let listEl: HTMLDivElement | undefined = $state();
  let recent: string[] = $state(loadRecent());

  // A screen mounted by a section change binds its keys after the next update.
  const afterMount = async () => {
    await tick();
    await new Promise((r) => requestAnimationFrame(() => r(null)));
  };
  const index = $derived(app.paletteOpen ? buildIndex(app, afterMount) : []);
  const ranked: Ranked[] = $derived(rank(query, index, recent).slice(0, 80));

  // One index space: rows are numbered in display order (layoutGroups), and the
  // highlight, aria-activedescendant, hover and Enter all use that number.
  const layout = $derived(layoutGroups(ranked, query, recent));
  const groups = $derived(layout.groups);
  const flat = $derived(layout.flat);

  $effect(() => {
    const q = query;
    if (!app.paletteOpen) return;
    // Opening or a new query highlights its first row. The empty field opens on the first
    // row that does not move hardware (a recent Park is listed, not preselected).
    // untrack: the index re-derives on every status event; only the query resets.
    active = q.trim() ? 0 : untrack(() => Math.max(0, flat.findIndex((row) => !row.r.cmd.hardware)));
    confirming = null;
  });

  $effect(() => {
    if (!app.paletteOpen) {
      query = '';
      confirming = null;
    }
  });

  function close(): void {
    app.paletteOpen = false;
  }

  function remember(id: string): void {
    recent = [id, ...recent.filter((r) => r !== id)].slice(0, 6);
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
    } catch {
      /* blocked storage: no recent list */
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
    void Promise.resolve(c.run()).catch(() => {});
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
    } else if (e.key === 'Home' && !query) {
      e.preventDefault();
      active = 0;
      void scroll();
    } else if (e.key === 'End' && !query) {
      e.preventDefault();
      active = Math.max(0, flat.length - 1);
      void scroll();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      run(flat[active]?.r);
    } else if (e.key === 'Escape' && confirming) {
      // The field owns this Escape (data-escape="local"): cancel the confirmation only.
      e.preventDefault();
      confirming = null;
    }
  }

  async function scroll(): Promise<void> {
    await tick();
    listEl?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
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

  /** Focus in on open, keys kept inside (Escape travels), focus back on close. */
  function modal(node: HTMLElement) {
    const back = new FocusReturn(document);
    queueMicrotask(() => input?.focus({ preventScroll: true }));
    const release = keepKeysInside(node);
    const onTab = (e: KeyboardEvent) => {
      if (e.key === 'Tab') e.preventDefault(); // one field: Tab stays in it
    };
    node.addEventListener('keydown', onTab);
    return {
      destroy() {
        node.removeEventListener('keydown', onTab);
        release();
        queueMicrotask(() => back.restore());
      },
    };
  }
</script>

{#if app.paletteOpen}
  <div class="layer" use:portal use:layer={{ kind: 'dialog', modal: true, onclose: close }} use:modal>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="scrim" onclick={close}></div>
    <div class="palette" role="dialog" aria-modal="true" aria-label="Command palette">
      <div class="field">
        <Icon name="search" size="m" />
        <input
          bind:this={input}
          bind:value={query}
          onkeydown={onKey}
          data-escape={confirming ? 'local' : undefined}
          placeholder="Find an action, a section, a setting…"
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
      <div class="list" id="palette-list" role="listbox" bind:this={listEl} aria-label="Commands">
        {#each groups as g (g.name)}
          <div class="group" role="presentation">
            <p class="gname" role="presentation">{g.name}</p>
            {#each g.rows as { r, pos } (r.cmd.id)}
              {@const c = r.cmd}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <div
                class="row"
                class:active={pos === active}
                class:disabled={!!c.disabled}
                data-active={pos === active}
                id="cmd-{pos}"
                role="option"
                aria-selected={pos === active}
                aria-disabled={c.disabled ? 'true' : undefined}
                tabindex="-1"
                onmousemove={() => (active = pos)}
                onclick={() => run(r)}
              >
                <span class="ico">{#if c.icon}<Icon name={c.icon} size="s" />{/if}</span>
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
                    <Control label="Cancel" size="s" onclick={() => (confirming = null)} />
                    <Control label={c.hardware.confirm} size="s" variant="danger" aria-keyshortcuts="Enter" onclick={() => run(r)}>
                      {#snippet trailing()}<kbd class="key cap-in">Enter</kbd>{/snippet}
                    </Control>
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
        <span><kbd class="key">↑</kbd><kbd class="key">↓</kbd> move</span>
        <span><kbd class="key">Enter</kbd> run · hardware asks first</span>
        <span><kbd class="key">Esc</kbd> close (also aborts motion)</span>
        <span class="count num">{flat.length} of {index.length}</span>
      </footer>
    </div>
  </div>
{/if}

<style>
  .layer {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
  }
  .scrim {
    position: absolute;
    inset: 0;
    background: var(--scrim);
  }
  .palette {
    position: absolute;
    top: 11vh;
    left: 50%;
    display: flex;
    flex-direction: column;
    width: min(680px, calc(100vw - 32px));
    max-height: 70vh;
    transform: translateX(-50%);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-m);
    background: var(--bg);
    box-shadow: var(--shadow-2);
    animation: enter var(--duration-base) var(--ease-out);
  }
  @keyframes enter {
    from {
      opacity: 0;
      transform: translate(-50%, -4px);
    }
  }
  .field {
    flex: none;
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
    font: inherit;
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
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
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
  /* The active row: neutral fill and edge (brass is for the deliberate action itself). */
  .row.active {
    background: var(--surface);
    box-shadow: inset 2px 0 0 var(--fg);
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
    max-width: 240px;
    overflow: hidden;
    color: var(--text-muted);
    font-size: var(--text-xs);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .hw {
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    letter-spacing: var(--tracking-caps);
    text-transform: uppercase;
  }
  .key {
    display: inline-flex;
    align-items: center;
    min-width: 20px;
    height: 20px;
    padding: 0 var(--space-1);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    justify-content: center;
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
    flex: none;
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
  /* The key cap inside the confirm button: drawn on the button's own ink. */
  .key.cap-in {
    height: 16px;
    margin-left: var(--space-2);
    border-color: currentColor;
    background: transparent;
    color: inherit;
    font-size: var(--text-2xs);
  }
  .count {
    margin-left: auto;
  }
</style>
