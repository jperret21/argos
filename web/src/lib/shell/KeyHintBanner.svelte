<!--
  The command palette affordance while Cmd / Ctrl is held alone (key hints,
  BRAND 7 amendment; design review): the palette has no button, so its key
  is shown where every screen can see it, in a neutral chip above the status
  bar, with the shortcuts sheet's key. Neutral ink, never brass; no pointer
  events (it disappears when the modifier is released).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ensureKeyHints, keyHintsVisible } from '../app/keyhints.svelte';
  import { formatShortcut } from '../app/shortcuts';
  import { useApp } from '../app/state.svelte';

  const app = useApp();
  onMount(() => ensureKeyHints());
  const palette = $derived(app.shortcuts.keyFor('palette.open') ?? 'Mod+K');
</script>

{#if keyHintsVisible() && !app.paletteOpen}
  <div class="banner" aria-hidden="true">
    <span><kbd class="cap">{formatShortcut(palette)}</kbd> Command palette</span>
    <span><kbd class="cap">?</kbd> Keyboard shortcuts</span>
  </div>
{/if}

<style>
  .banner {
    position: fixed;
    bottom: calc(var(--statusbar-h) + var(--space-3));
    left: calc(var(--sidebar-w) + (100vw - var(--sidebar-w)) / 2);
    z-index: var(--z-tooltip);
    display: flex;
    gap: var(--space-4);
    padding: var(--space-1) var(--space-3);
    border: var(--border-w) solid var(--border);
    border-radius: var(--radius-s);
    background: var(--surface);
    color: var(--fg);
    font-size: var(--text-xs);
    box-shadow: var(--shadow-1);
    transform: translateX(-50%);
    pointer-events: none;
    animation: in var(--duration-fast) var(--ease-out);
  }
  span {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .cap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: var(--cap-h);
    height: var(--cap-h);
    padding: 0 3px;
    border: var(--border-w) solid var(--border);
    border-bottom-width: 2px;
    border-radius: var(--radius-s);
    background: var(--bg-2);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    font-weight: var(--weight-medium);
    line-height: 1;
  }
  @keyframes in {
    from {
      opacity: 0;
    }
  }
</style>
