<!--
  Observe task modes (owner decision D1; promoted from src/lab/workspace/observe/ModeBar.svelte,
  web/lab/PROPOSAL.md 3.1 and 6, W3): Framing · Focus · Field · Run. A radio group (one is
  always selected), icon + label; below 1240 px of toolbar width the labels drop and the
  tooltip carries them (container query on the toolbar). The selected segment follows BRAND
  8's segmented rule: --toggled-bg fill, --fg text, no brass (a layout choice is not
  instrument state). A small dot marks a mode whose layout the observer changed (Arrange ›
  Reset brings its preset back).

  - Alt+1 … Alt+4 switch (registry ids observe.mode.*, matched on KeyboardEvent.code so
    AZERTY and macOS Option work), shown in the tooltip and by the held-⌘ key hints (the
    same neutral cap as every Control: the modes are icon-only at 1280 and need teaching
    most); no inline hint on hover (it would move the segments under the pointer). The app
    never switches mode by itself.
  - Field and Run are listed but unavailable in this version: they stay focusable, and a
    press says which wave brings them (tooltip v2 press-to-explain); arrows skip nothing,
    so the observer can read why.
-->
<script lang="ts">
  import Icon from '../../components/Icon.svelte';
  import { ensureKeyHints, keyHintsVisible } from '../../app/keyhints.svelte';
  import { formatShortcut } from '../../app/shortcuts';
  import { tooltip } from '../../components/tooltip';
  import { MODES, type Mode } from './layout';
  import type { ObserveWorkspace } from './workspace.svelte';

  interface Props {
    ws: ObserveWorkspace;
    /** Shortcut spec of a mode, from the registry ("Alt+1"); undefined when unbound. */
    keyFor?: (id: string) => string | undefined;
  }

  let { ws, keyFor = () => undefined }: Props = $props();
  ensureKeyHints();

  function choose(m: Mode): void {
    ws.setMode(m);
  }

  function onKey(e: KeyboardEvent, i: number): void {
    const n = MODES.length;
    let j = -1;
    if (e.key === 'ArrowRight') j = (i + 1) % n;
    else if (e.key === 'ArrowLeft') j = (i - 1 + n) % n;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = n - 1;
    if (j < 0) return;
    e.preventDefault();
    // Moving the focus never switches to an unavailable mode; Enter / Space on it explains.
    if (!MODES[j].unavailable) choose(MODES[j].id);
    (e.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLElement>('[role="radio"]')[j]?.focus();
  }
</script>

<div class="modes" role="radiogroup" aria-label="Observe task mode">
  {#each MODES as m, i (m.id)}
    {@const on = ws.mode === m.id}
    {@const key = keyFor(m.shortcut)}
    {@const changed = ws.modifiedMode(m.id)}
    <button
      type="button"
      role="radio"
      aria-checked={on}
      aria-disabled={m.unavailable ? true : undefined}
      tabindex={on ? 0 : -1}
      class="seg"
      class:on
      class:off={!!m.unavailable}
      data-mode={m.id}
      aria-keyshortcuts={key ? key.replace('Alt', 'Alt') : undefined}
      onclick={() => choose(m.id)}
      onkeydown={(e) => onKey(e, i)}
      use:tooltip={{
        text: `${m.label}: ${m.task}. Band: ${m.band}${changed ? ' · layout changed (Arrange resets it)' : ''}`,
        shortcut: m.unavailable ? undefined : key,
        reason: m.unavailable,
        placement: 'bottom',
      }}
    >
      <Icon name={m.icon} size={16} />
      <span class="text">{m.label}</span>
      {#if changed}<span class="mod" aria-label="layout changed"></span>{/if}
      {#if key && !m.unavailable && keyHintsVisible()}<kbd class="keyhint" aria-hidden="true">{formatShortcut(key)}</kbd>{/if}
    </button>
  {/each}
</div>

<style>
  .modes {
    display: inline-flex;
    flex: none;
    padding: 2px;
    gap: 2px;
    border: var(--border-w) solid var(--border-soft);
    border-radius: var(--radius-m);
    background: var(--bg-2);
  }
  .seg {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 28px;
    padding: 0 var(--space-3) 0 var(--space-2);
    border: var(--border-w) solid transparent;
    border-radius: var(--radius-s);
    background: transparent;
    color: var(--fg-muted);
    font-size: var(--text-s);
    font-weight: var(--weight-medium);
    cursor: pointer;
    transition:
      background-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }
  .seg:hover {
    background: var(--hover-bg);
    color: var(--fg);
  }
  .text {
    color: var(--text-muted);
  }
  .seg:hover .text {
    color: var(--fg);
  }
  .seg.on {
    background: var(--toggled-bg);
    border-color: var(--border);
    color: var(--fg);
  }
  .seg.on .text {
    color: var(--fg);
  }
  /* Not in this version: readable, clearly not a choice (dashed = not current). */
  .seg.off,
  .seg.off .text {
    color: var(--fg-disabled);
    cursor: help;
  }
  .seg.off:hover {
    background: transparent;
  }
  .seg:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  /* The held-⌘ cap, as Control.svelte draws it: neutral, never brass. */
  .keyhint {
    position: absolute;
    right: -5px;
    bottom: -6px;
    z-index: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: var(--cap-h);
    height: var(--cap-h);
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 1;
    pointer-events: none;
  }
  .mod {
    position: absolute;
    top: 3px;
    right: 3px;
    width: 4px;
    height: 4px;
    border-radius: var(--radius-round);
    background: var(--fg-muted);
  }

  @container toolbar (max-width: 1240px) {
    .text {
      display: none;
    }
    .seg {
      padding: 0 var(--space-2);
    }
  }
</style>
