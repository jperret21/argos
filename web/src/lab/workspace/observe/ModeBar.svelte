<!--
  Task-mode switch (functional-spaces P1): Framing · Focus · Field · Run.
  A radio group (one is always selected), icon + label; below 1360 px of
  toolbar width the labels drop and the tooltip carries them (container
  query on the toolbar). The selected segment follows BRAND 8's segmented
  rule: --toggled-bg fill, --fg text, no brass (a layout choice is not
  instrument state). A small dot marks a mode whose layout the observer
  changed (Arrange › Reset brings the preset back). Alt+1-4 switch, matched
  on KeyboardEvent.code so AZERTY and macOS Option work.
-->
<script lang="ts">
  import { formatShortcut } from '../../../lib/app/shortcuts';
  import Icon from '../../../lib/components/Icon.svelte';
  import { tooltip } from '../../../lib/components/tooltip';
  import { changedKeys, MODES, type Mode } from '../model/layout';
  import { ws } from '../model/app.svelte';

  function onKey(e: KeyboardEvent, i: number): void {
    const n = MODES.length;
    let j = -1;
    if (e.key === 'ArrowRight') j = (i + 1) % n;
    if (e.key === 'ArrowLeft') j = (i - 1 + n) % n;
    if (j < 0) return;
    e.preventDefault();
    ws.setMode(MODES[j].id);
    (e.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLElement>('[role="radio"]')[j]?.focus();
  }

  const modified = (m: Mode) => changedKeys(m, ws.layouts[m]).length > 0;
</script>

<div class="modes" role="radiogroup" aria-label="Observe task mode">
  {#each MODES as m, i (m.id)}
    {@const on = ws.mode === m.id && ws.section === 'observe'}
    <button
      type="button"
      role="radio"
      aria-checked={on}
      tabindex={on ? 0 : -1}
      class="seg"
      class:on
      aria-keyshortcuts={m.key.replace('Alt', 'Alt')}
      onclick={() => ws.setMode(m.id)}
      onkeydown={(e) => onKey(e, i)}
      use:tooltip={{ text: `${m.label}: ${m.task}`, shortcut: m.key, placement: 'bottom' }}
    >
      <Icon name={m.icon} size={16} />
      <span class="text">{m.label}</span>
      {#if modified(m.id)}<span class="mod" aria-label="layout changed"></span>{/if}
      <span class="key" aria-hidden="true">{formatShortcut(m.key).replace(/\s/g, '')}</span>
    </button>
  {/each}
</div>

<style>
  .modes {
    display: inline-flex;
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
  .seg:focus-visible {
    outline: var(--focus-ring-w) solid var(--focus-ring);
    outline-offset: 1px;
  }
  /* Key hint: only while hovering the bar, so the bar stays calm. */
  .key {
    display: none;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--text-muted);
  }
  .modes:hover .key {
    display: inline;
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
    .text,
    .modes:hover .key {
      display: none;
    }
    .seg {
      padding: 0 var(--space-2);
    }
  }
</style>
